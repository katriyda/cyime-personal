#!/usr/bin/env python3
"""Patch an upstream CyIME checkout into one independently-updatable package.

The repository intentionally does not vendor upstream source. CI checks out the
latest stable upstream release into a temporary directory and applies only the
release identity needed for an independent APK:

- applicationId and visible app/IME label
- update repository, release tag prefix and signing-certificate allowlist
- versionName / versionCode used for this package

Every anchor must match exactly once. If upstream moves an anchor, the build
fails instead of silently publishing an APK that updates from the wrong place.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

FAILS: list[str] = []


def fail(message: str) -> None:
    FAILS.append(message)


def read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        fail(f"找不到文件: {relative}")
        return ""
    return path.read_text(encoding="utf-8")


def write(root: Path, relative: str, text: str) -> None:
    (root / relative).write_text(text, encoding="utf-8", newline="\n")


def replace_once(
    root: Path,
    relative: str,
    pattern: str,
    replacement: str | Callable[[re.Match[str]], str],
    note: str,
    *,
    regex_flags: int = re.MULTILINE,
) -> None:
    """Replace exactly once; zero or multiple matches are fatal."""
    text = read(root, relative)
    if not text:
        return
    updated, count = re.subn(pattern, replacement, text, count=1, flags=regex_flags)
    if count != 1:
        fail(f"锚点不匹配（{note}）: {relative} :: {pattern}")
        return
    if updated != text:
        write(root, relative, updated)


def load_packages(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"读取包名清单失败: {path}: {error}", file=sys.stderr)
        raise SystemExit(2)
    packages = payload.get("packages")
    if not isinstance(packages, list) or not packages:
        print("packages.json 必须包含非空 packages 数组", file=sys.stderr)
        raise SystemExit(2)
    seen: dict[str, set[str]] = {"id": set(), "applicationId": set(), "suffix": set()}
    for item in packages:
        if not isinstance(item, dict):
            raise SystemExit("packages 每项必须是对象")
        for key in ("id", "applicationId", "label"):
            if not item.get(key):
                raise SystemExit(f"包名项缺少字段 {key}: {item}")
        package_id = str(item["id"])
        application_id = str(item["applicationId"])
        suffix = str(item.get("suffix") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_.]*", application_id):
            raise SystemExit(f"非法 applicationId: {application_id}")
        if suffix and not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", suffix):
            raise SystemExit(f"非法 suffix: {suffix}")
        for key, value in (("id", package_id), ("applicationId", application_id), ("suffix", suffix)):
            if value in seen[key]:
                raise SystemExit(f"重复的 {key}: {value}")
            seen[key].add(value)
    return payload


def package_by_id(payload: dict, package_id: str) -> dict:
    for item in payload["packages"]:
        if item["id"] == package_id:
            return item
    raise SystemExit(f"未知包 id: {package_id}")


def patch_identity(root: Path, package: dict) -> None:
    app_id = package["applicationId"]
    label = package["label"]
    replace_once(
        root,
        "app/build.gradle.kts",
        r'^(\s*)applicationId = "com\.cyletix\.cyime"$',
        rf'\1applicationId = "{app_id}"',
        "applicationId",
    )
    replace_once(
        root,
        "app/src/main/res/values/strings.xml",
        r'<string name="app_name" translatable="false">CyIME</string>',
        f'<string name="app_name" translatable="false">{label}</string>',
        "app_name",
    )
    replace_once(
        root,
        "app/src/main/AndroidManifest.xml",
        r'(android:name="com\.kingzcheung\.xime\.service\.XimeInputMethodService"\s*\n'
        r'\s*android:exported="true"\s*\n'
        r'\s*android:label=)"CyIME"',
        rf'\1"{label}"',
        "IME service label",
    )
    replace_once(
        root,
        "app/src/main/AndroidManifest.xml",
        r'<action android:name="com\.cyletix\.cyime\.DEV_LEARNING" />',
        f'<action android:name="{app_id}.DEV_LEARNING" />',
        "DEV_LEARNING action",
    )
    replace_once(
        root,
        "app/src/main/java/com/kingzcheung/xime/service/DevLearningReceiver.kt",
        r'const val ACTION = "com\.cyletix\.cyime\.DEV_LEARNING"',
        f'const val ACTION = "{app_id}.DEV_LEARNING"',
        "DevLearningReceiver ACTION",
    )
    replace_once(
        root,
        "app/src/main/java/com/kingzcheung/xime/keyboard/KeyboardPanelLaunch.kt",
        r'const val PREVIEW_EDITOR = "com\.cyletix\.cyime\.settings\.preview"',
        f'const val PREVIEW_EDITOR = "{app_id}.settings.preview"',
        "PREVIEW_EDITOR",
    )


def patch_update_channel(root: Path, repo: str, suffix: str) -> None:
    """Point updates at this repository and accept only this package's tags."""
    catalog = "app/src/main/java/com/kingzcheung/xime/update/AppUpdateCatalog.kt"
    updater = "app/src/main/java/com/kingzcheung/xime/update/AppUpdater.kt"
    prefix = f"{suffix}-" if suffix else ""
    replace_once(
        root,
        catalog,
        r'const val RELEASES_API = "https://api\.github\.com/repos/[^"]+?/releases\?per_page=30"',
        f'const val RELEASES_API = "https://api.github.com/repos/{repo}/releases?per_page=100"',
        "RELEASES_API",
    )
    replace_once(
        root,
        catalog,
        r'const val RELEASES_PAGE = "https://github\.com/[^"]+?/releases"',
        f'const val RELEASES_PAGE = "https://github.com/{repo}/releases"',
        "RELEASES_PAGE",
    )
    replace_once(
        root,
        catalog,
        r'fun githubAssetUrl\(tag: String, name: String\) = "https://github\.com/[^"]+?/releases/download/\$tag/\$name"',
        f'fun githubAssetUrl(tag: String, name: String) = "https://github.com/{repo}/releases/download/$tag/$name"',
        "githubAssetUrl",
    )
    # There is no per-package mirror. Never expose the upstream mirror.
    replace_once(
        root,
        catalog,
        r'const val MODELSCOPE_RELEASES = DownloadMirrors\.CYIME_MODELSCOPE \+ "app/releases\.json"',
        'const val MODELSCOPE_RELEASES = ""',
        "MODELSCOPE_RELEASES",
    )
    replace_once(
        root,
        catalog,
        r'const val MODELSCOPE_PAGE = "https://www\.modelscope\.cn/models/[^"]+"',
        "const val MODELSCOPE_PAGE = RELEASES_PAGE",
        "MODELSCOPE_PAGE",
    )
    # Only this package's own prefix is an update candidate.
    replace_once(
        root,
        catalog,
        r'^\s*private val androidTag = Regex\(.+\)$',
        lambda _: '    private val androidTag = Regex("""^'
        + prefix
        + 'v?(\\d+(?:\\.\\d+)*)$""")',
        "androidTag regex",
    )
    # A same-name mirror from upstream could deliver another package's APK.
    text = read(root, catalog)
    if text:
        updated, count = re.subn(
            r'    /\*\*[^\n]*\*/\n'
            r'    fun withMirror\(release: AppRelease, fromModelScope: Boolean\): AppRelease \{\n'
            r'.*?\n'
            r'    \}',
            '    /** 包名之间没有镜像：备用线路只能是本包自己的发布。 */\n'
            '    fun withMirror(release: AppRelease, @Suppress("UNUSED_PARAMETER") fromModelScope: Boolean): AppRelease =\n'
            '        release',
            text,
            count=1,
            flags=re.DOTALL,
        )
        if count != 1:
            fail("锚点不匹配（withMirror）")
        else:
            write(root, catalog, updated)
    replace_once(
        root,
        updater,
        r'for \(fromModelScope in if \(domestic\) listOf\(true, false\) else listOf\(false, true\)\) \{',
        "for (fromModelScope in listOf(false)) {",
        "update loop",
    )
    replace_once(
        root,
        "app/src/main/java/com/kingzcheung/xime/security/InstallIntegrity.kt",
        r'const val DOWNLOAD_URL = "https://github\.com/[^"]+?/releases"',
        f'const val DOWNLOAD_URL = "https://github.com/{repo}/releases"',
        "DOWNLOAD_URL",
    )


def patch_signature_gate(root: Path, cert_file: Path) -> None:
    """Accept this fork's certificate, not the upstream one."""
    relative = "app/src/main/java/com/kingzcheung/xime/security/InstallIntegrity.kt"
    if not cert_file.is_file():
        fail(f"缺少签名证书指纹: {cert_file}")
        return
    certs = [
        line.strip().lower()
        for line in cert_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not certs:
        fail(f"签名证书指纹为空: {cert_file}")
        return
    body = ",\n".join(f'        "{cert}",' for cert in certs)
    text = read(root, relative)
    if not text:
        return
    updated, count = re.subn(
        r"internal val OFFICIAL_CERTS: Set<String> = setOf\((?:[^)]*)\)",
        f"internal val OFFICIAL_CERTS: Set<String> = setOf(\n{body}\n    )",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        fail("锚点不匹配（OFFICIAL_CERTS）")
        return
    write(root, relative, updated)


def patch_version(root: Path, version_name: str, version_code: str) -> None:
    if version_name:
        if not re.fullmatch(r"\d+(?:\.\d+)+", version_name):
            fail(f"非法 versionName: {version_name}")
            return
        replace_once(
            root,
            "app/build.gradle.kts",
            r'^(\s*)versionName = "[^"]+"$',
            rf'\1versionName = "{version_name}"',
            "versionName",
        )
    if version_code:
        if not re.fullmatch(r"\d+", version_code):
            fail(f"非法 versionCode: {version_code}")
            return
        replace_once(
            root,
            "app/build.gradle.kts",
            r'^(\s*)versionCode = \d+$',
            rf"\1versionCode = {version_code}",
            "versionCode",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="upstream source root")
    parser.add_argument("--repo", default=os.environ.get("UPSTREAM_FORK_REPO", ""))
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--version-name", default="")
    parser.add_argument("--version-code", default="")
    args = parser.parse_args()

    root = args.root.resolve()
    if not (root / "app" / "build.gradle.kts").is_file():
        print(f"不是 CyIME 源码目录: {root}", file=sys.stderr)
        return 2
    if not args.repo:
        print("缺少 --repo（本仓 GitHub 全名）", file=sys.stderr)
        return 2

    payload = load_packages(args.packages.resolve())
    package = package_by_id(payload, args.package_id)
    suffix = str(package.get("suffix") or "")

    patch_identity(root, package)
    patch_update_channel(root, args.repo, suffix)
    patch_signature_gate(root, args.cert.resolve())
    patch_version(root, args.version_name, args.version_code)

    if FAILS:
        print("补丁失败，拒绝继续构建：", file=sys.stderr)
        for item in FAILS:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(f"补丁完成：{package['id']} -> {package['applicationId']}，更新源={args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

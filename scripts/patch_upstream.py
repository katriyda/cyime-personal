#!/usr/bin/env python3
"""Turn upstream CyIME into one independently-updatable package.

CI clones the upstream source fresh on every run. This repository keeps only
packages.json, the signing certificate fingerprint, this patch script and the
workflows. Patches must be anchored and fail closed: an incomplete patch must
never produce a publishable APK.
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
    ids: set[str] = set()
    app_ids: set[str] = set()
    suffixes: set[str] = set()
    for item in packages:
        if not isinstance(item, dict):
            print("packages 每项必须是对象", file=sys.stderr)
            raise SystemExit(2)
        missing = [key for key in ("id", "applicationId", "label") if not item.get(key)]
        if missing:
            print(f"包名项缺少字段 {missing}: {item}", file=sys.stderr)
            raise SystemExit(2)
        package_id = str(item["id"])
        if package_id in ids:
            print(f"重复的包 id: {package_id}", file=sys.stderr)
            raise SystemExit(2)
        application_id = str(item["applicationId"])
        if application_id in app_ids:
            print(f"重复的 applicationId: {application_id}", file=sys.stderr)
            raise SystemExit(2)
        if not re.fullmatch(r"[a-z][a-z0-9_.]*", application_id):
            print(f"非法 applicationId: {application_id}", file=sys.stderr)
            raise SystemExit(2)
        suffix = str(item.get("suffix") or "")
        if suffix and not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", suffix):
            print(f"非法 suffix: {suffix}", file=sys.stderr)
            raise SystemExit(2)
        if suffix in suffixes:
            print(f"重复的 suffix: {suffix}", file=sys.stderr)
            raise SystemExit(2)
        ids.add(package_id)
        app_ids.add(application_id)
        suffixes.add(suffix)
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
    # The IME service label is a literal on purpose, so the system picker still
    # shows a readable name if resources are unavailable mid-update.
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
        "manifest DEV_LEARNING action",
    )
    replace_once(
        root,
        "app/src/main/AndroidManifest.xml",
        r'applicationId（com\.cyletix\.cyime）',
        f"applicationId（{app_id}）",
        "manifest identity comment",
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
    replace_once(
        root,
        "app/src/androidTest/java/com/kingzcheung/xime/ExampleInstrumentedTest.kt",
        r'assertEquals\("com\.cyletix\.cyime", appContext\.packageName\)',
        f'assertEquals("{app_id}", appContext.packageName)',
        "ExampleInstrumentedTest package",
    )
    replace_once(
        root,
        "app/src/androidTest/java/com/kingzcheung/xime/settings/AppearanceDeliveryTest.kt",
        r'assertEquals\("com\.cyletix\.cyime", context\.packageName\)',
        f'assertEquals("{app_id}", context.packageName)',
        "AppearanceDeliveryTest package",
    )
    replace_once(
        root,
        "app/src/main/java/com/kingzcheung/xime/service/DevLearningReceiver.kt",
        r'adb shell am broadcast -n com\.cyletix\.cyime/com\.kingzcheung\.xime\.service\.DevLearningReceiver -a com\.cyletix\.cyime\.DEV_LEARNING',
        f"adb shell am broadcast -n {app_id}/com.kingzcheung.xime.service.DevLearningReceiver -a {app_id}.DEV_LEARNING",
        "DevLearningReceiver doc",
    )


def patch_update_catalog(root: Path, repo: str, suffix: str) -> None:
    """Point every update URL at this repository; accept only this package's tags."""
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
    # Update tests document upstream behavior. Rewrite both the URL and the
    # tag fixture so these tests still exercise this package's channel.
    test_file = "app/src/test/java/com/kingzcheung/xime/update/AppUpdateCatalogTest.kt"
    text = read(root, test_file)
    if text:
        text = text.replace(
            'https://github.com/Cyletix/CyIME/releases/download/x/$name',
            f'https://github.com/{repo}/releases/download/x/$name',
        )
        text = text.replace(
            'https://github.com/Cyletix/CyIME/releases/tag/$tag',
            f'https://github.com/{repo}/releases/tag/$tag',
        )
        text = text.replace(
            'https://github.com/Cyletix/CyIME/releases/tag/1.14.156',
            f'https://github.com/{repo}/releases/tag/{prefix}1.14.156',
        )
        write(root, test_file, text)
    replace_once(
        root,
        "app/src/test/java/com/kingzcheung/xime/update/AppUpdateCatalogTest.kt",
        r'"""\{"tag_name":"\$tag"',
        f'"""{{"tag_name":"{prefix}$tag"',
        "test release tag prefix",
    )
    # This fork has no domestic mirror. Replace upstream's mirror tests with
    # one assertion that both locales open this fork's own release page.
    text = read(root, test_file)
    if text:
        start = text.find(
            "    // Same shape scripts/store/sync_modelscope.py app writes"
        )
        end = text.find("    @Test\n    fun fdroidInstallsAreStoreManaged()")
        if start < 0 or end < 0 or end <= start:
            fail("锚点不匹配（mirror test block）")
        else:
            replacement = (
                "    @Test\n"
                f"    fun releasesPageUsesThisFork() {{\n"
                f'        assertEquals(AppUpdateCatalog.RELEASES_PAGE, AppUpdateCatalog.releasesPage(domestic = true))\n'
                f'        assertEquals(AppUpdateCatalog.RELEASES_PAGE, AppUpdateCatalog.releasesPage(domestic = false))\n'
                "    }\n\n"
            )
            write(root, test_file, text[:start] + replacement + text[end:])
    # The tag fixture must use this package's prefix; otherwise the update tests
    # silently pass only because they never exercise the filtered tag.
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
        r'^(\s*)if \(fromModelScope\) builder\.url\(AppUpdateCatalog\.MODELSCOPE_RELEASES\)$',
        r"\1if (fromModelScope) {"
        "\n"
        r"\1    if (AppUpdateCatalog.MODELSCOPE_RELEASES.isEmpty()) return null"
        "\n"
        r"\1    builder.url(AppUpdateCatalog.MODELSCOPE_RELEASES)"
        "\n"
        r"\1}",
        "modelscope skip",
    )
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
    """Make the fork accept its own certificate, not the upstream one."""
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
    patch_update_catalog(root, args.repo, suffix)
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

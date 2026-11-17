#!/usr/bin/env python3
"""Resolve the upstream release and the exact list of packages to build.

Reads the latest non-draft, non-prerelease upstream release whose tag is plain
``major.minor.patch``. The tag must also match the source's versionName.

Each package gets its own patch-level version when a release for the same
upstream version already exists. A package already published for this exact
upstream commit is skipped unless --force is passed.

Outputs GitHub Actions key=value lines on stdout.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path


def gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    )
    return result.stdout


def version_tuple(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag.split("."))


def read_upstream_version(upstream: str, tag: str) -> tuple[str, int]:
    content = gh(
        "api",
        f"repos/{upstream}/contents/app/build.gradle.kts?ref={tag}",
        "--jq",
        ".content",
    )
    build = base64.b64decode(content).decode("utf-8")
    name = re.search(r'^\s*versionName = "([^"]+)"$', build, re.MULTILINE)
    code = re.search(r"^\s*versionCode = (\d+)$", build, re.MULTILINE)
    if name is None or code is None:
        raise SystemExit(f"cannot read version from upstream {tag}")
    if name.group(1) != tag:
        raise SystemExit(f"release tag {tag} contains versionName {name.group(1)}")
    return name.group(1), int(code.group(1))


def resolve(
    upstream: str,
    own_repo: str,
    packages_path: Path,
    package_id: str,
    force: bool,
) -> dict:
    releases = json.loads(
        gh(
            "release",
            "list",
            "--repo",
            upstream,
            "--limit",
            "100",
            "--json",
            "tagName,isDraft,isPrerelease",
        )
    )
    stable = [
        row
        for row in releases
        if not row["isDraft"]
        and not row["isPrerelease"]
        and re.fullmatch(r"\d+\.\d+\.\d+", row["tagName"])
    ]
    if not stable:
        raise SystemExit("upstream has no stable Android release")
    tag = max(stable, key=lambda row: version_tuple(row["tagName"]))["tagName"]
    commit = gh("api", f"repos/{upstream}/commits/{tag}", "--jq", ".sha").strip()
    version_name, version_code = read_upstream_version(upstream, tag)

    data = json.loads(packages_path.read_text(encoding="utf-8"))
    selected = data["packages"]
    if package_id:
        selected = [item for item in selected if item["id"] == package_id]
        if not selected:
            raise SystemExit(f"unknown package id: {package_id}")

    own = json.loads(
        gh(
            "api",
            f"repos/{own_repo}/releases?per_page=100",
        )
    )
    # This is the REST shape (tag_name), not gh's --json shape (tagName).
    existing = {row["tag_name"]: row.get("body") or "" for row in own}

    major, minor, patch = version_tuple(version_name)
    resolved = []
    skipped = []
    for package in selected:
        suffix = package.get("suffix") or ""
        bump = 0
        while bump <= 20:
            package_version = f"{major}.{minor}.{patch + bump}"
            release_tag = f"{suffix}-v{package_version}"
            body = existing.get(release_tag)
            if body is None:
                break
            if commit in body and not force:
                skipped.append(package["id"])
                break
            bump += 1
        if package["id"] in skipped:
            continue
        if bump > 20:
            raise SystemExit(f"too many rebuilds for {suffix}")
        package_code = version_code * 10 + bump
        if package_code > 2_147_483_647:
            raise SystemExit("computed versionCode exceeds Android limit")
        resolved.append(
            dict(
                package,
                version=package_version,
                versionCode=package_code,
                tag=release_tag,
            )
        )

    return {
        "should_build": "true" if resolved else "false",
        "packages": json.dumps(resolved, ensure_ascii=False),
        "upstream_tag": tag,
        "upstream_commit": commit,
        "upstream_version": version_name,
        "upstream_code": str(version_code),
        "skipped_packages": ",".join(skipped),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--repo", required=True, help="this repository, owner/name")
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--package-id", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = resolve(
        args.upstream,
        args.repo,
        args.packages,
        args.package_id.strip(),
        args.force,
    )
    for key, value in result.items():
        if key == "skipped_packages" and not value:
            continue
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

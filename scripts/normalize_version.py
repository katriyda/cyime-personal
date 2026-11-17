#!/usr/bin/env python3
"""Produce the version used by every package build for one upstream revision.

Upstream uses e.g. 1.15.94 and a monotonically increasing versionCode. If this
repository already published that upstream version, the PATCH moves by one
while the versionCode advances. This script only computes strings; CI applies
them through patch_upstream.py.
"""
from __future__ import annotations

import argparse
import re
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="upstream versionName, e.g. 1.15.94")
    parser.add_argument("--patch-bump", action="store_true")
    parser.add_argument("--revision", default="0")
    parser.add_argument("--alpha", action="store_true", help="mark a non-release build")
    args = parser.parse_args()

    match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?([^0-9.]*)?", args.name.strip())
    if not match:
        print(f"无法解析版本号: {args.name}", file=sys.stderr)
        return 2
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    if args.patch_bump:
        patch += 1
    revision = int(args.revision)
    if revision < 0:
        print("revision 必须是非负整数", file=sys.stderr)
        return 2
    version = f"{major}.{minor}.{patch}"
    if args.alpha:
        version += f"-alpha.{revision}"
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

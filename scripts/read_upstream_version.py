#!/usr/bin/env python3
"""读出上游 app/build.gradle.kts 里的 versionName / versionCode，供 CI 命名和发布。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--key", choices=["versionName", "versionCode"], required=True)
    args = ap.parse_args()
    build = args.root.resolve() / "app" / "build.gradle.kts"
    if not build.is_file():
        print(f"找不到 {build}", file=sys.stderr)
        return 2
    text = build.read_text(encoding="utf-8")
    m = re.search(rf'^\s*{args.key} = ("?)([^"\n]+)\1$', text, flags=re.MULTILINE)
    if not m:
        print(f"读不到 {args.key}", file=sys.stderr)
        return 1
    print(m.group(2).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

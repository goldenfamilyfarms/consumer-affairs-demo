#!/usr/bin/env python3
"""Fail when frontend bundle exceeds configured budget."""

from __future__ import annotations

import argparse
from pathlib import Path


def total_js_bytes(dist_dir: Path) -> int:
    return sum(file.stat().st_size for file in dist_dir.rglob("*.js"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="frontend/dist")
    parser.add_argument("--max-kb", type=int, default=300)
    args = parser.parse_args()

    dist_dir = Path(args.dist)
    if not dist_dir.exists():
        print(f"Distribution folder not found: {dist_dir}")
        return 1

    total_bytes = total_js_bytes(dist_dir)
    budget_bytes = args.max_kb * 1024

    print(f"Total JS bundle size: {total_bytes / 1024:.1f} KB")
    print(f"Budget: {args.max_kb} KB")

    if total_bytes > budget_bytes:
        print("Bundle size budget exceeded.")
        return 1

    print("Bundle size is within budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

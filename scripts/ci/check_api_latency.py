#!/usr/bin/env python3
"""Fail if core API endpoints exceed a latency budget."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import django  # noqa: E402
from django.test import Client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seconds", type=float, default=0.35)
    args = parser.parse_args()

    django.setup()
    client = Client()

    endpoints = [
        "/api/brands/",
        "/api/brands/?sort=avg_rating&dir=desc&page=1&page_size=12",
        "/api/industries/",
    ]

    failures: list[str] = []
    for endpoint in endpoints:
        start = time.perf_counter()
        response = client.get(endpoint)
        elapsed = time.perf_counter() - start
        if response.status_code != 200:
            failures.append(f"{endpoint}: unexpected status {response.status_code}")
            continue
        if elapsed > args.max_seconds:
            failures.append(
                f"{endpoint}: {elapsed:.3f}s exceeded budget {args.max_seconds:.3f}s"
            )

    if failures:
        print("API latency regression detected:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"All API endpoints are within {args.max_seconds:.3f}s budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

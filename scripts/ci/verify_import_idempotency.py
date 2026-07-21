#!/usr/bin/env python3
"""Run import_wordpress twice and assert second run is a no-op."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
MANAGE = REPO_ROOT / "backend" / "manage.py"
COUNT_RE = re.compile(r"created=(\d+)\s+updated=(\d+)")


def run_import() -> str:
    result = subprocess.run(
        [str(PYTHON), str(MANAGE), "import_wordpress"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def extract_counts(output: str) -> list[tuple[int, int]]:
    return [(int(c), int(u)) for c, u in COUNT_RE.findall(output)]


def main() -> int:
    run_import()
    second = run_import()
    counts = extract_counts(second)
    if not counts:
        print("Unable to parse import summary from second run.")
        print(second)
        return 1

    non_zero = [(created, updated) for created, updated in counts if created or updated]
    if non_zero:
        print("Idempotency check failed: second run changed rows.")
        print(second)
        return 1

    print("Idempotency check passed: second import made no changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

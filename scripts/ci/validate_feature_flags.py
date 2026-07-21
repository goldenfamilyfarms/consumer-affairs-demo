#!/usr/bin/env python3
"""Validate feature flag config schema."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


REQUIRED_FIELDS = {"name", "description", "enabled", "owner", "kill_switch"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=".config/feature-flags.yaml")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Missing feature flag config: {config_path}")
        return 1

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    flags = data.get("flags", []) if isinstance(data, dict) else []
    if not isinstance(flags, list):
        print("Feature flag config must contain a 'flags' list.")
        return 1

    names: set[str] = set()
    errors: list[str] = []

    for index, flag in enumerate(flags, start=1):
        if not isinstance(flag, dict):
            errors.append(f"Flag entry #{index} is not an object.")
            continue

        missing = REQUIRED_FIELDS - flag.keys()
        if missing:
            errors.append(f"Flag entry #{index} missing fields: {sorted(missing)}")

        name = str(flag.get("name", "")).strip()
        if not name:
            errors.append(f"Flag entry #{index} has empty name")
        elif name in names:
            errors.append(f"Duplicate flag name: {name}")
        else:
            names.add(name)

        if not isinstance(flag.get("enabled"), bool):
            errors.append(f"Flag '{name or index}' has non-boolean enabled value")

        if not isinstance(flag.get("kill_switch"), bool):
            errors.append(f"Flag '{name or index}' has non-boolean kill_switch value")

    if errors:
        print("Feature flag validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"Validated {len(flags)} feature flags.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

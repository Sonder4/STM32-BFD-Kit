#!/usr/bin/env python3
"""Validate the core BFD-Kit repository layout before sync or publish."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REQUIRED_FILES = [
    "README.md",
    "README-en.md",
    "README-zh.md",
    "docs/platform_compatibility.md",
    "scripts/bfd_install.py",
    "scripts/bfd_tool_config.py",
    "scripts/bfd_project_detect.py",
    "scripts/bfd_cubeclt_build.py",
]


def validate_repo_layout(root: str | Path) -> list[str]:
    repo_root = Path(root).resolve()
    failures: list[str] = []
    for relative_path in REQUIRED_FILES:
        if not (repo_root / relative_path).is_file():
            failures.append(f"missing file: {relative_path}")
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate BFD-Kit core repository layout")
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    failures = validate_repo_layout(args.root)
    if failures:
        print("Repository validation failed:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("Repository validation passed.")
    print(f"Validated {len(REQUIRED_FILES)} required files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

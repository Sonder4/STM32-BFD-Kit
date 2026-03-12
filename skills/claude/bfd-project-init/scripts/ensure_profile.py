#!/usr/bin/env python3
"""Ensure the canonical BFD runtime profile exists and is up to date."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import bootstrap  # type: ignore  # noqa: E402


ALLOWED_BOOTSTRAP_CODES = {0, 2, 3}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure canonical .codex/bfd profile is present and fresh")
    parser.add_argument("--project-root", default=".", help="STM32 project root")
    parser.add_argument("--force-refresh", action="store_true", help="Rebuild profile even when fingerprint matches")
    parser.add_argument("--print-env-path", action="store_true", help="Print canonical env path relative to project root")
    parser.add_argument("--print-json-path", action="store_true", help="Print canonical json path relative to project root")
    return parser.parse_args()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def canonical_paths(project_root: Path) -> tuple[Path, Path]:
    return (
        project_root / bootstrap.DEFAULT_PROFILE_JSON,
        project_root / bootstrap.DEFAULT_PROFILE_ENV,
    )


def profile_is_fresh(project_root: Path, profile_json_path: Path, profile_env_path: Path) -> bool:
    if not profile_json_path.is_file() or not profile_env_path.is_file():
        return False

    profile = load_json(profile_json_path)
    if not isinstance(profile, dict):
        return False

    runtime = profile.get("runtime", {})
    if not isinstance(runtime, dict):
        return False

    if profile.get("schema_version") != bootstrap.SCHEMA_VERSION:
        return False
    if runtime.get("profile_dir") != bootstrap.DEFAULT_PROFILE_DIR:
        return False

    scan = bootstrap.scan_project(project_root)
    current_fingerprint = bootstrap.compute_profile_fingerprint(project_root, scan)
    return runtime.get("fingerprint") == current_fingerprint


def run_bootstrap(project_root: Path) -> int:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "bootstrap.py"),
        "--project-root",
        str(project_root),
        "--mode",
        "check",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.stdout:
        sys.stderr.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    profile_json_path, profile_env_path = canonical_paths(project_root)

    exit_code = 0
    if args.force_refresh or not profile_is_fresh(project_root, profile_json_path, profile_env_path):
        exit_code = run_bootstrap(project_root)
        if exit_code not in ALLOWED_BOOTSTRAP_CODES:
            return exit_code

    if args.print_json_path:
        print(bootstrap.DEFAULT_PROFILE_JSON)
    if args.print_env_path:
        print(bootstrap.DEFAULT_PROFILE_ENV)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

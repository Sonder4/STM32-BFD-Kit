#!/usr/bin/env python3
"""Install or inspect BFD-Kit inside a target STM32 project."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[1]
META_FILENAME = ".bfd_kit_install_meta.json"
SKIP_PARTS = {
    ".git",
    ".runtime",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def _should_skip(rel_path: Path) -> bool:
    return any(part in SKIP_PARTS for part in rel_path.parts)


def _git_short_hash(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _sync_tree(source_root: Path, target_root: Path, *, clean: bool) -> int:
    copied = 0
    if clean and target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    for source_path in sorted(source_root.rglob("*")):
        rel_path = source_path.relative_to(source_root)
        if _should_skip(rel_path):
            continue
        target_path = target_root / rel_path
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied += 1
    return copied


def _meta_path(target_bfd_kit: Path) -> Path:
    return target_bfd_kit / META_FILENAME


def _load_meta(target_bfd_kit: Path) -> dict[str, Any]:
    meta_path = _meta_path(target_bfd_kit)
    if not meta_path.is_file():
        return {}
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _save_meta(target_bfd_kit: Path, payload: dict[str, Any]) -> Path:
    meta_path = _meta_path(target_bfd_kit)
    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta_path


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _install_metadata(source_root: Path, project_root: Path, copied_files: int) -> dict[str, Any]:
    return {
        "source_root": str(source_root),
        "project_root": str(project_root),
        "version": _git_short_hash(source_root),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "copied_files": copied_files,
    }


def collect_status(project_root: Path) -> dict[str, Any]:
    target_bfd_kit = project_root / "BFD-Kit"
    metadata = _load_meta(target_bfd_kit)
    active_profile_env = project_root / ".codex" / "bfd" / "active_profile.env"
    active_profile_json = project_root / ".codex" / "bfd" / "active_profile.json"
    tool_config = project_root / ".codex" / "bfd" / "tool_config.json"
    return {
        "project_root": str(project_root),
        "target_bfd_kit": str(target_bfd_kit),
        "installed": target_bfd_kit.is_dir(),
        "metadata": metadata,
        "has_codex_skill_root": (project_root / ".codex" / "skills").is_dir(),
        "has_claude_skill_root": (project_root / ".claude" / "skills").is_dir(),
        "tool_config_path": str(tool_config),
        "tool_config_exists": tool_config.is_file(),
        "active_profile_env": str(active_profile_env),
        "active_profile_env_exists": active_profile_env.is_file(),
        "active_profile_json": str(active_profile_json),
        "active_profile_json_exists": active_profile_json.is_file(),
    }


def install_bfd_kit(
    project_root: Path,
    *,
    source_root: Path,
    clean: bool,
    detect_tools: bool,
    bootstrap_profile: bool,
    force_refresh: bool,
    skip_cutover: bool,
    global_tool_config: bool,
) -> dict[str, Any]:
    target_bfd_kit = project_root / "BFD-Kit"
    copied_files = _sync_tree(source_root, target_bfd_kit, clean=clean)
    meta_path = _save_meta(target_bfd_kit, _install_metadata(source_root, project_root, copied_files))
    summary: dict[str, Any] = {
        "project_root": str(project_root),
        "target_bfd_kit": str(target_bfd_kit),
        "copied_files": copied_files,
        "meta_path": str(meta_path),
    }

    if not skip_cutover:
        summary["cutover"] = _run_command(
            [
                sys.executable,
                str(target_bfd_kit / "scripts" / "migrate_bfd_skills.py"),
                "--repo-root",
                str(project_root),
                "--mode",
                "cutover",
            ],
            cwd=project_root,
        )
        if summary["cutover"]["returncode"] != 0:
            return summary

    if detect_tools:
        command = [
            sys.executable,
            str(target_bfd_kit / "scripts" / "bfd_tool_config.py"),
            "detect",
            "--write",
            "--workspace",
            str(project_root),
        ]
        if global_tool_config:
            command.append("--global")
        summary["detect_tools"] = _run_command(command, cwd=project_root)
        if summary["detect_tools"]["returncode"] != 0:
            return summary

    if bootstrap_profile:
        ensure_profile = project_root / ".codex" / "skills" / "bfd-project-init" / "scripts" / "ensure_profile.py"
        if not ensure_profile.is_file():
            summary["bootstrap_profile"] = {
                "returncode": 1,
                "stdout": "",
                "stderr": f"missing ensure_profile.py: {ensure_profile}\n",
            }
            return summary
        command = [
            sys.executable,
            str(ensure_profile),
            "--project-root",
            str(project_root),
            "--print-env-path",
        ]
        if force_refresh:
            command.insert(-1, "--force-refresh")
        summary["bootstrap_profile"] = _run_command(command, cwd=project_root)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or inspect BFD-Kit in a target STM32 project")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--source-root")
    parser.add_argument("--status", action="store_true", help="Report current install status without copying files")
    parser.add_argument("--detect-tools", action="store_true", help="Run bfd_tool_config.py detect --write after install")
    parser.add_argument("--bootstrap-profile", action="store_true", help="Run ensure_profile.py after install")
    parser.add_argument("--force-refresh", action="store_true", help="Pass --force-refresh to ensure_profile.py")
    parser.add_argument("--skip-cutover", action="store_true", help="Only copy BFD-Kit without updating active skill mirrors")
    parser.add_argument("--global-tool-config", action="store_true", help="Persist detected tools in global config instead of workspace config")
    parser.add_argument("--clean", action="store_true", help="Delete the target BFD-Kit directory before copying")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def _print_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if "installed" in payload:
        print(f"installed: {payload['installed']}")
        print(f"project_root: {payload['project_root']}")
        print(f"target_bfd_kit: {payload['target_bfd_kit']}")
        if payload.get("metadata"):
            print(f"version: {payload['metadata'].get('version', 'unknown')}")
            print(f"installed_at: {payload['metadata'].get('installed_at', 'unknown')}")
        print(f"tool_config_exists: {payload['tool_config_exists']}")
        print(f"active_profile_env_exists: {payload['active_profile_env_exists']}")
        print(f"active_profile_json_exists: {payload['active_profile_json_exists']}")
        return
    print(f"project_root: {payload['project_root']}")
    print(f"target_bfd_kit: {payload['target_bfd_kit']}")
    print(f"copied_files: {payload['copied_files']}")
    if "cutover" in payload:
        print(f"cutover_rc: {payload['cutover']['returncode']}")
    if "detect_tools" in payload:
        print(f"detect_tools_rc: {payload['detect_tools']['returncode']}")
    if "bootstrap_profile" in payload:
        print(f"bootstrap_profile_rc: {payload['bootstrap_profile']['returncode']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()
    source_root = Path(args.source_root).resolve() if args.source_root else SOURCE_ROOT
    if args.status:
        _print_payload(collect_status(project_root), as_json=args.json)
        return 0
    payload = install_bfd_kit(
        project_root,
        source_root=source_root,
        clean=args.clean,
        detect_tools=args.detect_tools,
        bootstrap_profile=args.bootstrap_profile,
        force_refresh=args.force_refresh,
        skip_cutover=args.skip_cutover,
        global_tool_config=args.global_tool_config,
    )
    _print_payload(payload, as_json=args.json)
    for key in ("cutover", "detect_tools", "bootstrap_profile"):
        stage = payload.get(key)
        if isinstance(stage, dict) and stage.get("returncode", 0) != 0:
            return int(stage["returncode"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

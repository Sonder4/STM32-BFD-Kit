#!/usr/bin/env python3
"""Cross-platform STM32CubeCLT-oriented CMake build wrapper for BFD-Kit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import bfd_project_detect
import bfd_tool_config


class CubeCltBuildError(RuntimeError):
    """Raised when the wrapper cannot complete the requested build step."""


def resolve_tool_paths(workspace: str | Path) -> dict[str, str]:
    root = Path(workspace).resolve()
    resolved: dict[str, str] = {}
    for tool_name in ("cmake", "ninja", "arm_none_eabi_gcc", "arm_none_eabi_gdb", "arm_none_eabi_objcopy"):
        tool_path = bfd_tool_config.resolve_tool_path(tool_name, workspace=root)
        if tool_path:
            resolved[tool_name] = tool_path
    return resolved


def build_env_with_tools(tool_paths: dict[str, str], *, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    ordered_dirs: list[str] = []
    seen: set[str] = set()
    for key in ("cmake", "ninja", "arm_none_eabi_gcc", "arm_none_eabi_gdb", "arm_none_eabi_objcopy"):
        path = tool_paths.get(key)
        if not path:
            continue
        directory = str(Path(path).expanduser().resolve().parent)
        if directory not in seen:
            seen.add(directory)
            ordered_dirs.append(directory)
    existing_path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join([*ordered_dirs, existing_path]) if existing_path else os.pathsep.join(ordered_dirs)
    return env


def resolve_preset_names(workspace: str | Path, preset_name: str | None) -> dict[str, str | None]:
    root = Path(workspace).resolve()
    presets = bfd_project_detect.detect_cmake_presets(root)
    configure_presets = {item["name"]: item for item in presets.get("configure", []) if item.get("name")}
    build_presets = {item["name"]: item for item in presets.get("build", []) if item.get("name")}

    if not configure_presets:
        return {"configure_preset": None, "build_preset": None, "binary_dir": None}

    chosen = preset_name or ("Debug" if "Debug" in configure_presets else next(iter(configure_presets)))
    if chosen in build_presets:
        build_preset = chosen
        configure_preset = build_presets[chosen].get("configurePreset") or chosen
    elif chosen in configure_presets:
        configure_preset = chosen
        build_preset = chosen if chosen in build_presets else None
    else:
        raise CubeCltBuildError(f"preset '{chosen}' not found in CMakePresets.json")

    binary_dir = configure_presets.get(configure_preset, {}).get("binaryDir")
    return {
        "configure_preset": configure_preset,
        "build_preset": build_preset,
        "binary_dir": binary_dir,
    }


def build_configure_command(
    workspace: str | Path,
    tool_paths: dict[str, str],
    *,
    preset_name: str | None,
    binary_dir: str | None,
    toolchain_file: str | None,
    extra_args: list[str] | None = None,
) -> tuple[list[str], str | None]:
    root = Path(workspace).resolve()
    cmake_path = tool_paths.get("cmake") or "cmake"
    preset_info = resolve_preset_names(root, preset_name) if preset_name or (root / "CMakePresets.json").is_file() else {}
    configure_preset = preset_info.get("configure_preset")
    resolved_binary_dir = preset_info.get("binary_dir") or binary_dir
    command: list[str]
    if configure_preset:
        command = [cmake_path, "--preset", str(configure_preset)]
    else:
        if not resolved_binary_dir:
            raise CubeCltBuildError("binary directory is required when no CMake preset is available")
        command = [cmake_path, "-S", str(root), "-B", str(Path(resolved_binary_dir))]
        ninja_path = tool_paths.get("ninja")
        if ninja_path:
            command.extend(["-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={ninja_path}"])
        if toolchain_file:
            command.append(f"-DCMAKE_TOOLCHAIN_FILE={toolchain_file}")
    if extra_args:
        command.extend(extra_args)
    return command, str(resolved_binary_dir) if resolved_binary_dir else None


def build_build_command(
    workspace: str | Path,
    tool_paths: dict[str, str],
    *,
    preset_name: str | None,
    binary_dir: str | None,
    target: str | None,
    jobs: int | None,
) -> tuple[list[str], str | None]:
    root = Path(workspace).resolve()
    cmake_path = tool_paths.get("cmake") or "cmake"
    preset_info = resolve_preset_names(root, preset_name) if preset_name or (root / "CMakePresets.json").is_file() else {}
    build_preset = preset_info.get("build_preset")
    resolved_binary_dir = preset_info.get("binary_dir") or binary_dir
    if build_preset:
        command = [cmake_path, "--build", "--preset", str(build_preset)]
    else:
        if not resolved_binary_dir:
            raise CubeCltBuildError("binary directory is required when no build preset is available")
        command = [cmake_path, "--build", str(Path(resolved_binary_dir))]
    if target:
        command.extend(["--target", target])
    if jobs is not None:
        command.extend(["-j", str(jobs)])
    return command, str(resolved_binary_dir) if resolved_binary_dir else None


def verify_artifact_bundles(bundles: list[dict[str, Any]], *, require_triplet: bool) -> dict[str, Any]:
    messages: list[str] = []
    ok = True
    for bundle in bundles:
        base_name = bundle.get("base_name", "<unknown>")
        missing = bundle.get("missing_kinds", [])
        stale = bundle.get("stale_kinds", [])
        if require_triplet and missing:
            ok = False
            messages.append(f"{base_name}: missing {', '.join(missing)}")
        if stale:
            ok = False
            messages.append(f"{base_name}: stale {', '.join(stale)}")
    return {"ok": ok, "messages": messages, "bundles": bundles}


def collect_build_report(workspace: str | Path, *, require_triplet: bool) -> dict[str, Any]:
    profile = bfd_project_detect.detect_project(workspace)
    report = verify_artifact_bundles(profile.get("artifact_bundles", []), require_triplet=require_triplet)
    report["project"] = profile
    report["tools"] = resolve_tool_paths(workspace)
    return report


def _run_command(command: list[str], *, env: dict[str, str], cwd: Path) -> int:
    completed = subprocess.run(command, cwd=str(cwd), env=env, check=False)
    return int(completed.returncode)


def _print_payload(payload: dict[str, Any], *, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    for key, value in payload.items():
        print(f"{key}: {value}")


def _cmd_inspect(args: argparse.Namespace) -> int:
    payload = collect_build_report(args.workspace, require_triplet=args.require_triplet)
    preset_name = args.preset or ("Debug" if args.prefer_debug else None)
    payload["preset"] = resolve_preset_names(args.workspace, preset_name)
    _print_payload(payload, json_mode=args.json_mode)
    return 0 if payload["ok"] else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    payload = collect_build_report(args.workspace, require_triplet=args.require_triplet)
    _print_payload(payload, json_mode=args.json_mode)
    return 0 if payload["ok"] else 1


def _cmd_configure(args: argparse.Namespace) -> int:
    tool_paths = resolve_tool_paths(args.workspace)
    command, resolved_binary_dir = build_configure_command(
        args.workspace,
        tool_paths,
        preset_name=args.preset,
        binary_dir=args.binary_dir,
        toolchain_file=args.toolchain_file,
        extra_args=args.extra_arg,
    )
    payload = {
        "command": command,
        "binary_dir": resolved_binary_dir,
        "tools": tool_paths,
    }
    if args.dry_run:
        _print_payload(payload, json_mode=args.json_mode)
        return 0
    env = build_env_with_tools(tool_paths)
    exit_code = _run_command(command, env=env, cwd=Path(args.workspace).resolve())
    payload["exit_code"] = exit_code
    _print_payload(payload, json_mode=args.json_mode)
    return exit_code


def _cmd_build(args: argparse.Namespace) -> int:
    tool_paths = resolve_tool_paths(args.workspace)
    env = build_env_with_tools(tool_paths)
    workspace = Path(args.workspace).resolve()
    executed: list[list[str]] = []
    if args.configure_if_needed:
        command, resolved_binary_dir = build_configure_command(
            workspace,
            tool_paths,
            preset_name=args.preset,
            binary_dir=args.binary_dir,
            toolchain_file=args.toolchain_file,
            extra_args=args.extra_arg,
        )
        if resolved_binary_dir and not Path(resolved_binary_dir).exists():
            if args.dry_run:
                executed.append(command)
            else:
                exit_code = _run_command(command, env=env, cwd=workspace)
                executed.append(command)
                if exit_code != 0:
                    _print_payload({"commands": executed, "exit_code": exit_code}, json_mode=args.json_mode)
                    return exit_code

    build_command, _resolved_binary_dir = build_build_command(
        workspace,
        tool_paths,
        preset_name=args.preset,
        binary_dir=args.binary_dir,
        target=args.target,
        jobs=args.jobs,
    )
    executed.append(build_command)
    if args.dry_run:
        _print_payload({"commands": executed, "tools": tool_paths}, json_mode=args.json_mode)
        return 0

    exit_code = _run_command(build_command, env=env, cwd=workspace)
    payload = collect_build_report(workspace, require_triplet=args.require_triplet)
    payload["commands"] = executed
    payload["exit_code"] = exit_code
    _print_payload(payload, json_mode=args.json_mode)
    if exit_code != 0:
        return exit_code
    return 0 if payload["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BFD-Kit STM32CubeCLT build wrapper")
    parser.add_argument("--json", dest="json_mode", action="store_true", help="Output JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect tools, presets, and artifacts")
    inspect.add_argument("--workspace", default=".")
    inspect.add_argument("--preset")
    inspect.add_argument("--prefer-debug", action="store_true")
    inspect.add_argument("--require-triplet", action="store_true")
    inspect.set_defaults(handler=_cmd_inspect)

    verify = subparsers.add_parser("verify-artifacts", help="Verify elf/hex/bin artifact consistency")
    verify.add_argument("--workspace", default=".")
    verify.add_argument("--require-triplet", action="store_true")
    verify.set_defaults(handler=_cmd_verify)

    configure = subparsers.add_parser("configure", help="Run CMake configure using presets or explicit arguments")
    configure.add_argument("--workspace", default=".")
    configure.add_argument("--preset")
    configure.add_argument("--binary-dir")
    configure.add_argument("--toolchain-file")
    configure.add_argument("--extra-arg", action="append", default=[])
    configure.add_argument("--dry-run", action="store_true")
    configure.set_defaults(handler=_cmd_configure)

    build = subparsers.add_parser("build", help="Run CMake build and verify artifact triplets")
    build.add_argument("--workspace", default=".")
    build.add_argument("--preset")
    build.add_argument("--binary-dir")
    build.add_argument("--toolchain-file")
    build.add_argument("--extra-arg", action="append", default=[])
    build.add_argument("--target")
    build.add_argument("--jobs", type=int)
    build.add_argument("--configure-if-needed", action="store_true")
    build.add_argument("--dry-run", action="store_true")
    build.add_argument("--require-triplet", action="store_true")
    build.set_defaults(handler=_cmd_build)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except CubeCltBuildError as exc:
        payload = {"error": str(exc), "type": type(exc).__name__}
        _print_payload(payload, json_mode=getattr(args, "json_mode", False))
        return 1


if __name__ == "__main__":
    sys.exit(main())

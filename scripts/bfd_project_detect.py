#!/usr/bin/env python3
"""Detect STM32 project metadata for BFD-Kit workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

import bfd_tool_config


IOC_TOOLCHAIN_MAP = {
    "stm32cubeclt": "stm32cubeclt",
    "gcc": "gcc",
    "mdk-arm": "keil",
    "ac6": "keil",
}


def detect_host_os() -> str:
    return bfd_tool_config.detect_host_os()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def detect_build_system(workspace: Path) -> str | None:
    if (workspace / "CMakeLists.txt").is_file():
        return "cmake"
    if list(workspace.glob("*.uvprojx")):
        return "keil"
    return None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(_read_text(path))
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _expand_preset_value(raw: str | None, workspace: Path) -> str | None:
    if raw is None:
        return None
    return raw.replace("${sourceDir}", str(workspace)).replace("${sourceParentDir}", str(workspace.parent))


def detect_cmake_presets(workspace: Path) -> dict[str, list[dict[str, Any]]]:
    payload = _load_json(workspace / "CMakePresets.json")
    if payload is None:
        return {"configure": [], "build": []}

    raw_configure = payload.get("configurePresets", [])
    raw_build = payload.get("buildPresets", [])
    if not isinstance(raw_configure, list):
        raw_configure = []
    if not isinstance(raw_build, list):
        raw_build = []

    configure_by_name = {
        item.get("name"): item for item in raw_configure if isinstance(item, dict) and item.get("name")
    }

    def resolve_configure(name: str | None, stack: set[str] | None = None) -> dict[str, Any]:
        if not name or name not in configure_by_name:
            return {}
        stack = stack or set()
        if name in stack:
            return dict(configure_by_name[name])
        current = dict(configure_by_name[name])
        inherited = current.get("inherits")
        merged: dict[str, Any] = {}
        if isinstance(inherited, list):
            for parent_name in inherited:
                merged.update(resolve_configure(parent_name, stack | {name}))
        elif isinstance(inherited, str):
            merged.update(resolve_configure(inherited, stack | {name}))
        merged.update(current)
        return merged

    configure_presets: list[dict[str, Any]] = []
    for item in raw_configure:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        resolved = resolve_configure(item["name"])
        binary_dir = _expand_preset_value(resolved.get("binaryDir"), workspace)
        toolchain_file = _expand_preset_value(resolved.get("toolchainFile"), workspace)
        configure_presets.append(
            {
                "name": resolved.get("name"),
                "generator": resolved.get("generator"),
                "binaryDir": binary_dir,
                "toolchainFile": toolchain_file,
                "cacheVariables": resolved.get("cacheVariables", {}),
            }
        )

    build_presets: list[dict[str, Any]] = []
    for item in raw_build:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        build_presets.append(
            {
                "name": item.get("name"),
                "configurePreset": item.get("configurePreset"),
            }
        )

    return {"configure": configure_presets, "build": build_presets}


def _find_ioc_file(workspace: Path) -> Path | None:
    files = sorted(workspace.glob("*.ioc"))
    return files[0] if files else None


def _parse_ioc_kv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _normalize_toolchain(raw: str | None, build_system: str | None) -> str | None:
    if raw:
        normalized = IOC_TOOLCHAIN_MAP.get(raw.strip().lower())
        if normalized:
            return normalized
        return raw.strip().lower()
    return build_system


def detect_target_mcu(workspace: Path, build_system: str | None) -> str | None:
    ioc_file = _find_ioc_file(workspace)
    if ioc_file is not None:
        values = _parse_ioc_kv(_read_text(ioc_file))
        for key in ("Mcu.Name", "ProjectManager.DeviceId"):
            value = values.get(key)
            if value:
                return value
    if build_system == "keil":
        for uvprojx in workspace.glob("*.uvprojx"):
            match = re.search(r"<Device>(.*?)</Device>", _read_text(uvprojx))
            if match:
                return match.group(1).strip()
    return None


def detect_toolchain(workspace: Path, build_system: str | None) -> str | None:
    ioc_file = _find_ioc_file(workspace)
    if ioc_file is not None:
        values = _parse_ioc_kv(_read_text(ioc_file))
        toolchain = _normalize_toolchain(values.get("ProjectManager.TargetToolchain"), build_system)
        if toolchain:
            return toolchain
    if build_system == "keil":
        return "keil"
    if build_system == "cmake":
        return "gcc"
    return build_system


def detect_stm32_family(target_mcu: str | None) -> str | None:
    if not target_mcu:
        return None
    normalized = target_mcu.upper()
    match = re.search(r"STM32([A-Z])(\d)", normalized)
    if not match:
        return None
    family_letter = match.group(1).lower()
    family_digit = match.group(2)
    return f"{family_letter}{family_digit}"


def find_build_directories(workspace: Path, cmake_presets: dict[str, list[dict[str, Any]]] | None = None) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    preset_payload = cmake_presets or detect_cmake_presets(workspace)
    for preset in preset_payload.get("configure", []):
        binary_dir = preset.get("binaryDir")
        if not binary_dir:
            continue
        path = Path(binary_dir).resolve()
        if path not in seen:
            seen.add(path)
            candidates.append(path)

    for relative in (
        "build",
        "builds",
        "build_gcc",
        "build_ac6",
        "build_stclang",
        "Debug",
        "Release",
    ):
        path = (workspace / relative).resolve()
        if path not in seen:
            seen.add(path)
            candidates.append(path)
    return candidates


def find_artifacts(workspace: Path, build_directories: list[Path] | None = None) -> list[dict[str, Any]]:
    ext_map = {
        ".elf": "elf",
        ".axf": "elf",
        ".hex": "hex",
        ".bin": "bin",
        ".map": "map",
    }
    results: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    search_roots = build_directories or find_build_directories(workspace)
    for root in search_roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if _should_ignore_artifact(path):
                continue
            kind = ext_map.get(path.suffix.lower())
            if kind is None:
                continue
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            results.append(
                {
                    "path": str(resolved),
                    "kind": kind,
                    "stem": path.stem,
                    "parent": str(resolved.parent),
                    "mtime": resolved.stat().st_mtime,
                }
            )
    return sorted(results, key=lambda item: item["path"])


def _should_ignore_artifact(path: Path) -> bool:
    ignored_dir_names = {"cmakefiles", "cmakescratch"}
    if any(parent.name.lower() in ignored_dir_names for parent in path.parents):
        return True
    stem = path.stem
    if stem.startswith("CMakeDetermineCompilerABI_"):
        return True
    if stem.startswith("cmTC_"):
        return True
    return False


def build_artifact_bundles(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for artifact in artifacts:
        key = (artifact["parent"], artifact["stem"])
        grouped.setdefault(key, {})[artifact["kind"]] = artifact

    bundles: list[dict[str, Any]] = []
    for (parent, stem), by_kind in sorted(grouped.items()):
        reference = by_kind.get("elf") or next(iter(by_kind.values()))
        reference_mtime = float(reference.get("mtime", 0.0))
        missing_kinds: list[str] = []
        if "elf" in by_kind:
            for required in ("hex", "bin"):
                if required not in by_kind:
                    missing_kinds.append(required)
        stale_kinds = [
            kind
            for kind, artifact in by_kind.items()
            if kind != reference["kind"] and float(artifact.get("mtime", 0.0)) < reference_mtime
        ]
        bundles.append(
            {
                "base_name": stem,
                "build_dir": parent,
                "artifacts": {kind: artifact["path"] for kind, artifact in sorted(by_kind.items())},
                "reference_kind": reference["kind"],
                "missing_kinds": missing_kinds,
                "stale_kinds": stale_kinds,
                "triplet_ready": "elf" in by_kind and not missing_kinds and not stale_kinds,
            }
        )

    bundles.sort(
        key=lambda item: (
            0 if "elf" in item["artifacts"] else 1,
            len(item["missing_kinds"]),
            len(item["stale_kinds"]),
            item["build_dir"],
            item["base_name"],
        )
    )
    return bundles


def detect_project(workspace: str | Path) -> dict:
    root = Path(workspace).resolve()
    build_system = detect_build_system(root)
    target_mcu = detect_target_mcu(root, build_system)
    toolchain = detect_toolchain(root, build_system)
    cmake_presets = detect_cmake_presets(root)
    build_directories = find_build_directories(root, cmake_presets)
    artifacts = find_artifacts(root, build_directories)
    bundles = build_artifact_bundles(artifacts)
    profile = {
        "workspace_root": str(root),
        "host_os": detect_host_os(),
        "build_system": build_system,
        "toolchain": toolchain,
        "target_mcu": target_mcu,
        "stm32_family": detect_stm32_family(target_mcu),
        "ioc_file": str(_find_ioc_file(root)) if _find_ioc_file(root) is not None else None,
        "configured_tools": bfd_tool_config.list_tools(workspace=root),
        "cmake_presets": cmake_presets,
        "build_directories": [str(item) for item in build_directories],
        "artifact_candidates": [item["path"] for item in artifacts],
        "artifact_bundles": bundles,
    }
    if bundles:
        bundle = bundles[0]
        if "elf" in bundle["artifacts"]:
            profile["artifact_path"] = bundle["artifacts"]["elf"]
        elif bundle["artifacts"]:
            profile["artifact_path"] = next(iter(bundle["artifacts"].values()))
        profile["preferred_build_dir"] = bundle["build_dir"]
    return profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect BFD-Kit project metadata")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    profile = detect_project(args.workspace)
    payload = json.dumps(profile, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    if args.json or not args.output:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

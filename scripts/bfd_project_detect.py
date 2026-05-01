#!/usr/bin/env python3
"""Detect STM32 project metadata for BFD-Kit workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

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


def find_artifacts(workspace: Path) -> list[Path]:
    patterns = [
        "build/**/*.elf",
        "build/**/*.axf",
        "builds/**/*.elf",
        "builds/**/*.axf",
        "Debug/**/*.elf",
        "Debug/**/*.axf",
        "Release/**/*.elf",
        "Release/**/*.axf",
    ]
    results: list[Path] = []
    for pattern in patterns:
        results.extend(workspace.glob(pattern))
    deduped = sorted({item.resolve() for item in results if item.is_file()})
    return deduped


def detect_project(workspace: str | Path) -> dict:
    root = Path(workspace).resolve()
    build_system = detect_build_system(root)
    target_mcu = detect_target_mcu(root, build_system)
    toolchain = detect_toolchain(root, build_system)
    artifacts = find_artifacts(root)
    profile = {
        "workspace_root": str(root),
        "host_os": detect_host_os(),
        "build_system": build_system,
        "toolchain": toolchain,
        "target_mcu": target_mcu,
        "stm32_family": detect_stm32_family(target_mcu),
        "ioc_file": str(_find_ioc_file(root)) if _find_ioc_file(root) is not None else None,
        "configured_tools": bfd_tool_config.list_tools(workspace=root),
        "artifact_candidates": [str(item) for item in artifacts],
    }
    if artifacts:
        profile["artifact_path"] = str(artifacts[0])
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

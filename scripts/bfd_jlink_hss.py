#!/usr/bin/env python3
"""Native J-Link HSS CLI for BFD-Kit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import sys
from typing import Any, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bfd_jlink_hss_core.elf_symbols import SymbolResolutionError, resolve_symbol_path
from bfd_jlink_hss_core.env import (
    ProbeDiscoveryError,
    default_jlink_exe_hints,
    default_jlink_exe_placeholder,
    list_probes,
    normalize_platform_name as normalize_probe_platform_name,
)
from bfd_jlink_hss_core.hss_sampling import (
    HssSamplingError,
    sample_scalar_specs,
    sample_scalar_symbol,
    sample_scalar_symbols,
)
from bfd_jlink_hss_core.hssdv_project import HssdvProjectError, load_hssdv_project
from bfd_jlink_hss_core.jlink_dll import (
    JLinkDll,
    JLinkDllError,
    choose_probe,
    default_jlink_dll_hints,
    default_jlink_dll_placeholder,
    resolve_jlinkarm_dll,
)


def find_profile_candidate_paths() -> list[Path]:
    roots = [Path.cwd().resolve(), SCRIPT_DIR.resolve(), *SCRIPT_DIR.resolve().parents]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for parent in [root, *root.parents]:
            for candidate in (
                parent / ".codex/bfd/active_profile.env",
                parent / ".codex/stm32/bootstrap/active_profile.env",
            ):
                resolved = candidate.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    candidates.append(candidate)
    return candidates


def load_profile_defaults() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in find_profile_candidate_paths():
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
        if values:
            break
    return values


PROFILE_DEFAULTS = load_profile_defaults()


def _env_or_profile_value(env_key: str, profile_key: str) -> Optional[str]:
    env_value = os.environ.get(env_key) if env_key else None
    if env_value:
        return env_value
    profile_value = PROFILE_DEFAULTS.get(profile_key)
    if profile_value:
        return profile_value
    return None


def _coalesce_value(
    explicit_value: Optional[str],
    project_value: Optional[str],
    env_key: str,
    profile_key: str,
    fallback: Optional[str] = None,
) -> Optional[str]:
    if explicit_value:
        return explicit_value
    if project_value:
        return project_value
    return _env_or_profile_value(env_key, profile_key) or fallback


def _coalesce_int(
    explicit_value: Optional[int],
    project_value: Optional[int],
    env_key: str,
    profile_key: str,
    fallback: int,
) -> int:
    if explicit_value is not None:
        return int(explicit_value)
    if project_value is not None:
        return int(project_value)
    inherited = _env_or_profile_value(env_key, profile_key)
    if inherited:
        return int(inherited)
    return int(fallback)


def output_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def output_text(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for child_key, child_value in value.items():
                    print(f"  {child_key}: {child_value}")
            elif isinstance(value, list):
                print(f"{key}:")
                for item in value:
                    print(f"  - {item}")
            else:
                print(f"{key}: {value}")
    else:
        print(str(payload))


def emit(payload: Any, *, json_mode: bool) -> None:
    if json_mode:
        output_json(payload)
    else:
        output_text(payload)


def select_probe_or_sn(*, usb_sn: Optional[str], jlink_exe: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    if usb_sn:
        return None, usb_sn
    selected = choose_probe(list_probes(jlink_exe), None)
    return selected.to_dict(), selected.serial_number


def resolve_existing_project_symbol_file(symbol_file: str | None, project_file: str | None) -> str | None:
    raw = str(symbol_file or "").strip()
    if not raw:
        return None

    project_dir = Path(project_file).resolve().parent if project_file else None
    candidates: list[Path] = []

    direct = Path(raw).expanduser()
    candidates.append(direct)
    candidates.append(Path(raw.replace("\\", "/")).expanduser())

    if project_dir is not None:
        basename = PureWindowsPath(raw).name if "\\" in raw or ":" in raw else Path(raw).name
        if basename:
            candidates.append(project_dir / basename)
        relative = Path(raw.replace("\\", "/"))
        if not relative.is_absolute():
            candidates.append(project_dir / relative)

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def normalize_platform_choice(platform_name: str) -> str:
    if platform_name == "auto":
        return normalize_probe_platform_name()
    return normalize_probe_platform_name(platform_name)


def _project_sample_command(project_file: str, normalized_platform: str) -> str:
    command = [
        "python3",
        "BFD-Kit/scripts/bfd_jlink_hss.py",
        "--json",
        "hss",
        "sample",
        "--project-file",
        project_file,
        "--duration",
        "0.5",
        "--output",
        "logs/data_acq/hss_project_capture.csv",
    ]
    if normalized_platform == "windows":
        command[0] = "python"
    return " ".join(command)


def cmd_probes_list(args: argparse.Namespace) -> int:
    probes = [probe.to_dict() for probe in list_probes(args.jlink_exe)]
    emit({"probes": probes}, json_mode=args.json_mode)
    return 0


def cmd_hss_inspect(args: argparse.Namespace) -> int:
    device = _coalesce_value(args.device, None, "STM32_DEVICE", "STM32_DEVICE")
    interface = _coalesce_value(args.interface, None, "STM32_IF", "STM32_IF", "SWD")
    speed = _coalesce_int(args.speed, None, "STM32_SPEED_KHZ", "STM32_SPEED_KHZ", 4000)
    if not device:
        raise ValueError("target device is required; pass --device or provide STM32_DEVICE in the profile")

    selected_probe, selected_sn = select_probe_or_sn(usb_sn=args.usb_sn, jlink_exe=args.jlink_exe)
    dll = JLinkDll(dll_path=args.jlink_dll or resolve_jlinkarm_dll())
    try:
        dll.open(usb_sn=selected_sn)
        connected_sn = dll.connect(device=device, interface=interface, speed_khz=speed)
        caps = dll.get_hss_caps()
    finally:
        dll.close()

    emit(
        {
            "jlink_dll": str(dll.dll_path),
            "selected_probe": selected_probe,
            "connected_serial_number": connected_sn,
            "caps": caps.to_dict(),
        },
        json_mode=args.json_mode,
    )
    return 0


def cmd_project_inspect(args: argparse.Namespace) -> int:
    project = load_hssdv_project(args.project_file)
    selected_specs = project.all_specs if args.include_disabled else project.enabled_specs
    normalized_platform = normalize_platform_choice(args.platform)
    resolved_symbol_file = resolve_existing_project_symbol_file(project.settings.symbol_file, project.project_file)
    payload = {
        "project_file": project.project_file,
        "settings": project.settings.to_dict(),
        "selected_specs_count": len(selected_specs),
        "selected_specs": [spec.to_dict() for spec in selected_specs],
        "resolved_defaults": {
            "local_symbol_file": resolved_symbol_file,
            "device": project.settings.device,
            "interface": project.settings.target_interface,
            "speed_khz": project.settings.speed_khz,
            "period_us": project.settings.period_us,
            "usb_sn": project.settings.usb_sn,
        },
        "platform_contract": {
            "platform": normalized_platform,
            "jlink_exe_placeholder": default_jlink_exe_placeholder(normalized_platform),
            "jlink_exe_hints": default_jlink_exe_hints(normalized_platform),
            "jlink_dll_placeholder": default_jlink_dll_placeholder(normalized_platform),
            "jlink_dll_hints": default_jlink_dll_hints(normalized_platform),
        },
        "sample_command_templates": {
            "native_hss_project": _project_sample_command(project.project_file, normalized_platform),
        },
    }
    emit(payload, json_mode=args.json_mode)
    return 0


def cmd_hss_sample(args: argparse.Namespace) -> int:
    project = load_hssdv_project(args.project_file) if args.project_file else None
    project_specs = []
    if project is not None:
        project_specs = project.all_specs if args.project_include_disabled else project.enabled_specs

    project_symbol_file = resolve_existing_project_symbol_file(
        project.settings.symbol_file if project else None,
        project.project_file if project else None,
    )
    elf_path = _coalesce_value(args.elf, project_symbol_file, "STM32_ELF", "STM32_ELF")
    device = _coalesce_value(args.device, project.settings.device if project else None, "STM32_DEVICE", "STM32_DEVICE")
    interface = _coalesce_value(args.interface, project.settings.target_interface if project else None, "STM32_IF", "STM32_IF", "SWD")
    speed = _coalesce_int(args.speed, project.settings.speed_khz if project else None, "STM32_SPEED_KHZ", "STM32_SPEED_KHZ", 4000)
    period_us = _coalesce_int(args.period_us, project.settings.period_us if project else None, "STM32_HSS_PERIOD_US", "STM32_HSS_PERIOD_US", 1000)
    usb_sn = _coalesce_value(args.usb_sn, project.settings.usb_sn if project else None, "STM32_JLINK_SN", "STM32_JLINK_SN")

    if not device:
        raise ValueError("target device is required; pass --device or provide STM32_DEVICE in the profile")
    if not project_specs and not args.symbol:
        raise ValueError("at least one --symbol or --project-file with enabled variables is required")

    selected_probe, selected_sn = select_probe_or_sn(usb_sn=usb_sn, jlink_exe=args.jlink_exe)
    dll = JLinkDll(dll_path=args.jlink_dll or resolve_jlinkarm_dll())

    if project_specs:
        symbol_specs = []
        if args.symbol:
            if not elf_path:
                raise ValueError("--elf is required when using --symbol unless the project SymbolFile resolves locally")
            symbol_specs = [resolve_symbol_path(elf_path, expression) for expression in args.symbol]
        result = sample_scalar_specs(
            dll=dll,
            capture_specs=[*project_specs, *symbol_specs],
            device=device,
            interface=interface,
            speed_khz=speed,
            duration_s=args.duration,
            period_us=period_us,
            output_csv=args.output,
            usb_sn=selected_sn,
            read_buffer_size=args.read_buffer_size,
        )
    elif len(args.symbol) == 1:
        if not elf_path:
            raise ValueError("--elf is required when using --symbol unless the project SymbolFile resolves locally")
        result = sample_scalar_symbol(
            dll=dll,
            elf_path=elf_path,
            symbol_expression=args.symbol[0],
            device=device,
            interface=interface,
            speed_khz=speed,
            duration_s=args.duration,
            period_us=period_us,
            output_csv=args.output,
            usb_sn=selected_sn,
            read_buffer_size=args.read_buffer_size,
        )
    else:
        if not elf_path:
            raise ValueError("--elf is required when using --symbol unless the project SymbolFile resolves locally")
        result = sample_scalar_symbols(
            dll=dll,
            elf_path=elf_path,
            symbol_expressions=list(args.symbol),
            device=device,
            interface=interface,
            speed_khz=speed,
            duration_s=args.duration,
            period_us=period_us,
            output_csv=args.output,
            usb_sn=selected_sn,
            read_buffer_size=args.read_buffer_size,
        )

    emit(
        {
            "selected_probe": selected_probe,
            **result.to_dict(),
        },
        json_mode=args.json_mode,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Native J-Link HSS CLI for BFD-Kit")
    parser.add_argument("--json", dest="json_mode", action="store_true", help="Output JSON")
    subparsers = parser.add_subparsers(dest="group", required=True)

    probes = subparsers.add_parser("probes", help="Probe discovery commands")
    probes_sub = probes.add_subparsers(dest="command", required=True)
    probes_list = probes_sub.add_parser("list", help="List available J-Link probes")
    probes_list.add_argument("--jlink-exe", default=None, help="Optional explicit JLinkExe path")
    probes_list.set_defaults(handler=cmd_probes_list)

    project = subparsers.add_parser("project", help="HSS DataVisualizer project helpers")
    project_sub = project.add_subparsers(dest="command", required=True)
    inspect = project_sub.add_parser("inspect", help="Inspect a Windows HSSDV project file")
    inspect.add_argument("--project-file", required=True, help="Path to .HSSDVProj")
    inspect.add_argument(
        "--include-disabled",
        action="store_true",
        help="Include disabled variables from the project file",
    )
    inspect.add_argument(
        "--platform",
        choices=["auto", "linux", "windows"],
        default="auto",
        help="Platform contract to render for path hints",
    )
    inspect.set_defaults(handler=cmd_project_inspect)

    hss = subparsers.add_parser("hss", help="Native HSS commands")
    hss_sub = hss.add_subparsers(dest="command", required=True)

    inspect = hss_sub.add_parser("inspect", help="Inspect native HSS capability")
    inspect.add_argument("--device", default=None, help="Target device")
    inspect.add_argument("--interface", default=None, help="Target interface, e.g. SWD")
    inspect.add_argument("--speed", type=int, default=None, help="Target interface speed in kHz")
    inspect.add_argument("--usb-sn", default=None, help="Optional J-Link USB serial number")
    inspect.add_argument("--jlink-dll", default=None, help="Optional explicit J-Link native DLL path")
    inspect.add_argument("--jlink-exe", default=None, help="Optional explicit JLinkExe path for probe discovery")
    inspect.set_defaults(handler=cmd_hss_inspect)

    sample = hss_sub.add_parser("sample", help="Sample one or more fixed-address scalar symbols using native HSS")
    sample.add_argument("--elf", default=None, help="ELF path; required for --symbol unless project SymbolFile resolves locally")
    sample.add_argument("--symbol", action="append", default=[], help="Fixed-address symbol path to sample; repeat for multi-symbol HSS")
    sample.add_argument("--project-file", default=None, help="Import enabled variables from a Windows HSSDV project file")
    sample.add_argument(
        "--project-include-disabled",
        action="store_true",
        help="Import disabled HSSDV variables too when --project-file is used",
    )
    sample.add_argument("--device", default=None, help="Target device")
    sample.add_argument("--interface", default=None, help="Target interface, e.g. SWD")
    sample.add_argument("--speed", type=int, default=None, help="Target interface speed in kHz")
    sample.add_argument("--duration", type=float, required=True, help="Sampling duration in seconds")
    sample.add_argument("--period-us", type=int, default=None, help="Requested HSS sampling period in microseconds")
    sample.add_argument("--output", required=True, help="CSV output path")
    sample.add_argument("--usb-sn", default=None, help="Optional J-Link USB serial number")
    sample.add_argument("--jlink-dll", default=None, help="Optional explicit J-Link native DLL path")
    sample.add_argument("--jlink-exe", default=None, help="Optional explicit JLinkExe path for probe discovery")
    sample.add_argument("--read-buffer-size", type=int, default=4096, help="Preferred HSS read buffer size")
    sample.set_defaults(handler=cmd_hss_sample)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (
        ProbeDiscoveryError,
        HssSamplingError,
        HssdvProjectError,
        JLinkDllError,
        SymbolResolutionError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        payload = {"error": str(exc), "type": type(exc).__name__}
        if getattr(args, "json_mode", False):
            output_json(payload)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

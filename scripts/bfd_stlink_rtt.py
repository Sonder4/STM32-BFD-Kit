#!/usr/bin/env python3
"""Polling-based SEGGER RTT reader built on STM32_Programmer_CLI."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Tuple

from bfd_stlink_rtt_core.programmer_cli import ProgrammerCliError, STM32ProgrammerCLI
from bfd_stlink_rtt_core.rtt_poll import (
    poll_up_channel,
    resolve_rtt_symbol,
    scan_for_rtt_signature,
)


ROLE_TO_CHANNEL = {
    "boot": 0,
    "diag": 1,
    "runtime": 2,
}


def find_profile_candidate_paths(script_path: Path) -> List[Path]:
    candidates: List[Path] = []
    for parent in [script_path.resolve().parent, *script_path.resolve().parents]:
        for candidate in (
            parent / ".codex/bfd/active_profile.env",
            parent / ".codex/stm32/bootstrap/active_profile.env",
        ):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def load_profile_defaults() -> Dict[str, str]:
    values: Dict[str, str] = {}
    script_path = Path(__file__).resolve()
    for path in find_profile_candidate_paths(script_path):
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
DEFAULT_DEVICE = os.environ.get("STM32_DEVICE", PROFILE_DEFAULTS.get("STM32_DEVICE", "STM32F427II"))
DEFAULT_INTERFACE = os.environ.get("STM32_IF", PROFILE_DEFAULTS.get("STM32_IF", "SWD"))
DEFAULT_SPEED = int(os.environ.get("STM32_SPEED_KHZ", PROFILE_DEFAULTS.get("STM32_SPEED_KHZ", "4000")))
DEFAULT_PROBE_SN = os.environ.get("STM32_PROBE_SN", PROFILE_DEFAULTS.get("STM32_PROBE_SN", ""))
DEFAULT_ELF = os.environ.get("STM32_ELF", PROFILE_DEFAULTS.get("STM32_ELF", ""))
DEFAULT_RTT_SYMBOL = os.environ.get("STM32_RTT_SYMBOL", PROFILE_DEFAULTS.get("STM32_RTT_SYMBOL", "_SEGGER_RTT"))
DEFAULT_SCAN_WINDOW = os.environ.get(
    "STM32_RTT_SCAN_WINDOW", PROFILE_DEFAULTS.get("STM32_RTT_SCAN_WINDOW", "0x20000000:0x00030000")
)


def parse_scan_window(text: str) -> Tuple[int, int]:
    start_text, _, size_text = text.partition(":")
    if not start_text or not size_text:
        raise ValueError(f"invalid scan window: {text}")
    return int(start_text, 0), int(size_text, 0)


def resolve_channel(role: Optional[str], channel: Optional[int]) -> int:
    if role is not None:
        return ROLE_TO_CHANNEL[role]
    if channel is None:
        return 0
    return channel


def normalize_text_payload(payload: bytes) -> str:
    return payload.replace(b"\x00", b"").decode("utf-8", errors="replace")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Polling-based ST-Link RTT capture for BFD-Kit")
    parser.add_argument("--elf", default=DEFAULT_ELF, help="ELF used to resolve _SEGGER_RTT when available")
    parser.add_argument("--rtt-symbol", default=DEFAULT_RTT_SYMBOL, help="RTT control block symbol")
    parser.add_argument("--scan-window", default=DEFAULT_SCAN_WINDOW, help="RAM scan window <start:size>")
    parser.add_argument("--ram-start", default=None, help="Override RAM scan start address")
    parser.add_argument("--ram-size", default=None, help="Override RAM scan size")
    parser.add_argument("--duration", type=float, default=5.0, help="Capture duration in seconds")
    parser.add_argument("--interval-ms", type=float, default=50.0, help="Polling interval in milliseconds")
    parser.add_argument("--channel", type=int, default=None, help="Explicit RTT up-buffer channel")
    parser.add_argument("--role", choices=sorted(ROLE_TO_CHANNEL.keys()), default=None, help="Named RTT channel role")
    parser.add_argument("--output", required=True, help="Output log path")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="Target device string")
    parser.add_argument("--interface", default=DEFAULT_INTERFACE, help="Debug interface")
    parser.add_argument("--speed-khz", type=int, default=DEFAULT_SPEED, help="ST-Link speed in KHz")
    parser.add_argument("--probe-sn", default=DEFAULT_PROBE_SN or None, help="Optional ST-Link serial number")
    parser.add_argument("--cli-path", default=None, help="Optional explicit STM32_Programmer_CLI path")
    parser.add_argument("--allow-empty", action="store_true", help="Return success even if no payload is captured")
    return parser


def resolve_scan_range(args: argparse.Namespace) -> Tuple[int, int]:
    if args.ram_start is not None or args.ram_size is not None:
        if args.ram_start is None or args.ram_size is None:
            raise ValueError("--ram-start and --ram-size must be provided together")
        return int(args.ram_start, 0), int(args.ram_size, 0)
    return parse_scan_window(args.scan_window)


def resolve_rtt_address(args: argparse.Namespace, client: STM32ProgrammerCLI) -> int:
    if args.elf:
        symbol_addr = resolve_rtt_symbol(args.elf, args.rtt_symbol)
        if symbol_addr is not None:
            return symbol_addr

    ram_start, ram_size = resolve_scan_range(args)
    rtt_addr = scan_for_rtt_signature(client, ram_start=ram_start, ram_size=ram_size)
    if rtt_addr is None:
        raise RuntimeError("RTT control block not found")
    return rtt_addr


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    channel = resolve_channel(args.role, args.channel)

    try:
        client = STM32ProgrammerCLI(
            cli_path=args.cli_path,
            interface=args.interface,
            speed_khz=args.speed_khz,
            serial_number=args.probe_sn,
        )
        rtt_addr = resolve_rtt_address(args, client)
    except (ProgrammerCliError, RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    payload_count = 0
    end_time = time.monotonic() + args.duration
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        while time.monotonic() < end_time:
            try:
                payload, _block = poll_up_channel(client, rtt_addr, channel=channel)
            except (ProgrammerCliError, RuntimeError, ValueError, IndexError) as exc:
                print(f"[ERROR] {exc}", file=sys.stderr)
                return 2

            if payload:
                text = normalize_text_payload(payload)
                if text:
                    payload_count += 1
                    handle.write(text)
                    handle.flush()
            time.sleep(max(args.interval_ms, 0.0) / 1000.0)

    if payload_count == 0 and not args.allow_empty:
        print("[ERROR] No RTT payload captured during polling window", file=sys.stderr)
        return 3

    print(f"[INFO] RTT capture complete: {output_path}")
    print(f"[INFO] channel={channel} payload_chunks={payload_count} rtt_addr=0x{rtt_addr:08X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

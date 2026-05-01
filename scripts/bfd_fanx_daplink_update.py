#!/usr/bin/env python3
"""Update FanX/Tek DAPLink probe firmware from Linux through its MSD bootloader."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile
from typing import Iterable, Sequence


DAPLINK_LABELS = {"DAPLINK"}
BOOTLOADER_LABELS = {"BOOTLOADER"}
START_BOOTLOADER_COMMAND = "START_BL.ACT"
START_INTERFACE_COMMAND = "START_IF.ACT"


class DAPLinkUpdateError(RuntimeError):
    """Raised when the FanX/Tek DAPLink update flow cannot continue."""


@dataclass(frozen=True)
class MountInfo:
    label: str
    path: str
    kind: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FileInfo:
    path: str
    exists: bool
    size: int | None = None
    sha256: str | None = None
    zip_entries: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def decode_proc_mount_path(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def classify_mount(path: Path) -> tuple[str, str] | None:
    label = path.name.upper()
    if label in DAPLINK_LABELS:
        return label, "interface"
    if label in BOOTLOADER_LABELS:
        return label, "bootloader"
    return None


def parse_proc_mounts(text: str) -> list[MountInfo]:
    mounts: list[MountInfo] = []
    for raw in text.splitlines():
        fields = raw.split()
        if len(fields) < 2:
            continue
        mount_path = Path(decode_proc_mount_path(fields[1]))
        classified = classify_mount(mount_path)
        if classified is None:
            continue
        label, kind = classified
        mounts.append(MountInfo(label=label, path=str(mount_path), kind=kind))
    return mounts


def default_search_roots() -> list[Path]:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    roots = [Path("/media") / user, Path("/run/media") / user, Path("/mnt")]
    return [root for root in roots if str(root) != "/media/" and str(root) != "/run/media/"]


def discover_mounts(search_roots: Sequence[Path] | None = None, proc_mounts_path: Path = Path("/proc/mounts")) -> list[MountInfo]:
    found: dict[str, MountInfo] = {}
    if proc_mounts_path.is_file():
        for mount in parse_proc_mounts(proc_mounts_path.read_text(encoding="utf-8", errors="ignore")):
            found[mount.path] = mount

    roots = list(search_roots) if search_roots is not None else default_search_roots()
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            classified = classify_mount(child)
            if classified is None:
                continue
            label, kind = classified
            found[str(child)] = MountInfo(label=label, path=str(child), kind=kind)
    return sorted(found.values(), key=lambda item: (item.kind, item.path))


def find_mount(kind: str, mounts: Sequence[MountInfo]) -> MountInfo | None:
    for mount in mounts:
        if mount.kind == kind:
            return mount
    return None


def wait_for_mount(kind: str, *, timeout_s: float, poll_s: float) -> MountInfo:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() <= deadline:
        mount = find_mount(kind, discover_mounts())
        if mount is not None:
            return mount
        time.sleep(poll_s)
    raise DAPLinkUpdateError(f"timed out waiting for FanX/Tek DAPLink {kind} mount")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_file(path: Path | None) -> FileInfo | None:
    if path is None:
        return None
    expanded = path.expanduser().resolve()
    if not expanded.exists():
        return FileInfo(path=str(expanded), exists=False)
    zip_entries: list[str] | None = None
    if expanded.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(expanded) as archive:
                zip_entries = archive.namelist()
        except zipfile.BadZipFile:
            zip_entries = []
    return FileInfo(
        path=str(expanded),
        exists=True,
        size=expanded.stat().st_size,
        sha256=sha256_file(expanded),
        zip_entries=zip_entries,
    )


def default_firmware_path() -> Path | None:
    candidates = [
        Path.cwd() / ".tools/FanX_Tek_DAPLink_High1_V261.bin",
        Path.cwd() / "FanX_Tek_DAPLink_High1_V261.bin",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def sync_filesystem(path: Path | None = None) -> None:
    if hasattr(os, "sync"):
        os.sync()
    subprocess.run(["sync"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if path is not None:
        subprocess.run(["sync", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write_empty_command(mount: MountInfo, name: str, *, execute: bool) -> Path:
    command_path = Path(mount.path) / name
    if execute:
        command_path.write_bytes(b"")
        sync_filesystem(command_path)
    return command_path


def copy_firmware_to_bootloader(firmware: Path, bootloader_mount: MountInfo, *, execute: bool) -> Path:
    source = firmware.expanduser().resolve()
    if not source.is_file():
        raise DAPLinkUpdateError(f"firmware file not found: {source}")
    destination = Path(bootloader_mount.path) / source.name
    if execute:
        shutil.copy2(source, destination)
        sync_filesystem(destination)
        if destination.exists() and destination.stat().st_size != source.stat().st_size:
            raise DAPLinkUpdateError(
                f"copied firmware size mismatch: source={source.stat().st_size}, dest={destination.stat().st_size}"
            )
    return destination


def make_log_path(log_dir: Path | None, prefix: str) -> Path | None:
    if log_dir is None:
        return None
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{timestamp}_{prefix}.json"


def write_log(path: Path | None, payload: dict) -> None:
    if path is not None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def build_info_payload(args: argparse.Namespace) -> dict:
    firmware = Path(args.firmware) if args.firmware else default_firmware_path()
    updater_zip = Path(args.updater_zip) if args.updater_zip else None
    return {
        "mounts": [mount.to_dict() for mount in discover_mounts()],
        "firmware": inspect_file(firmware).to_dict() if firmware else None,
        "updater_zip": inspect_file(updater_zip).to_dict() if updater_zip else None,
        "official_linux_update_flow": [
            f"copy empty {START_BOOTLOADER_COMMAND} to DAPLINK to enter bootloader",
            "wait for BOOTLOADER mount",
            "copy FanX_Tek_DAPLink_High1_V261.bin to BOOTLOADER",
            "wait for probe reboot",
        ],
    }


def cmd_info(args: argparse.Namespace) -> int:
    payload = build_info_payload(args)
    emit(payload, json_mode=args.json)
    write_log(make_log_path(args.log_dir, "fanx_daplink_info"), payload)
    return 0


def cmd_enter_bootloader(args: argparse.Namespace) -> int:
    mounts = discover_mounts()
    interface_mount = find_mount("interface", mounts)
    if interface_mount is None:
        raise DAPLinkUpdateError("DAPLINK interface mount not found; connect the probe or enter bootloader manually")
    command_path = write_empty_command(interface_mount, START_BOOTLOADER_COMMAND, execute=args.execute)
    payload = {
        "execute": args.execute,
        "action": "enter_bootloader",
        "interface_mount": interface_mount.to_dict(),
        "command_path": str(command_path),
    }
    if args.execute and args.wait:
        payload["bootloader_mount"] = wait_for_mount("bootloader", timeout_s=args.timeout_s, poll_s=args.poll_s).to_dict()
    emit(payload, json_mode=args.json)
    write_log(make_log_path(args.log_dir, "fanx_daplink_enter_bootloader"), payload)
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    firmware = Path(args.firmware) if args.firmware else default_firmware_path()
    if firmware is None:
        raise DAPLinkUpdateError("firmware path is required; pass --firmware")
    firmware = firmware.expanduser().resolve()
    if not firmware.is_file():
        raise DAPLinkUpdateError(f"firmware file not found: {firmware}")

    steps: list[dict] = []
    mounts = discover_mounts()
    bootloader_mount = find_mount("bootloader", mounts)

    if bootloader_mount is None and not args.manual_bootloader:
        interface_mount = find_mount("interface", mounts)
        if interface_mount is None:
            raise DAPLinkUpdateError("neither DAPLINK nor BOOTLOADER mount was found")
        command_path = write_empty_command(interface_mount, START_BOOTLOADER_COMMAND, execute=args.execute)
        steps.append(
            {
                "action": "enter_bootloader",
                "mount": interface_mount.to_dict(),
                "command_path": str(command_path),
                "executed": args.execute,
            }
        )
        if args.execute:
            bootloader_mount = wait_for_mount("bootloader", timeout_s=args.timeout_s, poll_s=args.poll_s)

    if bootloader_mount is None:
        if not args.execute:
            steps.append(
                {
                    "action": "wait_for_bootloader",
                    "executed": False,
                    "hint": "rerun with --execute after manually entering BOOTLOADER, or omit --manual-bootloader from normal DAPLINK mode",
                }
            )
            bootloader_mount = MountInfo(label="BOOTLOADER", path="<pending>", kind="bootloader")
        else:
            bootloader_mount = wait_for_mount("bootloader", timeout_s=args.timeout_s, poll_s=args.poll_s)

    destination = copy_firmware_to_bootloader(firmware, bootloader_mount, execute=args.execute) if bootloader_mount.path != "<pending>" else Path("<pending>") / firmware.name
    steps.append(
        {
            "action": "copy_firmware",
            "firmware": str(firmware),
            "firmware_sha256": sha256_file(firmware),
            "bootloader_mount": bootloader_mount.to_dict(),
            "destination": str(destination),
            "executed": args.execute,
        }
    )

    reboot_mount = None
    if args.execute and args.wait_reboot:
        try:
            reboot_mount = wait_for_mount("interface", timeout_s=args.reboot_timeout_s, poll_s=args.poll_s)
        except DAPLinkUpdateError as exc:
            steps.append({"action": "wait_reboot", "warning": str(exc)})

    payload = {
        "execute": args.execute,
        "dry_run": not args.execute,
        "steps": steps,
        "final_interface_mount": reboot_mount.to_dict() if reboot_mount else None,
    }
    emit(payload, json_mode=args.json)
    write_log(make_log_path(args.log_dir, "fanx_daplink_update"), payload)
    return 0


def emit(payload: dict, *, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def add_common_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Emit JSON")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Directory for JSON action logs",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FanX/Tek DAPLink High Linux firmware updater")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--log-dir", type=Path, default=Path("logs/flash"), help="Directory for JSON action logs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="Inspect local firmware/updater files and mounted DAPLink volumes")
    add_common_output_args(info)
    info.add_argument("--firmware", help="FanX/Tek encrypted interface firmware bin")
    info.add_argument("--updater-zip", help="Optional Windows updater zip to inventory")
    info.set_defaults(handler=cmd_info)

    enter = subparsers.add_parser("enter-bootloader", help="Copy START_BL.ACT to DAPLINK")
    add_common_output_args(enter)
    enter.add_argument("--execute", action="store_true", help="Actually write START_BL.ACT; without this flag only dry-runs")
    enter.add_argument("--wait", action="store_true", help="Wait for BOOTLOADER after writing START_BL.ACT")
    enter.add_argument("--timeout-s", type=float, default=30.0, help="Bootloader wait timeout")
    enter.add_argument("--poll-s", type=float, default=0.5, help="Mount polling interval")
    enter.set_defaults(handler=cmd_enter_bootloader)

    update = subparsers.add_parser("update", help="Run the official Linux MSD update flow")
    add_common_output_args(update)
    update.add_argument("--firmware", help="FanX/Tek encrypted interface firmware bin")
    update.add_argument("--execute", action="store_true", help="Actually write to DAPLINK/BOOTLOADER; without this flag only dry-runs")
    update.add_argument("--manual-bootloader", action="store_true", help="Assume the probe is or will be manually placed in BOOTLOADER mode")
    update.add_argument("--timeout-s", type=float, default=45.0, help="Bootloader wait timeout")
    update.add_argument("--reboot-timeout-s", type=float, default=60.0, help="Interface-mode wait timeout after firmware copy")
    update.add_argument("--poll-s", type=float, default=0.5, help="Mount polling interval")
    update.add_argument("--no-wait-reboot", dest="wait_reboot", action="store_false", help="Do not wait for DAPLINK to reappear after copy")
    update.set_defaults(handler=cmd_update, wait_reboot=True)

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return int(args.handler(args))
    except DAPLinkUpdateError as exc:
        payload = {"error": str(exc), "type": type(exc).__name__}
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

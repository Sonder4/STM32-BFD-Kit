#!/usr/bin/env python3
"""Flash and verify STM32 firmware through CMSIS-DAP probes with PyOCD."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


DEFAULT_FLASH_BASE = 0x08000000


class FlashError(RuntimeError):
    """Raised when a flash or verification step cannot continue."""


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_verify_range(value: str) -> Tuple[int, int]:
    parts = value.split(":", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            f"invalid verify range '{value}', expected <address>:<word_count>"
        )
    try:
        address = parse_int(parts[0].strip())
        word_count = int(parts[1].strip(), 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid verify range '{value}', expected <address>:<word_count>"
        ) from exc
    if word_count <= 0:
        raise argparse.ArgumentTypeError("verify range word_count must be greater than zero")
    return address, word_count


def resolve_pyocd(explicit: str | None = None) -> str:
    candidate = explicit or os.environ.get("PYOCD_BIN") or shutil.which("pyocd")
    if not candidate:
        raise FlashError("pyocd not found. Set PYOCD_BIN or pass --pyocd.")
    path = Path(candidate).expanduser()
    if path.is_file():
        return str(path.resolve())
    found = shutil.which(str(candidate))
    if found:
        return found
    raise FlashError(f"pyocd not executable: {candidate}")


def build_load_command(args: argparse.Namespace, pyocd: str) -> List[str]:
    command = [
        pyocd,
        "load",
        str(Path(args.firmware)),
        "-t",
        args.target,
        "-f",
        str(args.frequency),
        "-e",
        args.erase,
    ]
    if args.uid:
        command.extend(["-u", args.uid])
    if args.force_program:
        command.extend(["-O", "smart_flash=false"])
    if args.no_reset:
        command.append("--no-reset")
    return command


def build_verify_command(
    args: argparse.Namespace,
    pyocd: str,
    address: int,
    word_count: int,
) -> List[str]:
    command = [
        pyocd,
        "commander",
        "-t",
        args.target,
        "-f",
        str(args.frequency),
        "-c",
        f"read32 0x{address:08x} {word_count * 4}",
    ]
    if args.uid:
        command.extend(["-u", args.uid])
    if args.elf:
        command.extend(["--elf", str(Path(args.elf))])
    return command


def parse_intel_hex_bytes(path: Path) -> dict[int, int]:
    memory: dict[int, int] = {}
    upper = 0
    for line_no, raw_line in enumerate(path.read_text(encoding="ascii").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise FlashError(f"invalid Intel HEX line {line_no}: missing ':'")
        try:
            length = int(line[1:3], 16)
            offset = int(line[3:7], 16)
            record_type = int(line[7:9], 16)
            data = bytes.fromhex(line[9 : 9 + length * 2])
        except ValueError as exc:
            raise FlashError(f"invalid Intel HEX line {line_no}") from exc
        if record_type == 0x00:
            base = upper + offset
            for index, byte in enumerate(data):
                memory[base + index] = byte
        elif record_type == 0x01:
            break
        elif record_type == 0x02:
            if len(data) != 2:
                raise FlashError(f"invalid extended segment record at line {line_no}")
            upper = int.from_bytes(data, "big") << 4
        elif record_type == 0x04:
            if len(data) != 2:
                raise FlashError(f"invalid extended linear record at line {line_no}")
            upper = int.from_bytes(data, "big") << 16
        else:
            continue
    return memory


def read_image_words(path: Path, address: int, word_count: int, base_address: int = DEFAULT_FLASH_BASE) -> List[int]:
    suffix = path.suffix.lower()
    byte_count = word_count * 4
    if suffix == ".bin":
        offset = address - base_address
        if offset < 0:
            raise FlashError(f"address 0x{address:08x} is before binary base 0x{base_address:08x}")
        data = path.read_bytes()[offset : offset + byte_count]
    elif suffix in {".hex", ".ihx"}:
        memory = parse_intel_hex_bytes(path)
        try:
            data = bytes(memory[address + index] for index in range(byte_count))
        except KeyError as exc:
            raise FlashError(f"image does not contain byte at 0x{int(exc.args[0]):08x}") from exc
    else:
        raise FlashError(f"image verification supports .bin and .hex images, got {path.suffix}")
    if len(data) != byte_count:
        raise FlashError(f"image has only {len(data)} bytes for {word_count} words at 0x{address:08x}")
    return [int.from_bytes(data[index : index + 4], "little") for index in range(0, byte_count, 4)]


def parse_read32_words(output: str) -> List[int]:
    words: List[int] = []
    for line in output.splitlines():
        if not re.match(r"^[0-9a-fA-F]{8}:", line):
            continue
        payload = line.split("|", 1)[0].split(":", 1)[1]
        for token in payload.split():
            if re.fullmatch(r"[0-9a-fA-F]{8}", token):
                words.append(int(token, 16))
    return words


def format_words(words: Iterable[int]) -> str:
    return " ".join(f"{word:08x}" for word in words)


def run_logged(command: Sequence[str], log_path: Path | None) -> Tuple[int, str]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    command_line = "$ " + " ".join(command)
    text = f"{command_line}\n{result.stdout}"
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(text, encoding="utf-8")
    sys.stdout.write(result.stdout)
    return result.returncode, result.stdout


def make_log_stem(log_dir: Path | None, prefix: str) -> Tuple[Path | None, str | None]:
    if log_dir is None:
        return None, None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix).strip("_") or "pyocd_flash"
    return log_dir, f"{timestamp}_{safe_prefix}"


def make_log_path(log_dir: Path | None, stem: str | None, suffix: str) -> Path | None:
    if log_dir is None or stem is None:
        return None
    return log_dir / f"{stem}_{suffix}.log"


def verify_word_range(
    args: argparse.Namespace,
    pyocd: str,
    firmware: Path,
    address: int,
    word_count: int,
    bin_base_address: int,
    log_path: Path | None,
    label: str,
) -> None:
    expected = read_image_words(firmware, address, word_count, bin_base_address)
    verify_rc, verify_output = run_logged(
        build_verify_command(args, pyocd, address, word_count),
        log_path,
    )
    if verify_rc != 0:
        raise FlashError(
            f"{label} readback failed at 0x{address:08x} with exit code {verify_rc}"
        )
    actual = parse_read32_words(verify_output)[:word_count]
    if actual != expected:
        raise FlashError(
            f"{label} verification mismatch at 0x{address:08x}: "
            f"expected {format_words(expected)}, got {format_words(actual)}"
        )
    print(f"{label} verification OK at 0x{address:08x}: {format_words(actual)}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flash STM32 firmware through DAPLink/CMSIS-DAP using PyOCD")
    parser.add_argument("--firmware", required=True, help="HEX or BIN firmware image")
    parser.add_argument("--target", required=True, help="PyOCD target name, for example stm32h723xx")
    parser.add_argument("--uid", help="CMSIS-DAP probe unique ID")
    parser.add_argument("--frequency", default="100000", help="SWD/JTAG frequency in Hz, e.g. 100000 or 1M")
    parser.add_argument("--erase", choices=["auto", "chip", "sector"], default="sector", help="PyOCD erase mode")
    parser.add_argument("--force-program", action="store_true", help="Disable smart flash so matching pages are erased/programmed")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset after programming")
    parser.add_argument("--pyocd", help="Path to pyocd executable")
    parser.add_argument("--elf", help="Optional ELF for PyOCD commander symbol context")
    parser.add_argument("--address", type=parse_int, default=DEFAULT_FLASH_BASE, help="Vector/readback base address")
    parser.add_argument("--vector-words", type=int, default=8, help="Number of 32-bit vector words to compare")
    parser.add_argument(
        "--verify-range",
        action="append",
        type=parse_verify_range,
        default=[],
        metavar="ADDR:WORDS",
        help="Extra flash readback range(s), expressed as <address>:<32-bit-word-count>",
    )
    parser.add_argument("--bin-base-address", type=parse_int, default=DEFAULT_FLASH_BASE, help="Base address for raw .bin images")
    parser.add_argument("--no-verify-vector", action="store_true", help="Skip post-flash vector readback comparison")
    parser.add_argument("--log-dir", type=Path, default=Path("logs/flash"), help="Directory for load/verify logs")
    parser.add_argument("--log-prefix", default="pyocd_flash", help="Prefix for generated log filenames")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        firmware = Path(args.firmware)
        if not firmware.is_file():
            raise FlashError(f"firmware not found: {firmware}")
        pyocd = resolve_pyocd(args.pyocd)
        log_dir, log_stem = make_log_stem(args.log_dir, args.log_prefix)
        load_log = make_log_path(log_dir, log_stem, "load")

        load_rc, _load_output = run_logged(build_load_command(args, pyocd), load_log)
        if load_rc != 0:
            raise FlashError(f"pyocd load failed with exit code {load_rc}")

        if args.no_verify_vector and not args.verify_range:
            return 0

        verify_index = 0
        if not args.no_verify_vector:
            verify_index += 1
            verify_word_range(
                args,
                pyocd,
                firmware,
                args.address,
                args.vector_words,
                args.bin_base_address,
                make_log_path(log_dir, log_stem, f"verify_{verify_index:02d}_vector"),
                "Vector",
            )

        for address, word_count in args.verify_range:
            verify_index += 1
            verify_word_range(
                args,
                pyocd,
                firmware,
                address,
                word_count,
                args.bin_base_address,
                make_log_path(
                    log_dir,
                    log_stem,
                    f"verify_{verify_index:02d}_{address:08x}_{word_count}w",
                ),
                "Range",
            )
        return 0
    except FlashError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

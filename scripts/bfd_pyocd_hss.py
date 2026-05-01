#!/usr/bin/env python3
"""HSS-compatible fixed-symbol sampling through DAPLink/CMSIS-DAP and PyOCD."""

from __future__ import annotations

import argparse
import configparser
from dataclasses import asdict, dataclass
import csv
import json
import re
from pathlib import Path
import statistics
import sys
import time
from typing import Optional, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bfd_jlink_hss_core.elf_symbols import ResolvedSymbolPath, resolve_symbol_path
from bfd_jlink_hss_core.hss_sampling import HssSamplingError, decode_scalar_bytes


ADDRESS_SPEC_PATTERN = re.compile(
    r"^(?:(?P<name>[^@]+?)@)?(?P<address>0x[0-9A-Fa-f]+|\d+):(?P<type>[A-Za-z0-9_]+)$"
)
HSSDV_SECTION_PATTERN = re.compile(r"^VarInfo\d+$")
TYPE_DESC_INT_PATTERN = re.compile(r"(u?int)(8|16|32|64)_t", re.IGNORECASE)
SCALAR_TYPE_INFO = {
    "u8": {"byte_size": 1, "type_name": "uint8_t", "display": "uint8_t", "type_id": 0},
    "i8": {"byte_size": 1, "type_name": "int8_t", "display": "int8_t", "type_id": 0},
    "u16": {"byte_size": 2, "type_name": "uint16_t", "display": "uint16_t", "type_id": 0},
    "i16": {"byte_size": 2, "type_name": "int16_t", "display": "int16_t", "type_id": 0},
    "u32": {"byte_size": 4, "type_name": "uint32_t", "display": "uint32_t", "type_id": 0},
    "i32": {"byte_size": 4, "type_name": "int32_t", "display": "int32_t", "type_id": 0},
    "u64": {"byte_size": 8, "type_name": "uint64_t", "display": "uint64_t", "type_id": 0},
    "i64": {"byte_size": 8, "type_name": "int64_t", "display": "int64_t", "type_id": 0},
    "f32": {"byte_size": 4, "type_name": "float", "display": "float", "type_id": 1},
    "f64": {"byte_size": 8, "type_name": "double", "display": "double", "type_id": 1},
    "bool": {"byte_size": 1, "type_name": "bool", "display": "bool", "type_id": 0},
}
SCALAR_TYPE_ALIASES = {
    "u8": "u8",
    "uint8_t": "u8",
    "unsigned8": "u8",
    "i8": "i8",
    "int8_t": "i8",
    "s8": "i8",
    "u16": "u16",
    "uint16_t": "u16",
    "unsigned16": "u16",
    "i16": "i16",
    "int16_t": "i16",
    "s16": "i16",
    "u32": "u32",
    "uint32_t": "u32",
    "unsigned32": "u32",
    "i32": "i32",
    "int32_t": "i32",
    "s32": "i32",
    "u64": "u64",
    "uint64_t": "u64",
    "i64": "i64",
    "int64_t": "i64",
    "s64": "i64",
    "f32": "f32",
    "float": "f32",
    "f64": "f64",
    "double": "f64",
    "bool": "bool",
}
HSSDV_TYPE_MAP = {
    (0, 1): "u8",
    (0, 2): "u16",
    (0, 4): "u32",
    (0, 8): "u64",
    (1, 1): "i8",
    (2, 2): "i16",
    (3, 4): "i32",
    (4, 4): "f32",
    (4, 8): "f64",
}


class PyOcdHssError(RuntimeError):
    """Raised when PyOCD HSS-compatible sampling fails."""


@dataclass
class ManualCaptureSpec:
    expression: str
    root_symbol: str
    leaf_name: str
    final_type_tag: str
    final_type_name: str | None
    final_type_display: str
    type_id: int
    offset: int
    root_address: int
    final_address: int
    byte_size: int
    source_file: str | None
    source_kind: str
    alias: str | None = None
    formula: str | None = None
    project_section: str | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["root_address_hex"] = f"0x{self.root_address:08X}"
        payload["final_address_hex"] = f"0x{self.final_address:08X}"
        return payload


CaptureSpec = ResolvedSymbolPath | ManualCaptureSpec


@dataclass
class ReadRegion:
    start_address: int
    byte_size: int
    access_kind: str
    specs: list[CaptureSpec]

    def to_dict(self) -> dict:
        return {
            "start_address": f"0x{self.start_address:08X}",
            "byte_size": self.byte_size,
            "access_kind": self.access_kind,
            "specs": [spec.expression for spec in self.specs],
        }


@dataclass
class PyOcdHssRow:
    sample_index: int
    time_us: int
    values: dict[str, int | float]
    raw_hex: dict[str, str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PyOcdHssResult:
    csv_path: str
    meta_path: str
    sample_count: int
    duration_s: float
    requested_period_us: int
    actual_mean_period_us: float | None
    actual_min_period_us: int | None
    actual_max_period_us: int | None
    backend: str
    timestamp_source: str
    symbols: list[dict]
    read_plan: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PyOcdBenchmarkEntry:
    float_count: int
    payload_bytes: int
    sample_count: int
    duration_s: float
    requested_period_us: int
    actual_mean_period_us: float | None
    actual_min_period_us: int | None
    actual_max_period_us: int | None
    throughput_bytes_per_s: float
    stable_1000hz: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PyOcdBenchmarkResult:
    output_path: str | None
    target: str
    uid: str | None
    frequency_hz: int
    base_address: str
    duration_s: float
    requested_period_us: int
    stable_mean_tolerance_us: int
    stable_rate_floor_hz: float
    max_stable_float_count: int
    entries: list[PyOcdBenchmarkEntry]

    def to_dict(self) -> dict:
        return asdict(self)


def sanitize_symbol_name(expression: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z]+", "_", expression).strip("_")
    return sanitized or "symbol"


def normalize_scalar_type(type_name: str) -> str:
    normalized = SCALAR_TYPE_ALIASES.get(type_name.strip().lower())
    if normalized is None:
        raise PyOcdHssError(f"unsupported scalar type: {type_name}")
    return normalized


def build_manual_capture_spec(
    *,
    expression: str,
    address: int,
    scalar_type: str,
    source_kind: str,
    alias: str | None = None,
    formula: str | None = None,
    project_section: str | None = None,
    source_file: str | None = None,
) -> ManualCaptureSpec:
    type_key = normalize_scalar_type(scalar_type)
    info = SCALAR_TYPE_INFO[type_key]
    cleaned_expression = expression.strip()
    if not cleaned_expression:
        cleaned_expression = f"addr_0x{int(address):08X}"
    return ManualCaptureSpec(
        expression=cleaned_expression,
        root_symbol=cleaned_expression,
        leaf_name=cleaned_expression,
        final_type_tag="DW_TAG_base_type",
        final_type_name=info["type_name"],
        final_type_display=info["display"],
        type_id=info["type_id"],
        offset=0,
        root_address=int(address),
        final_address=int(address),
        byte_size=info["byte_size"],
        source_file=source_file,
        source_kind=source_kind,
        alias=alias,
        formula=formula,
        project_section=project_section,
    )


def parse_address_spec(spec_text: str) -> ManualCaptureSpec:
    match = ADDRESS_SPEC_PATTERN.match(spec_text.strip())
    if not match:
        raise PyOcdHssError(
            f"invalid --address-spec syntax: {spec_text}; expected name@0xADDR:type or 0xADDR:type"
        )
    name = (match.group("name") or "").strip()
    address = int(match.group("address"), 0)
    scalar_type = match.group("type")
    expression = name or f"addr_0x{address:08X}"
    return build_manual_capture_spec(
        expression=expression,
        address=address,
        scalar_type=scalar_type,
        source_kind="address",
    )


def infer_hssdv_scalar_type(type_value: int, size: int, type_desc: str | None) -> str:
    mapped = HSSDV_TYPE_MAP.get((int(type_value), int(size)))
    if mapped is not None:
        return mapped
    if type_desc:
        normalized = type_desc.lower()
        if "float" in normalized and size == 4:
            return "f32"
        if "double" in normalized and size == 8:
            return "f64"
        if "bool" in normalized and size == 1:
            return "bool"
        type_match = TYPE_DESC_INT_PATTERN.search(normalized)
        if type_match:
            prefix = "u" if type_match.group(1).lower().startswith("u") else "i"
            return f"{prefix}{type_match.group(2)}"
        if "unsigned" in normalized:
            return f"u{size * 8}"
    if int(type_value) == 0:
        return f"u{int(size) * 8}"
    raise PyOcdHssError(f"unsupported HSSDV variable type mapping: Type={type_value}, Size={size}, TypeDesc={type_desc}")


def parse_ini_bool(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def load_hssdv_project_specs(project_path: str | Path, *, include_disabled: bool = False) -> list[ManualCaptureSpec]:
    project = Path(project_path).expanduser().resolve()
    if not project.is_file():
        raise PyOcdHssError(f"HSSDV project file not found: {project}")

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(project, encoding="utf-8")

    specs: list[ManualCaptureSpec] = []
    for section_name in parser.sections():
        if not HSSDV_SECTION_PATTERN.match(section_name):
            continue
        section = parser[section_name]
        if not include_disabled and not parse_ini_bool(section.get("isEnableSmpl")):
            continue

        expression = (section.get("VarName") or "").strip()
        if not expression:
            raise PyOcdHssError(f"HSSDV section missing VarName: {section_name}")
        if "Address" not in section:
            raise PyOcdHssError(f"HSSDV section missing Address: {section_name}")
        if "Size" not in section:
            raise PyOcdHssError(f"HSSDV section missing Size: {section_name}")
        if "Type" not in section:
            raise PyOcdHssError(f"HSSDV section missing Type: {section_name}")

        address = int(section.get("Address", "0"), 0)
        size = int(section.get("Size", "0"), 0)
        type_value = int(section.get("Type", "0"), 0)
        scalar_type = infer_hssdv_scalar_type(type_value, size, section.get("TypeDesc"))
        spec = build_manual_capture_spec(
            expression=expression,
            address=address,
            scalar_type=scalar_type,
            source_kind="hssdv-project",
            alias=(section.get("VarAlias") or "").strip() or None,
            formula=(section.get("Formula") or "").strip() or None,
            project_section=section_name,
            source_file=str(project),
        )
        if spec.byte_size != size:
            raise PyOcdHssError(
                f"HSSDV size/type mismatch for {expression}: Type={type_value}, declared Size={size}, inferred Size={spec.byte_size}"
            )
        specs.append(spec)
    return specs


def validate_capture_specs(specs: Sequence[CaptureSpec]) -> list[CaptureSpec]:
    if not specs:
        raise PyOcdHssError("at least one capture spec is required")

    normalized = list(specs)
    seen_names: set[str] = set()
    seen_regions: set[tuple[int, int]] = set()
    for spec in normalized:
        if spec.expression in seen_names:
            raise PyOcdHssError(f"duplicate capture name detected: {spec.expression}")
        seen_names.add(spec.expression)

        key = (int(spec.final_address), int(spec.byte_size))
        if key in seen_regions:
            raise PyOcdHssError(
                f"duplicate sample address detected for {spec.expression}: "
                f"0x{spec.final_address:08X}/{spec.byte_size}"
            )
        seen_regions.add(key)
    return normalized


def resolve_symbols(elf_path: str, expressions: Sequence[str]) -> list[ResolvedSymbolPath]:
    if not expressions:
        raise PyOcdHssError("at least one --symbol is required")
    return [resolve_symbol_path(elf_path, expression) for expression in expressions]


def resolve_capture_specs(
    *,
    elf_path: str | None,
    symbol_expressions: Sequence[str],
    address_specs: Sequence[str],
    project_file: str | None,
    project_include_disabled: bool,
) -> list[CaptureSpec]:
    specs: list[CaptureSpec] = []
    if symbol_expressions:
        if not elf_path:
            raise PyOcdHssError("--elf is required when using --symbol")
        specs.extend(resolve_symbols(elf_path, symbol_expressions))
    specs.extend(parse_address_spec(spec_text) for spec_text in address_specs)
    if project_file:
        specs.extend(load_hssdv_project_specs(project_file, include_disabled=project_include_disabled))
    return validate_capture_specs(specs)


def build_float_benchmark_specs(base_address: int, float_count: int) -> list[ManualCaptureSpec]:
    if int(float_count) <= 0:
        raise PyOcdHssError("float_count must be greater than zero")

    specs: list[ManualCaptureSpec] = []
    start = int(base_address)
    for index in range(int(float_count)):
        specs.append(
            build_manual_capture_spec(
                expression=f"f{index:02d}",
                address=start + index * 4,
                scalar_type="f32",
                source_kind="benchmark-float",
            )
        )
    return specs


def read_symbol_bytes(target, symbol: CaptureSpec) -> bytes:
    address = int(symbol.final_address)
    size = int(symbol.byte_size)
    if size <= 0:
        raise PyOcdHssError(f"invalid byte size for {symbol.expression}: {size}")
    if size == 1:
        return int(target.read8(address)).to_bytes(1, "little")
    if size == 2 and address % 2 == 0:
        return int(target.read16(address)).to_bytes(2, "little")
    if size == 4 and address % 4 == 0:
        return int(target.read32(address)).to_bytes(4, "little")
    if size % 4 == 0 and address % 4 == 0:
        words = target.read_memory_block32(address, size // 4)
        return b"".join(int(word).to_bytes(4, "little") for word in words)
    return bytes(target.read_memory_block8(address, size))


def choose_region_access(address: int, size: int) -> str:
    if size == 1:
        return "read8"
    if size == 2 and address % 2 == 0:
        return "read16"
    if size == 4 and address % 4 == 0:
        return "read32"
    if size % 4 == 0 and address % 4 == 0:
        return "block32"
    return "block8"


def build_read_plan(specs: Sequence[CaptureSpec], *, merge_gap_bytes: int = 0) -> list[ReadRegion]:
    if merge_gap_bytes < 0:
        raise PyOcdHssError("merge-gap-bytes must be greater than or equal to zero")

    ordered = sorted(validate_capture_specs(specs), key=lambda spec: (int(spec.final_address), int(spec.byte_size)))
    plan: list[ReadRegion] = []
    current_specs: list[CaptureSpec] = []
    current_start: int | None = None
    current_end = 0

    for spec in ordered:
        spec_start = int(spec.final_address)
        spec_end = spec_start + int(spec.byte_size)
        if current_start is None or spec_start > current_end + merge_gap_bytes:
            if current_start is not None:
                size = current_end - current_start
                plan.append(
                    ReadRegion(
                        start_address=current_start,
                        byte_size=size,
                        access_kind=choose_region_access(current_start, size),
                        specs=list(current_specs),
                    )
                )
            current_start = spec_start
            current_end = spec_end
            current_specs = [spec]
            continue
        current_specs.append(spec)
        current_end = max(current_end, spec_end)

    if current_start is not None:
        size = current_end - current_start
        plan.append(
            ReadRegion(
                start_address=current_start,
                byte_size=size,
                access_kind=choose_region_access(current_start, size),
                specs=list(current_specs),
            )
        )
    return plan


def read_region_bytes(target, region: ReadRegion) -> bytes:
    if region.access_kind == "read8":
        return int(target.read8(region.start_address)).to_bytes(1, "little")
    if region.access_kind == "read16":
        return int(target.read16(region.start_address)).to_bytes(2, "little")
    if region.access_kind == "read32":
        return int(target.read32(region.start_address)).to_bytes(4, "little")
    if region.access_kind == "block32":
        words = target.read_memory_block32(region.start_address, region.byte_size // 4)
        return b"".join(int(word).to_bytes(4, "little") for word in words)
    return bytes(target.read_memory_block8(region.start_address, region.byte_size))


def sample_once(
    target,
    symbols: Sequence[CaptureSpec],
    *,
    sample_index: int,
    start_ns: int,
    read_plan: Sequence[ReadRegion] | None = None,
    merge_gap_bytes: int = 0,
) -> PyOcdHssRow:
    now_ns = time.monotonic_ns()
    values: dict[str, int | float] = {}
    raw_hex: dict[str, str] = {}
    plan = list(read_plan) if read_plan is not None else build_read_plan(symbols, merge_gap_bytes=merge_gap_bytes)
    for region in plan:
        region_bytes = read_region_bytes(target, region)
        for symbol in region.specs:
            offset = int(symbol.final_address) - region.start_address
            raw = region_bytes[offset : offset + int(symbol.byte_size)]
            if len(raw) != int(symbol.byte_size):
                raise PyOcdHssError(
                    f"short region slice for {symbol.expression}: expected {symbol.byte_size}, got {len(raw)}"
                )
            values[symbol.expression] = decode_scalar_bytes(symbol, raw)
            raw_hex[symbol.expression] = raw.hex()
    return PyOcdHssRow(
        sample_index=sample_index,
        time_us=(now_ns - start_ns) // 1000,
        values=values,
        raw_hex=raw_hex,
    )


def period_stats(rows: Sequence[PyOcdHssRow]) -> tuple[float | None, int | None, int | None]:
    if len(rows) < 2:
        return None, None, None
    periods = [rows[index].time_us - rows[index - 1].time_us for index in range(1, len(rows))]
    return float(statistics.fmean(periods)), min(periods), max(periods)


def write_csv(csv_path: str | Path, symbols: Sequence[CaptureSpec], rows: Sequence[PyOcdHssRow]) -> tuple[Path, dict[str, dict[str, str]]]:
    output = Path(csv_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    columns: dict[str, dict[str, str]] = {}
    header = ["sample_index", "time_us"]
    for symbol in symbols:
        stem = sanitize_symbol_name(symbol.expression)
        value_column = f"{stem}__value"
        raw_column = f"{stem}__raw_hex"
        columns[symbol.expression] = {"value": value_column, "raw_hex": raw_column}
        header.extend([value_column, raw_column])

    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            values: list[object] = [row.sample_index, row.time_us]
            for symbol in symbols:
                values.append(row.values[symbol.expression])
                values.append(row.raw_hex[symbol.expression])
            writer.writerow(values)
    return output, columns


def spec_to_metadata(symbol: CaptureSpec, columns: dict[str, dict[str, str]]) -> dict:
    payload = symbol.to_dict()
    payload["column_names"] = columns[symbol.expression]
    payload["byte_size"] = symbol.byte_size
    payload["address"] = f"0x{symbol.final_address:08X}"
    return payload


def write_metadata(
    csv_path: str | Path,
    *,
    symbols: Sequence[CaptureSpec],
    columns: dict[str, dict[str, str]],
    rows: Sequence[PyOcdHssRow],
    duration_s: float,
    period_us: int,
    target: str,
    uid: str | None,
    frequency_hz: int,
    read_plan: Sequence[ReadRegion],
) -> Path:
    mean_period, min_period, max_period = period_stats(rows)
    meta_path = Path(f"{Path(csv_path).expanduser().resolve()}.meta.json")
    symbol_payload = [spec_to_metadata(symbol, columns) for symbol in symbols]
    payload = {
        "backend": "pyocd-poll",
        "hss_compatibility": "host-polled HSS-compatible CSV; not probe-side timed SEGGER HSS",
        "timestamp_source": "host_monotonic",
        "target": target,
        "uid": uid,
        "frequency_hz": frequency_hz,
        "duration_s": duration_s,
        "requested_period_us": period_us,
        "sample_count": len(rows),
        "actual_mean_period_us": mean_period,
        "actual_min_period_us": min_period,
        "actual_max_period_us": max_period,
        "symbols": symbol_payload,
        "read_plan": [region.to_dict() for region in read_plan],
    }
    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta_path


def connect_pyocd_target(*, target_name: str, uid: str | None, frequency_hz: int):
    try:
        from pyocd.core.helpers import ConnectHelper
    except ImportError as exc:
        raise PyOcdHssError("pyocd Python package not found; run this script with the project's pyocd venv") from exc

    options = {
        "frequency": int(frequency_hz),
        "target_override": target_name,
        "connect_mode": "attach",
        "cache.enable_memory": False,
        "resume_on_disconnect": True,
    }
    return ConnectHelper.session_with_chosen_probe(unique_id=uid, options=options)


def capture_rows_with_pyocd(
    *,
    symbols: Sequence[CaptureSpec],
    target_name: str,
    uid: str | None,
    frequency_hz: int,
    duration_s: float,
    period_us: int,
    merge_gap_bytes: int,
) -> tuple[list[PyOcdHssRow], list[ReadRegion]]:
    if duration_s <= 0:
        raise PyOcdHssError("duration must be greater than zero")
    if period_us < 0:
        raise PyOcdHssError("period-us must be greater than or equal to zero")

    read_plan = build_read_plan(symbols, merge_gap_bytes=merge_gap_bytes)
    rows: list[PyOcdHssRow] = []
    period_s = period_us / 1_000_000.0 if period_us > 0 else 0.0

    with connect_pyocd_target(target_name=target_name, uid=uid, frequency_hz=frequency_hz) as session:
        target = session.board.target
        start_ns = time.monotonic_ns()
        start = time.monotonic()
        deadline = start + duration_s
        index = 0
        next_sample = start
        while time.monotonic() < deadline:
            rows.append(sample_once(target, symbols, sample_index=index, start_ns=start_ns, read_plan=read_plan))
            index += 1
            if period_s <= 0:
                continue
            next_sample += period_s
            sleep_s = next_sample - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)

    if not rows:
        raise PyOcdHssError("no samples captured")
    return rows, read_plan


def is_stable_1000hz(
    *,
    sample_count: int,
    duration_s: float,
    actual_mean_period_us: float | None,
    requested_period_us: int,
    stable_mean_tolerance_us: int = 50,
    stable_rate_floor_hz: float = 950.0,
) -> bool:
    if requested_period_us != 1000:
        return False
    if actual_mean_period_us is None or duration_s <= 0:
        return False
    sample_rate_hz = float(sample_count) / float(duration_s)
    if sample_rate_hz < float(stable_rate_floor_hz):
        return False
    return abs(float(actual_mean_period_us) - float(requested_period_us)) <= float(stable_mean_tolerance_us)


def make_benchmark_entry(
    *,
    float_count: int,
    duration_s: float,
    requested_period_us: int,
    rows: Sequence[PyOcdHssRow],
    stable_mean_tolerance_us: int = 50,
    stable_rate_floor_hz: float = 950.0,
) -> PyOcdBenchmarkEntry:
    actual_mean_period_us, actual_min_period_us, actual_max_period_us = period_stats(rows)
    payload_bytes = int(float_count) * 4
    throughput_bytes_per_s = float(payload_bytes * len(rows)) / float(duration_s)
    stable_1000hz = is_stable_1000hz(
        sample_count=len(rows),
        duration_s=duration_s,
        actual_mean_period_us=actual_mean_period_us,
        requested_period_us=requested_period_us,
        stable_mean_tolerance_us=stable_mean_tolerance_us,
        stable_rate_floor_hz=stable_rate_floor_hz,
    )
    return PyOcdBenchmarkEntry(
        float_count=int(float_count),
        payload_bytes=payload_bytes,
        sample_count=len(rows),
        duration_s=float(duration_s),
        requested_period_us=int(requested_period_us),
        actual_mean_period_us=actual_mean_period_us,
        actual_min_period_us=actual_min_period_us,
        actual_max_period_us=actual_max_period_us,
        throughput_bytes_per_s=throughput_bytes_per_s,
        stable_1000hz=stable_1000hz,
    )


def select_max_stable_float_count(entries: Sequence[PyOcdBenchmarkEntry]) -> int:
    stable_counts = [entry.float_count for entry in entries if entry.stable_1000hz]
    if not stable_counts:
        return 0
    return max(stable_counts)


def write_benchmark_report(output_path: str | Path, result: PyOcdBenchmarkResult) -> tuple[Path, Path]:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    csv_path = Path(f"{output}.csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "float_count",
                "payload_bytes",
                "sample_count",
                "duration_s",
                "requested_period_us",
                "actual_mean_period_us",
                "actual_min_period_us",
                "actual_max_period_us",
                "throughput_bytes_per_s",
                "stable_1000hz",
            ]
        )
        for entry in result.entries:
            writer.writerow(
                [
                    entry.float_count,
                    entry.payload_bytes,
                    entry.sample_count,
                    entry.duration_s,
                    entry.requested_period_us,
                    entry.actual_mean_period_us,
                    entry.actual_min_period_us,
                    entry.actual_max_period_us,
                    entry.throughput_bytes_per_s,
                    int(entry.stable_1000hz),
                ]
            )
    return output, csv_path


def benchmark_float_counts_with_pyocd(
    *,
    base_address: int,
    min_floats: int,
    max_floats: int,
    step_floats: int,
    target_name: str,
    uid: str | None,
    frequency_hz: int,
    duration_s: float,
    period_us: int,
    merge_gap_bytes: int,
    stable_mean_tolerance_us: int,
    stable_rate_floor_hz: float,
    output_path: str | None,
) -> PyOcdBenchmarkResult:
    if min_floats <= 0 or max_floats <= 0 or step_floats <= 0:
        raise PyOcdHssError("min-floats, max-floats, and step-floats must be greater than zero")
    if min_floats > max_floats:
        raise PyOcdHssError("min-floats must be less than or equal to max-floats")

    entries: list[PyOcdBenchmarkEntry] = []
    for float_count in range(int(min_floats), int(max_floats) + 1, int(step_floats)):
        symbols = build_float_benchmark_specs(base_address, float_count)
        rows, _read_plan = capture_rows_with_pyocd(
            symbols=symbols,
            target_name=target_name,
            uid=uid,
            frequency_hz=frequency_hz,
            duration_s=duration_s,
            period_us=period_us,
            merge_gap_bytes=merge_gap_bytes,
        )
        entries.append(
            make_benchmark_entry(
                float_count=float_count,
                duration_s=duration_s,
                requested_period_us=period_us,
                rows=rows,
                stable_mean_tolerance_us=stable_mean_tolerance_us,
                stable_rate_floor_hz=stable_rate_floor_hz,
            )
        )

    result = PyOcdBenchmarkResult(
        output_path=str(Path(output_path).expanduser().resolve()) if output_path else None,
        target=target_name,
        uid=uid,
        frequency_hz=frequency_hz,
        base_address=f"0x{int(base_address):08X}",
        duration_s=float(duration_s),
        requested_period_us=int(period_us),
        stable_mean_tolerance_us=int(stable_mean_tolerance_us),
        stable_rate_floor_hz=float(stable_rate_floor_hz),
        max_stable_float_count=select_max_stable_float_count(entries),
        entries=entries,
    )
    if output_path:
        write_benchmark_report(output_path, result)
    return result


def sample_with_pyocd(
    *,
    elf_path: str | None,
    symbol_expressions: Sequence[str],
    address_specs: Sequence[str],
    project_file: str | None,
    project_include_disabled: bool,
    target_name: str,
    uid: str | None,
    frequency_hz: int,
    duration_s: float,
    period_us: int,
    output_csv: str,
    merge_gap_bytes: int,
) -> PyOcdHssResult:
    symbols = resolve_capture_specs(
        elf_path=elf_path,
        symbol_expressions=symbol_expressions,
        address_specs=address_specs,
        project_file=project_file,
        project_include_disabled=project_include_disabled,
    )
    rows, read_plan = capture_rows_with_pyocd(
        symbols=symbols,
        target_name=target_name,
        uid=uid,
        frequency_hz=frequency_hz,
        duration_s=duration_s,
        period_us=period_us,
        merge_gap_bytes=merge_gap_bytes,
    )

    csv_path, columns = write_csv(output_csv, symbols, rows)
    meta_path = write_metadata(
        csv_path,
        symbols=symbols,
        columns=columns,
        rows=rows,
        duration_s=duration_s,
        period_us=period_us,
        target=target_name,
        uid=uid,
        frequency_hz=frequency_hz,
        read_plan=read_plan,
    )
    mean_period, min_period, max_period = period_stats(rows)
    return PyOcdHssResult(
        csv_path=str(csv_path),
        meta_path=str(meta_path),
        sample_count=len(rows),
        duration_s=duration_s,
        requested_period_us=period_us,
        actual_mean_period_us=mean_period,
        actual_min_period_us=min_period,
        actual_max_period_us=max_period,
        backend="pyocd-poll",
        timestamp_source="host_monotonic",
        symbols=[spec.to_dict() for spec in symbols],
        read_plan=[region.to_dict() for region in read_plan],
    )


def output_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DAPLink/PyOCD HSS-compatible sampler")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample = subparsers.add_parser("sample", help="Sample fixed-address scalar symbols through PyOCD polling")
    sample.add_argument("--elf", help="ELF path; required when using --symbol")
    sample.add_argument("--symbol", action="append", default=[], help="Fixed-address scalar symbol; repeat for multi-symbol")
    sample.add_argument(
        "--address-spec",
        action="append",
        default=[],
        help="Raw address scalar spec in name@0xADDR:type or 0xADDR:type form; repeat for multi-signal",
    )
    sample.add_argument("--project-file", help="Import enabled variables from a Windows HSSDV project file")
    sample.add_argument(
        "--project-include-disabled",
        action="store_true",
        help="Import disabled HSSDV variables too when --project-file is used",
    )
    sample.add_argument("--target", required=True, help="PyOCD target name, e.g. stm32h723xx")
    sample.add_argument("--uid", help="CMSIS-DAP probe UID")
    sample.add_argument("--frequency", type=int, default=10_000_000, help="SWD/JTAG frequency in Hz")
    sample.add_argument("--duration", type=float, required=True, help="Capture duration in seconds")
    sample.add_argument("--period-us", type=int, default=1000, help="Requested host polling period; 0 means run as fast as possible")
    sample.add_argument(
        "--merge-gap-bytes",
        type=int,
        default=0,
        help="Merge nearby addresses into one block read when the gap is within this byte count",
    )
    sample.add_argument("--output", required=True, help="CSV output path")

    benchmark = subparsers.add_parser(
        "benchmark-float",
        help="Sweep contiguous float counts on one RAM region and report the largest count that can hold 1000 Hz",
    )
    benchmark.add_argument("--address", required=True, help="Base address of the contiguous float region")
    benchmark.add_argument("--min-floats", type=int, default=1, help="Smallest float count to test")
    benchmark.add_argument("--max-floats", type=int, required=True, help="Largest float count to test")
    benchmark.add_argument("--step-floats", type=int, default=1, help="Step size between tested float counts")
    benchmark.add_argument("--target", required=True, help="PyOCD target name, e.g. stm32h723xx")
    benchmark.add_argument("--uid", help="CMSIS-DAP probe UID")
    benchmark.add_argument("--frequency", type=int, default=10_000_000, help="SWD/JTAG frequency in Hz")
    benchmark.add_argument("--duration", type=float, default=0.2, help="Capture duration per float-count case")
    benchmark.add_argument("--period-us", type=int, default=1000, help="Requested host polling period; use 1000 for the stable-1kHz sweep")
    benchmark.add_argument(
        "--merge-gap-bytes",
        type=int,
        default=0,
        help="Merge nearby addresses into one block read when the gap is within this byte count",
    )
    benchmark.add_argument(
        "--stable-mean-tolerance-us",
        type=int,
        default=50,
        help="Allowed absolute deviation from 1000 us when deciding whether 1000 Hz is stable",
    )
    benchmark.add_argument(
        "--stable-rate-floor-hz",
        type=float,
        default=950.0,
        help="Required minimum observed sample rate when deciding whether 1000 Hz is stable",
    )
    benchmark.add_argument("--output", required=True, help="JSON benchmark report path; a CSV summary is written next to it")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "sample":
            result = sample_with_pyocd(
                elf_path=args.elf,
                symbol_expressions=args.symbol,
                address_specs=args.address_spec,
                project_file=args.project_file,
                project_include_disabled=args.project_include_disabled,
                target_name=args.target,
                uid=args.uid,
                frequency_hz=args.frequency,
                duration_s=args.duration,
                period_us=args.period_us,
                output_csv=args.output,
                merge_gap_bytes=args.merge_gap_bytes,
            )
            payload = result.to_dict()
            if args.json:
                output_json(payload)
            else:
                output_json(payload)
            return 0
        if args.command == "benchmark-float":
            result = benchmark_float_counts_with_pyocd(
                base_address=int(args.address, 0),
                min_floats=args.min_floats,
                max_floats=args.max_floats,
                step_floats=args.step_floats,
                target_name=args.target,
                uid=args.uid,
                frequency_hz=args.frequency,
                duration_s=args.duration,
                period_us=args.period_us,
                merge_gap_bytes=args.merge_gap_bytes,
                stable_mean_tolerance_us=args.stable_mean_tolerance_us,
                stable_rate_floor_hz=args.stable_rate_floor_hz,
                output_path=args.output,
            )
            output_json(result.to_dict())
            return 0
        raise PyOcdHssError(f"unsupported command: {args.command}")
    except (PyOcdHssError, HssSamplingError, Exception) as exc:
        payload = {"error": str(exc), "type": type(exc).__name__}
        if getattr(args, "json", False):
            output_json(payload)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

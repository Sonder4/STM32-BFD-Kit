"""High-speed sampling orchestration for fixed-address scalar capture specs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import csv
import json
import re
import struct
import sys
import time
from typing import Iterable

from .elf_symbols import ResolvedSymbolPath, resolve_symbol_path
from .hssdv_project import FixedScalarCaptureSpec
from .jlink_dll import HssBlock, HssCaps, JLinkDll, JLinkDllError


class HssSamplingError(RuntimeError):
    """Raised when HSS acquisition or decode fails."""


CaptureSpec = ResolvedSymbolPath | FixedScalarCaptureSpec


@dataclass
class ScalarSample:
    sample_index: int
    time_us: int
    raw_hex: str
    value: int | float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HssSampleResult:
    csv_path: str
    meta_path: str | None
    sample_count: int
    symbol: dict | None
    symbols: list[dict]
    caps: dict
    connected_serial_number: int
    duration_s: float
    period_us: int
    record_size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MultiScalarSample:
    sample_index: int
    time_us: int
    values: dict[str, int | float]
    raw_hex: dict[str, str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _HssAcquisition:
    capture_specs: list[CaptureSpec]
    rows: list[MultiScalarSample]
    caps: HssCaps
    connected_serial_number: int
    record_size_bytes: int


def decode_scalar_bytes(spec: CaptureSpec, raw: bytes):
    if len(raw) != spec.byte_size:
        raise HssSamplingError(f"raw sample size mismatch for {spec.expression}: expected {spec.byte_size}, got {len(raw)}")

    type_name = (spec.final_type_name or "").lower()
    if spec.final_type_tag == "DW_TAG_base_type":
        if type_name == "float" and spec.byte_size == 4:
            return struct.unpack("<f", raw)[0]
        if type_name == "double" and spec.byte_size == 8:
            return struct.unpack("<d", raw)[0]
        if "unsigned" in type_name or type_name.startswith("uint"):
            return int.from_bytes(raw, byteorder="little", signed=False)
        if type_name in {"bool", "_bool"}:
            return int.from_bytes(raw, byteorder="little", signed=False)
        return int.from_bytes(raw, byteorder="little", signed=True)
    raise HssSamplingError(f"unsupported scalar type for native HSS decode: {spec.final_type_display}")


def _sanitize_symbol_name(expression: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z]+", "_", expression).strip("_")
    return sanitized or "symbol"


def _validate_capture_spec_list(capture_specs: list[CaptureSpec]) -> None:
    if not capture_specs:
        raise HssSamplingError("at least one fixed-address capture spec is required")
    seen: set[tuple[int, int]] = set()
    for spec in capture_specs:
        key = (int(spec.final_address), int(spec.byte_size))
        if key in seen:
            raise HssSamplingError(
                f"duplicate HSS block detected for {spec.expression}: address=0x{spec.final_address:08X}, size={spec.byte_size}"
            )
        seen.add(key)


def _record_size_for_specs(capture_specs: list[CaptureSpec]) -> int:
    _validate_capture_spec_list(capture_specs)
    return 4 + sum(spec.byte_size for spec in capture_specs)


def _normalize_capture_specs(
    *,
    symbol: CaptureSpec | None = None,
    symbols: list[CaptureSpec] | None = None,
    capture_specs: list[CaptureSpec] | None = None,
) -> tuple[list[CaptureSpec], bool]:
    if capture_specs is not None:
        return list(capture_specs), False
    if symbols is not None:
        return list(symbols), False
    if symbol is not None:
        return [symbol], True
    raise HssSamplingError("either symbol, symbols, or capture_specs must be provided")


def parse_hss_samples(
    payload: bytes,
    *,
    symbol: CaptureSpec | None = None,
    symbols: list[CaptureSpec] | None = None,
    capture_specs: list[CaptureSpec] | None = None,
    period_us: int,
    remainder: bytes = b"",
) -> tuple[list[ScalarSample] | list[MultiScalarSample], bytes]:
    specs, legacy_single_symbol = _normalize_capture_specs(
        symbol=symbol,
        symbols=symbols,
        capture_specs=capture_specs,
    )
    record_size = _record_size_for_specs(specs)
    data = remainder + payload
    full_size = len(data) - (len(data) % record_size)
    complete = data[:full_size]
    trailing = data[full_size:]
    samples: list[ScalarSample] | list[MultiScalarSample] = []
    for offset in range(0, len(complete), record_size):
        sample_index = struct.unpack_from("<I", complete, offset)[0]
        data_offset = offset + 4
        values: dict[str, int | float] = {}
        raw_hex: dict[str, str] = {}
        for spec in specs:
            raw_value = complete[data_offset : data_offset + spec.byte_size]
            values[spec.expression] = decode_scalar_bytes(spec, raw_value)
            raw_hex[spec.expression] = raw_value.hex()
            data_offset += spec.byte_size
        if legacy_single_symbol:
            resolved = specs[0]
            samples.append(
                ScalarSample(
                    sample_index=sample_index,
                    time_us=sample_index * period_us,
                    raw_hex=raw_hex[resolved.expression],
                    value=values[resolved.expression],
                )
            )
            continue
        samples.append(
            MultiScalarSample(
                sample_index=sample_index,
                time_us=sample_index * period_us,
                values=values,
                raw_hex=raw_hex,
            )
        )
    return samples, trailing


def write_scalar_csv(csv_path: str | Path, spec: CaptureSpec, samples: Iterable[ScalarSample]) -> Path:
    output = Path(csv_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_index", "time_us", "symbol", "value", "raw_hex", "address"])
        for sample in samples:
            writer.writerow(
                [
                    sample.sample_index,
                    sample.time_us,
                    spec.expression,
                    sample.value,
                    sample.raw_hex,
                    f"0x{spec.final_address:08X}",
                ]
            )
    return output


def write_multi_scalar_csv(
    csv_path: str | Path,
    capture_specs: list[CaptureSpec],
    rows: Iterable[MultiScalarSample],
) -> tuple[Path, dict[str, dict[str, str]]]:
    output = Path(csv_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    columns: dict[str, dict[str, str]] = {}
    header = ["sample_index", "time_us"]
    for spec in capture_specs:
        stem = _sanitize_symbol_name(spec.expression)
        value_column = f"{stem}__value"
        raw_column = f"{stem}__raw_hex"
        columns[spec.expression] = {"value": value_column, "raw_hex": raw_column}
        header.extend([value_column, raw_column])

    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            values: list[object] = [row.sample_index, row.time_us]
            for spec in capture_specs:
                values.append(row.values[spec.expression])
                values.append(row.raw_hex[spec.expression])
            writer.writerow(values)
    return output, columns


def write_multi_scalar_metadata(
    csv_path: str | Path,
    *,
    capture_specs: list[CaptureSpec],
    caps: HssCaps,
    connected_serial_number: int,
    period_us: int,
    duration_s: float,
    record_size_bytes: int,
    columns: dict[str, dict[str, str]],
) -> Path:
    meta_path = Path(f"{Path(csv_path).expanduser().resolve()}.meta.json")
    payload = {
        "symbols": [
            {
                **spec.to_dict(),
                "column_names": columns[spec.expression],
                "byte_size": spec.byte_size,
                "address": f"0x{spec.final_address:08X}",
            }
            for spec in capture_specs
        ],
        "caps": caps.to_dict(),
        "connected_serial_number": connected_serial_number,
        "period_us": period_us,
        "duration_s": duration_s,
        "record_size_bytes": record_size_bytes,
    }
    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta_path


def read_hss_payload_with_backoff(dll: JLinkDll, *, preferred_size: int, record_size: int) -> bytes:
    size = max(record_size, preferred_size)
    while size >= record_size:
        try:
            return dll.hss_read(size)
        except JLinkDllError:
            next_size = (size // 2) - ((size // 2) % record_size)
            if next_size < record_size:
                break
            size = next_size
    raise HssSamplingError(f"failed to read J-Link HSS data with any buffer size >= {record_size} bytes")


def _acquire_hss_rows(
    *,
    dll: JLinkDll,
    capture_specs: list[CaptureSpec],
    device: str,
    interface: str,
    speed_khz: int,
    duration_s: float,
    period_us: int,
    usb_sn: str | None = None,
    read_buffer_size: int = 4096,
) -> _HssAcquisition:
    if duration_s <= 0:
        raise HssSamplingError("duration_s must be greater than zero")
    if period_us <= 0:
        raise HssSamplingError("period_us must be greater than zero")

    _validate_capture_spec_list(capture_specs)
    connected_serial_number = -1
    caps: HssCaps | None = None
    all_rows: list[MultiScalarSample] = []
    remainder = b""
    hss_started = False

    try:
        dll.open(usb_sn=usb_sn)
        connected_serial_number = dll.connect(device=device, interface=interface, speed_khz=speed_khz)
        caps = dll.get_hss_caps()
        if caps.max_buffer_bytes_inferred <= 0:
            raise HssSamplingError(f"J-Link reported no usable HSS data blocks: {caps.to_dict()}")
        record_size = _record_size_for_specs(capture_specs)
        caps_buffer_bytes = caps.max_buffer_bytes_inferred if caps.max_buffer_bytes_inferred > 0 else read_buffer_size
        effective_read_buffer_size = max(record_size, min(read_buffer_size, caps_buffer_bytes))
        effective_read_buffer_size -= effective_read_buffer_size % record_size
        if effective_read_buffer_size < record_size:
            effective_read_buffer_size = record_size
        dll.hss_start(
            [HssBlock(address=spec.final_address, byte_size=spec.byte_size) for spec in capture_specs],
            period_us=period_us,
        )
        hss_started = True
        samples_per_read = max(1, effective_read_buffer_size // record_size)
        warmup_s = min(max(samples_per_read * period_us / 1_000_000.0, 0.05), max(duration_s, 0.2))
        time.sleep(warmup_s)
        start_time = time.monotonic()
        deadline = start_time + duration_s
        while time.monotonic() < deadline:
            payload = read_hss_payload_with_backoff(
                dll,
                preferred_size=effective_read_buffer_size,
                record_size=record_size,
            )
            if not payload:
                time.sleep(0.005)
                continue
            parsed, remainder = parse_hss_samples(
                payload,
                capture_specs=capture_specs,
                period_us=period_us,
                remainder=remainder,
            )
            all_rows.extend(parsed)
        payload = read_hss_payload_with_backoff(
            dll,
            preferred_size=effective_read_buffer_size,
            record_size=record_size,
        )
        if payload:
            parsed, remainder = parse_hss_samples(
                payload,
                capture_specs=capture_specs,
                period_us=period_us,
                remainder=remainder,
            )
            all_rows.extend(parsed)
        parsed, remainder = parse_hss_samples(
            b"",
            capture_specs=capture_specs,
            period_us=period_us,
            remainder=remainder,
        )
        all_rows.extend(parsed)
    finally:
        if hss_started:
            try:
                dll.hss_stop()
            except JLinkDllError as exc:
                if sys.exc_info()[0] is None:
                    raise HssSamplingError(f"failed to stop J-Link HSS cleanly: {exc}") from exc
        dll.close()

    if not all_rows:
        raise HssSamplingError("HSS returned no samples during the requested acquisition window")

    assert caps is not None
    return _HssAcquisition(
        capture_specs=list(capture_specs),
        rows=all_rows,
        caps=caps,
        connected_serial_number=connected_serial_number,
        record_size_bytes=record_size,
    )


def _acquire_hss_rows_from_symbols(
    *,
    dll: JLinkDll,
    elf_path: str,
    symbol_expressions: list[str],
    device: str,
    interface: str,
    speed_khz: int,
    duration_s: float,
    period_us: int,
    usb_sn: str | None = None,
    read_buffer_size: int = 4096,
) -> _HssAcquisition:
    capture_specs = [resolve_symbol_path(elf_path, expression) for expression in symbol_expressions]
    return _acquire_hss_rows(
        dll=dll,
        capture_specs=capture_specs,
        device=device,
        interface=interface,
        speed_khz=speed_khz,
        duration_s=duration_s,
        period_us=period_us,
        usb_sn=usb_sn,
        read_buffer_size=read_buffer_size,
    )


def sample_scalar_specs(
    *,
    dll: JLinkDll,
    capture_specs: list[CaptureSpec],
    device: str,
    interface: str,
    speed_khz: int,
    duration_s: float,
    period_us: int,
    output_csv: str,
    usb_sn: str | None = None,
    read_buffer_size: int = 4096,
) -> HssSampleResult:
    acquisition = _acquire_hss_rows(
        dll=dll,
        capture_specs=capture_specs,
        device=device,
        interface=interface,
        speed_khz=speed_khz,
        duration_s=duration_s,
        period_us=period_us,
        usb_sn=usb_sn,
        read_buffer_size=read_buffer_size,
    )
    csv_path, columns = write_multi_scalar_csv(output_csv, acquisition.capture_specs, acquisition.rows)
    meta_path = write_multi_scalar_metadata(
        csv_path,
        capture_specs=acquisition.capture_specs,
        caps=acquisition.caps,
        connected_serial_number=acquisition.connected_serial_number,
        period_us=period_us,
        duration_s=duration_s,
        record_size_bytes=acquisition.record_size_bytes,
        columns=columns,
    )
    return HssSampleResult(
        csv_path=str(csv_path),
        meta_path=str(meta_path),
        sample_count=len(acquisition.rows),
        symbol=acquisition.capture_specs[0].to_dict(),
        symbols=[spec.to_dict() for spec in acquisition.capture_specs],
        caps=acquisition.caps.to_dict(),
        connected_serial_number=acquisition.connected_serial_number,
        duration_s=duration_s,
        period_us=period_us,
        record_size_bytes=acquisition.record_size_bytes,
    )


def sample_scalar_symbols(
    *,
    dll: JLinkDll,
    elf_path: str,
    symbol_expressions: list[str],
    device: str,
    interface: str,
    speed_khz: int,
    duration_s: float,
    period_us: int,
    output_csv: str,
    usb_sn: str | None = None,
    read_buffer_size: int = 4096,
) -> HssSampleResult:
    acquisition = _acquire_hss_rows_from_symbols(
        dll=dll,
        elf_path=elf_path,
        symbol_expressions=symbol_expressions,
        device=device,
        interface=interface,
        speed_khz=speed_khz,
        duration_s=duration_s,
        period_us=period_us,
        usb_sn=usb_sn,
        read_buffer_size=read_buffer_size,
    )
    csv_path, columns = write_multi_scalar_csv(output_csv, acquisition.capture_specs, acquisition.rows)
    meta_path = write_multi_scalar_metadata(
        csv_path,
        capture_specs=acquisition.capture_specs,
        caps=acquisition.caps,
        connected_serial_number=acquisition.connected_serial_number,
        period_us=period_us,
        duration_s=duration_s,
        record_size_bytes=acquisition.record_size_bytes,
        columns=columns,
    )
    return HssSampleResult(
        csv_path=str(csv_path),
        meta_path=str(meta_path),
        sample_count=len(acquisition.rows),
        symbol=acquisition.capture_specs[0].to_dict(),
        symbols=[spec.to_dict() for spec in acquisition.capture_specs],
        caps=acquisition.caps.to_dict(),
        connected_serial_number=acquisition.connected_serial_number,
        duration_s=duration_s,
        period_us=period_us,
        record_size_bytes=acquisition.record_size_bytes,
    )


def sample_scalar_symbol(
    *,
    dll: JLinkDll,
    elf_path: str,
    symbol_expression: str,
    device: str,
    interface: str,
    speed_khz: int,
    duration_s: float,
    period_us: int,
    output_csv: str,
    usb_sn: str | None = None,
    read_buffer_size: int = 4096,
) -> HssSampleResult:
    acquisition = _acquire_hss_rows_from_symbols(
        dll=dll,
        elf_path=elf_path,
        symbol_expressions=[symbol_expression],
        device=device,
        interface=interface,
        speed_khz=speed_khz,
        duration_s=duration_s,
        period_us=period_us,
        usb_sn=usb_sn,
        read_buffer_size=read_buffer_size,
    )
    spec = acquisition.capture_specs[0]
    samples = [
        ScalarSample(
            sample_index=row.sample_index,
            time_us=row.time_us,
            raw_hex=row.raw_hex[spec.expression],
            value=row.values[spec.expression],
        )
        for row in acquisition.rows
    ]
    csv_path = write_scalar_csv(output_csv, spec, samples)
    return HssSampleResult(
        csv_path=str(csv_path),
        meta_path=None,
        sample_count=len(samples),
        symbol=spec.to_dict(),
        symbols=[spec.to_dict()],
        caps=acquisition.caps.to_dict(),
        connected_serial_number=acquisition.connected_serial_number,
        duration_s=duration_s,
        period_us=period_us,
        record_size_bytes=acquisition.record_size_bytes,
    )

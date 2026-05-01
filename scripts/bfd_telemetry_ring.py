#!/usr/bin/env python3
"""Generic MCU telemetry ring helpers for STM32 projects."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path
import struct
import sys
import time
from typing import Optional, Sequence


RING_MAGIC = 0x54444642
RING_HEADER_FORMAT = "<IHHHHIIIII"
RING_RECORD_HEADER_FORMAT = "<IIHH"
RING_HEADER_SIZE = struct.calcsize(RING_HEADER_FORMAT)
RING_RECORD_HEADER_SIZE = struct.calcsize(RING_RECORD_HEADER_FORMAT)

FIELD_TYPE_INFO = {
    "u8": {"fmt": "B", "size": 1},
    "i8": {"fmt": "b", "size": 1},
    "u16": {"fmt": "H", "size": 2},
    "i16": {"fmt": "h", "size": 2},
    "u32": {"fmt": "I", "size": 4},
    "i32": {"fmt": "i", "size": 4},
    "u64": {"fmt": "Q", "size": 8},
    "i64": {"fmt": "q", "size": 8},
    "f32": {"fmt": "f", "size": 4},
    "f64": {"fmt": "d", "size": 8},
}


class TelemetryRingError(RuntimeError):
    """Raised when telemetry ring operations fail."""


@dataclass
class FieldSpec:
    name: str
    type_name: str
    byte_size: int
    format_char: str
    offset: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RingLayout:
    fields: list[FieldSpec]
    payload_size: int
    record_stride: int
    capacity: int
    image_size: int

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["fields"] = [field.to_dict() for field in self.fields]
        return payload


@dataclass
class RingHeader:
    magic: int
    abi_version: int
    header_size: int
    record_stride: int
    capacity: int
    write_seq: int
    dropped_records: int
    flags: int

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["magic_hex"] = f"0x{self.magic:08X}"
        return payload


@dataclass
class RingRecord:
    seq: int
    time_us: int
    flags: int
    payload: dict[str, int | float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RingSnapshot:
    header: RingHeader
    layout: RingLayout
    records: list[RingRecord]

    def to_dict(self) -> dict:
        return {
            "header": self.header.to_dict(),
            "layout": self.layout.to_dict(),
            "records": [record.to_dict() for record in self.records],
        }


@dataclass
class TelemetryRingCaptureResult:
    csv_path: str
    meta_path: str
    record_count: int
    poll_count: int
    duration_s: float
    poll_period_us: int
    latest_write_seq: int
    dropped_records: int
    read_mode: str
    bytes_read: int
    full_image_reads: int
    incremental_block_reads: int
    layout: dict

    def to_dict(self) -> dict:
        return asdict(self)


def align_up(value: int, alignment: int) -> int:
    remainder = int(value) % int(alignment)
    if remainder == 0:
        return int(value)
    return int(value) + int(alignment) - remainder


def parse_field_spec(spec_text: str, *, offset: int) -> FieldSpec:
    raw = spec_text.strip()
    if ":" not in raw:
        raise TelemetryRingError(f"invalid --field syntax: {spec_text}; expected name:type")
    name, type_name = raw.split(":", 1)
    name = name.strip()
    type_key = type_name.strip().lower()
    if not name:
        raise TelemetryRingError(f"invalid empty field name in: {spec_text}")
    if type_key not in FIELD_TYPE_INFO:
        raise TelemetryRingError(f"unsupported field type: {type_name}")
    info = FIELD_TYPE_INFO[type_key]
    return FieldSpec(
        name=name,
        type_name=type_key,
        byte_size=int(info["size"]),
        format_char=str(info["fmt"]),
        offset=int(offset),
    )


def expand_field_array_spec(spec_text: str) -> list[str]:
    raw = spec_text.strip()
    parts = [part.strip() for part in raw.split(":")]
    if len(parts) != 3:
        raise TelemetryRingError(
            f"invalid --field-array syntax: {spec_text}; expected prefix:type:count"
        )
    prefix, type_name, count_text = parts
    if not prefix:
        raise TelemetryRingError(f"invalid empty array prefix in: {spec_text}")
    if type_name.lower() not in FIELD_TYPE_INFO:
        raise TelemetryRingError(f"unsupported array field type: {type_name}")
    try:
        count = int(count_text, 10)
    except ValueError as exc:
        raise TelemetryRingError(f"invalid array count in --field-array: {spec_text}") from exc
    if count <= 0:
        raise TelemetryRingError(f"array count must be greater than zero: {spec_text}")
    width = max(2, len(str(count - 1)))
    return [f"{prefix}_{index:0{width}d}:{type_name.lower()}" for index in range(count)]


def expand_field_texts(
    field_texts: Sequence[str] | None,
    field_array_texts: Sequence[str] | None = None,
) -> list[str]:
    expanded = list(field_texts or [])
    for field_array_text in field_array_texts or []:
        expanded.extend(expand_field_array_spec(field_array_text))
    return expanded


def parse_field_specs(field_texts: Sequence[str]) -> list[FieldSpec]:
    if not field_texts:
        raise TelemetryRingError("at least one --field is required")
    fields: list[FieldSpec] = []
    offset = 0
    seen_names: set[str] = set()
    for field_text in field_texts:
        field = parse_field_spec(field_text, offset=offset)
        if field.name in seen_names:
            raise TelemetryRingError(f"duplicate field name: {field.name}")
        seen_names.add(field.name)
        fields.append(field)
        offset += field.byte_size
    return fields


def build_layout(fields: Sequence[FieldSpec], *, capacity: int, record_stride: int | None = None) -> RingLayout:
    payload_size = sum(field.byte_size for field in fields)
    minimum_stride = align_up(RING_RECORD_HEADER_SIZE + payload_size, 4)
    stride = minimum_stride if record_stride is None else int(record_stride)
    if capacity <= 0:
        raise TelemetryRingError("capacity must be greater than zero")
    if stride < minimum_stride:
        raise TelemetryRingError(
            f"record_stride is too small for the declared payload: required {minimum_stride}, got {stride}"
        )
    return RingLayout(
        fields=list(fields),
        payload_size=payload_size,
        record_stride=stride,
        capacity=int(capacity),
        image_size=RING_HEADER_SIZE + stride * int(capacity),
    )


def decode_ring_header(raw_bytes: bytes) -> RingHeader:
    if len(raw_bytes) < RING_HEADER_SIZE:
        raise TelemetryRingError(f"short ring header: expected {RING_HEADER_SIZE}, got {len(raw_bytes)}")
    values = struct.unpack_from(RING_HEADER_FORMAT, raw_bytes, 0)
    magic, abi_version, header_size, record_stride, _reserved0, capacity, write_seq, dropped_records, flags, _reserved1 = values
    if magic != RING_MAGIC:
        raise TelemetryRingError(f"ring magic mismatch: expected 0x{RING_MAGIC:08X}, got 0x{magic:08X}")
    if header_size != RING_HEADER_SIZE:
        raise TelemetryRingError(f"unsupported ring header size: expected {RING_HEADER_SIZE}, got {header_size}")
    return RingHeader(
        magic=int(magic),
        abi_version=int(abi_version),
        header_size=int(header_size),
        record_stride=int(record_stride),
        capacity=int(capacity),
        write_seq=int(write_seq),
        dropped_records=int(dropped_records),
        flags=int(flags),
    )


def decode_payload(fields: Sequence[FieldSpec], payload_bytes: bytes) -> dict[str, int | float]:
    values: dict[str, int | float] = {}
    for field in fields:
        end = field.offset + field.byte_size
        raw = payload_bytes[field.offset:end]
        if len(raw) != field.byte_size:
            raise TelemetryRingError(
                f"short payload for field {field.name}: expected {field.byte_size}, got {len(raw)}"
            )
        values[field.name] = struct.unpack_from(f"<{field.format_char}", raw, 0)[0]
    return values


def decode_ring_image(image_bytes: bytes, fields: Sequence[FieldSpec]) -> RingSnapshot:
    header = decode_ring_header(image_bytes[:RING_HEADER_SIZE])
    layout = build_layout(fields, capacity=header.capacity, record_stride=header.record_stride)
    if len(image_bytes) < layout.image_size:
        raise TelemetryRingError(f"short ring image: expected {layout.image_size}, got {len(image_bytes)}")

    records: list[RingRecord] = []
    for slot_index in range(layout.capacity):
        record_offset = RING_HEADER_SIZE + slot_index * layout.record_stride
        seq, time_us, payload_size, flags = struct.unpack_from(RING_RECORD_HEADER_FORMAT, image_bytes, record_offset)
        if payload_size == 0 or seq >= header.write_seq:
            continue
        if payload_size > layout.payload_size:
            raise TelemetryRingError(
                f"record payload_size exceeds declared layout: slot={slot_index}, payload_size={payload_size}, layout_payload_size={layout.payload_size}"
            )
        payload_start = record_offset + RING_RECORD_HEADER_SIZE
        payload = decode_payload(fields, image_bytes[payload_start : payload_start + payload_size])
        records.append(RingRecord(seq=int(seq), time_us=int(time_us), flags=int(flags), payload=payload))
    records.sort(key=lambda record: record.seq)
    return RingSnapshot(header=header, layout=layout, records=records)


def collect_new_records(snapshot: RingSnapshot, last_seq: int) -> list[RingRecord]:
    return [record for record in snapshot.records if record.seq > int(last_seq)]


def build_incremental_slot_ranges(layout: RingLayout, start_seq: int, end_seq: int) -> list[tuple[int, int]]:
    if end_seq < start_seq:
        return []
    total_count = end_seq - start_seq + 1
    if total_count > layout.capacity:
        raise TelemetryRingError(
            f"requested incremental read exceeds ring capacity: total_count={total_count}, capacity={layout.capacity}"
        )
    start_slot = start_seq % layout.capacity
    first_count = min(total_count, layout.capacity - start_slot)
    ranges = [(start_slot, first_count)]
    remaining = total_count - first_count
    if remaining > 0:
        ranges.append((0, remaining))
    return ranges


def pack_record_into(
    image: bytearray,
    layout: RingLayout,
    slot_index: int,
    *,
    seq: int,
    time_us: int,
    flags: int,
    payload_values: dict[str, int | float],
) -> None:
    if slot_index < 0 or slot_index >= layout.capacity:
        raise TelemetryRingError(f"slot index out of range: {slot_index}")
    payload = bytearray(layout.payload_size)
    for field in layout.fields:
        if field.name not in payload_values:
            raise TelemetryRingError(f"missing payload field: {field.name}")
        struct.pack_into(f"<{field.format_char}", payload, field.offset, payload_values[field.name])
    record_offset = RING_HEADER_SIZE + slot_index * layout.record_stride
    struct.pack_into(
        RING_RECORD_HEADER_FORMAT,
        image,
        record_offset,
        int(seq),
        int(time_us),
        layout.payload_size,
        int(flags),
    )
    payload_start = record_offset + RING_RECORD_HEADER_SIZE
    image[payload_start : payload_start + layout.payload_size] = payload


def read_block_bytes(target, address: int, byte_size: int) -> bytes:
    if byte_size <= 0:
        raise TelemetryRingError("byte_size must be greater than zero")
    if byte_size == 1:
        return int(target.read8(address)).to_bytes(1, "little")
    if byte_size == 2 and address % 2 == 0:
        return int(target.read16(address)).to_bytes(2, "little")
    if byte_size == 4 and address % 4 == 0:
        return int(target.read32(address)).to_bytes(4, "little")
    if byte_size % 4 == 0 and address % 4 == 0:
        words = target.read_memory_block32(address, byte_size // 4)
        return b"".join(int(word).to_bytes(4, "little") for word in words)
    return bytes(target.read_memory_block8(address, byte_size))


def decode_records_from_slot_bytes(
    slot_bytes: bytes,
    fields: Sequence[FieldSpec],
    layout: RingLayout,
    *,
    write_seq_limit: int,
) -> list[RingRecord]:
    if len(slot_bytes) % layout.record_stride != 0:
        raise TelemetryRingError(
            f"slot byte length is not a multiple of record_stride: bytes={len(slot_bytes)}, stride={layout.record_stride}"
        )

    records: list[RingRecord] = []
    slot_count = len(slot_bytes) // layout.record_stride
    for slot_offset in range(slot_count):
        offset = slot_offset * layout.record_stride
        seq, time_us, payload_size, flags = struct.unpack_from(
            RING_RECORD_HEADER_FORMAT, slot_bytes, offset
        )
        if payload_size == 0 or seq >= int(write_seq_limit):
            continue
        if payload_size > layout.payload_size:
            raise TelemetryRingError(
                f"record payload_size exceeds declared layout in incremental read: payload_size={payload_size}, layout_payload_size={layout.payload_size}"
            )
        payload_start = offset + RING_RECORD_HEADER_SIZE
        payload = decode_payload(fields, slot_bytes[payload_start : payload_start + payload_size])
        records.append(RingRecord(seq=int(seq), time_us=int(time_us), flags=int(flags), payload=payload))
    records.sort(key=lambda record: record.seq)
    return records


def read_incremental_records(
    target,
    *,
    base_address: int,
    fields: Sequence[FieldSpec],
    layout: RingLayout,
    last_seq: int,
    write_seq: int,
) -> tuple[list[RingRecord], int, int]:
    start_seq = int(last_seq) + 1
    end_seq = int(write_seq) - 1
    if end_seq < start_seq:
        return [], 0, 0

    ranges = build_incremental_slot_ranges(layout, start_seq, end_seq)
    collected: dict[int, RingRecord] = {}
    bytes_read = 0
    for slot_index, slot_count in ranges:
        address = int(base_address) + RING_HEADER_SIZE + slot_index * layout.record_stride
        byte_size = slot_count * layout.record_stride
        raw = read_block_bytes(target, address, byte_size)
        bytes_read += len(raw)
        for record in decode_records_from_slot_bytes(
            raw, fields, layout, write_seq_limit=write_seq
        ):
            if start_seq <= record.seq <= end_seq:
                collected[record.seq] = record
    records = [collected[seq] for seq in sorted(collected)]
    return records, bytes_read, len(ranges)


def connect_pyocd_target(*, target_name: str, uid: str | None, frequency_hz: int):
    try:
        from pyocd.core.helpers import ConnectHelper
    except ImportError as exc:
        raise TelemetryRingError("pyocd Python package not found; run this script with the project's pyocd venv") from exc

    options = {
        "frequency": int(frequency_hz),
        "target_override": target_name,
        "connect_mode": "attach",
        "cache.enable_memory": False,
        "resume_on_disconnect": True,
    }
    return ConnectHelper.session_with_chosen_probe(unique_id=uid, options=options)


def write_capture_csv(csv_path: str | Path, records: Sequence[RingRecord], fields: Sequence[FieldSpec]) -> Path:
    output = Path(csv_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    header = ["sample_index", "time_us", "flags", *[field.name for field in fields]]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for record in records:
            row: list[object] = [record.seq, record.time_us, record.flags]
            row.extend(record.payload[field.name] for field in fields)
            writer.writerow(row)
    return output


def write_capture_meta(meta_path: str | Path, result: TelemetryRingCaptureResult) -> Path:
    output = Path(meta_path).expanduser().resolve()
    output.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def capture_ring_with_pyocd(
    *,
    address: int,
    field_texts: Sequence[str],
    field_array_texts: Sequence[str] | None,
    target_name: str,
    uid: str | None,
    frequency_hz: int,
    duration_s: float,
    poll_period_us: int,
    output_csv: str,
) -> TelemetryRingCaptureResult:
    if duration_s <= 0:
        raise TelemetryRingError("duration must be greater than zero")
    if poll_period_us < 0:
        raise TelemetryRingError("poll-period-us must be greater than or equal to zero")

    fields = parse_field_specs(expand_field_texts(field_texts, field_array_texts))
    records: list[RingRecord] = []
    last_seq = -1
    latest_snapshot: RingSnapshot | None = None
    poll_count = 0
    bytes_read = 0
    full_image_reads = 0
    incremental_block_reads = 0
    period_s = poll_period_us / 1_000_000.0 if poll_period_us > 0 else 0.0

    with connect_pyocd_target(target_name=target_name, uid=uid, frequency_hz=frequency_hz) as session:
        target = session.board.target
        start = time.monotonic()
        deadline = start + duration_s
        next_poll = start
        while time.monotonic() < deadline:
            header_bytes = read_block_bytes(target, int(address), RING_HEADER_SIZE)
            bytes_read += len(header_bytes)
            header = decode_ring_header(header_bytes)
            layout = build_layout(fields, capacity=header.capacity, record_stride=header.record_stride)
            need_full_snapshot = (
                latest_snapshot is None
                or latest_snapshot.layout.capacity != layout.capacity
                or latest_snapshot.layout.record_stride != layout.record_stride
                or last_seq < 0
                or (header.write_seq - (last_seq + 1)) >= layout.capacity
            )

            if need_full_snapshot:
                image_bytes = read_block_bytes(target, int(address), layout.image_size)
                bytes_read += len(image_bytes)
                full_image_reads += 1
                snapshot = decode_ring_image(image_bytes, fields)
                fresh = collect_new_records(snapshot, last_seq)
                latest_snapshot = snapshot
            else:
                fresh, incremental_bytes, incremental_ranges = read_incremental_records(
                    target,
                    base_address=int(address),
                    fields=fields,
                    layout=layout,
                    last_seq=last_seq,
                    write_seq=header.write_seq,
                )
                expected_count = max(0, header.write_seq - (last_seq + 1))
                bytes_read += incremental_bytes
                incremental_block_reads += incremental_ranges
                if len(fresh) != expected_count:
                    image_bytes = read_block_bytes(target, int(address), layout.image_size)
                    bytes_read += len(image_bytes)
                    full_image_reads += 1
                    snapshot = decode_ring_image(image_bytes, fields)
                    fresh = collect_new_records(snapshot, last_seq)
                    latest_snapshot = snapshot
                else:
                    latest_snapshot = RingSnapshot(header=header, layout=layout, records=fresh)

            if fresh:
                records.extend(fresh)
                last_seq = fresh[-1].seq
            poll_count += 1
            if period_s <= 0:
                continue
            next_poll += period_s
            sleep_s = next_poll - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)

    if latest_snapshot is None:
        raise TelemetryRingError("no telemetry ring snapshots captured")

    csv_path = write_capture_csv(output_csv, records, fields)
    meta_path = Path(f"{csv_path}.meta.json")
    result = TelemetryRingCaptureResult(
        csv_path=str(csv_path),
        meta_path=str(meta_path),
        record_count=len(records),
        poll_count=poll_count,
        duration_s=float(duration_s),
        poll_period_us=int(poll_period_us),
        latest_write_seq=int(latest_snapshot.header.write_seq),
        dropped_records=int(latest_snapshot.header.dropped_records),
        read_mode="incremental",
        bytes_read=int(bytes_read),
        full_image_reads=int(full_image_reads),
        incremental_block_reads=int(incremental_block_reads),
        layout=latest_snapshot.layout.to_dict(),
    )
    write_capture_meta(meta_path, result)
    return result


def output_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generic MCU telemetry ring helpers")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    layout = subparsers.add_parser("layout", help="Compute telemetry ring image sizes from a field list")
    layout.add_argument("--field", action="append", help="Payload field in name:type form; repeat for multi-field payloads")
    layout.add_argument("--field-array", action="append", help="Field array in prefix:type:count form; repeat for multiple arrays")
    layout.add_argument("--capacity", type=int, required=True, help="Ring slot count")

    capture = subparsers.add_parser("capture-pyocd", help="Capture a generic telemetry ring through PyOCD polling")
    capture.add_argument("--address", required=True, help="Ring base address")
    capture.add_argument("--field", action="append", help="Payload field in name:type form; repeat for multi-field payloads")
    capture.add_argument("--field-array", action="append", help="Field array in prefix:type:count form; repeat for multiple arrays")
    capture.add_argument("--target", required=True, help="PyOCD target name, e.g. stm32h723xx")
    capture.add_argument("--uid", help="CMSIS-DAP probe UID")
    capture.add_argument("--frequency", type=int, default=10_000_000, help="SWD/JTAG frequency in Hz")
    capture.add_argument("--duration", type=float, required=True, help="Capture duration in seconds")
    capture.add_argument("--poll-period-us", type=int, default=1000, help="Ring polling period; 0 means run as fast as possible")
    capture.add_argument("--output", required=True, help="CSV output path")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "layout":
            fields = parse_field_specs(expand_field_texts(args.field, getattr(args, "field_array", None)))
            layout = build_layout(fields, capacity=args.capacity)
            output_json(layout.to_dict())
            return 0
        if args.command == "capture-pyocd":
            result = capture_ring_with_pyocd(
                address=int(args.address, 0),
                field_texts=args.field,
                field_array_texts=getattr(args, "field_array", None),
                target_name=args.target,
                uid=args.uid,
                frequency_hz=args.frequency,
                duration_s=args.duration,
                poll_period_us=args.poll_period_us,
                output_csv=args.output,
            )
            output_json(result.to_dict())
            return 0
        raise TelemetryRingError(f"unsupported command: {args.command}")
    except (TelemetryRingError, Exception) as exc:
        payload = {"error": str(exc), "type": type(exc).__name__}
        if getattr(args, "json", False):
            output_json(payload)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

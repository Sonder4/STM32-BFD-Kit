import importlib.util
from pathlib import Path
import struct
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_telemetry_ring.py"
SPEC = importlib.util.spec_from_file_location("bfd_telemetry_ring", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_field_specs_and_layout():
    fields = MODULE.parse_field_specs(["pos:f32", "vel:f32", "state:u8"])
    layout = MODULE.build_layout(fields, capacity=8)

    assert [field.name for field in fields] == ["pos", "vel", "state"]
    assert layout.payload_size == 9
    assert layout.record_stride == 24
    assert layout.image_size == MODULE.RING_HEADER_SIZE + 8 * 24


def test_expand_field_texts_supports_field_array():
    field_texts = MODULE.expand_field_texts(["state:u32"], ["bench:f32:4"])
    fields = MODULE.parse_field_specs(field_texts)

    assert field_texts == [
        "state:u32",
        "bench_00:f32",
        "bench_01:f32",
        "bench_02:f32",
        "bench_03:f32",
    ]
    assert [field.name for field in fields] == [
        "state",
        "bench_00",
        "bench_01",
        "bench_02",
        "bench_03",
    ]


def test_decode_ring_image_returns_records_in_sequence_order():
    fields = MODULE.parse_field_specs(["pos:f32", "vel:f32"])
    layout = MODULE.build_layout(fields, capacity=4)
    image = bytearray(layout.image_size)
    struct.pack_into(
        MODULE.RING_HEADER_FORMAT,
        image,
        0,
        MODULE.RING_MAGIC,
        1,
        MODULE.RING_HEADER_SIZE,
        layout.record_stride,
        0,
        4,
        3,
        0,
        0,
        0,
    )
    MODULE.pack_record_into(image, layout, 0, seq=0, time_us=0, flags=0, payload_values={"pos": 1.0, "vel": 2.0})
    MODULE.pack_record_into(image, layout, 1, seq=1, time_us=1000, flags=0, payload_values={"pos": 3.0, "vel": 4.0})
    MODULE.pack_record_into(image, layout, 2, seq=2, time_us=2000, flags=0, payload_values={"pos": 5.0, "vel": 6.0})

    snapshot = MODULE.decode_ring_image(bytes(image), fields)

    assert snapshot.header.write_seq == 3
    assert [record.seq for record in snapshot.records] == [0, 1, 2]
    assert snapshot.records[2].payload["pos"] == 5.0
    assert snapshot.records[2].payload["vel"] == 6.0


def test_collect_new_records_handles_wraparound():
    fields = MODULE.parse_field_specs(["value:u32"])
    layout = MODULE.build_layout(fields, capacity=4)
    image = bytearray(layout.image_size)
    struct.pack_into(
        MODULE.RING_HEADER_FORMAT,
        image,
        0,
        MODULE.RING_MAGIC,
        1,
        MODULE.RING_HEADER_SIZE,
        layout.record_stride,
        0,
        4,
        6,
        0,
        0,
        0,
    )
    MODULE.pack_record_into(image, layout, 0, seq=4, time_us=4000, flags=0, payload_values={"value": 40})
    MODULE.pack_record_into(image, layout, 1, seq=5, time_us=5000, flags=0, payload_values={"value": 50})
    MODULE.pack_record_into(image, layout, 2, seq=2, time_us=2000, flags=0, payload_values={"value": 20})
    MODULE.pack_record_into(image, layout, 3, seq=3, time_us=3000, flags=0, payload_values={"value": 30})

    snapshot = MODULE.decode_ring_image(bytes(image), fields)
    fresh = MODULE.collect_new_records(snapshot, last_seq=3)

    assert [record.seq for record in fresh] == [4, 5]
    assert [record.payload["value"] for record in fresh] == [40, 50]


def test_build_incremental_slot_ranges_wraps_once():
    fields = MODULE.parse_field_specs(["value:u32"])
    layout = MODULE.build_layout(fields, capacity=8)

    ranges = MODULE.build_incremental_slot_ranges(layout, start_seq=6, end_seq=10)

    assert ranges == [(6, 2), (0, 3)]


def test_decode_records_from_slot_bytes_filters_by_write_seq_limit():
    fields = MODULE.parse_field_specs(["value:u32"])
    layout = MODULE.build_layout(fields, capacity=4)
    image = bytearray(layout.image_size)
    struct.pack_into(
        MODULE.RING_HEADER_FORMAT,
        image,
        0,
        MODULE.RING_MAGIC,
        1,
        MODULE.RING_HEADER_SIZE,
        layout.record_stride,
        0,
        4,
        6,
        0,
        0,
        0,
    )
    MODULE.pack_record_into(image, layout, 0, seq=4, time_us=4000, flags=0, payload_values={"value": 40})
    MODULE.pack_record_into(image, layout, 1, seq=5, time_us=5000, flags=0, payload_values={"value": 50})
    MODULE.pack_record_into(image, layout, 2, seq=6, time_us=6000, flags=0, payload_values={"value": 60})

    raw = image[MODULE.RING_HEADER_SIZE : MODULE.RING_HEADER_SIZE + 3 * layout.record_stride]
    records = MODULE.decode_records_from_slot_bytes(
        bytes(raw), fields, layout, write_seq_limit=6
    )

    assert [record.seq for record in records] == [4, 5]
    assert [record.payload["value"] for record in records] == [40, 50]

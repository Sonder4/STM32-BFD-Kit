import importlib.util
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_pyocd_hss.py"
SPEC = importlib.util.spec_from_file_location("bfd_pyocd_hss", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeSymbol:
    def __init__(self, expression, address, byte_size):
        self.expression = expression
        self.final_address = address
        self.byte_size = byte_size
        self.final_type_name = "unsigned int"
        self.final_type_tag = "DW_TAG_base_type"
        self.final_type_display = "unsigned int"

    def to_dict(self):
        return {
            "expression": self.expression,
            "final_address": self.final_address,
            "byte_size": self.byte_size,
        }


class FakeTarget:
    def __init__(self, memory=None):
        self.memory = memory or {}
        self.calls = []

    def _read_bytes(self, address, count):
        return bytes(self.memory.get(address + offset, 0) for offset in range(count))

    def read8(self, address):
        self.calls.append(("read8", address))
        return int.from_bytes(self._read_bytes(address, 1), "little")

    def read16(self, address):
        self.calls.append(("read16", address))
        return int.from_bytes(self._read_bytes(address, 2), "little")

    def read32(self, address):
        self.calls.append(("read32", address))
        return int.from_bytes(self._read_bytes(address, 4), "little")

    def read_memory_block32(self, address, count):
        self.calls.append(("read_memory_block32", address, count))
        raw = self._read_bytes(address, count * 4)
        return [int.from_bytes(raw[index : index + 4], "little") for index in range(0, len(raw), 4)]

    def read_memory_block8(self, address, count):
        self.calls.append(("read_memory_block8", address, count))
        return list(self._read_bytes(address, count))


def test_parse_address_spec_supports_named_scalar_types():
    spec = MODULE.parse_address_spec("tim2_cnt@0x40000024:u32")

    assert spec.expression == "tim2_cnt"
    assert spec.final_address == 0x40000024
    assert spec.byte_size == 4
    assert spec.final_type_name == "uint32_t"


def test_load_hssdv_project_specs_uses_enabled_entries_only(tmp_path):
    project_path = tmp_path / "demo.HSSDVProj"
    project_path.write_text(
        """
[TestSettings]
VarNum=3

[VarInfo0]
VarName=uwTick
VarAlias=系统Tick
Address=0x20000174
Formula=%1
Type=0
Size=4
TypeDesc=volatile uint32_t (volatile unsigned int)
isEnableSmpl=true

[VarInfo1]
VarName=disabledVar
VarAlias=disabledVar
Address=0x20000178
Formula=%1
Type=4
Size=4
TypeDesc=float (float)
isEnableSmpl=false

[VarInfo2]
VarName=sI16VarTest
VarAlias=sI16VarTest
Address=0x20000164
Formula=%1
Type=2
Size=2
TypeDesc=int16_t (short)
isEnableSmpl=true
""".strip(),
        encoding="utf-8",
    )

    specs = MODULE.load_hssdv_project_specs(project_path)

    assert [spec.expression for spec in specs] == ["uwTick", "sI16VarTest"]
    assert specs[0].alias == "系统Tick"
    assert specs[0].formula == "%1"
    assert specs[1].final_type_name == "int16_t"


def test_build_read_plan_coalesces_contiguous_specs():
    specs = [
        MODULE.parse_address_spec("speed@0x20000000:u32"),
        MODULE.parse_address_spec("current@0x20000004:u16"),
        MODULE.parse_address_spec("temp@0x20000010:u32"),
    ]

    plan = MODULE.build_read_plan(specs)

    assert len(plan) == 2
    assert (plan[0].start_address, plan[0].byte_size, plan[0].access_kind) == (0x20000000, 6, "block8")
    assert [spec.expression for spec in plan[0].specs] == ["speed", "current"]
    assert (plan[1].start_address, plan[1].byte_size, plan[1].access_kind) == (0x20000010, 4, "read32")


def test_sample_once_uses_single_block_read_for_contiguous_specs():
    target = FakeTarget(
        memory={
            0x20000000: 0x78,
            0x20000001: 0x56,
            0x20000002: 0x34,
            0x20000003: 0x12,
            0x20000004: 0xCD,
            0x20000005: 0xAB,
        }
    )
    specs = [
        MODULE.parse_address_spec("speed@0x20000000:u32"),
        MODULE.parse_address_spec("current@0x20000004:u16"),
    ]
    plan = MODULE.build_read_plan(specs)

    row = MODULE.sample_once(target, specs, sample_index=3, start_ns=1, read_plan=plan)

    assert row.sample_index == 3
    assert row.values["speed"] == 0x12345678
    assert row.values["current"] == 0xABCD
    assert target.calls == [("read_memory_block8", 0x20000000, 6)]


def test_sample_once_prefers_block32_for_aligned_regions():
    target = FakeTarget(
        memory={
            0x20000000: 0x78,
            0x20000001: 0x56,
            0x20000002: 0x34,
            0x20000003: 0x12,
            0x20000004: 0xEF,
            0x20000005: 0xCD,
            0x20000006: 0xAB,
            0x20000007: 0x90,
        }
    )
    specs = [
        MODULE.parse_address_spec("speed@0x20000000:u32"),
        MODULE.parse_address_spec("position@0x20000004:u32"),
    ]
    plan = MODULE.build_read_plan(specs)

    row = MODULE.sample_once(target, specs, sample_index=0, start_ns=1, read_plan=plan)

    assert row.values["speed"] == 0x12345678
    assert row.values["position"] == 0x90ABCDEF
    assert target.calls == [("read_memory_block32", 0x20000000, 2)]


def test_read_symbol_bytes_prefers_aligned_access():
    target = FakeTarget(
        memory={
            0x20000001: 0x01,
            0x20000002: 0x34,
            0x20000003: 0x12,
            0x20000004: 0x78,
            0x20000005: 0x56,
            0x20000006: 0x34,
            0x20000007: 0x12,
        }
    )

    assert MODULE.read_symbol_bytes(target, FakeSymbol("u8", 0x20000001, 1)) == b"\x01"
    assert MODULE.read_symbol_bytes(target, FakeSymbol("u16", 0x20000002, 2)) == b"\x34\x12"
    assert MODULE.read_symbol_bytes(target, FakeSymbol("u32", 0x20000004, 4)) == b"\x78\x56\x34\x12"


def test_read_symbol_bytes_reads_aligned_multiword():
    target = FakeTarget(
        memory={
            0x20000000: 0x44,
            0x20000001: 0x33,
            0x20000002: 0x22,
            0x20000003: 0x11,
            0x20000004: 0x45,
            0x20000005: 0x33,
            0x20000006: 0x22,
            0x20000007: 0x11,
        }
    )

    assert MODULE.read_symbol_bytes(target, FakeSymbol("u64", 0x20000000, 8)).hex() == "4433221145332211"


def test_write_csv_uses_hss_compatible_wide_columns(tmp_path):
    symbol = FakeSymbol("g_motor_data.speed", 0x20000000, 4)
    rows = [
        MODULE.PyOcdHssRow(
            sample_index=0,
            time_us=10,
            values={symbol.expression: 1},
            raw_hex={symbol.expression: "01000000"},
        )
    ]

    csv_path, columns = MODULE.write_csv(tmp_path / "sample.csv", [symbol], rows)

    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == (
        "sample_index,time_us,g_motor_data_speed__value,g_motor_data_speed__raw_hex"
    )
    assert columns[symbol.expression]["value"] == "g_motor_data_speed__value"


def test_period_stats_handles_short_and_regular_rows():
    assert MODULE.period_stats([]) == (None, None, None)
    rows = [
        MODULE.PyOcdHssRow(0, 0, {}, {}),
        MODULE.PyOcdHssRow(1, 1000, {}, {}),
        MODULE.PyOcdHssRow(2, 2200, {}, {}),
    ]

    assert MODULE.period_stats(rows) == (1100.0, 1000, 1200)


def test_build_float_benchmark_specs_creates_contiguous_f32_layout():
    specs = MODULE.build_float_benchmark_specs(0x20001000, 3)

    assert [spec.expression for spec in specs] == ["f00", "f01", "f02"]
    assert [spec.final_address for spec in specs] == [0x20001000, 0x20001004, 0x20001008]
    assert all(spec.final_type_name == "float" for spec in specs)


def test_make_benchmark_entry_marks_stable_1000hz():
    rows = [
        MODULE.PyOcdHssRow(0, 0, {}, {}),
        MODULE.PyOcdHssRow(1, 998, {}, {}),
        MODULE.PyOcdHssRow(2, 2003, {}, {}),
        MODULE.PyOcdHssRow(3, 3001, {}, {}),
    ]

    entry = MODULE.make_benchmark_entry(
        float_count=8,
        duration_s=0.004,
        requested_period_us=1000,
        rows=rows,
    )

    assert entry.float_count == 8
    assert entry.payload_bytes == 32
    assert entry.stable_1000hz is True
    assert entry.throughput_bytes_per_s == 32000.0


def test_select_max_stable_float_count_returns_largest_stable_entry():
    entries = [
        MODULE.PyOcdBenchmarkEntry(
            float_count=4,
            payload_bytes=16,
            sample_count=200,
            duration_s=0.2,
            requested_period_us=1000,
            actual_mean_period_us=999.0,
            actual_min_period_us=995,
            actual_max_period_us=1008,
            throughput_bytes_per_s=16000.0,
            stable_1000hz=True,
        ),
        MODULE.PyOcdBenchmarkEntry(
            float_count=8,
            payload_bytes=32,
            sample_count=200,
            duration_s=0.2,
            requested_period_us=1000,
            actual_mean_period_us=1001.0,
            actual_min_period_us=996,
            actual_max_period_us=1010,
            throughput_bytes_per_s=32000.0,
            stable_1000hz=True,
        ),
        MODULE.PyOcdBenchmarkEntry(
            float_count=12,
            payload_bytes=48,
            sample_count=150,
            duration_s=0.2,
            requested_period_us=1000,
            actual_mean_period_us=1340.0,
            actual_min_period_us=1010,
            actual_max_period_us=1800,
            throughput_bytes_per_s=36000.0,
            stable_1000hz=False,
        ),
    ]

    assert MODULE.select_max_stable_float_count(entries) == 8

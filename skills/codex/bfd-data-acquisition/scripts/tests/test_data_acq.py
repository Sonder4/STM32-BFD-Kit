import csv
import importlib.util
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "data_acq.py"
SPEC = importlib.util.spec_from_file_location("data_acq", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DataAcqTest(unittest.TestCase):
    def test_find_profile_candidate_paths_supports_bfd_kit_and_codex_layouts(self):
        bfd_script = Path("/tmp/project/BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py")
        codex_script = Path("/tmp/project/.codex/skills/bfd-data-acquisition/scripts/data_acq.py")

        bfd_candidates = MODULE.find_profile_candidate_paths(bfd_script)
        codex_candidates = MODULE.find_profile_candidate_paths(codex_script)

        self.assertIn(Path("/tmp/project/.codex/bfd/active_profile.env"), bfd_candidates)
        self.assertIn(Path("/tmp/project/.codex/bfd/active_profile.env"), codex_candidates)

    def test_find_profile_candidate_paths_includes_current_project_cwd(self):
        script_path = Path("/opt/BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py")

        candidates = MODULE.find_profile_candidate_paths(
            script_path,
            cwd=Path("/tmp/project/subdir"),
        )

        self.assertIn(Path("/tmp/project/.codex/bfd/active_profile.env"), candidates)

    def test_default_dwarf_cache_root_prefers_project_cwd_codex(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / ".codex").mkdir()
            (tmp_path / "subdir").mkdir()

            cache_root = MODULE.default_dwarf_cache_root(
                script_path=Path("/opt/BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py"),
                cwd=tmp_path / "subdir",
            )

            self.assertEqual(cache_root, tmp_path / ".codex/bfd/dwarf_cache")

    def test_parse_layout_supports_u32_vectors(self):
        layout = MODULE.parse_layout("u32x2")

        self.assertEqual(layout.element_type, "u32")
        self.assertEqual(layout.count, 2)
        self.assertEqual(layout.element_size, 4)
        self.assertEqual(layout.total_size, 8)
        self.assertEqual(layout.decode(b"\x01\x00\x00\x00\x02\x00\x00\x00"), [1, 2])

    def test_nonstop_read_uses_monitor_mem_command(self):
        layout = MODULE.parse_layout("u32x2")

        self.assertEqual(
            MODULE.build_nonstop_read_command(0x20000000, layout),
            "mem32 0x20000000 2",
        )

    def test_nonstop_setup_enforces_background_access(self):
        self.assertEqual(
            MODULE.build_nonstop_setup_commands(),
            ["target extended-remote :2331", "monitor exec SetAllowStopMode = 0"],
        )

    def test_nonstop_vector_reads_use_block_mem_command(self):
        layout = MODULE.parse_layout("u32x3")

        self.assertEqual(
            MODULE.build_nonstop_read_commands(0x20000000, layout),
            ["mem32 0x20000000 3"],
        )

    def test_parse_monitor_values_accepts_data_equals_format(self):
        output = "\n".join(
            [
                "Reading from address 0x2000F860 (Data = 0x00000003)",
                "Reading from address 0x2000F864 (Data = 0x00000004)",
            ]
        )

        self.assertEqual(MODULE.parse_monitor_values(output, 4), [3, 4])

    def test_parse_monitor_values_ignores_register_dump_lines(self):
        output = "\n".join(
            [
                "R0 = 00000000, R1 = A5A5A5A5, R2 = A5A5A5A5, R3 = 00000001",
                "SP(R13)= 20000E88, MSP= 2002FFE0, PSP= 20000E88, R14(LR) = 0800DD51",
                "20010490 = 00018E88 ",
                "20010494 = 00000004 ",
            ]
        )

        self.assertEqual(MODULE.parse_monitor_values(output, 4), [0x00018E88, 0x00000004])

    def test_snapshot_savebin_command_uses_hex_size(self):
        self.assertEqual(
            MODULE.build_snapshot_savebin_command(Path("/tmp/capture.bin"), 0x2000F860, 12),
            "savebin /tmp/capture.bin 0x2000F860 0xC",
        )

    def test_is_valid_sram_pointer_accepts_internal_sram(self):
        self.assertTrue(MODULE.is_valid_sram_pointer(0x20000000))
        self.assertTrue(MODULE.is_valid_sram_pointer(0x2001FFFC))
        self.assertFalse(MODULE.is_valid_sram_pointer(0x00000000))
        self.assertFalse(MODULE.is_valid_sram_pointer(0x08000000))

    def test_pointer_sample_consistency_requires_even_stable_seq(self):
        self.assertTrue(MODULE.is_consistent_pointer_sample(8, 8, 0x20001000))
        self.assertFalse(MODULE.is_consistent_pointer_sample(7, 8, 0x20001000))
        self.assertFalse(MODULE.is_consistent_pointer_sample(9, 9, 0x20001000))
        self.assertFalse(MODULE.is_consistent_pointer_sample(8, 8, 0x00000000))

    def test_write_samples_csv_uses_metadata_columns(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "sample.csv"
            MODULE.write_samples_csv(
                csv_path,
                [
                    {
                        "host_time_s": 1.25,
                        "sample_idx": 3,
                        "symbol": "g_test",
                        "address": "0x20000000",
                        "capture_mode": "nonstop",
                        "values": [10, 20],
                    }
                ],
                value_count=2,
            )

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(
            rows[0],
            ["host_time_s", "sample_idx", "symbol", "address", "capture_mode", "value0", "value1"],
        )
        self.assertEqual(rows[1], ["1.25", "3", "g_test", "0x20000000", "nonstop", "10", "20"])

    def test_write_samples_csv_includes_pointer_metadata_columns(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "pointer_sample.csv"
            MODULE.write_samples_csv(
                csv_path,
                [
                    {
                        "host_time_s": 1.0,
                        "sample_idx": 0,
                        "symbol": "g_local_probe_addr",
                        "address": "0x20001000",
                        "capture_mode": "nonstop",
                        "pointer_symbol": "g_local_probe_addr",
                        "pointer_value": "0x20002000",
                        "seq_before": 2,
                        "seq_after": 2,
                        "values": [3.5],
                    }
                ],
                value_count=1,
            )

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(
            rows[0],
            [
                "host_time_s",
                "sample_idx",
                "symbol",
                "address",
                "capture_mode",
                "pointer_symbol",
                "pointer_value",
                "seq_before",
                "seq_after",
                "value0",
            ],
        )

    def test_decode_profile_registry_contains_symbol_sampling_profiles(self):
        registry = MODULE.get_decode_profile_registry()

        self.assertIn("u32_ptr_array", registry)
        self.assertIn("dji_motor_measure", registry)
        self.assertIn("dji_motor_instance_measure", registry)
        self.assertEqual(registry["u32_ptr_array"].size, 4)
        self.assertEqual(registry["dji_motor_measure"].size, 28)
        self.assertEqual(registry["dji_motor_instance_measure"].size, 28)

    def test_decode_u32_ptr_array_entries_shapes_pointer_rows(self):
        rows = MODULE.decode_u32_ptr_array_entries(
            symbol="__hub_m3508_inst",
            symbol_address=0x08004000,
            pointer_values=[0x20001000, 0x00000000, 0x08001234],
        )

        self.assertEqual(
            rows,
            [
                {
                    "index": 0,
                    "symbol": "__hub_m3508_inst",
                    "symbol_address": "0x08004000",
                    "entry_address": "0x08004000",
                    "pointer_value": "0x20001000",
                    "is_null": False,
                    "is_sram_pointer": True,
                },
                {
                    "index": 1,
                    "symbol": "__hub_m3508_inst",
                    "symbol_address": "0x08004000",
                    "entry_address": "0x08004004",
                    "pointer_value": "0x00000000",
                    "is_null": True,
                    "is_sram_pointer": False,
                },
                {
                    "index": 2,
                    "symbol": "__hub_m3508_inst",
                    "symbol_address": "0x08004000",
                    "entry_address": "0x08004008",
                    "pointer_value": "0x08001234",
                    "is_null": False,
                    "is_sram_pointer": False,
                },
            ],
        )

    def test_decode_dji_motor_measure_bytes_returns_named_fields(self):
        raw = (
            b"\x34\x12"
            b"\x78\x56"
            b"\x00\x00\x20\x41"
            b"\x00\x00\xA0\x41"
            b"\x9C\xFF"
            b"\x2C\x01"
            b"\x37"
            b"\x00\x00\x00"
            b"\x00\x00\xC8\x42"
            b"\x05\x00\x00\x00"
        )

        row = MODULE.decode_dji_motor_measure_bytes(
            raw,
            symbol="motor_measure_0",
            base_address=0x20002000,
            index=0,
        )

        self.assertEqual(row["symbol"], "motor_measure_0")
        self.assertEqual(row["base_address"], "0x20002000")
        self.assertEqual(row["last_ecd"], 0x1234)
        self.assertEqual(row["ecd"], 0x5678)
        self.assertAlmostEqual(row["angle_single_round_deg"], 10.0)
        self.assertAlmostEqual(row["speed_deg_per_s"], 20.0)
        self.assertEqual(row["speed_rpm"], -100)
        self.assertEqual(row["real_current"], 300)
        self.assertEqual(row["temperature_c"], 55)
        self.assertAlmostEqual(row["total_angle_deg"], 100.0)
        self.assertEqual(row["total_round"], 5)

    def test_decode_dji_motor_instance_measure_adds_instance_metadata(self):
        raw = (
            b"\x01\x00"
            b"\x02\x00"
            b"\x00\x00\x80\x3F"
            b"\x00\x00\x00\x40"
            b"\x03\x00"
            b"\x04\x00"
            b"\x05"
            b"\x00\x00\x00"
            b"\x00\x00\x40\x40"
            b"\x06\x00\x00\x00"
        )

        row = MODULE.decode_dji_motor_instance_measure_bytes(
            raw,
            symbol="__hub_m3508_inst",
            instance_pointer=0x20003000,
            index=2,
        )

        self.assertEqual(row["symbol"], "__hub_m3508_inst")
        self.assertEqual(row["index"], 2)
        self.assertEqual(row["instance_pointer"], "0x20003000")
        self.assertEqual(row["measure_base_address"], "0x20003000")
        self.assertEqual(row["last_ecd"], 1)
        self.assertEqual(row["ecd"], 2)
        self.assertEqual(row["speed_rpm"], 3)
        self.assertEqual(row["real_current"], 4)
        self.assertEqual(row["temperature_c"], 5)
        self.assertEqual(row["total_round"], 6)

    def test_build_symbol_summary_reports_pointer_counts(self):
        summary = MODULE.build_symbol_summary(
            metadata={
                "symbol": "__hub_m3508_inst",
                "mode": "symbol",
                "decode_profile": "u32_ptr_array",
                "count": 4,
            },
            rows=[
                {"index": 0, "pointer_value": "0x20001000", "is_null": False, "is_sram_pointer": True},
                {"index": 1, "pointer_value": "0x00000000", "is_null": True, "is_sram_pointer": False},
                {"index": 2, "pointer_value": "0x20002000", "is_null": False, "is_sram_pointer": True},
                {"index": 3, "pointer_value": "0x08001234", "is_null": False, "is_sram_pointer": False},
            ],
        )

        self.assertIn("symbol: __hub_m3508_inst", summary)
        self.assertIn("decode_profile: u32_ptr_array", summary)
        self.assertIn("entries: 4", summary)
        self.assertIn("null_entries: 1", summary)
        self.assertIn("sram_pointer_entries: 2", summary)

    def test_validate_args_rejects_decode_profile_and_layout_together(self):
        args = Namespace(
            mode="symbol",
            capture_mode="snapshot",
            symbol="__hub_m3508_inst",
            decode_profile="u32_ptr_array",
            layout="u32x4",
            pointer_array=False,
            follow_pointer=False,
            variable=None,
            address=None,
            pointer_symbol=None,
            rtt=False,
        )

        with self.assertRaisesRegex(ValueError, "--decode-profile and --layout are mutually exclusive"):
            MODULE.validate_args(args)

    def test_validate_args_requires_pointer_array_before_follow_pointer(self):
        args = Namespace(
            mode="symbol",
            capture_mode="snapshot",
            symbol="__hub_m3508_inst",
            decode_profile="dji_motor_instance_measure",
            layout=None,
            pointer_array=False,
            follow_pointer=True,
            variable=None,
            address=None,
            pointer_symbol=None,
            rtt=False,
        )

        with self.assertRaisesRegex(ValueError, "--follow-pointer requires --pointer-array"):
            MODULE.validate_args(args)

    def test_validate_args_requires_symbol_in_symbol_mode(self):
        args = Namespace(
            mode="symbol",
            capture_mode="snapshot",
            symbol=None,
            decode_profile="u32_ptr_array",
            layout=None,
            pointer_array=True,
            follow_pointer=False,
            variable=None,
            address=None,
            pointer_symbol=None,
            rtt=False,
        )

        with self.assertRaisesRegex(ValueError, "--symbol is required when --mode symbol is used"):
            MODULE.validate_args(args)

    def test_validate_args_rejects_non_snapshot_capture_mode_in_symbol_mode(self):
        args = Namespace(
            mode="symbol",
            capture_mode="nonstop",
            symbol="__hub_m3508_inst",
            decode_profile="u32_ptr_array",
            layout=None,
            pointer_array=True,
            follow_pointer=False,
            variable=None,
            address=None,
            pointer_symbol=None,
            rtt=False,
            format="summary",
            count=4,
        )

        with self.assertRaisesRegex(ValueError, "symbol mode currently supports only --capture-mode snapshot"):
            MODULE.validate_args(args)

    def test_validate_args_requires_symbol_in_symbol_auto_mode(self):
        args = Namespace(
            mode="symbol-auto",
            capture_mode="snapshot",
            symbol=None,
            decode_profile=None,
            layout=None,
            pointer_array=False,
            follow_pointer=False,
            follow_depth=1,
            variable=None,
            address=None,
            pointer_symbol=None,
            rtt=False,
            format="summary",
            count=1,
        )

        with self.assertRaisesRegex(ValueError, "--symbol is required when --mode symbol-auto is used"):
            MODULE.validate_args(args)

    def test_validate_args_rejects_manual_decode_options_in_symbol_auto_mode(self):
        args = Namespace(
            mode="symbol-auto",
            capture_mode="snapshot",
            symbol="__hub_m3508_inst",
            decode_profile="u32_ptr_array",
            layout=None,
            pointer_array=False,
            follow_pointer=False,
            follow_depth=1,
            variable=None,
            address=None,
            pointer_symbol=None,
            rtt=False,
            format="summary",
            count=1,
        )

        with self.assertRaisesRegex(ValueError, "symbol-auto does not accept manual decode options"):
            MODULE.validate_args(args)

    def test_capture_symbol_auto_rows_decodes_pointer_array_with_follow_depth(self):
        type_schemas = {
            "type:Mode": type(
                "EnumSchema",
                (),
                {
                    "kind": "enum",
                    "size": 4,
                    "underlying_type": "u32",
                    "values": {"MODE_A": 0, "MODE_B": 2},
                },
            )(),
            "type:Inner": type(
                "StructSchema",
                (),
                {
                    "kind": "struct",
                    "size": 8,
                    "fields": [
                        type("Field", (), {"name": "count", "offset": 0, "type_ref": "type:unsigned int"})(),
                        type("Field", (), {"name": "mode", "offset": 4, "type_ref": "type:Mode"})(),
                    ],
                },
            )(),
            "type:Outer": type(
                "StructSchema",
                (),
                {
                    "kind": "struct",
                    "size": 16,
                    "fields": [
                        type("Field", (), {"name": "inner", "offset": 0, "type_ref": "type:Inner"})(),
                        type("Field", (), {"name": "temperature", "offset": 8, "type_ref": "type:float"})(),
                        type("Field", (), {"name": "flag", "offset": 12, "type_ref": "type:unsigned char"})(),
                    ],
                },
            )(),
            "type:pointer:OuterPtr": type(
                "PointerSchema",
                (),
                {"kind": "pointer", "size": 4, "pointer_size": 4, "target_type_ref": "type:Outer"},
            )(),
            "type:array:type_pointer_OuterPtr[2]": type(
                "ArraySchema",
                (),
                {
                    "kind": "array",
                    "size": 8,
                    "count": 2,
                    "element_type_ref": "type:pointer:OuterPtr",
                    "stride": 4,
                },
            )(),
        }

        class FakeAcq:
            def read_snapshot_block(self, address, size):
                blobs = {
                    0x20010000: b"\x00\x10\x00\x20\x10\x10\x00\x20",
                    0x20001000: b"\x07\x00\x00\x00\x02\x00\x00\x00\x00\x00\x12\x42\x01\x00\x00\x00",
                    0x20001010: b"\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\x42\x00\x00\x00\x00",
                }
                self.last = (address, size)
                return blobs[address]

        rows = MODULE.capture_symbol_auto_rows(
            FakeAcq(),
            symbol_name="g_outer_ptrs",
            symbol_address=0x20010000,
            root_type_ref="type:array:type_pointer_OuterPtr[2]",
            type_schemas=type_schemas,
            follow_depth=1,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "g_outer_ptrs")
        self.assertEqual(rows[0]["__address__"], "0x20001000")
        self.assertEqual(rows[0]["__decode_status__"], "ok")
        self.assertEqual(rows[0]["inner"]["count"], 7)
        self.assertEqual(rows[0]["inner"]["mode"]["name"], "MODE_B")
        self.assertAlmostEqual(rows[0]["temperature"], 36.5)
        self.assertEqual(rows[1]["inner"]["count"], 8)

    def test_load_symbol_auto_schema_from_cache_reads_builtin_root_symbol(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            elf_path = tmp_path / "firmware.elf"
            cache_root = tmp_path / "cache"
            elf_path.write_bytes(b"ELFTEST")

            dwarf_schema = MODULE.load_local_module("dwarf_schema")
            fingerprint = dwarf_schema.compute_elf_fingerprint(elf_path)
            dwarf_schema.write_json_file(
                dwarf_schema.symbol_cache_path(cache_root, fingerprint, "g_counter"),
                {
                    "schema_version": dwarf_schema.SCHEMA_VERSION,
                    "elf_fingerprint": fingerprint,
                    "symbol": "g_counter",
                    "address": "0x20000010",
                    "root_type_ref": "type:unsigned int",
                },
            )

            symbol_schema, type_schemas = MODULE.load_symbol_auto_schema_from_cache(
                cache_root=cache_root,
                elf_path=elf_path,
                symbol_name="g_counter",
            )

            self.assertEqual(symbol_schema.symbol, "g_counter")
            self.assertEqual(symbol_schema.address, "0x20000010")
            self.assertEqual(symbol_schema.root_type_ref, "type:unsigned int")
            self.assertEqual(type_schemas, {})

    def test_resolve_symbol_auto_schema_rebuilds_on_cache_miss(self):
        fake_symbol_schema = type(
            "SymbolSchema",
            (),
            {
                "symbol": "g_counter",
                "address": "0x20000020",
                "root_type_ref": "type:unsigned int",
            },
        )()

        with mock.patch.object(MODULE, "load_symbol_auto_schema_from_cache", return_value=None) as load_cache:
            with mock.patch.object(
                MODULE,
                "reflect_symbol_auto_schema",
                return_value=(fake_symbol_schema, {}, "rebuild"),
            ) as reflect:
                symbol_schema, type_schemas, cache_status = MODULE.resolve_symbol_auto_schema(
                    cache_root=Path("/tmp/cache"),
                    elf_path=Path("/tmp/firmware.elf"),
                    symbol_name="g_counter",
                )

        load_cache.assert_called_once()
        reflect.assert_called_once()
        self.assertEqual(symbol_schema.address, "0x20000020")
        self.assertEqual(type_schemas, {})
        self.assertEqual(cache_status, "rebuild")

    def test_resolve_symbol_auto_root_size_uses_schema_size(self):
        type_schemas = {
            "type:Leaf": type("LeafSchema", (), {"size": 44})(),
            "type:Array": type("ArraySchema", (), {"size": 176})(),
        }

        self.assertEqual(MODULE.resolve_symbol_auto_root_size("type:Array", type_schemas), 176)

    def test_build_metadata_prefers_explicit_raw_size_when_no_layout(self):
        args = Namespace(
            device="STM32F427II",
            interface="SWD",
            speed=4000,
            count=1,
            mode="snapshot",
            size=4,
            pointer_symbol=None,
            decode_profile=None,
            symbol="chassis_parameter",
            workflow_mode="symbol_auto",
            follow_depth=0,
            effective_capture_mode="snapshot",
            elf="builds/gcc/debug/RSCF_A.elf",
        )

        metadata = MODULE.build_metadata(
            args=args,
            symbol="chassis_parameter",
            address=0x20014118,
            layout=None,
            interval_ms=1,
            raw_size=388,
        )

        self.assertEqual(metadata["size"], 388)
        self.assertEqual(metadata["follow_depth"], 0)
        self.assertEqual(metadata["capture_mode"], "snapshot")


if __name__ == "__main__":
    unittest.main(verbosity=2)

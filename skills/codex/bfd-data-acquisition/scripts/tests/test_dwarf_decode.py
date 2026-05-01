import importlib.util
import struct
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]

SCHEMA_SPEC = importlib.util.spec_from_file_location("dwarf_schema", SCRIPT_DIR / "dwarf_schema.py")
SCHEMA_MODULE = importlib.util.module_from_spec(SCHEMA_SPEC)
assert SCHEMA_SPEC.loader is not None
sys.modules[SCHEMA_SPEC.name] = SCHEMA_MODULE
SCHEMA_SPEC.loader.exec_module(SCHEMA_MODULE)

DECODE_SPEC = importlib.util.spec_from_file_location("dwarf_decode", SCRIPT_DIR / "dwarf_decode.py")
DECODE_MODULE = importlib.util.module_from_spec(DECODE_SPEC)
assert DECODE_SPEC.loader is not None
sys.modules[DECODE_SPEC.name] = DECODE_MODULE
DECODE_SPEC.loader.exec_module(DECODE_MODULE)


class DwarfDecodeTest(unittest.TestCase):
    def setUp(self):
        self.type_schemas = {
            "type:Inner": SCHEMA_MODULE.StructTypeSchema(
                type_id="type:Inner",
                name="Inner",
                size=8,
                fields=[
                    SCHEMA_MODULE.FieldSchema(name="count", offset=0, type_ref="type:unsigned int"),
                    SCHEMA_MODULE.FieldSchema(name="mode", offset=4, type_ref="type:Mode"),
                ],
            ),
            "type:Outer": SCHEMA_MODULE.StructTypeSchema(
                type_id="type:Outer",
                name="Outer",
                size=16,
                fields=[
                    SCHEMA_MODULE.FieldSchema(name="inner", offset=0, type_ref="type:Inner"),
                    SCHEMA_MODULE.FieldSchema(name="temperature", offset=8, type_ref="type:float"),
                    SCHEMA_MODULE.FieldSchema(name="flag", offset=12, type_ref="type:unsigned char"),
                ],
            ),
            "type:OuterArray": SCHEMA_MODULE.ArrayTypeSchema(
                type_id="type:OuterArray",
                name="OuterArray",
                size=32,
                count=2,
                element_type_ref="type:Outer",
                stride=16,
            ),
            "type:Mode": SCHEMA_MODULE.EnumTypeSchema(
                type_id="type:Mode",
                name="Mode",
                size=4,
                underlying_type="u32",
                values={"MODE_A": 0, "MODE_B": 2},
            ),
            "type:pointer:OuterPtr": SCHEMA_MODULE.PointerTypeSchema(
                type_id="type:pointer:OuterPtr",
                name="OuterPtr",
                size=4,
                pointer_size=4,
                target_type_ref="type:Outer",
            ),
        }

    def test_decode_struct_with_nested_struct_and_enum(self):
        raw = (
            struct.pack("<I", 7)
            + struct.pack("<I", 2)
            + struct.pack("<f", 36.5)
            + struct.pack("<B", 1)
            + b"\x00\x00\x00"
        )

        decoded = DECODE_MODULE.decode_bytes_by_type(raw, "type:Outer", self.type_schemas)

        self.assertEqual(decoded["inner"]["count"], 7)
        self.assertEqual(decoded["inner"]["mode"]["value"], 2)
        self.assertEqual(decoded["inner"]["mode"]["name"], "MODE_B")
        self.assertAlmostEqual(decoded["temperature"], 36.5)
        self.assertEqual(decoded["flag"], 1)

    def test_decode_array_of_structs(self):
        raw = (
            struct.pack("<IIfBxxx", 1, 0, 20.0, 1)
            + struct.pack("<IIfBxxx", 2, 2, 21.5, 0)
        )

        decoded = DECODE_MODULE.decode_bytes_by_type(raw, "type:OuterArray", self.type_schemas)

        self.assertEqual(len(decoded), 2)
        self.assertEqual(decoded[0]["inner"]["count"], 1)
        self.assertEqual(decoded[1]["inner"]["mode"]["name"], "MODE_B")
        self.assertAlmostEqual(decoded[1]["temperature"], 21.5)

    def test_decode_pointer_follow_depth_zero_returns_pointer_metadata_only(self):
        raw = struct.pack("<I", 0x20001000)

        decoded = DECODE_MODULE.decode_bytes_by_type(
            raw,
            "type:pointer:OuterPtr",
            self.type_schemas,
            follow_depth=0,
        )

        self.assertEqual(decoded["pointer_value"], "0x20001000")
        self.assertEqual(decoded["decode_status"], "not_followed")
        self.assertNotIn("pointee", decoded)

    def test_decode_pointer_follow_depth_one_reads_target(self):
        raw = struct.pack("<I", 0x20001000)
        target_raw = (
            struct.pack("<I", 9)
            + struct.pack("<I", 0)
            + struct.pack("<f", 18.25)
            + struct.pack("<B", 1)
            + b"\x00\x00\x00"
        )

        def read_memory(address: int, size: int) -> bytes:
            self.assertEqual(address, 0x20001000)
            self.assertEqual(size, 16)
            return target_raw

        decoded = DECODE_MODULE.decode_bytes_by_type(
            raw,
            "type:pointer:OuterPtr",
            self.type_schemas,
            follow_depth=1,
            read_memory=read_memory,
        )

        self.assertEqual(decoded["decode_status"], "ok")
        self.assertEqual(decoded["pointee"]["inner"]["count"], 9)
        self.assertAlmostEqual(decoded["pointee"]["temperature"], 18.25)

    def test_decode_pointer_rejects_non_sram_target(self):
        raw = struct.pack("<I", 0x08001234)

        decoded = DECODE_MODULE.decode_bytes_by_type(
            raw,
            "type:pointer:OuterPtr",
            self.type_schemas,
            follow_depth=1,
            read_memory=lambda _address, _size: b"",
        )

        self.assertEqual(decoded["decode_status"], "pointer_out_of_sram")

    def test_decode_long_long_unsigned_scalar(self):
        raw = struct.pack("<Q", 0x1122334455667788)

        decoded = DECODE_MODULE.decode_bytes_by_type(raw, "type:long long unsigned int", self.type_schemas)

        self.assertEqual(decoded, 0x1122334455667788)

    def test_decode_truncated_scalar_returns_metadata_instead_of_raising(self):
        decoded = DECODE_MODULE.decode_bytes_by_type(b"\x34", "type:unsigned int", self.type_schemas)

        self.assertEqual(decoded["decode_status"], "truncated")
        self.assertEqual(decoded["type_ref"], "type:unsigned int")
        self.assertEqual(decoded["expected_size"], 4)
        self.assertEqual(decoded["actual_size"], 1)

    def test_decode_truncated_struct_marks_short_field_without_raising(self):
        decoded = DECODE_MODULE.decode_bytes_by_type(b"\x07\x00\x00\x00", "type:Outer", self.type_schemas)

        self.assertEqual(decoded["__decode_status__"], "truncated")
        self.assertEqual(decoded["inner"]["count"], 7)
        self.assertEqual(decoded["inner"]["mode"]["decode_status"], "truncated")
        self.assertEqual(decoded["temperature"]["decode_status"], "truncated")
        self.assertEqual(decoded["flag"]["decode_status"], "truncated")

    def test_flatten_decoded_value_uses_field_paths(self):
        decoded = {
            "inner": {"count": 7, "mode": {"value": 2, "name": "MODE_B"}},
            "temperature": 36.5,
            "flag": 1,
        }

        flattened = DECODE_MODULE.flatten_decoded_value(decoded)

        self.assertEqual(flattened["inner.count"], 7)
        self.assertEqual(flattened["inner.mode.value"], 2)
        self.assertEqual(flattened["inner.mode.name"], "MODE_B")
        self.assertEqual(flattened["temperature"], 36.5)
        self.assertEqual(flattened["flag"], 1)

    def test_build_generic_summary_uses_scalar_paths_without_domain_assumptions(self):
        entries = [
            {
                "__index__": 0,
                "__address__": "0x20001000",
                "__decode_status__": "ok",
                "inner": {"count": 7, "mode": {"value": 2, "name": "MODE_B"}},
                "temperature": 36.5,
            }
        ]

        summary = DECODE_MODULE.build_generic_summary(entries, max_fields=3)

        self.assertIn("[0]", summary)
        self.assertIn("addr=0x20001000", summary)
        self.assertIn("status=ok", summary)
        self.assertIn("inner.count=7", summary)
        self.assertIn("inner.mode.value=2", summary)
        self.assertIn("temperature=36.5", summary)


if __name__ == "__main__":
    unittest.main(verbosity=2)

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "dwarf_schema.py"
SPEC = importlib.util.spec_from_file_location("dwarf_schema", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DwarfSchemaTest(unittest.TestCase):
    def test_struct_schema_serializes_expected_shape(self):
        schema = MODULE.StructTypeSchema(
            type_id="type:Example",
            name="Example",
            size=12,
            fields=[
                MODULE.FieldSchema(name="a", offset=0, type_ref="type:u32"),
                MODULE.FieldSchema(name="b", offset=4, type_ref="type:u16"),
            ],
        )

        self.assertEqual(
            schema.to_dict(),
            {
                "schema_version": MODULE.SCHEMA_VERSION,
                "kind": "struct",
                "type_id": "type:Example",
                "name": "Example",
                "size": 12,
                "fields": [
                    {"name": "a", "offset": 0, "type_ref": "type:u32"},
                    {"name": "b", "offset": 4, "type_ref": "type:u16"},
                ],
            },
        )

    def test_array_schema_serializes_count_stride_and_element_type(self):
        schema = MODULE.ArrayTypeSchema(
            type_id="type:ExampleArray",
            name="ExampleArray",
            size=32,
            count=4,
            element_type_ref="type:Example",
            stride=8,
        )

        self.assertEqual(schema.kind, "array")
        self.assertEqual(schema.to_dict()["count"], 4)
        self.assertEqual(schema.to_dict()["stride"], 8)
        self.assertEqual(schema.to_dict()["element_type_ref"], "type:Example")

    def test_pointer_schema_serializes_target_type(self):
        schema = MODULE.PointerTypeSchema(
            type_id="type:ExamplePtr",
            name="ExamplePtr",
            size=4,
            pointer_size=4,
            target_type_ref="type:Example",
        )

        self.assertEqual(
            schema.to_dict()["target_type_ref"],
            "type:Example",
        )

    def test_enum_schema_serializes_underlying_type_and_values(self):
        schema = MODULE.EnumTypeSchema(
            type_id="type:ExampleEnum",
            name="ExampleEnum",
            size=4,
            underlying_type="u32",
            values={"A": 0, "B": 2},
        )

        self.assertEqual(
            schema.to_dict(),
            {
                "schema_version": MODULE.SCHEMA_VERSION,
                "kind": "enum",
                "type_id": "type:ExampleEnum",
                "name": "ExampleEnum",
                "size": 4,
                "underlying_type": "u32",
                "values": {"A": 0, "B": 2},
            },
        )

    def test_symbol_schema_serializes_root_type_and_address(self):
        schema = MODULE.SymbolSchema(
            elf_fingerprint="abc123",
            symbol="g_example",
            address="0x20000000",
            root_type_ref="type:ExampleArray",
        )

        self.assertEqual(
            schema.to_dict(),
            {
                "schema_version": MODULE.SCHEMA_VERSION,
                "elf_fingerprint": "abc123",
                "symbol": "g_example",
                "address": "0x20000000",
                "root_type_ref": "type:ExampleArray",
            },
        )

    def test_compute_elf_fingerprint_uses_sha256_of_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            elf_path = Path(tmp_dir) / "firmware.elf"
            elf_path.write_bytes(b"ELFTEST")

            self.assertEqual(
                MODULE.compute_elf_fingerprint(elf_path),
                hashlib.sha256(b"ELFTEST").hexdigest(),
            )

    def test_cache_paths_use_fingerprint_and_safe_symbol_name(self):
        cache_root = Path("/tmp/dwarf_cache")

        self.assertEqual(
            MODULE.index_cache_path(cache_root, "fp123"),
            cache_root / "index" / "fp123.json",
        )
        self.assertEqual(
            MODULE.symbol_cache_path(cache_root, "fp123", "__hub_m3508_inst"),
            cache_root / "symbols" / "fp123" / "__hub_m3508_inst.json",
        )
        self.assertEqual(
            MODULE.type_cache_path(cache_root, "fp123", "type:DJIMotorInstance"),
            cache_root / "types" / "fp123" / "type_DJIMotorInstance.json",
        )

    def test_schema_version_mismatch_is_detected(self):
        self.assertTrue(MODULE.is_schema_version_compatible({"schema_version": MODULE.SCHEMA_VERSION}))
        self.assertFalse(MODULE.is_schema_version_compatible({"schema_version": MODULE.SCHEMA_VERSION + 1}))
        self.assertFalse(MODULE.is_schema_version_compatible({}))

    def test_write_json_file_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "types" / "fp123" / "example.json"
            payload = {"schema_version": MODULE.SCHEMA_VERSION, "kind": "struct"}

            MODULE.write_json_file(output_path, payload)

            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)

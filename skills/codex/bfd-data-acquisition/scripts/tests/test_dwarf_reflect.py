import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]

SCHEMA_SPEC = importlib.util.spec_from_file_location("dwarf_schema", SCRIPT_DIR / "dwarf_schema.py")
SCHEMA_MODULE = importlib.util.module_from_spec(SCHEMA_SPEC)
assert SCHEMA_SPEC.loader is not None
sys.modules[SCHEMA_SPEC.name] = SCHEMA_MODULE
SCHEMA_SPEC.loader.exec_module(SCHEMA_MODULE)

REFLECT_SPEC = importlib.util.spec_from_file_location("dwarf_reflect", SCRIPT_DIR / "dwarf_reflect.py")
REFLECT_MODULE = importlib.util.module_from_spec(REFLECT_SPEC)
assert REFLECT_SPEC.loader is not None
sys.modules[REFLECT_SPEC.name] = REFLECT_MODULE
REFLECT_SPEC.loader.exec_module(REFLECT_MODULE)


ELF_PATH = Path("builds/gcc/debug/RSCF_A.elf")


class FakeAttr:
    def __init__(self, value):
        self.value = value


class FakeDie:
    def __init__(self, tag, *, offset=0, attributes=None, children=None, refs=None):
        self.tag = tag
        self.offset = offset
        self.attributes = attributes or {}
        self._children = children or []
        self._refs = refs or {}

    def iter_children(self):
        return iter(self._children)

    def get_DIE_from_attribute(self, name):
        return self._refs[name]


@unittest.skipUnless(ELF_PATH.is_file(), "requires built ELF fixture")
class DwarfReflectTest(unittest.TestCase):
    def test_reflect_symbol_schema_for_hub_m3508_pointer_array(self):
        symbol_schema, type_schemas = REFLECT_MODULE.reflect_symbol_from_elf(
            ELF_PATH,
            "__hub_m3508_inst",
        )

        self.assertEqual(symbol_schema.symbol, "__hub_m3508_inst")
        self.assertIn(symbol_schema.root_type_ref, type_schemas)

        root_schema = type_schemas[symbol_schema.root_type_ref]
        self.assertEqual(root_schema.kind, "array")
        self.assertEqual(root_schema.count, 4)
        self.assertIn(root_schema.element_type_ref, type_schemas)

        pointer_schema = type_schemas[root_schema.element_type_ref]
        self.assertEqual(pointer_schema.kind, "pointer")
        self.assertEqual(pointer_schema.pointer_size, 4)
        self.assertEqual(pointer_schema.target_type_ref, "type:DJIMotorInstance")

    def test_reflect_dji_measure_struct_contains_expected_fields(self):
        _symbol_schema, type_schemas = REFLECT_MODULE.reflect_symbol_from_elf(
            ELF_PATH,
            "__hub_m3508_inst",
        )

        self.assertIn("type:DJI_Motor_Measure_s", type_schemas)
        measure_schema = type_schemas["type:DJI_Motor_Measure_s"]

        field_offsets = {field.name: field.offset for field in measure_schema.fields}
        self.assertEqual(measure_schema.kind, "struct")
        self.assertEqual(measure_schema.size, 28)
        self.assertEqual(field_offsets["last_ecd"], 0)
        self.assertEqual(field_offsets["ecd"], 2)
        self.assertEqual(field_offsets["angle_single_round"], 4)
        self.assertEqual(field_offsets["speed_rpm"], 12)
        self.assertEqual(field_offsets["temperature"], 16)
        self.assertEqual(field_offsets["total_round"], 24)

    def test_unsupported_union_tag_is_rejected(self):
        with self.assertRaises(REFLECT_MODULE.UnsupportedTypeFeatureError):
            REFLECT_MODULE.ensure_supported_type_tag("DW_TAG_union_type")

    def test_emit_symbol_cache_writes_index_symbol_and_types(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_root = Path(tmp_dir)
            symbol_schema, type_schemas = REFLECT_MODULE.reflect_symbol_from_elf(
                ELF_PATH,
                "__hub_m3508_inst",
            )
            fingerprint = SCHEMA_MODULE.compute_elf_fingerprint(ELF_PATH)

            REFLECT_MODULE.emit_symbol_cache(
                cache_root=cache_root,
                elf_path=ELF_PATH,
                symbol_schema=symbol_schema,
                type_schemas=type_schemas,
            )

            self.assertTrue(SCHEMA_MODULE.index_cache_path(cache_root, fingerprint).is_file())
            self.assertTrue(
                SCHEMA_MODULE.symbol_cache_path(cache_root, fingerprint, "__hub_m3508_inst").is_file()
            )
            self.assertTrue(
                SCHEMA_MODULE.type_cache_path(cache_root, fingerprint, "type:DJIMotorInstance").is_file()
            )

    def test_build_array_schema_uses_typedef_target_size_as_stride(self):
        struct_die = FakeDie(
            "DW_TAG_structure_type",
            offset=0x30,
            attributes={
                "DW_AT_name": FakeAttr(b"Wheel_Group_t"),
                "DW_AT_byte_size": FakeAttr(44),
            },
        )
        typedef_die = FakeDie(
            "DW_TAG_typedef",
            offset=0x20,
            attributes={"DW_AT_name": FakeAttr(b"wheel_alias")},
            refs={"DW_AT_type": struct_die},
        )
        subrange_die = FakeDie(
            "DW_TAG_subrange_type",
            offset=0x11,
            attributes={"DW_AT_count": FakeAttr(4)},
        )
        array_die = FakeDie(
            "DW_TAG_array_type",
            offset=0x10,
            refs={"DW_AT_type": typedef_die},
            children=[subrange_die],
        )

        context = REFLECT_MODULE.ReflectContext(type_schemas={})
        schema = REFLECT_MODULE.build_array_schema(array_die, context, preferred_name=None)

        self.assertEqual(schema.element_type_ref, "type:wheel_alias")
        self.assertEqual(schema.count, 4)
        self.assertEqual(schema.stride, 44)
        self.assertEqual(schema.size, 176)


if __name__ == "__main__":
    unittest.main(verbosity=2)

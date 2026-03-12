#!/usr/bin/env python3
"""
DWARF reflection helpers for symbol-driven schema generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Tuple

from elftools.elf.elffile import ELFFile

from dwarf_schema import (
    ArrayTypeSchema,
    EnumTypeSchema,
    FieldSchema,
    PointerTypeSchema,
    StructTypeSchema,
    SymbolSchema,
    compute_elf_fingerprint,
    index_cache_path,
    symbol_cache_path,
    type_cache_path,
    write_json_file,
)


SUPPORTED_TYPE_TAGS = {
    "DW_TAG_typedef",
    "DW_TAG_structure_type",
    "DW_TAG_array_type",
    "DW_TAG_pointer_type",
    "DW_TAG_enumeration_type",
    "DW_TAG_base_type",
    "DW_TAG_const_type",
    "DW_TAG_volatile_type",
    "DW_TAG_restrict_type",
}


class DwarfReflectError(RuntimeError):
    pass


class UnsupportedTypeFeatureError(DwarfReflectError):
    pass


@dataclass
class ReflectContext:
    type_schemas: Dict[str, object]


def decode_die_name(die) -> str:
    name_attr = die.attributes.get("DW_AT_name")
    if not name_attr:
        return ""
    value = name_attr.value
    return value.decode(errors="ignore") if isinstance(value, bytes) else str(value)


def ensure_supported_type_tag(tag: str) -> None:
    if tag in SUPPORTED_TYPE_TAGS:
        return

    if tag in {"DW_TAG_union_type", "DW_TAG_subroutine_type", "DW_TAG_ptr_to_member_type"}:
        raise UnsupportedTypeFeatureError(f"unsupported DWARF type feature: {tag}")
    raise UnsupportedTypeFeatureError(f"unsupported DWARF type tag: {tag}")


def unsupported_type_ref(die) -> str:
    return f"unsupported:{die.tag}:{die.offset}"


def load_elf(elf_path: Path) -> ELFFile:
    return ELFFile(BytesIO(Path(elf_path).read_bytes()))


def find_symbol_address(elffile: ELFFile, symbol_name: str) -> int:
    symtab = elffile.get_section_by_name(".symtab")
    if symtab is None:
        raise DwarfReflectError("ELF has no .symtab section")

    symbols = symtab.get_symbol_by_name(symbol_name)
    if not symbols:
        raise DwarfReflectError(f"symbol not found in ELF symbol table: {symbol_name}")
    return int(symbols[0]["st_value"])


def find_variable_die(dwarf_info, symbol_name: str):
    for cu in dwarf_info.iter_CUs():
        for die in cu.iter_DIEs():
            if die.tag != "DW_TAG_variable":
                continue
            if decode_die_name(die) == symbol_name:
                return die
    raise DwarfReflectError(f"symbol not found in DWARF variable entries: {symbol_name}")


def unwrap_qualifiers(die):
    current = die
    while current.tag in {"DW_TAG_const_type", "DW_TAG_volatile_type", "DW_TAG_restrict_type"}:
        if "DW_AT_type" not in current.attributes:
            raise DwarfReflectError(f"qualified type without DW_AT_type at DIE offset {current.offset}")
        current = current.get_DIE_from_attribute("DW_AT_type")
    return current


def make_type_id(kind: str, name: str) -> str:
    return f"type:{kind}:{name}" if kind else f"type:{name}"


def byte_size_of_die(die, default: int = 4) -> int:
    size_attr = unwrap_qualifiers(die).attributes.get("DW_AT_byte_size")
    if size_attr is None:
        return default
    return int(size_attr.value)


def reflect_symbol_from_elf(elf_path: Path, symbol_name: str) -> Tuple[SymbolSchema, Dict[str, object]]:
    elffile = load_elf(elf_path)
    if not elffile.has_dwarf_info():
        raise DwarfReflectError(f"ELF has no DWARF info: {elf_path}")

    dwarf_info = elffile.get_dwarf_info()
    symbol_die = find_variable_die(dwarf_info, symbol_name)
    symbol_address = find_symbol_address(elffile, symbol_name)

    if "DW_AT_type" not in symbol_die.attributes:
        raise DwarfReflectError(f"DWARF variable has no type: {symbol_name}")

    context = ReflectContext(type_schemas={})
    root_type_die = symbol_die.get_DIE_from_attribute("DW_AT_type")
    root_type_ref = reflect_type_die(root_type_die, context, preferred_name=None, allow_unsupported=False)

    symbol_schema = SymbolSchema(
        elf_fingerprint=compute_elf_fingerprint(Path(elf_path)),
        symbol=symbol_name,
        address=f"0x{symbol_address:08X}",
        root_type_ref=root_type_ref,
    )
    return symbol_schema, context.type_schemas


def reflect_type_die(die, context: ReflectContext, preferred_name: Optional[str], allow_unsupported: bool = True) -> str:
    current = unwrap_qualifiers(die)
    try:
        ensure_supported_type_tag(current.tag)
    except UnsupportedTypeFeatureError:
        if allow_unsupported:
            return unsupported_type_ref(current)
        raise

    if current.tag == "DW_TAG_typedef":
        alias_name = decode_die_name(current)
        if "DW_AT_type" not in current.attributes:
            raise DwarfReflectError(f"typedef has no underlying type: {alias_name or current.offset}")
        return reflect_type_die(
            current.get_DIE_from_attribute("DW_AT_type"),
            context,
            preferred_name=alias_name,
            allow_unsupported=allow_unsupported,
        )

    if current.tag == "DW_TAG_base_type":
        name = decode_die_name(current) or f"base_{current.offset}"
        return make_type_id("", name)

    if current.tag == "DW_TAG_structure_type":
        schema = build_struct_schema(current, context, preferred_name)
        context.type_schemas.setdefault(schema.type_id, schema)
        return schema.type_id

    if current.tag == "DW_TAG_pointer_type":
        schema = build_pointer_schema(current, context, preferred_name)
        context.type_schemas.setdefault(schema.type_id, schema)
        return schema.type_id

    if current.tag == "DW_TAG_array_type":
        schema = build_array_schema(current, context, preferred_name)
        context.type_schemas.setdefault(schema.type_id, schema)
        return schema.type_id

    if current.tag == "DW_TAG_enumeration_type":
        schema = build_enum_schema(current, preferred_name)
        context.type_schemas.setdefault(schema.type_id, schema)
        return schema.type_id

    raise UnsupportedTypeFeatureError(f"unsupported type tag in reflector: {current.tag}")


def build_struct_schema(die, context: ReflectContext, preferred_name: Optional[str]) -> StructTypeSchema:
    struct_name = preferred_name or decode_die_name(die) or f"anon_struct_{die.offset}"
    size_attr = die.attributes.get("DW_AT_byte_size")
    if size_attr is None:
        raise DwarfReflectError(f"struct has no byte size: {struct_name}")

    fields = []
    for child in die.iter_children():
        if child.tag != "DW_TAG_member":
            continue
        field_name = decode_die_name(child)
        if not field_name:
            raise UnsupportedTypeFeatureError(f"anonymous struct member is unsupported at {child.offset}")
        location_attr = child.attributes.get("DW_AT_data_member_location")
        if location_attr is None or not isinstance(location_attr.value, int):
            raise UnsupportedTypeFeatureError(f"unsupported member location for {field_name}")
        field_type_die = child.get_DIE_from_attribute("DW_AT_type")
        field_type_ref = reflect_type_die(field_type_die, context, preferred_name=None, allow_unsupported=True)
        fields.append(FieldSchema(name=field_name, offset=int(location_attr.value), type_ref=field_type_ref))

    return StructTypeSchema(
        type_id=make_type_id("", struct_name),
        name=struct_name,
        size=int(size_attr.value),
        fields=fields,
    )


def build_pointer_schema(die, context: ReflectContext, preferred_name: Optional[str]) -> PointerTypeSchema:
    size_attr = die.attributes.get("DW_AT_byte_size")
    pointer_size = int(size_attr.value) if size_attr is not None else 4
    if "DW_AT_type" not in die.attributes:
        target_type_ref = "type:void"
    else:
        target_type_ref = reflect_type_die(
            die.get_DIE_from_attribute("DW_AT_type"),
            context,
            preferred_name=None,
            allow_unsupported=True,
        )

    pointer_name = preferred_name or f"ptr_to_{target_type_ref.replace(':', '_')}"
    return PointerTypeSchema(
        type_id=make_type_id("pointer", pointer_name),
        name=pointer_name,
        size=pointer_size,
        pointer_size=pointer_size,
        target_type_ref=target_type_ref,
    )


def resolve_array_count(die) -> int:
    for child in die.iter_children():
        if child.tag != "DW_TAG_subrange_type":
            continue
        if "DW_AT_count" in child.attributes:
            return int(child.attributes["DW_AT_count"].value)
        if "DW_AT_upper_bound" in child.attributes:
            return int(child.attributes["DW_AT_upper_bound"].value) + 1
    raise DwarfReflectError(f"array has no count/subrange information at DIE offset {die.offset}")


def build_array_schema(die, context: ReflectContext, preferred_name: Optional[str]) -> ArrayTypeSchema:
    if "DW_AT_type" not in die.attributes:
        raise DwarfReflectError(f"array type missing element type at DIE offset {die.offset}")

    element_type_die = die.get_DIE_from_attribute("DW_AT_type")
    element_type_ref = reflect_type_die(element_type_die, context, preferred_name=None, allow_unsupported=True)
    count = resolve_array_count(die)
    stride = byte_size_of_die(element_type_die, default=4)
    array_name = preferred_name or f"{element_type_ref.replace(':', '_')}[{count}]"
    return ArrayTypeSchema(
        type_id=make_type_id("array", array_name),
        name=array_name,
        size=count * stride,
        count=count,
        element_type_ref=element_type_ref,
        stride=stride,
    )


def build_enum_schema(die, preferred_name: Optional[str]) -> EnumTypeSchema:
    enum_name = preferred_name or decode_die_name(die) or f"anon_enum_{die.offset}"
    size_attr = die.attributes.get("DW_AT_byte_size")
    enum_values: Dict[str, int] = {}
    for child in die.iter_children():
        if child.tag != "DW_TAG_enumerator":
            continue
        enum_values[decode_die_name(child)] = int(child.attributes["DW_AT_const_value"].value)

    return EnumTypeSchema(
        type_id=make_type_id("", enum_name),
        name=enum_name,
        size=int(size_attr.value) if size_attr is not None else 4,
        underlying_type=f"u{(int(size_attr.value) if size_attr is not None else 4) * 8}",
        values=enum_values,
    )


def emit_symbol_cache(cache_root: Path, elf_path: Path, symbol_schema: SymbolSchema, type_schemas: Dict[str, object]) -> None:
    fingerprint = compute_elf_fingerprint(Path(elf_path))
    write_json_file(
        index_cache_path(cache_root, fingerprint),
        {
            "schema_version": 1,
            "elf_fingerprint": fingerprint,
            "elf_path": str(Path(elf_path)),
            "symbols": [symbol_schema.symbol],
            "type_count": len(type_schemas),
        },
    )
    write_json_file(
        symbol_cache_path(cache_root, fingerprint, symbol_schema.symbol),
        symbol_schema.to_dict(),
    )
    for type_id, schema in type_schemas.items():
        write_json_file(
            type_cache_path(cache_root, fingerprint, type_id),
            schema.to_dict(),
        )

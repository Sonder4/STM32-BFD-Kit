#!/usr/bin/env python3
"""
Schema-driven memory decode helpers for DWARF-reflected types.
"""

from __future__ import annotations

import struct
from typing import Any, Callable, Dict, Mapping, Optional


SRAM_ADDRESS_RANGES = (
    (0x20000000, 0x20040000),
    (0x10000000, 0x10010000),
)


ScalarReader = Callable[[bytes], Any]


SCALAR_READERS: Dict[str, tuple[int, ScalarReader]] = {
    "type:unsigned char": (1, lambda data: struct.unpack("<B", data)[0]),
    "type:char": (1, lambda data: struct.unpack("<b", data)[0]),
    "type:signed char": (1, lambda data: struct.unpack("<b", data)[0]),
    "type:_Bool": (1, lambda data: bool(struct.unpack("<B", data)[0])),
    "type:short unsigned int": (2, lambda data: struct.unpack("<H", data)[0]),
    "type:short int": (2, lambda data: struct.unpack("<h", data)[0]),
    "type:unsigned int": (4, lambda data: struct.unpack("<I", data)[0]),
    "type:int": (4, lambda data: struct.unpack("<i", data)[0]),
    "type:long unsigned int": (4, lambda data: struct.unpack("<I", data)[0]),
    "type:long int": (4, lambda data: struct.unpack("<i", data)[0]),
    "type:long long unsigned int": (8, lambda data: struct.unpack("<Q", data)[0]),
    "type:long long int": (8, lambda data: struct.unpack("<q", data)[0]),
    "type:float": (4, lambda data: struct.unpack("<f", data)[0]),
    "type:double": (8, lambda data: struct.unpack("<d", data)[0]),
    "type:void": (0, lambda _data: None),
}


def is_valid_sram_pointer(address: int) -> bool:
    return any(start <= address < end for start, end in SRAM_ADDRESS_RANGES)


def format_hex32(value: int) -> str:
    return f"0x{value & 0xFFFFFFFF:08X}"


def type_byte_size(type_ref: str, type_schemas: Mapping[str, Any]) -> int:
    if type_ref.startswith("unsupported:"):
        return 0
    if type_ref in SCALAR_READERS:
        return SCALAR_READERS[type_ref][0]
    schema = type_schemas[type_ref]
    return int(schema.size)


def decode_bytes_by_type(
    raw: bytes,
    type_ref: str,
    type_schemas: Mapping[str, Any],
    *,
    follow_depth: int = 0,
    read_memory: Optional[Callable[[int, int], bytes]] = None,
) -> Any:
    if type_ref.startswith("unsupported:"):
        return {"unsupported_type": type_ref}

    if type_ref in SCALAR_READERS:
        size, reader = SCALAR_READERS[type_ref]
        return reader(raw[:size])

    schema = type_schemas[type_ref]

    if schema.kind == "struct":
        decoded: Dict[str, Any] = {}
        for field in schema.fields:
            field_size = type_byte_size(field.type_ref, type_schemas)
            field_raw = raw[field.offset : field.offset + field_size]
            decoded[field.name] = decode_bytes_by_type(
                field_raw,
                field.type_ref,
                type_schemas,
                follow_depth=follow_depth,
                read_memory=read_memory,
            )
        return decoded

    if schema.kind == "array":
        values = []
        for index in range(schema.count):
            start = index * schema.stride
            end = start + schema.stride
            values.append(
                decode_bytes_by_type(
                    raw[start:end],
                    schema.element_type_ref,
                    type_schemas,
                    follow_depth=follow_depth,
                    read_memory=read_memory,
                )
            )
        return values

    if schema.kind == "enum":
        scalar_type_ref = {
            "u8": "type:unsigned char",
            "u16": "type:short unsigned int",
            "u32": "type:unsigned int",
            "s8": "type:char",
            "s16": "type:short int",
            "s32": "type:int",
        }.get(schema.underlying_type, "type:unsigned int")
        value = decode_bytes_by_type(raw, scalar_type_ref, type_schemas)
        name = None
        for enum_name, enum_value in schema.values.items():
            if enum_value == value:
                name = enum_name
                break
        return {"value": value, "name": name}

    if schema.kind == "pointer":
        pointer_value = struct.unpack("<I", raw[: schema.pointer_size])[0]
        decoded = {
            "pointer_value": format_hex32(pointer_value),
            "is_null": pointer_value == 0,
            "is_sram_pointer": is_valid_sram_pointer(pointer_value),
        }
        if pointer_value == 0:
            decoded["decode_status"] = "null_pointer"
            return decoded
        if not is_valid_sram_pointer(pointer_value):
            decoded["decode_status"] = "pointer_out_of_sram"
            return decoded
        if follow_depth <= 0:
            decoded["decode_status"] = "not_followed"
            return decoded
        if read_memory is None:
            decoded["decode_status"] = "no_memory_reader"
            return decoded

        target_size = type_byte_size(schema.target_type_ref, type_schemas)
        target_raw = read_memory(pointer_value, target_size)
        decoded["decode_status"] = "ok"
        decoded["pointee"] = decode_bytes_by_type(
            target_raw,
            schema.target_type_ref,
            type_schemas,
            follow_depth=follow_depth - 1,
            read_memory=read_memory,
        )
        return decoded

    raise ValueError(f"unsupported schema kind: {schema.kind}")


def flatten_decoded_value(value: Any, prefix: str = "") -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}

    if isinstance(value, dict):
        for key, item in value.items():
            if key.startswith("__"):
                continue
            path = f"{prefix}.{key}" if prefix else key
            flattened.update(flatten_decoded_value(item, path))
        if not value:
            flattened[prefix] = {}
        return flattened

    if isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            flattened.update(flatten_decoded_value(item, path))
        if not value and prefix:
            flattened[prefix] = []
        return flattened

    if prefix:
        flattened[prefix] = value
    return flattened


def build_generic_summary(entries: list[dict[str, Any]], max_fields: int = 4) -> str:
    lines = [f"entries: {len(entries)}"]
    for index, entry in enumerate(entries):
        parts = [f"[{entry.get('__index__', index)}]"]
        if "__address__" in entry:
            parts.append(f"addr={entry['__address__']}")
        if "__decode_status__" in entry:
            parts.append(f"status={entry['__decode_status__']}")
        flattened = flatten_decoded_value(entry)
        scalar_items = [(key, value) for key, value in flattened.items() if not isinstance(value, (dict, list))]
        scalar_items.sort(key=lambda item: (isinstance(item[1], str), item[0].endswith(".name"), item[0]))
        for key, value in scalar_items[:max_fields]:
            parts.append(f"{key}={value}")
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"

#!/usr/bin/env python3
"""
Canonical schema model and cache helpers for DWARF-driven data acquisition.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


SCHEMA_VERSION = 1


def sanitize_cache_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


@dataclass(frozen=True)
class FieldSchema:
    name: str
    offset: int
    type_ref: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "offset": self.offset,
            "type_ref": self.type_ref,
        }


@dataclass(frozen=True)
class StructTypeSchema:
    type_id: str
    name: str
    size: int
    fields: List[FieldSchema]
    kind: str = "struct"

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": self.kind,
            "type_id": self.type_id,
            "name": self.name,
            "size": self.size,
            "fields": [field.to_dict() for field in self.fields],
        }


@dataclass(frozen=True)
class ArrayTypeSchema:
    type_id: str
    name: str
    size: int
    count: int
    element_type_ref: str
    stride: int
    kind: str = "array"

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": self.kind,
            "type_id": self.type_id,
            "name": self.name,
            "size": self.size,
            "count": self.count,
            "element_type_ref": self.element_type_ref,
            "stride": self.stride,
        }


@dataclass(frozen=True)
class PointerTypeSchema:
    type_id: str
    name: str
    size: int
    pointer_size: int
    target_type_ref: str
    kind: str = "pointer"

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": self.kind,
            "type_id": self.type_id,
            "name": self.name,
            "size": self.size,
            "pointer_size": self.pointer_size,
            "target_type_ref": self.target_type_ref,
        }


@dataclass(frozen=True)
class EnumTypeSchema:
    type_id: str
    name: str
    size: int
    underlying_type: str
    values: Dict[str, int]
    kind: str = "enum"

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": self.kind,
            "type_id": self.type_id,
            "name": self.name,
            "size": self.size,
            "underlying_type": self.underlying_type,
            "values": dict(self.values),
        }


@dataclass(frozen=True)
class SymbolSchema:
    elf_fingerprint: str
    symbol: str
    address: str
    root_type_ref: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "elf_fingerprint": self.elf_fingerprint,
            "symbol": self.symbol,
            "address": self.address,
            "root_type_ref": self.root_type_ref,
        }


def compute_elf_fingerprint(elf_path: Path) -> str:
    digest = hashlib.sha256()
    with Path(elf_path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_cache_path(cache_root: Path, elf_fingerprint: str) -> Path:
    return Path(cache_root) / "index" / f"{sanitize_cache_name(elf_fingerprint)}.json"


def symbol_cache_path(cache_root: Path, elf_fingerprint: str, symbol: str) -> Path:
    return Path(cache_root) / "symbols" / sanitize_cache_name(elf_fingerprint) / f"{sanitize_cache_name(symbol)}.json"


def type_cache_path(cache_root: Path, elf_fingerprint: str, type_id: str) -> Path:
    return Path(cache_root) / "types" / sanitize_cache_name(elf_fingerprint) / f"{sanitize_cache_name(type_id)}.json"


def is_schema_version_compatible(payload: Dict[str, object]) -> bool:
    return payload.get("schema_version") == SCHEMA_VERSION


def write_json_file(output_path: Path, payload: Dict[str, object]) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

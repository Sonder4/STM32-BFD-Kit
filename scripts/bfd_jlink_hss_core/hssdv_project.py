"""Shared parsing for Windows HSS_DataVisualizer project files."""

from __future__ import annotations

import configparser
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Optional


HSSDV_SECTION_PATTERN = re.compile(r"^VarInfo\d+$")
TYPE_DESC_INT_PATTERN = re.compile(r"(u?int)(8|16|32|64)_t", re.IGNORECASE)
SCALAR_TYPE_INFO = {
    "u8": {"byte_size": 1, "type_name": "uint8_t", "display": "uint8_t", "type_id": 0},
    "i8": {"byte_size": 1, "type_name": "int8_t", "display": "int8_t", "type_id": 0},
    "u16": {"byte_size": 2, "type_name": "uint16_t", "display": "uint16_t", "type_id": 0},
    "i16": {"byte_size": 2, "type_name": "int16_t", "display": "int16_t", "type_id": 0},
    "u32": {"byte_size": 4, "type_name": "uint32_t", "display": "uint32_t", "type_id": 0},
    "i32": {"byte_size": 4, "type_name": "int32_t", "display": "int32_t", "type_id": 0},
    "u64": {"byte_size": 8, "type_name": "uint64_t", "display": "uint64_t", "type_id": 0},
    "i64": {"byte_size": 8, "type_name": "int64_t", "display": "int64_t", "type_id": 0},
    "f32": {"byte_size": 4, "type_name": "float", "display": "float", "type_id": 1},
    "f64": {"byte_size": 8, "type_name": "double", "display": "double", "type_id": 1},
    "bool": {"byte_size": 1, "type_name": "bool", "display": "bool", "type_id": 0},
}
SCALAR_TYPE_ALIASES = {
    "u8": "u8",
    "uint8_t": "u8",
    "unsigned8": "u8",
    "i8": "i8",
    "int8_t": "i8",
    "s8": "i8",
    "u16": "u16",
    "uint16_t": "u16",
    "unsigned16": "u16",
    "i16": "i16",
    "int16_t": "i16",
    "s16": "i16",
    "u32": "u32",
    "uint32_t": "u32",
    "unsigned32": "u32",
    "i32": "i32",
    "int32_t": "i32",
    "s32": "i32",
    "u64": "u64",
    "uint64_t": "u64",
    "i64": "i64",
    "int64_t": "i64",
    "s64": "i64",
    "f32": "f32",
    "float": "f32",
    "f64": "f64",
    "double": "f64",
    "bool": "bool",
}
HSSDV_TYPE_MAP = {
    (0, 1): "u8",
    (0, 2): "u16",
    (0, 4): "u32",
    (0, 8): "u64",
    (1, 1): "i8",
    (2, 2): "i16",
    (3, 4): "i32",
    (4, 4): "f32",
    (4, 8): "f64",
}
JLINK_TARGET_IF_MAP = {
    0: "JTAG",
    1: "SWD",
}
JLINK_HOST_IF_MAP = {
    0: "USB",
    1: "IP",
}


class HssdvProjectError(RuntimeError):
    """Raised when a DataVisualizer HSSDV project file is invalid."""


@dataclass
class FixedScalarCaptureSpec:
    expression: str
    root_symbol: str
    leaf_name: str
    final_type_tag: str
    final_type_name: str | None
    final_type_display: str
    type_id: int
    offset: int
    root_address: int
    final_address: int
    byte_size: int
    source_file: str | None
    source_kind: str
    alias: str | None = None
    formula: str | None = None
    project_section: str | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["root_address_hex"] = f"0x{self.root_address:08X}"
        payload["final_address_hex"] = f"0x{self.final_address:08X}"
        return payload


@dataclass
class HssdvProjectSettings:
    symbol_file: str | None
    device: str | None
    target_interface: str | None
    speed_khz: int | None
    period_us: int | None
    usb_sn: str | None
    host_interface: str | None
    host_address: str | None
    ip_port: int | None
    settings_file: str | None
    script_file: str | None
    debugger_type: int | None
    xlink_probe: int | None
    xlink_chip: int | None
    xlink_target_if_raw: int | None
    xlink_speed_khz: int | None
    xlink_sample_rate_hz: int | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HssdvProject:
    project_file: str
    settings: HssdvProjectSettings
    enabled_specs: list[FixedScalarCaptureSpec]
    all_specs: list[FixedScalarCaptureSpec]

    def to_dict(self) -> dict:
        return {
            "project_file": self.project_file,
            "settings": self.settings.to_dict(),
            "enabled_specs": [spec.to_dict() for spec in self.enabled_specs],
            "all_specs": [spec.to_dict() for spec in self.all_specs],
        }


def normalize_scalar_type(type_name: str) -> str:
    normalized = SCALAR_TYPE_ALIASES.get(type_name.strip().lower())
    if normalized is None:
        raise HssdvProjectError(f"unsupported scalar type: {type_name}")
    return normalized


def build_fixed_scalar_capture_spec(
    *,
    expression: str,
    address: int,
    scalar_type: str,
    source_kind: str,
    alias: str | None = None,
    formula: str | None = None,
    project_section: str | None = None,
    source_file: str | None = None,
) -> FixedScalarCaptureSpec:
    type_key = normalize_scalar_type(scalar_type)
    info = SCALAR_TYPE_INFO[type_key]
    cleaned_expression = expression.strip()
    if not cleaned_expression:
        cleaned_expression = f"addr_0x{int(address):08X}"
    return FixedScalarCaptureSpec(
        expression=cleaned_expression,
        root_symbol=cleaned_expression,
        leaf_name=cleaned_expression,
        final_type_tag="DW_TAG_base_type",
        final_type_name=info["type_name"],
        final_type_display=info["display"],
        type_id=info["type_id"],
        offset=0,
        root_address=int(address),
        final_address=int(address),
        byte_size=info["byte_size"],
        source_file=source_file,
        source_kind=source_kind,
        alias=alias,
        formula=formula,
        project_section=project_section,
    )


def infer_hssdv_scalar_type(type_value: int, size: int, type_desc: str | None) -> str:
    mapped = HSSDV_TYPE_MAP.get((int(type_value), int(size)))
    if mapped is not None:
        return mapped
    if type_desc:
        normalized = type_desc.lower()
        if "float" in normalized and size == 4:
            return "f32"
        if "double" in normalized and size == 8:
            return "f64"
        if "bool" in normalized and size == 1:
            return "bool"
        type_match = TYPE_DESC_INT_PATTERN.search(normalized)
        if type_match:
            prefix = "u" if type_match.group(1).lower().startswith("u") else "i"
            return f"{prefix}{type_match.group(2)}"
        if "unsigned" in normalized:
            return f"u{size * 8}"
    if int(type_value) == 0:
        return f"u{int(size) * 8}"
    raise HssdvProjectError(
        f"unsupported HSSDV variable type mapping: Type={type_value}, Size={size}, TypeDesc={type_desc}"
    )


def parse_ini_bool(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(raw: str | None) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    return int(text, 0)


def _optional_text(raw: str | None) -> str | None:
    text = str(raw or "").strip()
    return text or None


def _load_project_parser(project_path: str | Path) -> tuple[Path, configparser.ConfigParser]:
    project = Path(project_path).expanduser().resolve()
    if not project.is_file():
        raise HssdvProjectError(f"HSSDV project file not found: {project}")
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(project, encoding="utf-8")
    return project, parser


def _parse_project_specs(
    parser: configparser.ConfigParser,
    project: Path,
) -> tuple[list[FixedScalarCaptureSpec], list[FixedScalarCaptureSpec]]:
    enabled_specs: list[FixedScalarCaptureSpec] = []
    all_specs: list[FixedScalarCaptureSpec] = []
    for section_name in parser.sections():
        if not HSSDV_SECTION_PATTERN.match(section_name):
            continue
        section = parser[section_name]

        expression = (section.get("VarName") or "").strip()
        if not expression:
            raise HssdvProjectError(f"HSSDV section missing VarName: {section_name}")
        if "Address" not in section:
            raise HssdvProjectError(f"HSSDV section missing Address: {section_name}")
        if "Size" not in section:
            raise HssdvProjectError(f"HSSDV section missing Size: {section_name}")
        if "Type" not in section:
            raise HssdvProjectError(f"HSSDV section missing Type: {section_name}")

        address = int(section.get("Address", "0"), 0)
        size = int(section.get("Size", "0"), 0)
        type_value = int(section.get("Type", "0"), 0)
        scalar_type = infer_hssdv_scalar_type(type_value, size, section.get("TypeDesc"))
        spec = build_fixed_scalar_capture_spec(
            expression=expression,
            address=address,
            scalar_type=scalar_type,
            source_kind="hssdv-project",
            alias=(section.get("VarAlias") or "").strip() or None,
            formula=(section.get("Formula") or "").strip() or None,
            project_section=section_name,
            source_file=str(project),
        )
        if spec.byte_size != size:
            raise HssdvProjectError(
                f"HSSDV size/type mismatch for {expression}: Type={type_value}, declared Size={size}, inferred Size={spec.byte_size}"
            )
        all_specs.append(spec)
        if parse_ini_bool(section.get("isEnableSmpl")):
            enabled_specs.append(spec)
    return enabled_specs, all_specs


def _parse_project_settings(parser: configparser.ConfigParser) -> HssdvProjectSettings:
    misc = parser["MiscSettings"] if parser.has_section("MiscSettings") else {}
    jlink = parser["JLinkSettings"] if parser.has_section("JLinkSettings") else {}
    xlink = parser["xLinkSettings"] if parser.has_section("xLinkSettings") else {}

    jlink_target_if_raw = _optional_int(jlink.get("TargetIF"))
    host_if_raw = _optional_int(jlink.get("HostIF"))
    speed_khz = _optional_int(jlink.get("Speed"))
    period_us = _optional_int(jlink.get("HSS_Period_us"))
    xlink_sample_rate_hz = _optional_int(xlink.get("SmplRate"))
    if period_us is None and xlink_sample_rate_hz and xlink_sample_rate_hz > 0:
        period_us = int(round(1_000_000.0 / float(xlink_sample_rate_hz)))

    return HssdvProjectSettings(
        symbol_file=_optional_text(misc.get("SymbolFile")),
        device=_optional_text(jlink.get("sDevice")),
        target_interface=JLINK_TARGET_IF_MAP.get(jlink_target_if_raw) if jlink_target_if_raw is not None else None,
        speed_khz=speed_khz,
        period_us=period_us,
        usb_sn=_optional_text(jlink.get("SerialNo")),
        host_interface=JLINK_HOST_IF_MAP.get(host_if_raw) if host_if_raw is not None else None,
        host_address=_optional_text(jlink.get("sHost")),
        ip_port=_optional_int(jlink.get("IpPort")),
        settings_file=_optional_text(jlink.get("sSettingsFile")),
        script_file=_optional_text(jlink.get("sScriptFile")),
        debugger_type=_optional_int(jlink.get("DebuggerType")),
        xlink_probe=_optional_int(xlink.get("Probe")),
        xlink_chip=_optional_int(xlink.get("Chip")),
        xlink_target_if_raw=_optional_int(xlink.get("TargetIF")),
        xlink_speed_khz=_optional_int(xlink.get("Speed")),
        xlink_sample_rate_hz=xlink_sample_rate_hz,
    )


def load_hssdv_project(project_path: str | Path) -> HssdvProject:
    project, parser = _load_project_parser(project_path)
    enabled_specs, all_specs = _parse_project_specs(parser, project)
    settings = _parse_project_settings(parser)
    return HssdvProject(
        project_file=str(project),
        settings=settings,
        enabled_specs=enabled_specs,
        all_specs=all_specs,
    )


def load_hssdv_project_specs(
    project_path: str | Path,
    *,
    include_disabled: bool = False,
) -> list[FixedScalarCaptureSpec]:
    project = load_hssdv_project(project_path)
    return project.all_specs if include_disabled else project.enabled_specs

#!/usr/bin/env python3
"""STM32 project bootstrap for F4/H7 profile-driven skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = "1.0.0"
FINGERPRINT_VERSION = "1"
DEFAULT_PROFILE_DIR = ".codex/bfd"
LEGACY_PROFILE_DIR = ".codex/stm32/bootstrap"
DEFAULT_PROFILE_JSON = f"{DEFAULT_PROFILE_DIR}/active_profile.json"
DEFAULT_PROFILE_ENV = f"{DEFAULT_PROFILE_DIR}/active_profile.env"
DEFAULT_REPORT = f"{DEFAULT_PROFILE_DIR}/bootstrap_report.md"
DEFAULT_IOC_JSON_DIR = f"{DEFAULT_PROFILE_DIR}/ioc_json"
DEFAULT_PROFILE_OVERRIDES_ENV = f"{DEFAULT_PROFILE_DIR}/profile_overrides.env"
LEGACY_PROFILE_JSON = f"{LEGACY_PROFILE_DIR}/active_profile.json"
LEGACY_PROFILE_ENV = f"{LEGACY_PROFILE_DIR}/active_profile.env"
LEGACY_REPORT = f"{LEGACY_PROFILE_DIR}/bootstrap_report.md"

SKIP_SCAN_DIRS = {
    ".git",
    ".codex/stm32/templates",
    ".codex/bfd",
    ".codex/debug",
    ".claude",
    "logs",
    "archive",
    "skills_packages",
    "BFD-Kit",
    "build",
    "builds",
    "build_ac6",
    "build_gcc",
    "build_armclang",
}

FAMILY_KEY_MAP = {
    "STM32F4": "f4",
    "STM32H7": "h7",
}

RTT_SCAN_WINDOW = {
    "STM32F4": "0x20000000:0x00030000",
    "STM32H7": "0x24000000:0x00080000",
}


@dataclass
class ScanResult:
    ioc: Optional[Path]
    project_name: str
    mcu_family: str
    mcu_name: str
    mcu_user_name: str
    startup: Optional[Path]
    linker: Optional[Path]
    svd: Optional[Path]
    cfg: Optional[Path]
    elf: Optional[Path]
    hex_file: Optional[Path]
    map_file: Optional[Path]
    jlink_flash: Optional[Path]
    jlink_debug: Optional[Path]
    jlink_rtt: Optional[Path]


def info(msg: str) -> None:
    print(f"[INFO] {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


def is_ignored(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        return False
    rel_str = str(rel)
    for item in SKIP_SCAN_DIRS:
        if rel_str == item or rel_str.startswith(item + os.sep):
            return True
    return False


def read_ioc_kv(ioc_path: Path) -> Dict[str, str]:
    config: Dict[str, str] = {}
    try:
        text = ioc_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        warn(f"failed to read ioc: {ioc_path} ({exc})")
        return config

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        config[k.strip()] = v.strip()
    return config


def normalize_family(mcu_family_raw: str, mcu_name_raw: str) -> str:
    text = f"{mcu_family_raw} {mcu_name_raw}".upper()
    if "STM32F4" in text:
        return "STM32F4"
    if "STM32H7" in text:
        return "STM32H7"
    return "UNKNOWN"


def normalize_device(user_name: str, mcu_name: str) -> str:
    preferred = user_name.strip() or mcu_name.strip()
    preferred = preferred.replace('"', "")
    preferred = preferred.replace(" ", "")

    normalized = preferred.upper()
    if "STM32F427" in normalized:
        return "STM32F427II"
    if "STM32H723" in normalized:
        return "STM32H723ZG"

    return preferred


def list_candidates(root: Path, pattern: str, recursive: bool = False) -> List[Path]:
    if recursive:
        items = [p for p in root.rglob(pattern) if p.is_file() and not is_ignored(p, root)]
    else:
        items = [p for p in root.glob(pattern) if p.is_file()]
    return sorted(items)


def pick_best(candidates: Iterable[Path], project_name: str = "") -> Optional[Path]:
    pool = list(candidates)
    if not pool:
        return None

    name = project_name.lower().strip()

    def score(path: Path) -> Tuple[int, int, str]:
        stem = path.stem.lower()
        match_score = 0
        if name:
            if stem == name:
                match_score = -3
            elif stem.startswith(name):
                match_score = -2
            elif name in stem:
                match_score = -1
        depth = len(path.parts)
        return (match_score, depth, str(path))

    return sorted(pool, key=score)[0]


def pick_family_file(candidates: Iterable[Path], family: str) -> Optional[Path]:
    pool = list(candidates)
    if not pool:
        return None
    fam_key = "f4" if family == "STM32F4" else "h7" if family == "STM32H7" else ""
    if fam_key:
        family_matches = [p for p in pool if fam_key in p.name.lower() or family.lower() in p.name.lower()]
        if family_matches:
            return sorted(family_matches)[0]
    return sorted(pool)[0]


def find_artifact(root: Path, ext: str, project_name: str) -> Optional[Path]:
    preferred_dirs = [
        root / "build_gcc",
        root / "builds/gcc/debug",
        root / "build_ac6",
        root / "builds/gcc/release",
    ]

    for d in preferred_dirs:
        if d.is_dir():
            match = pick_best(sorted(d.glob(f"*.{ext}")), project_name)
            if match is not None:
                return match

    candidates: List[Path] = []
    for d in (root / "builds", root / "build", root):
        if d.is_dir():
            for p in d.rglob(f"*.{ext}"):
                if p.is_file() and not is_ignored(p, root):
                    candidates.append(p)

    return pick_best(candidates, project_name)


def scan_project(project_root: Path) -> ScanResult:
    ioc_top = list_candidates(project_root, "*.ioc", recursive=False)
    ioc_rec = list_candidates(project_root, "*.ioc", recursive=True)
    ioc = pick_best(ioc_top) or pick_best(ioc_rec)

    config: Dict[str, str] = {}
    if ioc:
        config = read_ioc_kv(ioc)

    project_name = config.get("ProjectManager.ProjectName", project_root.name)
    mcu_name = config.get("Mcu.Name", "")
    mcu_user_name = config.get("Mcu.UserName", "")
    mcu_family = normalize_family(config.get("Mcu.Family", ""), mcu_name)

    startup = pick_best(list_candidates(project_root, "startup_stm32*.s", recursive=False), project_name)
    if startup is None:
        startup = pick_best(list_candidates(project_root, "startup_stm32*.s", recursive=True), project_name)

    linker_candidates = list_candidates(project_root, "*.ld", recursive=False) + list_candidates(project_root, "*.sct", recursive=False)
    if not linker_candidates:
        linker_candidates = list_candidates(project_root, "*.ld", recursive=True) + list_candidates(project_root, "*.sct", recursive=True)
    linker = pick_family_file(linker_candidates, mcu_family)

    svd_candidates = list_candidates(project_root, "*.svd", recursive=False)
    if not svd_candidates:
        svd_candidates = list_candidates(project_root, "*.svd", recursive=True)
    svd = pick_family_file(svd_candidates, mcu_family)

    cfg_candidates = list_candidates(project_root, "*.cfg", recursive=False)
    cfg_priority = [p for p in cfg_candidates if "stm32" in p.name.lower()]
    cfg = pick_best(cfg_priority) or pick_best(cfg_candidates)

    elf = find_artifact(project_root, "elf", project_name)
    hex_file = find_artifact(project_root, "hex", project_name)
    map_file = find_artifact(project_root, "map", project_name)

    jlink_dir = project_root / "build_tools/jlink"

    return ScanResult(
        ioc=ioc,
        project_name=project_name,
        mcu_family=mcu_family,
        mcu_name=mcu_name,
        mcu_user_name=mcu_user_name,
        startup=startup,
        linker=linker,
        svd=svd,
        cfg=cfg,
        elf=elf,
        hex_file=hex_file,
        map_file=map_file,
        jlink_flash=(jlink_dir / "flash.jlink") if (jlink_dir / "flash.jlink").is_file() else None,
        jlink_debug=(jlink_dir / "debug.jlink") if (jlink_dir / "debug.jlink").is_file() else None,
        jlink_rtt=(jlink_dir / "rtt.jlink") if (jlink_dir / "rtt.jlink").is_file() else None,
    )


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")
    return True


def copy_file(src: Path, dst: Path, force: bool = False) -> bool:
    if not src.exists():
        return False
    if dst.exists() and not force:
        return False
    ensure_parent(dst)
    shutil.copy2(src, dst)
    return True


def default_jlink_templates(device: str) -> Dict[str, str]:
    return {
        "flash.jlink": (
            f"device {device}\n"
            "si SWD\n"
            "speed 4000\n"
            "connect\n"
            "h\n"
            "// loadfile path should be provided by wrapper script\n"
            "exit\n"
        ),
        "debug.jlink": (
            f"device {device}\n"
            "si SWD\n"
            "speed 4000\n"
            "connect\n"
            "h\n"
            "regs\n"
            "exit\n"
        ),
        "rtt.jlink": (
            f"device {device}\n"
            "si SWD\n"
            "speed 4000\n"
            "connect\n"
            "go\n"
            "exit\n"
        ),
    }


def find_template(repo_root: Path, family: str, pattern: str) -> Optional[Path]:
    key = FAMILY_KEY_MAP.get(family)
    if not key:
        return None
    template_dir = repo_root / ".codex/stm32/templates" / key
    if not template_dir.is_dir():
        return None
    matches = sorted(template_dir.glob(pattern))
    return matches[0] if matches else None


def apply_missing_files(
    repo_root: Path,
    project_root: Path,
    scan: ScanResult,
    device: str,
    force: bool,
) -> List[str]:
    generated: List[str] = []

    if scan.mcu_family == "UNKNOWN":
        return generated

    if scan.startup is None:
        src = find_template(repo_root, scan.mcu_family, "startup_stm32*.s")
        if src:
            dst = project_root / src.name
            if copy_file(src, dst, force=force):
                generated.append(str(dst))

    if scan.linker is None:
        src = find_template(repo_root, scan.mcu_family, "*.ld") or find_template(repo_root, scan.mcu_family, "*.sct")
        if src:
            dst = project_root / src.name
            if copy_file(src, dst, force=force):
                generated.append(str(dst))

    if scan.svd is None:
        src = find_template(repo_root, scan.mcu_family, "*.svd")
        if src:
            dst = project_root / src.name
            if copy_file(src, dst, force=force):
                generated.append(str(dst))

    if scan.cfg is None:
        src = find_template(repo_root, scan.mcu_family, "stm32*.cfg") or find_template(repo_root, scan.mcu_family, "*.cfg")
        if src:
            dst = project_root / src.name
            if copy_file(src, dst, force=force):
                generated.append(str(dst))

    jlink_dir = project_root / "build_tools/jlink"
    jlink_dir.mkdir(parents=True, exist_ok=True)
    templates = default_jlink_templates(device)
    for file_name, content in templates.items():
        dst = jlink_dir / file_name
        if write_text(dst, content, force=force):
            generated.append(str(dst))

    return generated


def to_rel_str(path: Optional[Path], root: Path) -> str:
    if not path:
        return ""
    try:
        return os.path.relpath(path.resolve(), root.resolve())
    except Exception:
        return str(path)


def file_signature(path: Optional[Path], root: Path) -> Dict[str, object]:
    rel_path = to_rel_str(path, root)
    if path is None:
        return {"path": rel_path, "exists": False}
    try:
        stat = path.stat()
        return {
            "path": rel_path,
            "exists": True,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    except FileNotFoundError:
        return {"path": rel_path, "exists": False}


def build_profile_fingerprint_payload(project_root: Path, scan: ScanResult) -> Dict[str, object]:
    return {
        "fingerprint_version": FINGERPRINT_VERSION,
        "project_name": scan.project_name,
        "mcu_family": scan.mcu_family,
        "mcu_name": scan.mcu_name,
        "mcu_user_name": scan.mcu_user_name,
        "ioc": file_signature(scan.ioc, project_root),
        "startup": file_signature(scan.startup, project_root),
        "linker": file_signature(scan.linker, project_root),
        "svd": file_signature(scan.svd, project_root),
        "cfg": file_signature(scan.cfg, project_root),
        "elf": file_signature(scan.elf, project_root),
        "hex": file_signature(scan.hex_file, project_root),
        "map": file_signature(scan.map_file, project_root),
        "jlink_flash": file_signature(scan.jlink_flash, project_root),
        "jlink_debug": file_signature(scan.jlink_debug, project_root),
        "jlink_rtt": file_signature(scan.jlink_rtt, project_root),
    }


def compute_profile_fingerprint(project_root: Path, scan: ScanResult) -> str:
    payload = build_profile_fingerprint_payload(project_root, scan)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def export_ioc_json(repo_root: Path, project_root: Path, ioc_path: Optional[Path]) -> Optional[str]:
    if ioc_path is None:
        return "IOC parser export skipped: missing .ioc file"

    parser_script = repo_root / ".codex/skills/bfd-ioc-parser/scripts/parse_ioc.py"
    output_dir = project_root / DEFAULT_IOC_JSON_DIR
    if not parser_script.is_file():
        return f"IOC parser export skipped: missing parser script ({to_rel_str(parser_script, project_root)})"

    cmd = [
        sys.executable,
        str(parser_script),
        "--ioc",
        str(ioc_path),
        "--output",
        str(output_dir),
        "--no-history",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:
        return f"IOC parser export failed: {exc}"

    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "unknown parser failure").strip().splitlines()[-1]
        return f"IOC parser export failed: {message}"

    return None


def unique_paths(paths: Iterable[Path]) -> List[Path]:
    unique: List[Path] = []
    seen = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def build_output_targets(project_root: Path, primary: Path, canonical_rel: str, legacy_rel: str) -> List[Path]:
    return unique_paths([
        primary,
        resolve_output(project_root, canonical_rel),
        resolve_output(project_root, legacy_rel),
    ])


def build_profile(project_root: Path, scan: ScanResult, generated_files: List[str]) -> Tuple[Dict[str, object], List[str], List[str]]:
    device = normalize_device(scan.mcu_user_name, scan.mcu_name)
    family = scan.mcu_family

    blockers: List[str] = []
    warnings: List[str] = []

    if scan.ioc is None:
        blockers.append("Missing .ioc file")
    if family == "UNKNOWN":
        blockers.append("Unsupported or unknown MCU family (expected STM32F4/STM32H7)")
    if not device:
        blockers.append("Missing MCU device name from ioc")
    if scan.startup is None:
        blockers.append("Missing startup assembly file (*.s)")
    if scan.linker is None:
        blockers.append("Missing linker script (*.ld or *.sct)")
    if scan.svd is None:
        blockers.append("Missing SVD file (*.svd)")

    if scan.elf is None:
        warnings.append("Missing ELF artifact (build not found)")
    if scan.hex_file is None:
        warnings.append("Missing HEX artifact (build not found)")
    if scan.map_file is None:
        warnings.append("Missing MAP artifact (build not found)")

    has_jlink = shutil.which("JLinkExe") is not None
    fingerprint = compute_profile_fingerprint(project_root, scan)

    profile: Dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "project": {
            "root": ".",
            "name": scan.project_name,
            "ioc_file": to_rel_str(scan.ioc, project_root),
        },
        "mcu": {
            "family": family,
            "name": scan.mcu_name,
            "user_name": scan.mcu_user_name,
        },
        "artifacts": {
            "startup_file": to_rel_str(scan.startup, project_root),
            "linker_file": to_rel_str(scan.linker, project_root),
            "svd_file": to_rel_str(scan.svd, project_root),
            "cfg_file": to_rel_str(scan.cfg, project_root),
            "elf": to_rel_str(scan.elf, project_root),
            "hex": to_rel_str(scan.hex_file, project_root),
            "map": to_rel_str(scan.map_file, project_root),
            "jlink_flash": to_rel_str(scan.jlink_flash, project_root),
            "jlink_debug": to_rel_str(scan.jlink_debug, project_root),
            "jlink_rtt": to_rel_str(scan.jlink_rtt, project_root),
        },
        "debug": {
            "probe": "jlink",
            "device": device,
            "interface": "SWD",
            "speed_khz": "4000",
        },
        "rtt": {
            "symbol": "_SEGGER_RTT",
            "scan_window": RTT_SCAN_WINDOW.get(family, ""),
        },
        "runtime": {
            "profile_dir": DEFAULT_PROFILE_DIR,
            "legacy_profile_dir": LEGACY_PROFILE_DIR,
            "profile_json": DEFAULT_PROFILE_JSON,
            "profile_env": DEFAULT_PROFILE_ENV,
            "legacy_profile_json": LEGACY_PROFILE_JSON,
            "legacy_profile_env": LEGACY_PROFILE_ENV,
            "ioc_json_dir": DEFAULT_IOC_JSON_DIR,
            "profile_overrides_env": DEFAULT_PROFILE_OVERRIDES_ENV,
            "fingerprint_version": FINGERPRINT_VERSION,
            "fingerprint": fingerprint,
        },
        "tooling": {
            "jlink_available": has_jlink,
        },
        "capabilities": {
            "flash": bool(device and (scan.elf or scan.hex_file)),
            "rtt": bool(device and scan.elf),
            "register_capture": bool(scan.svd),
        },
        "gaps": {
            "blockers": blockers,
            "warnings": warnings,
        },
        "generated_files": [os.path.relpath(item, project_root) for item in generated_files],
    }

    return profile, blockers, warnings


def write_profile_json(path: Path, profile: Dict[str, object]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_profile_env(path: Path, profile: Dict[str, object]) -> None:
    ensure_parent(path)
    debug = profile.get("debug", {})
    art = profile.get("artifacts", {})
    mcu = profile.get("mcu", {})
    rtt = profile.get("rtt", {})
    project = profile.get("project", {})
    runtime = profile.get("runtime", {})

    lines = [
        f"STM32_PROFILE_VERSION={SCHEMA_VERSION}",
        f"STM32_PROFILE_DIR={runtime.get('profile_dir', DEFAULT_PROFILE_DIR)}",
        f"STM32_PROFILE_JSON={runtime.get('profile_json', DEFAULT_PROFILE_JSON)}",
        f"STM32_PROFILE_ENV={runtime.get('profile_env', DEFAULT_PROFILE_ENV)}",
        f"STM32_PROFILE_LEGACY_DIR={runtime.get('legacy_profile_dir', LEGACY_PROFILE_DIR)}",
        f"STM32_PROFILE_LEGACY_JSON={runtime.get('legacy_profile_json', LEGACY_PROFILE_JSON)}",
        f"STM32_PROFILE_LEGACY_ENV={runtime.get('legacy_profile_env', LEGACY_PROFILE_ENV)}",
        f"STM32_PROFILE_FINGERPRINT={runtime.get('fingerprint', '')}",
        f"STM32_PROFILE_FINGERPRINT_VERSION={runtime.get('fingerprint_version', FINGERPRINT_VERSION)}",
        f"STM32_IOC_JSON_DIR={runtime.get('ioc_json_dir', DEFAULT_IOC_JSON_DIR)}",
        f"STM32_PROFILE_OVERRIDES_ENV={runtime.get('profile_overrides_env', DEFAULT_PROFILE_OVERRIDES_ENV)}",
        f"STM32_PROJECT_ROOT={project.get('root', '')}",
        f"STM32_IOC={project.get('ioc_file', '')}",
        f"STM32_FAMILY={mcu.get('family', '')}",
        f"STM32_DEVICE={debug.get('device', '')}",
        f"STM32_IF={debug.get('interface', 'SWD')}",
        f"STM32_SPEED_KHZ={debug.get('speed_khz', '4000')}",
        f"STM32_PROBE={debug.get('probe', 'jlink')}",
        f"STM32_ELF={art.get('elf', '')}",
        f"STM32_HEX={art.get('hex', '')}",
        f"STM32_MAP={art.get('map', '')}",
        f"STM32_STARTUP={art.get('startup_file', '')}",
        f"STM32_LINKER={art.get('linker_file', '')}",
        f"STM32_SVD={art.get('svd_file', '')}",
        f"STM32_CFG={art.get('cfg_file', '')}",
        f"STM32_RTT_SYMBOL={rtt.get('symbol', '_SEGGER_RTT')}",
        f"STM32_RTT_SCAN_WINDOW={rtt.get('scan_window', '')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(path: Path, profile: Dict[str, object], blockers: List[str], warnings: List[str]) -> None:
    ensure_parent(path)
    project = profile.get("project", {})
    mcu = profile.get("mcu", {})
    debug = profile.get("debug", {})
    art = profile.get("artifacts", {})
    generated = profile.get("generated_files", [])

    lines: List[str] = [
        "# BFD Project Init Report",
        "",
        f"- Generated at: {profile.get('generated_at', '')}",
        f"- Project root: {project.get('root', '')}",
        f"- MCU family: {mcu.get('family', '')}",
        f"- MCU name: {mcu.get('name', '')}",
        f"- Debug device: {debug.get('device', '')}",
        "",
        "## Artifacts",
        f"- IOC: {project.get('ioc_file', '')}",
        f"- Startup: {art.get('startup_file', '')}",
        f"- Linker: {art.get('linker_file', '')}",
        f"- SVD: {art.get('svd_file', '')}",
        f"- ELF: {art.get('elf', '')}",
        f"- HEX: {art.get('hex', '')}",
        f"- MAP: {art.get('map', '')}",
        "",
        "## Gaps",
    ]

    if blockers:
        lines.append("### Blockers")
        for item in blockers:
            lines.append(f"- {item}")
    else:
        lines.append("- Blockers: none")

    if warnings:
        lines.append("### Warnings")
        for item in warnings:
            lines.append(f"- {item}")
    else:
        lines.append("- Warnings: none")

    lines.extend([
        "",
        "## Generated Files",
    ])

    if generated:
        for item in generated:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend([
        "",
        "## Next Commands",
        "```bash",
        "# Flash",
        "./build_tools/jlink/flash.sh",
        "",
        "# RTT",
        "./build_tools/jlink/rtt.sh logs/rtt/bootstrap_check.log 5 --mode quick",
        "",
        "# Orchestrated debug campaign",
        "./.codex/skills/bfd-debug-orchestrator/scripts/run_fault_campaign.sh --skip-build",
        "```",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    ensure_parent(dst)
    shutil.copy2(src, dst)
    return True


def seed_templates(repo_root: Path, family_key: str, source_root: Path) -> int:
    if family_key not in {"f4", "h7"}:
        print(f"[ERROR] unsupported seed family: {family_key}", file=sys.stderr)
        return 1

    source_root = source_root.resolve()
    if not source_root.is_dir():
        print(f"[ERROR] seed source not found: {source_root}", file=sys.stderr)
        return 1

    template_dir = (repo_root / ".codex/stm32/templates" / family_key).resolve()
    template_dir.mkdir(parents=True, exist_ok=True)

    copied: List[str] = []

    patterns = ["*.svd", "startup_stm32*.s", "*.ld", "*.sct", "*.cfg"]
    for pattern in patterns:
        for src in sorted(source_root.glob(pattern)):
            dst = template_dir / src.name
            if copy_if_exists(src, dst):
                copied.append(str(dst))

    jlink_map = {
        "build_tools/jlink/flash.jlink": "flash.jlink.tpl",
        "build_tools/jlink/debug.jlink": "debug.jlink.tpl",
        "build_tools/jlink/rtt.jlink": "rtt.jlink.tpl",
    }
    for rel, out_name in jlink_map.items():
        src = source_root / rel
        dst = template_dir / out_name
        if copy_if_exists(src, dst):
            copied.append(str(dst))

    manifest = {
        "seeded_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "family": family_key,
        "source": os.path.relpath(source_root, repo_root),
        "copied": [os.path.relpath(item, repo_root) for item in copied],
    }
    (template_dir / "seed_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[INFO] template seed complete: {template_dir}")
    print(f"[INFO] copied files: {len(copied)}")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="STM32 bootstrap profile generator (F4/H7)")
    parser.add_argument("--project-root", default=".", help="Target project root (default: .)")
    parser.add_argument("--mode", choices=["check", "apply"], default="check", help="check: report only; apply: allow remediation")
    parser.add_argument("--apply", action="store_true", help="Required with --mode apply to actually write files")
    parser.add_argument("--force", action="store_true", help="Allow overwrite when applying")
    parser.add_argument("--out-json", default=DEFAULT_PROFILE_JSON, help="Profile JSON path")
    parser.add_argument("--out-env", default=DEFAULT_PROFILE_ENV, help="Profile env path")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="Markdown report path")
    parser.add_argument("--seed-family", choices=["f4", "h7"], help="Seed template registry for a family")
    parser.add_argument("--seed-source", help="Source project path for template seed")
    return parser.parse_args()


def resolve_output(project_root: Path, path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else (project_root / path)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[4]

    if args.seed_family:
        if not args.seed_source:
            print("[ERROR] --seed-source is required when --seed-family is set", file=sys.stderr)
            return 1
        return seed_templates(repo_root, args.seed_family, Path(args.seed_source))

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"[ERROR] project root not found: {project_root}", file=sys.stderr)
        return 1

    scan = scan_project(project_root)
    device = normalize_device(scan.mcu_user_name, scan.mcu_name)

    generated_files: List[str] = []
    if args.mode == "apply":
        if args.apply:
            generated_files = apply_missing_files(repo_root, project_root, scan, device, force=args.force)
            scan = scan_project(project_root)
            device = normalize_device(scan.mcu_user_name, scan.mcu_name)
        else:
            warn("mode=apply without --apply: running in report-only mode")

    profile, blockers, warnings = build_profile(project_root, scan, generated_files)

    ioc_warning = export_ioc_json(repo_root, project_root, scan.ioc)
    if ioc_warning:
        warnings.append(ioc_warning)
        profile["gaps"]["warnings"] = warnings

    out_json = resolve_output(project_root, args.out_json)
    out_env = resolve_output(project_root, args.out_env)
    out_report = resolve_output(project_root, args.report)

    json_targets = build_output_targets(project_root, out_json, DEFAULT_PROFILE_JSON, LEGACY_PROFILE_JSON)
    env_targets = build_output_targets(project_root, out_env, DEFAULT_PROFILE_ENV, LEGACY_PROFILE_ENV)
    report_targets = build_output_targets(project_root, out_report, DEFAULT_REPORT, LEGACY_REPORT)

    for path_item in json_targets:
        write_profile_json(path_item, profile)
    for path_item in env_targets:
        write_profile_env(path_item, profile)
    for path_item in report_targets:
        write_report(path_item, profile, blockers, warnings)

    print(f"PROFILE_JSON={os.path.relpath(resolve_output(project_root, DEFAULT_PROFILE_JSON), project_root)}")
    print(f"PROFILE_ENV={os.path.relpath(resolve_output(project_root, DEFAULT_PROFILE_ENV), project_root)}")
    print(f"REPORT={os.path.relpath(resolve_output(project_root, DEFAULT_REPORT), project_root)}")
    print(f"BLOCKERS={len(blockers)}")
    print(f"WARNINGS={len(warnings)}")

    if blockers:
        return 2

    if not profile.get("tooling", {}).get("jlink_available", False):
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())

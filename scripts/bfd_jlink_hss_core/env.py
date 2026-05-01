"""Probe discovery helpers for the native BFD-Kit HSS CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
from typing import Iterable, Optional


PROBE_PATTERN = re.compile(
    r"J-Link\[(?P<index>\d+)\]:\s+Connection:\s+(?P<connection>[^,]+),\s+Serial number:\s+(?P<serial>\d+),\s+ProductName:\s+(?P<product>.+)$"
)


class ProbeDiscoveryError(RuntimeError):
    """Raised when probe enumeration fails."""


@dataclass
class ProbeInfo:
    index: int
    connection: str
    serial_number: str
    product_name: str

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_platform_name(platform_name: Optional[str] = None) -> str:
    raw = (platform_name or sys.platform).strip().lower()
    if raw.startswith("win"):
        return "windows"
    if raw.startswith("linux"):
        return "linux"
    if raw.startswith("darwin"):
        return "darwin"
    return raw


def default_jlink_exe_placeholder(platform_name: Optional[str] = None) -> str:
    normalized = normalize_platform_name(platform_name)
    if normalized == "windows":
        return r"<JLINK_INSTALL_DIR>\JLink.exe"
    return "<JLINK_INSTALL_DIR>/JLinkExe"


def default_jlink_exe_hints(platform_name: Optional[str] = None) -> list[str]:
    normalized = normalize_platform_name(platform_name)
    if normalized == "windows":
        return [
            r"%JLINK_EXE%",
            r"%ProgramFiles%\SEGGER\JLink\JLink.exe",
            r"%ProgramFiles(x86)%\SEGGER\JLink\JLink.exe",
            default_jlink_exe_placeholder("windows"),
        ]
    return [
        "$JLINK_EXE",
        "/opt/SEGGER/JLink/JLinkExe",
        "/usr/local/bin/JLinkExe",
        default_jlink_exe_placeholder("linux"),
    ]


def iter_default_jlink_exe_candidates(
    platform_name: Optional[str] = None,
    environ: Optional[dict[str, str]] = None,
) -> Iterable[str]:
    env = environ or os.environ
    normalized = normalize_platform_name(platform_name)
    env_path = env.get("JLINK_EXE")
    if env_path:
        yield env_path

    which_path = shutil.which("JLinkExe")
    if which_path:
        yield which_path

    if normalized == "windows":
        seen: set[str] = set()
        roots = [
            env.get("ProgramW6432"),
            env.get("ProgramFiles"),
            env.get("ProgramFiles(x86)"),
        ]
        for root in roots:
            if not root:
                continue
            base = Path(root)
            direct = base / "SEGGER" / "JLink" / "JLink.exe"
            for candidate in [direct, *sorted(base.glob("SEGGER/JLink*/JLink.exe"))]:
                rendered = str(candidate)
                if rendered in seen:
                    continue
                seen.add(rendered)
                yield rendered
        return

    for pattern in (
        "/opt/SEGGER/JLink*/JLinkExe",
        "/usr/bin/JLinkExe",
        "/usr/local/bin/JLinkExe",
    ):
        for path in sorted(Path("/").glob(pattern.lstrip("/"))):
            if path.is_file():
                yield str(path)


def resolve_existing_file(candidates: Iterable[Optional[str]]) -> Optional[Path]:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
    return None


def resolve_jlink_exe(explicit_path: Optional[str] = None, platform_name: Optional[str] = None) -> Path:
    candidates = [explicit_path] if explicit_path else list(iter_default_jlink_exe_candidates(platform_name=platform_name))
    path = resolve_existing_file(candidates)
    if path is None:
        hints = ", ".join(default_jlink_exe_hints(platform_name))
        raise ProbeDiscoveryError(f"JLinkExe not found; set JLINK_EXE or install it at one of: {hints}")
    return path


def parse_probe_list(text: str) -> list[ProbeInfo]:
    probes: list[ProbeInfo] = []
    for line in text.splitlines():
        match = PROBE_PATTERN.search(line.strip())
        if not match:
            continue
        probes.append(
            ProbeInfo(
                index=int(match.group("index")),
                connection=match.group("connection"),
                serial_number=match.group("serial"),
                product_name=match.group("product").strip(),
            )
        )
    return probes


def list_probes(jlink_exe: Optional[str] = None) -> list[ProbeInfo]:
    jlink_path = resolve_jlink_exe(jlink_exe)
    result = subprocess.run(
        [str(jlink_path)],
        input="ShowEmuList\nexit\n",
        text=True,
        capture_output=True,
        check=False,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    probes = parse_probe_list(combined)
    if result.returncode != 0 and not probes:
        raise ProbeDiscoveryError(combined.strip() or f"JLinkExe failed with exit code {result.returncode}")
    return probes

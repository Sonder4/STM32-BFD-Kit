#!/usr/bin/env python3
"""Render canonical SEGGER Ozone project files from the active STM32 profile."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Tuple


CPU_SVD = "$(InstallDir)/Config/CPU/Cortex-M4F.svd"
PROBE_PATTERN = re.compile(
    r"J-Link\[(?P<index>\d+)\]:\s+Connection:\s+(?P<connection>[^,]+),\s+Serial number:\s+(?P<serial>\d+),\s+ProductName:\s+(?P<product>.+)$"
)


class ProbeDiscoveryError(RuntimeError):
    """Raised when current J-Link probe enumeration fails."""


@dataclass
class ProbeInfo:
    index: int
    connection: str
    serial_number: str
    product_name: str


def _iter_default_jlink_exe_candidates() -> Iterable[str]:
    env_path = os.environ.get("JLINK_EXE")
    if env_path:
        yield env_path

    which_path = shutil.which("JLinkExe")
    if which_path:
        yield which_path

    for pattern in (
        "/opt/SEGGER/JLink*/JLinkExe",
        "/usr/bin/JLinkExe",
        "/usr/local/bin/JLinkExe",
    ):
        for path in sorted(Path("/").glob(pattern.lstrip("/"))):
            if path.is_file():
                yield str(path)


def _resolve_existing_file(candidates: Iterable[Optional[str]]) -> Optional[Path]:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
    return None


def _resolve_jlink_exe(explicit_path: Optional[str] = None) -> Path:
    candidates = [explicit_path] if explicit_path else list(_iter_default_jlink_exe_candidates())
    path = _resolve_existing_file(candidates)
    if path is None:
        raise ProbeDiscoveryError("JLinkExe not found")
    return path


def _parse_probe_list(text: str) -> List[ProbeInfo]:
    probes: List[ProbeInfo] = []
    for line in text.splitlines():
        match = PROBE_PATTERN.search(line.strip())
        if not match:
            continue
        probes.append(
            ProbeInfo(
                index=int(match.group("index")),
                connection=match.group("connection").strip(),
                serial_number=match.group("serial").strip(),
                product_name=match.group("product").strip(),
            )
        )
    return probes


def _list_probes(jlink_exe: Optional[str] = None, timeout_seconds: float = 8.0) -> List[ProbeInfo]:
    jlink_path = _resolve_jlink_exe(jlink_exe)
    try:
        result = subprocess.run(
            [str(jlink_path)],
            input="ShowEmuList\nexit\n",
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="ignore") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="ignore") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        partial = (stdout + stderr).strip()
        detail = f" Partial output: {partial}" if partial else ""
        raise ProbeDiscoveryError(
            f"JLinkExe probe enumeration timed out after {timeout_seconds:.1f}s.{detail}"
        ) from exc
    combined = (result.stdout or "") + (result.stderr or "")
    probes = _parse_probe_list(combined)
    if result.returncode != 0 and not probes:
        raise ProbeDiscoveryError(combined.strip() or f"JLinkExe failed with exit code {result.returncode}")
    return probes


def _choose_probe(probes: List[ProbeInfo], requested_sn: Optional[str]) -> ProbeInfo:
    explicit_sn = (requested_sn or "").strip()
    if explicit_sn:
        for probe in probes:
            if probe.serial_number == explicit_sn:
                return probe
        serials = ", ".join(probe.serial_number for probe in probes) or "<none>"
        raise ProbeDiscoveryError(
            f"requested J-Link serial number not found: {explicit_sn}; detected probes: {serials}"
        )

    if not probes:
        raise ProbeDiscoveryError("no J-Link probes detected")

    if len(probes) == 1:
        return probes[0]

    env_sn = os.environ.get("JLINK_SN", "").strip()
    if env_sn:
        for probe in probes:
            if probe.serial_number == env_sn:
                return probe
        serials = ", ".join(probe.serial_number for probe in probes)
        raise ProbeDiscoveryError(
            f"JLINK_SN={env_sn} not found among detected J-Link probes: {serials}"
        )

    probe_labels = ", ".join(f"{probe.serial_number} ({probe.product_name})" for probe in probes)
    raise ProbeDiscoveryError(
        "multiple J-Link probes detected; set JLINK_SN or pass --host-sn explicitly "
        f"({probe_labels})"
    )


def _resolve_probe_binding(
    host_if: str,
    host_sn: Optional[str],
    jlink_exe: Optional[str],
    probe_timeout_seconds: float,
) -> Tuple[str, Optional[ProbeInfo]]:
    if host_if.upper() != "USB":
        return host_sn or "", None

    normalized = (host_sn or "auto").strip()
    if normalized == "":
        return "", None

    if normalized.lower() == "auto":
        probe = _choose_probe(_list_probes(jlink_exe, timeout_seconds=probe_timeout_seconds), None)
        return probe.serial_number, probe

    probe = _choose_probe(_list_probes(jlink_exe, timeout_seconds=probe_timeout_seconds), normalized)
    return probe.serial_number, probe


def _load_profile(project_root: Path) -> Dict[str, str]:
    candidates = [
        project_root / ".codex/bfd/active_profile.env",
        project_root / ".codex/stm32/bootstrap/active_profile.env",
    ]
    for path in candidates:
        if path.is_file():
            result: Dict[str, str] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                result[key] = value
            return result
    raise FileNotFoundError("active_profile.env not found under .codex/bfd or legacy bootstrap path")


def _path_expr(project_root: Path, raw: str) -> str:
    path = Path(raw)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    try:
        rel = path.relative_to(project_root)
    except ValueError:
        return str(path)
    return f"$(ProjectDir)/{rel.as_posix()}"


def _lower_path(value: str) -> str:
    return "".join(ch.lower() if "A" <= ch <= "Z" else ch for ch in value)


def _format_speed(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "4 MHz"
    if any(ch.isalpha() for ch in stripped):
        return stripped
    try:
        khz = int(stripped)
    except ValueError:
        return stripped
    if khz % 1000 == 0:
        return f"{khz // 1000} MHz"
    return f"{khz} kHz"


def _parse_open_doc(item: str) -> Tuple[str, int]:
    if ":" not in item:
        return item, 1
    path_part, line_part = item.rsplit(":", 1)
    try:
        line = int(line_part)
    except ValueError:
        path_part = item
        line = 1
    return path_part, line


def _parse_watch(item: str) -> Tuple[str, str, str]:
    parts = item.split(":", 2)
    expr = parts[0]
    refresh = parts[1] if len(parts) >= 2 and parts[1] else "5"
    display = parts[2] if len(parts) >= 3 and parts[2] else "DISPLAY_FORMAT_DEC"
    return expr, refresh, display


def _render_jdebug(
    jdebug_path: Path,
    project_root: Path,
    device: str,
    host_if: str,
    host_sn: str,
    target_if: str,
    tif_speed: str,
    cpu_svd: str,
    svd_expr: str,
    elf_expr: str,
    os_plugin: str,
    hss_speed: str,
    probe_comment: str,
) -> str:
    return f"""/*********************************************************************
*                 (c) SEGGER Microcontroller GmbH                    *
*                      The Embedded Experts                          *
*                         www.segger.com                             *
**********************************************************************

File          : {jdebug_path}
Created       : 17. Apr 2026
Ozone Version : generated by BFD Ozone
Probe         : {probe_comment}
*/

/*********************************************************************
*
*       OnProjectLoad
*
**********************************************************************
*/
void OnProjectLoad (void) {{
  Project.AddPathSubstitute ("{project_root.as_posix()}", "$(ProjectDir)");
  Project.AddPathSubstitute ("{_lower_path(project_root.as_posix())}", "$(ProjectDir)");
  Project.SetDevice ("{device}");
  Project.SetHostIF ("{host_if}", "{host_sn}");
  Project.SetTargetIF ("{target_if}");
  Project.SetTIFSpeed ("{tif_speed}");
  Project.AddSvdFile ("{cpu_svd}");
  Project.AddSvdFile ("{svd_expr}");
  Edit.SysVar (VAR_HSS_SPEED, {hss_speed});
  Project.SetOSPlugin ("{os_plugin}");
  File.Open ("{elf_expr}");
}}

void AfterTargetReset (void) {{
  _SetupTarget();
}}

void AfterTargetDownload (void) {{
  _SetupTarget();
}}

void _SetupTarget(void) {{
  unsigned int SP;
  unsigned int PC;
  unsigned int VectorTableAddr;

  VectorTableAddr = Elf.GetBaseAddr();
  SP = Target.ReadU32(VectorTableAddr);
  if (SP != 0xFFFFFFFF) {{
    Target.SetReg("SP", SP);
  }}
  PC = Elf.GetEntryPointPC();
  if (PC != 0xFFFFFFFF) {{
    Target.SetReg("PC", PC);
  }} else {{
    Util.Error("Project script error: failed to set up entry point PC", 1);
  }}
}}
"""


def _render_user(project_root: Path, open_docs: List[str], watches: List[str]) -> str:
    lines: List[str] = [""]
    for entry in open_docs:
        rel_path, line = _parse_open_doc(entry)
        abs_path = (project_root / rel_path).resolve()
        lines.append(
            f'OpenDocument="{abs_path.name}", FilePath="{abs_path.as_posix()}", Line={line}'
        )
    lines.extend(
        [
            'OpenToolbar="Debug", Floating=0, x=0, y=0',
            'OpenWindow="Source Files", DockArea=LEFT, x=0, y=0, w=360, h=780, FilterBarShown=1, TotalValueBarShown=1, ToolBarShown=0',
            'OpenWindow="Watched Data 1", DockArea=RIGHT, x=0, y=0, w=720, h=980, FilterBarShown=0, TotalValueBarShown=0, ToolBarShown=0',
            'OpenWindow="Console", DockArea=BOTTOM, x=0, y=0, w=1247, h=318, FilterBarShown=0, TotalValueBarShown=0, ToolBarShown=0',
            'OpenWindow="Memory 1", DockArea=BOTTOM, x=1, y=0, w=1245, h=318, FilterBarShown=0, TotalValueBarShown=0, ToolBarShown=0, EditorAddress=0x0',
            'SmartViewPlugin="", Page="", Toolbar="Hidden", Window="SmartView 1"',
            'TableHeader="RegisterSelectionDialog", SortCol="None", SortOrder="ASCENDING", VisibleCols=[], ColWidths=[]',
            'TableHeader="TargetExceptionDialog", SortCol="Name", SortOrder="ASCENDING", VisibleCols=["Name";"Value";"Address";"Description"], ColWidths=[200;100;100;900]',
            'TableHeader="Source Files", SortCol="Path", SortOrder="ASCENDING", VisibleCols=["File";"Path"], ColWidths=[239;819]',
            'TableHeader="Watched Data 1", SortCol="Expression", SortOrder="ASCENDING", VisibleCols=["Expression";"Value";"Location";"Refresh"], ColWidths=[348;272;104;152]',
        ]
    )
    for entry in watches:
        expr, refresh, display = _parse_watch(entry)
        lines.append(
            f'WatchedExpression="{expr}", RefreshRate={refresh}, DisplayFormat={display}, Window=Watched Data 1'
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render canonical Ozone project files from the active STM32 profile")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--jdebug", required=True)
    parser.add_argument("--user-file")
    parser.add_argument("--device")
    parser.add_argument("--host-if", default="USB")
    parser.add_argument(
        "--host-sn",
        default="auto",
        help='J-Link USB serial number. Use "auto" to enumerate the current probe, or "" to keep the binding blank.',
    )
    parser.add_argument("--jlink-exe", help="Optional path to JLinkExe for probe enumeration")
    parser.add_argument(
        "--probe-timeout-seconds",
        type=float,
        default=8.0,
        help="Timeout for JLinkExe probe enumeration before failing fast.",
    )
    parser.add_argument("--target-if")
    parser.add_argument("--tif-speed")
    parser.add_argument("--cpu-svd", default=CPU_SVD)
    parser.add_argument("--elf")
    parser.add_argument("--svd")
    parser.add_argument("--os-plugin", default="FreeRTOSPlugin_Cortex-M")
    parser.add_argument("--hss-speed", default="FREQ_200_HZ")
    parser.add_argument("--rewrite-user", action="store_true")
    parser.add_argument("--open-doc", action="append", default=[])
    parser.add_argument("--watch", action="append", default=[])
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    profile = _load_profile(project_root)

    device = args.device or profile.get("STM32_DEVICE", "STM32F427II")
    target_if = args.target_if or profile.get("STM32_IF", "SWD")
    tif_speed = _format_speed(args.tif_speed or profile.get("STM32_SPEED_KHZ", "4000"))
    elf_expr = _path_expr(project_root, args.elf or profile["STM32_ELF"])
    svd_expr = _path_expr(project_root, args.svd or profile["STM32_SVD"])
    resolved_host_sn, probe = _resolve_probe_binding(
        args.host_if,
        args.host_sn,
        args.jlink_exe,
        args.probe_timeout_seconds,
    )
    if probe is not None:
        print(
            f"[bfd-ozone] using current J-Link probe S/N={probe.serial_number} "
            f"Product={probe.product_name}"
        )
        probe_comment = f"{probe.product_name} (S/N {probe.serial_number})"
    elif args.host_if.upper() == "USB" and resolved_host_sn == "":
        print("[bfd-ozone] keeping blank J-Link USB serial binding in .jdebug")
        probe_comment = "blank USB serial binding"
    else:
        probe_comment = "not applicable"

    jdebug_path = (project_root / args.jdebug).resolve()
    jdebug_path.write_text(
        _render_jdebug(
            project_root=project_root,
            jdebug_path=jdebug_path,
            device=device,
            host_if=args.host_if,
            host_sn=resolved_host_sn,
            target_if=target_if,
            tif_speed=tif_speed,
            cpu_svd=args.cpu_svd,
            svd_expr=svd_expr,
            elf_expr=elf_expr,
            os_plugin=args.os_plugin,
            hss_speed=args.hss_speed,
            probe_comment=probe_comment,
        ),
        encoding="utf-8",
    )
    print(f"[bfd-ozone] wrote {jdebug_path}")

    if args.user_file:
        user_path = (project_root / args.user_file).resolve()
        if args.rewrite_user or (not user_path.exists()):
            user_path.write_text(
                _render_user(project_root, args.open_doc, args.watch),
                encoding="utf-8",
            )
            print(f"[bfd-ozone] wrote {user_path}")
        else:
            print(f"[bfd-ozone] kept existing {user_path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ProbeDiscoveryError) as exc:
        print(f"[bfd-ozone] {exc}", file=sys.stderr)
        raise SystemExit(2)

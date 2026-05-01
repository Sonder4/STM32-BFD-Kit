#!/usr/bin/env python3
"""BFD-Kit experiment dataset and Matlab bridge."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bfd_jlink_hss import _default_int, _default_value, select_probe_or_sn
from bfd_jlink_hss_core.hss_sampling import sample_scalar_symbols
from bfd_jlink_hss_core.jlink_dll import JLinkDll, resolve_jlinkarm_dll
from bfd_mcp_client import McpError, find_mcp_server, run_matlab_script_via_mcp


DEFAULT_MATLAB_BIN = "/home/xuan/matlab/bin/matlab"
TEMPLATES_DIR = SCRIPT_DIR.parent / "resources" / "matlab" / "templates"
ANALYSIS_SCRIPTS = {
    "system-id": "run_system_id.m",
    "control": "run_control_tuning.m",
    "kalman": "run_kalman_tuning.m",
    "mcd-check": "run_mcd_codegen_check.m",
}


class ExperimentError(RuntimeError):
    """Raised when an experiment workflow cannot continue."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", name.strip())
    return safe.strip("._") or "experiment"


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def find_matlab_bin(explicit: Optional[str] = None) -> Optional[str]:
    candidates: list[Optional[str]] = [
        explicit,
        os.environ.get("MATLAB_BIN"),
        DEFAULT_MATLAB_BIN,
        shutil.which("matlab"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if _is_executable(path):
            return str(path.resolve())
    return None


def _read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _to_int(value: Any) -> Optional[int]:
    parsed = _to_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _value_columns(headers: list[str], rows: list[dict[str, str]]) -> list[str]:
    columns: list[str] = []
    for header in headers:
        lower = header.lower()
        if lower in {"sample_index", "time_us", "time_s"} or "raw_hex" in lower:
            continue
        if header.endswith("__value"):
            columns.append(header)
            continue
        numeric_count = sum(1 for row in rows if _to_float(row.get(header)) is not None)
        if rows and numeric_count >= max(1, len(rows) // 2):
            columns.append(header)
    return columns


def _column_stats(rows: list[dict[str, str]], columns: list[str]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for column in columns:
        values: list[float] = []
        missing = 0
        non_numeric = 0
        for row in rows:
            raw = row.get(column)
            if raw is None or str(raw).strip() == "":
                missing += 1
                continue
            parsed = _to_float(raw)
            if parsed is None:
                non_numeric += 1
                continue
            values.append(parsed)
        stats[column] = {
            "count": len(values),
            "missing": missing,
            "non_numeric": non_numeric,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "mean": statistics.fmean(values) if values else None,
            "std": statistics.pstdev(values) if len(values) > 1 else 0.0 if values else None,
            "first": values[0] if values else None,
            "last": values[-1] if values else None,
        }
    return stats


def _classify_columns(columns: list[str]) -> dict[str, list[str]]:
    classification = {
        "input_columns": [],
        "output_columns": [],
        "state_columns": [],
        "sensor_columns": [],
        "motor_columns": [],
    }
    for column in columns:
        lower = column.lower()
        if re.search(r"(cmd|command|target|setpoint|input|ref)", lower):
            classification["input_columns"].append(column)
        if re.search(r"(speed|rpm|angle|position|pos|output|measure|meas|feedback)", lower):
            classification["output_columns"].append(column)
        if re.search(r"(state|pos|position|vel|velocity|x_)", lower):
            classification["state_columns"].append(column)
        if re.search(r"(imu|gyro|acc|sensor|yaw|pitch|roll|temp|adc|encoder)", lower):
            classification["sensor_columns"].append(column)
        if re.search(r"(motor|rpm|speed|current|torque|encoder)", lower):
            classification["motor_columns"].append(column)
    return classification


def _sample_index_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    indices = [_to_int(row.get("sample_index")) for row in rows]
    indices = [index for index in indices if index is not None]
    if not indices:
        return {"available": False, "missing_count": 0, "duplicate_count": 0}
    missing_count = 0
    for previous, current in zip(indices, indices[1:]):
        if current > previous + 1:
            missing_count += current - previous - 1
    return {
        "available": True,
        "first": indices[0],
        "last": indices[-1],
        "missing_count": missing_count,
        "duplicate_count": len(indices) - len(set(indices)),
    }


def _timing_summary(rows: list[dict[str, str]], meta: dict[str, Any]) -> dict[str, Any]:
    times = [_to_float(row.get("time_us")) for row in rows]
    times = [item for item in times if item is not None]
    diffs = [current - previous for previous, current in zip(times, times[1:])]
    nominal = meta.get("period_us")
    if nominal is None and diffs:
        nominal = statistics.median(diffs)
    if nominal is not None:
        nominal = int(nominal) if float(nominal).is_integer() else float(nominal)
    tolerance = max(1.0, abs(float(nominal)) * 0.01) if nominal is not None else 0.0
    irregular = sum(1 for diff in diffs if nominal is not None and abs(diff - float(nominal)) > tolerance)
    return {
        "available": bool(times),
        "first_time_us": times[0] if times else None,
        "last_time_us": times[-1] if times else None,
        "nominal_period_us": nominal,
        "min_interval_us": min(diffs) if diffs else None,
        "max_interval_us": max(diffs) if diffs else None,
        "irregular_interval_count": irregular,
    }


def _compact_rows(rows: list[dict[str, str]], columns: list[str], limit: int = 2) -> dict[str, list[dict[str, str]]]:
    keep = ["sample_index", "time_us", *columns]

    def trim(row: dict[str, str]) -> dict[str, str]:
        return {key: row.get(key, "") for key in keep if key in row}

    return {
        "head": [trim(row) for row in rows[:limit]],
        "tail": [trim(row) for row in rows[-limit:]] if len(rows) > limit else [],
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# BFD Experiment Summary: {summary['csv_path']}",
        "",
        f"- samples: {summary['sample_count']}",
        f"- value columns: {', '.join(summary['value_columns']) if summary['value_columns'] else 'none'}",
        f"- sample index missing: {summary['sample_index'].get('missing_count', 0)}",
        f"- timing nominal period us: {summary['timing'].get('nominal_period_us')}",
        f"- timing irregular intervals: {summary['timing'].get('irregular_interval_count')}",
        "",
        "## Column Stats",
    ]
    for name, stats in summary["columns"].items():
        lines.append(
            f"- {name}: count={stats['count']} min={stats['min']} max={stats['max']} "
            f"mean={stats['mean']} std={stats['std']}"
        )
    lines.append("")
    lines.append("## Classification")
    for key, values in summary["classification"].items():
        lines.append(f"- {key}: {', '.join(values) if values else 'none'}")
    return "\n".join(lines) + "\n"


def summarize_capture(csv_path: Path, meta_path: Optional[Path] = None, output_dir: Optional[Path] = None) -> dict[str, Any]:
    if not csv_path.is_file():
        raise ExperimentError(f"CSV not found: {csv_path}")
    meta = _read_json(meta_path) if meta_path else {}
    headers, rows = _read_csv_rows(csv_path)
    value_columns = _value_columns(headers, rows)
    target_dir = output_dir or csv_path.parent
    summary = {
        "schema_version": 1,
        "csv_path": str(csv_path.resolve()),
        "meta_path": str(meta_path.resolve()) if meta_path else None,
        "summary_json_path": str((target_dir / "summary.json").resolve()),
        "summary_md_path": str((target_dir / "summary.md").resolve()),
        "sample_count": len(rows),
        "value_columns": value_columns,
        "sample_index": _sample_index_summary(rows),
        "timing": _timing_summary(rows, meta),
        "columns": _column_stats(rows, value_columns),
        "classification": _classify_columns(value_columns),
        "examples": _compact_rows(rows, value_columns),
    }
    _write_json(target_dir / "summary.json", summary)
    (target_dir / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    return summary


def ensure_matlab_templates(dataset_dir: Path) -> Path:
    matlab_dir = dataset_dir / "matlab"
    matlab_dir.mkdir(parents=True, exist_ok=True)
    if not TEMPLATES_DIR.is_dir():
        raise ExperimentError(f"Matlab template directory not found: {TEMPLATES_DIR}")
    for template in sorted(TEMPLATES_DIR.glob("*.m")):
        target = matlab_dir / template.name
        if (not target.exists()) or (template.stat().st_mtime > target.stat().st_mtime):
            shutil.copyfile(template, target)
    return matlab_dir


def _result_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        return dict(result.to_dict())
    return {
        "csv_path": getattr(result, "csv_path", None),
        "meta_path": getattr(result, "meta_path", None),
        "sample_count": getattr(result, "sample_count", None),
        "symbols": getattr(result, "symbols", []),
        "caps": getattr(result, "caps", {}),
        "connected_serial_number": getattr(result, "connected_serial_number", None),
        "duration_s": getattr(result, "duration_s", None),
        "period_us": getattr(result, "period_us", None),
        "record_size_bytes": getattr(result, "record_size_bytes", None),
    }


def build_manifest(
    *,
    args: argparse.Namespace,
    dataset_dir: Path,
    csv_path: Path,
    meta_path: Path,
    summary: dict[str, Any],
    hss_result: dict[str, Any],
    selected_probe: Optional[dict[str, Any]],
    matlab_bin: Optional[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "experiment_name": args.experiment_name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "stimulus": args.stimulus,
        "notes": args.notes,
        "dataset_dir": str(dataset_dir.resolve()),
        "target": {
            "elf": str(Path(args.elf).expanduser().resolve()),
            "device": args.device,
            "probe": "jlink",
            "selected_probe": selected_probe,
            "interface": args.interface,
            "speed_khz": args.speed,
        },
        "capture": {
            "backend": "jlink_hss",
            "csv": str(csv_path.name),
            "meta": str(meta_path.name),
            "period_us": args.period_us,
            "duration_s": args.duration,
            "symbols": list(args.symbol),
            "hss_result": hss_result,
        },
        "classification": summary["classification"],
        "matlab": {
            "matlab_bin": matlab_bin,
            "required_toolboxes": [
                "System Identification Toolbox",
                "Control System Toolbox",
                "Model Predictive Control Toolbox",
                "Sensor Fusion and Tracking Toolbox",
                "Simulink",
                "Simulink Test",
                "MATLAB Coder",
                "Simulink Coder",
                "Embedded Coder",
            ],
            "preferred_backend": "matlab-mcp-core-server",
        },
    }


def emit_compact(summary: dict[str, Any], *, dataset_dir: Optional[Path] = None) -> None:
    if dataset_dir is not None:
        print(f"dataset_dir: {dataset_dir}")
    print(f"samples: {summary['sample_count']}")
    print(f"value_columns: {', '.join(summary['value_columns']) if summary['value_columns'] else 'none'}")
    print(f"missing_sample_indices: {summary['sample_index'].get('missing_count', 0)}")
    print(f"irregular_intervals: {summary['timing'].get('irregular_interval_count')}")
    print(f"summary_json: {summary['summary_json_path']}")


def cmd_summarize(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset_dir).expanduser().resolve() if args.dataset_dir else None
    if args.csv:
        csv_path = Path(args.csv).expanduser().resolve()
    elif dataset_dir is not None:
        csv_path = dataset_dir / "capture.csv"
    else:
        raise ExperimentError("pass either --dataset-dir or --csv")
    meta_path = Path(args.meta).expanduser().resolve() if args.meta else Path(f"{csv_path}.meta.json")
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else csv_path.parent
    summary = summarize_capture(csv_path, meta_path if meta_path.is_file() else None, output_dir)
    emit_compact(summary)
    return 0


def cmd_capture_hss(args: argparse.Namespace) -> int:
    args.elf = _default_value(args.elf, "STM32_ELF", "STM32_ELF")
    args.device = _default_value(args.device, "STM32_DEVICE", "STM32_DEVICE", "STM32F427II")
    args.interface = _default_value(args.interface, "STM32_IF", "STM32_IF", "SWD")
    args.speed = _default_int(args.speed, "STM32_SPEED_KHZ", "STM32_SPEED_KHZ", 4000)
    if not args.elf:
        raise ExperimentError("ELF path is required; pass --elf or provide STM32_ELF")

    output_root = Path(args.output_dir).expanduser().resolve()
    args.experiment_name = _safe_name(args.experiment_name or time.strftime("hss_%Y%m%d_%H%M%S"))
    dataset_dir = output_root / args.experiment_name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    csv_path = dataset_dir / "capture.csv"

    selected_probe, selected_sn = select_probe_or_sn(usb_sn=args.usb_sn, jlink_exe=args.jlink_exe)
    dll = JLinkDll(dll_path=args.jlink_dll or resolve_jlinkarm_dll())
    result = sample_scalar_symbols(
        dll=dll,
        elf_path=args.elf,
        symbol_expressions=list(args.symbol),
        device=args.device,
        interface=args.interface,
        speed_khz=args.speed,
        duration_s=args.duration,
        period_us=args.period_us,
        output_csv=str(csv_path),
        usb_sn=selected_sn,
        read_buffer_size=args.read_buffer_size,
    )
    hss_result = _result_to_dict(result)
    meta_path = Path(getattr(result, "meta_path", None) or f"{csv_path}.meta.json").expanduser().resolve()
    summary = summarize_capture(Path(result.csv_path), meta_path if meta_path.is_file() else None, dataset_dir)
    matlab_bin = find_matlab_bin(args.matlab_bin)
    ensure_matlab_templates(dataset_dir)
    manifest = build_manifest(
        args=args,
        dataset_dir=dataset_dir,
        csv_path=Path(result.csv_path),
        meta_path=meta_path,
        summary=summary,
        hss_result=hss_result,
        selected_probe=selected_probe,
        matlab_bin=matlab_bin,
    )
    _write_json(dataset_dir / "manifest.json", manifest)
    emit_compact(summary, dataset_dir=dataset_dir)
    return 0


def _matlab_run_expr(script_path: Path) -> str:
    path = str(script_path.resolve()).replace("'", "''")
    return f"run('{path}')"


def _write_backend_status(out_dir: Path, status: dict[str, Any]) -> None:
    _write_json(out_dir / "matlab_backend.json", status)
    analysis = status.get("analysis")
    if analysis:
        _write_json(out_dir / f"matlab_backend_{_safe_name(str(analysis))}.json", status)


def _default_mcp_args(args: argparse.Namespace, *, dataset_dir: Path, out_dir: Path) -> list[str]:
    if args.mcp_arg:
        return list(args.mcp_arg)
    matlab_root = args.mcp_matlab_root or os.environ.get("MATLAB_ROOT")
    if not matlab_root:
        matlab_bin = find_matlab_bin(args.matlab_bin)
        if matlab_bin:
            matlab_root = str(Path(matlab_bin).resolve().parents[1])
    work_dir = Path(args.mcp_working_dir).expanduser().resolve() if args.mcp_working_dir else dataset_dir
    log_dir = Path(args.mcp_log_dir).expanduser().resolve() if args.mcp_log_dir else out_dir / "mcp_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    mcp_args = [
        f"--initial-working-folder={work_dir}",
        "--matlab-display-mode=nodesktop",
        "--disable-telemetry=true",
        f"--log-folder={log_dir}",
    ]
    if matlab_root:
        mcp_args.insert(0, f"--matlab-root={Path(matlab_root).expanduser().resolve()}")
    return mcp_args


def _run_matlab_cli(args: argparse.Namespace, *, script_path: Path, out_dir: Path) -> int:
    matlab_bin = find_matlab_bin(args.matlab_bin)
    if matlab_bin is None:
        raise ExperimentError("Matlab executable not found; pass --matlab-bin or set MATLAB_BIN")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [matlab_bin, "-batch", _matlab_run_expr(script_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    log_text = (result.stdout or "") + (result.stderr or "")
    (out_dir / "matlab.log").write_text(log_text, encoding="utf-8")
    (out_dir / f"matlab_{_safe_name(args.analysis)}.log").write_text(log_text, encoding="utf-8")
    print(f"matlab_log: {out_dir / 'matlab.log'}")
    if result.returncode != 0:
        print(f"matlab_exit_code: {result.returncode}", file=sys.stderr)
        return result.returncode
    return 0


def _run_matlab_mcp(args: argparse.Namespace, *, dataset_dir: Path, script_path: Path, out_dir: Path) -> int:
    server = find_mcp_server(args.mcp_server)
    if server is None:
        raise ExperimentError("matlab-mcp-core-server not found; pass --mcp-server or set MATLAB_MCP_SERVER")
    mcp_args = _default_mcp_args(args, dataset_dir=dataset_dir, out_dir=out_dir)
    result = run_matlab_script_via_mcp(
        server=server,
        server_args=mcp_args,
        script_path=script_path,
        satk_root=args.satk_root,
        timeout_s=args.mcp_timeout_sec,
    )
    _write_json(out_dir / "matlab_mcp_result.json", result)
    _write_json(out_dir / f"matlab_mcp_result_{_safe_name(args.analysis)}.json", result)
    log_text = str(result.get("log_text", "")) + "\n"
    (out_dir / "matlab.log").write_text(log_text, encoding="utf-8")
    (out_dir / f"matlab_{_safe_name(args.analysis)}.log").write_text(log_text, encoding="utf-8")
    _write_backend_status(
        out_dir,
        {
            "backend": "mcp",
            "server": server,
            "server_args": mcp_args,
            "analysis": args.analysis,
            "script": str(script_path),
            "satk_root": args.satk_root,
        },
    )
    print(f"matlab_backend: mcp")
    print(f"matlab_log: {out_dir / 'matlab.log'}")
    print(f"mcp_result: {out_dir / 'matlab_mcp_result.json'}")
    return 0


def cmd_matlab_run(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset_dir).expanduser().resolve()
    if not dataset_dir.is_dir():
        raise ExperimentError(f"dataset directory not found: {dataset_dir}")
    matlab_dir = ensure_matlab_templates(dataset_dir)
    script_name = ANALYSIS_SCRIPTS[args.analysis]
    script_path = matlab_dir / script_name
    if not script_path.is_file():
        raise ExperimentError(f"Matlab analysis script not found: {script_path}")

    out_dir = dataset_dir / "matlab_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    backend = args.matlab_backend
    if backend in {"auto", "mcp"}:
        try:
            return _run_matlab_mcp(args, dataset_dir=dataset_dir, script_path=script_path, out_dir=out_dir)
        except (ExperimentError, McpError, OSError, ValueError) as exc:
            (out_dir / "matlab_mcp_error.log").write_text(str(exc) + "\n", encoding="utf-8")
            if backend == "mcp":
                print(f"matlab_mcp_error: {exc}", file=sys.stderr)
                return 1
            print(f"matlab_backend: cli_fallback")
            print(f"matlab_mcp_error_log: {out_dir / 'matlab_mcp_error.log'}")
    status = _run_matlab_cli(args, script_path=script_path, out_dir=out_dir)
    _write_backend_status(
        out_dir,
        {
            "backend": "cli",
            "analysis": args.analysis,
            "script": str(script_path),
            "reason": "explicit cli backend" if backend == "cli" else "mcp unavailable or failed",
        },
    )
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BFD-Kit experiment dataset and Matlab bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture-hss", help="Capture a J-Link HSS experiment dataset")
    capture.add_argument("--elf", default=None, help="ELF path; falls back to STM32_ELF")
    capture.add_argument("--symbol", action="append", required=True, help="Fixed-address scalar symbol; repeat for multiple")
    capture.add_argument("--device", default=None, help="Target device")
    capture.add_argument("--interface", default=None, help="Target interface")
    capture.add_argument("--speed", type=int, default=None, help="Target speed in kHz")
    capture.add_argument("--duration", type=float, required=True, help="Capture duration in seconds")
    capture.add_argument("--period-us", type=int, default=1000, help="HSS sampling period in microseconds")
    capture.add_argument("--output-dir", default="logs/experiments", help="Experiment root output directory")
    capture.add_argument("--experiment-name", default=None, help="Dataset directory name")
    capture.add_argument("--stimulus", default=None, help="Experiment stimulus description")
    capture.add_argument("--notes", default=None, help="Operator notes")
    capture.add_argument("--usb-sn", default=None, help="Optional J-Link USB serial number")
    capture.add_argument("--jlink-dll", default=None, help="Optional libjlinkarm.so path")
    capture.add_argument("--jlink-exe", default=None, help="Optional JLinkExe path for probe discovery")
    capture.add_argument("--read-buffer-size", type=int, default=4096, help="Preferred HSS read buffer size")
    capture.add_argument("--matlab-bin", default=None, help="Optional Matlab executable path")
    capture.set_defaults(handler=cmd_capture_hss)

    summarize = subparsers.add_parser("summarize", help="Summarize a capture CSV without printing full data")
    summarize.add_argument("--dataset-dir", default=None, help="Dataset directory containing capture.csv")
    summarize.add_argument("--csv", default=None, help="Capture CSV path")
    summarize.add_argument("--meta", default=None, help="Capture metadata JSON path")
    summarize.add_argument("--output-dir", default=None, help="Summary output directory")
    summarize.set_defaults(handler=cmd_summarize)

    matlab = subparsers.add_parser("matlab-run", help="Run a Matlab analysis template for a dataset")
    matlab.add_argument("--dataset-dir", required=True, help="Dataset directory")
    matlab.add_argument("--analysis", choices=sorted(ANALYSIS_SCRIPTS), required=True, help="Analysis template to run")
    matlab.add_argument("--matlab-bin", default=None, help="Optional Matlab executable path")
    matlab.add_argument("--matlab-backend", choices=["auto", "mcp", "cli"], default="auto", help="Matlab execution backend")
    matlab.add_argument("--mcp-server", default=None, help="Optional matlab-mcp-core-server executable")
    matlab.add_argument("--mcp-arg", action="append", default=[], help="Argument passed to matlab-mcp-core-server; repeatable")
    matlab.add_argument("--mcp-timeout-sec", type=float, default=180.0, help="MCP request timeout")
    matlab.add_argument("--mcp-matlab-root", default=None, help="Matlab root passed to MCP server")
    matlab.add_argument("--mcp-working-dir", default=None, help="Initial working folder passed to MCP server")
    matlab.add_argument("--mcp-log-dir", default=None, help="MCP server log folder")
    matlab.add_argument("--satk-root", default=None, help="Optional Simulink Agentic Toolkit root for satk_initialize")
    matlab.set_defaults(handler=cmd_matlab_run)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ExperimentError, OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

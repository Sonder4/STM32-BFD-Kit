import importlib.util
import json
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_experiment.py"
SPEC = importlib.util.spec_from_file_location("bfd_experiment", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_capture(csv_path: Path) -> None:
    csv_path.write_text(
        "\n".join(
            [
                "sample_index,time_us,motor_cmd__value,motor_cmd__raw_hex,motor_speed__value",
                "0,0,0,00,1.0",
                "1,1000,1,01,2.0",
                "3,3000,1,01,5.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_find_matlab_bin_prefers_explicit_path(tmp_path):
    matlab_bin = tmp_path / "matlab"
    matlab_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    matlab_bin.chmod(0o755)

    assert MODULE.find_matlab_bin(str(matlab_bin)) == str(matlab_bin.resolve())


def test_summarize_wide_csv_writes_compact_artifacts(tmp_path):
    csv_path = tmp_path / "capture.csv"
    _write_capture(csv_path)
    meta_path = tmp_path / "capture.csv.meta.json"
    meta_path.write_text('{"period_us": 1000, "symbols": []}', encoding="utf-8")

    exit_code = MODULE.main(["summarize", "--csv", str(csv_path), "--meta", str(meta_path), "--output-dir", str(tmp_path)])

    assert exit_code == 0
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["sample_count"] == 3
    assert summary["sample_index"]["missing_count"] == 1
    assert summary["timing"]["nominal_period_us"] == 1000
    assert summary["timing"]["irregular_interval_count"] == 1
    assert summary["columns"]["motor_speed__value"]["max"] == 5.0
    assert "motor_cmd__value" in summary["classification"]["input_columns"]
    assert "motor_speed__value" in summary["classification"]["motor_columns"]
    assert (tmp_path / "summary.md").is_file()


def test_capture_hss_creates_dataset_manifest_and_summary(tmp_path, monkeypatch):
    captured = {}

    class FakeDll:
        def __init__(self, dll_path=None):
            self.dll_path = dll_path

    def fake_sample_scalar_symbols(**kwargs):
        captured.update(kwargs)
        output_csv = Path(kwargs["output_csv"])
        _write_capture(output_csv)
        meta_path = Path(f"{output_csv}.meta.json")
        meta_path.write_text(
            json.dumps(
                {
                    "period_us": kwargs["period_us"],
                    "duration_s": kwargs["duration_s"],
                    "symbols": [{"expression": item} for item in kwargs["symbol_expressions"]],
                }
            ),
            encoding="utf-8",
        )
        return type(
            "Result",
            (),
            {
                "csv_path": str(output_csv),
                "meta_path": str(meta_path),
                "sample_count": 3,
                "symbols": [{"expression": item} for item in kwargs["symbol_expressions"]],
                "symbol": {"expression": kwargs["symbol_expressions"][0]},
                "caps": {"raw_words": [10, 64, 2]},
                "connected_serial_number": 602712337,
                "duration_s": kwargs["duration_s"],
                "period_us": kwargs["period_us"],
                "record_size_bytes": 12,
                "to_dict": lambda self=None: {"sample_count": 3},
            },
        )()

    monkeypatch.setattr(MODULE, "JLinkDll", FakeDll)
    monkeypatch.setattr(MODULE, "resolve_jlinkarm_dll", lambda: "/opt/SEGGER/JLink/libjlinkarm.so")
    monkeypatch.setattr(MODULE, "select_probe_or_sn", lambda **_kwargs: ({"serial_number": "602712337"}, "602712337"))
    monkeypatch.setattr(MODULE, "sample_scalar_symbols", fake_sample_scalar_symbols)

    exit_code = MODULE.main(
        [
            "capture-hss",
            "--elf",
            str(tmp_path / "app.elf"),
            "--symbol",
            "motor.cmd",
            "--symbol",
            "motor.speed",
            "--device",
            "STM32F427II",
            "--duration",
            "0.1",
            "--period-us",
            "1000",
            "--output-dir",
            str(tmp_path),
            "--experiment-name",
            "motor_step_001",
            "--stimulus",
            "step",
            "--notes",
            "unit test",
        ]
    )

    assert exit_code == 0
    dataset_dir = tmp_path / "motor_step_001"
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["experiment_name"] == "motor_step_001"
    assert manifest["capture"]["backend"] == "jlink_hss"
    assert manifest["capture"]["symbols"] == ["motor.cmd", "motor.speed"]
    assert manifest["classification"]["input_columns"] == ["motor_cmd__value"]
    assert captured["usb_sn"] == "602712337"
    assert (dataset_dir / "matlab" / "run_system_id.m").is_file()


def test_matlab_run_invokes_batch_script_and_writes_log(tmp_path, monkeypatch):
    dataset_dir = tmp_path / "dataset"
    matlab_dir = dataset_dir / "matlab"
    matlab_dir.mkdir(parents=True)
    script_path = matlab_dir / "run_system_id.m"
    script_path.write_text("disp('ok')\n", encoding="utf-8")
    (dataset_dir / "manifest.json").write_text('{"schema_version": 1}', encoding="utf-8")
    matlab_bin = tmp_path / "matlab"
    matlab_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    matlab_bin.chmod(0o755)
    calls = []

    def fake_run(command, text, capture_output, check):
        calls.append(command)
        return type("Result", (), {"returncode": 0, "stdout": "MATLAB ok\n", "stderr": ""})()

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    monkeypatch.setattr(MODULE, "find_mcp_server", lambda _explicit=None: None)

    exit_code = MODULE.main(
        [
            "matlab-run",
            "--dataset-dir",
            str(dataset_dir),
            "--analysis",
            "system-id",
            "--matlab-bin",
            str(matlab_bin),
        ]
    )

    assert exit_code == 0
    assert calls[0][0] == str(matlab_bin.resolve())
    assert calls[0][1] == "-batch"
    assert "run_system_id.m" in calls[0][2]
    assert "MATLAB ok" in (dataset_dir / "matlab_out" / "matlab.log").read_text(encoding="utf-8")
    backend = json.loads((dataset_dir / "matlab_out" / "matlab_backend.json").read_text(encoding="utf-8"))
    assert backend["backend"] == "cli"


def test_matlab_run_prefers_mcp_when_server_is_available(tmp_path, monkeypatch):
    dataset_dir = tmp_path / "dataset"
    matlab_dir = dataset_dir / "matlab"
    matlab_dir.mkdir(parents=True)
    script_path = matlab_dir / "run_system_id.m"
    script_path.write_text("disp('ok')\n", encoding="utf-8")
    (dataset_dir / "manifest.json").write_text('{"schema_version": 1}', encoding="utf-8")
    server = tmp_path / "matlab-mcp-core-server"
    server.write_text("#!/bin/sh\n", encoding="utf-8")
    server.chmod(0o755)
    calls = []

    def fake_run_matlab_script_via_mcp(**kwargs):
        calls.append(kwargs)
        return {
            "backend": "mcp",
            "tool_names": ["detect_matlab_toolboxes", "run_matlab_file"],
            "log_text": "MCP ok",
        }

    monkeypatch.setattr(MODULE, "find_mcp_server", lambda _explicit=None: str(server))
    monkeypatch.setattr(MODULE, "run_matlab_script_via_mcp", fake_run_matlab_script_via_mcp)

    exit_code = MODULE.main(
        [
            "matlab-run",
            "--dataset-dir",
            str(dataset_dir),
            "--analysis",
            "system-id",
            "--mcp-arg=--test-mode",
        ]
    )

    assert exit_code == 0
    assert calls[0]["server"] == str(server)
    assert calls[0]["server_args"] == ["--test-mode"]
    assert calls[0]["script_path"] == script_path
    assert "MCP ok" in (dataset_dir / "matlab_out" / "matlab.log").read_text(encoding="utf-8")
    backend = json.loads((dataset_dir / "matlab_out" / "matlab_backend.json").read_text(encoding="utf-8"))
    assert backend["backend"] == "mcp"

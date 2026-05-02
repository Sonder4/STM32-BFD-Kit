import importlib.util
import json
import os
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_project_detect.py"
SPEC = importlib.util.spec_from_file_location("bfd_project_detect", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_detect_cmake_h7_project_from_ioc_and_artifacts(tmp_path):
    workspace = tmp_path / "RSCF_h7"
    workspace.mkdir()
    (workspace / "CMakeLists.txt").write_text("project(RSCF_H7)\n", encoding="utf-8")
    (workspace / "RSCF_A.ioc").write_text(
        "\n".join(
            [
                "ProjectManager.TargetToolchain=STM32CubeCLT",
                "Mcu.Name=STM32H723ZGTx",
                "ProjectManager.DeviceId=STM32H723ZGTx",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    build_dir = workspace / "builds" / "gcc" / "debug"
    build_dir.mkdir(parents=True)
    (build_dir / "RSCF_H7_BOARD_ONE.elf").write_bytes(b"\x7fELF")

    profile = MODULE.detect_project(workspace)

    assert profile["build_system"] == "cmake"
    assert profile["toolchain"] == "stm32cubeclt"
    assert profile["target_mcu"] == "STM32H723ZGTx"
    assert profile["stm32_family"] == "h7"
    assert profile["artifact_path"].endswith("RSCF_H7_BOARD_ONE.elf")


def test_detect_keil_f4_project(tmp_path):
    workspace = tmp_path / "RSCF_f4"
    workspace.mkdir()
    (workspace / "app.uvprojx").write_text(
        "\n".join(
            [
                "<Project>",
                "  <Targets>",
                "    <Target>",
                "      <TargetOption>",
                "        <TargetCommonOption>",
                "          <Device>STM32F427IIHx</Device>",
                "        </TargetCommonOption>",
                "      </TargetOption>",
                "    </Target>",
                "  </Targets>",
                "</Project>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (workspace / "board.ioc").write_text("ProjectManager.TargetToolchain=MDK-ARM\nMcu.Name=STM32F427IIHx\n", encoding="utf-8")

    profile = MODULE.detect_project(workspace)

    assert profile["build_system"] == "keil"
    assert profile["toolchain"] == "keil"
    assert profile["target_mcu"] == "STM32F427IIHx"
    assert profile["stm32_family"] == "f4"


def test_project_detect_cli_writes_json_profile(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "CMakeLists.txt").write_text("project(test)\n", encoding="utf-8")
    (workspace / "demo.ioc").write_text("ProjectManager.TargetToolchain=STM32CubeCLT\nMcu.Name=STM32F427VETx\n", encoding="utf-8")
    output_path = tmp_path / "profile.json"

    exit_code = MODULE.main(["--workspace", str(workspace), "--output", str(output_path)])

    assert exit_code == 0
    profile = json.loads(output_path.read_text(encoding="utf-8"))
    assert profile["toolchain"] == "stm32cubeclt"
    assert profile["stm32_family"] == "f4"


def test_detect_project_includes_cmake_presets_and_artifact_bundles(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "CMakeLists.txt").write_text("project(test)\n", encoding="utf-8")
    (workspace / "board.ioc").write_text("ProjectManager.TargetToolchain=STM32CubeCLT\nMcu.Name=STM32H723ZGTx\n", encoding="utf-8")
    (workspace / "CMakePresets.json").write_text(
        json.dumps(
            {
                "version": 3,
                "configurePresets": [
                    {
                        "name": "Debug",
                        "generator": "Ninja",
                        "binaryDir": "${sourceDir}/builds/gcc/debug",
                    }
                ],
                "buildPresets": [
                    {
                        "name": "Debug",
                        "configurePreset": "Debug",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    build_dir = workspace / "builds" / "gcc" / "debug"
    build_dir.mkdir(parents=True)
    (build_dir / "demo.elf").write_text("elf\n", encoding="utf-8")
    (build_dir / "demo.hex").write_text("hex\n", encoding="utf-8")
    (build_dir / "demo.bin").write_text("bin\n", encoding="utf-8")

    profile = MODULE.detect_project(workspace)

    assert profile["cmake_presets"]["configure"][0]["name"] == "Debug"
    assert profile["cmake_presets"]["configure"][0]["binaryDir"].endswith("/builds/gcc/debug")
    assert profile["build_directories"][0].endswith("/builds/gcc/debug")
    assert profile["artifact_bundles"][0]["base_name"] == "demo"
    assert profile["artifact_bundles"][0]["triplet_ready"] is True
    assert profile["artifact_bundles"][0]["stale_kinds"] == []


def test_detect_project_marks_stale_hex_and_missing_bin(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "CMakeLists.txt").write_text("project(test)\n", encoding="utf-8")
    build_dir = workspace / "build"
    build_dir.mkdir()
    elf_path = build_dir / "app.elf"
    hex_path = build_dir / "app.hex"
    elf_path.write_text("elf-new\n", encoding="utf-8")
    hex_path.write_text("hex-old\n", encoding="utf-8")
    elf_path.write_text("elf-newer\n", encoding="utf-8")
    os.utime(hex_path, (10, 10))
    os.utime(elf_path, (20, 20))

    profile = MODULE.detect_project(workspace)

    bundle = profile["artifact_bundles"][0]
    assert bundle["base_name"] == "app"
    assert bundle["triplet_ready"] is False
    assert bundle["missing_kinds"] == ["bin"]
    assert "hex" in bundle["stale_kinds"]


def test_detect_project_ignores_cmake_internal_artifacts(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "CMakeLists.txt").write_text("project(test)\n", encoding="utf-8")
    build_dir = workspace / "builds" / "gcc" / "debug"
    internal_dir = build_dir / "CMakeFiles" / "3.28.1"
    internal_dir.mkdir(parents=True)
    (internal_dir / "CMakeDetermineCompilerABI_C.bin").write_text("bin\n", encoding="utf-8")
    (build_dir / "demo.elf").write_text("elf\n", encoding="utf-8")
    (build_dir / "demo.hex").write_text("hex\n", encoding="utf-8")
    (build_dir / "demo.bin").write_text("bin\n", encoding="utf-8")

    profile = MODULE.detect_project(workspace)

    assert all("CMakeDetermineCompilerABI_C.bin" not in item for item in profile["artifact_candidates"])
    assert len(profile["artifact_bundles"]) == 1
    assert profile["artifact_bundles"][0]["base_name"] == "demo"

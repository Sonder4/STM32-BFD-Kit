import importlib.util
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_cubeclt_build.py"
SPEC = importlib.util.spec_from_file_location("bfd_cubeclt_build", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_env_prepends_tool_directories():
    env = MODULE.build_env_with_tools(
        {
            "cmake": "/opt/st/stm32cubeclt/CMake/bin/cmake",
            "ninja": "/opt/st/stm32cubeclt/Ninja/bin/ninja",
            "arm_none_eabi_gcc": "/opt/st/stm32cubeclt/GNU-tools-for-STM32/bin/arm-none-eabi-gcc",
        },
        base_env={"PATH": "/usr/bin"},
    )

    assert env["PATH"].startswith("/opt/st/stm32cubeclt/CMake/bin")
    assert env["PATH"].endswith("/usr/bin")


def test_resolve_preset_names_prefers_matching_build_preset(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "CMakePresets.json").write_text(
        """
{
  "version": 3,
  "configurePresets": [
    {"name": "Debug", "generator": "Ninja", "binaryDir": "${sourceDir}/build/debug"}
  ],
  "buildPresets": [
    {"name": "Debug", "configurePreset": "Debug"}
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = MODULE.resolve_preset_names(workspace, "Debug")

    assert resolved["configure_preset"] == "Debug"
    assert resolved["build_preset"] == "Debug"
    assert resolved["binary_dir"].endswith("/build/debug")


def test_verify_artifact_bundles_reports_missing_triplet():
    bundles = [
        {
            "base_name": "demo",
            "artifacts": {"elf": "/tmp/demo.elf", "hex": "/tmp/demo.hex"},
            "missing_kinds": ["bin"],
            "stale_kinds": [],
            "triplet_ready": False,
        }
    ]

    report = MODULE.verify_artifact_bundles(bundles, require_triplet=True)

    assert report["ok"] is False
    assert "missing bin" in report["messages"][0]


def test_build_commands_preserve_resolved_cmake_exe_path(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "CMakePresets.json").write_text(
        """
{
  "version": 3,
  "configurePresets": [
    {"name": "Debug", "generator": "Ninja", "binaryDir": "${sourceDir}/build/debug"}
  ],
  "buildPresets": [
    {"name": "Debug", "configurePreset": "Debug"}
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    tool_paths = {
        "cmake": str(tmp_path / "STM32CubeCLT" / "CMake" / "bin" / "cmake.exe"),
        "ninja": str(tmp_path / "STM32CubeCLT" / "Ninja" / "bin" / "ninja.exe"),
    }
    configure_command, _ = MODULE.build_configure_command(workspace, tool_paths, preset_name="Debug", binary_dir=None, toolchain_file=None)
    build_command, _ = MODULE.build_build_command(workspace, tool_paths, preset_name="Debug", binary_dir=None, target=None, jobs=None)

    assert configure_command[0].endswith("cmake.exe")
    assert configure_command[1:] == ["--preset", "Debug"]
    assert build_command[0].endswith("cmake.exe")
    assert build_command[1:] == ["--build", "--preset", "Debug"]

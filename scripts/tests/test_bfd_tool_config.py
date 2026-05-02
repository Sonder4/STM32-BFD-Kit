import importlib.util
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_tool_config.py"
SPEC = importlib.util.spec_from_file_location("bfd_tool_config", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_workspace_config_overrides_global(tmp_path):
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    workspace.mkdir()
    home.mkdir()

    MODULE.set_tool_path("stm32cubeclt_root", "/opt/stm32cubeclt-global", workspace=workspace, home=home, global_flag=True)
    MODULE.set_tool_path("stm32cubeclt_root", "/work/stm32cubeclt-local", workspace=workspace, home=home, global_flag=False)

    assert MODULE.get_tool_path("stm32cubeclt_root", workspace=workspace, home=home) == "/work/stm32cubeclt-local"
    assert MODULE.get_tool_path("stm32cubeclt_root", workspace=None, home=home) == "/opt/stm32cubeclt-global"


def test_list_tools_reports_workspace_and_global_sources(tmp_path):
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    workspace.mkdir()
    home.mkdir()

    MODULE.set_tool_path("cmake", "/usr/bin/cmake", workspace=workspace, home=home, global_flag=True)
    MODULE.set_tool_path("jlink_exe", "/opt/segger/JLinkExe", workspace=workspace, home=home, global_flag=False)

    tools = MODULE.list_tools(workspace=workspace, home=home)

    assert tools["cmake"]["path"] == "/usr/bin/cmake"
    assert tools["cmake"]["source"] == "global"
    assert tools["jlink_exe"]["path"] == "/opt/segger/JLinkExe"
    assert tools["jlink_exe"]["source"] == "workspace"


def test_remove_tool_path_only_affects_requested_scope(tmp_path):
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    workspace.mkdir()
    home.mkdir()

    MODULE.set_tool_path("pyocd", "/usr/bin/pyocd-global", workspace=workspace, home=home, global_flag=True)
    MODULE.set_tool_path("pyocd", "/work/venv/bin/pyocd", workspace=workspace, home=home, global_flag=False)

    assert MODULE.remove_tool_path("pyocd", workspace=workspace, home=home, global_flag=False) is True
    assert MODULE.get_tool_path("pyocd", workspace=workspace, home=home) == "/usr/bin/pyocd-global"
    assert MODULE.remove_tool_path("pyocd", workspace=workspace, home=home, global_flag=True) is True
    assert MODULE.get_tool_path("pyocd", workspace=workspace, home=home) is None


def test_detect_default_tools_finds_cubeclt_binaries_from_root(tmp_path, monkeypatch):
    cube_root = tmp_path / "STM32CubeCLT"
    (cube_root / "CMake" / "bin").mkdir(parents=True)
    (cube_root / "Ninja" / "bin").mkdir(parents=True)
    (cube_root / "GNU-tools-for-STM32" / "bin").mkdir(parents=True)
    (cube_root / "STM32CubeProgrammer" / "bin").mkdir(parents=True)
    (cube_root / "STLink-gdb-server" / "bin").mkdir(parents=True)
    (cube_root / "CMake" / "bin" / "cmake").write_text("", encoding="utf-8")
    (cube_root / "Ninja" / "bin" / "ninja").write_text("", encoding="utf-8")
    (cube_root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gcc").write_text("", encoding="utf-8")
    (cube_root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gdb").write_text("", encoding="utf-8")
    (cube_root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-objcopy").write_text("", encoding="utf-8")
    (cube_root / "STM32CubeProgrammer" / "bin" / "STM32_Programmer_CLI").write_text("", encoding="utf-8")
    (cube_root / "STLink-gdb-server" / "bin" / "ST-LINK_gdbserver").write_text("", encoding="utf-8")

    monkeypatch.setenv("STM32CUBECLT_ROOT", str(cube_root))
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: None)

    detected = MODULE.detect_default_tools(host_os="linux")

    assert detected["stm32cubeclt_root"] == str(cube_root)
    assert detected["cmake"].endswith("/CMake/bin/cmake")
    assert detected["ninja"].endswith("/Ninja/bin/ninja")
    assert detected["arm_none_eabi_gcc"].endswith("/GNU-tools-for-STM32/bin/arm-none-eabi-gcc")
    assert detected["arm_none_eabi_gdb"].endswith("/GNU-tools-for-STM32/bin/arm-none-eabi-gdb")
    assert detected["arm_none_eabi_objcopy"].endswith("/GNU-tools-for-STM32/bin/arm-none-eabi-objcopy")
    assert detected["stm32cubeprogrammer_cli"].endswith("/STM32CubeProgrammer/bin/STM32_Programmer_CLI")
    assert detected["stlink_gdb_server"].endswith("/STLink-gdb-server/bin/ST-LINK_gdbserver")


def test_resolve_tool_path_falls_back_to_detected_cubeclt_tool(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cube_root = tmp_path / "cube"
    (cube_root / "CMake" / "bin").mkdir(parents=True)
    (cube_root / "CMake" / "bin" / "cmake").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        MODULE,
        "detect_default_tools",
        lambda host_os=None: {
            "stm32cubeclt_root": str(cube_root),
            "cmake": str(cube_root / "CMake" / "bin" / "cmake"),
        },
    )

    resolved = MODULE.resolve_tool_path("cmake", workspace=workspace)

    assert resolved == str(cube_root / "CMake" / "bin" / "cmake")


def test_detect_default_tools_accepts_versioned_cubeclt_root(tmp_path, monkeypatch):
    parent = tmp_path / "opt" / "st"
    base_root = parent / "stm32cubeclt"
    versioned_root = parent / "stm32cubeclt_1.21.0"
    (versioned_root / "STM32CubeProgrammer" / "bin").mkdir(parents=True)
    (versioned_root / "STM32CubeProgrammer" / "bin" / "STM32_Programmer_CLI").write_text("", encoding="utf-8")

    monkeypatch.setattr(MODULE, "LINUX_DEFAULT_CUBECLT_ROOTS", [str(base_root)])
    monkeypatch.delenv("STM32CUBECLT_ROOT", raising=False)
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: None)

    detected = MODULE.detect_default_tools(host_os="linux")

    assert detected["stm32cubeclt_root"] == str(versioned_root)
    assert detected["stm32cubeprogrammer_cli"].endswith("/STM32CubeProgrammer/bin/STM32_Programmer_CLI")


def test_detect_default_tools_finds_windows_cubeclt_binaries_from_root(tmp_path, monkeypatch):
    cube_root = tmp_path / "STM32CubeCLT"
    (cube_root / "CMake" / "bin").mkdir(parents=True)
    (cube_root / "Ninja" / "bin").mkdir(parents=True)
    (cube_root / "GNU-tools-for-STM32" / "bin").mkdir(parents=True)
    (cube_root / "STM32CubeProgrammer" / "bin").mkdir(parents=True)
    (cube_root / "STLink-gdb-server" / "bin").mkdir(parents=True)
    (cube_root / "CMake" / "bin" / "cmake.exe").write_text("", encoding="utf-8")
    (cube_root / "Ninja" / "bin" / "ninja.exe").write_text("", encoding="utf-8")
    (cube_root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gcc.exe").write_text("", encoding="utf-8")
    (cube_root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gdb.exe").write_text("", encoding="utf-8")
    (cube_root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-objcopy.exe").write_text("", encoding="utf-8")
    (cube_root / "STM32CubeProgrammer" / "bin" / "STM32_Programmer_CLI.exe").write_text("", encoding="utf-8")
    (cube_root / "STLink-gdb-server" / "bin" / "ST-LINK_gdbserver.exe").write_text("", encoding="utf-8")

    monkeypatch.setenv("STM32CUBECLT_ROOT", str(cube_root))
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: None)

    detected = MODULE.detect_default_tools(host_os="windows")

    assert detected["stm32cubeclt_root"] == str(cube_root)
    assert detected["cmake"].endswith("/CMake/bin/cmake.exe")
    assert detected["ninja"].endswith("/Ninja/bin/ninja.exe")
    assert detected["arm_none_eabi_gcc"].endswith("/GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe")
    assert detected["arm_none_eabi_gdb"].endswith("/GNU-tools-for-STM32/bin/arm-none-eabi-gdb.exe")
    assert detected["arm_none_eabi_objcopy"].endswith("/GNU-tools-for-STM32/bin/arm-none-eabi-objcopy.exe")
    assert detected["stm32cubeprogrammer_cli"].endswith("/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe")
    assert detected["stlink_gdb_server"].endswith("/STLink-gdb-server/bin/ST-LINK_gdbserver.exe")


def test_detect_default_tools_accepts_versioned_windows_cubeclt_root(tmp_path, monkeypatch):
    parent = tmp_path / "vendor"
    base_root = parent / "STM32CubeCLT"
    versioned_root = parent / "STM32CubeCLT_1.21.0"
    (versioned_root / "STM32CubeProgrammer" / "bin").mkdir(parents=True)
    (versioned_root / "STM32CubeProgrammer" / "bin" / "STM32_Programmer_CLI.exe").write_text("", encoding="utf-8")

    monkeypatch.setattr(MODULE, "WINDOWS_DEFAULT_CUBECLT_ROOTS", [str(base_root)])
    monkeypatch.delenv("STM32CUBECLT_ROOT", raising=False)
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: None)

    detected = MODULE.detect_default_tools(host_os="windows")

    assert detected["stm32cubeclt_root"] == str(versioned_root)
    assert detected["stm32cubeprogrammer_cli"].endswith("/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe")

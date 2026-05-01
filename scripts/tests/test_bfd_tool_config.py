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

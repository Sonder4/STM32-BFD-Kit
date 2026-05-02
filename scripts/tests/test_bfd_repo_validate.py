import importlib.util
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_repo_validate.py"
SPEC = importlib.util.spec_from_file_location("bfd_repo_validate", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_validate_repo_layout_accepts_minimal_expected_tree(tmp_path):
    root = tmp_path / "BFD-Kit"
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "scripts" / "bfd_install.py").write_text("", encoding="utf-8")
    (root / "scripts" / "bfd_tool_config.py").write_text("", encoding="utf-8")
    (root / "scripts" / "bfd_project_detect.py").write_text("", encoding="utf-8")
    (root / "scripts" / "bfd_cubeclt_build.py").write_text("", encoding="utf-8")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    (root / "README-en.md").write_text("# demo\n", encoding="utf-8")
    (root / "README-zh.md").write_text("# demo\n", encoding="utf-8")
    (root / "docs" / "platform_compatibility.md").write_text("# guide\n", encoding="utf-8")

    failures = MODULE.validate_repo_layout(root)

    assert failures == []


def test_validate_repo_layout_reports_missing_core_files(tmp_path):
    root = tmp_path / "BFD-Kit"
    root.mkdir()

    failures = MODULE.validate_repo_layout(root)

    assert any("scripts/bfd_install.py" in item for item in failures)
    assert any("README.md" in item for item in failures)

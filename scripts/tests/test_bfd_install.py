import importlib.util
import json
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "bfd_install.py"
SPEC = importlib.util.spec_from_file_location("bfd_install", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _create_fake_source_tree(root: Path) -> None:
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "migrate_bfd_skills.py").write_text(
        "import sys\nraise SystemExit(0)\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    (root / "README-en.md").write_text("# demo-en\n", encoding="utf-8")
    (root / "README-zh.md").write_text("# demo-zh\n", encoding="utf-8")
    (root / "skills" / "codex" / "bfd-project-init").mkdir(parents=True)
    (root / "skills" / "codex" / "bfd-project-init" / "SKILL.md").write_text("---\nname: test\n---\n", encoding="utf-8")
    (root / ".runtime" / "venv").mkdir(parents=True)
    (root / ".runtime" / "venv" / "skip.txt").write_text("skip\n", encoding="utf-8")


def test_install_copies_files_and_skips_runtime(tmp_path):
    source_root = tmp_path / "source"
    project_root = tmp_path / "project"
    source_root.mkdir()
    project_root.mkdir()
    _create_fake_source_tree(source_root)

    payload = MODULE.install_bfd_kit(
        project_root,
        source_root=source_root,
        clean=False,
        detect_tools=False,
        bootstrap_profile=False,
        force_refresh=False,
        skip_cutover=True,
        global_tool_config=False,
    )

    assert payload["copied_files"] >= 5
    assert (project_root / "BFD-Kit" / "README.md").is_file()
    assert (project_root / "BFD-Kit" / "scripts" / "migrate_bfd_skills.py").is_file()
    assert not (project_root / "BFD-Kit" / ".runtime").exists()

    meta = json.loads((project_root / "BFD-Kit" / ".bfd_kit_install_meta.json").read_text(encoding="utf-8"))
    assert meta["project_root"] == str(project_root)


def test_status_reports_install_state(tmp_path):
    source_root = tmp_path / "source"
    project_root = tmp_path / "project"
    source_root.mkdir()
    project_root.mkdir()
    _create_fake_source_tree(source_root)

    before = MODULE.collect_status(project_root)
    assert before["installed"] is False

    MODULE.install_bfd_kit(
        project_root,
        source_root=source_root,
        clean=False,
        detect_tools=False,
        bootstrap_profile=False,
        force_refresh=False,
        skip_cutover=True,
        global_tool_config=False,
    )

    after = MODULE.collect_status(project_root)
    assert after["installed"] is True
    assert after["metadata"]["project_root"] == str(project_root)

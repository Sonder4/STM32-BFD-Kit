# Repository Guidelines

## Project Structure & Module Organization

`scripts/` contains the executable tooling: `bfd_jlink_hss.py`, its Bash wrapper, runtime setup, and migration utilities. Shared Python logic for HSS lives in `scripts/bfd_jlink_hss_core/`. Tests are under `scripts/tests/` and follow the same CLI/core split. `skills/codex/` and `skills/claude/` are the canonical mirrored skill packs; keep behavior and file layout aligned across both trees. `resources/stm32/templates/` stores STM32 family templates, `requirements/` holds runtime dependencies, and `docs/plans/` is for design or implementation notes.

## Build, Test, and Development Commands

Use the repo root for all commands:

- `bash init_project.sh --project-root .` bootstraps the local runtime and refreshes the active BFD profile.
- `bash scripts/install_python_runtime.sh --help` shows runtime installation options for the managed virtualenv in `.runtime/venv`.
- `python3 scripts/bfd_jlink_hss.py --help` verifies the main CLI entrypoint.
- `python3 scripts/migrate_bfd_skills.py --help` checks the skill sync/stage/cutover utility.
- `python3 -m pytest scripts/tests -q` runs the Python test suite.

## Coding Style & Naming Conventions

Python uses 4-space indentation, module-level `snake_case`, and `PascalCase` for classes. Match the existing typed, standard-library-first style used in `scripts/bfd_jlink_hss.py` and `scripts/bfd_jlink_hss_core/`. Keep CLIs `argparse`-based and prefer small helpers over large inline blocks. Bash scripts should start with `#!/bin/bash` and `set -euo pipefail`. Use descriptive filenames such as `test_bfd_jlink_hss_core.py` or `bfd_jlink_hss.sh`.

## Testing Guidelines

Add or update `pytest` coverage for every behavior change in `scripts/` or `scripts/bfd_jlink_hss_core/`. Name tests `test_<behavior>.py` and keep hardware-facing tests deterministic by stubbing J-Link interactions with `monkeypatch`, following the existing suite. Run `python3 -m pytest scripts/tests -q` before opening a PR.

## Commit & Pull Request Guidelines

History follows short Conventional Commit subjects such as `feat(hss): ...`, `docs(readme): ...`, and `sync: ...`. Prefer `type(scope): summary` when a scope is clear. PRs should include the purpose, affected paths, verification commands, and any hardware impact. If a change alters CLI output or debug artifacts, include a sample log, CSV, or JSON snippet instead of a screenshot.

## Environment & Maintenance Notes

The toolkit is tuned for Ubuntu 22.04. Do not hardcode workstation-specific absolute paths in docs, prompts, or scripts. Keep Codex and Claude skill trees synchronized, and treat `.runtime/venv` and generated `.codex/bfd/` profile files as build artifacts, not hand-edited source.

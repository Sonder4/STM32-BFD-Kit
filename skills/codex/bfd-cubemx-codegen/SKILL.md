---
name: bfd-cubemx-codegen
description: Use when a project already has a valid STM32CubeMX .ioc file and the goal is to regenerate CubeMX-managed code in place without changing clock, pin, peripheral, or toolchain configuration.
---

# BFD CubeMX Codegen

Use this skill to regenerate STM32CubeMX-managed project files from an existing `.ioc` only.

## Quick Start

1. Pass `--ioc` or `--project-root`.
2. Use a repository-local log directory.
3. Check the report and confirm the `.ioc` hash stayed unchanged.

## Core Commands

```bash
python3 scripts/generate_from_ioc.py \
  --ioc example_stm32h7.ioc \
  --cubemx $STM32CUBEMX_PATH \
  --log-dir logs/skills
```

```bash
python3 scripts/generate_from_ioc.py \
  --project-root . \
  --log-dir logs/skills
```

## Workflow

1. Locate the `.ioc` file and `STM32CubeMX` executable.
2. Hash the `.ioc` file before generation.
3. Emit a temporary read-only CubeMX command file.
4. Run CubeMX headless and store logs in the repository.
5. Hash the `.ioc` again and fail if it changed.

## Hard Rules

- Do not edit `.ioc` files in this skill.
- Do not emit CubeMX commands that change configuration.
- Do not use this skill to create new projects or enable peripherals.
- Keep final logs and reports under `logs/skills/`.

## Outputs

- `logs/skills/cubemx_codegen_*.log`
- `logs/skills/cubemx_codegen_*.md`

## Scripts

- `scripts/generate_from_ioc.py`

## References

- `references/readonly-boundary.md`

## Related Skills

- `bfd-ioc-parser`
- `bfd-project-init`
- `rscf-a-hal-editor`

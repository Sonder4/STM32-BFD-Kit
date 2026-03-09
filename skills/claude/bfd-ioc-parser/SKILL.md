---
name: bfd-ioc-parser
description: Use when parsing STM32CubeMX .ioc files to extract hardware configuration and generate structured JSON outputs for review or downstream analysis.
---

# BFD IOC Parser

Use this skill to parse `.ioc` files and produce normalized configuration artifacts.

## Quick Start

1. Use CLI only.
2. Parse one `.ioc` file or scan a directory.
3. Store outputs in a repository path.

## Core Commands

```bash
# Scan current directory
python3 ./.codex/skills/bfd-ioc-parser/scripts/parse_ioc.py --scan .
```

```bash
# Recursive scan
python3 ./.codex/skills/bfd-ioc-parser/scripts/parse_ioc.py --scan ./example_projects --recursive
```

```bash
# Parse a specific ioc file
python3 ./.codex/skills/bfd-ioc-parser/scripts/parse_ioc.py --ioc ./example_projects/example_stm32_project/example_stm32h7.ioc
```

```bash
# Parse with explicit output directory
python3 ./.codex/skills/bfd-ioc-parser/scripts/parse_ioc.py --ioc example_stm32h7.ioc --output ./logs/ioc_json
```

## Workflow

1. Locate `.ioc` file(s).
2. Parse and generate JSON artifacts.
3. Validate generated files before downstream use.

## Outputs

- `summary.json`
- `clock_config.json`
- `gpio_config.json`
- peripheral-specific config JSON files

## Hard Rules

- Do not modify `.ioc` files in this skill.
- Keep final outputs inside the repository.
- Use explicit output paths for reproducibility.

## Scripts

- `.codex/skills/bfd-ioc-parser/scripts/parse_ioc.py`
- `.codex/skills/bfd-ioc-parser/scripts/analyze_startup.py`

## References

- `.codex/skills/bfd-ioc-parser/references/ioc_format.md`
- `.codex/skills/bfd-ioc-parser/references/memory_map_stm32h723.md`

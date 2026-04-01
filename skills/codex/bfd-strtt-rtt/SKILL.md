---
name: bfd-strtt-rtt
description: Use when capturing SEGGER RTT over ST-Link via memory polling, or when implementing and diagnosing strtt-style RTT control-block scanning and ring-buffer polling.
---

# BFD STRTT RTT

Use this skill for polling-based ST-Link RTT workflows inspired by `strtt`. This skill is independent from J-Link RTT and independent from J-Link HSS.

## Quick Start

```bash
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
```

```bash
python3 BFD-Kit/scripts/bfd_stlink_rtt.py \
  --elf "${STM32_ELF}" \
  --role boot \
  --duration 5 \
  --output logs/rtt/stlink_rtt.log
```

## Core Pattern

- Resolve `_SEGGER_RTT` from ELF when possible.
- Fall back to scanning `STM32_RTT_SCAN_WINDOW` for `"SEGGER RTT"`.
- Parse `SEGGER_RTT_CB` and buffer descriptors.
- Poll unread bytes from the selected up-buffer.
- Write back `RdOff` after host-side consumption.

## Hard Rules

- This path is RTT polling, not HSS.
- Prefer it for textual boot/diag/runtime evidence, not for high-rate scalar sampling.
- If no usable payload is captured, fall back to `bfd-data-acquisition`.
- If the probe is J-Link, use `bfd-rtt-logger` for native J-Link RTT instead of this skill.

## Related Skills

- `bfd-rtt-logger`
- `bfd-stlink-interface`
- `bfd-data-acquisition`

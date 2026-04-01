---
name: bfd-stlink-interface
description: Use when flashing, reading memory, writing memory, or starting debug sessions through ST-Link tools such as STM32_Programmer_CLI or ST-LINK_gdbserver, especially when J-Link-specific commands do not apply.
---

# BFD ST-Link Interface

Use this skill for ST-Link-specific probe control. This skill is independent from J-Link and does not describe HSS flows.

## Quick Start

```bash
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
```

```bash
/opt/st/stm32cubeclt_1.19.0/STM32CubeProgrammer/bin/STM32_Programmer_CLI -l stlink
```

```bash
python3 BFD-Kit/skills/codex/bfd-flash-programmer/scripts/stlink_flash.py --firmware "${STM32_HEX}"
```

## Core Commands

```bash
# Connect and identify target
STM32_Programmer_CLI -c port=SWD mode=UR reset=HWrst freq="${STM32_SPEED_KHZ}"
```

```bash
# Read memory
STM32_Programmer_CLI -c port=SWD mode=UR reset=HWrst freq="${STM32_SPEED_KHZ}" -r32 0x20000000 4
```

```bash
# Write memory
STM32_Programmer_CLI -c port=SWD mode=UR reset=HWrst freq="${STM32_SPEED_KHZ}" -w32 0x20000000 0x12345678 -nv
```

```bash
# Start ST-Link GDB server
ST-LINK_gdbserver -p 61234 -m 1
```

## Hard Rules

- Use `freq=<kHz>` for `STM32_Programmer_CLI` SWD connections; do not use `speed=<kHz>`.
- Lock the probe by serial number when multiple ST-Links may be connected.
- Treat ST-Link memory access as polling/snapshot style access, not as an HSS-equivalent path.
- Keep ST-Link guidance separate from J-Link-only flows.

## Related Skills

- `bfd-flash-programmer`
- `bfd-debug-interface`
- `bfd-strtt-rtt`

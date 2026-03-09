# STM32 Bootstrap File Matrix

## Required (Blocker if missing)

- `.ioc`
- startup assembly (`startup_stm32*.s`)
- linker script (`*.ld` or `*.sct`)
- SVD file (`*.svd`)
- MCU family/device resolved from ioc

## Recommended (Warning if missing)

- build artifact `.elf`
- build artifact `.hex`
- build artifact `.map`
- OpenOCD/J-Link cfg (`*.cfg`)
- `build_tools/jlink/{flash.jlink,debug.jlink,rtt.jlink}`

## Family Defaults

- `STM32F4`
  - RTT scan window: `0x20000000:0x00030000`
- `STM32H7`
  - RTT scan window: `0x24000000:0x00080000`

## Apply Mode Behavior

- `--mode apply --apply` creates missing baseline files from `.codex/stm32/templates/<family>/`.
- Existing files are preserved unless `--force` is set.

---
name: bfd-flash-programmer
description: Use when flashing STM32 firmware, verifying flash results, diagnosing download failures, or running repeatable CLI-based flash workflows.
---

# BFD Flash Programmer

## Self-Improvement Loop (Required)

- When this skill encounters a build, flash, debug, script-usage, or other workflow problem, do not stop at the local workaround after the issue is solved.
- Record the resolved issue and lesson in `BFD-Kit/.learnings/ERRORS.md` and/or `BFD-Kit/.learnings/LEARNINGS.md`; unresolved capability gaps go to `BFD-Kit/.learnings/FEATURE_REQUESTS.md`.
- Promote reusable fixes into the affected BFD-Kit asset in the same task when feasible: update the relevant `SKILL.md`, script, wrapper, or resource so the next run benefits by default.
- When a learning is promoted into a skill or script, append a short entry to `BFD-Kit/.learnings/CHANGELOG.md` and mention the improvement in the task close-out.

Use this skill for deterministic flash and verification workflows.

## Quick Start

1. Generate bootstrap profile first.
2. Confirm `STM32_DEVICE/STM32_ELF` in profile.
3. Flash and keep logs under `logs/flash/`.

## Core Commands

```bash
# 0) Bootstrap profile (required)
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
```

```bash
# 0a) Nested subproject case: current cwd is the firmware subproject, but .codex lives in a shared workspace root
python3 /abs/path/to/.codex/skills/bfd-project-init/scripts/bootstrap.py \
  --project-root /abs/path/to/firmware_subproject \
  --mode check
```

```bash
# 1) Project standard flash flow
bash ./build_tools/jlink/flash.sh | tee logs/flash/flash_$(date +%Y%m%d_%H%M%S).log
```

```bash
# 2) Optional build-dir override
bash ./build_tools/jlink/flash.sh builds/gcc/debug | tee logs/flash/flash_builddir_$(date +%Y%m%d_%H%M%S).log
```

```bash
# 3) Python wrapper with explicit override
python3 ./.codex/skills/bfd-flash-programmer/scripts/jlink_flash.py \
  --firmware "${STM32_HEX}" \
  --device "${STM32_DEVICE}" \
  --address 0x08000000
```

```bash
# 4) DAPLink / CMSIS-DAP fallback through PyOCD
python3 BFD-Kit/scripts/bfd_pyocd_flash.py \
  --firmware "${STM32_HEX}" \
  --target stm32h723xx \
  --uid "<cmsis-dap-uid>" \
  --frequency 100000 \
  --force-program \
  --log-dir logs/flash \
  --log-prefix pyocd_flash
```

```bash
# 5) FanX/Tek DAPLink High probe firmware update on Linux (dry-run by default)
python3 BFD-Kit/scripts/bfd_fanx_daplink_update.py info \
  --firmware .tools/FanX_Tek_DAPLink_High1_V261.bin \
  --updater-zip .tools/FanX_Tek_DAPLink_Updater_V0.0.2.zip

python3 BFD-Kit/scripts/bfd_fanx_daplink_update.py update \
  --firmware .tools/FanX_Tek_DAPLink_High1_V261.bin

# Add --execute only after confirming the detected DAPLINK/BOOTLOADER mount.
python3 BFD-Kit/scripts/bfd_fanx_daplink_update.py update \
  --firmware .tools/FanX_Tek_DAPLink_High1_V261.bin \
  --execute
```

```bash
# 6) Fallback when the project copy does not ship build_tools/jlink/flash.sh
printf "device ${STM32_DEVICE}\nsi ${STM32_IF}\nspeed ${STM32_SPEED_KHZ}\nconnect\nr\nloadfile ${STM32_HEX}\nr\ng\nexit\n" \
  | JLinkExe | tee logs/flash/flash_jlink_direct_$(date +%Y%m%d_%H%M%S).log
```

## Workflow

1. Run bootstrap profile.
2. Connect and identify device.
3. Program and verify.
4. Reset and validate runtime logs.

## Hard Rules

- Fail-fast if bootstrap profile is missing.
- Save final flash logs under `logs/flash/`.
- Always run verification after programming.
- Do not erase before confirming exact device model.
- If the target firmware lives in a nested subproject but `.codex/skills/...` is provided by a higher-level shared workspace root, do not run `./.codex/...` from the subproject cwd. Invoke the bootstrap or wrapper script via the actual skill path, or switch cwd to the workspace root that really contains `.codex`, while keeping `--project-root` pointed at the firmware subproject.
- If `./build_tools/jlink/flash.sh` returns `Permission denied`, rerun it via `bash ./build_tools/jlink/flash.sh` instead of assuming probe or flash tool failure.
- If `./build_tools/jlink/flash.sh` is absent in the target project copy, do not stop on the missing wrapper. Fall back to direct `JLinkExe` flashing with `STM32_DEVICE`, `STM32_IF`, `STM32_SPEED_KHZ`, and `STM32_HEX` from the bootstrap profile.
- If the wrapper or `JLinkExe -USB <configured_sn>` reports `Connecting to J-Link via USB...FAILED`, but plain `JLinkExe` or `ShowEmuList USB` can still see a probe, treat it as a stale fixed probe serial binding first. Compare the configured S/N with the actually enumerated S/N, then retry with `JLINK_SN=<actual_sn>` before assuming target-side SWD failure.
- If a FanX/Tek DAPLink High or another CMSIS-DAP probe enumerates as `0d28:0204` and `pyocd list` sees it, prefer the PyOCD fallback above for download evidence. PyOCD vector readback is stronger evidence than drag-and-drop HEX, because drag-and-drop can leave the copied file visible even when target programming did not occur.
- If OpenOCD reports `CMSIS-DAP: SWD not supported` with a DAPLink probe, treat old OpenOCD compatibility as a tool-path hypothesis first. Verify with current PyOCD before concluding the STM32 board or SWD wiring is bad.
- For FanX/Tek DAPLink High probe firmware updates on Linux, use the official mass-storage flow instead of running the Windows updater under Wine: copy empty `START_BL.ACT` to the `DAPLINK` volume, wait for `BOOTLOADER`, then copy the encrypted `FanX_Tek_DAPLink_High1_V261.bin` to `BOOTLOADER`. The BFD wrapper never writes by default; require explicit `--execute` before touching the probe firmware.
- Do not treat `FanX_Tek_DAPLink_High1_V261.bin` as a raw MCU image. It is an encrypted interface-firmware package consumed by the FanX bootloader, so do not flash it with PyOCD/OpenOCD/J-Link to a target address.

## Scripts

- `./build_tools/jlink/flash.sh`
- `BFD-Kit/scripts/bfd_pyocd_flash.py`
- `BFD-Kit/scripts/bfd_fanx_daplink_update.py`
- `.codex/skills/bfd-flash-programmer/scripts/jlink_flash.py`
- `.codex/skills/bfd-flash-programmer/scripts/stlink_flash.py`

## Related Skills

- `bfd-project-init`
- `bfd-rtt-logger`
- `bfd-debug-interface`
- `verification-before-completion`

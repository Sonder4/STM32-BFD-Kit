---
name: bfd-ozone
description: Use when preparing, auditing, repairing, or launching SEGGER Ozone STM32 debug projects (.jdebug / .jdebug.user). Trigger this skill when Ozone shows stale Windows paths, wrong ELF/SVD/device/interface settings, missing FreeRTOS awareness, duplicated case-variant project files, stale fixed J-Link serial bindings, or when a user wants a ready-to-debug Ozone session opened from the current STM32 project.
---

# BFD Ozone

## Overview

Use this skill to normalize SEGGER Ozone project files against the active STM32 bootstrap profile and open Ozone with a clean, current project configuration.

Prefer generating canonical `.jdebug` / `.jdebug.user` files from the active project profile instead of hand-editing stale Ozone exports line by line.

## Self-Improvement Loop (Required)

- When this skill encounters a build, flash, debug, script-usage, or other workflow problem, do not stop at the local workaround after the issue is solved.
- Record the resolved issue and lesson in `BFD-Kit/.learnings/ERRORS.md` and/or `BFD-Kit/.learnings/LEARNINGS.md`; unresolved capability gaps go to `BFD-Kit/.learnings/FEATURE_REQUESTS.md`.
- Promote reusable fixes into the affected BFD-Kit asset in the same task when feasible: update the relevant `SKILL.md`, script, wrapper, or resource so the next run benefits by default.
- When a learning is promoted into a skill or script, append a short entry to `BFD-Kit/.learnings/CHANGELOG.md` and mention the improvement in the task close-out.

## Required Precheck

Run bootstrap before touching any Ozone project:

```bash
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
```

Fail fast if the active profile is missing, or if `${STM32_ELF}` does not resolve to a real file.

## Canonical Workflow

1. Run bootstrap and read `.codex/bfd/active_profile.env`.
2. Enumerate the current J-Link probe with `JLinkExe` before touching `.jdebug`.
3. Inspect the existing `.jdebug` / `.jdebug.user` pair.
4. Look for obvious drift:
   - stale Windows path substitutes
   - wrong `Project.SetDevice()`
   - wrong `Project.SetTargetIF()` such as `JTAG` on an SWD project
   - wrong ELF path
   - fixed `Project.SetHostIF("USB", "<old-sn>")`
   - missing `Project.SetOSPlugin("FreeRTOSPlugin_Cortex-M")` on a FreeRTOS project
   - duplicated case-variant project files such as `RSCF_A.jdebug` and `rscf_a.jdebug`
5. Regenerate canonical files with `scripts/prepare_ozone_project.py`.
6. Launch Ozone with `scripts/launch_ozone.sh`.

## Canonical Generation

Primary helper:

```bash
python3 scripts/prepare_ozone_project.py \
  --project-root . \
  --jdebug RSCF_A.jdebug \
  --user-file RSCF_A.jdebug.user \
  --rewrite-user \
  --open-doc Core/Src/main.c:1 \
  --open-doc USER/APP/robot.c:1 \
  --watch chassis_parameter:5:DISPLAY_FORMAT_DEC
```

The helper renders a canonical `.jdebug` from the active bootstrap profile and can also generate a curated `.jdebug.user` with project-specific open documents and watched expressions.

Before writing the file, it enumerates the current J-Link probe through `JLinkExe ShowEmuList` and, by default, binds the generated `.jdebug` to the currently visible probe serial number.

## FreeRTOS Awareness Popup

If Ozone shows a dialog like:

`The target application seems to be using FreeRTOS, but FreeRTOS awareness is not enabled`

then the target most likely contains FreeRTOS symbols, but the loaded `.jdebug` project is missing:

```js
Project.SetOSPlugin ("FreeRTOSPlugin_Cortex-M");
```

Treat this as an Ozone project configuration problem, not as a firmware fault.

## Probe Binding Rule

Before every Ozone preparation run, enumerate the currently visible J-Link probe first.

Default behavior in this skill is now:

- `prepare_ozone_project.py` auto-runs `JLinkExe -> ShowEmuList`
- if exactly one probe is visible, write that current serial into `Project.SetHostIF("USB", "<current-sn>")`
- if multiple probes are visible, require `JLINK_SN=<serial>` or `--host-sn <serial>`
- if `JLinkExe` probe enumeration hangs or no probe is visible, fail fast before launching Ozone

Only keep `Project.SetHostIF("USB", "")` when the user explicitly asks to preserve a blank binding for portability.

## Launch

Use:

```bash
bash scripts/launch_ozone.sh RSCF_A.jdebug
```

If the user wants Ozone opened from this session, remember that launching a GUI app usually needs explicit user approval in the terminal harness.

## References

- `references/ozone-project-rules.md`
- `scripts/prepare_ozone_project.py`
- `scripts/launch_ozone.sh`

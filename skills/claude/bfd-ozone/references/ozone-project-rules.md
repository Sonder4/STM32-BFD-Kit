# Ozone Project Rules

## Canonical `.jdebug`

Use the active bootstrap profile as the source of truth for:

- target device
- target interface
- debug speed
- ELF path
- SVD path

Do not keep stale values exported from another machine or another board.

## Common Drift Patterns

### 1. Wrong path substitutes

Typical symptom:

- `Project.AddPathSubstitute("E:/...")`
- `.jdebug.user` opens `E:/...` files that no longer exist

Fix:

- replace with the current project root
- regenerate `.jdebug.user` instead of editing dozens of stale entries by hand

### 2. Wrong target interface

Typical symptom:

- `Project.SetTargetIF("JTAG")` on a project that is actually wired for SWD

Fix:

- follow `STM32_IF` from the bootstrap profile

### 3. Wrong device

Typical symptom:

- generic `Cortex-M4` instead of the real STM32 device

Fix:

- use the exact MCU device from the active profile, for example `STM32F427II`

### 4. Wrong ELF path

Typical symptom:

- path still points at a deleted IDE build directory such as `cmake-build-debug-*`

Fix:

- point Ozone to the active bootstrap ELF, usually `builds/gcc/debug/<name>.elf`

### 5. FreeRTOS popup

Typical symptom:

- Ozone reports that the target seems to use FreeRTOS but awareness is not enabled

Fix:

- add `Project.SetOSPlugin("FreeRTOSPlugin_Cortex-M");`

### 6. Probe enumeration and binding

Before regenerating `.jdebug`, enumerate the current J-Link probe first.

Required behavior:

- run `JLinkExe` with `ShowEmuList`
- if exactly one probe is visible, bind that serial into `Project.SetHostIF("USB", "<current-sn>")`
- if multiple probes are visible, require `JLINK_SN=<serial>` or an explicit `--host-sn`
- if `JLinkExe` hangs or no probe is visible, stop and treat it as a host/probe problem before blaming Ozone project fields

Only keep a blank host serial when the user explicitly asks for a portable, non-bound project.

### 7. Stale fixed J-Link serial binding

Typical symptom:

- `.jdebug` contains `Project.SetHostIF("USB", "<old-sn>")`
- Ozone opens but cannot attach on a different probe

Fix:

- re-enumerate the currently visible probe and rewrite the host serial to that current S/N

### 8. Case-variant duplicates

Typical symptom:

- both `RSCF_A.jdebug` and `rscf_a.jdebug` exist and contain different settings

Fix:

- pick one canonical file name
- if compatibility copies are needed, make them content-identical

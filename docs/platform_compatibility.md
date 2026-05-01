# Platform Compatibility Guide

## Goal

BFD-Kit keeps one STM32 workflow across Ubuntu and Windows hosts by normalizing tool discovery around `STM32CubeCLT`, explicit workspace tool config, and project-profile detection.

- Supported host focus: `linux`, `windows`
- Supported build lanes: `STM32CubeCLT`, `GCC`, `Keil`
- Intentionally not supported in this revision: `IAR`

## Canonical Helpers

- `scripts/bfd_tool_config.py`
  - Persist workspace or global tool paths
  - Detect common executables from `PATH` and `STM32CubeCLT`
- `scripts/bfd_project_detect.py`
  - Detect build system, toolchain, target MCU, STM32 family, `.ioc`, and artifact candidates

Recommended bootstrap order:

1. Detect tool paths on the current host
2. Persist any host-specific overrides
3. Detect the target STM32 project
4. Build or flash with the detected profile

Preferred bootstrap command when moving between Ubuntu and Windows:

```bash
python3 BFD-Kit/scripts/bfd_install.py \
  --project-root /path/to/project \
  --detect-tools \
  --bootstrap-profile
```

## STM32CubeCLT Root Conventions

Common roots used by BFD-Kit detection:

- Linux:
  - `/opt/st/stm32cubeclt`
  - `/opt/STM32CubeCLT`
- Windows:
  - `D:\STM32CubeCLT`
  - `C:\ST\STM32CubeCLT`

Override rules:

- Environment override: `STM32CUBECLT_ROOT`
- Workspace override: `python3 scripts/bfd_tool_config.py set stm32cubeclt_root <path> --workspace <project>`
- Global override: `python3 scripts/bfd_tool_config.py set stm32cubeclt_root <path> --global`

## Executable Naming Differences

Typical executable names handled by `bfd_tool_config.py`:

- `STM32_Programmer_CLI` / `STM32_Programmer_CLI.exe`
- `ST-LINK_gdbserver` / `ST-LINK_gdbserver.exe`
- `JLinkExe` / `JLink.exe`
- `JLinkGDBServerCLExe` / `JLinkGDBServerCL.exe`
- `UV4` / `UV4.exe`
- `arm-none-eabi-gcc`
- `arm-none-eabi-gdb`
- `cmake`
- `ninja`

Windows-specific notes:

- Always assume `.exe` suffixes may be required
- Paths can contain spaces; quote them explicitly
- Backslashes are accepted by native tools, but BFD-Kit should not assume one slash style in persisted paths

Linux-specific notes:

- USB probe access often depends on group membership or udev rules
- Serial ports usually appear as `/dev/ttyACM*` or `/dev/ttyUSB*`

## Recommended Commands

Detect tools from the current host:

```bash
python3 scripts/bfd_tool_config.py detect --write --workspace /path/to/project
```

Inspect persisted tool paths:

```bash
python3 scripts/bfd_tool_config.py list --workspace /path/to/project
python3 scripts/bfd_tool_config.py path --workspace /path/to/project
```

Detect a project profile:

```bash
python3 scripts/bfd_project_detect.py --workspace /path/to/project --json
```

## Ubuntu -> Windows Migration Checklist

When moving an STM32 project from Ubuntu to Windows, check these items in order:

1. Regenerate the host tool config on Windows instead of copying Linux paths blindly
2. Re-run `bfd_project_detect.py` on Windows to refresh the project profile
3. Replace hard-coded Unix paths like `/tmp/...`, `/opt/...`, or `/dev/ttyACM0`
4. Check custom CMake commands for shell-only syntax, especially `tee`, `cp`, `rm`, and Bash-only quoting
5. Verify commands that invoke `armasm.exe`, `JLink.exe`, or `STM32_Programmer_CLI.exe`
6. Re-check path case sensitivity; Windows may hide collisions that Linux exposed
7. Confirm `cmake` and `ninja` come from the intended `STM32CubeCLT` installation
8. Re-check serial port names and probe-driver binding on Windows

Common build breaks to audit early:

- `CMakePresets.json` or local scripts still point at Linux-only generators, shell wrappers, or absolute toolchain files
- custom commands assume `/bin/sh`, `chmod`, symbolic links, or executable bits
- source files or scripts embed `/dev/tty*`, `/media/<user>/...`, or `/opt/st/...` paths
- Windows path spaces break unquoted `JLink.exe`, `STM32_Programmer_CLI.exe`, or `armasm.exe` invocations
- mixed `CRLF/LF` and case-only filename differences confuse generated-file reuse or incremental builds
- copied Keil or CubeMX artifacts still reference an older Linux build directory

## Build Guidance

- Prefer `STM32CubeCLT + CMake + Ninja` as the shared build lane across Ubuntu and Windows
- Keep `Keil` support only for legacy project inspection or compatibility needs
- Do not expand new `IAR` workflows in this repository

## Telemetry / Debug Notes

- For high-rate memory capture, keep probe selection explicit in the project profile
- `telemetry ring` workflows should prefer incremental record reads over whole-image reads when the host backend supports it
- When comparing `J-Link` and `DAPLink`, report the exact probe model and exact date because host-side behavior is probe-dependent

# Platform Validation Record (2026-05-02)

## Scope

This record captures the latest cross-platform evidence for the `STM32CubeCLT` convergence work in `BFD-Kit`.

It intentionally separates:

- Ubuntu evidence that was executed on a real host and target project
- Windows evidence that is currently limited to static path/command validation and unit-test coverage

This file is a validation record, not a claim that a Windows host flash/build cycle has already been executed end-to-end.

## Ubuntu Actual Validation

Target project:

- `/home/xuan/RC2026/PC/rc26-nav2/RSCF_A/RSCF_h7`

True-source toolkit:

- `/home/xuan/RC2026/STM32/BFD-Kit`

Commands executed on Ubuntu:

```bash
python3 /home/xuan/RC2026/STM32/BFD-Kit/scripts/bfd_cubeclt_build.py --json inspect --workspace /home/xuan/RC2026/PC/rc26-nav2/RSCF_A/RSCF_h7 --preset Debug --require-triplet
python3 /home/xuan/RC2026/STM32/BFD-Kit/scripts/bfd_cubeclt_build.py --json build --workspace /home/xuan/RC2026/PC/rc26-nav2/RSCF_A/RSCF_h7 --preset Debug --configure-if-needed --require-triplet --dry-run
python3 /home/xuan/RC2026/STM32/BFD-Kit/scripts/bfd_tool_config.py resolve stm32cubeprogrammer_cli --workspace /home/xuan/RC2026/PC/rc26-nav2/RSCF_A/RSCF_h7
python3 /home/xuan/RC2026/STM32/BFD-Kit/scripts/bfd_tool_config.py resolve stlink_gdb_server --workspace /home/xuan/RC2026/PC/rc26-nav2/RSCF_A/RSCF_h7
python3 /home/xuan/RC2026/STM32/BFD-Kit/scripts/bfd_repo_validate.py --root /home/xuan/RC2026/STM32/BFD-Kit
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest /home/xuan/RC2026/STM32/BFD-Kit/scripts/tests/test_bfd_tool_config.py /home/xuan/RC2026/STM32/BFD-Kit/scripts/tests/test_bfd_project_detect.py /home/xuan/RC2026/STM32/BFD-Kit/scripts/tests/test_bfd_cubeclt_build.py /home/xuan/RC2026/STM32/BFD-Kit/scripts/tests/test_bfd_repo_validate.py -q
```

Observed Ubuntu results:

- `bfd_cubeclt_build.py inspect` correctly detected `Debug` preset and `RSCF_H7_BOARD_ONE.elf/.hex/.bin`
- `bfd_cubeclt_build.py build --dry-run` resolved the build lane to:
  - `/opt/st/stm32cubeclt_1.21.0/CMake/bin/cmake --build --preset Debug`
- `bfd_tool_config.py resolve stm32cubeprogrammer_cli` returned:
  - `/opt/st/stm32cubeclt_1.21.0/STM32CubeProgrammer/bin/STM32_Programmer_CLI`
- `bfd_tool_config.py resolve stlink_gdb_server` returned:
  - `/opt/st/stm32cubeclt_1.21.0/STLink-gdb-server/bin/ST-LINK_gdbserver`
- `bfd_repo_validate.py` passed
- current targeted test suite passed:
  - `20 passed`

Interpretation:

- Ubuntu path discovery, preset resolution, artifact bundle detection, and shared `STM32CubeCLT` command construction are verified on a real host.

## Windows Static Validation

What is covered right now:

- `.exe` tool discovery for:
  - `cmake.exe`
  - `ninja.exe`
  - `arm-none-eabi-gcc.exe`
  - `arm-none-eabi-gdb.exe`
  - `arm-none-eabi-objcopy.exe`
  - `STM32_Programmer_CLI.exe`
  - `ST-LINK_gdbserver.exe`
- versioned Windows `STM32CubeCLT` root discovery such as `STM32CubeCLT_1.21.0`
- `cmake.exe --preset Debug`
- `cmake.exe --build --preset Debug`

Evidence sources:

- `scripts/tests/test_bfd_tool_config.py`
  - `test_detect_default_tools_finds_windows_cubeclt_binaries_from_root`
  - `test_detect_default_tools_accepts_versioned_windows_cubeclt_root`
- `scripts/tests/test_bfd_cubeclt_build.py`
  - `test_build_commands_preserve_resolved_cmake_exe_path`

Interpretation:

- The current code now has explicit automated coverage for Windows executable naming and versioned-root path resolution.
- This removes a large class of migration ambiguity without requiring a separate code path.

## Current Limit

The following item is still not covered by direct evidence in this session:

- a real Windows host executing configure/build/export/flash against an STM32 project

Therefore the current state is:

- Ubuntu actual validation: complete
- Windows static/tooling validation: complete
- Windows real-host execution validation: pending

## Recommended Next Step On A Real Windows Host

When a Windows machine is available, run:

```powershell
python BFD-Kit\scripts\bfd_tool_config.py detect --write --workspace .
python BFD-Kit\scripts\bfd_cubeclt_build.py --json inspect --workspace . --preset Debug --require-triplet
python BFD-Kit\scripts\bfd_cubeclt_build.py --json build --workspace . --preset Debug --configure-if-needed --require-triplet --dry-run
python BFD-Kit\scripts\bfd_repo_validate.py --root BFD-Kit
```

Then record:

- resolved `cmake.exe` / `ninja.exe` / `STM32_Programmer_CLI.exe`
- actual preset resolution
- artifact triplet status
- whether a real flash lane also succeeds on that host

# BFD-Kit: AI STM32 Debug Toolkit

[简体中文](README-zh.md) | [English](README-en.md)

BFD-Kit is a portable, CLI-first toolkit for AI-assisted STM32 debug workflows.
It standardizes IOC discovery, active profile generation, flashing, RTT logging, register/data capture, and fault evidence collection.
中文概要：BFD-Kit 面向 `STM32F4/STM32H7`，强调 `CLI + STM32CubeCLT + 可归档证据` 的统一调试/采集工作流。

## Project Note

- This project leverages [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) to drive CLI-based handling for J-Link related workflows.
- ST-Link support is split by capability: flash and RTT polling are supported, but there is no ST-Link equivalent of native J-Link HSS in this revision.
- The toolkit still validates fastest on Ubuntu 22.04, but this revision also adds Windows/Linux path normalization around `STM32CubeCLT`.
- `BFD-Kit/scripts/bfd_tool_config.py` and `BFD-Kit/scripts/bfd_project_detect.py` are the new cross-platform entry points for host tool discovery and STM32 project profiling.
- `Keil` compatibility is retained; `IAR` is intentionally not carried forward in this repository revision.

## Scope

- Target families bundled now: `STM32F4`, `STM32H7`
- Agent targets: Codex + Claude
- Canonical source tree: `BFD-Kit/skills/{codex,claude}/bfd-*`
- Runtime profile directory: `.codex/bfd/`
- Legacy compatibility mirror: `.codex/stm32/bootstrap/`

## Directory Layout

- `BFD-Kit/skills/codex/`: canonical Codex skill pack
- `BFD-Kit/skills/claude/`: canonical Claude skill pack
- `BFD-Kit/resources/stm32/templates/`: family templates (`f4/`, `h7/`)
- `BFD-Kit/resources/stm32/telemetry_ring/`: family-agnostic MCU telemetry ring templates for `STM32F4` / `STM32H7`
- `BFD-Kit/init_project.sh`: one-command project onboarding entry
- `BFD-Kit/scripts/bfd_install.py`: cross-platform Python installer for copy/cutover/tool-detect/profile-bootstrap flows
- `BFD-Kit/scripts/bfd_jlink_hss.sh`: native J-Link HSS wrapper with managed Python runtime
- `BFD-Kit/scripts/bfd_pyocd_hss.py`: DAPLink / CMSIS-DAP fixed-address sampler with float-count benchmarking
- `BFD-Kit/scripts/bfd_telemetry_ring.py`: generic telemetry-ring sizing and PyOCD capture utility
- `BFD-Kit/scripts/bfd_tool_config.py`: workspace/global tool-path registry with `STM32CubeCLT` discovery
- `BFD-Kit/scripts/bfd_project_detect.py`: STM32 project metadata detector for `CMake`, `Keil`, `.ioc`, and artifact candidates
- `BFD-Kit/scripts/bfd_stlink_rtt.py`: polling-based ST-Link RTT capture built on `STM32_Programmer_CLI`
- `BFD-Kit/docs/platform_compatibility.md`: Ubuntu/Windows migration notes and tool-path conventions
- `BFD-Kit/.runtime/venv`: local Python runtime installed on demand for portable script execution
- `BFD-Kit/scripts/migrate_bfd_skills.py`: import/cutover utility
- `BFD-Kit/MAINTENANCE-zh.md`: maintainer-facing maintenance checklist

## Skill Set

- `bfd-project-init`: scan `.ioc`/startup/linker/svd/cfg/build artifacts and generate one active profile
- `bfd-ioc-parser`: parse `.ioc` and export structured JSON to `.codex/bfd/ioc_json/`
- `bfd-cubemx-codegen`: regenerate CubeMX-managed files from an existing `.ioc` in read-only mode
- `bfd-flash-programmer`: deterministic J-Link/ST-Link flash flow
- `bfd-rtt-logger`: runtime RTT capture and validation
- `bfd-stlink-interface`: ST-Link-only flash, memory, and GDB-server usage
- `bfd-strtt-rtt`: polling-based ST-Link RTT workflow modeled after `strtt`
- `bfd-debug-interface`: structured debug workflow and fault context handling
- `bfd-debug-executor`: one-shot J-Link command execution
- `bfd-register-capture`: peripheral register sampling/export
- `bfd-data-acquisition`: runtime data capture and analysis
- `bfd-fault-logger`: HardFault/BusFault/UsageFault archival
- `bfd-debug-orchestrator`: end-to-end debug campaign orchestration
- `bfd-user-feedback`: user-facing status/feedback hooks

Legacy overlapping STM32 skills are intended to be removed from active mirrors once the canonical `bfd-*` trees are staged and cut over.

`bfd-data-acquisition` also carries the reusable local-variable probe resource under `resources/local-probe/` for stack-variable sampling workflows.

## New in This Revision

- `bfd-data-acquisition` now supports generic `--mode symbol-auto`
- `bfd-data-acquisition` now includes a native J-Link HSS CLI path for non-halting fixed-address scalar sampling
- `bfd-data-acquisition` now also includes a DAPLink / PyOCD float-count benchmark path for answering "how many floats can stay at 1000 Hz"
- `symbol-auto` uses `ELF + DWARF` reflection to decode global/static objects without business-specific hardcoding
- DWARF schemas are cached under `.codex/bfd/dwarf_cache/` for reuse across repeated inspections
- RTT failure guidance now explicitly routes to RAM sampling instead of ad-hoc GDB/J-Link command design
- `bfd-debug-interface` and `bfd-rtt-logger` delegate structured symbol decoding to `bfd-data-acquisition`
- `bfd-rtt-logger` now includes a polling-based ST-Link RTT path built on `STM32_Programmer_CLI`
- probe capability boundaries are now explicit: ST-Link RTT is supported, but ST-Link has no HSS-equivalent path in this revision
- a reusable MCU telemetry-ring template is now bundled for `STM32F4` and `STM32H7`, together with a host-side decoder/capture CLI
- `bfd_telemetry_ring.py` now supports incremental ring-record reads and `--field-array prefix:type:count` for large float payload benchmarks
- `bfd_tool_config.py` and `bfd_project_detect.py` now provide the cross-platform base layer for `STM32CubeCLT`, `Keil`, and artifact detection

## Probe Capability Boundaries

- J-Link:
  - flash
  - RTT quick/dual
  - native HSS scalar sampling
  - one-shot J-Link command execution
- ST-Link:
  - flash
  - memory read/write through `STM32_Programmer_CLI`
  - polling-based RTT capture through `BFD-Kit/scripts/bfd_stlink_rtt.py`
  - no HSS-equivalent path in this revision

Keep ST-Link and `strtt`-style RTT usage in these dedicated skills rather than mixing them into J-Link-only skills.

Supported V1 reflected type families:

- `struct`
- `array`
- `pointer`
- `typedef`
- `enum`

Current recommendation:

- first choice: `symbol-auto` for any stable global/static symbol with usable DWARF
- second choice: `--mode symbol` with an explicit decode profile or layout
- last choice: raw address sampling or low-level debug commands

## Fast Init

Preferred cross-platform entry:

```bash
# Copy BFD-Kit into the target STM32 project, update active mirrors, detect host tools, and bootstrap the profile
python3 BFD-Kit/scripts/bfd_install.py \
  --project-root /path/to/your/stm32-project \
  --detect-tools \
  --bootstrap-profile

# Inspect the current install state later
python3 BFD-Kit/scripts/bfd_install.py --project-root /path/to/your/stm32-project --status
```

```bash
# One command: install/update BFD skills, refresh .codex/bfd profile, and prepare local Python runtime
bash BFD-Kit/init_project.sh --project-root .

# Optional modes
bash BFD-Kit/init_project.sh --project-root . --cutover-only
bash BFD-Kit/init_project.sh --project-root . --bootstrap-only --force-refresh
bash BFD-Kit/init_project.sh --project-root . --runtime-only
```

## Cross-Platform Setup

```bash
# Detect common host tools and persist them into the target workspace
python3 BFD-Kit/scripts/bfd_tool_config.py detect --write --workspace .

# Review the persisted tool map
python3 BFD-Kit/scripts/bfd_tool_config.py list --workspace .

# Detect the active STM32 project profile from .ioc / CMake / Keil artifacts
python3 BFD-Kit/scripts/bfd_project_detect.py --workspace . --json
```

Platform notes:

- shared Ubuntu/Windows guidance lives in `BFD-Kit/docs/platform_compatibility.md`
- `STM32CubeCLT` is the preferred shared toolchain lane
- `Keil` stays supported for compatibility; `IAR` does not
- `scripts/bfd_install.py` is the preferred Windows/Linux bootstrap entry when a Bash-first flow is inconvenient

## Standard Workflow

```bash
# 1) Generate/refresh the canonical runtime profile
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check

# 1.5) Optionally regenerate CubeMX-managed files from the current .ioc
python3 ./.codex/skills/bfd-cubemx-codegen/scripts/generate_from_ioc.py --project-root . --log-dir logs/skills

# 2) Flash
./build_tools/jlink/flash.sh builds/gcc/debug | tee logs/flash/flash_$(date +%Y%m%d_%H%M%S).log
# or
python3 BFD-Kit/skills/codex/bfd-flash-programmer/scripts/stlink_flash.py \
  --firmware "${STM32_HEX}"

# 3) RTT runtime log
./build_tools/jlink/rtt.sh logs/rtt/rtt_$(date +%Y%m%d_%H%M%S).log 5 --mode quick
# or, when STM32_PROBE=stlink
python3 BFD-Kit/scripts/bfd_stlink_rtt.py \
  --elf "${STM32_ELF}" \
  --role boot \
  --duration 5 \
  --output logs/rtt/stlink_rtt_$(date +%Y%m%d_%H%M%S).log

# 3.5) If RTT has no usable payload, switch to generic RAM decode
python3 ./.codex/skills/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --mode symbol-auto \
  --symbol <global_symbol> \
  --follow-depth 1 \
  --format summary \
  --output logs/data_acq/<global_symbol>.summary

# 3.6) For high-rate, non-halting scalar sampling, switch to native HSS
bash BFD-Kit/scripts/bfd_jlink_hss.sh --json hss sample \
  --symbol chassis_parameter.IMU.yaw \
  --symbol chassis_parameter.IMU.pitch \
  --duration 0.3 \
  --period-us 1000 \
  --output logs/data_acq/imu_yaw_pitch_hss.csv

# 3.7) For DAPLink / CMSIS-DAP throughput limits, benchmark contiguous float reads directly
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_pyocd_hss.py --json benchmark-float \
  --address 0x200096E8 \
  --min-floats 1 \
  --max-floats 32 \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 0.2 \
  --period-us 1000 \
  --output logs/data_acq/pyocd_float_benchmark.json

# 3.8) When host polling becomes the bottleneck, move the fast path into an MCU telemetry ring
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_telemetry_ring.py --json capture-pyocd \
  --address 0x24020000 \
  --field pos_rad:f32 \
  --field vel_rads:f32 \
  --field torque_nm:f32 \
  --field state:u32 \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 1.0 \
  --poll-period-us 1000 \
  --output logs/data_acq/app_ring_capture.csv

# 4) One-shot debug session
./build_tools/jlink/debug.sh | tee logs/debug/debug_$(date +%Y%m%d_%H%M%S).log
```

## Recommended Data-Acquisition Flow

```bash
# Generic global/static object decode
python3 ./.codex/skills/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --mode symbol-auto \
  --symbol g_object_state \
  --follow-depth 0 \
  --format summary

# Generic pointer-hub decode
python3 ./.codex/skills/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --mode symbol-auto \
  --symbol g_object_hub \
  --follow-depth 1 \
  --format json

# Manual fallback when DWARF auto reflection is not suitable
python3 ./.codex/skills/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --mode symbol \
  --symbol g_object_array \
  --count <N> \
  --decode-profile <profile_name> \
  --format csv

# Native J-Link HSS for one or more fixed-address scalar symbols
bash BFD-Kit/scripts/bfd_jlink_hss.sh --json hss sample \
  --symbol chassis_parameter.IMU.yaw \
  --symbol chassis_parameter.IMU.pitch \
  --duration 1 \
  --period-us 1000 \
  --output logs/data_acq/imu_yaw_pitch_hss.csv

# DAPLink / CMSIS-DAP benchmark: find the largest float count that still holds 1000 Hz
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_pyocd_hss.py --json benchmark-float \
  --address 0x200096E8 \
  --min-floats 1 \
  --max-floats 32 \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 0.2 \
  --period-us 1000 \
  --output logs/data_acq/pyocd_float_benchmark.json

# MCU telemetry ring capture when the control loop itself runs faster than host polling
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_telemetry_ring.py --json capture-pyocd \
  --address 0x24020000 \
  --field pos_rad:f32 \
  --field vel_rads:f32 \
  --field torque_nm:f32 \
  --field state:u32 \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 1.0 \
  --poll-period-us 1000 \
  --output logs/data_acq/app_ring_capture.csv
```

On `J-Link PLUS`, SEGGER's model limits and local HSS verification both indicate a 10-symbol ceiling. Do not treat `hss inspect` raw capability word 2 as the symbol-count limit. `hss sample` writes a synchronized wide CSV to `--output` and a metadata sidecar JSON to `--output.meta.json`.
This HSS path remains J-Link-only. The ST-Link backend in this revision does not provide an equivalent high-rate native sampler.
For DAPLink / PyOCD, the short board is still host-driven polling. Once a 1 kHz sweep can no longer hold the required float count, move the fast loop to the bundled MCU telemetry ring instead of trying to present host polling as native HSS.
Latest measured reference on `RSCF_h7` with FanX/Tek DAPLink High at `10 MHz` SWD: a single contiguous `float` reaches about `267 us` average update with `benchmark-float --period-us 0`; the best repeatable stable `1000 Hz` boundary is currently `53 floats / 212 B`; `55 floats` passed once but failed repeatability; the practical end-to-end host-polled path is currently in the `~0.2 MB/s` class, so a real `1 MB/s` target requires an MCU telemetry ring, USB bulk/CDC streaming, or custom probe-side sampling rather than more host-poll tuning.

## Runtime Profile Contract

- Canonical files:
  - `.codex/bfd/active_profile.json`
  - `.codex/bfd/active_profile.env`
  - `.codex/bfd/bootstrap_report.md`
  - `.codex/bfd/ioc_json/`
- Compatibility mirror:
  - `.codex/stm32/bootstrap/active_profile.json`
  - `.codex/stm32/bootstrap/active_profile.env`
- Auto-init:
  - `build_tools/jlink/profile_env.sh` calls `ensure_profile.py`
  - `rtt_plot_live.py` prefers `.codex/bfd/active_profile.env`
- Local runtime:
  - `BFD-Kit/.runtime/venv`
  - `BFD-Kit/scripts/install_python_runtime.sh` installs `pyelftools`
  - `BFD-Kit/scripts/bfd_jlink_hss.sh` uses the local runtime automatically

## Integrate Into an Existing Project

```bash
bash BFD-Kit/init_project.sh --project-root .
python3 BFD-Kit/scripts/migrate_bfd_skills.py --mode stage
python3 BFD-Kit/scripts/migrate_bfd_skills.py --mode cutover
```

- `stage`: import active `.codex/.claude` BFD skills into `BFD-Kit/`
- `cutover`: push `BFD-Kit/` canonical skills back into active mirrors and back up old mirrors under `archive/skills_migration/`

## Maintainer Notes

- Keep BFD-Kit skills, scripts, docs, and `.learnings` aligned across maintained copies.
- Avoid exposing local absolute paths, workspace topology, mirror relationships, or repository-boundary details in project-facing docs and prompts.
- Before publishing from any repository, verify the current repo root, remote, branch, and worktree state.
- See `BFD-Kit/MAINTENANCE-zh.md` for the generic maintenance checklist.

## Verification

```bash
bash BFD-Kit/init_project.sh --help
python3 BFD-Kit/scripts/bfd_install.py --help
bash BFD-Kit/scripts/install_python_runtime.sh --help
python3 BFD-Kit/scripts/bfd_jlink_hss.py --help
python3 BFD-Kit/scripts/migrate_bfd_skills.py --help
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
python3 ./.codex/skills/bfd-project-init/scripts/ensure_profile.py --project-root . --print-env-path
python3 ./.codex/skills/bfd-cubemx-codegen/scripts/generate_from_ioc.py --help
```

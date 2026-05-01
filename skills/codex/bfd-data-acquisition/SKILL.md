---
name: bfd-data-acquisition
description: Use when acquiring STM32 runtime data from global symbols, memory regions, stack-published local slots, or RTT channels and converting captures into structured artifacts for analysis.
---

# BFD Data Acquisition

## Self-Improvement Loop (Required)

- When this skill encounters a build, flash, debug, script-usage, or other workflow problem, do not stop at the local workaround after the issue is solved.
- Record the resolved issue and lesson in `BFD-Kit/.learnings/ERRORS.md` and/or `BFD-Kit/.learnings/LEARNINGS.md`; unresolved capability gaps go to `BFD-Kit/.learnings/FEATURE_REQUESTS.md`.
- Promote reusable fixes into the affected BFD-Kit asset in the same task when feasible: update the relevant `SKILL.md`, script, wrapper, or resource so the next run benefits by default.
- When a learning is promoted into a skill or script, append a short entry to `BFD-Kit/.learnings/CHANGELOG.md` and mention the improvement in the task close-out.

## Purpose

Use this skill when the task is "show the contents of this global/static object" and the object can be resolved from an ELF.

This skill is the default path for:

- global/static object inspection
- pointer-hub decoding
- enum-bearing state objects
- stack-published local-slot capture through pointer symbols
- raw RAM capture only when no stable symbol exists

This skill is not tied to any motor model or business object. The primary workflow is generic `ELF + symbol + DWARF`.

## Required Precheck

Run bootstrap before any acquisition command:

```bash
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
```

Fail fast if `${STM32_ELF}` or the active bootstrap profile is missing.

Before the first `symbol-auto` run, also verify that the exact interpreter behind `python3` can import `elftools`:

```bash
python3 -c "import elftools, sys; print(sys.executable)"
```

If this fails:

- on Ubuntu system Python, install `python3-pyelftools`
- if an activated conda environment shadows system `python3`, either install `pyelftools` into that environment or invoke `/usr/bin/python3` explicitly for the acquisition command

## Primary Command Contract

Primary script:

```bash
python3 BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py ...
```

Primary mode:

```bash
python3 BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --mode symbol-auto \
  --symbol <global_symbol> \
  --follow-depth 1 \
  --format summary \
  --output logs/data_acq/<symbol>.summary
```

Meaning of the primary arguments:

- `--mode symbol-auto`: resolve the symbol from ELF, reflect its DWARF type, reuse or rebuild schema cache, sample RAM, and decode named fields.
- `--symbol <global_symbol>`: required global or static object symbol.
- `--follow-depth <N>`: pointer follow depth.
- `--format summary|json|csv`: output renderer.

`symbol-auto` rules:

- requires `--symbol`
- supports only `--capture-mode snapshot`
- rejects manual decode options such as `--decode-profile`, `--layout`, `--pointer-array`, and `--follow-pointer`
- writes or reuses cache under `.codex/bfd/dwarf_cache/`
- when the script is invoked from a central BFD-Kit checkout, it also searches the current working directory upward for `.codex/bfd/active_profile.env` and `.codex/bfd/dwarf_cache`, so run it from the target project directory when you want project-local profile/cache resolution
- root object size and typedef-backed array element sizes come from the reflected DWARF schema; if a snapshot is shorter than expected, the script now reports an explicit capture-size mismatch or truncated nested field metadata instead of a raw Python `struct.error`

## Follow-Depth Rules

- `--follow-depth 0`: decode the root object only; pointers remain address metadata.
- `--follow-depth 1`: follow one pointer layer. Use this first for pointer hubs and object tables.
- `--follow-depth >1`: recursively follow nested pointers. Increase only when the object layout requires it.

If `--follow-depth >1` on a pointer array or pointer-rich object crashes with errors such as `struct.error: unpack requires a buffer of 1 bytes`, stop deep recursion on that object. Fall back to `--follow-depth 1` to recover the first-layer structs plus child pointer addresses, then inspect the nested child objects separately with another acquisition or raw J-Link `mem32` reads.

## Standard Workflow Order

1. Use `--mode symbol-auto` first when the target object has DWARF-supported type information.
2. Fall back to `--mode symbol` only when:
   - the target type contains unsupported DWARF features
   - a manual decode profile is intentionally narrower than the full object
   - a typed scalar layout is sufficient
3. Use `--pointer-symbol` only for stack-published local data.
4. Use raw `--address` capture only when no stable symbol exists.

## Native HSS Escalation

When the requirement is high-rate, non-halting sampling of a fixed-address scalar global/static variable on a J-Link target, prefer the native HSS CLI path instead of GUI J-Scope automation or halt/read/go loops:

```bash
bash BFD-Kit/scripts/bfd_jlink_hss.sh --json hss sample \
  --symbol chassis_parameter.IMU.yaw \
  --symbol chassis_parameter.IMU.pitch \
  --duration 0.3 \
  --period-us 1000 \
  --output logs/data_acq/imu_yaw_pitch_hss.csv
```

Use this path only for fixed-address scalar globals/statics. Repeat `--symbol` for multi-symbol sampling. On `J-Link PLUS`, SEGGER's model limits and local HSS verification both indicate a 10-symbol ceiling; do not treat `hss inspect` raw capability word 2 as the symbol-count limit. The wrapper uses `BFD-Kit/.runtime/venv` automatically after `bash BFD-Kit/init_project.sh --project-root .`. If the target is a pointer-driven object graph or needs DWARF field decoding, stay on `symbol-auto`. The command writes a wide CSV to `--output` and a metadata sidecar JSON to `--output.meta.json`.

Do not assume requested `--period-us` equals the achieved sample period on every probe model. Local `RSCF_h7` validation with `J-Link CE` showed a practical single-float floor near `1000 us`, even when `--period-us` was reduced from `1000` down to `1` and SWD was raised from `4000` to `8000 kHz`. When a new J-Link model, target, or board wiring is introduced, run an explicit sweep first and report the effective period from captured sample counts instead of trusting the requested value or a capability word name.

ST-Link does not provide an HSS-equivalent path in this revision. If `STM32_PROBE=stlink`, treat high-rate capture as a separate polling/snapshot design problem rather than a drop-in replacement for native J-Link HSS.

If the requirement is textual RTT evidence over ST-Link, switch to the independent `bfd-strtt-rtt` skill instead of forcing that flow through J-Link RTT guidance.

For FanX/Tek DAPLink High or another CMSIS-DAP probe, use the PyOCD HSS-compatible sampler when native J-Link HSS is unavailable but a fixed-address scalar CSV is still needed:

```bash
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_pyocd_hss.py --json sample \
  --elf RSCF_h7/builds/gcc/debug/RSCF_H7_BOARD_ONE.elf \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --symbol g_system_status.status_byte \
  --duration 0.5 \
  --period-us 1000 \
  --output RSCF_h7/logs/data_acq/g_system_status_pyocd_hss.csv
```

This backend intentionally writes the same wide CSV + `.meta.json` shape as native HSS, but it is host-polled and uses host monotonic timestamps. Do not label it as SEGGER probe-side HSS. For deterministic high-rate system identification, prefer firmware telemetry mirror/ring or a custom DAPLink vendor-command backend once the probe firmware source is available.

When the question is specifically "how many `float` values can DAPLink / PyOCD hold at a stable `1000 Hz` update?", use the built-in benchmark instead of guessing from one-off captures:

```bash
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_pyocd_hss.py --json benchmark-float \
  --address 0x200096E8 \
  --min-floats 1 \
  --max-floats 64 \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 0.2 \
  --period-us 1000 \
  --output RSCF_h7/logs/data_acq/pyocd_float_benchmark.json
```

This report tells you:

- the largest repeated `float_count` that still meets the configured 1 kHz stability rule
- the effective bytes per second at each float count
- where the host-polled path starts to fall behind

If the needed float count is above the stable 1 kHz boundary, stop trying to stretch host polling and move the fast path into the bundled MCU telemetry ring:

```bash
python3 BFD-Kit/scripts/bfd_telemetry_ring.py --json layout \
  --field pos_rad:f32 \
  --field vel_rads:f32 \
  --field torque_nm:f32 \
  --field state:u32 \
  --capacity 128
```

Then capture the ring through PyOCD once the firmware has published the ring image symbol/address:

```bash
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
  --output RSCF_h7/logs/data_acq/app_ring_capture.csv
```

The current `bfd_pyocd_hss.py` also supports two generic paths that align better with `UNI_DataVisualizer` style direct-read workflows:

- raw SRAM/MMIO scalar capture via repeated `--address-spec name@0xADDR:type`
- importing enabled variables from a Windows `HSSDVProj` file via `--project-file`

The script now coalesces contiguous addresses into one region read and automatically selects `block32` when the merged region is 4-byte aligned and 4-byte sized. On `RSCF_h7` with FanX/Tek DAPLink High at `10 MHz SWD`, local validation reached about `51.25 kB/s` for a packed `41B` struct field group and about `128 kB/s` for a merged `64B block32` raw-memory capture. This clears the practical `50 kB/s` threshold for MCU runtime data collection, but it is still not probe-side HSS and should not be positioned as a `1 MB/s` equivalent.

Example: raw address/MMIO capture with automatic `block32` merge:

```bash
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_pyocd_hss.py --json sample \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 0.2 \
  --period-us 500 \
  --address-spec w00@0x200096E8:u32 \
  --address-spec w01@0x200096EC:u32 \
  --address-spec w02@0x200096F0:u32 \
  --address-spec w03@0x200096F4:u32 \
  --output RSCF_h7/logs/data_acq/raw_block32_pyocd_hss.csv
```

Example: import a Windows DataVisualizer project directly:

```bash
RSCF_h7/.tools/pyocd-venv/bin/python BFD-Kit/scripts/bfd_pyocd_hss.py --json sample \
  --project-file .tmp_datavis/DataVisualizer_0.0.4.0/STM32F103VET6.HSSDVProj \
  --target stm32h723xx \
  --uid 6d1395736d13957301 \
  --frequency 10000000 \
  --duration 0.2 \
  --period-us 1000 \
  --output RSCF_h7/logs/data_acq/hssdv_project_capture.csv
```

Before using an imported `HSSDVProj` as a formal benchmark source, inspect it for duplicate addresses. The bundled `DataVisualizer_0.0.4.0/STM32F103VET6.HSSDVProj` demo contains repeated address entries, so importing it without review can make a capture look richer than the underlying unique RAM locations actually are.

## Generic Command Templates

### 1. Decode a Global or Static Object

```bash
python3 BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --mode symbol-auto \
  --symbol g_object_state \
  --follow-depth 0 \
  --format summary \
  --output logs/data_acq/g_object_state.summary
```

### 2. Decode a Pointer Hub or Pointer Array

```bash
python3 BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --mode symbol-auto \
  --symbol g_object_hub \
  --follow-depth 1 \
  --format json \
  --output logs/data_acq/g_object_hub.json
```

### 3. Manual Symbol Fallback When Auto Reflection Is Not Suitable

```bash
python3 BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --mode symbol \
  --symbol g_object_array \
  --count <N> \
  --decode-profile <profile_name> \
  --format csv \
  --output logs/data_acq/g_object_array.csv
```

### 4. Stack-Published Local Variable Capture

```bash
python3 BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py \
  --elf "${STM32_ELF}" \
  --pointer-symbol g_local_probe_addr \
  --seq-symbol g_local_probe_seq \
  --layout f32x1 \
  --count 20 \
  --interval-ms 20 \
  --mode nonstop \
  --output logs/data_acq/local_probe.csv
```

### 5. Raw Address Capture

```bash
python3 BFD-Kit/skills/codex/bfd-data-acquisition/scripts/data_acq.py \
  --address 0x20000000 \
  --layout u32x4 \
  --count 20 \
  --mode snapshot \
  --output logs/data_acq/raw_u32.csv
```

## Output Policy

- Save final artifacts under `logs/data_acq/`.
- Use `summary` for fast operator judgment.
- Use `json` for downstream AI or tool consumption.
- Use `csv` for manual table review.
- Treat `.codex/bfd/dwarf_cache/` as a reusable cache, not as the final evidence artifact.
- Do not run multiple J-Link RAM sampling, RTT, or GDB attach flows against the same target in parallel.

## Decision Rules

Use this skill instead of hand-written GDB or J-Link memory expressions when:

- an ELF symbol exists
- the task is "inspect this global/static object"
- the task needs named fields rather than raw words
- RTT produced no payload and RAM is the next validation path

Switch to `bfd-debug-interface` only when:

- the task is register-centric
- the symbol is not available
- lower-level breakpoint, watchpoint, or fault control is required

---
name: bfd-rtt-logger
description: Use when capturing STM32 RTT output through the current J-Link mainline, validating runtime behavior after flash/reset, or collecting short runtime evidence from J-Link RTT channels.
---

# BFD RTT Logger

## Self-Improvement Loop (Required)

- When this skill encounters a build, flash, debug, script-usage, or other workflow problem, do not stop at the local workaround after the issue is solved.
- Record the resolved issue and lesson in `BFD-Kit/.learnings/ERRORS.md` and/or `BFD-Kit/.learnings/LEARNINGS.md`; unresolved capability gaps go to `BFD-Kit/.learnings/FEATURE_REQUESTS.md`.
- Promote reusable fixes into the affected BFD-Kit asset in the same task when feasible: update the relevant `SKILL.md`, script, wrapper, or resource so the next run benefits by default.
- When a learning is promoted into a skill or script, append a short entry to `BFD-Kit/.learnings/CHANGELOG.md` and mention the improvement in the task close-out.

Use this skill to capture RTT logs with profile-driven defaults.

## Quick Start

1. Run bootstrap profile first.
2. Use J-Link `quick` mode for routine runtime checks.
3. Use `dual` mode only after reset/reconnect flows on J-Link.
4. If the active probe is ST-Link, switch to `bfd-strtt-rtt` instead of this skill.

## Core Commands

```bash
# 0) Bootstrap profile (required)
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
```

```bash
# 1) Quick mode
./build_tools/jlink/rtt.sh logs/rtt/rtt_quick.log 5 --mode quick
```

```bash
# 2) Dual mode for reset-follow capture
./build_tools/jlink/rtt.sh logs/rtt/rtt_dual.log 6 --mode dual --reset-policy gdb-reset-go
```

```bash
# 3) Resolve RTT address from profile ELF
./.codex/skills/bfd-rtt-logger/scripts/get_rtt_address.sh \
  --elf "${STM32_ELF}" \
  --device "${STM32_DEVICE}" \
  --out logs/debug/rtt_addr_probe.log
```

## Workflow

1. Run bootstrap and verify profile env.
2. Confirm RTT symbol/address.
3. Capture with J-Link `quick/dual`.
4. Archive logs and extract key evidence lines.

## USB CDC Service False-Negative Triage

If a ROS/service transaction clearly leaves the host, but the host never receives `SYSTEM_STATUS`, `ODOM`, or other regular upstream packets, do not immediately conclude that the service FSM is broken. Check RTT first:

- If RTT repeatedly shows lines such as `W:[usb] tx fail ... status=1`, treat `status=1` as `USBD_BUSY` on the ST USB CDC stack.
- In this pattern, the visible failure is usually the MCU USB upstream path, not the service handler itself.
- For `mcu_comm`-style firmware that reuses a shared static TX buffer, confirm that the USB send path waits for `TxState == 0` before reusing the buffer and also waits for TX completion after `CDC_Transmit_*()` succeeds.
- When this signature appears, prioritize transport-layer repair or verification before spending time on service/action state machines.

## Probe Capability Boundary

- J-Link supports `quick`, `dual`, and native HSS.
- ST-Link uses the independent `bfd-strtt-rtt` skill.
- ST-Link does not use this J-Link mainline RTT path.

## Hard Rules

- Fail-fast if bootstrap profile is missing.
- Save final logs under `logs/rtt/`.
- In `dual` mode, do not open competing J-Link sessions.
- Keep final evidence in repository paths only.

## Scripts

- `.codex/skills/bfd-rtt-logger/scripts/rtt_log.sh`
- `.codex/skills/bfd-rtt-logger/scripts/rtt_log.ps1`
- `.codex/skills/bfd-rtt-logger/scripts/get_rtt_address.sh`

## Related Skills

- `bfd-project-init`
- `bfd-debug-interface`
- `bfd-fault-logger`
- `bfd-debug-orchestrator`

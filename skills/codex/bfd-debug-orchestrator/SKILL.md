---
name: bfd-debug-orchestrator
description: Use when running end-to-end STM32 debug campaigns that coordinate flash, RTT, register capture, HardFault snapshots, and error archival across multiple tools.
---

# BFD Debug Orchestrator

Use this skill to coordinate multi-step debug campaigns with profile-driven device settings.

## Execution Order

1. `bfd-project-init`
2. `systematic-debugging`
3. `bfd-rtt-logger`
4. `bfd-debug-executor`
5. `bfd-register-capture`
6. `bfd-fault-logger`
7. `verification-before-completion`

## Core Commands

```bash
# 0) Bootstrap profile (required)
python3 ./.codex/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
```

```bash
# Full fault campaign
./.codex/skills/bfd-debug-orchestrator/scripts/run_fault_campaign.sh
```

```bash
# Inject one scenario
./.codex/skills/bfd-debug-orchestrator/scripts/inject_fault_scenario.sh --scenario 3
```

```bash
# Capture one HardFault snapshot
./.codex/skills/bfd-debug-orchestrator/scripts/capture_hardfault_snapshot.sh
```

```bash
# Manual dual RTT capture after reset
./build_tools/jlink/rtt.sh logs/rtt/manual_dual.log 6 --mode dual --reset-policy gdb-reset-go
```

## Scenario Set

- `1`: recoverable IMU communication fault
- `2`: recoverable Flash parameter fault
- `3`: illegal address write (HardFault)
- `4`: UDF trap (UsageFault/HardFault)

## Hard Rules

- Fail-fast if bootstrap profile is missing.
- Output only key conclusions and evidence paths by default.
- For each HardFault, generate both `md` and `json` records.
- Save all artifacts under `logs/` or `.codex/debug/`.
- In dual RTT mode, reset through the same GDB server backend.

## References

- `.codex/skills/bfd-debug-orchestrator/references/hardfault_record_template.md`
- `.codex/skills/bfd-debug-orchestrator/references/error_evolution_schema.md`
- `.codex/skills/bfd-debug-orchestrator/references/token_saving_output_rules.md`

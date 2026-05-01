---
name: bfd-matlab-mcd
description: Use when building a closed STM32-to-Matlab workflow for J-Link HSS data capture, system identification, PID/LQR/MPC tuning, Kalman parameter estimation, or Matlab/Simulink code-generation feedback loops.
---

# BFD Matlab MCD Workflow

## Self-Improvement Loop (Required)

- When this skill encounters a build, flash, debug, script-usage, Matlab, or code-generation workflow problem, record the resolved issue and lesson in `BFD-Kit/.learnings/ERRORS.md` and/or `BFD-Kit/.learnings/LEARNINGS.md`.
- Unresolved capability gaps go to `BFD-Kit/.learnings/FEATURE_REQUESTS.md`.
- Promote reusable fixes into the affected BFD-Kit asset in the same task when feasible.
- When a learning is promoted into a skill or script, append a short entry to `BFD-Kit/.learnings/CHANGELOG.md`.

## Purpose

Use this skill for the full loop:

1. capture synchronized MCU scalar variables with J-Link HSS;
2. store the run as an experiment dataset with manifest and compact summaries;
3. run Matlab analysis without sending full CSV files into the AI context;
4. use Matlab results for system identification, PID/LQR/MPC candidates, Kalman noise parameters, or MCD codegen checks;
5. feed hardware evidence back into the next Matlab or firmware iteration.

## Precheck

```bash
python3 ./.claude/skills/bfd-project-init/scripts/bootstrap.py --project-root . --mode check
```

```bash
/home/xuan/matlab/bin/matlab -batch "disp(version)"
```

If Matlab is installed elsewhere, pass `--matlab-bin <path>` or set `MATLAB_BIN`.

## Capture A Dataset

```bash
python3 BFD-Kit/scripts/bfd_experiment.py capture-hss \
  --elf "${STM32_ELF}" \
  --symbol motor_cmd \
  --symbol motor_speed \
  --duration 2.0 \
  --period-us 1000 \
  --output-dir logs/experiments \
  --experiment-name motor_step_001 \
  --stimulus "step command"
```

The command writes `capture.csv`, `capture.csv.meta.json`, `manifest.json`, `summary.json`, `summary.md`, and Matlab templates under `matlab/`. Terminal output is compact by default.

## Summarize Existing Data

```bash
python3 BFD-Kit/scripts/bfd_experiment.py summarize \
  --dataset-dir logs/experiments/motor_step_001
```

Use summaries for AI review. Do not paste full CSV files unless the task explicitly requires raw samples.

## Run Matlab Analysis

```bash
python3 BFD-Kit/scripts/bfd_experiment.py matlab-run \
  --dataset-dir logs/experiments/motor_step_001 \
  --analysis system-id \
  --matlab-bin /home/xuan/matlab/bin/matlab
```

`matlab-run` defaults to `--matlab-backend auto`. In auto mode, BFD-Kit first tries the official MathWorks `matlab-mcp-core-server`; if the MCP server is unavailable or fails before a Matlab script runs, it records the MCP error under `matlab_out/matlab_mcp_error.log` and falls back to `matlab -batch`.

Use explicit MCP mode when validating an agentic Matlab/Simulink session:

```bash
python3 BFD-Kit/scripts/bfd_experiment.py matlab-run \
  --dataset-dir logs/experiments/motor_step_001 \
  --analysis mcd-check \
  --matlab-backend mcp \
  --mcp-server /path/to/matlab-mcp-core-server \
  --mcp-matlab-root /home/xuan/matlab \
  --satk-root /path/to/simulink-agentic-toolkit
```

The MCP path uses `detect_matlab_toolboxes`, `check_matlab_code`, and `run_matlab_file` when exposed by the server. If `--satk-root` is provided, it also runs `satk_initialize` through `evaluate_matlab_code` before the dataset analysis file, enabling Simulink Agentic Toolkit model-query and MBD workflows in the same session.

Supported `--analysis` values:

- `system-id`: build `iddata` from classified input/output columns and estimate a conservative first-order model.
- `control`: produce baseline PID, LQR, and MPC candidates from an identified model.
- `kalman`: estimate measurement `R` and process `Q` covariance candidates from selected columns.
- `mcd-check`: record Matlab/Simulink codegen toolbox availability and MCU integration rules.

## Hard Rules

- Use J-Link HSS only for fixed-address scalar globals/statics.
- Do not run HSS, RTT, GDB, or RAM polling concurrently on the same probe.
- Do not assume input/output columns. If `manifest.json` lacks classification, update classification before trusting system identification output.
- Prefer the MathWorks Matlab MCP Core Server and Simulink Agentic Toolkit for agent-driven Matlab/Simulink work; use `matlab -batch` only as an explicit or automatic fallback.
- Generated C/C++ must enter business-layer wrappers such as `USER/Modules` or `USER/APP`, not CubeMX-managed directories.
- Treat Matlab-generated PID/LQR/MPC/Kalman parameters as candidates until validated by firmware build, flash, and hardware capture evidence.

## References

- `BFD-Kit/docs/plans/stm32-matlab-mcd-workflow.md`
- `BFD-Kit/scripts/bfd_experiment.py`
- MathWorks Matlab MCP Core Server: https://www.mathworks.com/products/matlab-mcp-core-server.html
- MathWorks Simulink Agentic Toolkit: https://ww2.mathworks.cn/products/simulink-agentic-toolkit.html
- `BFD-Kit/resources/matlab/templates/`
- `bfd-data-acquisition`
- `bfd-debug-orchestrator`

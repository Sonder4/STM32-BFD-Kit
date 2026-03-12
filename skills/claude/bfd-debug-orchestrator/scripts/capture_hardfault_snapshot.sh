#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

PROFILE_HELPER="${PROJECT_ROOT}/build_tools/jlink/profile_env.sh"
if [[ ! -f "${PROFILE_HELPER}" ]]; then
  echo "[ERROR] profile helper not found: ${PROFILE_HELPER}" >&2
  exit 2
fi
# shellcheck source=build_tools/jlink/profile_env.sh
source "${PROFILE_HELPER}"
load_stm32_profile_env "${PROJECT_ROOT}" || exit 2

ELF="${STM32_ELF:-}"
SCENARIO_ID="0"
DEVICE="${STM32_DEVICE}"
IFACE="${STM32_IF:-SWD}"
SPEED="${STM32_SPEED_KHZ:-4000}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --elf)
      ELF="$2"
      shift 2
      ;;
    --scenario)
      SCENARIO_ID="$2"
      shift 2
      ;;
    --device)
      DEVICE="$2"
      shift 2
      ;;
    --if)
      IFACE="$2"
      shift 2
      ;;
    --speed)
      SPEED="$2"
      shift 2
      ;;
    -h|--help)
      cat <<USAGE
Usage:
  capture_hardfault_snapshot.sh [--elf <path>] [--scenario <id>] [--device <name>] [--if <name>] [--speed <kHz>]
USAGE
      exit 0
      ;;
    *)
      echo "[ERROR] unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${ELF}" || ! -f "${ELF}" ]]; then
  echo "[ERROR] ELF not found: ${ELF:-<empty>}" >&2
  exit 1
fi

for tool in JLinkExe python3 arm-none-eabi-addr2line; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "[ERROR] missing tool: $tool" >&2
    exit 1
  fi
done

DATE_DIR="${PROJECT_ROOT}/logs/hw_error/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"
ID="ERR_$(date +%Y%m%d_%H%M%S)"
CMD_FILE="${DATE_DIR}/${ID}.jlink"
RAW_LOG="${DATE_DIR}/${ID}_snapshot.log"
JSON_OUT="${DATE_DIR}/${ID}.json"
MD_OUT="${DATE_DIR}/${ID}.md"

cat > "$CMD_FILE" <<JLINK
device ${DEVICE}
si ${IFACE}
speed ${SPEED}
connect
h
regs
mem32 0xE000ED28 4
mem32 0xE000ED34 1
mem32 0xE000ED38 1
mem32 0xE000ED3C 1
exit
JLINK

JLinkExe -CommandFile "$CMD_FILE" > "$RAW_LOG" 2>&1

python3 - "$RAW_LOG" "$JSON_OUT" "$MD_OUT" "$ELF" "$SCENARIO_ID" "$ID" "$CMD_FILE" <<'PY'
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

raw_path = Path(sys.argv[1])
json_path = Path(sys.argv[2])
md_path = Path(sys.argv[3])
elf = sys.argv[4]
scenario_id = sys.argv[5]
err_id = sys.argv[6]
cmd_file = sys.argv[7]
text = raw_path.read_text(errors="ignore")

reg = {}

def set_hex(name, value):
    reg[name] = f"0x{value.upper()}"

m = re.search(r"PC\s*=\s*([0-9A-Fa-f]{8})", text)
if m:
    set_hex("PC", m.group(1))

patterns = [
    (r"R0\s*=\s*([0-9A-Fa-f]{8}),\s*R1\s*=\s*([0-9A-Fa-f]{8}),\s*R2\s*=\s*([0-9A-Fa-f]{8}),\s*R3\s*=\s*([0-9A-Fa-f]{8})", ["R0", "R1", "R2", "R3"]),
    (r"R4\s*=\s*([0-9A-Fa-f]{8}),\s*R5\s*=\s*([0-9A-Fa-f]{8}),\s*R6\s*=\s*([0-9A-Fa-f]{8}),\s*R7\s*=\s*([0-9A-Fa-f]{8})", ["R4", "R5", "R6", "R7"]),
    (r"R8\s*=\s*([0-9A-Fa-f]{8}),\s*R9\s*=\s*([0-9A-Fa-f]{8}),\s*R10=\s*([0-9A-Fa-f]{8}),\s*R11=\s*([0-9A-Fa-f]{8})", ["R8", "R9", "R10", "R11"]),
]
for pat, names in patterns:
    m = re.search(pat, text)
    if m:
        for n, v in zip(names, m.groups()):
            set_hex(n, v)

m = re.search(r"R12=\s*([0-9A-Fa-f]{8})", text)
if m:
    set_hex("R12", m.group(1))

m = re.search(r"SP\(R13\)=\s*([0-9A-Fa-f]{8}),\s*MSP=\s*([0-9A-Fa-f]{8}),\s*PSP=\s*([0-9A-Fa-f]{8}),\s*R14\(LR\)\s*=\s*([0-9A-Fa-f]{8})", text)
if m:
    set_hex("SP", m.group(1))
    set_hex("MSP", m.group(2))
    set_hex("PSP", m.group(3))
    set_hex("LR", m.group(4))

m = re.search(r"XPSR\s*=\s*([0-9A-Fa-f]{8}).*?IPSR\s*=\s*([0-9A-Fa-f]{3})\s*\(([^\)]+)\)", text)
fault_type = "UnknownFault"
ipsr_desc = "N/A"
if m:
    set_hex("xPSR", m.group(1))
    ipsr_desc = m.group(3).strip()
    if "HardFault" in ipsr_desc:
        fault_type = "HardFault"
    elif "UsageFault" in ipsr_desc:
        fault_type = "UsageFault"
    elif "BusFault" in ipsr_desc:
        fault_type = "BusFault"
    elif "MemManage" in ipsr_desc:
        fault_type = "MemManageFault"

fault_status = {
    "CFSR": "0x00000000",
    "HFSR": "0x00000000",
    "DFSR": "0x00000000",
    "MMFAR": "0x00000000",
    "BFAR": "0x00000000",
    "AFSR": "0x00000000",
}

m = re.search(r"E000ED28\s*=\s*([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})", text)
if m:
    fault_status["CFSR"] = f"0x{m.group(1).upper()}"
    fault_status["HFSR"] = f"0x{m.group(2).upper()}"
    fault_status["DFSR"] = f"0x{m.group(3).upper()}"
    fault_status["MMFAR"] = f"0x{m.group(4).upper()}"

m = re.search(r"E000ED34\s*=\s*([0-9A-Fa-f]{8})", text)
if m:
    fault_status["MMFAR"] = f"0x{m.group(1).upper()}"

m = re.search(r"E000ED38\s*=\s*([0-9A-Fa-f]{8})", text)
if m:
    fault_status["BFAR"] = f"0x{m.group(1).upper()}"

m = re.search(r"E000ED3C\s*=\s*([0-9A-Fa-f]{8})", text)
if m:
    fault_status["AFSR"] = f"0x{m.group(1).upper()}"

stack_trace = []
for key in ("PC", "LR"):
    if key in reg:
        stack_trace.append(reg[key])

addr2line = []
for addr in stack_trace:
    try:
        out = subprocess.check_output([
            "arm-none-eabi-addr2line", "-e", elf, "-f", "-C", addr
        ], text=True, stderr=subprocess.STDOUT).strip().splitlines()
        func = out[0] if len(out) > 0 else "??"
        loc = out[1] if len(out) > 1 else "??:0"
    except Exception:
        func = "??"
        loc = "??:0"
    addr2line.append({"address": addr, "function": func, "location": loc})

payload = {
    "id": err_id,
    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    "fault_type": fault_type,
    "severity": "Critical",
    "source": "CPU",
    "description": f"{fault_type} captured by bfd-debug-orchestrator",
    "registers": reg,
    "fault_status": fault_status,
    "stack_trace": stack_trace,
    "addr2line": addr2line,
    "context": {
        "scenario_id": int(scenario_id),
        "ipsr_desc": ipsr_desc,
    },
    "evidence_paths": {
        "snapshot_log": str(raw_path),
        "jlink_cmd": cmd_file,
    },
    "raw_data": None,
}

json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

lines = [
    f"# {err_id}",
    "",
    "## Summary",
    f"- Timestamp: {payload['timestamp']}",
    f"- Type: {fault_type}",
    f"- Scenario: {scenario_id}",
    f"- IPSR: {ipsr_desc}",
    "",
    "## Key Registers",
]
for k in ["PC", "LR", "SP", "MSP", "PSP", "xPSR"]:
    if k in reg:
        lines.append(f"- {k}: {reg[k]}")

lines += [
    "",
    "## Fault Status",
    f"- CFSR: {fault_status['CFSR']}",
    f"- HFSR: {fault_status['HFSR']}",
    f"- DFSR: {fault_status['DFSR']}",
    f"- MMFAR: {fault_status['MMFAR']}",
    f"- BFAR: {fault_status['BFAR']}",
    f"- AFSR: {fault_status['AFSR']}",
    "",
    "## Addr2line",
]
for item in addr2line:
    lines.append(f"- {item['address']} -> {item['function']} @ {item['location']}")

lines += [
    "",
    "## Evidence",
    f"- snapshot_log: {raw_path}",
    f"- jlink_cmd: {cmd_file}",
    f"- json: {json_path}",
]

md_path.write_text("\n".join(lines) + "\n")
PY

cat <<OUT
ERROR_ID=${ID}
SNAPSHOT_LOG=${RAW_LOG}
JSON=${JSON_OUT}
MD=${MD_OUT}
OUT

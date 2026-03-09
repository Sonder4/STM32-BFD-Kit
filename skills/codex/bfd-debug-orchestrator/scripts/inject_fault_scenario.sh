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

SCENARIO=""
ELF="${STM32_ELF:-}"
DEVICE="${STM32_DEVICE}"
IFACE="${STM32_IF:-SWD}"
SPEED="${STM32_SPEED_KHZ:-4000}"

usage() {
  cat <<USAGE
Usage:
  inject_fault_scenario.sh --scenario <id> [--elf <path>] [--device <name>] [--if <name>] [--speed <kHz>]

Scenarios:
  1 IMU_COMM_FAULT
  2 FLASH_PARAM_FAULT
  3 HARDFAULT_BAD_PTR
  4 USAGEFAULT_UDF (legacy: DIV0)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario)
      SCENARIO="$2"
      shift 2
      ;;
    --elf)
      ELF="$2"
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
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$SCENARIO" ]]; then
  echo "[ERROR] --scenario is required" >&2
  exit 1
fi

if [[ -z "$ELF" || ! -f "$ELF" ]]; then
  echo "[ERROR] ELF not found: ${ELF:-<empty>}" >&2
  exit 1
fi

if ! command -v arm-none-eabi-nm >/dev/null 2>&1; then
  echo "[ERROR] missing arm-none-eabi-nm" >&2
  exit 1
fi

if ! command -v JLinkExe >/dev/null 2>&1; then
  echo "[ERROR] missing JLinkExe" >&2
  exit 1
fi

ADDR="$(arm-none-eabi-nm -n "$ELF" | awk '$3=="g_debug_fault_scenario" {print "0x"$1; exit}')"
if [[ -z "$ADDR" ]]; then
  echo "[ERROR] symbol g_debug_fault_scenario not found in ELF" >&2
  exit 1
fi

mkdir -p "${PROJECT_ROOT}/logs/debug"
TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="${PROJECT_ROOT}/logs/debug/${TS}_inject_s${SCENARIO}.log"
CMD="${PROJECT_ROOT}/logs/debug/${TS}_inject_s${SCENARIO}.jlink"

cat > "$CMD" <<JLINK
device ${DEVICE}
si ${IFACE}
speed ${SPEED}
connect
h
w4 ${ADDR} ${SCENARIO}
go
exit
JLINK

{
  echo "TIMESTAMP=$(date +%Y-%m-%dT%H:%M:%S%:z)"
  echo "SCENARIO=${SCENARIO}"
  echo "ELF=${ELF}"
  echo "DEVICE=${DEVICE}"
  echo "IFACE=${IFACE}"
  echo "SPEED=${SPEED}"
  echo "VAR_ADDR=${ADDR}"
  echo "JLINK_CMD=${CMD}"
} > "$LOG"

JLinkExe -CommandFile "$CMD" >> "$LOG" 2>&1

cat <<OUT
SCENARIO=${SCENARIO}
VAR_ADDR=${ADDR}
INJECT_LOG=${LOG}
OUT

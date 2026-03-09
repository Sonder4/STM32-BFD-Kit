#!/bin/bash
#===============================================================================
# SEGGER RTT runtime address probe (profile-driven)
#===============================================================================

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

DEVICE="${STM32_DEVICE}"
IFACE="${STM32_IF:-SWD}"
SPEED="${STM32_SPEED_KHZ:-4000}"
ELF_FILE="${STM32_ELF:-}"
OUT_FILE=""
SCAN_WINDOW="${STM32_RTT_SCAN_WINDOW:-0x24000000:0x00080000}"

usage() {
  cat <<'EOF'
Usage:
  get_rtt_address.sh [options]

Options:
  --elf <path>            ELF file path
  --device <name>         target device (default from profile)
  --if <name>             debug interface (default from profile)
  --speed <kHz>           debug speed (default from profile)
  --out <path>            output log path
  --scan-window <start:size>
                          RAM scan window, e.g. 0x20000000:0x00030000
  -h, --help              show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --elf)
      ELF_FILE="$2"
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
    --out)
      OUT_FILE="$2"
      shift 2
      ;;
    --scan-window)
      SCAN_WINDOW="$2"
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

if [[ -z "${ELF_FILE}" || ! -f "${ELF_FILE}" ]]; then
  echo "[ERROR] ELF not found: ${ELF_FILE:-<empty>}" >&2
  exit 1
fi

SCAN_START_HEX="${SCAN_WINDOW%%:*}"
SCAN_SIZE_HEX="${SCAN_WINDOW##*:}"

if [[ -z "${OUT_FILE}" ]]; then
  mkdir -p "${PROJECT_ROOT}/logs/debug"
  OUT_FILE="${PROJECT_ROOT}/logs/debug/$(date +%Y-%m-%d_%H%M%S)_rtt_addr_probe.log"
else
  mkdir -p "$(dirname "${OUT_FILE}")"
fi

RAW_LOG="${OUT_FILE%.log}.jlink.log"
SCAN_BIN="${OUT_FILE%.log}.scan.bin"
TMP_CMD="$(mktemp)"

cleanup() {
  rm -f "${TMP_CMD}"
}
trap cleanup EXIT

for tool in JLinkExe arm-none-eabi-nm grep awk; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "[ERROR] missing tool: ${tool}" | tee -a "${OUT_FILE}" >&2
    exit 1
  fi
done

RTT_SYMBOL_ADDR="$(arm-none-eabi-nm -n "${ELF_FILE}" | awk '$3=="_SEGGER_RTT" {print "0x"$1; exit}')"
UPBUF_SYMBOL_ADDR="$(arm-none-eabi-nm -n "${ELF_FILE}" | awk '$3=="_acUpBuffer" {print "0x"$1; exit}')"

if [[ -z "${RTT_SYMBOL_ADDR}" ]]; then
  echo "[ERROR] _SEGGER_RTT not found in ELF: ${ELF_FILE}" | tee -a "${OUT_FILE}" >&2
  exit 1
fi

SIGNATURE_HEX="53 45 47 47 45 52 20 52 54 54"
RUNTIME_ADDR=""
ADDR_SOURCE="NONE"
SIGNATURE_OK=0

run_jlink() {
  local cmd_file="$1"
  local output
  set +e
  output="$(JLinkExe -CommandFile "${cmd_file}" 2>&1)"
  local rc=$?
  set -e
  echo "${output}" >> "${RAW_LOG}"
  return "${rc}"
}

: > "${RAW_LOG}"

# Step 1: validate symbol address
cat > "${TMP_CMD}" <<EOF
device ${DEVICE}
si ${IFACE}
speed ${SPEED}
connect
h
mem8 ${RTT_SYMBOL_ADDR} 32
exit
EOF

if run_jlink "${TMP_CMD}"; then
  if grep -q "${SIGNATURE_HEX}" "${RAW_LOG}"; then
    RUNTIME_ADDR="${RTT_SYMBOL_ADDR}"
    ADDR_SOURCE="ELF_SYMBOL_VALIDATED"
    SIGNATURE_OK=1
  fi
fi

# Step 2: scan RAM window if symbol validation failed
if [[ -z "${RUNTIME_ADDR}" ]]; then
  cat > "${TMP_CMD}" <<EOF
device ${DEVICE}
si ${IFACE}
speed ${SPEED}
connect
h
savebin ${SCAN_BIN} ${SCAN_START_HEX} ${SCAN_SIZE_HEX}
exit
EOF

  if run_jlink "${TMP_CMD}" && [[ -s "${SCAN_BIN}" ]]; then
    OFFSET_DEC="$(grep -oba "SEGGER RTT" "${SCAN_BIN}" | head -n 1 | cut -d: -f1 || true)"
    if [[ -n "${OFFSET_DEC}" ]]; then
      SCAN_START_DEC=$((SCAN_START_HEX))
      RUNTIME_ADDR="$(printf "0x%08X" $((SCAN_START_DEC + OFFSET_DEC)))"
      ADDR_SOURCE="RAM_SCAN_VALIDATED"
      SIGNATURE_OK=1
    fi
  fi
fi

if [[ -n "${RUNTIME_ADDR}" ]]; then
  EXIT_CODE=0
else
  EXIT_CODE=2
fi

{
  echo "TIMESTAMP=$(date +%Y-%m-%dT%H:%M:%S%:z)"
  echo "DEVICE=${DEVICE}"
  echo "INTERFACE=${IFACE}"
  echo "SPEED_KHZ=${SPEED}"
  echo "ELF_FILE=${ELF_FILE}"
  echo "SCAN_WINDOW=${SCAN_START_HEX}:${SCAN_SIZE_HEX}"
  echo "RTT_SYMBOL_ADDR=${RTT_SYMBOL_ADDR}"
  echo "UPBUF_SYMBOL_ADDR=${UPBUF_SYMBOL_ADDR:-N/A}"
  echo "RTT_RUNTIME_ADDR=${RUNTIME_ADDR:-N/A}"
  echo "SIGNATURE_OK=${SIGNATURE_OK}"
  echo "ADDRESS_SOURCE=${ADDR_SOURCE}"
  echo "RAW_JLINK_LOG=${RAW_LOG}"
  echo "EXIT_CODE=${EXIT_CODE}"
} | tee "${OUT_FILE}"

exit "${EXIT_CODE}"

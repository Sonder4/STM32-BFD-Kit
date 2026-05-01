#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: launch_ozone.sh <project.jdebug>" >&2
  exit 1
fi

PROJECT_FILE="$1"
OZONE_BIN="${OZONE_BIN:-ozone}"

if ! command -v "$OZONE_BIN" >/dev/null 2>&1; then
  echo "[bfd-ozone] ozone executable not found in PATH" >&2
  exit 1
fi

if [ ! -f "$PROJECT_FILE" ]; then
  echo "[bfd-ozone] project file not found: $PROJECT_FILE" >&2
  exit 1
fi

exec "$OZONE_BIN" "$PROJECT_FILE"

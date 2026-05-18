#!/usr/bin/env bash
# Example: run a batch render from input/ into output/ for 1 hour with a 0.8s crossfade.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
if [ -f "$VENV_DIR/bin/activate" ]; then
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
fi

cd "$PROJECT_DIR"

INPUT="${INPUT:-input}"
OUTPUT="${OUTPUT:-output}"
HOURS="${HOURS:-1}"
CROSSFADE="${CROSSFADE:-0.8}"

python main.py --input "$INPUT" --output "$OUTPUT" --hours "$HOURS" --crossfade "$CROSSFADE" --batch

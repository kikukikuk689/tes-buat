#!/usr/bin/env bash
# One-shot: setup virtualenv + install dependencies + run a batch render from
# input/ into output/. Override defaults with INPUT, OUTPUT, HOURS, CROSSFADE.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

bash "$SCRIPT_DIR/setup.sh"

VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

cd "$PROJECT_DIR"

INPUT="${INPUT:-input}"
OUTPUT="${OUTPUT:-output}"
HOURS="${HOURS:-1}"
CROSSFADE="${CROSSFADE:-0.8}"

exec python main.py --input "$INPUT" --output "$OUTPUT" --hours "$HOURS" --crossfade "$CROSSFADE" --batch

#!/usr/bin/env bash
# Launch the Streamlit UI for ASMR Seamless Loop Maker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
if [ -f "$VENV_DIR/bin/activate" ]; then
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
fi

cd "$PROJECT_DIR"
exec streamlit run app/ui.py "$@"

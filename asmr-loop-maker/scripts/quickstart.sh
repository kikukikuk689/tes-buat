#!/usr/bin/env bash
# One-shot: setup virtualenv + install dependencies + launch the Streamlit UI.
# Useful for first-time users who just want to double-click and go.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

bash "$SCRIPT_DIR/setup.sh"

VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

cd "$PROJECT_DIR"
exec python -m streamlit run app/ui.py "$@"

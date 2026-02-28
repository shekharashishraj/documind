#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PY="${PROJECT_ROOT}/.venv/bin/python"

if [[ -x "$VENV_PY" ]]; then
  PYTHON="$VENV_PY"
else
  PYTHON="python"
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: ./run_pdf.sh \"/absolute/path/to/file.pdf\" \"Your prompt here\""
  exit 1
fi

PDF_PATH="$1"
shift
PROMPT="$*"

exec "$PYTHON" "$SCRIPT_DIR/run_on_pdf.py" "$PDF_PATH" "$PROMPT"

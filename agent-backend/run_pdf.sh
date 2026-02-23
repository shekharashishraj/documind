#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$REPO_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Error: .venv is missing or not executable at: $VENV_PY"
  echo "Create it with: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.lock.txt"
  exit 1
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: ./run_pdf.sh \"/absolute/path/to/file.pdf\" \"Your prompt here\""
  exit 1
fi

PDF_PATH="$1"
shift
PROMPT="$*"

exec "$VENV_PY" "$REPO_DIR/run_on_pdf.py" "$PDF_PATH" "$PROMPT"

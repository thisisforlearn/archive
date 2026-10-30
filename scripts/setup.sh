#!/usr/bin/env bash
# msarchive bootstrap — local WSL2/machine setup.
# Installs deps STRICTLY inside ~/ml_env venv (per project rule: never system-wide).
# Author: Vaibhav (Vaibhav Agarwal, archiver) | GPL-3.0-only
set -euo pipefail

VENV="${HOME}/ml_env"

if [ ! -d "$VENV" ]; then
    echo "[setup] creating venv at $VENV"
    python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt

cp -n .env.example .env 2>/dev/null || true
echo "[setup] done. Remember to fill .env (IA + HF keys), then run:"
echo "        source ~/ml_env/bin/activate && python -m msarchive run --max-hours 8"

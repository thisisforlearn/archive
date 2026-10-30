#!/usr/bin/env bash
# run.sh — the one-liner. git clone https://github.com/thisisforlearn/archive && cd archive && ./run.sh
# Does EVERYTHING: venv (~/ml_env only, per project rule), deps, hooks wiring,
# first-run key prompts (stored in .env), then the full pipeline.
# Author: Vaibhav (Vaibhav Agarwal, archiver) <nekomeowpurr@proton.me>
# https://github.com/thisisforlearn/archive | GPL-3.0-only
set -euo pipefail

cd "$(dirname "$0")"
VENV="${HOME}/ml_env"

# 1 — venv + deps (fast no-op after first run)
if [ ! -x "${VENV}/bin/python" ]; then
    echo "[run] creating venv at $VENV (project rule: never system-wide)"
    python3 -m venv "$VENV"
fi
source "${VENV}/bin/activate"
python -m pip -q install --upgrade pip 2>/dev/null || true
python -m pip -q install -r requirements.txt 2>/dev/null || true

# 2 — commit co-authoring (Vaibhav author + thisisforlearn co-author)
git config --local core.hooksPath hooks 2>/dev/null || true
git config --local commit.template .commit-template 2>/dev/null || true

# 3 — keys: prompt once (only when BOTH key sets are missing; partial configs kept)
if [[ ! -f .env ]]; then cp -n .env.example .env || true; fi
if [ "${1:-run}" = "run" ] && ! grep -qi '^IA_S3_SECRET_KEY=.\+' .env 2>/dev/null && ! grep -qi '^HF_TOKEN=.\+' .env 2>/dev/null; then
    echo "[run] first run: paste your free keys (they are saved to .env, never committed)"
    read -r -p "  IA_S3_ACCESS_KEY  (archive.org/account/s3.php): " IA_ACCESS || true
    read -r -p "  IA_S3_SECRET_KEY  : " IA_SECRET || true
    read -r -p "  HF_TOKEN          (huggingface.co/settings/tokens): " HFT || true
    { echo; echo "IA_S3_ACCESS_KEY=${IA_ACCESS}"; echo "IA_S3_SECRET_KEY=${IA_SECRET}"; echo "HF_TOKEN=${HFT}"; } >> .env
    echo "[run] keys stored in .env OK"
fi

# 4 — the pipeline. Budget default 8h locally (.env or $MAX_HOURS to override)
MAX_HOURS="${MAX_HOURS:-8}"
if [ "${1:-run}" = "run" ]; then
    exec python -m msarchive run --max-hours "${MAX_HOURS}" ${MSARCHIVE_ARGS:-} "${@:2}"
else
    exec python -m msarchive "$@"
fi

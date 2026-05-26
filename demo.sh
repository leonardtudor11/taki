#!/usr/bin/env bash
# Taki — one-command demo.
#
# Boots the Flask backend (server.py) which serves both the static dashboard
# AND the live-cascade SSE endpoint. Fresh clone → ~60 seconds → live at
# http://localhost:5001
#
# Once it's open you get three buttons in the cascade toolbar:
#   ▶ replay cascade  — animate the cached brief.json (always works, offline)
#   ▶ live demo       — real backend run on the fixture cascade (no keys)
#   ⚡ live run ▾    — real backend run on a target via Bright Data + LLM
#                       (needs BRIGHTDATA_API_KEY + GCP_PROJECT_ID/GEMINI_API_KEY in .env)
#
# Usage:
#   ./demo.sh                    # default
#   TAKI_BACKEND_PORT=5050 ./demo.sh
#   PYTHON=python3.11 ./demo.sh
#
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
PORT=${TAKI_BACKEND_PORT:-5001}

say() { printf '\n\033[1;36m→ %s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
err() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

# 1. venv (idempotent — always reconciles deps with requirements.txt)
if [ ! -d .venv ]; then
  say "creating Python virtualenv (.venv)…"
  "$PYTHON" -m venv .venv
fi
say "syncing deps from requirements.txt…"
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

# 2. test sweep — proves the cascade still wires end-to-end
say "running test suite…"
.venv/bin/python -m pytest -q

# 3. brief — generate from fixtures if the dashboard's brief is missing/empty
if [ ! -s frontend/brief.json ]; then
  say "no frontend/brief.json found — generating fixture brief (no keys)…"
  .venv/bin/python run.py --demo
fi

# 4. unified server (static frontend + /api/run SSE endpoint)
if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  say "port ${PORT} already serving — reusing existing server"
else
  say "starting Taki backend on :${PORT} (static + /api/run SSE)…"
  TAKI_BACKEND_PORT="${PORT}" nohup .venv/bin/python server.py \
      >/tmp/taki-server.log 2>&1 &
  # give it a moment to bind
  for _ in 1 2 3 4 5 6 7 8; do
    if curl -sf "http://localhost:${PORT}/api/status" >/dev/null 2>&1; then break; fi
    sleep 0.25
  done
fi

# 5. report status + open browser
STATUS=$(curl -sf "http://localhost:${PORT}/api/status" || echo '{}')
URL="http://localhost:${PORT}/"
echo
ok "dashboard live at ${URL}"
echo "    · ▶ replay cascade  — animate the cached cascade (works offline)"
echo "    · ▶ live demo       — actual backend run on fixtures, no keys needed"
if echo "$STATUS" | grep -q '"live":true'; then
  echo "    · ⚡ live run ▾     — real Bright Data + LLM run (your .env is wired)"
else
  echo "    · ⚡ live run ▾     — disabled; fill .env (BRIGHTDATA_API_KEY + GCP_PROJECT_ID or GEMINI_API_KEY)"
fi
echo "    · dropped drawer    — every hallucination the grounding guard caught"
echo

if command -v open >/dev/null 2>&1; then
  open "${URL}"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${URL}"
fi

#!/usr/bin/env bash
# Taki — one-command demo.
#
# Boots the dashboard with the bundled brief and opens it in your browser.
# Fresh clone → ~60 seconds → live cascade at http://localhost:8000
#
# No API keys needed: the repo ships a real cached brief (frontend/brief.json),
# and `--demo` regenerates one from offline fixtures if it ever goes missing.
#
# Usage:
#   ./demo.sh           # default
#   PORT=8080 ./demo.sh # override port
#   PYTHON=python3.11 ./demo.sh
#
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
PORT=${PORT:-8000}

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

# 4. static server
if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  say "port ${PORT} already serving — reusing existing server"
else
  say "starting static server on :${PORT}…"
  (cd frontend && nohup .venv/bin/python -m http.server "${PORT}" >/tmp/taki-demo-server.log 2>&1 &)
  # give it a moment to bind
  for _ in 1 2 3 4 5; do
    if curl -sf "http://localhost:${PORT}/" >/dev/null 2>&1; then break; fi
    sleep 0.2
  done
fi

URL="http://localhost:${PORT}/"
echo
ok "dashboard live at ${URL}"
echo "    · cytoscape cascade graph: click a department to filter · hover edges to read handoffs"
echo "    · ▶ replay cascade: watch the pipeline animate from PII → guardrails → depts → assemble"
echo "    · dropped drawer: every hallucination the grounding guard caught, listed verbatim"
echo

# 5. open the browser if we have one
if command -v open >/dev/null 2>&1; then
  open "${URL}"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${URL}"
fi

#!/usr/bin/env bash
# One-command start on macOS / Linux: installs what is missing, checks the setup, starts the chat, opens the browser.
#   chmod +x start.sh && ./start.sh
set -e
cd "$(dirname "$0")"
PY=python3
command -v $PY >/dev/null 2>&1 || { echo "Python 3 is not installed. On macOS: install from https://www.python.org/downloads/ (3.11 or 3.12)."; exit 1; }
if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env created from .env.example. Fill MS_CLIENT_ID, MS_CLIENT_SECRET, APP_PASSWORD, SECRET_KEY (and ANTHROPIC_API_KEY), then run ./start.sh again."
  ${EDITOR:-open -t} .env 2>/dev/null || true
  exit 0
fi
if [ -d .git ] && [ "${AUTO_UPDATE:-1}" != "0" ] && command -v git >/dev/null 2>&1; then
  echo "== Checking for updates"; git pull --ff-only || echo "(update skipped: $?)"
fi
if [ ! -d .venv ]; then $PY -m venv .venv; fi
. .venv/bin/activate
pip install --quiet --disable-pip-version-check -r requirements.txt
if [ ! -d Agency/Templates ]; then
  echo "No Agency folder next to the code: writing the sample one (templates, example files)."
  python -m outreach.cli demo
fi
echo; echo "== Status =="; python -m outreach.cli status
PORT="${PORT:-8080}"
echo; echo "Starting the chat on http://localhost:$PORT  (Ctrl+C stops it)"
(sleep 2; open "http://localhost:$PORT" 2>/dev/null || xdg-open "http://localhost:$PORT" 2>/dev/null || true) &
python -m outreach.cli serve

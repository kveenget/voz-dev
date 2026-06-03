#!/usr/bin/env bash
# Lanzador para LaunchAgent (carga .env y ejecuta el agente en segundo plano).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
export VOZ_BACKGROUND=1
export VOZ_ACTIVATION=hotkey
if [[ -x venv/bin/python ]]; then
  exec venv/bin/python main.py
fi
exec python3 main.py

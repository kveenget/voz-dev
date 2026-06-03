#!/usr/bin/env bash
# voz-dev — desarrollo y servicio en segundo plano (Mac)
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
ORIG_PWD="$PWD"   # guardar ANTES de cd — es el directorio del proyecto del usuario
cd "$ROOT"
PY=python3
if [[ -x venv/bin/python ]]; then
  PY=venv/bin/python
fi

cmd="${1:-run}"

case "$cmd" in
  install)
    bash scripts/macos-install.sh
    ;;
  uninstall)
    LABEL="com.vozdev.agent"
    PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl unload -w "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    PIDF="$HOME/Library/Application Support/voz-dev/vozdev.pid"
    [[ -f "$PIDF" ]] && kill "$(cat "$PIDF")" 2>/dev/null || true
    pkill -f "${ROOT}/main.py" 2>/dev/null || true
    rm -f /tmp/vozdev_main.pid
    echo "Servicio desinstalado."
    ;;
  stop|kill-all)
    LABEL="com.vozdev.agent"
    PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl unload -w "$PLIST" 2>/dev/null || true
    PIDF="$HOME/Library/Application Support/voz-dev/vozdev.pid"
    [[ -f "$PIDF" ]] && kill "$(cat "$PIDF")" 2>/dev/null || true
    pkill -f "${ROOT}/main.py" 2>/dev/null || true
    pkill -f "${ROOT}/widget.py" 2>/dev/null || true
    if [[ -f /tmp/vozdev_widget.pid ]]; then
      kill "$(cat /tmp/vozdev_widget.pid)" 2>/dev/null || true
    fi
    rm -f /tmp/vozdev_main.pid /tmp/vozdev_widget.pid 2>/dev/null || true
    echo "✅ Todo voz-dev detenido (agente + widget + servicio)."
    echo "   Para que NO arranque al encender el Mac: ./dev.sh uninstall"
    ;;
  start)
    bash scripts/macos-install.sh
    ;;
  status)
    if launchctl print "gui/$(id -u)/com.vozdev.agent" &>/dev/null; then
      echo "✅ LaunchAgent cargado"
    else
      echo "⚠️  LaunchAgent no cargado"
    fi
    PIDF="$HOME/Library/Application Support/voz-dev/vozdev.pid"
    if [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "✅ Proceso activo PID $(cat "$PIDF") (fallback)"
    elif pgrep -f "${ROOT}/main.py" >/dev/null 2>&1; then
      echo "✅ Proceso main.py en ejecución"
    else
      echo "❌ No está corriendo — ejecuta: ./dev.sh install"
    fi
    ;;
  logs)
    tail -f "${TMPDIR:-/tmp}/vozdev.log"
    ;;
  test-hotkey)
    echo "Pulsa ⌥A o ⌘⇧U (10 s)…"
    "$PY" -c "
from voz.hotkey import start_hotkey_listener, esperar_hotkey, stop_hotkey_listener
import threading, time
start_hotkey_listener('option+a')
t = threading.Thread(target=esperar_hotkey, daemon=True)
t.start()
t.join(timeout=10)
stop_hotkey_listener()
print('Fin test')
"
    ;;
  now)
    exec "$PY" main.py --now "${2:-$ORIG_PWD}"
    ;;
  run|*)
    if [[ -x venv/bin/python ]]; then
      venv/bin/pip install -q -r requirements.txt 2>/dev/null || true
    fi
    if [[ "${VOZ_BACKGROUND:-}" != "1" ]] && [[ -f /tmp/vozdev_main.pid ]]; then
      OLD=$(cat /tmp/vozdev_main.pid 2>/dev/null || true)
      if [[ -n "$OLD" ]] && kill -0 "$OLD" 2>/dev/null; then
        echo "ℹ️  El servicio en segundo plano ya está activo (PID $OLD)."
        echo "   Pulsa ⌥A o clic en Mike. Logs: ./dev.sh logs"
        echo "   Para reinstalar: ./dev.sh install"
        exit 0
      fi
    fi
    exec "$PY" main.py
    ;;
esac

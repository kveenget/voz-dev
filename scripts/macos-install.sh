#!/usr/bin/env bash
# Instala voz-dev en segundo plano (Mac). Si LaunchAgent falla en Escritorio, usa fallback.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LABEL="com.vozdev.agent"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
SUPPORT="$HOME/Library/Application Support/voz-dev"
LOG_OUT="${TMPDIR:-/tmp}/vozdev.log"
LOG_ERR="${TMPDIR:-/tmp}/vozdev.err.log"
PID_FILE="$SUPPORT/vozdev.pid"
PY="$ROOT/venv/bin/python"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

echo "📦 Instalando voz-dev en segundo plano (Mac)…"

if [[ ! -x "$PY" ]]; then
  echo "Creando venv…"
  python3 -m venv venv
  PY="$ROOT/venv/bin/python"
fi
"$PY" -m pip install -q -r requirements.txt

mkdir -p "$SUPPORT" "$HOME/Library/LaunchAgents"
echo "$ROOT" > "$SUPPORT/project.path"

# Lanzador fuera del Escritorio (el plist solo referencia ~/Library)
cat > "$SUPPORT/run.sh" <<'RUNEOF'
#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cat "$DIR/project.path")"
export VOZ_BACKGROUND=1
export VOZ_ACTIVATION=hotkey
export PYTHONUNBUFFERED=1
cd "$ROOT" || exit 1
exec "$ROOT/venv/bin/python" "$ROOT/main.py"
RUNEOF
chmod +x "$SUPPORT/run.sh"

# Limpiar servicio anterior
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootout "${DOMAIN}" "$PLIST" 2>/dev/null || true
launchctl unload -w "$PLIST" 2>/dev/null || true
if [[ -f "$PID_FILE" ]]; then
  old="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$old" ]] && kill "$old" 2>/dev/null || true
fi
pkill -f "${ROOT}/main.py" 2>/dev/null || true
sleep 0.5

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${SUPPORT}/run.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${SUPPORT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_OUT}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_ERR}</string>
</dict>
</plist>
EOF

plutil -lint "$PLIST" >/dev/null || { echo "❌ plist inválido"; exit 1; }

INSTALLED=0
if launchctl bootstrap "${DOMAIN}" "$PLIST" 2>/dev/null; then
  launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
  launchctl kickstart -k "${DOMAIN}/${LABEL}" 2>/dev/null || true
  INSTALLED=1
  echo "✅ LaunchAgent cargado."
elif launchctl load -w "$PLIST" 2>/dev/null; then
  INSTALLED=1
  echo "✅ LaunchAgent cargado (modo load -w)."
fi

if [[ "$INSTALLED" -eq 0 ]]; then
  echo ""
  echo "⚠️  LaunchAgent no pudo cargarse (error 5 = común con proyecto en Escritorio)."
  echo "   Arrancando en segundo plano ahora (modo fallback)…"
  nohup "${SUPPORT}/run.sh" >>"$LOG_OUT" 2>>"$LOG_ERR" &
  echo $! >"$PID_FILE"
  INSTALLED=2
  echo "✅ Proceso en background PID $(cat "$PID_FILE")"
  echo ""
  if [[ "$ROOT" == *"/Desktop/"* ]]; then
    echo "   Para que arranque al reiniciar el Mac, haz UNA de estas:"
    echo "   1) Mueve la carpeta:  mv ~/Desktop/voz-dev ~/Developer/voz-dev"
    echo "      luego:  cd ~/Developer/voz-dev && ./dev.sh install"
    echo "   2) Ajustes → Privacidad → Acceso total al disco → activa Terminal"
    echo "      y vuelve a ejecutar: ./dev.sh install"
    echo ""
  fi
fi

sleep 2
echo ""
echo "   ⌥ + A  → widget + agente + saludo"
echo "   Clic en «Mike» arriba → igual"
echo "   Logs: ./dev.sh logs"
echo ""
echo "⚠️  Accesibilidad (para ⌥A en cualquier app):"
echo "   Ajustes → Privacidad → Accesibilidad → activa «Python»"
echo "   Ruta: ${PY}"
echo ""

open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
osascript -e 'display notification "Pulsa ⌥A para hablar con Mike." with title "Voz-dev"' 2>/dev/null || true

"""Herramientas macOS: apps, sistema, Spotify, notas, proyectos."""

import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

from agent_tools.constants import SHUTDOWN_SENTINEL
from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import abrir_en_editor


def register_mac_tools(project_root: str) -> None:
    _ = project_root
    tools = [
        (
            "abrir_app",
            "Abre una aplicación en la Mac",
            {"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]},
            _abrir_app,
        ),
        (
            "cerrar_app",
            "Cierra una aplicación",
            {"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]},
            _cerrar_app,
        ),
        (
            "abrir_url",
            "Abre una URL en el navegador",
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            _abrir_url,
        ),
        (
            "cambiar_volumen",
            "Cambia el volumen del sistema (0-100)",
            {"type": "object", "properties": {"nivel": {"type": "integer"}}, "required": ["nivel"]},
            _cambiar_volumen,
        ),
        (
            "apagar_asistente",
            "Cierra voz-dev. SOLO si el usuario pidió cerrar el asistente y confirmó.",
            {"type": "object", "properties": {}},
            _apagar_asistente,
        ),
        (
            "modo_oscuro",
            "Activa o desactiva modo oscuro del sistema",
            {
                "type": "object",
                "properties": {"activar": {"type": "boolean"}},
                "required": ["activar"],
            },
            _modo_oscuro,
        ),
        (
            "screenshot",
            "Captura interactiva al Escritorio (legacy; para analizar usa ver_pantalla)",
            {"type": "object", "properties": {}},
            _screenshot,
        ),
        (
            "bateria",
            "Consulta nivel de batería",
            {"type": "object", "properties": {}},
            _bateria,
        ),
        (
            "spotify",
            "Controla Spotify: play, pause, next, previous, play_cancion",
            {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "previous", "play_cancion"],
                    },
                    "cancion": {"type": "string"},
                },
                "required": ["accion"],
            },
            _spotify,
        ),
        (
            "crear_nota",
            "Crea nota en la app Notas",
            {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "contenido": {"type": "string"},
                },
                "required": ["titulo", "contenido"],
            },
            _crear_nota,
        ),
        (
            "recordatorio",
            "Crea recordatorio en Recordatorios",
            {
                "type": "object",
                "properties": {
                    "texto": {"type": "string"},
                    "fecha": {"type": "string", "description": "YYYY-MM-DD HH:MM opcional"},
                },
                "required": ["texto"],
            },
            _recordatorio,
        ),
        (
            "crear_proyecto",
            "Crea carpeta de proyecto en el Escritorio y abre en el editor",
            {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "tipo": {"type": "string", "enum": ["python", "node", "react", "vacio"]},
                },
                "required": ["nombre", "tipo"],
            },
            _crear_proyecto,
        ),
        (
            "leer_clipboard",
            "Lee el contenido actual del portapapeles",
            {"type": "object", "properties": {}},
            _leer_clipboard,
        ),
        (
            "escribir_clipboard",
            "Escribe texto al portapapeles",
            {
                "type": "object",
                "properties": {"texto": {"type": "string"}},
                "required": ["texto"],
            },
            _escribir_clipboard,
        ),
        (
            "notificar",
            "Muestra una notificación nativa de macOS (para avisar cuando termina una tarea larga)",
            {
                "type": "object",
                "properties": {
                    "mensaje": {"type": "string"},
                    "titulo": {"type": "string", "description": "Default: Ecov"},
                },
                "required": ["mensaje"],
            },
            _notificar,
        ),
        (
            "archivo_activo_cursor",
            "Detecta qué archivo tiene abierto el usuario en Cursor o VS Code",
            {"type": "object", "properties": {}},
            _archivo_activo_cursor,
        ),
        (
            "guardar_nota_sesion",
            "Guarda un resumen de lo que se hizo en esta sesión. Úsalo al despedirte o cuando el usuario lo pida.",
            {
                "type": "object",
                "properties": {
                    "resumen": {"type": "string"},
                    "proyecto": {"type": "string"},
                },
                "required": ["resumen"],
            },
            _guardar_nota_sesion,
        ),
        (
            "ver_historial",
            "Muestra el historial de sesiones anteriores guardadas",
            {
                "type": "object",
                "properties": {
                    "sesiones": {"type": "integer", "description": "Cuántas sesiones mostrar (default 5)"},
                },
                "required": [],
            },
            _ver_historial,
        ),
    ]
    for name, desc, params, handler in tools:
        register(ToolSpec(name, desc, params, handler, "mac"))


def _abrir_app(args: dict, ctx: ToolContext) -> str:
    subprocess.Popen(["open", "-a", args.get("app", "")])
    return "ok"


def _cerrar_app(args: dict, ctx: ToolContext) -> str:
    subprocess.run(["pkill", "-x", args.get("app", "")])
    return "ok"


def _abrir_url(args: dict, ctx: ToolContext) -> str:
    subprocess.Popen(["open", args.get("url", "")])
    return "ok"


def _cambiar_volumen(args: dict, ctx: ToolContext) -> str:
    subprocess.run(["osascript", "-e", f"set volume output volume {args.get('nivel', 50)}"])
    return "ok"


def _apagar_asistente(args: dict, ctx: ToolContext) -> str:
    ctx.set_widget_state("idle")
    print("\n👋 Cerrando asistente...")
    return SHUTDOWN_SENTINEL


def _modo_oscuro(args: dict, ctx: ToolContext) -> str:
    val = "true" if args.get("activar", True) else "false"
    script = f'tell app "System Events" to tell appearance preferences to set dark mode to {val}'
    subprocess.run(["osascript", "-e", script])
    return "ok"


def _screenshot(args: dict, ctx: ToolContext) -> str:
    subprocess.Popen(["screencapture", "-i", os.path.expanduser("~/Desktop/screenshot.png")])
    return "Captura guardada en ~/Desktop/screenshot.png"


def _bateria(args: dict, ctx: ToolContext) -> str:
    result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    return result.stdout or "Sin datos"


def _spotify(args: dict, ctx: ToolContext) -> str:
    accion = args.get("accion", "")
    cancion = args.get("cancion", "")
    if accion == "play":
        subprocess.run(["osascript", "-e", 'tell app "Spotify" to play'])
    elif accion == "pause":
        subprocess.run(["osascript", "-e", 'tell app "Spotify" to pause'])
    elif accion == "next":
        subprocess.run(["osascript", "-e", 'tell app "Spotify" to next track'])
    elif accion == "previous":
        subprocess.run(["osascript", "-e", 'tell app "Spotify" to previous track'])
    elif accion == "play_cancion" and cancion:
        return _spotify_play_cancion(cancion, ctx)
    return "ok"


def _spotify_play_cancion(cancion: str, ctx: ToolContext) -> str:
    import re
    track_uri = None
    track_name = cancion
    artist_name = ""

    # 1. Spotify Web API (si hay credenciales)
    sp_client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
    sp_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    if sp_client_id and sp_client_secret:
        try:
            creds = base64.b64encode(f"{sp_client_id}:{sp_client_secret}".encode()).decode()
            req = urllib.request.Request(
                "https://accounts.spotify.com/api/token",
                data=b"grant_type=client_credentials",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urllib.request.urlopen(req, context=ctx.ssl_context) as r:
                token = json.loads(r.read()).get("access_token", "")
            q = urllib.parse.quote(cancion)
            search_req = urllib.request.Request(
                f"https://api.spotify.com/v1/search?q={q}&type=track&limit=1",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(search_req, context=ctx.ssl_context) as r:
                items = json.loads(r.read()).get("tracks", {}).get("items", [])
            if items:
                track_uri = items[0]["uri"]
                track_name = items[0]["name"]
                artist_name = items[0]["artists"][0]["name"]
        except Exception as e:
            print(f"⚠️ Spotify API: {e}")

    # 2. Sin credenciales: GPT-4.1 mini busca el URI exacto en la web
    if not track_uri and ctx.openai_api_key:
        try:
            print(f"🔍 Buscando URI de Spotify para: {cancion}")
            from openai import OpenAI
            client = OpenAI(api_key=ctx.openai_api_key)
            resp = client.responses.create(
                model="gpt-4.1-mini",
                tools=[{"type": "web_search_preview"}],
                input=(
                    f"Find the exact Spotify URI for the song '{cancion}'. "
                    "Search open.spotify.com or Google. "
                    "Reply with ONLY the URI like: spotify:track:4iJyoBOLtHqaWYs3vyWs68 "
                    "No other text, no explanation."
                ),
            )
            for bloque in resp.output:
                if getattr(bloque, "type", "") == "message":
                    for parte in getattr(bloque, "content", []):
                        if getattr(parte, "type", "") == "output_text":
                            m = re.search(r"spotify:track:[A-Za-z0-9]{22}", parte.text)
                            if m:
                                track_uri = m.group(0)
                                break
        except Exception as e:
            print(f"⚠️ GPT-4.1 Spotify: {e}")

    # 3. Play si tenemos URI
    if track_uri:
        subprocess.run(
            ["osascript", "-e", f'tell application "Spotify" to play track "{track_uri}"']
        )
        label = f"{track_name} de {artist_name}" if artist_name else track_name
        return f"Reproduciendo {label}"

    # 4. Fallback: abrir búsqueda, sin auto-play
    q = urllib.parse.quote(cancion)
    subprocess.Popen(["open", f"spotify:search:{q}"])
    return f"Abrí la búsqueda de '{cancion}' en Spotify. Selecciona la canción."


def _crear_nota(args: dict, ctx: ToolContext) -> str:
    titulo = args.get("titulo", "Nota")
    contenido = args.get("contenido", "")
    script = f"""
    tell application "Notes"
        activate
        tell account "iCloud"
            make new note with properties {{name:"{titulo}", body:"{titulo}\\n\\n{contenido}"}}
        end tell
    end tell
    """
    subprocess.run(["osascript", "-e", script])
    return f"Nota '{titulo}' creada"


def _recordatorio(args: dict, ctx: ToolContext) -> str:
    texto = args.get("texto", "")
    fecha = args.get("fecha", "")
    if fecha:
        script = f"""
        tell application "Reminders"
            activate
            make new reminder with properties {{name:"{texto}", due date:date "{fecha}"}}
        end tell
        """
    else:
        script = f"""
        tell application "Reminders"
            activate
            make new reminder with properties {{name:"{texto}"}}
        end tell
        """
    subprocess.run(["osascript", "-e", script])
    return f"Recordatorio '{texto}' creado"


def _leer_clipboard(args: dict, ctx: ToolContext) -> str:
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    contenido = result.stdout
    return contenido if contenido else "(portapapeles vacío)"


def _escribir_clipboard(args: dict, ctx: ToolContext) -> str:
    texto = args.get("texto", "")
    subprocess.run(["pbcopy"], input=texto.encode())
    return f"Copiado al portapapeles ({len(texto)} caracteres)"


def _notificar(args: dict, ctx: ToolContext) -> str:
    mensaje = args.get("mensaje", "")
    titulo = args.get("titulo", "Ecov")
    safe_msg = mensaje.replace('"', "'")
    safe_titulo = titulo.replace('"', "'")
    script = f'display notification "{safe_msg}" with title "{safe_titulo}"'
    subprocess.run(["osascript", "-e", script])
    return "ok"


def _archivo_activo_cursor(args: dict, ctx: ToolContext) -> str:
    import re as _re
    # Intentar por título de ventana (Cursor/VS Code muestran el filename)
    for proceso in ["Cursor", "Code"]:
        script = f"""
        tell application "System Events"
            if exists process "{proceso}" then
                return name of window 1 of process "{proceso}"
            end if
        end tell
        """
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            titulo = r.stdout.strip().lstrip("● ").strip()
            partes = _re.split(r"\s[—\-]\s", titulo)
            if partes:
                nombre = partes[0].strip()
                root = ctx.project_root
                for dirpath, _, files in os.walk(root):
                    if nombre in files:
                        return os.path.join(dirpath, nombre)
                return f"{nombre} (en {proceso}, no encontrado en {root})"

    # Fallback: archivos de código abiertos por Cursor vía lsof
    try:
        ext_pat = _re.compile(
            r'\.(py|js|ts|jsx|tsx|go|rs|java|c|cpp|h|json|yaml|yml|md|sh|rb|swift|kt)$'
        )
        r2 = subprocess.run(["lsof", "-c", "Cursor", "-n", "-P"],
                            capture_output=True, text=True, timeout=5)
        archivos = sorted({
            p for line in r2.stdout.splitlines()
            if len((parts := line.split())) > 8
            and ext_pat.search(p := parts[-1])
            and os.path.isfile(p)
        })[:5]
        if archivos:
            return "Archivos abiertos en Cursor:\n" + "\n".join(archivos)
    except Exception:
        pass
    return "No encontré archivo activo en Cursor/VS Code"


_HISTORIAL_FILE = os.path.expanduser("~/.vozdev/historial.jsonl")


def _guardar_nota_sesion(args: dict, ctx: ToolContext) -> str:
    import json as _json
    resumen = args.get("resumen", "").strip()
    proyecto = args.get("proyecto", os.path.basename(ctx.project_root))
    if not resumen:
        return "Falta el resumen."
    os.makedirs(os.path.dirname(_HISTORIAL_FILE), exist_ok=True)
    entrada = {
        "fecha": time.strftime("%Y-%m-%d %H:%M"),
        "proyecto": proyecto,
        "resumen": resumen,
    }
    with open(_HISTORIAL_FILE, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entrada, ensure_ascii=False) + "\n")
    return f"Sesión guardada en historial ({proyecto})"


def _ver_historial(args: dict, ctx: ToolContext) -> str:
    import json as _json
    n = int(args.get("sesiones", 5))
    if not os.path.isfile(_HISTORIAL_FILE):
        return "No hay historial guardado todavía."
    with open(_HISTORIAL_FILE, encoding="utf-8") as f:
        lineas = f.readlines()
    entradas = []
    for l in lineas:
        try:
            entradas.append(_json.loads(l))
        except Exception:
            pass
    recientes = entradas[-n:][::-1]
    if not recientes:
        return "Historial vacío."
    partes = []
    for e in recientes:
        partes.append(f"[{e.get('fecha','')}] {e.get('proyecto','')}\n{e.get('resumen','')}")
    return "\n\n---\n".join(partes)


def _crear_proyecto(args: dict, ctx: ToolContext) -> str:
    nombre_p = args.get("nombre", "proyecto")
    tipo = args.get("tipo", "python")
    ruta = os.path.expanduser(f"~/Desktop/{nombre_p}")
    os.makedirs(ruta, exist_ok=True)
    if tipo == "python":
        subprocess.run(f"python3 -m venv {ruta}/venv", shell=True)
        open(os.path.join(ruta, "main.py"), "w").close()
        with open(os.path.join(ruta, "README.md"), "w") as f:
            f.write(f"# {nombre_p}\n")
    elif tipo == "react":
        subprocess.Popen(
            f"cd ~/Desktop && npx create-react-app {nombre_p}",
            shell=True,
        )
    elif tipo == "node":
        subprocess.run(f"cd {ruta} && npm init -y && touch index.js", shell=True)
    abrir_en_editor(ruta)
    return f"Proyecto {nombre_p} en ~/Desktop/{nombre_p}"

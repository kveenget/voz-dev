"""Captura de pantalla + análisis con modelo vision (OpenAI)."""

import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

_FLASH_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "..", "voz", "screen_flash.py"
)


def _lanzar_flash():
    try:
        subprocess.Popen(
            [sys.executable, _FLASH_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass

from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import truncar_salida

VISION_MODEL = os.getenv("VOZ_VISION_MODEL", "gpt-4o-mini")
VISION_PROMPT_DEFAULT = (
    "Describe en español lo que ves en esta captura de pantalla de una Mac. "
    "Si hay errores de código, terminal o IDE, transcríbelos literalmente. "
    "Si hay UI, resume elementos relevantes. Sé concreto y breve."
)


def register_vision_tools(project_root: str) -> None:
    _ = project_root
    spec = ToolSpec(
        "ver_pantalla",
        "Captura la pantalla del Mac y analiza qué se ve (errores, terminal, IDE, UI). "
        "Úsala cuando pidan ver la pantalla, un error en pantalla, o qué hay visible.",
        {
            "type": "object",
            "properties": {
                "pregunta": {
                    "type": "string",
                    "description": "Qué buscar en la captura (opcional)",
                },
                "pantalla_completa": {
                    "type": "boolean",
                    "description": "True = pantalla completa (default). False = ventana frontal.",
                },
            },
            "required": [],
        },
        _ver_pantalla,
        "vision",
    )
    register(spec)
    register(
        ToolSpec(
            "analizar_pantalla",
            "Igual que ver_pantalla: captura y analiza la pantalla.",
            {
                "type": "object",
                "properties": {
                    "pregunta": {"type": "string"},
                    "pantalla_completa": {"type": "boolean"},
                },
                "required": [],
            },
            _ver_pantalla,
            "vision",
        )
    )


def _id_ventana_frontal() -> int:
    script = (
        'tell application "System Events" to get the id of window 1 '
        "of (first application process whose frontmost is true)"
    )
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode != 0:
        raise RuntimeError("No pude detectar la ventana frontal.")
    return int(r.stdout.strip())


def _capturar_pantalla(pantalla_completa: bool = True) -> str:
    fd, path = tempfile.mkstemp(suffix=".png", prefix="vozdev_screen_")
    os.close(fd)
    try:
        if pantalla_completa:
            cmd = ["screencapture", "-x", path]
        else:
            wid = _id_ventana_frontal()
            cmd = ["screencapture", "-x", "-l", str(wid), path]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            raise RuntimeError(
                f"screencapture falló ({r.returncode}). "
                f"Activa Grabación de pantalla para Terminal/Python en Ajustes. {err}"
            )
        if not os.path.isfile(path) or os.path.getsize(path) < 100:
            raise RuntimeError("La captura está vacía o no se guardó.")
        return path
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


def _analizar_con_vision(
    image_path: str,
    pregunta: str,
    ctx: ToolContext,
) -> str:
    if not ctx.openai_api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")

    with open(image_path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode("ascii")

    prompt = pregunta.strip() or VISION_PROMPT_DEFAULT
    body = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        "max_tokens": 900,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {ctx.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ctx.ssl_context, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Vision API {e.code}: {err_body[:500]}") from e

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Respuesta vision inesperada: {data!s}") from e


def _ver_pantalla(args: dict, ctx: ToolContext) -> str:
    pantalla_completa = args.get("pantalla_completa", True)
    if isinstance(pantalla_completa, str):
        pantalla_completa = pantalla_completa.lower() not in ("0", "false", "no")

    pregunta = args.get("pregunta", "") or ""
    path = None
    try:
        ctx.set_widget_state("capturing")
        path = _capturar_pantalla(pantalla_completa=bool(pantalla_completa))
        _lanzar_flash()
        ctx.set_widget_state("analyzing")
        texto = _analizar_con_vision(path, pregunta, ctx)
        ctx.set_widget_state("thinking")
        return truncar_salida(
            f"[Captura de pantalla analizada]\n{texto}",
            4500,
        )
    except Exception as e:
        ctx.set_widget_state("idle")
        return f"No pude ver la pantalla: {e}"
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

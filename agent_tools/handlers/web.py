"""Búsqueda web: DuckDuckGo instant answer + agente GPT-4.1 con web search real."""

import json
import subprocess
import urllib.parse
import urllib.request

from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register


def register_web_tools(project_root: str) -> None:
    _ = project_root
    register(
        ToolSpec(
            "buscar_web",
            "Abre una búsqueda en el navegador",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            _buscar_web,
            "web",
        )
    )
    register(
        ToolSpec(
            "buscar_y_responder",
            "Busca en internet y devuelve respuesta con datos actuales (precios, noticias, etc.)",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            _buscar_y_responder,
            "web",
        )
    )
    register(
        ToolSpec(
            "investigar",
            (
                "Investiga cualquier pregunta con información real y actualizada usando GPT-4.1 "
                "con búsqueda web. Úsala para: precios, noticias, documentación, comparativas, "
                "cómo hacer algo, errores desconocidos, librerías, APIs, etc. "
                "Devuelve una respuesta completa y precisa lista para leer en voz alta."
            ),
            {
                "type": "object",
                "properties": {
                    "pregunta": {
                        "type": "string",
                        "description": "La pregunta o tema a investigar, en lenguaje natural.",
                    }
                },
                "required": ["pregunta"],
            },
            _investigar,
            "web",
        )
    )


def _investigar(args: dict, ctx: ToolContext) -> str:
    pregunta = args.get("pregunta", "").strip()
    if not pregunta:
        return "Falta la pregunta."
    print(f"🔬 Investigando con GPT-4.1: {pregunta}")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=ctx.openai_api_key)
        resp = client.responses.create(
            model="gpt-4.1",
            tools=[{"type": "web_search_preview"}],
            input=pregunta,
        )
        # Extraer el texto de la respuesta
        texto = ""
        for bloque in resp.output:
            if getattr(bloque, "type", "") == "message":
                for parte in getattr(bloque, "content", []):
                    if getattr(parte, "type", "") == "output_text":
                        texto += parte.text
        return texto.strip() or "No obtuve respuesta."
    except Exception as e:
        return f"Error al investigar: {e}"


def _buscar_web(args: dict, ctx: ToolContext) -> str:
    query = args.get("query", "").replace(" ", "+")
    subprocess.Popen(["open", f"https://www.google.com/search?q={query}"])
    return "ok"


def _buscar_y_responder(args: dict, ctx: ToolContext) -> str:
    query = args.get("query", "")
    print(f"🔍 Buscando: {query}")
    try:
        q = urllib.parse.quote(query)
        req = urllib.request.Request(
            f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1",
            headers={"User-Agent": "Mozilla/5.0 VozDev/1.0"},
        )
        with urllib.request.urlopen(req, context=ctx.ssl_context, timeout=5) as r:
            data = json.loads(r.read())
        respuesta = ""
        if data.get("AbstractText"):
            respuesta = data["AbstractText"]
        elif data.get("Answer"):
            respuesta = data["Answer"]
        elif data.get("Definition"):
            respuesta = data["Definition"]
        elif data.get("RelatedTopics"):
            temas = [
                t.get("Text")
                for t in data["RelatedTopics"][:3]
                if isinstance(t, dict) and t.get("Text")
            ]
            respuesta = " | ".join(temas)
        if respuesta:
            return respuesta[:500]
        q2 = query.replace(" ", "+")
        subprocess.Popen(["open", f"https://www.google.com/search?q={q2}"])
        return f"No encontré respuesta directa; abrí Google para '{query}'"
    except Exception as e:
        q2 = query.replace(" ", "+")
        subprocess.Popen(["open", f"https://www.google.com/search?q={q2}"])
        return f"Error al buscar: {e}"

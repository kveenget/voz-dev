"""
Notas de voz — crea, edita, lee y busca notas en markdown.
Las notas viven en VOZ_NOTES_DIR (default ~/Documents/VozNotas/).
Opcionalmente puede escribir también en Apple Notes vía osascript.
"""

import os
import re
import subprocess
from datetime import datetime

from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import truncar_salida

NOTES_DIR = os.path.expanduser(
    os.getenv("VOZ_NOTES_DIR", "~/Documents/VozNotas")
)


def _dir() -> str:
    os.makedirs(NOTES_DIR, exist_ok=True)
    return NOTES_DIR


def _slug(titulo: str) -> str:
    """Título → nombre de archivo seguro."""
    s = titulo.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:60] or "nota"


def _nota_path(titulo: str) -> str:
    return os.path.join(_dir(), _slug(titulo) + ".md")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def register_notes_tools(project_root: str) -> None:
    _ = project_root

    register(ToolSpec(
        "nota_crear",
        (
            "Crea una nota nueva con título y contenido. "
            "Úsala cuando el usuario diga 'anota', 'escribe', 'guarda esto', 'toma nota de...'."
        ),
        {
            "type": "object",
            "properties": {
                "titulo": {
                    "type": "string",
                    "description": "Título de la nota (se usa como nombre de archivo)",
                },
                "contenido": {
                    "type": "string",
                    "description": "Texto de la nota",
                },
                "apple_notes": {
                    "type": "boolean",
                    "description": "Si true, también crea la nota en Apple Notes (default false)",
                },
            },
            "required": ["titulo", "contenido"],
        },
        _nota_crear,
        "notes",
    ))

    register(ToolSpec(
        "nota_agregar",
        (
            "Agrega texto al final de una nota existente. "
            "Úsala cuando el usuario diga 'agrega a la nota X', 'añade esto', 'escribe también...'"
        ),
        {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título de la nota a la que agregar"},
                "contenido": {"type": "string", "description": "Texto a agregar"},
            },
            "required": ["titulo", "contenido"],
        },
        _nota_agregar,
        "notes",
    ))

    register(ToolSpec(
        "nota_leer",
        "Lee el contenido de una nota por su título.",
        {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título (o parte del título) de la nota"},
            },
            "required": ["titulo"],
        },
        _nota_leer,
        "notes",
    ))

    register(ToolSpec(
        "nota_listar",
        "Lista todas las notas guardadas con su fecha de creación.",
        {
            "type": "object",
            "properties": {
                "limite": {"type": "integer", "description": "Máximo de notas a mostrar (default 20)"},
            },
            "required": [],
        },
        _nota_listar,
        "notes",
    ))

    register(ToolSpec(
        "nota_buscar",
        "Busca notas que contengan una palabra o frase.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Palabra o frase a buscar"},
            },
            "required": ["query"],
        },
        _nota_buscar,
        "notes",
    ))

    register(ToolSpec(
        "nota_borrar",
        "Elimina una nota por título.",
        {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título de la nota a eliminar"},
            },
            "required": ["titulo"],
        },
        _nota_borrar,
        "notes",
    ))


# ── Implementaciones ────────────────────────────────────────────────────────


def _nota_crear(args: dict, ctx: ToolContext) -> str:
    titulo = (args.get("titulo") or "").strip()
    contenido = (args.get("contenido") or "").strip()
    if not titulo:
        return "Necesito un título para la nota"
    if not contenido:
        return "La nota está vacía"

    path = _nota_path(titulo)
    encabezado = f"# {titulo}\n_Creada: {_ts()}_\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(encabezado + contenido + "\n")

    if args.get("apple_notes"):
        _escribir_apple_notes(titulo, contenido)

    return f"Nota '{titulo}' guardada en {path}"


def _nota_agregar(args: dict, ctx: ToolContext) -> str:
    titulo = (args.get("titulo") or "").strip()
    contenido = (args.get("contenido") or "").strip()
    if not titulo or not contenido:
        return "Necesito el título y el texto a agregar"

    path = _encontrar_nota(titulo)
    if not path:
        # Si no existe, la crea
        return _nota_crear({"titulo": titulo, "contenido": contenido}, ctx)

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n_Actualizada: {_ts()}_\n{contenido}\n")

    return f"Agregado a '{titulo}'"


def _nota_leer(args: dict, ctx: ToolContext) -> str:
    titulo = (args.get("titulo") or "").strip()
    if not titulo:
        return "Dime el título de la nota"

    path = _encontrar_nota(titulo)
    if not path:
        return f"No encontré ninguna nota con '{titulo}'. Usa nota_listar para ver las disponibles."

    with open(path, encoding="utf-8") as f:
        contenido = f.read()

    return truncar_salida(contenido, 3000)


def _nota_listar(args: dict, ctx: ToolContext) -> str:
    d = _dir()
    archivos = sorted(
        [f for f in os.listdir(d) if f.endswith(".md")],
        key=lambda f: os.path.getmtime(os.path.join(d, f)),
        reverse=True,
    )
    limite = int(args.get("limite", 20))
    archivos = archivos[:limite]

    if not archivos:
        return f"No hay notas en {d}"

    lineas = [f"Notas en {d}:\n"]
    for f in archivos:
        path = os.path.join(d, f)
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        nombre = f[:-3].replace("-", " ").title()
        lineas.append(f"  • {nombre} ({mtime})")

    return "\n".join(lineas)


def _nota_buscar(args: dict, ctx: ToolContext) -> str:
    query = (args.get("query") or "").strip().lower()
    if not query:
        return "Dime qué buscar"

    d = _dir()
    resultados = []
    for f in os.listdir(d):
        if not f.endswith(".md"):
            continue
        path = os.path.join(d, f)
        with open(path, encoding="utf-8") as fh:
            texto = fh.read()
        if query in texto.lower():
            nombre = f[:-3].replace("-", " ").title()
            # Extraer línea con el match para contexto
            for linea in texto.splitlines():
                if query in linea.lower():
                    resultados.append(f"  • {nombre}: …{linea.strip()[:80]}…")
                    break

    if not resultados:
        return f"No encontré notas con '{query}'"
    return f"Encontré {len(resultados)} nota(s) con '{query}':\n" + "\n".join(resultados)


def _nota_borrar(args: dict, ctx: ToolContext) -> str:
    titulo = (args.get("titulo") or "").strip()
    if not titulo:
        return "Dime el título de la nota a borrar"

    path = _encontrar_nota(titulo)
    if not path:
        return f"No encontré ninguna nota con '{titulo}'"

    os.remove(path)
    return f"Nota '{titulo}' eliminada"


def _encontrar_nota(titulo: str) -> str | None:
    """Busca un archivo .md por título exacto o parcial."""
    d = _dir()
    slug = _slug(titulo)

    # Exacto primero
    exact = os.path.join(d, slug + ".md")
    if os.path.isfile(exact):
        return exact

    # Búsqueda parcial
    titulo_lower = titulo.lower()
    for f in os.listdir(d):
        if not f.endswith(".md"):
            continue
        nombre = f[:-3].replace("-", " ")
        if titulo_lower in nombre or nombre in titulo_lower:
            return os.path.join(d, f)

    return None


def _escribir_apple_notes(titulo: str, contenido: str) -> None:
    """Crea la nota también en Apple Notes vía osascript."""
    script = f'''
    tell application "Notes"
        make new note at folder "Notes" with properties {{
            name: "{titulo.replace('"', '')}",
            body: "{contenido.replace('"', '').replace(chr(10), "\\n")}"
        }}
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], timeout=10, capture_output=True)
    except Exception:
        pass

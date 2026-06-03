"""Herramientas de IDE / repo — núcleo tipo Cursor."""

import os
import subprocess

from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import (
    abrir_en_editor,
    detectar_comando_pruebas,
    resolver_directorio,
    run_shell,
    truncar_salida,
)


def _path_en_proyecto(ctx: ToolContext, ruta: str) -> str:
    path = os.path.expanduser(ruta)
    if os.path.isabs(path):
        return os.path.realpath(path)
    # Ruta relativa: siempre dentro del proyecto activo
    root = os.path.realpath(resolver_directorio(ctx))
    real = os.path.realpath(os.path.join(root, path))
    if not real.startswith(root + os.sep) and real != root:
        raise ValueError(f"Ruta fuera del proyecto ({root}): {path}")
    return real


def _registrar_ide_tools(project_root: str) -> None:
    pr = project_root

    register(ToolSpec(
        "ejecutar_terminal",
        "Ejecuta un comando bash en el repo SIN abrir la app Terminal. "
        "NO uses para revisar o editar código (usa leer_archivo, editar_archivo, buscar_codigo).",
        {
            "type": "object",
            "properties": {
                "comando": {"type": "string"},
                "directorio": {"type": "string", "description": f"Default: {pr}"},
                "mostrar_terminal": {
                    "type": "boolean",
                    "description": "True solo si el usuario pide ver Terminal abierta",
                },
            },
            "required": ["comando"],
        },
        _ejecutar_terminal,
        "ide",
    ))
    register(ToolSpec(
        "ejecutar_pruebas",
        "Corre tests (pytest, npm test, cargo test) y devuelve salida.",
        {
            "type": "object",
            "properties": {
                "comando": {"type": "string"},
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _ejecutar_pruebas,
        "ide",
    ))
    register(ToolSpec(
        "revisar_codigo",
        "Revisa un archivo del proyecto (lee el contenido). NO abre Terminal. "
        "Úsala cuando pidan revisar, mirar o analizar código en un archivo.",
        {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ej: main.py"},
                "max_lineas": {"type": "integer"},
            },
            "required": ["ruta"],
        },
        _leer_archivo,
        "ide",
    ))
    register(ToolSpec(
        "leer_archivo",
        "Lee un archivo del proyecto. NO abre Terminal.",
        {
            "type": "object",
            "properties": {
                "ruta": {"type": "string"},
                "max_lineas": {"type": "integer"},
            },
            "required": ["ruta"],
        },
        _leer_archivo,
        "ide",
    ))
    register(ToolSpec(
        "escribir_archivo",
        "Crea o reemplaza un archivo completo. Para cambios pequeños prefiere editar_archivo.",
        {
            "type": "object",
            "properties": {
                "ruta": {"type": "string"},
                "contenido": {"type": "string"},
            },
            "required": ["ruta", "contenido"],
        },
        _escribir_archivo,
        "ide",
    ))
    register(ToolSpec(
        "editar_archivo",
        "Modifica código existente: reemplaza un fragmento por otro. Lee el archivo antes si no lo tienes.",
        {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ej: main.py"},
                "buscar": {"type": "string", "description": "Texto exacto a reemplazar (incluye espacios)"},
                "reemplazar": {"type": "string", "description": "Texto nuevo"},
                "todas": {
                    "type": "boolean",
                    "description": "True = reemplazar todas las ocurrencias",
                },
            },
            "required": ["ruta", "buscar", "reemplazar"],
        },
        _editar_archivo,
        "ide",
    ))
    register(ToolSpec(
        "buscar_codigo",
        "Busca texto o patrón en el repo (rg/grep). Útil antes de refactors.",
        {
            "type": "object",
            "properties": {
                "patron": {"type": "string"},
                "directorio": {"type": "string"},
                "max_resultados": {"type": "integer"},
            },
            "required": ["patron"],
        },
        _buscar_codigo,
        "coding",
    ))
    register(ToolSpec(
        "listar_directorio",
        "Lista archivos y carpetas del proyecto o subcarpeta.",
        {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Subcarpeta relativa, default raíz"},
                "profundidad": {"type": "integer", "description": "Niveles (default 3)"},
            },
            "required": [],
        },
        _listar_directorio,
        "coding",
    ))
    register(ToolSpec(
        "abrir_en_vscode",
        "Abre un archivo o carpeta del proyecto en Cursor o VS Code. Ruta relativa al repo, ej: main.py, agent_tools/handlers/ide.py",
        {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Archivo o carpeta relativa al proyecto, ej: main.py",
                },
            },
            "required": ["ruta"],
        },
        _abrir_en_vscode,
        "ide",
    ))
    register(ToolSpec(
        "abrir_archivo",
        "Igual que abrir_en_vscode: abre un archivo en Cursor/VS Code (ruta relativa, ej: widget.py).",
        {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ej: main.py, dev.sh"},
            },
            "required": ["ruta"],
        },
        _abrir_en_vscode,
        "ide",
    ))
    register(ToolSpec(
        "dictar_en_archivo",
        "Escribe texto dictado por voz directamente en un archivo. "
        "append = agregar al final (default). reemplazar = sobreescribir el archivo.",
        {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Archivo destino"},
                "texto": {"type": "string", "description": "Texto dictado a escribir"},
                "modo": {
                    "type": "string",
                    "enum": ["append", "reemplazar"],
                    "description": "append (default) o reemplazar",
                },
            },
            "required": ["ruta", "texto"],
        },
        _dictar_en_archivo,
        "ide",
    ))


def register_ide_tools(project_root: str) -> None:
    _registrar_ide_tools(project_root)


def _abrir_terminal_mac(cwd: str, comando: str) -> None:
    linea = f"cd {cwd} && {comando}"
    script = f'''
    tell application "Terminal"
        activate
        do script "{linea}"
    end tell
    '''
    subprocess.run(["osascript", "-e", script])


def _ejecutar_terminal(args: dict, ctx: ToolContext) -> str:
    cmd = args.get("comando", "")
    cwd = resolver_directorio(ctx, args.get("directorio"))
    mostrar = bool(args.get("mostrar_terminal", False))
    if mostrar:
        _abrir_terminal_mac(cwd, cmd)
    result = run_shell(cmd, cwd)
    output = truncar_salida(result.stdout or result.stderr)
    if result.returncode != 0:
        return f"Error {result.returncode}:\n{output}"
    return output or "OK"


def _ejecutar_pruebas(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    cmd = args.get("comando") or detectar_comando_pruebas(cwd)
    ctx.set_widget_state("thinking")
    result = run_shell(cmd, cwd, timeout=300)
    output = truncar_salida(result.stdout or result.stderr)
    if result.returncode == 0:
        return f"Tests OK ({cmd}):\n{output}"
    return f"Tests fallaron ({cmd}):\n{output}"


def _leer_archivo(args: dict, ctx: ToolContext) -> str:
    max_lineas = int(args.get("max_lineas", 400))
    path = _path_en_proyecto(ctx, args.get("ruta", ""))
    if not os.path.isfile(path):
        return f"No encontré: {path}"
    lineas = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, linea in enumerate(f):
            if i >= max_lineas:
                lineas.append(f"… ({max_lineas} líneas)")
                break
            lineas.append(linea.rstrip("\n"))
    return truncar_salida(f"{path}:\n" + "\n".join(lineas), 4000)


def _escribir_archivo(args: dict, ctx: ToolContext) -> str:
    path = _path_en_proyecto(ctx, args.get("ruta", ""))
    contenido = args.get("contenido", "")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(contenido)
    return f"Escrito {path} ({len(contenido)} caracteres)"


def _editar_archivo(args: dict, ctx: ToolContext) -> str:
    path = _path_en_proyecto(ctx, args.get("ruta", ""))
    if not os.path.isfile(path):
        return f"No encontré: {path}"
    buscar = args.get("buscar", "")
    reemplazar = args.get("reemplazar", "")
    todas = bool(args.get("todas", False))
    if not buscar:
        return "Falta el texto a buscar."
    with open(path, encoding="utf-8", errors="replace") as f:
        contenido = f.read()
    count = contenido.count(buscar)
    if count == 0:
        return f"No encontré ese fragmento en {path}. Lee el archivo y vuelve a intentar."
    if count > 1 and not todas:
        return (
            f"Hay {count} coincidencias en {path}. Sé más específico o usa todas=true."
        )
    nuevo = contenido.replace(buscar, reemplazar, -1 if todas else 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(nuevo)
    abrir_en_editor(path)
    return f"Editado {path}: {count if todas else 1} reemplazo(s). Abierto en el editor."


def _buscar_codigo(args: dict, ctx: ToolContext) -> str:
    patron = args.get("patron", "")
    cwd = resolver_directorio(ctx, args.get("directorio"))
    max_res = int(args.get("max_resultados", 40))
    if subprocess.run(["which", "rg"], capture_output=True).returncode == 0:
        cmd = ["rg", "-n", "--max-count", str(max_res), "-S", patron, cwd]
        result = subprocess.run(cmd, capture_output=True, text=True)
    else:
        cmd = f"grep -rn --exclude-dir=node_modules --exclude-dir=venv --exclude-dir=.git -m {max_res} {patron!r} ."
        result = run_shell(cmd, cwd)
    out = truncar_salida((result.stdout or "") + (result.stderr or ""))
    return out or "Sin coincidencias"


def _listar_directorio(args: dict, ctx: ToolContext) -> str:
    sub = args.get("ruta", "").strip() or "."
    prof = int(args.get("profundidad", 3))
    base = _path_en_proyecto(ctx, sub)
    if not os.path.isdir(base):
        return f"No es carpeta: {base}"
    lineas = []
    base_depth = base.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(base):
        depth = root.rstrip(os.sep).count(os.sep) - base_depth
        if depth > prof:
            dirs.clear()
            continue
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", ".git"))
        rel = os.path.relpath(root, base) or "."
        lineas.append(f"{rel}/")
        for f in sorted(files)[:30]:
            if f.startswith("."):
                continue
            lineas.append(f"  {f}")
        if len(lineas) > 200:
            lineas.append("… (truncado)")
            break
    return "\n".join(lineas) or "(vacío)"


def _abrir_en_vscode(args: dict, ctx: ToolContext) -> str:
    raw = (args.get("ruta") or "").strip()
    try:
        if not raw or raw in (".", "./"):
            ruta = resolver_directorio(ctx)
        else:
            ruta = _path_en_proyecto(ctx, raw)
    except ValueError as e:
        return str(e)
    return abrir_en_editor(ruta)


def _dictar_en_archivo(args: dict, ctx: ToolContext) -> str:
    ruta = (args.get("ruta") or "").strip()
    texto = args.get("texto", "")
    modo = (args.get("modo") or "append").strip()
    if not ruta:
        return "Falta la ruta del archivo."
    path = _path_en_proyecto(ctx, ruta)
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    if modo == "reemplazar" or not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(texto)
        return f"{'Creado' if not os.path.isfile(path) else 'Reemplazado'} {path} ({len(texto)} chars)"
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + texto)
    return f"Dictado en {path} ({len(texto)} chars añadidos)"

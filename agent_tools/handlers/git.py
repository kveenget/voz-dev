"""Git — commit, push; Terminal solo si se pide explícitamente."""

import shlex
import subprocess

from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import resolver_directorio, run_shell, truncar_salida


def register_git_tools(project_root: str) -> None:
    pr = project_root

    register(ToolSpec(
        "abrir_terminal",
        "Abre la app Terminal en la carpeta del proyecto (sin ejecutar comando).",
        {
            "type": "object",
            "properties": {
                "directorio": {"type": "string", "description": f"Default: {pr}"},
            },
            "required": [],
        },
        _abrir_terminal,
        "git",
    ))
    register(ToolSpec(
        "git_status",
        "Muestra estado de git (rama, archivos modificados). No abre Terminal.",
        {
            "type": "object",
            "properties": {"directorio": {"type": "string"}},
            "required": [],
        },
        _git_status,
        "git",
    ))
    register(ToolSpec(
        "git_commit",
        "Hace git add y commit con un mensaje. No abre Terminal salvo mostrar_terminal=true.",
        {
            "type": "object",
            "properties": {
                "mensaje": {"type": "string", "description": "Mensaje del commit"},
                "incluir_todo": {
                    "type": "boolean",
                    "description": "Si true, git add -A antes del commit (default true)",
                },
                "directorio": {"type": "string"},
            },
            "required": ["mensaje"],
        },
        _git_commit,
        "git",
    ))
    register(ToolSpec(
        "git_push",
        "Sube commits a GitHub (git push). No abre Terminal salvo mostrar_terminal=true.",
        {
            "type": "object",
            "properties": {
                "remoto": {"type": "string", "description": "default origin"},
                "rama": {"type": "string", "description": "default: rama actual"},
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _git_push,
        "git",
    ))
    register(ToolSpec(
        "git_subir_github",
        "Atajo: add (opcional), commit y push a GitHub en un paso. Para 'sube esto a GitHub'.",
        {
            "type": "object",
            "properties": {
                "mensaje": {"type": "string", "description": "Mensaje del commit"},
                "incluir_todo": {"type": "boolean"},
                "remoto": {"type": "string"},
                "rama": {"type": "string"},
                "directorio": {"type": "string"},
            },
            "required": ["mensaje"],
        },
        _git_subir_github,
        "git",
    ))
    register(ToolSpec(
        "git_diff",
        "Muestra los cambios sin commitear. Usa staged=true para ver lo que está en staging.",
        {
            "type": "object",
            "properties": {
                "archivo": {"type": "string", "description": "Archivo específico (opcional)"},
                "staged": {"type": "boolean", "description": "True = cambios en staging (default false)"},
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _git_diff,
        "git",
    ))
    register(ToolSpec(
        "git_log",
        "Muestra el historial de commits recientes del proyecto.",
        {
            "type": "object",
            "properties": {
                "commits": {"type": "integer", "description": "Cantidad de commits (default 10)"},
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _git_log,
        "git",
    ))
    register(ToolSpec(
        "git_crear_pr",
        "Crea un Pull Request en GitHub usando gh CLI.",
        {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "cuerpo": {"type": "string"},
                "base": {"type": "string", "description": "Rama destino (default main)"},
                "directorio": {"type": "string"},
            },
            "required": ["titulo"],
        },
        _git_crear_pr,
        "git",
    ))
    register(ToolSpec(
        "github_issues",
        "Lista, crea o ve issues de GitHub usando gh CLI.",
        {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["listar", "crear", "ver"],
                    "description": "listar (default), crear, ver",
                },
                "titulo": {"type": "string", "description": "Para crear"},
                "cuerpo": {"type": "string", "description": "Para crear"},
                "numero": {"type": "integer", "description": "Para ver un issue específico"},
                "limite": {"type": "integer", "description": "Para listar (default 10)"},
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _github_issues,
        "git",
    ))


def _abrir_terminal_en(cwd: str, comando: str | None = None) -> None:
    if comando:
        linea = f"cd {cwd} && {comando}"
    else:
        linea = f"cd {cwd} && clear"
    script = f'''
    tell application "Terminal"
        activate
        do script "{linea}"
    end tell
    '''
    subprocess.run(["osascript", "-e", script])


def _run_git(
    cmd: str,
    ctx: ToolContext,
    directorio=None,
    timeout: int = 120,
    mostrar_terminal: bool = False,
):
    cwd = resolver_directorio(ctx, directorio)
    if mostrar_terminal:
        _abrir_terminal_en(cwd, cmd)
    return run_shell(cmd, cwd, timeout=timeout)


def _abrir_terminal(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    _abrir_terminal_en(cwd)
    return f"Terminal abierta en {cwd}"


def _git_status(args: dict, ctx: ToolContext) -> str:
    mostrar = bool(args.get("mostrar_terminal", False))
    result = _run_git(
        "git status -sb && git diff --stat",
        ctx,
        args.get("directorio"),
        mostrar_terminal=mostrar,
    )
    out = truncar_salida((result.stdout or "") + (result.stderr or ""))
    if result.returncode != 0:
        return f"Git status falló:\n{out}"
    return out or "Working tree limpio"


def _git_commit(args: dict, ctx: ToolContext) -> str:
    mensaje = (args.get("mensaje") or "").strip()
    if not mensaje:
        return "Necesito un mensaje de commit"
    incluir = args.get("incluir_todo", True)
    add = "git add -A && " if incluir else ""
    cmd = f"{add}git commit -m {shlex.quote(mensaje)}"
    mostrar = bool(args.get("mostrar_terminal", False))
    result = _run_git(cmd, ctx, args.get("directorio"), mostrar_terminal=mostrar)
    out = truncar_salida((result.stdout or "") + (result.stderr or ""))
    if result.returncode != 0:
        return f"Commit falló:\n{out}"
    return out or f"Commit creado: {mensaje}"


def _git_push(args: dict, ctx: ToolContext) -> str:
    remoto = args.get("remoto") or "origin"
    rama = args.get("rama", "").strip()
    if rama:
        cmd = f"git push {remoto} {rama}"
    else:
        cmd = f"git push {remoto}"
    mostrar = bool(args.get("mostrar_terminal", False))
    result = _run_git(
        cmd, ctx, args.get("directorio"), timeout=180, mostrar_terminal=mostrar
    )
    out = truncar_salida((result.stdout or "") + (result.stderr or ""))
    if result.returncode != 0:
        hint = " Pide abrir_terminal si necesitas login." if not mostrar else ""
        return f"Push falló:{hint}\n{out}"
    return out or f"Push a {remoto} OK"


def _git_subir_github(args: dict, ctx: ToolContext) -> str:
    mensaje = (args.get("mensaje") or "").strip()
    if not mensaje:
        return "Necesito el mensaje del commit"
    incluir = args.get("incluir_todo", True)
    remoto = args.get("remoto") or "origin"
    rama = args.get("rama", "").strip()
    add = "git add -A && " if incluir else ""
    push = f"git push {remoto} {rama}" if rama else f"git push {remoto}"
    cmd = f"{add}git commit -m {shlex.quote(mensaje)} && {push}"
    mostrar = bool(args.get("mostrar_terminal", False))
    result = _run_git(
        cmd, ctx, args.get("directorio"), timeout=180, mostrar_terminal=mostrar
    )
    out = truncar_salida((result.stdout or "") + (result.stderr or ""))
    if result.returncode != 0:
        return f"Subida a GitHub falló:\n{out}"
    return out or f"Listo: commit '{mensaje}' y push a {remoto}"


def _git_diff(args: dict, ctx: ToolContext) -> str:
    staged = bool(args.get("staged", False))
    archivo = (args.get("archivo") or "").strip()
    cmd = "git diff --staged" if staged else "git diff"
    if archivo:
        cmd += f" -- {shlex.quote(archivo)}"
    result = _run_git(cmd, ctx, args.get("directorio"))
    out = truncar_salida((result.stdout or "") + (result.stderr or ""), 3000)
    return out or "Sin cambios pendientes"


def _git_log(args: dict, ctx: ToolContext) -> str:
    n = int(args.get("commits", 10))
    cmd = f"git log --oneline -n {n}"
    result = _run_git(cmd, ctx, args.get("directorio"))
    out = truncar_salida(result.stdout or result.stderr)
    return out or "Sin historial de commits"


def _git_crear_pr(args: dict, ctx: ToolContext) -> str:
    titulo = (args.get("titulo") or "").strip()
    if not titulo:
        return "Necesito un título para el PR"
    cuerpo = (args.get("cuerpo") or "").strip()
    base = (args.get("base") or "main").strip()
    cwd = resolver_directorio(ctx, args.get("directorio"))
    cmd = f"gh pr create --title {shlex.quote(titulo)} --base {shlex.quote(base)}"
    cmd += f" --body {shlex.quote(cuerpo or titulo)}"
    result = run_shell(cmd, cwd, timeout=60)
    out = truncar_salida((result.stdout or "") + (result.stderr or ""))
    if result.returncode != 0:
        return f"PR falló (¿está instalado gh? ¿autenticado?):\n{out}"
    return out or f"PR creado: {titulo}"


def _github_issues(args: dict, ctx: ToolContext) -> str:
    accion = (args.get("accion") or "listar").strip()
    cwd = resolver_directorio(ctx, args.get("directorio"))
    if accion == "listar":
        limite = int(args.get("limite", 10))
        result = run_shell(f"gh issue list --limit {limite}", cwd)
        out = truncar_salida((result.stdout or "") + (result.stderr or ""))
        return out or "No hay issues abiertos"
    elif accion == "crear":
        titulo = (args.get("titulo") or "").strip()
        if not titulo:
            return "Necesito el título del issue"
        cuerpo = (args.get("cuerpo") or "").strip()
        cmd = f"gh issue create --title {shlex.quote(titulo)}"
        cmd += f" --body {shlex.quote(cuerpo or titulo)}"
        result = run_shell(cmd, cwd, timeout=30)
        out = truncar_salida((result.stdout or "") + (result.stderr or ""))
        return out or f"Issue '{titulo}' creado"
    elif accion == "ver":
        numero = str(args.get("numero", "")).strip()
        if not numero:
            return "Necesito el número del issue"
        result = run_shell(f"gh issue view {numero}", cwd)
        return truncar_salida((result.stdout or "") + (result.stderr or ""))
    return f"Acción '{accion}' no reconocida. Usa: listar, crear, ver"

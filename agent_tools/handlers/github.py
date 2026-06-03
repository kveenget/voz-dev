"""
GitHub & control de versiones completo — requiere gh CLI autenticado.
Cubre: crear repo, clonar, init+conectar, ramas, pull, stash, merge.
"""

import shlex
import subprocess

from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import resolver_directorio, run_shell, truncar_salida


def register_github_tools(project_root: str) -> None:
    _ = project_root

    register(ToolSpec(
        "github_crear_repo",
        (
            "Crea un repositorio nuevo en la cuenta de GitHub del usuario. "
            "Si el proyecto ya tiene git inicializado, puede conectarlo y hacer push automáticamente."
        ),
        {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre del repositorio (sin espacios)",
                },
                "descripcion": {
                    "type": "string",
                    "description": "Descripción del repo (opcional)",
                },
                "privado": {
                    "type": "boolean",
                    "description": "True = privado, False = público (default False)",
                },
                "conectar_y_push": {
                    "type": "boolean",
                    "description": (
                        "Si true, conecta el directorio actual como origin y hace push "
                        "(default true cuando ya hay commits)"
                    ),
                },
                "directorio": {"type": "string"},
            },
            "required": ["nombre"],
        },
        _github_crear_repo,
        "git",
    ))

    register(ToolSpec(
        "github_listar_repos",
        "Lista los repositorios de la cuenta de GitHub del usuario.",
        {
            "type": "object",
            "properties": {
                "limite": {"type": "integer", "description": "Cantidad (default 15)"},
                "tipo": {
                    "type": "string",
                    "enum": ["all", "public", "private", "forks", "sources"],
                    "description": "Filtro (default all)",
                },
            },
            "required": [],
        },
        _github_listar_repos,
        "git",
    ))

    register(ToolSpec(
        "github_clonar",
        "Clona un repositorio de GitHub al directorio indicado.",
        {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "usuario/nombre o URL completa del repo",
                },
                "destino": {
                    "type": "string",
                    "description": "Directorio donde clonar (opcional)",
                },
                "abrir_editor": {
                    "type": "boolean",
                    "description": "Si true, abre el proyecto en el editor al terminar",
                },
            },
            "required": ["repo"],
        },
        _github_clonar,
        "git",
    ))

    register(ToolSpec(
        "git_init_y_conectar",
        (
            "Inicializa git en el proyecto actual, crea un repo en GitHub y hace el primer push. "
            "Úsalo para proyectos nuevos que aún no están en GitHub."
        ),
        {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre del repo en GitHub (si se omite, usa el nombre de la carpeta)",
                },
                "descripcion": {"type": "string"},
                "privado": {"type": "boolean", "description": "Default False"},
                "mensaje_inicial": {
                    "type": "string",
                    "description": "Mensaje del primer commit (default 'Initial commit')",
                },
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _git_init_y_conectar,
        "git",
    ))

    register(ToolSpec(
        "git_pull",
        "Descarga y fusiona los últimos cambios del repositorio remoto.",
        {
            "type": "object",
            "properties": {
                "remoto": {"type": "string", "description": "default origin"},
                "rama": {"type": "string", "description": "default: rama actual"},
                "rebase": {
                    "type": "boolean",
                    "description": "Si true, usa --rebase en vez de merge (default false)",
                },
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _git_pull,
        "git",
    ))

    register(ToolSpec(
        "git_crear_rama",
        "Crea una rama nueva y cambia a ella.",
        {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la rama"},
                "desde": {
                    "type": "string",
                    "description": "Rama base (default: rama actual)",
                },
                "directorio": {"type": "string"},
            },
            "required": ["nombre"],
        },
        _git_crear_rama,
        "git",
    ))

    register(ToolSpec(
        "git_checkout",
        "Cambia de rama o restaura un archivo a su última versión commiteada.",
        {
            "type": "object",
            "properties": {
                "rama_o_archivo": {
                    "type": "string",
                    "description": "Nombre de la rama o ruta del archivo",
                },
                "directorio": {"type": "string"},
            },
            "required": ["rama_o_archivo"],
        },
        _git_checkout,
        "git",
    ))

    register(ToolSpec(
        "git_merge",
        "Fusiona una rama en la rama actual.",
        {
            "type": "object",
            "properties": {
                "rama": {"type": "string", "description": "Rama a fusionar"},
                "no_ff": {
                    "type": "boolean",
                    "description": "Si true, fuerza commit de merge (--no-ff, default true)",
                },
                "directorio": {"type": "string"},
            },
            "required": ["rama"],
        },
        _git_merge,
        "git",
    ))

    register(ToolSpec(
        "git_stash",
        "Guarda temporalmente los cambios sin commitear (stash) o los recupera.",
        {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["guardar", "recuperar", "listar", "borrar"],
                    "description": "guardar (default), recuperar (pop), listar, borrar",
                },
                "mensaje": {
                    "type": "string",
                    "description": "Mensaje descriptivo al guardar (opcional)",
                },
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _git_stash,
        "git",
    ))

    register(ToolSpec(
        "github_repo_info",
        "Muestra información del repositorio GitHub del proyecto actual (URL, visibilidad, estrelllas, etc.).",
        {
            "type": "object",
            "properties": {"directorio": {"type": "string"}},
            "required": [],
        },
        _github_repo_info,
        "git",
    ))


# ── Implementaciones ────────────────────────────────────────────────────────


def _gh(cmd: str, cwd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return run_shell(cmd, cwd, timeout=timeout)


def _out(r: subprocess.CompletedProcess) -> str:
    return truncar_salida((r.stdout or "") + (r.stderr or ""))


def _github_crear_repo(args: dict, ctx: ToolContext) -> str:
    nombre = (args.get("nombre") or "").strip().replace(" ", "-")
    if not nombre:
        return "Necesito el nombre del repositorio"

    cwd = resolver_directorio(ctx, args.get("directorio"))
    desc = (args.get("descripcion") or "").strip()
    vis = "--private" if args.get("privado") else "--public"
    conectar = args.get("conectar_y_push", True)

    cmd = f"gh repo create {shlex.quote(nombre)} {vis}"
    if desc:
        cmd += f" --description {shlex.quote(desc)}"

    if conectar:
        cmd += " --source=. --remote=origin --push"

    r = _gh(cmd, cwd, timeout=120)
    out = _out(r)
    if r.returncode != 0:
        return f"No pude crear el repo (¿gh autenticado? `gh auth login`):\n{out}"
    return out or f"Repositorio '{nombre}' creado{' y conectado' if conectar else ''} en GitHub"


def _github_listar_repos(args: dict, ctx: ToolContext) -> str:
    limite = int(args.get("limite", 15))
    tipo = (args.get("tipo") or "all").strip()
    cwd = resolver_directorio(ctx, None)
    r = _gh(f"gh repo list --limit {limite} --type {tipo}", cwd)
    out = _out(r)
    if r.returncode != 0:
        return f"No pude listar repos:\n{out}"
    return out or "No se encontraron repositorios"


def _github_clonar(args: dict, ctx: ToolContext) -> str:
    repo = (args.get("repo") or "").strip()
    if not repo:
        return "Necesito el repo a clonar (usuario/nombre o URL)"

    destino = (args.get("destino") or "").strip()
    cwd = resolver_directorio(ctx, destino or None)
    abrir = bool(args.get("abrir_editor", False))

    cmd = f"gh repo clone {shlex.quote(repo)}"
    r = _gh(cmd, cwd, timeout=180)
    out = _out(r)
    if r.returncode != 0:
        return f"No pude clonar:\n{out}"

    if abrir:
        nombre = repo.split("/")[-1].replace(".git", "")
        import os
        from agent_tools.utils import abrir_en_editor
        ruta = os.path.join(cwd, nombre)
        abrir_en_editor(ruta)

    return out or f"Clonado: {repo}"


def _git_init_y_conectar(args: dict, ctx: ToolContext) -> str:
    import os
    cwd = resolver_directorio(ctx, args.get("directorio"))
    nombre = (args.get("nombre") or os.path.basename(cwd)).strip().replace(" ", "-")
    desc = (args.get("descripcion") or "").strip()
    vis = "--private" if args.get("privado") else "--public"
    msg = (args.get("mensaje_inicial") or "Initial commit").strip()

    pasos = []

    # 1. Init si no hay .git
    if not os.path.isdir(os.path.join(cwd, ".git")):
        r = run_shell("git init && git add -A", cwd)
        pasos.append(_out(r))
        if r.returncode != 0:
            return "git init falló:\n" + "\n".join(pasos)

    # 2. Commit inicial si no hay commits
    r_log = run_shell("git log --oneline -1", cwd)
    if r_log.returncode != 0 or not (r_log.stdout or "").strip():
        r = run_shell(f"git add -A && git commit -m {shlex.quote(msg)}", cwd)
        pasos.append(_out(r))
        if r.returncode != 0:
            return "Commit inicial falló:\n" + "\n".join(pasos)

    # 3. Crear repo en GitHub y conectar
    cmd = f"gh repo create {shlex.quote(nombre)} {vis} --source=. --remote=origin --push"
    if desc:
        cmd += f" --description {shlex.quote(desc)}"
    r = _gh(cmd, cwd, timeout=180)
    pasos.append(_out(r))
    if r.returncode != 0:
        return "No pude crear el repo en GitHub:\n" + "\n".join(pasos)

    return "\n".join(p for p in pasos if p) or f"✓ '{nombre}' inicializado y subido a GitHub"


def _git_pull(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    remoto = (args.get("remoto") or "origin").strip()
    rama = (args.get("rama") or "").strip()
    rebase = "--rebase" if args.get("rebase") else ""
    cmd = f"git pull {rebase} {remoto} {rama}".strip()
    r = run_shell(cmd, cwd, timeout=120)
    out = _out(r)
    if r.returncode != 0:
        return f"Pull falló:\n{out}"
    return out or "Actualizado desde el remoto"


def _git_crear_rama(args: dict, ctx: ToolContext) -> str:
    nombre = (args.get("nombre") or "").strip().replace(" ", "-")
    if not nombre:
        return "Necesito el nombre de la rama"
    cwd = resolver_directorio(ctx, args.get("directorio"))
    desde = (args.get("desde") or "").strip()
    cmd = f"git checkout -b {shlex.quote(nombre)}"
    if desde:
        cmd += f" {shlex.quote(desde)}"
    r = run_shell(cmd, cwd)
    out = _out(r)
    if r.returncode != 0:
        return f"No pude crear la rama:\n{out}"
    return out or f"Rama '{nombre}' creada y activa"


def _git_checkout(args: dict, ctx: ToolContext) -> str:
    target = (args.get("rama_o_archivo") or "").strip()
    if not target:
        return "Necesito el nombre de la rama o el archivo"
    cwd = resolver_directorio(ctx, args.get("directorio"))
    r = run_shell(f"git checkout {shlex.quote(target)}", cwd)
    out = _out(r)
    if r.returncode != 0:
        return f"Checkout falló:\n{out}"
    return out or f"Cambiado a: {target}"


def _git_merge(args: dict, ctx: ToolContext) -> str:
    rama = (args.get("rama") or "").strip()
    if not rama:
        return "Necesito el nombre de la rama a fusionar"
    cwd = resolver_directorio(ctx, args.get("directorio"))
    no_ff = "--no-ff" if args.get("no_ff", True) else ""
    cmd = f"git merge {no_ff} {shlex.quote(rama)}".strip()
    r = run_shell(cmd, cwd, timeout=60)
    out = _out(r)
    if r.returncode != 0:
        return f"Merge falló (puede haber conflictos):\n{out}"
    return out or f"Rama '{rama}' fusionada"


def _git_stash(args: dict, ctx: ToolContext) -> str:
    accion = (args.get("accion") or "guardar").strip()
    cwd = resolver_directorio(ctx, args.get("directorio"))
    if accion == "guardar":
        msg = (args.get("mensaje") or "").strip()
        cmd = f"git stash push -m {shlex.quote(msg)}" if msg else "git stash push"
    elif accion == "recuperar":
        cmd = "git stash pop"
    elif accion == "listar":
        cmd = "git stash list"
    elif accion == "borrar":
        cmd = "git stash drop"
    else:
        return f"Acción '{accion}' no reconocida. Usa: guardar, recuperar, listar, borrar"
    r = run_shell(cmd, cwd)
    out = _out(r)
    if r.returncode != 0:
        return f"Stash {accion} falló:\n{out}"
    return out or f"Stash {accion} OK"


def _github_repo_info(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    r = _gh("gh repo view --json name,description,visibility,url,stargazerCount,defaultBranchRef,pushedAt", cwd)
    if r.returncode != 0:
        return f"No pude obtener info del repo (¿hay remote origin?):\n{_out(r)}"
    import json
    try:
        d = json.loads(r.stdout or "{}")
        branch = (d.get("defaultBranchRef") or {}).get("name", "?")
        return (
            f"Repo: {d.get('name', '?')}\n"
            f"URL: {d.get('url', '?')}\n"
            f"Visibilidad: {d.get('visibility', '?')}\n"
            f"Rama por defecto: {branch}\n"
            f"Estrellas: {d.get('stargazerCount', 0)}\n"
            f"Descripción: {d.get('description') or '(sin descripción)'}\n"
            f"Último push: {d.get('pushedAt', '?')}"
        )
    except Exception:
        return truncar_salida(r.stdout or r.stderr)

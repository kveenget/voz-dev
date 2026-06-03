"""
Herramientas de calidad de código: análisis de proyecto, lectura multi-archivo,
búsqueda de definiciones y verificación (lint/typecheck).
"""

import json
import os
import subprocess

from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import resolver_directorio, run_shell, truncar_salida

_IGNORE_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", ".git",
    "dist", "build", ".next", "coverage", ".mypy_cache", ".ruff_cache",
}
_CODE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".kt", ".swift", ".rb", ".php", ".css", ".scss", ".html",
    ".json", ".yaml", ".yml", ".toml", ".md",
}


def register_coding_tools(project_root: str) -> None:
    _ = project_root

    register(ToolSpec(
        "analizar_proyecto",
        (
            "Lee la estructura del proyecto y detecta: lenguaje, framework, dependencias clave, "
            "archivos de configuración y patrones de código existentes. "
            "ÚSALA SIEMPRE antes de escribir código nuevo en un proyecto desconocido."
        ),
        {
            "type": "object",
            "properties": {
                "directorio": {"type": "string"},
                "profundo": {
                    "type": "boolean",
                    "description": "Si true, lee también archivos de código clave (default false)",
                },
            },
            "required": [],
        },
        _analizar_proyecto,
        "coding",
    ))

    register(ToolSpec(
        "leer_multiples_archivos",
        (
            "Lee varios archivos del proyecto de una vez. "
            "Úsala para entender contexto antes de editar: tipos, interfaces, imports, patrones."
        ),
        {
            "type": "object",
            "properties": {
                "rutas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de rutas relativas al proyecto (máx 8)",
                },
                "max_lineas_por_archivo": {
                    "type": "integer",
                    "description": "Límite de líneas por archivo (default 150)",
                },
            },
            "required": ["rutas"],
        },
        _leer_multiples_archivos,
        "coding",
    ))

    register(ToolSpec(
        "buscar_definicion",
        (
            "Encuentra dónde está definida una función, clase, variable o tipo en el proyecto. "
            "Más preciso que buscar_codigo para encontrar la declaración exacta."
        ),
        {
            "type": "object",
            "properties": {
                "simbolo": {
                    "type": "string",
                    "description": "Nombre del símbolo a buscar (función, clase, tipo, variable)",
                },
                "directorio": {"type": "string"},
            },
            "required": ["simbolo"],
        },
        _buscar_definicion,
        "coding",
    ))

    register(ToolSpec(
        "verificar_codigo",
        (
            "Verifica el código después de escribirlo: corre lint y typecheck según el stack "
            "(ruff+mypy para Python, tsc+eslint para TypeScript/JS, etc.). "
            "ÚSALA después de editar_archivo o escribir_archivo para detectar errores antes de commitear."
        ),
        {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Archivo específico a verificar (opcional — si se omite verifica todo el proyecto)",
                },
                "directorio": {"type": "string"},
            },
            "required": [],
        },
        _verificar_codigo,
        "coding",
    ))

    register(ToolSpec(
        "ver_estructura",
        (
            "Muestra la estructura de carpetas del proyecto de forma compacta, "
            "ignorando node_modules, venv, .git, etc."
        ),
        {
            "type": "object",
            "properties": {
                "directorio": {"type": "string"},
                "profundidad": {"type": "integer", "description": "default 4"},
            },
            "required": [],
        },
        _ver_estructura,
        "coding",
    ))

    register(ToolSpec(
        "indexar_proyecto_completo",
        (
            "Lee TODOS los archivos de código del proyecto y construye un mapa completo: "
            "estructura, stack, dependencias y contenido de cada archivo. "
            "Úsalo cuando el dev dice 'cuéntame el proyecto', 'entiende la estructura', "
            "'analiza todo el código', o antes de tareas grandes multi-archivo. "
            "Da al agente contexto total equivalente a leer el workspace completo."
        ),
        {
            "type": "object",
            "properties": {
                "directorio": {"type": "string"},
                "max_chars": {
                    "type": "integer",
                    "description": "Límite de caracteres totales (default 80000 ≈ 60K tokens)",
                },
                "solo_estructura": {
                    "type": "boolean",
                    "description": "Si true, solo árbol de archivos sin contenido (rápido)",
                },
            },
            "required": [],
        },
        _indexar_proyecto_completo,
        "coding",
    ))


# ── Implementaciones ────────────────────────────────────────────────────────


def _analizar_proyecto(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    profundo = bool(args.get("profundo", False))
    secciones = []

    # 1. Estructura de primer nivel
    try:
        top = sorted(os.listdir(cwd))
        top_clean = [f for f in top if f not in _IGNORE_DIRS and not f.startswith(".")]
        secciones.append("Archivos raíz: " + ", ".join(top_clean[:30]))
    except OSError:
        pass

    # 2. Detectar stack
    stack = _detectar_stack(cwd)
    secciones.append(f"Stack detectado: {stack}")

    # 3. Leer configs clave
    configs = [
        "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
        "go.mod", "tsconfig.json", "next.config.mjs", "next.config.js",
        "vite.config.ts", "vite.config.js", "tailwind.config.ts",
        ".eslintrc.json", "ruff.toml", "mypy.ini", "setup.cfg",
        "docker-compose.yml", "Dockerfile",
    ]
    for cfg_file in configs:
        path = os.path.join(cwd, cfg_file)
        if os.path.isfile(path):
            contenido = _leer_corto(path, max_chars=800)
            secciones.append(f"\n--- {cfg_file} ---\n{contenido}")

    # 4. Árbol compacto (2 niveles)
    arbol = _arbol(cwd, max_depth=2)
    secciones.append(f"\nEstructura:\n{arbol}")

    # 5. Lectura profunda — archivos clave de código
    if profundo:
        claves = _archivos_clave(cwd)
        for p in claves[:5]:
            rel = os.path.relpath(p, cwd)
            contenido = _leer_corto(p, max_chars=600)
            secciones.append(f"\n--- {rel} ---\n{contenido}")

    return truncar_salida("\n".join(secciones), 4000)


def _leer_multiples_archivos(args: dict, ctx: ToolContext) -> str:
    rutas = args.get("rutas", [])[:8]
    max_lineas = int(args.get("max_lineas_por_archivo", 150))
    cwd = resolver_directorio(ctx)
    partes = []

    for ruta in rutas:
        path = os.path.join(cwd, ruta) if not os.path.isabs(ruta) else ruta
        path = os.path.realpath(path)
        if not os.path.isfile(path):
            partes.append(f"--- {ruta} ---\n(no encontrado)")
            continue
        lineas = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, linea in enumerate(f):
                if i >= max_lineas:
                    lineas.append(f"… (+{sum(1 for _ in f)} líneas más)")
                    break
                lineas.append(linea.rstrip("\n"))
        partes.append(f"--- {ruta} ---\n" + "\n".join(lineas))

    return truncar_salida("\n\n".join(partes), 4500)


def _buscar_definicion(args: dict, ctx: ToolContext) -> str:
    simbolo = (args.get("simbolo") or "").strip()
    if not simbolo:
        return "Necesito el nombre del símbolo"
    cwd = resolver_directorio(ctx, args.get("directorio"))

    # Patrones de definición para distintos lenguajes
    patrones = [
        # Python
        f"def {simbolo}",
        f"class {simbolo}",
        f"{simbolo} =",
        f"{simbolo}: ",
        # TypeScript/JS
        f"function {simbolo}",
        f"const {simbolo}",
        f"let {simbolo}",
        f"var {simbolo}",
        f"type {simbolo}",
        f"interface {simbolo}",
        f"export function {simbolo}",
        f"export const {simbolo}",
        f"export class {simbolo}",
        f"export type {simbolo}",
        f"export interface {simbolo}",
        # Go, Rust, Java
        f"func {simbolo}",
        f"fn {simbolo}",
        f"pub fn {simbolo}",
    ]

    resultados = []
    if _tiene_rg():
        patron_rg = "|".join(f"({p.replace(' ', r'\s+')})" for p in patrones[:8])
        r = subprocess.run(
            ["rg", "-n", "-S", "--max-count", "3", patron_rg, cwd],
            capture_output=True, text=True,
        )
        out = r.stdout.strip()
    else:
        patron_grep = rf"\(def\|class\|function\|const\|type\|interface\|fn\|func\) {simbolo}"
        r = run_shell(
            f"grep -rn --include='*.py' --include='*.ts' --include='*.tsx' "
            f"--include='*.js' --include='*.go' --include='*.rs' "
            f"--exclude-dir=node_modules --exclude-dir=venv --exclude-dir=.git "
            f"-E '(def|class|function|const|let|type|interface|fn|func)\\s+{simbolo}' .",
            cwd,
        )
        out = r.stdout.strip()

    if not out:
        return f"No encontré definición de '{simbolo}'. Puede estar en node_modules o generado dinámicamente."

    # Mostrar contexto de cada resultado (±2 líneas)
    lineas = out.splitlines()[:10]
    return truncar_salida(f"Definición de '{simbolo}':\n" + "\n".join(lineas))


def _verificar_codigo(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    ruta = args.get("ruta", "")
    target = os.path.join(cwd, ruta) if ruta and not os.path.isabs(ruta) else ruta or cwd
    resultados = []
    stack = _detectar_stack(cwd)

    if "python" in stack.lower():
        resultados.extend(_verificar_python(cwd, target if ruta else None))
    if any(s in stack.lower() for s in ("typescript", "javascript", "next", "react", "node")):
        resultados.extend(_verificar_js(cwd, target if ruta else None))
    if "rust" in stack.lower():
        r = run_shell("cargo check 2>&1", cwd, timeout=120)
        resultados.append(("Cargo check", r.stdout or r.stderr, r.returncode))
    if "go" in stack.lower():
        r = run_shell("go vet ./... 2>&1", cwd, timeout=60)
        resultados.append(("go vet", r.stdout or r.stderr, r.returncode))

    if not resultados:
        return "No detecté un checker disponible para este proyecto (¿instala ruff, tsc o eslint?)."

    partes = []
    ok = True
    for nombre, salida, code in resultados:
        icono = "✅" if code == 0 else "❌"
        salida = salida.strip()
        partes.append(f"{icono} {nombre}:\n{salida or 'Sin errores'}")
        if code != 0:
            ok = False

    resumen = "✅ Todo OK" if ok else "❌ Hay errores — revisa antes de commitear"
    return truncar_salida(resumen + "\n\n" + "\n\n".join(partes), 3500)


def _ver_estructura(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    depth = int(args.get("profundidad", 4))
    return truncar_salida(_arbol(cwd, max_depth=depth), 3000)


def _indexar_proyecto_completo(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    max_chars_total = int(args.get("max_chars", 80_000))
    solo_estructura = bool(args.get("solo_estructura", False))

    stack = _detectar_stack(cwd)
    estructura = _arbol(cwd, max_depth=6)

    secciones = [
        f"# Proyecto: {os.path.basename(cwd)}",
        f"# Stack: {stack}",
        f"# Ruta: {cwd}",
        "",
        "## Estructura completa:",
        estructura,
    ]

    if solo_estructura:
        return truncar_salida("\n".join(secciones), max_chars_total)

    secciones.append("\n## Archivos de código:")
    chars_usados = sum(len(s) for s in secciones)

    todos_archivos = _recolectar_archivos(cwd)
    archivos_leidos = 0
    archivos_omitidos = []

    for rel_path, full_path, size in todos_archivos:
        if chars_usados >= max_chars_total:
            archivos_omitidos.append(rel_path)
            continue

        espacio = max_chars_total - chars_usados
        max_chars_archivo = min(espacio, 10_000)

        try:
            with open(full_path, encoding="utf-8", errors="replace") as f:
                contenido = f.read(max_chars_archivo)
            truncado = size > max_chars_archivo
            attr = ' truncated="true"' if truncado else ""
            entrada = f'\n<file path="{rel_path}"{attr}>\n{contenido}\n</file>'
            secciones.append(entrada)
            chars_usados += len(entrada)
            archivos_leidos += 1
        except OSError:
            continue

    if archivos_omitidos:
        omitidos_str = "\n".join(f"  - {p}" for p in archivos_omitidos[:30])
        secciones.append(f"\n# No incluidos por límite ({len(archivos_omitidos)}):\n{omitidos_str}")

    secciones.append(f"\n# Resumen: {archivos_leidos} archivos, {chars_usados:,} chars")
    return "\n".join(secciones)


# ── Helpers internos ────────────────────────────────────────────────────────


def _detectar_stack(cwd: str) -> str:
    indicadores = []
    checks = [
        ("package.json", _leer_json_keys),
        ("pyproject.toml", None),
        ("requirements.txt", None),
        ("Cargo.toml", None),
        ("go.mod", None),
        ("pom.xml", None),
    ]
    for fname, fn in checks:
        path = os.path.join(cwd, fname)
        if not os.path.isfile(path):
            continue
        if fname == "package.json":
            deps = fn(path)
            if "next" in deps:
                indicadores.append("Next.js")
            if "react" in deps:
                indicadores.append("React")
            if "vue" in deps:
                indicadores.append("Vue")
            if "express" in deps:
                indicadores.append("Express")
            if "typescript" in deps or os.path.isfile(os.path.join(cwd, "tsconfig.json")):
                indicadores.append("TypeScript")
            else:
                indicadores.append("JavaScript/Node")
            if "tailwindcss" in deps:
                indicadores.append("Tailwind")
        elif fname == "pyproject.toml":
            indicadores.append("Python")
            content = _leer_corto(path, 400)
            if "fastapi" in content.lower():
                indicadores.append("FastAPI")
            if "django" in content.lower():
                indicadores.append("Django")
            if "flask" in content.lower():
                indicadores.append("Flask")
        elif fname == "requirements.txt":
            indicadores.append("Python")
            content = _leer_corto(path, 400)
            for fw in ("fastapi", "django", "flask", "openai", "torch", "pandas"):
                if fw in content.lower():
                    indicadores.append(fw.capitalize())
        elif fname == "Cargo.toml":
            indicadores.append("Rust")
        elif fname == "go.mod":
            indicadores.append("Go")
        elif fname == "pom.xml":
            indicadores.append("Java/Maven")

    return ", ".join(indicadores) if indicadores else "Desconocido"


def _leer_json_keys(path: str) -> set:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        deps = set()
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            deps.update(k.lower() for k in d.get(section, {}).keys())
        return deps
    except Exception:
        return set()


def _leer_corto(path: str, max_chars: int = 600) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(max_chars)
    except OSError:
        return "(no legible)"


def _arbol(cwd: str, max_depth: int = 3) -> str:
    lineas = []
    base_depth = cwd.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(cwd):
        depth = root.rstrip(os.sep).count(os.sep) - base_depth
        if depth > max_depth:
            dirs.clear()
            continue
        dirs[:] = sorted(d for d in dirs if d not in _IGNORE_DIRS and not d.startswith("."))
        indent = "  " * depth
        nombre = os.path.basename(root) or root
        if depth > 0:
            lineas.append(f"{indent}{nombre}/")
        for f in sorted(files)[:20]:
            if f.startswith(".") or os.path.splitext(f)[1] not in _CODE_EXTS:
                continue
            lineas.append(f"{'  ' * (depth+1)}{f}")
        if len(lineas) > 150:
            lineas.append("… (truncado)")
            break
    return "\n".join(lineas)


def _recolectar_archivos(cwd: str) -> list[tuple[str, str, int]]:
    """Devuelve (rel_path, full_path, size) ordenado: configs pequeñas primero, luego por tamaño."""
    _CONFIG_NAMES = {
        "package.json", "pyproject.toml", "tsconfig.json", "requirements.txt",
        "Cargo.toml", "go.mod", "Makefile", "docker-compose.yml", "Dockerfile",
    }
    resultado = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = sorted(d for d in dirs if d not in _IGNORE_DIRS and not d.startswith("."))
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _CODE_EXTS and fname not in _CONFIG_NAMES:
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, cwd)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0
            resultado.append((rel_path, full_path, size))

    resultado.sort(key=lambda x: (os.path.basename(x[0]) not in _CONFIG_NAMES, x[2]))
    return resultado


def _archivos_clave(cwd: str) -> list[str]:
    candidatos = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
        for f in files:
            if any(f == k for k in ("main.py", "index.ts", "index.js", "app.py",
                                     "server.js", "server.ts", "app.ts", "layout.tsx",
                                     "page.tsx", "__init__.py")):
                candidatos.append(os.path.join(root, f))
    return candidatos


def _tiene_rg() -> bool:
    return subprocess.run(["which", "rg"], capture_output=True).returncode == 0


def _verificar_python(cwd: str, ruta: str | None) -> list[tuple]:
    resultados = []
    target = ruta or "."

    # ruff (linter rápido)
    r = run_shell(f"ruff check {target} --output-format=concise 2>&1", cwd, timeout=30)
    if r.returncode != 127:  # 127 = comando no encontrado
        resultados.append(("ruff", r.stdout or r.stderr, r.returncode))

    # mypy (typecheck) — solo si hay mypy instalado
    r_mypy = run_shell(f"mypy {target} --ignore-missing-imports --no-error-summary 2>&1", cwd, timeout=60)
    if r_mypy.returncode != 127:
        resultados.append(("mypy", r_mypy.stdout or r_mypy.stderr, r_mypy.returncode))

    if not resultados:
        # Fallback: python -m py_compile
        py = "venv/bin/python" if os.path.isfile(os.path.join(cwd, "venv/bin/python")) else "python3"
        tgt = ruta or "."
        if os.path.isfile(tgt):
            r2 = run_shell(f"{py} -m py_compile {tgt} 2>&1", cwd, timeout=15)
            resultados.append(("py_compile", r2.stdout or r2.stderr or "OK", r2.returncode))

    return resultados


def _verificar_js(cwd: str, ruta: str | None) -> list[tuple]:
    resultados = []
    target = ruta or "."
    node_bin = os.path.join(cwd, "node_modules", ".bin")

    # TypeScript — tsc
    tsc = os.path.join(node_bin, "tsc")
    if os.path.isfile(tsc) and os.path.isfile(os.path.join(cwd, "tsconfig.json")):
        r = run_shell(f"{tsc} --noEmit 2>&1", cwd, timeout=120)
        resultados.append(("tsc", r.stdout or r.stderr, r.returncode))

    # ESLint
    eslint = os.path.join(node_bin, "eslint")
    if os.path.isfile(eslint):
        tgt = ruta or "."
        r = run_shell(f"{eslint} {tgt} --max-warnings=0 2>&1", cwd, timeout=60)
        if r.returncode != 127:
            resultados.append(("eslint", r.stdout or r.stderr, r.returncode))

    return resultados

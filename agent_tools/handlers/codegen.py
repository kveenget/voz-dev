"""
Generación de código con modelo especializado (Claude / GPT-4o).

El agente de voz (gpt-realtime-2) orquesta; este módulo delega la escritura
real de código a un modelo con razonamiento profundo y contexto largo.

Configuración (.env):
  ANTHROPIC_API_KEY   → usa Claude claude-sonnet-4-6 (recomendado)
  VOZ_CODE_MODEL      → modelo a usar (default: claude-sonnet-4-6 / gpt-4o)
  Si no hay ANTHROPIC_API_KEY, usa OPENAI_API_KEY con gpt-4o como fallback.
"""

import json
import os
import re
import urllib.error
import urllib.request

from agent_tools.context import ToolContext
from agent_tools.handlers.coding import _recolectar_archivos
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import abrir_en_editor, resolver_directorio, truncar_salida

_MAX_CHARS_POR_ARCHIVO = 12_000
_MAX_ARCHIVOS = 10
_MAX_ITERACIONES_FIX = 3


def register_codegen_tools(project_root: str) -> None:
    _ = project_root

    register(ToolSpec(
        "generar_codigo",
        (
            "Genera código de producción usando un modelo especializado (Claude/GPT-4o). "
            "Úsala para features nuevas, componentes completos o cambios complejos. "
            "Lee archivos de contexto para imitar los patrones del proyecto. "
            "Es más potente que editar_archivo para tareas de escritura no triviales."
        ),
        {
            "type": "object",
            "properties": {
                "tarea": {
                    "type": "string",
                    "description": "Descripción detallada de lo que debe hacer el código",
                },
                "ruta_destino": {
                    "type": "string",
                    "description": "Archivo donde guardar el código generado (relativo al proyecto)",
                },
                "archivos_contexto": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Archivos a leer para entender patrones del proyecto "
                        "(tipos, imports, componentes similares). Máx 10."
                    ),
                },
                "instrucciones": {
                    "type": "string",
                    "description": "Instrucciones adicionales de estilo o restricciones",
                },
                "abrir_editor": {
                    "type": "boolean",
                    "description": "Abre el archivo en Cursor al terminar (default true)",
                },
            },
            "required": ["tarea"],
        },
        _generar_codigo,
        "coding",
    ))

    register(ToolSpec(
        "refactorizar_codigo",
        (
            "Refactoriza un archivo o fragmento de código usando un modelo especializado. "
            "Puede mejorar legibilidad, extraer funciones, aplicar patrones, reducir duplicación."
        ),
        {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Archivo a refactorizar",
                },
                "objetivo": {
                    "type": "string",
                    "description": "Qué mejorar: 'legibilidad', 'rendimiento', 'tipos', 'separar en funciones', etc.",
                },
                "archivos_contexto": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Archivos relacionados para entender el contexto",
                },
            },
            "required": ["ruta", "objetivo"],
        },
        _refactorizar_codigo,
        "coding",
    ))

    register(ToolSpec(
        "revisar_y_mejorar",
        (
            "Hace una revisión profunda de código: detecta bugs, problemas de seguridad, "
            "código muerto, mejoras de rendimiento y sugiere o aplica cambios."
        ),
        {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Archivo a revisar",
                },
                "aplicar_cambios": {
                    "type": "boolean",
                    "description": "Si true, aplica las mejoras directamente. Si false, solo reporta (default false).",
                },
            },
            "required": ["ruta"],
        },
        _revisar_y_mejorar,
        "coding",
    ))

    register(ToolSpec(
        "ejecutar_tarea",
        (
            "Ejecuta una tarea de código compleja de forma autónoma: analiza el proyecto, "
            "planifica los cambios, genera o modifica los archivos necesarios, verifica errores "
            "y los corrige automáticamente. "
            "Úsala para tareas grandes: 'agrega autenticación', 'crea el módulo de pagos', "
            "'refactoriza la capa de datos', 'implementa X feature'. "
            "Es el modo más poderoso — equivalente al Composer de Cursor."
        ),
        {
            "type": "object",
            "properties": {
                "tarea": {
                    "type": "string",
                    "description": "Descripción completa de lo que hay que hacer",
                },
                "archivos_relevantes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Archivos que el agente debe leer para entender el contexto",
                },
                "directorio": {"type": "string"},
            },
            "required": ["tarea"],
        },
        _ejecutar_tarea,
        "coding",
    ))

    register(ToolSpec(
        "generar_tests",
        (
            "Genera tests unitarios / de integración para un archivo o función. "
            "Detecta el framework de tests del proyecto (pytest, jest, vitest, etc.)."
        ),
        {
            "type": "object",
            "properties": {
                "ruta": {
                    "type": "string",
                    "description": "Archivo del que generar tests",
                },
                "ruta_tests": {
                    "type": "string",
                    "description": "Dónde guardar los tests (opcional — lo infiere si no se pasa)",
                },
                "tipo": {
                    "type": "string",
                    "description": "unitarios (default), integración, e2e",
                },
            },
            "required": ["ruta"],
        },
        _generar_tests,
        "coding",
    ))

    register(ToolSpec(
        "explicar_proyecto",
        (
            "Analiza el proyecto completo con IA y genera una consultoría técnica profunda: "
            "arquitectura, flujos de datos, puntos fuertes, deuda técnica y recomendaciones "
            "concretas priorizadas con esfuerzo estimado. "
            "Úsala cuando el dev quiere entender un proyecto nuevo, necesita un tour guiado, "
            "pide recomendaciones de mejora, o quiere saber qué atacar primero. "
            "Foco ajustable: general, arquitectura, seguridad, rendimiento, deuda_tecnica, onboarding."
        ),
        {
            "type": "object",
            "properties": {
                "directorio": {"type": "string"},
                "foco": {
                    "type": "string",
                    "description": (
                        "general (default) | arquitectura | seguridad | rendimiento "
                        "| deuda_tecnica | onboarding"
                    ),
                },
                "nivel_dev": {
                    "type": "string",
                    "description": "junior | senior | auto (default) — adapta profundidad de la explicación",
                },
            },
            "required": [],
        },
        _explicar_proyecto,
        "coding",
    ))


# ── Motor de inferencia ─────────────────────────────────────────────────────


def _modelo_codigo() -> str:
    if os.getenv("VOZ_CODE_MODEL"):
        return os.getenv("VOZ_CODE_MODEL")
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude-sonnet-4-6"
    return "gpt-4o"


def _usar_claude() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _llamar_modelo(prompt: str, ctx: ToolContext, max_tokens: int = 8192) -> str:
    if _usar_claude():
        return _llamar_claude(prompt, ctx, max_tokens)
    return _llamar_gpt4o(prompt, ctx, max_tokens)


def _llamar_claude(prompt: str, ctx: ToolContext, max_tokens: int) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model = _modelo_codigo()
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ctx.ssl_context, timeout=180) as resp:
            data = json.loads(resp.read())
        return data["content"][0]["text"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Claude API {e.code}: {e.read().decode()[:400]}") from e


def _llamar_gpt4o(prompt: str, ctx: ToolContext, max_tokens: int) -> str:
    model = _modelo_codigo() if _modelo_codigo() != "claude-sonnet-4-6" else "gpt-4o"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
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
        with urllib.request.urlopen(req, context=ctx.ssl_context, timeout=180) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenAI API {e.code}: {e.read().decode()[:400]}") from e


# ── Helpers ─────────────────────────────────────────────────────────────────


def _leer_archivo(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(_MAX_CHARS_POR_ARCHIVO)
    except OSError:
        return ""


def _bloque_archivos(rutas: list[str], cwd: str) -> str:
    partes = []
    for ruta in rutas[:_MAX_ARCHIVOS]:
        path = os.path.join(cwd, ruta) if not os.path.isabs(ruta) else ruta
        contenido = _leer_archivo(path)
        if contenido:
            partes.append(f'<file path="{ruta}">\n{contenido}\n</file>')
    return "\n\n".join(partes)


def _limpiar_codigo(texto: str) -> str:
    """Quita markdown fences si el modelo las añadió."""
    texto = texto.strip()
    match = re.match(r"^```[\w]*\n(.*?)```$", texto, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Múltiples fences: quitar solo la primera y última
    lineas = texto.splitlines()
    if lineas and lineas[0].startswith("```"):
        lineas = lineas[1:]
    if lineas and lineas[-1].strip() == "```":
        lineas = lineas[:-1]
    return "\n".join(lineas).strip()


def _escribir(path: str, contenido: str) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(contenido)


def _modelo_label() -> str:
    return f"{'Claude' if _usar_claude() else 'GPT-4o'} ({_modelo_codigo()})"


# ── Implementaciones ────────────────────────────────────────────────────────


def _generar_codigo(args: dict, ctx: ToolContext) -> str:
    tarea = (args.get("tarea") or "").strip()
    if not tarea:
        return "Necesito una descripción de la tarea"

    cwd = resolver_directorio(ctx)
    ruta_destino = (args.get("ruta_destino") or "").strip()
    contexto_rutas = args.get("archivos_contexto") or []
    instrucciones = (args.get("instrucciones") or "").strip()
    abrir = args.get("abrir_editor", True)

    # Leer archivo destino si ya existe (edición, no creación)
    destino_actual = ""
    if ruta_destino:
        path_dest = os.path.join(cwd, ruta_destino) if not os.path.isabs(ruta_destino) else ruta_destino
        if os.path.isfile(path_dest):
            destino_actual = _leer_archivo(path_dest)

    contexto_str = _bloque_archivos(contexto_rutas, cwd)

    prompt = f"""Eres un dev senior experto. Escribe código de producción limpio, correcto y sin placeholder.

{f'<context>{chr(10)}{contexto_str}{chr(10)}</context>' if contexto_str else ''}

{f'<current_file path="{ruta_destino}">{chr(10)}{destino_actual}{chr(10)}</current_file>' if destino_actual else ''}

TAREA: {tarea}
{f'INSTRUCCIONES ADICIONALES: {instrucciones}' if instrucciones else ''}

REGLAS ESTRICTAS:
- Código completo y funcional. Sin TODOs, sin placeholders, sin "// implementar".
- Imita exactamente el estilo del proyecto (imports, naming, estructura).
- TypeScript: todos los tipos correctos, nada de `any` salvo último recurso.
- Si modificas un archivo existente: devuelve el archivo COMPLETO, no solo el fragmento.
- Responde ÚNICAMENTE con el código. Sin explicaciones, sin markdown fences.
"""

    ctx.set_widget_state("thinking")
    try:
        codigo = _llamar_modelo(prompt, ctx)
    except Exception as e:
        ctx.set_widget_state("idle")
        return f"Error llamando al modelo de código: {e}"

    codigo = _limpiar_codigo(codigo)

    if ruta_destino:
        path_dest = os.path.join(cwd, ruta_destino) if not os.path.isabs(ruta_destino) else ruta_destino
        _escribir(path_dest, codigo)
        if abrir:
            abrir_en_editor(path_dest)
        lineas = len(codigo.splitlines())
        return (
            f"[{_modelo_label()}] Código generado → {ruta_destino} "
            f"({lineas} líneas). Abierto en el editor."
        )

    return truncar_salida(f"[{_modelo_label()}]\n\n{codigo}", 4000)


def _refactorizar_codigo(args: dict, ctx: ToolContext) -> str:
    ruta = (args.get("ruta") or "").strip()
    objetivo = (args.get("objetivo") or "legibilidad").strip()
    if not ruta:
        return "Necesito la ruta del archivo a refactorizar"

    cwd = resolver_directorio(ctx)
    path = os.path.join(cwd, ruta) if not os.path.isabs(ruta) else ruta
    if not os.path.isfile(path):
        return f"No encontré: {path}"

    contenido = _leer_archivo(path)
    contexto_rutas = args.get("archivos_contexto") or []
    contexto_str = _bloque_archivos(contexto_rutas, cwd)

    prompt = f"""Eres un dev senior. Refactoriza el siguiente código.

{f'<context>{chr(10)}{contexto_str}{chr(10)}</context>' if contexto_str else ''}

<file path="{ruta}">
{contenido}
</file>

OBJETIVO DEL REFACTOR: {objetivo}

REGLAS:
- Mantén exactamente el mismo comportamiento externo (no cambies la API pública).
- Aplica el objetivo sin excederte — no cambies lo que no hace falta.
- Devuelve el archivo COMPLETO refactorizado.
- Solo código, sin explicaciones ni fences.
"""

    ctx.set_widget_state("thinking")
    try:
        resultado = _llamar_modelo(prompt, ctx)
    except Exception as e:
        ctx.set_widget_state("idle")
        return f"Error en el modelo: {e}"

    resultado = _limpiar_codigo(resultado)
    _escribir(path, resultado)
    abrir_en_editor(path)
    return f"[{_modelo_label()}] Refactor aplicado → {ruta}. Abierto en Cursor."


def _revisar_y_mejorar(args: dict, ctx: ToolContext) -> str:
    ruta = (args.get("ruta") or "").strip()
    aplicar = bool(args.get("aplicar_cambios", False))
    if not ruta:
        return "Necesito la ruta del archivo a revisar"

    cwd = resolver_directorio(ctx)
    path = os.path.join(cwd, ruta) if not os.path.isabs(ruta) else ruta
    if not os.path.isfile(path):
        return f"No encontré: {path}"

    contenido = _leer_archivo(path)

    if aplicar:
        prompt = f"""Revisa este código y aplica todas las mejoras necesarias.

<file path="{ruta}">
{contenido}
</file>

Busca y corrige: bugs, problemas de seguridad (XSS, inyección, secrets expuestos),
código muerto, renders innecesarios, tipos incorrectos, manejo de errores faltante,
race conditions, memory leaks.

Devuelve el archivo COMPLETO mejorado. Solo código, sin fences ni explicaciones.
"""
        ctx.set_widget_state("thinking")
        resultado = _limpiar_codigo(_llamar_modelo(prompt, ctx))
        _escribir(path, resultado)
        abrir_en_editor(path)
        return f"[{_modelo_label()}] Revisión aplicada → {ruta}. Abierto en Cursor."
    else:
        prompt = f"""Haz una revisión de código profunda y devuelve un informe.

<file path="{ruta}">
{contenido}
</file>

Reporta en estas categorías (omite las que estén bien):
🐛 BUGS: problemas de lógica o comportamiento incorrecto
🔒 SEGURIDAD: vulnerabilidades, secrets, XSS, inyección
⚡ RENDIMIENTO: operaciones innecesarias, re-renders, queries N+1
🧹 CALIDAD: código muerto, duplicación, nombres confusos
📝 TIPOS: `any`, tipos incorrectos, tipos faltantes (TypeScript)
⚠️ ERRORES: errores sin manejar, promesas sin catch

Para cada problema: línea aproximada, descripción breve, solución concreta.
Sé directo y práctico. Si el código está bien, dilo.
"""
        ctx.set_widget_state("thinking")
        try:
            informe = _llamar_modelo(prompt, ctx, max_tokens=2048)
        except Exception as e:
            ctx.set_widget_state("idle")
            return f"Error en el modelo: {e}"
        return truncar_salida(f"[{_modelo_label()}] Revisión de {ruta}:\n\n{informe}", 3500)


def _generar_tests(args: dict, ctx: ToolContext) -> str:
    ruta = (args.get("ruta") or "").strip()
    tipo = (args.get("tipo") or "unitarios").strip()
    if not ruta:
        return "Necesito la ruta del archivo a testear"

    cwd = resolver_directorio(ctx)
    path = os.path.join(cwd, ruta) if not os.path.isabs(ruta) else ruta
    if not os.path.isfile(path):
        return f"No encontré: {path}"

    contenido = _leer_archivo(path)

    # Inferir ruta de tests
    ruta_tests = (args.get("ruta_tests") or "").strip()
    if not ruta_tests:
        ruta_tests = _inferir_ruta_tests(ruta, cwd)

    # Detectar framework
    framework = _detectar_framework_tests(cwd)

    prompt = f"""Genera tests {tipo} para el siguiente archivo.

<file path="{ruta}">
{contenido}
</file>

Framework de tests: {framework}
Tipo: {tipo}

REGLAS:
- Tests completos y funcionales, no esqueletos.
- Cubre casos felices Y casos de error / edge cases.
- Nombres de test descriptivos en español o inglés según el estilo del proyecto.
- Imports correctos — no inventes rutas, usa la ruta relativa real: {ruta}
- Solo código de tests, sin explicaciones ni fences.
"""

    ctx.set_widget_state("thinking")
    try:
        tests = _llamar_modelo(prompt, ctx)
    except Exception as e:
        ctx.set_widget_state("idle")
        return f"Error generando tests: {e}"

    tests = _limpiar_codigo(tests)
    path_tests = os.path.join(cwd, ruta_tests) if not os.path.isabs(ruta_tests) else ruta_tests
    _escribir(path_tests, tests)
    abrir_en_editor(path_tests)
    return (
        f"[{_modelo_label()}] Tests generados → {ruta_tests} "
        f"({len(tests.splitlines())} líneas). Abierto en Cursor."
    )


def _ejecutar_tarea(args: dict, ctx: ToolContext) -> str:
    """
    Loop agéntico completo:
    1. Planificar (qué archivos crear/modificar y por qué)
    2. Ejecutar (generar cada archivo con contexto completo)
    3. Verificar (lint + typecheck)
    4. Auto-corregir (hasta _MAX_ITERACIONES_FIX veces)
    5. Reportar resultado
    """
    tarea = (args.get("tarea") or "").strip()
    if not tarea:
        return "Necesito la descripción de la tarea"

    cwd = resolver_directorio(ctx, args.get("directorio"))
    archivos_hint = args.get("archivos_relevantes") or []

    ctx.set_widget_state("thinking")
    log = []

    # ── FASE 0: Indexar proyecto completo ──────────────────────────────────
    # Leer TODO el codebase para dar al modelo de código contexto total.
    # Los archivos hint se incluyen primero (prioridad máxima).
    contexto_proyecto = _contexto_completo(cwd, archivos_hint)
    log.append(f"📦 Proyecto indexado ({len(contexto_proyecto):,} chars)")

    # ── FASE 1: Planificación ───────────────────────────────────────────────
    plan_prompt = f"""Eres un dev senior con acceso al codebase completo. Analiza la tarea y devuelve un plan de acción en JSON.

CODEBASE COMPLETO:
{contexto_proyecto}

TAREA: {tarea}

Devuelve SOLO un JSON válido con esta forma exacta:
{{
  "resumen": "Una frase de qué hace esta tarea",
  "archivos": [
    {{
      "ruta": "ruta/relativa/al/archivo.ts",
      "accion": "crear" | "modificar",
      "descripcion": "Qué hace este archivo y qué cambios necesita",
      "contexto_necesario": ["ruta/de/archivo/a/leer.ts", "otro.ts"]
    }}
  ]
}}

Sé preciso con las rutas — usa las que existen en la estructura del proyecto.
No inventes dependencias que no existen. Si la tarea es pequeña, lista solo 1-2 archivos.
"""
    try:
        plan_raw = _llamar_modelo(plan_prompt, ctx, max_tokens=2048)
        plan_raw = _limpiar_codigo(plan_raw)
        # Extraer JSON si viene envuelto en texto
        match = re.search(r'\{[\s\S]*\}', plan_raw)
        plan = json.loads(match.group() if match else plan_raw)
    except Exception as e:
        # Si falla la planificación, intentar ejecución directa sin plan
        log.append(f"⚠️ Planificación simplificada ({e})")
        plan = {"resumen": tarea, "archivos": []}

    resumen_plan = plan.get("resumen", tarea)
    archivos_plan = plan.get("archivos", [])
    log.append(f"📋 Plan: {resumen_plan}")
    log.append(f"📁 Archivos a tocar: {len(archivos_plan)}")

    archivos_modificados = []

    # ── FASE 2: Ejecución archivo por archivo ───────────────────────────────
    for item in archivos_plan:
        ruta = item.get("ruta", "")
        accion = item.get("accion", "crear")
        descripcion = item.get("descripcion", "")
        contexto_rutas = item.get("contexto_necesario", []) + archivos_hint

        if not ruta:
            continue

        path = os.path.join(cwd, ruta) if not os.path.isabs(ruta) else ruta
        contenido_actual = _leer_archivo(path) if os.path.isfile(path) else ""

        gen_prompt = f"""Eres un dev senior con acceso al codebase completo. {accion.upper()} el archivo indicado.

CODEBASE COMPLETO:
{contexto_proyecto}

{f'CONTENIDO ACTUAL DE {ruta}:{chr(10)}{contenido_actual}' if contenido_actual else ''}

TAREA GLOBAL: {tarea}
TAREA ESPECÍFICA PARA ESTE ARCHIVO: {descripcion}

REGLAS ESTRICTAS:
- Código completo y funcional. Sin TODOs ni placeholders.
- Imita exactamente el estilo existente del proyecto.
- TypeScript: tipos correctos, sin `any`.
- Devuelve el archivo COMPLETO.
- Solo código. Sin explicaciones. Sin markdown fences.
"""
        try:
            codigo = _limpiar_codigo(_llamar_modelo(gen_prompt, ctx))
            _escribir(path, codigo)
            archivos_modificados.append(ruta)
            log.append(f"  ✅ {accion}: {ruta} ({len(codigo.splitlines())} líneas)")
        except Exception as e:
            log.append(f"  ❌ Error en {ruta}: {e}")

    if not archivos_modificados:
        # No hubo archivos del plan — generar directamente
        try:
            fallback_prompt = f"""Eres un dev senior con acceso al codebase completo. Ejecuta esta tarea.

CODEBASE COMPLETO:
{contexto_proyecto}

TAREA: {tarea}

Devuelve el código completo del archivo principal. Solo código, sin fences.
"""
            codigo = _limpiar_codigo(_llamar_modelo(fallback_prompt, ctx))
            return truncar_salida(f"[{_modelo_label()}]\n\n{codigo}", 4000)
        except Exception as e:
            return f"Error ejecutando la tarea: {e}"

    # ── FASE 3: Verificación + auto-corrección ──────────────────────────────
    errores_previos = ""
    for iteracion in range(_MAX_ITERACIONES_FIX):
        errores = _verificar_proyecto(cwd)
        if not errores:
            log.append(f"  ✅ Verificación OK (iteración {iteracion + 1})")
            break

        log.append(f"  ⚠️ Errores en iteración {iteracion + 1} — corrigiendo...")

        # Auto-corrección
        fix_prompt = f"""Corrige estos errores de compilación/lint en el proyecto.

ERRORES:
{errores}

ARCHIVOS MODIFICADOS:
{_bloque_archivos(archivos_modificados, cwd)}

INSTRUCCIONES:
- Analiza cada error, entiende la causa raíz
- Devuelve un JSON con los archivos corregidos:
{{
  "archivos": [
    {{"ruta": "ruta/archivo.ts", "contenido": "...código completo..."}}
  ]
}}
Solo JSON válido. Los contenidos deben ser código completo y funcional.
"""
        try:
            fix_raw = _limpiar_codigo(_llamar_modelo(fix_prompt, ctx, max_tokens=6000))
            match = re.search(r'\{[\s\S]*\}', fix_raw)
            fix_data = json.loads(match.group() if match else fix_raw)
            for f_item in fix_data.get("archivos", []):
                f_ruta = f_item.get("ruta", "")
                f_codigo = f_item.get("contenido", "")
                if f_ruta and f_codigo:
                    f_path = os.path.join(cwd, f_ruta) if not os.path.isabs(f_ruta) else f_ruta
                    _escribir(f_path, _limpiar_codigo(f_codigo))
                    log.append(f"    🔧 Corregido: {f_ruta}")
            errores_previos = errores
        except Exception as e:
            log.append(f"    ❌ Auto-corrección falló: {e}")
            break

    # ── FASE 4: Abrir archivos en editor ────────────────────────────────────
    for ruta in archivos_modificados[:3]:
        path = os.path.join(cwd, ruta) if not os.path.isabs(ruta) else ruta
        abrir_en_editor(path)

    return truncar_salida(
        f"[{_modelo_label()}] Tarea completada: {resumen_plan}\n\n"
        + "\n".join(log)
        + f"\n\nArchivos: {', '.join(archivos_modificados)}",
        3500,
    )


def _explicar_proyecto(args: dict, ctx: ToolContext) -> str:
    cwd = resolver_directorio(ctx, args.get("directorio"))
    foco = (args.get("foco") or "general").strip().lower()
    nivel = (args.get("nivel_dev") or "auto").strip().lower()

    ctx.set_widget_state("thinking")

    contexto = _contexto_completo(cwd, [], max_chars=100_000)
    nombre_proyecto = os.path.basename(cwd)

    focos_desc = {
        "general": "arquitectura, flujos principales, fortalezas, debilidades y recomendaciones generales",
        "arquitectura": "patrones de diseño, separación de capas, acoplamiento, cohesión, flujo de datos",
        "seguridad": "vulnerabilidades, autenticación, autorización, exposición de datos, manejo de secrets",
        "rendimiento": "cuellos de botella, queries ineficientes, re-renders, uso de memoria, concurrencia",
        "deuda_tecnica": "código duplicado, funciones gigantes, falta de tests, acoplamiento alto, código obsoleto",
        "onboarding": "qué hace el proyecto, cómo empezar, qué leer primero, flujo principal de principio a fin",
    }
    desc_foco = focos_desc.get(foco, focos_desc["general"])

    niveles_desc = {
        "junior": "El dev conoce los fundamentos pero no patrones avanzados. Usa analogías concretas, explica el 'por qué' de cada decisión.",
        "senior": "El dev tiene experiencia profunda. Sé técnico, directo, habla de tradeoffs y decisiones de diseño sin explicar lo obvio.",
        "auto": "Detecta el nivel de sofisticación del código y ajusta la profundidad automáticamente.",
    }
    desc_nivel = niveles_desc.get(nivel, niveles_desc["auto"])

    prompt = f"""Eres un arquitecto de software senior haciendo una consultoría técnica.
Analiza este proyecto completo y genera un informe estructurado y accionable.

PROYECTO: {nombre_proyecto}
FOCO DE ANÁLISIS: {desc_foco}
NIVEL DEL DEV: {desc_nivel}

CODEBASE COMPLETO:
{contexto}

Genera el análisis con estas secciones:

## RESUMEN EJECUTIVO
2-3 frases: qué hace el proyecto, tech stack principal, y la observación más importante.

## ARQUITECTURA Y FLUJOS
- Patrón principal (MVC, Clean Architecture, monolito modular, microservicios, etc.)
- Cómo están organizadas las capas/módulos
- Flujo de datos: desde la entrada del usuario hasta la respuesta/efecto
- Qué decisiones de diseño son notables

## PUNTOS FUERTES
2-4 cosas bien implementadas, con referencia a archivos o módulos específicos.

## ÁREAS DE MEJORA (priorizadas)
Para cada punto incluye:
- Prioridad: 🔴 CRÍTICO | 🟡 IMPORTANTE | 🟢 NICETOHAVE
- Problema concreto (qué está mal y por qué importa)
- Archivo(s) y línea aproximada si aplica
- Recomendación exacta (qué hacer, no solo "mejorar X")
- Esfuerzo: bajo (<1h) | medio (1-4h) | alto (>4h)

## TOP 3 PRÓXIMOS PASOS
Las 3 acciones que más valor agregarían, en orden de prioridad.
Para cada una: qué hacer + por qué es prioritario.

## PREGUNTAS AL DEV
2-3 preguntas abiertas sobre decisiones de diseño no obvias desde el código.
(Útiles para entender intención del diseño antes de cambiar algo)

Sé específico y directo. Cita archivos y módulos reales del proyecto.
Escribe en español. Adapta la profundidad técnica al nivel indicado.
No rellenes con genéricos — todo debe ser específico de ESTE proyecto.
"""

    try:
        analisis = _llamar_modelo(prompt, ctx, max_tokens=4096)
    except Exception as e:
        ctx.set_widget_state("idle")
        return f"Error analizando el proyecto: {e}"

    return truncar_salida(
        f"[Consultoría: {nombre_proyecto} | foco: {foco} | nivel: {nivel}]\n\n{analisis}",
        5000,
    )


def _contexto_completo(cwd: str, archivos_hint: list[str], max_chars: int = 120_000) -> str:
    """
    Indexa el proyecto completo para dar al modelo de código máximo contexto.
    Los archivos hint tienen prioridad y se incluyen primero completos.
    Luego se rellena con el resto del codebase hasta max_chars.
    """
    secciones = [f"# Proyecto: {os.path.basename(cwd)}", f"# Ruta: {cwd}", ""]
    chars_usados = sum(len(s) for s in secciones)

    # 1. Archivos hint primero (contexto explícito del usuario)
    hint_incluidos = set()
    for ruta in archivos_hint:
        path = os.path.join(cwd, ruta) if not os.path.isabs(ruta) else ruta
        if not os.path.isfile(path):
            continue
        contenido = _leer_archivo(path)
        entrada = f'\n<file path="{ruta}" priority="hint">\n{contenido}\n</file>'
        secciones.append(entrada)
        chars_usados += len(entrada)
        hint_incluidos.add(os.path.realpath(path))

    # 2. Resto del proyecto por orden de prioridad (configs → código pequeño → código grande)
    todos = _recolectar_archivos(cwd)
    for rel_path, full_path, size in todos:
        if chars_usados >= max_chars:
            break
        if os.path.realpath(full_path) in hint_incluidos:
            continue

        espacio = max_chars - chars_usados
        max_archivo = min(espacio, 12_000)
        try:
            with open(full_path, encoding="utf-8", errors="replace") as f:
                contenido = f.read(max_archivo)
            truncado = size > max_archivo
            attr = ' truncated="true"' if truncado else ""
            entrada = f'\n<file path="{rel_path}"{attr}>\n{contenido}\n</file>'
            secciones.append(entrada)
            chars_usados += len(entrada)
        except OSError:
            continue

    return "\n".join(secciones)


def _arbol_compacto(cwd: str) -> str:
    lineas = []
    ignore = {"node_modules", "venv", ".venv", "__pycache__", ".git", "dist", "build", ".next"}
    base_depth = cwd.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(cwd):
        depth = root.rstrip(os.sep).count(os.sep) - base_depth
        if depth > 2:
            dirs.clear()
            continue
        dirs[:] = sorted(d for d in dirs if d not in ignore and not d.startswith("."))
        indent = "  " * depth
        nombre = os.path.basename(root) or root
        if depth > 0:
            lineas.append(f"{indent}{nombre}/")
        code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}
        for f in sorted(files)[:15]:
            if os.path.splitext(f)[1] in code_exts or f in ("package.json", "pyproject.toml"):
                lineas.append(f"{'  ' * (depth+1)}{f}")
        if len(lineas) > 80:
            break
    return "\n".join(lineas)


def _verificar_proyecto(cwd: str) -> str:
    """Retorna string de errores o vacío si todo OK."""
    errores = []

    # Python
    if os.path.isfile(os.path.join(cwd, "pyproject.toml")) or \
       os.path.isfile(os.path.join(cwd, "requirements.txt")):
        from agent_tools.utils import run_shell
        r = run_shell("ruff check . --output-format=concise 2>&1", cwd, timeout=30)
        if r.returncode not in (0, 127) and r.stdout:
            errores.append(r.stdout[:2000])
        r2 = run_shell("mypy . --ignore-missing-imports --no-error-summary 2>&1", cwd, timeout=60)
        if r2.returncode not in (0, 127) and r2.stdout:
            errores.append(r2.stdout[:2000])

    # TypeScript
    tsc = os.path.join(cwd, "node_modules", ".bin", "tsc")
    if os.path.isfile(tsc) and os.path.isfile(os.path.join(cwd, "tsconfig.json")):
        from agent_tools.utils import run_shell
        r = run_shell(f"{tsc} --noEmit 2>&1", cwd, timeout=120)
        if r.returncode != 0 and r.stdout:
            errores.append(r.stdout[:2000])

    return "\n".join(errores)


def _inferir_ruta_tests(ruta: str, cwd: str) -> str:
    nombre, ext = os.path.splitext(os.path.basename(ruta))
    carpeta = os.path.dirname(ruta)

    # Python: test_nombre.py junto al archivo o en tests/
    if ext == ".py":
        tests_dir = os.path.join(cwd, "tests")
        if os.path.isdir(tests_dir):
            return os.path.join("tests", f"test_{nombre}.py")
        return os.path.join(carpeta, f"test_{nombre}.py")

    # JS/TS: nombre.test.ts junto al archivo o en __tests__/
    if ext in (".ts", ".tsx", ".js", ".jsx"):
        tests_dir = os.path.join(cwd, os.path.dirname(ruta), "__tests__")
        if os.path.isdir(tests_dir):
            return os.path.join(os.path.dirname(ruta), "__tests__", f"{nombre}.test{ext}")
        return os.path.join(carpeta, f"{nombre}.test{ext}")

    return os.path.join(carpeta, f"{nombre}.test{ext}")


def _detectar_framework_tests(cwd: str) -> str:
    pkg = os.path.join(cwd, "package.json")
    if os.path.isfile(pkg):
        try:
            with open(pkg, encoding="utf-8") as f:
                d = json.load(f)
            deps = {}
            deps.update(d.get("dependencies", {}))
            deps.update(d.get("devDependencies", {}))
            if "vitest" in deps:
                return "vitest"
            if "jest" in deps:
                return "jest"
            if "mocha" in deps:
                return "mocha"
        except Exception:
            pass

    for f in ("pytest.ini", "pyproject.toml", "setup.cfg"):
        if os.path.isfile(os.path.join(cwd, f)):
            return "pytest"

    if os.path.isfile(os.path.join(cwd, "requirements.txt")):
        return "pytest"

    return "jest"

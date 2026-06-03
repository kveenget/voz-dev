# Agent tools (extensible, estilo Cursor)

## Cómo se añaden herramientas

1. Crear handler en `handlers/mi_modulo.py`
2. `register(ToolSpec(name, description, parameters, handler, category))`
3. Llamar el registrador desde `handlers/__init__.py`
4. Añadir categoría a `VOZ_TOOL_GROUPS` en `.env` si aplica

## Categorías

| Grupo | Ejemplos |
|-------|----------|
| `ide` | terminal, tests, leer/escribir archivo, VS Code |
| `coding` | buscar_codigo, listar_directorio |
| `mac` | apps, Spotify, notas, sistema (`handlers/mac.py`) |
| `web` | buscar en internet (`handlers/web.py`) |
| `coding` | aplicar_patch, buscar_codigo, listar_directorio |
| `vision` | ver_pantalla, analizar_pantalla (captura + gpt-4o vision) |

## Roadmap producto (tipo Cursor)

- **MCP**: `VOZ_MCP_CONFIG=tools.json` → servidores MCP exponen más tools sin tocar Python
- **IDE bridge**: extensión Cursor/VS Code → archivo activo, selección, aplicar diff
- **Permisos**: `VOZ_TOOL_POLICY=ask|allow` por categoría
- **Plugins**: `VOZ_PLUGINS_DIR` (default `~/.voz/tools/*.py`) con función `register_tools()` cargada al inicio

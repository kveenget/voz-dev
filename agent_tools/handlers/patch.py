"""Edición por parches (search/replace robusto)."""

import os

from agent_tools.context import ToolContext
from agent_tools.registry import ToolSpec, register
from agent_tools.utils import path_en_proyecto


def register_patch_tools(project_root: str) -> None:
    _ = project_root
    register(
        ToolSpec(
            "aplicar_patch",
            "Aplica un cambio en un archivo: reemplaza old_string por new_string. "
            "old_string debe coincidir exactamente (incluye espacios). "
            "Para archivos nuevos usa escribir_archivo.",
            {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {
                        "type": "boolean",
                        "description": "Si true, reemplaza todas las ocurrencias",
                    },
                },
                "required": ["ruta", "old_string", "new_string"],
            },
            _aplicar_patch,
            "coding",
        )
    )


def _aplicar_patch(args: dict, ctx: ToolContext) -> str:
    path = path_en_proyecto(ctx, args.get("ruta", ""))
    old = args.get("old_string", "")
    new = args.get("new_string", "")
    if not old:
        return "old_string vacío"
    if not os.path.isfile(path):
        return f"No existe: {path}"
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        return "old_string no encontrado en el archivo"
    if args.get("replace_all"):
        updated = content.replace(old, new)
        count = content.count(old)
    else:
        updated = content.replace(old, new, 1)
        count = 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    return f"Patch aplicado ({count} reemplazo(s)): {path}"

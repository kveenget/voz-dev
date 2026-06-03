from agent_tools.config import enabled_categories
from agent_tools.constants import SHUTDOWN_SENTINEL
from agent_tools.context import ToolContext
from agent_tools.handlers import register_builtin_tools
from agent_tools.plugins import load_plugins
from agent_tools.registry import execute, get_openai_tools, list_tools

_initialized = False


def init_tools(project_root: str) -> None:
    global _initialized
    if _initialized:
        return
    register_builtin_tools(project_root)
    load_plugins()
    _initialized = True


def get_session_tools(categories=None) -> list[dict]:
    cats = categories or enabled_categories()
    return get_openai_tools(cats)


def run_tool(name: str, args: dict, ctx: ToolContext) -> str:
    result = execute(name, args, ctx)
    if result is not None:
        return result
    return f"Herramienta desconocida: {name}"


__all__ = [
    "SHUTDOWN_SENTINEL",
    "ToolContext",
    "get_session_tools",
    "init_tools",
    "list_tools",
    "run_tool",
]

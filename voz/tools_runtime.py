from agent_tools import SHUTDOWN_SENTINEL, ToolContext, get_session_tools, init_tools, run_tool
from agent_tools.config import enabled_categories

from voz import config as cfg
from voz.widget_ctl import set_widget_state

_CTX: ToolContext | None = None


def bootstrap() -> ToolContext:
    global _CTX
    init_tools(cfg.PROJECT_ROOT)
    _CTX = ToolContext(
        project_root=cfg.PROJECT_ROOT,
        ssl_context=cfg.ssl_context,
        set_widget_state=set_widget_state,
        openai_api_key=cfg.OPENAI_API_KEY or "",
    )
    return _CTX


def session_tools() -> list[dict]:
    return get_session_tools(enabled_categories())


def ejecutar_funcion(nombre: str, args: dict) -> str:
    ctx = _CTX or bootstrap()
    print(f"⚡ {nombre}({args})")
    try:
        return run_tool(nombre, args, ctx)
    except Exception as e:
        print(f"❌ Error: {e}")
        return str(e)


__all__ = ["SHUTDOWN_SENTINEL", "bootstrap", "ejecutar_funcion", "session_tools"]

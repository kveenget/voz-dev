from dataclasses import dataclass
from typing import Any, Callable

from agent_tools.context import ToolContext

Handler = Callable[[dict, ToolContext], str]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Handler
    category: str = "coding"


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    if spec.name in _REGISTRY:
        raise ValueError(f"Tool duplicada: {spec.name}")
    _REGISTRY[spec.name] = spec


def get_openai_tools(categories: set[str] | None = None) -> list[dict]:
    tools = []
    for spec in _REGISTRY.values():
        if categories and spec.category not in categories:
            continue
        tools.append({
            "type": "function",
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        })
    return tools


def execute(name: str, args: dict, ctx: ToolContext) -> str | None:
    spec = _REGISTRY.get(name)
    if not spec:
        return None
    return spec.handler(args, ctx)


def list_tools() -> list[str]:
    return sorted(_REGISTRY.keys())

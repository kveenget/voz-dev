from dataclasses import dataclass
from typing import Callable, Optional
import ssl


@dataclass
class ToolContext:
    project_root: str
    ssl_context: ssl.SSLContext
    set_widget_state: Callable[[str], None]
    openai_api_key: str = ""

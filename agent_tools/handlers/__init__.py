from agent_tools.handlers.codegen import register_codegen_tools
from agent_tools.handlers.coding import register_coding_tools
from agent_tools.handlers.git import register_git_tools
from agent_tools.handlers.github import register_github_tools
from agent_tools.handlers.ide import register_ide_tools
from agent_tools.handlers.mac import register_mac_tools
from agent_tools.handlers.notes import register_notes_tools
from agent_tools.handlers.patch import register_patch_tools
from agent_tools.handlers.vision import register_vision_tools
from agent_tools.handlers.web import register_web_tools


def register_builtin_tools(project_root: str) -> None:
    register_ide_tools(project_root)
    register_coding_tools(project_root)
    register_codegen_tools(project_root)
    register_git_tools(project_root)
    register_github_tools(project_root)
    register_notes_tools(project_root)
    register_patch_tools(project_root)
    register_vision_tools(project_root)
    register_mac_tools(project_root)
    register_web_tools(project_root)

from typing import Any

from app.core.config import Settings
from app.services.mcp_tools.base import MCPToolSpec
from app.services.mcp_tools.friend_link_parser import TOOL_SPEC as FRIEND_LINK_PARSER_TOOL


_TOOL_REGISTRY: dict[str, MCPToolSpec] = {
    FRIEND_LINK_PARSER_TOOL.name: FRIEND_LINK_PARSER_TOOL,
}


def list_public_tools() -> list[MCPToolSpec]:
    return [tool for tool in _TOOL_REGISTRY.values() if tool.public]


def get_public_tool(name: str) -> MCPToolSpec | None:
    tool = _TOOL_REGISTRY.get(name)
    if tool and tool.public:
        return tool
    return None


def call_public_tool(name: str, arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    tool = get_public_tool(name)
    if tool is None:
        raise KeyError(name)
    return tool.handler(arguments, settings)

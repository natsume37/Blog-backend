from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import Settings


ToolHandler = Callable[[dict[str, Any], Settings], dict[str, Any]]


@dataclass(frozen=True)
class MCPToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    public: bool
    handler: ToolHandler

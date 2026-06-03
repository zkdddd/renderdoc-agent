"""Tool registry for RenderDoc Agent."""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    """A callable tool with metadata."""

    name: str
    description: str
    parameters: dict  # JSON Schema for parameters
    execute: Callable[..., Any]

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry for managing tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def to_openai_schemas(self) -> list[dict]:
        """Get all tool definitions in OpenAI function calling format."""
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> Any:
        """Execute a tool by name with given arguments."""
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        return tool.execute(**arguments)

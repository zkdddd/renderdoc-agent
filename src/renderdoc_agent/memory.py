"""Conversation memory management."""

from dataclasses import dataclass, field


@dataclass
class Memory:
    """Manages conversation message history."""

    messages: list[dict] = field(default_factory=list)
    max_messages: int = 50

    def add_message(self, role: str, content: str, tool_calls: list | None = None):
        """Add a message to history."""
        msg = {"role": role, "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)
        self._trim()

    def add_tool_result(self, tool_call_id: str, name: str, content: str):
        """Add a tool result message."""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        })

    def get_messages(self) -> list[dict]:
        """Get all messages for LLM context."""
        return list(self.messages)

    def clear(self):
        """Clear conversation history."""
        self.messages.clear()

    def _trim(self):
        """Keep history within limits, preserving system message."""
        if len(self.messages) <= self.max_messages:
            return
        # Keep first message (system) and trim oldest after it
        system = self.messages[:1]
        recent = self.messages[-(self.max_messages - 1):]
        self.messages = system + recent

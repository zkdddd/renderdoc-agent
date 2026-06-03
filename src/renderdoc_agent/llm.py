"""Ollama LLM client for RenderDoc Agent."""

import json
import requests
from typing import Generator

from .config import Config


class OllamaClient:
    """Client for Ollama local LLM service."""

    def __init__(self, config: Config):
        self.base_url = config.ollama_base_url
        self.model = config.model
        self.temperature = config.temperature

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> dict | Generator[dict, None, None]:
        """Send a chat request to Ollama.

        Args:
            messages: Conversation messages.
            tools: Tool definitions in OpenAI function calling format.
            stream: Whether to stream the response.

        Returns:
            Response dict or generator of response chunks.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": self.temperature},
        }
        if tools:
            payload["tools"] = tools

        if stream:
            return self._stream(url, payload)

        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def _stream(self, url: str, payload: dict) -> Generator[dict, None, None]:
        """Stream response chunks from Ollama."""
        resp = requests.post(url, json=payload, stream=True, timeout=120)
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                yield json.loads(line)

    def chat_once(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Non-streaming chat call, returns the full response dict."""
        return self.chat(messages, tools=tools, stream=False)

"""Configuration for RenderDoc Agent."""

from dataclasses import dataclass, field


@dataclass
class Config:
    # Ollama settings
    ollama_base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b"

    # Agent settings
    max_tool_rounds: int = 5
    temperature: float = 0.7

    # Default analysis platform
    default_platform: str = "pc_high"

    # renderdoc Python module path (directory containing renderdoc.pyd / renderdoc.so)
    renderdoc_module_path: str = ""

    # Python executable used by the helper process
    helper_python: str = ""

    # Simulated data mode (when renderdoc module is unavailable)
    use_mock_data: bool = False

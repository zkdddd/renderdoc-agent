"""Analyze RDC files using RenderDoc Python API or mock data."""

import os
from typing import Callable, Optional

from .registry import Tool
from ..config import Config


def _mock_rdc_data(rdc_file: str) -> dict:
    """Generate mock analysis data for development/testing."""
    filename = os.path.basename(rdc_file)
    return {
        "draw_calls": 2347,
        "triangles": 1_856_000,
        "vertices": 2_134_000,
        "unique_shaders": 42,
        "shader_list": [
            "PBR_Opaque", "PBR_Transparent", "UI_Default", "PostProcess_Bloom",
            "Shadow_Caster", "Terrain_Splat", "Particle_Additive", "Skybox_Cubemap",
        ],
        "unique_textures": 187,
        "texture_memory_mb": 1843.2,
        "source_file": filename,
        "mock": True,
    }


def analyze_rdc(rdc_file: str, get_data: Optional[Callable] = None,
                use_mock: bool = False) -> dict:
    """Analyze an .rdc file and return structured rendering metrics.

    Args:
        rdc_file: Path to the .rdc file.
        get_data: Callable(rdc_file) -> dict of pre-extracted data (or None if unavailable).
        use_mock: If True, return mock data when renderdoc is unavailable.

    Returns:
        Dict with rendering metrics.
    """
    if not os.path.isfile(rdc_file) and not use_mock:
        raise FileNotFoundError(f"RDC file not found: {rdc_file}")

    if get_data is not None:
        extracted = get_data(rdc_file)
        if extracted is not None:
            dc = extracted.get("drawcall_data", {})
            if "error" not in dc:
                result = {
                    "draw_calls": dc.get("draw_calls", 0),
                    "triangles": dc.get("triangles", 0),
                    "vertices": dc.get("vertices", 0),
                    "unique_shaders": dc.get("unique_shaders", 0),
                    "shader_list": dc.get("shader_list", []),
                    "unique_textures": dc.get("unique_textures", 0),
                    "texture_memory_mb": dc.get("texture_memory_mb", 0),
                    "source_file": extracted.get("source_file", os.path.basename(rdc_file)),
                    "mock": False,
                }
                return result

    if use_mock:
        return _mock_rdc_data(rdc_file)

    raise RuntimeError("renderdoc 模块不可用且 mock 数据已禁用")


def create_analyze_rdc_tool(get_data: Callable, config: Config) -> Tool:
    """Create and return the AnalyzeRDC tool.

    Args:
        get_data: Callable(rdc_file) -> extracted data dict or None.
        config: Application configuration.
    """
    def execute(rdc_file: str) -> dict:
        return analyze_rdc(
            rdc_file=rdc_file,
            get_data=get_data,
            use_mock=config.use_mock_data,
        )

    return Tool(
        name="analyze_rdc",
        description=(
            "Analyze a RenderDoc .rdc capture file. "
            "Extracts draw call count, triangle count, texture memory, "
            "shader information, and other rendering metrics. "
            "Input is the file path to the .rdc file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "rdc_file": {
                    "type": "string",
                    "description": "Path to the .rdc file to analyze",
                },
            },
            "required": ["rdc_file"],
        },
        execute=execute,
    )

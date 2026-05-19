"""Texture analysis tool for RenderDoc Agent."""

import os
from typing import Callable, Optional

from .registry import Tool
from ..config import Config


def _mock_texture_data(rdc_file: str) -> dict:
    """Generate mock texture analysis data for development/testing."""
    return {
        "total_textures": 187,
        "total_memory_mb": 1843.2,
        "format_distribution": {
            "BC1/DXT1": 45,
            "BC3/DXT5": 32,
            "BC7": 28,
            "ASTC_4x4": 25,
            "R8G8B8A8_UNORM": 20,
            "R16G16B16A16_FLOAT": 15,
            "Other": 22,
        },
        "size_distribution": {
            "4096x4096": 12,
            "2048x2048": 45,
            "1024x1024": 68,
            "512x512": 42,
            "256x256": 20,
        },
        "mipmap_status": {
            "has_mipmap": 156,
            "no_mipmap": 31,
            "partial_mipmap": 0,
        },
        "uncompressed_textures": [
            {"name": "UI_Atlas_01", "format": "R8G8B8A8_UNORM", "size": "4096x4096", "memory_mb": 64.0},
            {"name": "Character_Diffuse", "format": "R8G8B8A8_UNORM", "size": "2048x2048", "memory_mb": 16.0},
            {"name": "Particle_Sprite", "format": "R8G8B8A8_UNORM", "size": "1024x1024", "memory_mb": 4.0},
            {"name": "Font_Atlas", "format": "R8_UNORM", "size": "2048x2048", "memory_mb": 4.0},
        ],
        "largest_textures": [
            {"name": "Terrain_Height", "format": "R16_FLOAT", "size": "8192x8192", "memory_mb": 128.0},
            {"name": "Terrain_Normal", "format": "BC5", "size": "8192x8192", "memory_mb": 64.0},
            {"name": "Sky_Cubemap", "format": "BC6H", "size": "2048x2048", "memory_mb": 48.0},
            {"name": "UI_Atlas_01", "format": "R8G8B8A8_UNORM", "size": "4096x4096", "memory_mb": 64.0},
            {"name": "Character_Diffuse", "format": "BC7", "size": "4096x4096", "memory_mb": 16.0},
            {"name": "Character_Normal", "format": "BC5", "size": "4096x4096", "memory_mb": 16.0},
            {"name": "Environment_Diffuse", "format": "BC7", "size": "2048x2048", "memory_mb": 4.0},
            {"name": "Environment_Normal", "format": "BC5", "size": "2048x2048", "memory_mb": 4.0},
            {"name": "Shadow_Atlas", "format": "D24_UNORM_S8_UINT", "size": "4096x4096", "memory_mb": 64.0},
            {"name": "GBuffer_Albedo", "format": "R8G8B8A8_UNORM_SRGB", "size": "1920x1080", "memory_mb": 7.9},
        ],
        "source_file": os.path.basename(rdc_file),
        "mock": True,
    }


def analyze_textures(rdc_file: str, get_data: Optional[Callable] = None,
                     use_mock: bool = False) -> dict:
    """Analyze textures in an .rdc file.

    Args:
        rdc_file: Path to the .rdc file.
        get_data: Callable(rdc_file) -> dict of pre-extracted data (or None if unavailable).
        use_mock: If True, return mock data when renderdoc is unavailable.

    Returns:
        Dict with texture analysis results.
    """
    if not os.path.isfile(rdc_file) and not use_mock:
        raise FileNotFoundError(f"RDC file not found: {rdc_file}")

    if get_data is not None:
        extracted = get_data(rdc_file)
        if extracted is not None:
            td = extracted.get("texture_data", {})
            if "error" not in td:
                td["source_file"] = extracted.get("source_file", os.path.basename(rdc_file))
                return td

    if use_mock:
        return _mock_texture_data(rdc_file)

    raise RuntimeError("renderdoc 模块不可用且 mock 数据已禁用")


def create_texture_analysis_tool(get_data: Callable, config: Config) -> Tool:
    """Create and return the TextureAnalysis tool.

    Args:
        get_data: Callable(rdc_file) -> extracted data dict or None.
        config: Application configuration.
    """
    def execute(rdc_file: str) -> dict:
        return analyze_textures(
            rdc_file=rdc_file,
            get_data=get_data,
            use_mock=config.use_mock_data,
        )

    return Tool(
        name="analyze_textures",
        description=(
            "Analyze texture resources in a RenderDoc .rdc capture file. "
            "Provides detailed information about texture formats, sizes, mipmap status, "
            "compression ratios, memory usage, and identifies uncompressed textures. "
            "Use this to find texture-related optimization opportunities."
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

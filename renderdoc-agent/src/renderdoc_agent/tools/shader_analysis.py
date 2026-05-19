"""Shader analysis tool for RenderDoc Agent."""

import os
from typing import Callable, Optional

from .registry import Tool
from ..config import Config


def _mock_shader_data(rdc_file: str) -> dict:
    """Generate mock shader analysis data for development/testing."""
    return {
        "total_shaders": 42,
        "total_variants": 156,
        "variant_explosion": [
            {"name": "PBR_Opaque", "variants": 48, "keywords": ["NORMAL_MAP", "PARALLAX", "EMISSION", "DETAIL_MAP"]},
            {"name": "Particle_Additive", "variants": 24, "keywords": ["SOFT_PARTICLE", "DISTORTION", "FLIPBOOK"]},
            {"name": "Terrain_Splat", "variants": 16, "keywords": ["LAYERS_4", "LAYERS_8", "SNOW", "WETNESS"]},
        ],
        "complexity": [
            {"name": "PBR_Opaque", "vertex_instructions": 120, "fragment_instructions": 350, "texture_samples": 6},
            {"name": "PBR_Transparent", "vertex_instructions": 110, "fragment_instructions": 320, "texture_samples": 5},
            {"name": "PostProcess_Bloom", "vertex_instructions": 30, "fragment_instructions": 85, "texture_samples": 4},
            {"name": "PostProcess_Tonemap", "vertex_instructions": 20, "fragment_instructions": 45, "texture_samples": 2},
            {"name": "Shadow_Caster", "vertex_instructions": 60, "fragment_instructions": 10, "texture_samples": 0},
            {"name": "Terrain_Splat", "vertex_instructions": 90, "fragment_instructions": 520, "texture_samples": 12},
            {"name": "UI_Default", "vertex_instructions": 40, "fragment_instructions": 25, "texture_samples": 1},
            {"name": "Skybox_Cubemap", "vertex_instructions": 35, "fragment_instructions": 60, "texture_samples": 1},
            {"name": "Particle_Additive", "vertex_instructions": 50, "fragment_instructions": 70, "texture_samples": 2},
            {"name": "Deferred_Lighting", "vertex_instructions": 25, "fragment_instructions": 180, "texture_samples": 5},
        ],
        "uniform_usage": {
            "total_uniforms": 245,
            "unused_uniforms": 18,
            "per_shader_uniforms": [
                {"name": "PBR_Opaque", "uniforms": 32, "used": 28},
                {"name": "PBR_Transparent", "uniforms": 28, "used": 25},
                {"name": "PostProcess_Bloom", "uniforms": 12, "used": 10},
                {"name": "Terrain_Splat", "uniforms": 24, "used": 20},
                {"name": "Deferred_Lighting", "uniforms": 18, "used": 16},
            ],
        },
        "overly_complex_shaders": [
            {"name": "Terrain_Splat", "fragment_instructions": 520, "reason": "混合层数过多，建议减少 Splat 层级或使用 Virtual Texture"},
        ],
        "source_file": os.path.basename(rdc_file),
        "mock": True,
    }


def analyze_shaders(rdc_file: str, get_data: Optional[Callable] = None,
                    use_mock: bool = False) -> dict:
    """Analyze shaders in an .rdc file.

    Args:
        rdc_file: Path to the .rdc file.
        get_data: Callable(rdc_file) -> dict of pre-extracted data (or None if unavailable).
        use_mock: If True, return mock data when renderdoc is unavailable.

    Returns:
        Dict with shader analysis results.
    """
    if not os.path.isfile(rdc_file) and not use_mock:
        raise FileNotFoundError(f"RDC file not found: {rdc_file}")

    if get_data is not None:
        extracted = get_data(rdc_file)
        if extracted is not None:
            sd = extracted.get("shader_data", {})
            if "error" not in sd:
                sd["source_file"] = extracted.get("source_file", os.path.basename(rdc_file))
                return sd

    if use_mock:
        return _mock_shader_data(rdc_file)

    raise RuntimeError("renderdoc 模块不可用且 mock 数据已禁用")


def create_shader_analysis_tool(get_data: Callable, config: Config) -> Tool:
    """Create and return the ShaderAnalysis tool.

    Args:
        get_data: Callable(rdc_file) -> extracted data dict or None.
        config: Application configuration.
    """
    def execute(rdc_file: str) -> dict:
        return analyze_shaders(
            rdc_file=rdc_file,
            get_data=get_data,
            use_mock=config.use_mock_data,
        )

    return Tool(
        name="analyze_shaders",
        description=(
            "Analyze shader programs in a RenderDoc .rdc capture file. "
            "Provides information about shader variants, complexity (instruction counts), "
            "uniform usage, and identifies overly complex shaders or variant explosion. "
            "Use this to find shader-related performance issues."
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

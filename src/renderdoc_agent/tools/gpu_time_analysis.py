"""GPU time analysis tool for RenderDoc Agent."""

import os
from typing import Callable, Optional

from .registry import Tool
from ..config import Config


def _mock_gpu_time_data(rdc_file: str) -> dict:
    """Generate mock GPU timing data for development/testing."""
    return {
        "total_gpu_time_ms": 16.67,
        "frame_time_ms": 14.2,
        "fps_estimate": 70.4,
        "pass_breakdown": [
            {"name": "ShadowMap", "time_ms": 2.1, "percentage": 14.8, "draw_calls": 456},
            {"name": "GBuffer", "time_ms": 4.5, "percentage": 31.7, "draw_calls": 1234},
            {"name": "Lighting", "time_ms": 1.8, "percentage": 12.7, "draw_calls": 23},
            {"name": "Transparent", "time_ms": 2.3, "percentage": 16.2, "draw_calls": 567},
            {"name": "PostProcess", "time_ms": 1.9, "percentage": 13.4, "draw_calls": 12},
            {"name": "UI", "time_ms": 1.6, "percentage": 11.3, "draw_calls": 67},
        ],
        "top_expensive_drawcalls": [
            {"draw_call_id": 1234, "name": "DrawIndexed", "time_ms": 0.8, "shader": "PBR_Opaque", "triangles": 50000},
            {"draw_call_id": 1567, "name": "DrawIndexed", "time_ms": 0.6, "shader": "Terrain_Splat", "triangles": 42000},
            {"draw_call_id": 890, "name": "DrawIndexed", "time_ms": 0.5, "shader": "PBR_Opaque", "triangles": 38000},
            {"draw_call_id": 2100, "name": "DrawIndexed", "time_ms": 0.4, "shader": "PBR_Transparent", "triangles": 25000},
            {"draw_call_id": 456, "name": "DrawIndexed", "time_ms": 0.35, "shader": "PBR_Opaque", "triangles": 30000},
            {"draw_call_id": 789, "name": "DrawIndexed", "time_ms": 0.3, "shader": "Shadow_Caster", "triangles": 28000},
            {"draw_call_id": 1100, "name": "DrawIndexed", "time_ms": 0.28, "shader": "PBR_Opaque", "triangles": 22000},
            {"draw_call_id": 1900, "name": "DrawIndexed", "time_ms": 0.25, "shader": "Particle_Additive", "triangles": 15000},
            {"draw_call_id": 500, "name": "DrawIndexed", "time_ms": 0.22, "shader": "PBR_Opaque", "triangles": 20000},
            {"draw_call_id": 2200, "name": "DrawIndexed", "time_ms": 0.2, "shader": "UI_Default", "triangles": 5000},
        ],
        "bottleneck": "GBuffer",
        "budget_status": {
            "60fps": {"budget_ms": 16.67, "status": "PASS", "margin_ms": 2.47},
            "30fps": {"budget_ms": 33.33, "status": "PASS", "margin_ms": 19.13},
        },
        "source_file": os.path.basename(rdc_file),
        "mock": True,
    }


def analyze_gpu_time(rdc_file: str, get_data: Optional[Callable] = None,
                     use_mock: bool = False) -> dict:
    """Analyze GPU timing for each pass in an .rdc file.

    Args:
        rdc_file: Path to the .rdc file.
        get_data: Callable(rdc_file) -> dict of pre-extracted data (or None if unavailable).
        use_mock: If True, return mock data when renderdoc is unavailable.

    Returns:
        Dict with GPU timing analysis results.
    """
    if not os.path.isfile(rdc_file) and not use_mock:
        raise FileNotFoundError(f"RDC file not found: {rdc_file}")

    if get_data is not None:
        extracted = get_data(rdc_file)
        if extracted is not None:
            gd = extracted.get("gpu_time_data", {})
            if "error" not in gd:
                gd["source_file"] = extracted.get("source_file", os.path.basename(rdc_file))
                return gd

    if use_mock:
        return _mock_gpu_time_data(rdc_file)

    raise RuntimeError("renderdoc 模块不可用且 mock 数据已禁用")


def create_gpu_time_analysis_tool(get_data: Callable, config: Config) -> Tool:
    """Create and return the GPUTimeAnalysis tool.

    Args:
        get_data: Callable(rdc_file) -> extracted data dict or None.
        config: Application configuration.
    """
    def execute(rdc_file: str) -> dict:
        return analyze_gpu_time(
            rdc_file=rdc_file,
            get_data=get_data,
            use_mock=config.use_mock_data,
        )

    return Tool(
        name="analyze_gpu_time",
        description=(
            "Analyze GPU timing for render passes and draw calls in a RenderDoc .rdc capture file. "
            "Provides per-pass timing breakdown, identifies the most expensive draw calls, "
            "estimates FPS, and checks against 60fps/30fps budgets. "
            "Requires GPU performance counter support. Use this to find rendering bottlenecks."
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

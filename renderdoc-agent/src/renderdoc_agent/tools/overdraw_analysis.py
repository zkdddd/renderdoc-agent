"""Overdraw and bandwidth analysis tool for RenderDoc Agent."""

import os
from typing import Callable, Optional

from .registry import Tool
from ..config import Config


def _mock_overdraw_data(rdc_file: str) -> dict:
    """Generate mock overdraw/bandwidth data for development/testing."""
    return {
        "overdraw_ratio": 2.3,
        "overdraw_distribution": {
            "1x": "35%",
            "2x": "40%",
            "3x": "15%",
            "4x+": "10%",
        },
        "pixel_fill_rate": {
            "total_pixels_written": 4423680,
            "screen_pixels": 1920000,
            "overdraw_pixels": 2503680,
        },
        "bandwidth": {
            "estimated_bandwidth_gb": 8.5,
            "render_target_writes_gb": 3.2,
            "texture_reads_gb": 4.1,
            "depth_writes_gb": 1.2,
        },
        "high_overdraw_regions": [
            {"region": "Transparent Objects", "overdraw": 3.5, "cause": "多层半透明叠加，排序开销大"},
            {"region": "Particle Systems", "overdraw": 4.2, "cause": "粒子密度高，无 Early-Z 优化"},
            {"region": "UI Elements", "overdraw": 2.8, "cause": "UI 层叠较多"},
        ],
        "optimization_potential": {
            "bandwidth_saving_mb": 1200,
            "suggestions": [
                "对透明物体使用 OIT (Order Independent Transparency) 减少 Overdraw",
                "降低粒子系统的填充率，使用 GPU Particle 或减少粒子数量",
                "使用 Early-Z 优化减少不可见像素的着色开销",
                "对远处物体使用低分辨率渲染 (Variable Rate Shading)",
            ],
        },
        "source_file": os.path.basename(rdc_file),
        "mock": True,
    }


def analyze_overdraw(rdc_file: str, get_data: Optional[Callable] = None,
                     use_mock: bool = False) -> dict:
    """Analyze overdraw and bandwidth in an .rdc file.

    Args:
        rdc_file: Path to the .rdc file.
        get_data: Callable(rdc_file) -> dict of pre-extracted data (or None if unavailable).
        use_mock: If True, return mock data when renderdoc is unavailable.

    Returns:
        Dict with overdraw and bandwidth analysis results.
    """
    if not os.path.isfile(rdc_file) and not use_mock:
        raise FileNotFoundError(f"RDC file not found: {rdc_file}")

    if get_data is not None:
        extracted = get_data(rdc_file)
        if extracted is not None:
            od = extracted.get("overdraw_data", {})
            if "error" not in od:
                od["source_file"] = extracted.get("source_file", os.path.basename(rdc_file))
                return od

    if use_mock:
        return _mock_overdraw_data(rdc_file)

    raise RuntimeError("renderdoc 模块不可用且 mock 数据已禁用")


def create_overdraw_analysis_tool(get_data: Callable, config: Config) -> Tool:
    """Create and return the OverdrawAnalysis tool.

    Args:
        get_data: Callable(rdc_file) -> extracted data dict or None.
        config: Application configuration.
    """
    def execute(rdc_file: str) -> dict:
        return analyze_overdraw(
            rdc_file=rdc_file,
            get_data=get_data,
            use_mock=config.use_mock_data,
        )

    return Tool(
        name="analyze_overdraw",
        description=(
            "Analyze pixel overdraw and bandwidth consumption in a RenderDoc .rdc capture file. "
            "Provides overdraw ratio, pixel fill rate, bandwidth estimation, "
            "identifies high-overdraw regions, and suggests optimization opportunities. "
            "Use this to find fill-rate bottlenecks and bandwidth issues."
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

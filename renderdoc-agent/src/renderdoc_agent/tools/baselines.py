"""Performance baseline data and comparison logic."""

from typing import Any

from .registry import Tool

# Platform baselines: { metric: threshold }
BASELINES: dict[str, dict[str, float]] = {
    "mobile_high": {
        "label": "移动端高端",
        "draw_calls": 1500,
        "triangles": 800_000,
        "texture_memory_mb": 1536,  # 1.5GB
        "shader_variants": 100,
        "fragment_instructions": 256,
        "overdraw_ratio": 2.0,
        "frame_time_ms": 16.67,
        "bandwidth_gb": 4.0,
    },
    "mobile_mid": {
        "label": "移动端中端",
        "draw_calls": 800,
        "triangles": 400_000,
        "texture_memory_mb": 800,
        "shader_variants": 60,
        "fragment_instructions": 128,
        "overdraw_ratio": 1.5,
        "frame_time_ms": 33.33,
        "bandwidth_gb": 2.0,
    },
    "pc_high": {
        "label": "PC 高端",
        "draw_calls": 5000,
        "triangles": 3_000_000,
        "texture_memory_mb": 4096,  # 4GB
        "shader_variants": 300,
        "fragment_instructions": 512,
        "overdraw_ratio": 3.0,
        "frame_time_ms": 16.67,
        "bandwidth_gb": 12.0,
    },
    "pc_mid": {
        "label": "PC 中端",
        "draw_calls": 2500,
        "triangles": 1_500_000,
        "texture_memory_mb": 2048,  # 2GB
        "shader_variants": 200,
        "fragment_instructions": 384,
        "overdraw_ratio": 2.5,
        "frame_time_ms": 16.67,
        "bandwidth_gb": 8.0,
    },
}

METRIC_LABELS = {
    "draw_calls": "DrawCall 数量",
    "triangles": "三角形数量",
    "texture_memory_mb": "纹理显存 (MB)",
    "shader_variants": "Shader 变体数",
    "fragment_instructions": "Fragment 指令数",
    "overdraw_ratio": "Overdraw 比例",
    "frame_time_ms": "帧时间 (ms)",
    "bandwidth_gb": "带宽 (GB/帧)",
}


def compare_with_baseline(data: dict, platform: str = "pc_high") -> dict:
    """Compare rendering metrics against a platform baseline.

    Args:
        data: Dict with rendering metrics (draw_calls, triangles, texture_memory_mb).
        platform: One of mobile_high, mobile_mid, pc_high, pc_mid.

    Returns:
        Dict with comparison results including over-budget items and usage ratios.
    """
    baseline = BASELINES.get(platform)
    if baseline is None:
        return {"error": f"Unknown platform: {platform}. Choose from: {list(BASELINES.keys())}"}

    label = baseline["label"]
    results = {
        "platform": label,
        "metrics": [],
        "over_budget": [],
        "status": "PASS",
    }

    for metric, threshold in baseline.items():
        if metric == "label":
            continue
        actual = data.get(metric)
        if actual is None:
            continue
        ratio = actual / threshold if threshold > 0 else 0
        over = actual > threshold
        entry = {
            "name": METRIC_LABELS.get(metric, metric),
            "actual": actual,
            "threshold": threshold,
            "ratio": round(ratio, 2),
            "over_budget": over,
        }
        results["metrics"].append(entry)
        if over:
            results["over_budget"].append(entry)
            results["status"] = "FAIL"

    return results


def create_baseline_tool() -> Tool:
    """Create and return the BaselineCompare tool."""
    def execute(data: dict, platform: str = "pc_high") -> dict:
        return compare_with_baseline(data, platform)

    return Tool(
        name="compare_baseline",
        description=(
            "Compare rendering metrics against platform performance baselines. "
            "Supported platforms: mobile_high, mobile_mid, pc_high, pc_mid. "
            "Pass the metrics dict from analyze_rdc and the target platform."
        ),
        parameters={
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": "Rendering metrics dict with draw_calls, triangles, texture_memory_mb, etc.",
                    "properties": {
                        "draw_calls": {"type": "integer"},
                        "triangles": {"type": "integer"},
                        "texture_memory_mb": {"type": "number"},
                        "shader_variants": {"type": "integer"},
                        "fragment_instructions": {"type": "integer"},
                        "overdraw_ratio": {"type": "number"},
                        "frame_time_ms": {"type": "number"},
                        "bandwidth_gb": {"type": "number"},
                    },
                },
                "platform": {
                    "type": "string",
                    "description": "Target platform: mobile_high, mobile_mid, pc_high, pc_mid",
                    "enum": ["mobile_high", "mobile_mid", "pc_high", "pc_mid"],
                },
            },
            "required": ["data"],
        },
        execute=execute,
    )

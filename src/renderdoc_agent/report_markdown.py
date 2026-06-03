"""Markdown report rendering for deterministic analysis runs."""

from datetime import datetime


def render_markdown_report(
    rdc_file: str,
    platform: str,
    baseline_result: dict,
    extracted: dict,
) -> str:
    analysis_data = extracted.get("drawcall_data", {})
    texture_data = extracted.get("texture_data", {})
    shader_data = extracted.get("shader_data", {})
    gpu_time_data = extracted.get("gpu_time_data", {})
    overdraw_data = extracted.get("overdraw_data", {})
    run_meta = extracted.get("run_meta", {})
    timings = run_meta.get("timings_ms", {})

    lines = []
    lines.append("# RenderDoc Analysis Report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- File: {rdc_file}")
    lines.append(f"- Platform: {baseline_result.get('platform', platform)}")
    lines.append(f"- Status: {baseline_result.get('status', 'unknown')}")
    lines.append(f"- Mode: {run_meta.get('mode', 'quick')}")
    lines.append(f"- Cache Hit: {run_meta.get('cache_hit', False)}")
    lines.append("")

    lines.append("## Timings")
    lines.append(f"- Total: {timings.get('total_ms', 'N/A')} ms")
    lines.append(f"- Base: {timings.get('base_ms', 'N/A')} ms")
    lines.append(f"- GPU: {timings.get('gpu_ms', 'N/A')} ms")
    lines.append(f"- Overdraw: {timings.get('overdraw_ms', 'N/A')} ms")
    lines.append("")

    lines.append("## Baseline")
    for metric in baseline_result.get("metrics", []):
        status = "OVER" if metric.get("over_budget") else "OK"
        lines.append(
            f"- {metric.get('name', '')}: actual={metric.get('actual', '')}, "
            f"threshold={metric.get('threshold', '')}, ratio={metric.get('ratio', '')}, "
            f"status={status}"
        )
    lines.append("")

    lines.append("## Core Metrics")
    lines.append(f"- Draw Calls: {analysis_data.get('draw_calls', 0)}")
    lines.append(f"- Triangles: {analysis_data.get('triangles', 0)}")
    lines.append(f"- Texture Memory MB: {analysis_data.get('texture_memory_mb', 0)}")
    lines.append(f"- Shader Variants: {shader_data.get('total_variants', 'N/A')}")
    lines.append(f"- Frame Time ms: {gpu_time_data.get('frame_time_ms', 'N/A')}")
    lines.append(f"- FPS Estimate: {gpu_time_data.get('fps_estimate', 'N/A')}")
    lines.append(f"- Overdraw Ratio: {overdraw_data.get('overdraw_ratio', 'N/A')}")
    lines.append("")

    lines.append("## Texture")
    lines.append(f"- Total Textures: {texture_data.get('total_textures', 'N/A')}")
    lines.append(f"- Total Memory MB: {texture_data.get('total_memory_mb', 'N/A')}")
    lines.append("")

    lines.append("## GPU")
    lines.append(f"- Bottleneck: {gpu_time_data.get('bottleneck', 'N/A')}")
    lines.append("")

    return "\n".join(lines)

"""Report generation with multiple output formats."""

import csv
import json
import io
from datetime import datetime


def generate_csv_report(
    analysis_data: dict,
    baseline_result: dict,
    texture_data: dict | None = None,
    shader_data: dict | None = None,
    gpu_time_data: dict | None = None,
    overdraw_data: dict | None = None,
) -> str:
    """Generate CSV format report.

    Args:
        analysis_data: Metrics from analyze_rdc.
        baseline_result: Result from compare_baseline.
        texture_data: Optional result from analyze_textures.
        shader_data: Optional result from analyze_shaders.
        gpu_time_data: Optional result from analyze_gpu_time.
        overdraw_data: Optional result from analyze_overdraw.

    Returns:
        CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header section
    writer.writerow(["RenderDoc 性能分析报告"])
    writer.writerow(["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])

    # Platform info
    platform = baseline_result.get("platform", "未知")
    status = baseline_result.get("status", "未知")
    writer.writerow(["目标平台", platform])
    writer.writerow(["整体状态", status])
    writer.writerow([])

    # Metrics table
    writer.writerow(["指标名称", "实际值", "阈值", "比率", "是否超标"])

    metrics = baseline_result.get("metrics", [])
    for m in metrics:
        writer.writerow([
            m.get("name", ""),
            m.get("actual", ""),
            m.get("threshold", ""),
            m.get("ratio", ""),
            "是" if m.get("over_budget") else "否",
        ])

    writer.writerow([])

    # Additional info from analysis
    writer.writerow(["基础信息"])
    writer.writerow(["DrawCall 数量", analysis_data.get("draw_calls", "")])
    writer.writerow(["三角形数量", analysis_data.get("triangles", "")])
    writer.writerow(["顶点数量", analysis_data.get("vertices", "")])
    writer.writerow(["唯一 Shader 数", analysis_data.get("unique_shaders", "")])
    writer.writerow(["唯一纹理数", analysis_data.get("unique_textures", "")])
    writer.writerow(["纹理显存 (MB)", analysis_data.get("texture_memory_mb", "")])

    # Texture analysis section
    if texture_data and not texture_data.get("error"):
        writer.writerow([])
        writer.writerow(["纹理分析"])
        writer.writerow(["纹理总数", texture_data.get("total_textures", "")])
        writer.writerow(["纹理总内存 (MB)", texture_data.get("total_memory_mb", "")])
        mipmap = texture_data.get("mipmap_status", {})
        writer.writerow(["有 Mipmap", mipmap.get("has_mipmap", "")])
        writer.writerow(["无 Mipmap", mipmap.get("no_mipmap", "")])
        uncomp = texture_data.get("uncompressed_textures", [])
        writer.writerow(["未压缩纹理数", len(uncomp)])
        for tex in uncomp:
            writer.writerow(["  未压缩纹理", tex.get("name", ""), tex.get("format", ""), tex.get("size", "")])

    # Shader analysis section
    if shader_data and not shader_data.get("error"):
        writer.writerow([])
        writer.writerow(["Shader 分析"])
        writer.writerow(["Shader 总数", shader_data.get("total_shaders", "")])
        writer.writerow(["变体总数", shader_data.get("total_variants", "")])
        explosion = shader_data.get("variant_explosion", [])
        for s in explosion:
            writer.writerow(["  变体爆炸", s.get("name", ""), "变体数", s.get("variants", "")])
        uniform = shader_data.get("uniform_usage", {})
        writer.writerow(["Uniform 总数", uniform.get("total_uniforms", "")])
        writer.writerow(["未使用 Uniform", uniform.get("unused_uniforms", "")])

    # GPU time analysis section
    if gpu_time_data and not gpu_time_data.get("error"):
        writer.writerow([])
        writer.writerow(["GPU 耗时分析"])
        writer.writerow(["帧时间 (ms)", gpu_time_data.get("frame_time_ms", "")])
        writer.writerow(["估算 FPS", gpu_time_data.get("fps_estimate", "")])
        writer.writerow(["瓶颈 Pass", gpu_time_data.get("bottleneck", "")])
        for p in gpu_time_data.get("pass_breakdown", []):
            writer.writerow(["  Pass", p.get("name", ""), "耗时 (ms)", p.get("time_ms", ""), "占比", f"{p.get('percentage', '')}%"])

    # Overdraw analysis section
    if overdraw_data and not overdraw_data.get("error"):
        writer.writerow([])
        writer.writerow(["Overdraw 分析"])
        writer.writerow(["Overdraw 比例", overdraw_data.get("overdraw_ratio", "")])
        bw = overdraw_data.get("bandwidth", {})
        writer.writerow(["估算带宽 (GB/帧)", bw.get("estimated_bandwidth_gb", "")])
        for region in overdraw_data.get("high_overdraw_regions", []):
            writer.writerow(["  高 Overdraw 区域", region.get("region", ""), "Overdraw", region.get("overdraw", "")])

    if analysis_data.get("mock"):
        writer.writerow([])
        writer.writerow(["注意", "当前使用模拟数据"])

    return output.getvalue()


def generate_json_report(
    analysis_data: dict,
    baseline_result: dict,
    texture_data: dict | None = None,
    shader_data: dict | None = None,
    gpu_time_data: dict | None = None,
    overdraw_data: dict | None = None,
) -> str:
    """Generate JSON format report.

    Args:
        analysis_data: Metrics from analyze_rdc.
        baseline_result: Result from compare_baseline.
        texture_data: Optional result from analyze_textures.
        shader_data: Optional result from analyze_shaders.
        gpu_time_data: Optional result from analyze_gpu_time.
        overdraw_data: Optional result from analyze_overdraw.

    Returns:
        JSON string.
    """
    report = {
        "generated_at": datetime.now().isoformat(),
        "platform": baseline_result.get("platform", "未知"),
        "status": baseline_result.get("status", "未知"),
        "metrics": baseline_result.get("metrics", []),
        "over_budget": baseline_result.get("over_budget", []),
        "analysis": {
            "draw_calls": analysis_data.get("draw_calls"),
            "triangles": analysis_data.get("triangles"),
            "vertices": analysis_data.get("vertices"),
            "unique_shaders": analysis_data.get("unique_shaders"),
            "unique_textures": analysis_data.get("unique_textures"),
            "texture_memory_mb": analysis_data.get("texture_memory_mb"),
        },
        "is_mock_data": analysis_data.get("mock", False),
    }

    if texture_data and not texture_data.get("error"):
        report["texture_analysis"] = texture_data

    if shader_data and not shader_data.get("error"):
        report["shader_analysis"] = shader_data

    if gpu_time_data and not gpu_time_data.get("error"):
        report["gpu_time_analysis"] = gpu_time_data

    if overdraw_data and not overdraw_data.get("error"):
        report["overdraw_analysis"] = overdraw_data

    return json.dumps(report, ensure_ascii=False, indent=2)

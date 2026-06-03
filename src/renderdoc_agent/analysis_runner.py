"""Deterministic single-file analysis pipeline."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .config import Config
from .report_markdown import render_markdown_report
from .tools.analyze_rdc import analyze_rdc
from .tools.baselines import compare_with_baseline
from .tools.gpu_time_analysis import analyze_gpu_time
from .tools.overdraw_analysis import analyze_overdraw
from .tools.shader_analysis import analyze_shaders
from .tools.texture_analysis import analyze_textures


def quick_report(
    rdc_file: str,
    platform: str,
    config: Config,
    mode: str = "quick",
    output_dir: str | None = None,
) -> dict:
    """Generate a deterministic quick/half/full report without LLM."""
    helper = Path(__file__).resolve().parent / "renderdoc_helper.py"
    helper_python = config.helper_python or sys.executable
    helper_env = os.environ.copy()
    helper_env.setdefault("PYTHONIOENCODING", "utf-8")
    out_dir = Path(output_dir or Path.cwd())
    out_dir.mkdir(parents=True, exist_ok=True)
    result_json_path = out_dir / "result.json"
    report_md_path = out_dir / "report.md"

    cmd = [
        helper_python,
        str(helper),
        rdc_file,
        "--renderdoc-path",
        config.renderdoc_module_path,
        "--mode",
        mode,
        "--output",
        str(result_json_path),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=helper_env,
        check=False,
    )
    if proc.returncode != 0:
        if not config.use_mock_data:
            raise RuntimeError(proc.stderr or proc.stdout or "renderdoc helper failed")

        print(f"[警告] renderdoc helper 失败: {proc.stderr or proc.stdout}")
        analysis_data = analyze_rdc(rdc_file=rdc_file, use_mock=True)
        texture_data = analyze_textures(rdc_file=rdc_file, use_mock=True)
        shader_data = analyze_shaders(rdc_file=rdc_file, use_mock=True)
        gpu_time_data = analyze_gpu_time(rdc_file=rdc_file, use_mock=True)
        overdraw_data = analyze_overdraw(rdc_file=rdc_file, use_mock=True)
        extracted = {
            "source_file": rdc_file,
            "drawcall_data": analysis_data,
            "texture_data": texture_data,
            "shader_data": shader_data,
            "gpu_time_data": gpu_time_data,
            "overdraw_data": overdraw_data,
            "run_meta": {
                "mode": mode,
                "cache_hit": False,
                "timings_ms": {},
            },
        }
    else:
        with open(result_json_path, "r", encoding="utf-8") as file:
            extracted = json.load(file)

        drawcall_data = extracted.get("drawcall_data", {})
        analysis_data = {
            "draw_calls": drawcall_data.get("draw_calls", 0),
            "triangles": drawcall_data.get("triangles", 0),
            "vertices": drawcall_data.get("vertices", 0),
            "unique_shaders": drawcall_data.get("unique_shaders", 0),
            "shader_list": drawcall_data.get("shader_list", []),
            "unique_textures": drawcall_data.get("unique_textures", 0),
            "texture_memory_mb": drawcall_data.get("texture_memory_mb", 0),
            "source_file": extracted.get("source_file", ""),
            "mock": False,
        }
        texture_data = extracted.get("texture_data", {})
        texture_data["source_file"] = extracted.get("source_file", "")
        shader_data = extracted.get("shader_data", {})
        shader_data["source_file"] = extracted.get("source_file", "")
        gpu_time_data = extracted.get("gpu_time_data", {})
        gpu_time_data["source_file"] = extracted.get("source_file", "")
        overdraw_data = extracted.get("overdraw_data", {})
        overdraw_data["source_file"] = extracted.get("source_file", "")

    baseline_input = {
        "draw_calls": analysis_data.get("draw_calls"),
        "triangles": analysis_data.get("triangles"),
        "texture_memory_mb": analysis_data.get("texture_memory_mb"),
        "shader_variants": shader_data.get("total_variants"),
        "fragment_instructions": max(
            (item.get("fragment_instructions", 0) for item in shader_data.get("complexity", [])),
            default=0,
        ),
        "overdraw_ratio": overdraw_data.get("overdraw_ratio"),
        "frame_time_ms": gpu_time_data.get("frame_time_ms"),
        "bandwidth_gb": overdraw_data.get("bandwidth", {}).get("estimated_bandwidth_gb"),
    }

    baseline_result = compare_with_baseline(baseline_input, platform)

    report = render_markdown_report(rdc_file, platform, baseline_result, extracted)
    with open(report_md_path, "w", encoding="utf-8") as file:
        file.write(report)

    print(f"结果已保存: {result_json_path}")
    print(f"报告已保存: {report_md_path}")

    run_meta = extracted.get("run_meta", {})
    return {
        "file_name": Path(rdc_file).name,
        "mode": mode,
        "status": baseline_result.get("status", "unknown"),
        "draw_calls": analysis_data.get("draw_calls"),
        "triangles": analysis_data.get("triangles"),
        "texture_memory_mb": analysis_data.get("texture_memory_mb"),
        "frame_time_ms": gpu_time_data.get("frame_time_ms"),
        "fps_estimate": gpu_time_data.get("fps_estimate"),
        "overdraw_ratio": overdraw_data.get("overdraw_ratio"),
        "total_ms": run_meta.get("timings_ms", {}).get("total_ms"),
        "cache_hit": run_meta.get("cache_hit"),
        "error": "",
    }

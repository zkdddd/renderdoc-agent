"""CLI entry point for RenderDoc Agent."""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from .config import Config
from .agent import ReactAgent
from .tools.analyze_rdc import analyze_rdc
from .tools.texture_analysis import analyze_textures
from .tools.shader_analysis import analyze_shaders
from .tools.gpu_time_analysis import analyze_gpu_time
from .tools.overdraw_analysis import analyze_overdraw
from .tools.baselines import compare_with_baseline


PLATFORM_HELP = (
    "目标平台可选:\n"
    "  mobile_high  - 移动端高端 (DC≤1500, Tri≤800K, Tex≤1.5GB)\n"
    "  mobile_mid   - 移动端中端 (DC≤800, Tri≤400K, Tex≤800MB)\n"
    "  pc_high      - PC 高端 (DC≤5000, Tri≤3M, Tex≤4GB)\n"
    "  pc_mid       - PC 中端 (DC≤2500, Tri≤1.5M, Tex≤2GB)"
)


def print_banner():
    print("=" * 56)
    print("  RenderDoc Agent — 游戏渲染性能分析")
    print("  输入 .rdc 文件路径进行分析，输入 quit 退出")
    print("=" * 56)
    print()


def print_help():
    print("命令:")
    print("  <path/to/file.rdc>         分析指定的 .rdc 文件")
    print("  platform <name>            切换目标平台 (mobile_high/mobile_mid/pc_high/pc_mid)")
    print("  reset                      清除对话历史")
    print("  help                       显示此帮助")
    print("  quit / exit                退出")
    print()
    print(PLATFORM_HELP)


def _render_markdown_report(rdc_file: str, platform: str, baseline_result: dict, extracted: dict) -> str:
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
    for m in baseline_result.get("metrics", []):
        status = "OVER" if m.get("over_budget") else "OK"
        lines.append(
            f"- {m.get('name', '')}: actual={m.get('actual', '')}, threshold={m.get('threshold', '')}, ratio={m.get('ratio', '')}, status={status}"
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


def quick_report(rdc_file: str, platform: str, config: Config, mode: str = "quick", output_dir: str = None):
    """Generate a deterministic quick/half/full report without LLM."""
    helper = Path(__file__).resolve().parent / "renderdoc_helper.py"
    helper_python = config.helper_python or sys.executable
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

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        if config.use_mock_data:
            print(f"[警告] renderdoc helper 失败: {proc.stderr or proc.stdout}")
            analysis_data = analyze_rdc(rdc_file=rdc_file, use_mock=True)
            texture_data = analyze_textures(rdc_file=rdc_file, use_mock=True)
            shader_data = analyze_shaders(rdc_file=rdc_file, use_mock=True)
            gpu_time_data = analyze_gpu_time(rdc_file=rdc_file, use_mock=True)
            overdraw_data = analyze_overdraw(rdc_file=rdc_file, use_mock=True)
        else:
            raise RuntimeError(proc.stderr or proc.stdout or "renderdoc helper failed")
    else:
        with open(result_json_path, "r", encoding="utf-8") as f:
            extracted = json.load(f)

        dc = extracted.get("drawcall_data", {})
        analysis_data = {
            "draw_calls": dc.get("draw_calls", 0),
            "triangles": dc.get("triangles", 0),
            "vertices": dc.get("vertices", 0),
            "unique_shaders": dc.get("unique_shaders", 0),
            "shader_list": dc.get("shader_list", []),
            "unique_textures": dc.get("unique_textures", 0),
            "texture_memory_mb": dc.get("texture_memory_mb", 0),
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

    # Build aggregated data for baseline comparison
    baseline_input = {
        "draw_calls": analysis_data.get("draw_calls"),
        "triangles": analysis_data.get("triangles"),
        "texture_memory_mb": analysis_data.get("texture_memory_mb"),
        "shader_variants": shader_data.get("total_variants"),
        "fragment_instructions": max(
            (s.get("fragment_instructions", 0) for s in shader_data.get("complexity", [])),
            default=0,
        ),
        "overdraw_ratio": overdraw_data.get("overdraw_ratio"),
        "frame_time_ms": gpu_time_data.get("frame_time_ms"),
        "bandwidth_gb": overdraw_data.get("bandwidth", {}).get("estimated_bandwidth_gb"),
    }

    # Compare with baseline
    baseline_result = compare_with_baseline(baseline_input, platform)

    report = _render_markdown_report(rdc_file, platform, baseline_result, extracted)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"结果已保存: {result_json_path}")
    print(f"报告已保存: {report_md_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="RenderDoc Agent - 游戏渲染性能分析")
    parser.add_argument("rdc_file", nargs="?", help=".rdc 文件路径（可选，进入交互模式后也可输入）")
    parser.add_argument("--platform", "-p", default="pc_high", help="目标平台 (默认: pc_high)")
    parser.add_argument("--model", "-m", default="qwen2.5:3b", help="Ollama 模型名 (默认: qwen2.5:3b)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama 服务地址")
    parser.add_argument("--mock", action="store_true", default=False, help="使用模拟数据 (默认关闭)")
    parser.add_argument("--no-mock", action="store_true", help="禁用模拟数据（已默认禁用，保留向后兼容）")
    parser.add_argument("--mode", choices=["quick", "half", "full"], default="quick",
                        help="分析档位: quick|half|full (默认: quick)")
    parser.add_argument("--output-dir", "-o", help="输出目录 (默认: 当前目录，固定生成 result.json/report.md)")
    parser.add_argument("--renderdoc-path", help="renderdoc Python 模块路径 (包含 renderdoc.pyd/so)")
    parser.add_argument("--helper-python", help="helper 进程使用的 Python 可执行文件")
    args = parser.parse_args()

    use_mock = args.mock or args.no_mock is False and False
    # --mock explicitly enables mock; otherwise default is False
    # --no_mock is kept for backwards compat but is a no-op now

    config = Config(
        ollama_base_url=args.ollama_url,
        model=args.model,
        default_platform=args.platform,
        use_mock_data=args.mock,
        renderdoc_module_path=args.renderdoc_path or "",
        helper_python=args.helper_python or "",
    )

    # Deterministic report mode (no LLM)
    if args.rdc_file:
        quick_report(args.rdc_file, args.platform, config, args.mode, args.output_dir)
        return

    agent = ReactAgent(config)

    try:
        # Quick analysis mode: rdc_file provided as CLI argument
        if args.rdc_file:
            platform = config.default_platform
            query = f"请分析这个 RenderDoc 抓帧文件: {args.rdc_file}\n目标平台: {platform}"
            print(f"\n正在分析: {args.rdc_file} (平台: {platform})\n")
            result = agent.run(query)

            print(result)
            return

        # Interactive mode
        print_banner()
        print_help()
        print()

        while True:
            try:
                user_input = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("再见！")
                break

            if user_input.lower() == "help":
                print_help()
                continue

            if user_input.lower() == "reset":
                agent.reset()
                print("[对话已重置]\n")
                continue

            if user_input.lower().startswith("platform "):
                new_platform = user_input.split(maxsplit=1)[1].strip()
                config.default_platform = new_platform
                print(f"[目标平台已切换为: {new_platform}]\n")
                continue

            # Check if user pasted an .rdc path directly
            if user_input.endswith(".rdc"):
                platform = config.default_platform
                user_input = f"请分析这个 RenderDoc 抓帧文件: {user_input}\n目标平台: {platform}"

            print()
            result = agent.run(user_input)
            print(f"\n{result}\n")
    finally:
        agent.shutdown()


if __name__ == "__main__":
    main()

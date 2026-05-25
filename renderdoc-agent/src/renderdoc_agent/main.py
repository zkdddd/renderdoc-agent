"""CLI entry point for RenderDoc Agent."""

import json
import subprocess
import sys
from pathlib import Path

from .config import Config
from .agent import ReactAgent
from .tools.analyze_rdc import analyze_rdc
from .tools.texture_analysis import analyze_textures
from .tools.shader_analysis import analyze_shaders
from .tools.gpu_time_analysis import analyze_gpu_time
from .tools.overdraw_analysis import analyze_overdraw
from .tools.baselines import compare_with_baseline
from .report import generate_csv_report, generate_json_report


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


def quick_report(rdc_file: str, platform: str, config: Config, fmt: str = "text", output: str = None):
    """Generate a quick report without LLM."""
    helper = Path(__file__).resolve().parent / "renderdoc_helper.py"
    helper_python = config.helper_python or sys.executable
    cmd = [helper_python, str(helper), rdc_file, "--renderdoc-path", config.renderdoc_module_path]

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
        extracted = None
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                extracted = json.loads(line)
                break
        if extracted is None:
            raise RuntimeError(f"renderdoc helper did not return JSON: {proc.stdout}")

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

    # Generate report
    if fmt == "csv":
        report = generate_csv_report(analysis_data, baseline_result, texture_data, shader_data, gpu_time_data, overdraw_data)
    elif fmt == "json":
        report = generate_json_report(analysis_data, baseline_result, texture_data, shader_data, gpu_time_data, overdraw_data)
    else:
        # Text format - structured report
        lines = []
        lines.append("=" * 60)
        lines.append("RenderDoc 性能分析报告")
        lines.append("=" * 60)
        lines.append(f"文件: {rdc_file}")
        lines.append(f"平台: {baseline_result.get('platform', platform)}")
        lines.append(f"状态: {baseline_result.get('status', '未知')}")
        lines.append("")

        # Baseline metrics
        lines.append("-" * 60)
        lines.append(f"{'指标':<18} {'实际值':<12} {'阈值':<12} {'比率':<8} {'状态':<8}")
        lines.append("-" * 60)
        for m in baseline_result.get("metrics", []):
            name = m.get("name", "")
            actual = m.get("actual", "")
            threshold = m.get("threshold", "")
            ratio = m.get("ratio", "")
            status = "超标" if m.get("over_budget") else "正常"
            lines.append(f"{name:<18} {actual:<12} {threshold:<12} {ratio:<8} {status:<8}")
        lines.append("-" * 60)
        lines.append("")

        # Texture analysis
        lines.append("纹理分析:")
        lines.append(f"  纹理总数: {texture_data.get('total_textures', 'N/A')}")
        lines.append(f"  纹理总内存: {texture_data.get('total_memory_mb', 'N/A')} MB")
        mipmap = texture_data.get("mipmap_status", {})
        lines.append(f"  Mipmap: 有 {mipmap.get('has_mipmap', 'N/A')} / 无 {mipmap.get('no_mipmap', 'N/A')}")
        uncomp = texture_data.get("uncompressed_textures", [])
        if uncomp:
            lines.append(f"  未压缩纹理 ({len(uncomp)}):")
            for tex in uncomp:
                lines.append(f"    - {tex['name']}: {tex['format']} {tex['size']} ({tex['memory_mb']} MB)")
        lines.append("")

        # Shader analysis
        lines.append("Shader 分析:")
        lines.append(f"  Shader 总数: {shader_data.get('total_shaders', 'N/A')}")
        lines.append(f"  变体总数: {shader_data.get('total_variants', 'N/A')}")
        explosion = shader_data.get("variant_explosion", [])
        if explosion:
            lines.append("  变体爆炸:")
            for s in explosion:
                lines.append(f"    - {s['name']}: {s['variants']} 变体 (关键字: {', '.join(s.get('keywords', []))})")
        lines.append("")

        # GPU time analysis
        lines.append("GPU 耗时分析:")
        lines.append(f"  帧时间: {gpu_time_data.get('frame_time_ms', 'N/A')} ms")
        lines.append(f"  估算 FPS: {gpu_time_data.get('fps_estimate', 'N/A')}")
        lines.append(f"  瓶颈 Pass: {gpu_time_data.get('bottleneck', 'N/A')}")
        lines.append("  Pass 耗时:")
        for p in gpu_time_data.get("pass_breakdown", []):
            lines.append(f"    - {p['name']}: {p['time_ms']} ms ({p['percentage']}%)")
        lines.append("")

        # Overdraw analysis
        lines.append("Overdraw 分析:")
        lines.append(f"  Overdraw 比例: {overdraw_data.get('overdraw_ratio', 'N/A')}x")
        bw = overdraw_data.get("bandwidth", {})
        lines.append(f"  估算带宽: {bw.get('estimated_bandwidth_gb', 'N/A')} GB/帧")
        high_regions = overdraw_data.get("high_overdraw_regions", [])
        if high_regions:
            lines.append("  高 Overdraw 区域:")
            for r in high_regions:
                lines.append(f"    - {r['region']}: {r['overdraw']}x ({r['cause']})")
        opt = overdraw_data.get("optimization_potential", {})
        suggestions = opt.get("suggestions", [])
        if suggestions:
            lines.append("  优化建议:")
            for s in suggestions:
                lines.append(f"    - {s}")
        lines.append("")

        if analysis_data.get("mock"):
            lines.append("[注意: 当前使用模拟数据]")

        report = "\n".join(lines)

    # Output
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已保存到: {output}")
    else:
        print(report)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="RenderDoc Agent - 游戏渲染性能分析")
    parser.add_argument("rdc_file", nargs="?", help=".rdc 文件路径（可选，进入交互模式后也可输入）")
    parser.add_argument("--platform", "-p", default="pc_high", help="目标平台 (默认: pc_high)")
    parser.add_argument("--model", "-m", default="qwen2.5:3b", help="Ollama 模型名 (默认: qwen2.5:3b)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama 服务地址")
    parser.add_argument("--mock", action="store_true", default=False, help="使用模拟数据 (默认关闭)")
    parser.add_argument("--no-mock", action="store_true", help="禁用模拟数据（已默认禁用，保留向后兼容）")
    parser.add_argument("--format", "-f", choices=["text", "csv", "json"], default="text",
                        help="输出格式 (默认: text)")
    parser.add_argument("--output", "-o", help="输出文件路径 (不指定则输出到终端)")
    parser.add_argument("--quick", "-q", action="store_true",
                        help="快速报告模式，不使用 LLM 直接输出数据")
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

    # Quick report mode (no LLM)
    if args.rdc_file and args.quick:
        quick_report(args.rdc_file, args.platform, config, args.format, args.output)
        return

    agent = ReactAgent(config)

    try:
        # Quick analysis mode: rdc_file provided as CLI argument
        if args.rdc_file:
            platform = config.default_platform
            query = f"请分析这个 RenderDoc 抓帧文件: {args.rdc_file}\n目标平台: {platform}"
            print(f"\n正在分析: {args.rdc_file} (平台: {platform})\n")
            result = agent.run(query)

            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(result)
                print(f"报告已保存到: {args.output}")
            else:
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

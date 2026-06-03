"""CLI entry point for RenderDoc Agent."""

import sys
from pathlib import Path

from .agent import ReactAgent
from .analysis_runner import quick_report
from .batch_runner import batch_analyze, collect_rdc_files
from .config import Config


PLATFORM_HELP = (
    "目标平台可选:\n"
    "  mobile_high  - 移动端高端 (DC<=1500, Tri<=800K, Tex<=1.5GB)\n"
    "  mobile_mid   - 移动端中端 (DC<=800, Tri<=400K, Tex<=800MB)\n"
    "  pc_high      - PC 高端 (DC<=5000, Tri<=3M, Tex<=4GB)\n"
    "  pc_mid       - PC 中端 (DC<=2500, Tri<=1.5M, Tex<=2GB)"
)


def _configure_stdio_encoding() -> None:
    """Prefer UTF-8 for CLI output so Chinese text stays stable in logs/pipes."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def print_banner() -> None:
    print("=" * 56)
    print("  RenderDoc Agent - 游戏渲染性能分析")
    print("  输入 .rdc 文件路径进行分析，输入 quit 退出")
    print("=" * 56)
    print()


def print_help() -> None:
    print("命令:")
    print("  <path/to/file.rdc>         分析指定的 .rdc 文件")
    print("  platform <name>            切换目标平台 (mobile_high/mobile_mid/pc_high/pc_mid)")
    print("  reset                      清除对话历史")
    print("  help                       显示此帮助")
    print("  quit / exit                退出")
    print()
    print(PLATFORM_HELP)


def build_config(args) -> Config:
    return Config(
        ollama_base_url=args.ollama_url,
        model=args.model,
        default_platform=args.platform,
        use_mock_data=args.mock,
        renderdoc_module_path=args.renderdoc_path or "",
        helper_python=args.helper_python or "",
    )


def run_interactive_mode(config: Config) -> None:
    agent = ReactAgent(config)

    try:
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

            lowered = user_input.lower()
            if lowered in ("quit", "exit", "q"):
                print("再见！")
                break

            if lowered == "help":
                print_help()
                continue

            if lowered == "reset":
                agent.reset()
                print("[对话已重置]\n")
                continue

            if lowered.startswith("platform "):
                new_platform = user_input.split(maxsplit=1)[1].strip()
                config.default_platform = new_platform
                print(f"[目标平台已切换为: {new_platform}]\n")
                continue

            if user_input.endswith(".rdc"):
                platform = config.default_platform
                user_input = f"请分析这个 RenderDoc 抓帧文件: {user_input}\n目标平台: {platform}"

            print()
            result = agent.run(user_input)
            print(f"\n{result}\n")
    finally:
        agent.shutdown()


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="RenderDoc Agent - 游戏渲染性能分析")
    parser.add_argument("rdc_file", nargs="?", help=".rdc 文件路径（可选，进入交互模式后也可输入）")
    parser.add_argument("--platform", "-p", default="pc_high", help="目标平台 (默认: pc_high)")
    parser.add_argument("--model", "-m", default="qwen2.5:3b", help="Ollama 模型名 (默认: qwen2.5:3b)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama 服务地址")
    parser.add_argument("--mock", action="store_true", default=False, help="使用模拟数据 (默认关闭)")
    parser.add_argument("--no-mock", action="store_true", help="禁用模拟数据（已默认禁用，保留向后兼容）")
    parser.add_argument(
        "--mode",
        choices=["quick", "half", "full"],
        default="quick",
        help="分析档位: quick|half|full (默认: quick)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        help="输出目录 (默认: 当前目录，固定生成 result.json/report.md)",
    )
    parser.add_argument("--input-dir", help="批量分析目录（与 rdc_file 二选一）")
    parser.add_argument("--recursive", action="store_true", help="批量模式下递归扫描子目录")
    parser.add_argument("--jobs", type=int, default=1, help="批量并发数 (默认: 1 串行)")
    parser.add_argument("--renderdoc-path", help="renderdoc Python 模块路径 (包含 renderdoc.pyd/so)")
    parser.add_argument("--helper-python", help="helper 进程使用的 Python 可执行文件")
    args = parser.parse_args()

    if bool(args.rdc_file) == bool(args.input_dir):
        parser.error("rdc_file 与 --input-dir 必须二选一")
    if args.jobs < 1:
        parser.error("--jobs 必须 >= 1")

    return args


def main() -> None:
    _configure_stdio_encoding()
    args = parse_args()
    config = build_config(args)

    if args.input_dir:
        files = collect_rdc_files(args.input_dir, args.recursive)
        if not files:
            raise SystemExit(f"未找到 .rdc 文件: {args.input_dir}")
        batch_output_dir = Path(args.output_dir or Path.cwd())
        batch_analyze(files, args.platform, args.mode, config, batch_output_dir, args.jobs)
        return

    if args.rdc_file:
        quick_report(args.rdc_file, args.platform, config, args.mode, args.output_dir)
        return

    run_interactive_mode(config)


if __name__ == "__main__":
    main()

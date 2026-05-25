"""Standalone RenderDoc helper for Python 3.6."""

import argparse
import json
import os
import sys
from pathlib import Path
import importlib.util


def main():
    parser = argparse.ArgumentParser(description="RenderDoc helper")
    parser.add_argument("rdc_file")
    parser.add_argument("--renderdoc-path", default="", help="Directory containing renderdoc.pyd")
    parser.add_argument("--half", action="store_true", help="Run half extraction (include GPU time, skip overdraw)")
    parser.add_argument("--full", action="store_true", help="Run full extraction including slow analyses")
    args = parser.parse_args()

    if args.renderdoc_path and args.renderdoc_path not in sys.path:
        sys.path.insert(0, args.renderdoc_path)

    # Ensure renderdoc.pyd dependent DLLs are discoverable on Windows.
    if args.renderdoc_path:
        dll_dirs = [args.renderdoc_path, str(Path(args.renderdoc_path).resolve().parent)]
        for dll_dir in dll_dirs:
            if os.path.isdir(dll_dir):
                os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")

    import renderdoc as rd

    def progress(msg):
        print(msg, flush=True)

    extract_path = Path(__file__).resolve().parent / "tools" / "renderdoc_extract.py"
    spec = importlib.util.spec_from_file_location("renderdoc_extract", str(extract_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    extract_drawcall_data = module.extract_drawcall_data
    extract_texture_data = module.extract_texture_data
    extract_shader_data = module.extract_shader_data
    extract_gpu_time_data = module.extract_gpu_time_data
    extract_overdraw_data = module.extract_overdraw_data

    if not os.path.isfile(args.rdc_file):
        print(json.dumps({"error": f"RDC file not found: {args.rdc_file}"}, ensure_ascii=False))
        raise SystemExit(1)

    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    progress("[5%] 初始化回放")
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(args.rdc_file, "", None)
    if result != rd.ResultCode.Succeeded:
        print(json.dumps({"error": f"Failed to open file: {result}"}, ensure_ascii=False))
        raise SystemExit(1)

    if not cap.LocalReplaySupport():
        print(json.dumps({"error": "Local replay not supported for this capture"}, ensure_ascii=False))
        raise SystemExit(1)

    result, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if result != rd.ResultCode.Succeeded:
        print(json.dumps({"error": f"Failed to initialize replay: {result}"}, ensure_ascii=False))
        raise SystemExit(1)

    try:
        # Fast mode by default: skip expensive sections for quick real-data validation.
        progress("[35%] 提取 DrawCall")
        drawcall_data = extract_drawcall_data(controller)
        progress("[55%] 提取纹理")
        texture_data = extract_texture_data(controller)
        progress("[70%] 提取 Shader")
        shader_data = extract_shader_data(controller)

        if args.full:
            try:
                progress("[82%] 提取 GPU 耗时")
                gpu_time_data = extract_gpu_time_data(controller)
            except Exception as e:
                gpu_time_data = {"error": str(e)}
            try:
                progress("[92%] 提取 Overdraw")
                overdraw_data = extract_overdraw_data(controller)
            except Exception as e:
                overdraw_data = {"error": str(e)}
        elif args.half:
            try:
                progress("[85%] 提取 GPU 耗时")
                gpu_time_data = extract_gpu_time_data(controller)
            except Exception as e:
                gpu_time_data = {"error": str(e)}
            overdraw_data = {"error": "skipped in half mode"}
        else:
            gpu_time_data = {"error": "skipped in fast mode"}
            overdraw_data = {"error": "skipped in fast mode"}

        output = {
            "source_file": os.path.basename(args.rdc_file),
            "mock": False,
            "drawcall_data": drawcall_data,
            "texture_data": texture_data,
            "shader_data": shader_data,
            "gpu_time_data": gpu_time_data,
            "overdraw_data": overdraw_data,
        }
        progress("[100%] 完成")
        print(json.dumps(output, ensure_ascii=False))
    finally:
        controller.Shutdown()
        cap.Shutdown()
        rd.ShutdownReplay()


if __name__ == "__main__":
    main()

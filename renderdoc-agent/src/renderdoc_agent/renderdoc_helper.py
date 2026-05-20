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
    args = parser.parse_args()

    if args.renderdoc_path and args.renderdoc_path not in sys.path:
        sys.path.insert(0, args.renderdoc_path)

    import renderdoc as rd

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
        output = {
            "source_file": os.path.basename(args.rdc_file),
            "mock": False,
            "drawcall_data": extract_drawcall_data(controller),
            "texture_data": extract_texture_data(controller),
            "shader_data": extract_shader_data(controller),
            "gpu_time_data": extract_gpu_time_data(controller),
            "overdraw_data": extract_overdraw_data(controller),
        }
        print(json.dumps(output, ensure_ascii=False))
    finally:
        controller.Shutdown()
        cap.Shutdown()
        rd.ShutdownReplay()


if __name__ == "__main__":
    main()

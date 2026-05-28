"""Standalone RenderDoc helper for Python 3.6."""

import argparse
import hashlib
import json
import os
import tempfile
import sys
import time
from pathlib import Path
from typing import Optional
import importlib.util


CACHE_VERSION = 2


def _cache_path(rdc_file: str, renderdoc_path: str) -> Path:
    abs_path = os.path.abspath(rdc_file)
    st = os.stat(abs_path)
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
    payload = "|".join([
        abs_path,
        str(st.st_size),
        str(mtime_ns),
        renderdoc_path or "",
        str(CACHE_VERSION),
    ])
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "renderdoc_agent_cache" / f"{digest}.json"


def _load_cache(path: Path) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _build_output(source_file: str, cache: dict, mode: str) -> dict:
    output = {
        "source_file": source_file,
        "mock": False,
        "drawcall_data": cache.get("drawcall_data", {}),
        "texture_data": cache.get("texture_data", {}),
        "shader_data": cache.get("shader_data", {}),
    }

    if mode == "quick":
        output["gpu_time_data"] = {"error": "skipped in fast mode"}
        output["overdraw_data"] = {"error": "skipped in fast mode"}
    elif mode == "half":
        output["gpu_time_data"] = cache.get("gpu_time_data", {"error": "skipped in half mode"})
        output["overdraw_data"] = {"error": "skipped in half mode"}
    else:
        output["gpu_time_data"] = cache.get("gpu_time_data", {})
        output["overdraw_data"] = cache.get("overdraw_data", {})

    return output


def _round_ms(seconds: float) -> float:
    return round(seconds * 1000.0, 2)


def main():
    parser = argparse.ArgumentParser(description="RenderDoc helper")
    parser.add_argument("rdc_file")
    parser.add_argument("--renderdoc-path", default="", help="Directory containing renderdoc.pyd")
    parser.add_argument("--overdraw-samples", type=int, default=80, help="PixelHistory sample count for overdraw")
    parser.add_argument("--output", default="", help="Write final JSON to a file instead of stdout")
    parser.add_argument("--mode", choices=["quick", "half", "full"], default="quick", help="Extraction level")
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
    overdraw_sample_count = max(10, int(args.overdraw_samples))

    if not os.path.isfile(args.rdc_file):
        print(json.dumps({"error": f"RDC file not found: {args.rdc_file}"}, ensure_ascii=False))
        raise SystemExit(1)

    cache_file = _cache_path(args.rdc_file, args.renderdoc_path)
    cached = _load_cache(cache_file) or {}

    mode = args.mode
    if args.full:
        mode = "full"
    elif args.half:
        mode = "half"
    base_keys = ("drawcall_data", "texture_data", "shader_data")
    need_base = any(k not in cached for k in base_keys)
    need_gpu = mode in ("half", "full") and "gpu_time_data" not in cached
    need_overdraw = mode == "full" and "overdraw_data" not in cached
    need_live = need_base or need_gpu or need_overdraw

    total_start = time.perf_counter()
    timings = {}
    cache_hit = not need_live

    if need_live:
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
    else:
        progress("[5%] 命中缓存")
        cap = None
        controller = None

    try:
        if need_base:
            # First pass: collect base data once and cache it.
            base_start = time.perf_counter()
            progress("[35%] 提取 DrawCall")
            drawcall_data = extract_drawcall_data(controller)
            progress("[55%] 提取纹理")
            texture_data = extract_texture_data(controller)
            progress("[70%] 提取 Shader")
            shader_data = extract_shader_data(controller)
            timings["base_ms"] = _round_ms(time.perf_counter() - base_start)

            cached.update({
                "drawcall_data": drawcall_data,
                "texture_data": texture_data,
                "shader_data": shader_data,
            })

            _save_cache(cache_file, cached)
        else:
            drawcall_data = cached.get("drawcall_data", {})
            texture_data = cached.get("texture_data", {})
            shader_data = cached.get("shader_data", {})

        if need_gpu and controller is None:
            raise RuntimeError("GPU time requires live replay, but cache had no gpu_time_data")
        if need_gpu:
            gpu_start = time.perf_counter()
            try:
                progress("[85%] 提取 GPU 耗时")
                cached["gpu_time_data"] = extract_gpu_time_data(controller)
            except Exception as e:
                cached["gpu_time_data"] = {"error": str(e)}
            timings["gpu_ms"] = _round_ms(time.perf_counter() - gpu_start)
            _save_cache(cache_file, cached)

        if need_overdraw and controller is None:
            raise RuntimeError("Overdraw requires live replay, but cache had no overdraw_data")
        if need_overdraw:
            overdraw_start = time.perf_counter()
            try:
                progress("[92%] 提取 Overdraw")
                cached["overdraw_data"] = extract_overdraw_data(controller, sample_count=overdraw_sample_count)
            except Exception as e:
                cached["overdraw_data"] = {"error": str(e)}
            timings["overdraw_ms"] = _round_ms(time.perf_counter() - overdraw_start)
            _save_cache(cache_file, cached)

        output = _build_output(os.path.basename(args.rdc_file), cached, mode)
        timings["total_ms"] = _round_ms(time.perf_counter() - total_start)
        output["run_meta"] = {
            "mode": mode,
            "cache_hit": cache_hit,
            "timings_ms": timings,
            "overdraw_samples": overdraw_sample_count,
        }
        progress("[100%] 完成")
        final_json = json.dumps(output, ensure_ascii=False)
        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(final_json)
        else:
            print(final_json)
    finally:
        if controller is not None:
            controller.Shutdown()
        if cap is not None:
            cap.Shutdown()
        if cached is None:
            rd.ShutdownReplay()


if __name__ == "__main__":
    main()

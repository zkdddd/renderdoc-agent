"""RenderDoc replay extraction using the renderdoc Python API."""

import os
import sys
from typing import Optional, Tuple


def init_renderdoc(module_path: str = "") -> bool:
    """Try to import renderdoc module. Returns True if available."""
    if module_path and module_path not in sys.path:
        sys.path.insert(0, module_path)
    try:
        import renderdoc  # noqa: F401
        return True
    except ImportError:
        return False


def open_capture(rdc_file: str) -> Tuple[object, object]:
    """Open an .rdc file and return (CaptureFile, ReplayController)."""
    import renderdoc as rd

    if not os.path.isfile(rdc_file):
        raise FileNotFoundError(f"RDC file not found: {rdc_file}")

    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(rdc_file, "", None)
    if result != rd.ResultCode.Succeeded:
        cap.Shutdown()
        rd.ShutdownReplay()
        raise RuntimeError(f"无法打开文件: {result}")

    if not cap.LocalReplaySupport():
        cap.Shutdown()
        rd.ShutdownReplay()
        raise RuntimeError("此捕获文件不支持本地回放")

    result, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if result != rd.ResultCode.Succeeded:
        cap.Shutdown()
        rd.ShutdownReplay()
        raise RuntimeError(f"无法初始化回放: {result}")

    return cap, controller


def close_capture(cap, controller) -> None:
    """Shutdown controller and capture file."""
    if controller:
        controller.Shutdown()
    if cap:
        cap.Shutdown()


def extract_via_renderdoc_api(rdc_file: str, module_path: str = "") -> dict:
    """Extract all rendering data from an .rdc file via renderdoc API."""
    if not init_renderdoc(module_path):
        raise RuntimeError("renderdoc 模块不可用")

    import renderdoc as rd

    cap = None
    controller = None
    try:
        cap, controller = open_capture(rdc_file)

        from .renderdoc_extract import (
            extract_drawcall_data,
            extract_texture_data,
            extract_shader_data,
            extract_gpu_time_data,
            extract_overdraw_data,
        )

        output = {
            "source_file": os.path.basename(rdc_file),
            "mock": False,
        }

        try:
            output["drawcall_data"] = extract_drawcall_data(controller)
        except Exception as e:
            output["drawcall_data"] = {"error": str(e)}

        try:
            output["texture_data"] = extract_texture_data(controller)
        except Exception as e:
            output["texture_data"] = {"error": str(e)}

        try:
            output["shader_data"] = extract_shader_data(controller)
        except Exception as e:
            output["shader_data"] = {"error": str(e)}

        try:
            output["gpu_time_data"] = extract_gpu_time_data(controller)
        except Exception as e:
            output["gpu_time_data"] = {"error": str(e)}

        try:
            output["overdraw_data"] = extract_overdraw_data(controller)
        except Exception as e:
            output["overdraw_data"] = {"error": str(e)}

        return output
    finally:
        if controller is not None or cap is not None:
            close_capture(cap, controller)
        rd.ShutdownReplay()

"""RenderDoc replay controller lifecycle management."""

import sys
import os
import json
import subprocess
import tempfile
import time
from typing import Optional, Tuple


# Default path to qrenderdoc.exe
DEFAULT_QRENDERDOC_PATH = r"D:\kd\Tool\renderdoc1.44\qrenderdoc.exe"

# Path to the extraction script template (relative to this file)
_EXTRACT_SCRIPT = os.path.join(os.path.dirname(__file__), "renderdoc_extract.py")


def init_renderdoc(module_path: str = "") -> bool:
    """Try to import renderdoc module. Returns True if available.

    Args:
        module_path: Optional path to directory containing renderdoc.pyd / renderdoc.so.

    Returns:
        True if renderdoc module is available.
    """
    if module_path and module_path not in sys.path:
        sys.path.insert(0, module_path)
    try:
        import renderdoc  # noqa: F401
        return True
    except ImportError:
        return False


def open_capture(rdc_file: str) -> Tuple[object, object]:
    """Open an .rdc file and return (CaptureFile, ReplayController).

    Args:
        rdc_file: Path to the .rdc capture file.

    Returns:
        Tuple of (cap, controller) where cap is the CaptureFile handle
        and controller is the ReplayController.

    Raises:
        FileNotFoundError: If rdc_file does not exist.
        RuntimeError: If the capture cannot be opened or replayed.
    """
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
    """Shutdown controller and capture file.

    Args:
        cap: The CaptureFile handle (or None).
        controller: The ReplayController (or None).
    """
    if controller:
        controller.Shutdown()
    if cap:
        cap.Shutdown()


def find_qrenderdoc(qrenderdoc_path: str = "") -> str:
    """Find qrenderdoc.exe path.

    Args:
        qrenderdoc_path: Explicit path to qrenderdoc.exe. If empty, uses default.

    Returns:
        Absolute path to qrenderdoc.exe.

    Raises:
        FileNotFoundError: If qrenderdoc.exe cannot be found.
    """
    path = qrenderdoc_path or DEFAULT_QRENDERDOC_PATH
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"qrenderdoc.exe 未找到: {path}\n"
            f"请通过 --qrenderdoc-path 参数指定 qrenderdoc.exe 的路径，\n"
            f"或确认 RenderDoc 已安装在 {DEFAULT_QRENDERDOC_PATH}"
        )
    return os.path.abspath(path)


def _generate_extract_script(rdc_file: str, output_file: str) -> str:
    """Generate a Python extraction script with hardcoded paths.

    RenderDoc's embedded Python does not have sys.argv available,
    so we generate a script with the paths baked in.

    Args:
        rdc_file: Absolute path to the .rdc file.
        output_file: Absolute path for the JSON output file.

    Returns:
        Path to the generated temporary script file.
    """
    # Read the template script
    with open(_EXTRACT_SCRIPT, "r", encoding="utf-8") as f:
        template = f.read()

    # Replace the main() function's argument parsing with hardcoded values
    # We inject the paths right after the function definition
    injected = '''
def main():
    rdc_file = r"{}"
    output_file = r"{}"
'''.format(rdc_file, output_file)

    # Replace the original main() function's argument parsing section
    old_main_start = '''def main():
    if len(sys.argv) < 3:'''
    old_main_end = '''    rdc_file = sys.argv[1]
    output_file = sys.argv[2]'''

    # Find and replace the argument parsing block
    start_idx = template.find(old_main_start)
    if start_idx == -1:
        raise RuntimeError("Cannot find main() function in extract script template")

    end_marker = '    output_file = sys.argv[2]\n'
    end_idx = template.find(end_marker, start_idx)
    if end_idx == -1:
        raise RuntimeError("Cannot find argument parsing in extract script template")
    end_idx += len(end_marker)

    new_script = template[:start_idx] + injected + template[end_idx:]

    # Write to a temp file
    fd, script_path = tempfile.mkstemp(suffix=".py", prefix="renderdoc_extract_")
    os.close(fd)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(new_script)

    return script_path


def extract_via_qrenderdoc(rdc_file: str, qrenderdoc_path: str = "",
                           timeout: int = 600) -> dict:
    """Extract all rendering data from an .rdc file via qrenderdoc subprocess.

    Launches qrenderdoc.exe with a generated extraction script. The script
    writes JSON to a temp file and calls os._exit(0) to terminate before the
    Qt UI opens. This function waits for the output file to appear, then
    kills the process.

    Args:
        rdc_file: Path to the .rdc capture file.
        qrenderdoc_path: Explicit path to qrenderdoc.exe.
        timeout: Maximum seconds to wait for extraction.

    Returns:
        Dict with all extracted rendering data.

    Raises:
        FileNotFoundError: If rdc_file or qrenderdoc.exe not found.
        RuntimeError: If extraction fails or times out.
    """
    if not os.path.isfile(rdc_file):
        raise FileNotFoundError(f"RDC file not found: {rdc_file}")

    qrenderdoc = find_qrenderdoc(qrenderdoc_path)

    if not os.path.isfile(_EXTRACT_SCRIPT):
        raise FileNotFoundError(f"提取脚本未找到: {_EXTRACT_SCRIPT}")

    abs_rdc = os.path.abspath(rdc_file)

    # Create temp files for output and script
    fd, output_file = tempfile.mkstemp(suffix=".json", prefix="renderdoc_extract_")
    os.close(fd)

    script_path = None
    process = None

    try:
        # Generate script with hardcoded paths
        script_path = _generate_extract_script(abs_rdc, output_file)

        cmd = [qrenderdoc, "--python", script_path, abs_rdc]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for the output file to appear and contain valid JSON
        start_time = time.time()
        data = None

        while time.time() - start_time < timeout:
            # Check if process exited early (error case)
            retcode = process.poll()
            if retcode is not None and data is None:
                if os.path.isfile(output_file) and os.path.getsize(output_file) > 0:
                    break
                stderr = ""
                stdout = ""
                try:
                    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
                except Exception:
                    pass
                try:
                    stdout = process.stdout.read().decode("utf-8", errors="replace") if process.stdout else ""
                except Exception:
                    pass
                raise RuntimeError(
                    f"qrenderdoc 提前退出 (code {retcode})\n"
                    f"stderr: {stderr[:500]}\n"
                    f"stdout: {stdout[:500]}"
                )

            # Check if output file has been written
            if os.path.isfile(output_file):
                try:
                    file_size = os.path.getsize(output_file)
                    if file_size > 0:
                        # Try to read and parse JSON
                        with open(output_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        break
                except (json.JSONDecodeError, OSError):
                    # File still being written or invalid, wait
                    time.sleep(1.0)
                    continue

            time.sleep(1.0)

        if data is None:
            if process and process.poll() is None:
                process.kill()
            raise RuntimeError(
                f"qrenderdoc 提取超时（超过 {timeout} 秒），"
                f".rdc 文件可能过大或 GPU 驱动无响应"
            )

        # Check if the extracted data contains an error
        if "error" in data and len(data) == 1:
            raise RuntimeError(f"RenderDoc 提取失败: {data['error']}")

        return data

    finally:
        # Kill the process if still running
        if process and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=5)
            except Exception:
                pass

        # Clean up temp files
        for path in [output_file, script_path]:
            try:
                if path and os.path.isfile(path):
                    os.unlink(path)
            except OSError:
                pass

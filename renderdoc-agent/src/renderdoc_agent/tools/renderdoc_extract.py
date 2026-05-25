"""
RenderDoc data extraction script.

This script is designed to run INSIDE RenderDoc's embedded Python environment
via: qrenderdoc.exe --python renderdoc_extract.py capture.rdc output.json

It imports the built-in `renderdoc` module (only available inside qrenderdoc),
opens the .rdc file, extracts all analysis metrics, writes JSON to the output
file, and calls os._exit(0) to terminate before the Qt UI opens.

Compatible with Python 3.6 (RenderDoc's embedded Python version).
"""

import sys
import os
import json


def extract_drawcall_data(controller):
    """Extract draw call, triangle, vertex, shader, and texture metrics."""
    import renderdoc as rd

    draw_calls = 0
    total_triangles = 0
    total_vertices = 0
    shaders_seen = set()

    def walk(action):
        nonlocal draw_calls, total_triangles, total_vertices
        if action.flags & rd.ActionFlags.Drawcall:
            draw_calls += 1
            total_triangles += action.numIndices // 3
            total_vertices += getattr(action, "numVertices", 0)
            controller.SetFrameEvent(action.eventId, True)
            state = controller.GetPipelineState()
            for stage in [rd.ShaderStage.Vertex, rd.ShaderStage.Fragment]:
                refl = state.GetShaderReflection(stage)
                if refl:
                    shaders_seen.add(refl.resourceId)
        for child in action.children:
            walk(child)

    for action in controller.GetRootActions():
        walk(action)

    textures = controller.GetTextures()
    texture_memory_bytes = sum(t.byteSize for t in textures)

    return {
        "draw_calls": draw_calls,
        "triangles": total_triangles,
        "vertices": total_vertices,
        "unique_shaders": len(shaders_seen),
        "shader_list": sorted(str(s) for s in shaders_seen),
        "unique_textures": len(textures),
        "texture_memory_mb": round(texture_memory_bytes / (1024.0 * 1024.0), 1),
    }


def extract_texture_data(controller):
    """Extract texture format, size, mipmap, and compression info."""
    import renderdoc as rd

    textures = controller.GetTextures()

    format_dist = {}
    size_dist = {}
    has_mip = 0
    no_mip = 0
    uncompressed = []
    all_textures = []

    for tex in textures:
        fmt_name = tex.format.Name()
        format_dist[fmt_name] = format_dist.get(fmt_name, 0) + 1

        size_key = "{}x{}".format(tex.width, tex.height)
        size_dist[size_key] = size_dist.get(size_key, 0) + 1

        if tex.mips > 1:
            has_mip += 1
        else:
            no_mip += 1

        mem_mb = round(tex.byteSize / (1024.0 * 1024.0), 1)
        is_compressed = tex.format.BlockFormat()
        if not is_compressed and tex.width >= 256:
            uncompressed.append({
                "name": str(tex.resourceId),
                "format": fmt_name,
                "size": size_key,
                "memory_mb": mem_mb,
            })

        all_textures.append({
            "name": str(tex.resourceId),
            "format": fmt_name,
            "size": size_key,
            "memory_mb": mem_mb,
        })

    all_textures.sort(key=lambda t: t["memory_mb"], reverse=True)

    return {
        "total_textures": len(textures),
        "total_memory_mb": round(sum(t.byteSize for t in textures) / (1024.0 * 1024.0), 1),
        "format_distribution": format_dist,
        "size_distribution": size_dist,
        "mipmap_status": {
            "has_mipmap": has_mip,
            "no_mipmap": no_mip,
            "partial_mipmap": 0,
        },
        "uncompressed_textures": uncompressed[:20],
        "largest_textures": all_textures[:10],
    }


def extract_shader_data(controller):
    """Extract shader metadata from pipeline state at each draw call."""
    import renderdoc as rd

    shader_map = {}

    def walk(action):
        if action.flags & rd.ActionFlags.Drawcall:
            controller.SetFrameEvent(action.eventId, True)
            state = controller.GetPipelineState()

            for stage in [rd.ShaderStage.Vertex, rd.ShaderStage.Fragment]:
                refl = state.GetShaderReflection(stage)
                if refl and refl.resourceId not in shader_map:
                    tex_samples = sum(1 for r in refl.readOnlyResources if r.isTexture)

                    shader_map[refl.resourceId] = {
                        "entry": state.GetShaderEntryPoint(stage),
                        "stage": stage.name,
                        "cbuffers": len(refl.constantBlocks),
                        "textures": tex_samples,
                        "rw_resources": len(refl.readWriteResources),
                        "input_count": len(refl.inputSignature),
                        "output_count": len(refl.outputSignature),
                    }

        for child in action.children:
            walk(child)

    for action in controller.GetRootActions():
        walk(action)

    complexity_list = []
    total_uniforms = 0
    for sid, info in shader_map.items():
        total_uniforms += info["cbuffers"]
        complexity_list.append({
            "name": info["entry"],
            "stage": info["stage"],
            "constant_blocks": info["cbuffers"],
            "texture_bindings": info["textures"],
            "rw_bindings": info["rw_resources"],
        })

    return {
        "total_shaders": len(shader_map),
        "total_variants": len(shader_map),
        "complexity": complexity_list,
        "uniform_usage": {
            "total_uniforms": total_uniforms,
            "unused_uniforms": 0,
            "per_shader_uniforms": [],
        },
    }


def extract_gpu_time_data(controller):
    """Extract GPU timing per draw call and per pass using performance counters."""
    import renderdoc as rd

    counters = controller.EnumerateCounters()
    if rd.GPUCounter.EventGPUDuration not in counters:
        return {"error": "GPU does not support EventGPUDuration counter"}

    results = controller.FetchCounters([rd.GPUCounter.EventGPUDuration])

    action_map = {}

    def walk(action):
        action_map[action.eventId] = action
        for child in action.children:
            walk(child)

    for action in controller.GetRootActions():
        walk(action)

    # Per-drawcall timing
    draw_times = []
    for r in results:
        action = action_map.get(r.eventId)
        if action and action.flags & rd.ActionFlags.Drawcall:
            time_ms = r.value.d * 1000.0
            draw_times.append({
                "event_id": r.eventId,
                "name": action.GetName(controller.GetStructuredFile()),
                "time_ms": round(time_ms, 3),
                "triangles": action.numIndices // 3 if action.numIndices else 0,
            })

    frame_time_ms = sum(d["time_ms"] for d in draw_times)

    # Pass breakdown via marker boundaries
    pass_groups = {}
    marker_stack = []

    def walk_pass(action):
        if action.flags & rd.ActionFlags.PushMarker:
            marker_stack.append((action.eventId, action.GetName(controller.GetStructuredFile())))
        elif action.flags & rd.ActionFlags.PopMarker:
            if marker_stack:
                marker_stack.pop()

        if action.flags & rd.ActionFlags.Drawcall:
            pass_name = marker_stack[-1][1] if marker_stack else "Unknown"
            if pass_name not in pass_groups:
                pass_groups[pass_name] = {"time_ms": 0.0, "draw_calls": 0}
            for r in results:
                if r.eventId == action.eventId:
                    pass_groups[pass_name]["time_ms"] += r.value.d * 1000.0
                    pass_groups[pass_name]["draw_calls"] += 1
                    break

        for child in action.children:
            walk_pass(child)

    for action in controller.GetRootActions():
        walk_pass(action)

    total_time = sum(g["time_ms"] for g in pass_groups.values())
    pass_breakdown = []
    for name, data in sorted(pass_groups.items(), key=lambda x: x[1]["time_ms"], reverse=True):
        pct = round((data["time_ms"] / total_time * 100), 1) if total_time > 0 else 0
        pass_breakdown.append({
            "name": name,
            "time_ms": round(data["time_ms"], 2),
            "percentage": pct,
            "draw_calls": data["draw_calls"],
        })

    draw_times.sort(key=lambda d: d["time_ms"], reverse=True)

    return {
        "total_gpu_time_ms": round(frame_time_ms, 2),
        "frame_time_ms": round(frame_time_ms, 2),
        "fps_estimate": round(1000.0 / frame_time_ms, 1) if frame_time_ms > 0 else 0,
        "pass_breakdown": pass_breakdown,
        "top_expensive_drawcalls": draw_times[:10],
        "bottleneck": pass_breakdown[0]["name"] if pass_breakdown else "Unknown",
        "budget_status": {
            "60fps": {
                "budget_ms": 16.67,
                "status": "PASS" if frame_time_ms <= 16.67 else "FAIL",
                "margin_ms": round(16.67 - frame_time_ms, 2),
            },
            "30fps": {
                "budget_ms": 33.33,
                "status": "PASS" if frame_time_ms <= 33.33 else "FAIL",
                "margin_ms": round(33.33 - frame_time_ms, 2),
            },
        },
    }


def extract_overdraw_data(controller, sample_count=200):
    """Estimate overdraw via pixel history sampling."""
    import renderdoc as rd
    import random

    # Find the last draw call
    def find_last_draw(actions):
        last = None
        for action in actions:
            if action.flags & rd.ActionFlags.Drawcall:
                last = action
            child = find_last_draw(action.children)
            if child is not None:
                last = child
        return last

    root_actions = controller.GetRootActions()
    last_draw = find_last_draw(root_actions)
    if not last_draw:
        return {"error": "No draw calls found"}

    controller.SetFrameEvent(last_draw.eventId, True)
    state = controller.GetPipelineState()

    outputs = state.GetOutputTargets()
    color_target = None
    for o in outputs:
        if o.resourceId != rd.ResourceId.Null():
            color_target = o.resourceId
            break

    if color_target is None:
        return {"error": "No color target found"}

    textures = controller.GetTextures()
    target_tex = None
    for t in textures:
        if t.resourceId == color_target:
            target_tex = t
            break

    if not target_tex:
        return {"error": "Color target texture info not found"}

    width, height = target_tex.width, target_tex.height
    screen_pixels = width * height

    sub = rd.Subresource(0, 0, 0)
    total_fragments = 0
    actual_samples = 0

    for _ in range(sample_count):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        try:
            history = controller.PixelHistory(color_target, x, y, sub, rd.CompType.Float)
            passing = sum(1 for mod in history if mod.Passed())
            total_fragments += passing
            actual_samples += 1
        except Exception:
            pass

    avg_overdraw = total_fragments / actual_samples if actual_samples > 0 else 0

    return {
        "overdraw_ratio": round(avg_overdraw, 2),
        "pixel_fill_rate": {
            "total_pixels_written": int(screen_pixels * avg_overdraw),
            "screen_pixels": screen_pixels,
            "overdraw_pixels": int(screen_pixels * (avg_overdraw - 1)),
        },
        "sample_count": actual_samples,
    }


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: qrenderdoc.exe --python renderdoc_extract.py <capture.rdc> <output.json>"}))
        sys.exit(1)

    rdc_file = sys.argv[1]
    output_file = sys.argv[2]

    if not os.path.isfile(rdc_file):
        error = {"error": "RDC file not found: {}".format(rdc_file)}
        with open(output_file, "w") as f:
            json.dump(error, f, ensure_ascii=False)
        os._exit(1)

    import renderdoc as rd

    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(rdc_file, "", None)
    if result != rd.ResultCode.Succeeded:
        cap.Shutdown()
        rd.ShutdownReplay()
        error = {"error": "Failed to open file: {}".format(str(result))}
        with open(output_file, "w") as f:
            json.dump(error, f, ensure_ascii=False)
        os._exit(1)

    if not cap.LocalReplaySupport():
        cap.Shutdown()
        rd.ShutdownReplay()
        error = {"error": "Local replay not supported for this capture"}
        with open(output_file, "w") as f:
            json.dump(error, f, ensure_ascii=False)
        os._exit(1)

    result, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if result != rd.ResultCode.Succeeded:
        cap.Shutdown()
        rd.ShutdownReplay()
        error = {"error": "Failed to initialize replay: {}".format(str(result))}
        with open(output_file, "w") as f:
            json.dump(error, f, ensure_ascii=False)
        os._exit(1)

    try:
        output = {
            "source_file": os.path.basename(rdc_file),
            "mock": False,
        }

        # Extract all data sections
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

        # Write JSON to output file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False)

    finally:
        controller.Shutdown()
        cap.Shutdown()
        rd.ShutdownReplay()

    # Force exit before Qt UI opens
    os._exit(0)


if __name__ == "__main__":
    main()

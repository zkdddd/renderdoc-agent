"""Tests for all analysis tools and baselines."""

import json
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from renderdoc_agent.tools.analyze_rdc import analyze_rdc, _mock_rdc_data
from renderdoc_agent.tools.texture_analysis import analyze_textures
from renderdoc_agent.tools.shader_analysis import analyze_shaders
from renderdoc_agent.tools.gpu_time_analysis import analyze_gpu_time
from renderdoc_agent.tools.overdraw_analysis import analyze_overdraw
from renderdoc_agent.tools.baselines import compare_with_baseline, BASELINES


class TestAnalyzeRDC:
    """Tests for RDC analysis."""

    def test_mock_data_returns_all_fields(self):
        result = _mock_rdc_data("test.rdc")
        assert "draw_calls" in result
        assert "triangles" in result
        assert "texture_memory_mb" in result
        assert "shader_list" in result
        assert result["mock"] is True

    def test_analyze_rdc_mock_mode(self):
        result = analyze_rdc("nonexistent.rdc", use_mock=True)
        assert result["draw_calls"] > 0
        assert result["source_file"] == "nonexistent.rdc"

    def test_analyze_rdc_no_data_falls_back_to_mock(self):
        """When get_data returns None, should fall back to mock data."""
        result = analyze_rdc("nonexistent.rdc", get_data=lambda f: None, use_mock=True)
        assert result["draw_calls"] > 0
        assert result["mock"] is True

    def test_analyze_rdc_no_mock_no_data_raises(self):
        """When mock is disabled and file doesn't exist, should raise."""
        try:
            analyze_rdc("nonexistent.rdc", get_data=lambda f: None, use_mock=False)
            assert False, "Should have raised"
        except (RuntimeError, FileNotFoundError):
            pass  # Either error is acceptable


class TestTextureAnalysis:
    """Tests for texture analysis."""

    def test_mock_texture_data_fields(self):
        result = analyze_textures("test.rdc", use_mock=True)
        assert "total_textures" in result
        assert "total_memory_mb" in result
        assert "format_distribution" in result
        assert "size_distribution" in result
        assert "mipmap_status" in result
        assert "uncompressed_textures" in result
        assert "largest_textures" in result
        assert result["mock"] is True

    def test_mock_texture_data_values(self):
        result = analyze_textures("test.rdc", use_mock=True)
        assert result["total_textures"] > 0
        assert result["total_memory_mb"] > 0
        assert len(result["uncompressed_textures"]) > 0
        assert len(result["largest_textures"]) > 0

    def test_texture_source_file(self):
        result = analyze_textures("my_frame.rdc", use_mock=True)
        assert result["source_file"] == "my_frame.rdc"

    def test_format_distribution_sum(self):
        result = analyze_textures("test.rdc", use_mock=True)
        total = sum(result["format_distribution"].values())
        assert total == result["total_textures"]


class TestShaderAnalysis:
    """Tests for shader analysis."""

    def test_mock_shader_data_fields(self):
        result = analyze_shaders("test.rdc", use_mock=True)
        assert "total_shaders" in result
        assert "total_variants" in result
        assert "complexity" in result
        assert "uniform_usage" in result
        assert result["mock"] is True

    def test_mock_shader_data_values(self):
        result = analyze_shaders("test.rdc", use_mock=True)
        assert result["total_shaders"] > 0
        assert result["total_variants"] > 0
        assert len(result["complexity"]) > 0

    def test_shader_source_file(self):
        result = analyze_shaders("my_frame.rdc", use_mock=True)
        assert result["source_file"] == "my_frame.rdc"

    def test_uniform_usage_fields(self):
        result = analyze_shaders("test.rdc", use_mock=True)
        uniform = result["uniform_usage"]
        assert "total_uniforms" in uniform
        assert "unused_uniforms" in uniform
        assert "per_shader_uniforms" in uniform


class TestGPUTimeAnalysis:
    """Tests for GPU time analysis."""

    def test_mock_gpu_time_fields(self):
        result = analyze_gpu_time("test.rdc", use_mock=True)
        assert "total_gpu_time_ms" in result
        assert "frame_time_ms" in result
        assert "fps_estimate" in result
        assert "pass_breakdown" in result
        assert "top_expensive_drawcalls" in result
        assert "bottleneck" in result
        assert "budget_status" in result
        assert result["mock"] is True

    def test_pass_breakdown_percentages(self):
        result = analyze_gpu_time("test.rdc", use_mock=True)
        total_pct = sum(p["percentage"] for p in result["pass_breakdown"])
        assert abs(total_pct - 100.0) < 1.0  # approximately 100%

    def test_budget_status_fields(self):
        result = analyze_gpu_time("test.rdc", use_mock=True)
        budget = result["budget_status"]
        assert "60fps" in budget
        assert "30fps" in budget
        assert "budget_ms" in budget["60fps"]
        assert "status" in budget["60fps"]

    def test_gpu_time_source_file(self):
        result = analyze_gpu_time("my_frame.rdc", use_mock=True)
        assert result["source_file"] == "my_frame.rdc"


class TestOverdrawAnalysis:
    """Tests for overdraw analysis."""

    def test_mock_overdraw_fields(self):
        result = analyze_overdraw("test.rdc", use_mock=True)
        assert "overdraw_ratio" in result
        assert "overdraw_distribution" in result
        assert "pixel_fill_rate" in result
        assert "bandwidth" in result
        assert "high_overdraw_regions" in result
        assert "optimization_potential" in result
        assert result["mock"] is True

    def test_overdraw_ratio_positive(self):
        result = analyze_overdraw("test.rdc", use_mock=True)
        assert result["overdraw_ratio"] > 0

    def test_bandwidth_fields(self):
        result = analyze_overdraw("test.rdc", use_mock=True)
        bw = result["bandwidth"]
        assert "estimated_bandwidth_gb" in bw
        assert "render_target_writes_gb" in bw
        assert "texture_reads_gb" in bw
        assert "depth_writes_gb" in bw

    def test_optimization_suggestions(self):
        result = analyze_overdraw("test.rdc", use_mock=True)
        opt = result["optimization_potential"]
        assert "bandwidth_saving_mb" in opt
        assert "suggestions" in opt
        assert len(opt["suggestions"]) > 0

    def test_overdraw_source_file(self):
        result = analyze_overdraw("my_frame.rdc", use_mock=True)
        assert result["source_file"] == "my_frame.rdc"


class TestBaselines:
    """Tests for baseline comparison."""

    def test_pass_within_budget(self):
        data = {
            "draw_calls": 1000,
            "triangles": 500_000,
            "texture_memory_mb": 1000,
        }
        result = compare_with_baseline(data, "pc_high")
        assert result["status"] == "PASS"
        assert len(result["over_budget"]) == 0

    def test_fail_over_budget(self):
        data = {
            "draw_calls": 6000,
            "triangles": 4_000_000,
            "texture_memory_mb": 5000,
        }
        result = compare_with_baseline(data, "pc_high")
        assert result["status"] == "FAIL"
        assert len(result["over_budget"]) >= 3

    def test_partial_over_budget(self):
        data = {
            "draw_calls": 3000,  # OK for pc_high (5000)
            "triangles": 4_000_000,  # Over (3M)
            "texture_memory_mb": 1000,  # OK (4096)
        }
        result = compare_with_baseline(data, "pc_high")
        assert result["status"] == "FAIL"
        assert len(result["over_budget"]) == 1
        assert result["over_budget"][0]["name"] == "三角形数量"

    def test_mobile_mid_baseline(self):
        data = {
            "draw_calls": 900,
            "triangles": 300_000,
            "texture_memory_mb": 700,
        }
        result = compare_with_baseline(data, "mobile_mid")
        assert result["status"] == "FAIL"
        assert result["over_budget"][0]["name"] == "DrawCall 数量"

    def test_unknown_platform(self):
        result = compare_with_baseline({}, "unknown")
        assert "error" in result

    def test_ratio_calculation(self):
        data = {
            "draw_calls": 2500,
            "triangles": 1_500_000,
            "texture_memory_mb": 2048,
        }
        result = compare_with_baseline(data, "pc_high")
        for metric in result["metrics"]:
            assert "ratio" in metric
            assert metric["ratio"] > 0

    def test_new_metrics_shader_variants(self):
        data = {
            "draw_calls": 1000,
            "triangles": 500_000,
            "texture_memory_mb": 1000,
            "shader_variants": 400,  # Over pc_high limit of 300
        }
        result = compare_with_baseline(data, "pc_high")
        assert result["status"] == "FAIL"
        shader_entry = [m for m in result["metrics"] if m["name"] == "Shader 变体数"]
        assert len(shader_entry) == 1
        assert shader_entry[0]["over_budget"] is True

    def test_new_metrics_overdraw(self):
        data = {
            "draw_calls": 1000,
            "triangles": 500_000,
            "texture_memory_mb": 1000,
            "overdraw_ratio": 4.0,  # Over pc_high limit of 3.0
        }
        result = compare_with_baseline(data, "pc_high")
        assert result["status"] == "FAIL"
        overdraw_entry = [m for m in result["metrics"] if m["name"] == "Overdraw 比例"]
        assert len(overdraw_entry) == 1
        assert overdraw_entry[0]["over_budget"] is True

    def test_new_metrics_frame_time(self):
        data = {
            "draw_calls": 1000,
            "triangles": 500_000,
            "texture_memory_mb": 1000,
            "frame_time_ms": 20.0,  # Over pc_high limit of 16.67
        }
        result = compare_with_baseline(data, "pc_high")
        assert result["status"] == "FAIL"
        ft_entry = [m for m in result["metrics"] if m["name"] == "帧时间 (ms)"]
        assert len(ft_entry) == 1
        assert ft_entry[0]["over_budget"] is True

    def test_mobile_high_new_metrics(self):
        """Mobile high should have stricter thresholds for new metrics."""
        data = {
            "draw_calls": 500,
            "triangles": 200_000,
            "texture_memory_mb": 500,
            "shader_variants": 120,  # Over mobile_high limit of 100
            "overdraw_ratio": 2.5,  # Over mobile_high limit of 2.0
        }
        result = compare_with_baseline(data, "mobile_high")
        assert result["status"] == "FAIL"
        assert len(result["over_budget"]) == 2


class TestReportGeneration:
    """Tests for report generation with new data."""

    def test_json_report_with_all_data(self):
        from renderdoc_agent.report import generate_json_report

        analysis = _mock_rdc_data("test.rdc")
        baseline = compare_with_baseline(analysis, "pc_high")
        texture = analyze_textures("test.rdc", use_mock=True)
        shader = analyze_shaders("test.rdc", use_mock=True)
        gpu_time = analyze_gpu_time("test.rdc", use_mock=True)
        overdraw = analyze_overdraw("test.rdc", use_mock=True)

        report_str = generate_json_report(analysis, baseline, texture, shader, gpu_time, overdraw)
        report = json.loads(report_str)

        assert "texture_analysis" in report
        assert "shader_analysis" in report
        assert "gpu_time_analysis" in report
        assert "overdraw_analysis" in report
        assert report["texture_analysis"]["total_textures"] == 187

    def test_csv_report_with_all_data(self):
        from renderdoc_agent.report import generate_csv_report

        analysis = _mock_rdc_data("test.rdc")
        baseline = compare_with_baseline(analysis, "pc_high")
        texture = analyze_textures("test.rdc", use_mock=True)
        shader = analyze_shaders("test.rdc", use_mock=True)
        gpu_time = analyze_gpu_time("test.rdc", use_mock=True)
        overdraw = analyze_overdraw("test.rdc", use_mock=True)

        report = generate_csv_report(analysis, baseline, texture, shader, gpu_time, overdraw)
        assert "纹理分析" in report
        assert "Shader 分析" in report
        assert "GPU 耗时分析" in report
        assert "Overdraw 分析" in report


if __name__ == "__main__":
    # Simple test runner
    test_classes = [
        TestAnalyzeRDC,
        TestTextureAnalysis,
        TestShaderAnalysis,
        TestGPUTimeAnalysis,
        TestOverdrawAnalysis,
        TestBaselines,
        TestReportGeneration,
    ]
    passed = 0
    failed = 0
    for cls in test_classes:
        instance = cls()
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                    print(f"  PASS: {cls.__name__}.{method_name}")
                    passed += 1
                except Exception as e:
                    print(f"  FAIL: {cls.__name__}.{method_name} - {e}")
                    failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")

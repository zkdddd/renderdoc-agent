# RenderDoc Agent

游戏渲染性能分析 Agent，基于 RenderDoc 抓帧数据和 LLM 进行自动性能诊断。

## 功能

- 解析 RenderDoc `.rdc` 帧捕获文件
- 提取 DrawCall、三角形、纹理显存、Shader 等指标
- 与多平台性能基线对比（移动端/PC，高端/中端）
- 输出结构化诊断报告与优化建议

## 安装

```bash
cd renderdoc-agent
pip install -e .
```

## 前置条件

1. **Ollama**：本地运行 LLM 服务
   ```bash
   # 安装 Ollama 后拉取模型
   ollama pull qwen2.5:3b
   ```

2. **rdc-cli**（可选）：用于解析真实 `.rdc` 文件
   - 无 rdc-cli 时自动使用模拟数据模式

## 使用

```bash
# 直接分析文件（默认 quick）
python -m renderdoc_agent path/to/frame.rdc --renderdoc-path D:/kd/Tool/ren1.36/Development/pymodules --helper-python D:/py36/python.exe

# 指定分析档位
python -m renderdoc_agent frame.rdc --mode quick --output-dir ./out
python -m renderdoc_agent frame.rdc --mode half --output-dir ./out
python -m renderdoc_agent frame.rdc --mode full --output-dir ./out

# 批量分析（默认串行）
python -m renderdoc_agent --input-dir D:/rdc_samples --mode quick --output-dir ./batch_out

# 批量分析（递归 + 并发 2）
python -m renderdoc_agent --input-dir D:/rdc_samples --recursive --jobs 2 --mode half --output-dir ./batch_out
```

固定输出文件:

- `out/result.json`
- `out/report.md`

批量模式会额外生成:

- `<output-dir>/summary.csv`
- `<output-dir>/<序号>_<文件名>/result.json`
- `<output-dir>/<序号>_<文件名>/report.md`

`result.json` 包含结构化指标与运行元数据（`run_meta.timings_ms`），用于性能对比与自动化处理。

### 参数说明

- `--mode quick|half|full`：分析档位（默认 `quick`）
- `--output-dir`：输出目录（固定写入 `result.json` 和 `report.md`）
- `--input-dir`：批量分析目录（与单文件路径二选一）
- `--recursive`：批量模式递归扫描子目录
- `--jobs`：批量并发数（默认 `1`，推荐先串行）
- `--platform`：目标平台基线
- `--renderdoc-path`：`renderdoc.pyd` 所在目录
- `--helper-python`：用于 helper 的 Python（建议 3.6）

### 平台基线

| 平台 | DrawCall | 三角形 | 纹理显存 |
|------|----------|--------|----------|
| mobile_high | ≤1500 | ≤800K | ≤1.5GB |
| mobile_mid | ≤800 | ≤400K | ≤800MB |
| pc_high | ≤5000 | ≤3M | ≤4GB |
| pc_mid | ≤2500 | ≤1.5M | ≤2GB |

## 测试

```bash
python -m pytest tests/ -v
# 或
python tests/test_analyze_rdc.py
```

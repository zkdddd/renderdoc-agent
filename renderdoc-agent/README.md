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
# 交互模式
python -m renderdoc_agent

# 直接分析文件
python -m renderdoc_agent path/to/frame.rdc

# 指定平台
python -m renderdoc_agent frame.rdc --platform mobile_mid

# 指定模型
python -m renderdoc_agent --model qwen2.5:3b
```

### 交互命令

| 命令 | 说明 |
|------|------|
| `<path.rdc>` | 分析 .rdc 文件 |
| `platform <name>` | 切换目标平台 |
| `reset` | 清除对话历史 |
| `help` | 显示帮助 |
| `quit` | 退出 |

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

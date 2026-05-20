"""ReAct Agent core loop for RenderDoc Agent."""

import json
from typing import Any, Optional

from .llm import OllamaClient
from .memory import Memory
from .tools.registry import ToolRegistry
from .config import Config

SYSTEM_PROMPT = """你是一位专业的游戏渲染性能分析师，擅长使用 RenderDoc 抓帧数据诊断 GPU 渲染瓶颈。

## 你的能力
- 使用 analyze_rdc 工具解析 .rdc 帧捕获文件，提取 DrawCall、三角形、纹理显存、Shader 等基础指标
- 使用 analyze_textures 工具分析纹理格式、尺寸、Mipmap、压缩情况、内存占用
- 使用 analyze_shaders 工具分析 Shader 变体数量、复杂度、编译指令数、Uniform 使用情况
- 使用 analyze_gpu_time 工具分析各 Pass 和 DrawCall 的 GPU 耗时，找出渲染瓶颈
- 使用 analyze_overdraw 工具分析 Overdraw 比例、像素填充率、带宽消耗
- 使用 compare_baseline 工具将指标与目标平台性能基线对比，识别超标项

## 分析流程
1. 用户提供 .rdc 文件路径后，先调用 analyze_rdc 获取基础渲染指标
2. 调用 analyze_textures 获取纹理详情，检查压缩率和 Mipmap 状态
3. 调用 analyze_shaders 获取 Shader 变体和复杂度信息
4. 调用 analyze_gpu_time 获取各 Pass 耗时，识别最慢的 Pass
5. 调用 analyze_overdraw 获取 Overdraw 和带宽数据
6. 根据用户指定的目标平台（默认 PC 高端），调用 compare_baseline 进行基线对比
7. 基于所有数据给出结构化的性能分析报告

## 输出格式
分析完成后，严格按以下格式输出：

### 【性能摘要】
用表格列出关键指标及与基线的对比结果。

### 【诊断分析】
逐项分析超标指标和潜在问题：
- DrawCall 过高：可能是合批不足、UI 元素过多
- 三角形过多：LOD 不足、远处模型未简化
- 纹理显存过大：纹理未压缩、Mipmap 缺失、分辨率过高
- 纹理问题：列出未压缩纹理和缺少 Mipmap 的纹理
- Shader 问题：变体爆炸、复杂度过高、Uniform 冗余
- GPU 耗时：哪个 Pass 是瓶颈，最耗时的 DrawCall
- Overdraw 问题：高 Overdraw 区域、带宽消耗过高

### 【优化建议】
给出 3-5 条具体可操作的优化建议，按优先级排序，每条说明预期收益。

## 注意事项
- 数据不足时主动用工具获取，不要猜测
- 如果 renderdoc 模块不可用，使用模拟数据时要明确告知用户
- 用中文回答
"""


class ReactAgent:
    """ReAct (Reasoning + Acting) agent loop."""

    def __init__(self, config: Config):
        self.config = config
        self.llm = OllamaClient(config)
        self.memory = Memory()
        self.registry = ToolRegistry()
        self._extracted_data = None  # Cache for extracted data
        self._rd_available = False
        self._init_renderdoc()
        self._register_tools()

    def _init_renderdoc(self):
        """Check if renderdoc API is available."""
        from .tools.rdc_replay import init_renderdoc
        self._rd_available = init_renderdoc(self.config.renderdoc_module_path)

    def _ensure_data(self, rdc_file: str) -> dict:
        """Get extracted rendering data for an .rdc file.

        Uses the renderdoc Python API to extract all data at once,
        then caches the result for subsequent tool calls.

        Returns:
            Dict with all extracted data, or None if unavailable (falls back to mock).
        """
        if self._extracted_data is not None:
            return self._extracted_data

        if not self._rd_available:
            return None

        from .tools.rdc_replay import extract_via_renderdoc_api
        try:
            self._extracted_data = extract_via_renderdoc_api(
                rdc_file, self.config.renderdoc_module_path
            )
            return self._extracted_data
        except Exception as e:
            if not self.config.use_mock_data:
                raise
            return None

    def _register_tools(self):
        """Register all available tools."""
        from .tools.analyze_rdc import create_analyze_rdc_tool
        from .tools.baselines import create_baseline_tool
        from .tools.texture_analysis import create_texture_analysis_tool
        from .tools.shader_analysis import create_shader_analysis_tool
        from .tools.gpu_time_analysis import create_gpu_time_analysis_tool
        from .tools.overdraw_analysis import create_overdraw_analysis_tool

        self.registry.register(create_analyze_rdc_tool(self._ensure_data, self.config))
        self.registry.register(create_baseline_tool())
        self.registry.register(create_texture_analysis_tool(self._ensure_data, self.config))
        self.registry.register(create_shader_analysis_tool(self._ensure_data, self.config))
        self.registry.register(create_gpu_time_analysis_tool(self._ensure_data, self.config))
        self.registry.register(create_overdraw_analysis_tool(self._ensure_data, self.config))

    def _build_system_message(self) -> dict:
        return {"role": "system", "content": SYSTEM_PROMPT}

    def run(self, user_input: str) -> str:
        """Run the ReAct loop for a user query.

        Args:
            user_input: User's message.

        Returns:
            Final text response from the agent.
        """
        # Initialize with system prompt if this is the first message
        if not self.memory.messages:
            self.memory.messages.append(self._build_system_message())

        self.memory.add_message("user", user_input)

        tools_schema = self.registry.to_openai_schemas()

        for round_num in range(self.config.max_tool_rounds):
            response = self.llm.chat_once(
                self.memory.get_messages(),
                tools=tools_schema,
            )

            msg = response.get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])

            # If no tool calls, we have the final answer
            if not tool_calls:
                self.memory.add_message("assistant", content)
                return content

            # Add assistant message with tool calls
            self.memory.add_message("assistant", content or "", tool_calls=tool_calls)

            # Execute each tool call
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                raw_args = func.get("arguments", {})

                # arguments may be a JSON string or already a dict
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args

                tool_call_id = tc.get("id", f"call_{tool_name}_{round_num}")

                try:
                    result = self.registry.execute(tool_name, args)
                    result_str = json.dumps(result, ensure_ascii=False, indent=2)
                except Exception as e:
                    result_str = json.dumps({"error": str(e)}, ensure_ascii=False)

                self.memory.add_tool_result(tool_call_id, tool_name, result_str)

        # Max rounds reached — ask LLM for a final summary with all gathered data
        self.memory.add_message("user", "请基于以上所有工具返回的数据，给出完整的性能分析报告。")
        response = self.llm.chat_once(self.memory.get_messages())
        final_content = response.get("message", {}).get("content", "分析完成，但未能生成最终报告。")
        self.memory.add_message("assistant", final_content)
        return final_content

    def reset(self):
        """Clear conversation history."""
        self.memory.clear()
        self._extracted_data = None

    def shutdown(self):
        """Release resources."""
        self._extracted_data = None

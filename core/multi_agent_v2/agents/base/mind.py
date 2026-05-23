"""
Mind - Agent心智（思考引擎）

每个 Agent 拥有独立的心智，负责：
- LLM 驱动的思考与推理
- 计划制定与置信度评估
- 工具调用选择（LLM function-calling）
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from .models import Thought, Task

logger = logging.getLogger(__name__)


class Mind:
    """Agent心智 - 思考引擎"""

    def __init__(self, agent: 'BaseAgent'):
        self.agent = agent
        self.thinking_history: List[Thought] = []
        self.llm_router = None
        self.prompt_manager = None
        self._trace: Optional[Any] = None
        self._init_dependencies()

    def _init_dependencies(self):
        """初始化依赖（延迟导入避免循环依赖）"""
        try:
            from core.engine.llm_backend import get_llm_router
            from core.multi_agent_v2.agents.prompts.agent_prompts import get_prompt_manager
            self.llm_router = get_llm_router()
            self.prompt_manager = get_prompt_manager()
            logger.info(f"Mind组件依赖初始化成功 (Agent: {self.agent.agent_id})")
        except Exception as e:
            logger.warning(f"Mind组件依赖初始化失败: {e}")

    async def _get_available_tool_definitions(self, task_description: str = "") -> List[Dict]:
        """获取可用工具定义，按任务描述筛选

        使用 ToolRegistry 统一管理，支持按任务过滤减少注入数量。
        返回 OpenAI function-calling 格式。
        """
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry

        registry = get_tool_registry()
        if not registry._initialized:
            await registry.discover_all()

        if task_description:
            tools = registry.get_tools_for_task(task_description, max_tools=20)
        else:
            tools = list(registry._tools.values())

        definitions = []
        for t in tools:
            definitions.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
                "_server": t.server,
                "_tool_name": t.tool_name,
            })

        if definitions:
            logger.info(f"Mind 获取到 {len(definitions)} 个工具定义 (任务过滤: {bool(task_description)})")
        return definitions

    async def think(self, task: Task) -> Thought:
        """思考：LLM驱动，最多重试3次，失败直接报错"""
        logger.info(f"Agent {self.agent.agent_id} 正在思考任务: {task.type}")

        trace = self._trace
        if trace:
            trace.on_thinking("思考中", task.description[:80])

        if not self.llm_router or not self.prompt_manager:
            raise RuntimeError(f"LLM 不可用 (agent={self.agent.agent_id})，无法思考")

        last_error = None
        for attempt in range(3):
            try:
                thought = await self._think_with_llm(task)
                if trace:
                    trace.on_thinking_result(f"推理完成，计划 {len(thought.plan)} 步")
                    trace.set_plan(thought.plan)
                    trace.on_thinking_end()
                return thought
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM思考失败(第{attempt+1}次): {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue

        logger.error(f"LLM思考失败3次，放弃: {last_error}")
        raise RuntimeError(f"LLM思考失败: {last_error}")

    async def _think_with_llm(self, task: Task) -> Thought:
        # 获取提示词
        agent_type = self.agent.agent_type.value
        prompt = self.prompt_manager.get_prompt(agent_type)

        if not prompt:
            raise RuntimeError(f"未找到提示词 (agent_type={agent_type})")

        # 构建思考提示词
        thinking_prompt = prompt.thinking_prompt.format(
            task_description=task.description,
            task_id=task.task_id,
            task_type=task.type,
            task_result="待思考",
            plan="待制定...",
            conclusion="待定",
        )

        # 查重提醒注入
        try:
            _advice = self.agent._tracker.advice(task.description)
            if _advice:
                thinking_prompt += f"\n\n{_advice}"
        except Exception:
            pass

        # RAG 知识注入 — 思考前查知识库
        try:
            from core.search.rag_search_engine import RAGSearchEngine
            engine = RAGSearchEngine()
            rag_result = await engine.search_and_learn(
                query=task.description, user_id=1, max_results=3, learn=False
            )
            if rag_result and rag_result.get("results"):
                knowledge = rag_result["results"]
                thinking_prompt += f"\n\n### 相关知识\n{knowledge[:2000]}"
        except Exception as e:
            logger.debug(f"RAG 知识注入失败: {e}")

        # 获取工具定义并注入（按任务描述筛选，减少 LLM 选择噪音）
        tool_defs = await self._get_available_tool_definitions(task_description=task.description)
        tools_param = tool_defs if tool_defs else None
        if tools_param and len(tools_param) > 50:
            for td in tools_param:
                fn = td.get("function", {})
                desc = fn.get("description", "")
                if len(desc) > 200:
                    fn["description"] = desc[:200] + "..."
        if tools_param:
            logger.debug(f"注入 {len(tools_param)} 个工具定义到 LLM")

        # 构建完整的消息列表
        messages = [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": thinking_prompt}
        ]

        # 调用LLM（带超时）
        try:
            response = await asyncio.wait_for(
                self.llm_router.chat(messages, temperature=0.7, max_tokens=1500, tools=tools_param),
                timeout=25,
            )
        except asyncio.TimeoutError:
            logger.warning("LLM 响应超时")
            raise TimeoutError("LLM 响应超时")
        except Exception as e:
            logger.warning(f"LLM chat 失败: {e}")
            raise

        # 检测 LLM 返回的 tool_calls（OpenAI 格式：choices[0].message.tool_calls）
        tool_calls_parsed = self._extract_tool_calls(response)
        if tool_calls_parsed is not None:
            # 从 OpenAI 格式中提取文本内容
            content = self._extract_openai_content(response) or response
            thought = self._parse_llm_response(content, task)
            thought.tool_calls = tool_calls_parsed
            logger.info(f"LLM 自主选择了 {len(tool_calls_parsed)} 个工具调用")
            return thought

        # 解析LLM响应
        thought = self._parse_llm_response(response, task)
        return thought

    def _parse_llm_response(self, response: str, task: Task) -> Thought:
        """解析LLM响应为Thought对象（JSON 优先，文本 fallback）"""
        reasoning = response
        plan = []
        confidence = 0.5

        # 尝试 JSON 解析
        parsed_json = self._try_parse_json_response(response)
        if parsed_json:
            reasoning = parsed_json.get("reasoning", response)
            plan = parsed_json.get("plan", [])
            confidence = self._confidence_from_response(json.dumps(parsed_json, ensure_ascii=False), plan)
        else:
            # 文本 fallback：从行中提取计划
            lines = response.split('\n')
            for line in lines:
                if line.strip():
                    plan.append(line.strip())
                    if len(plan) >= 10:
                        break
            confidence = self._confidence_from_response(response, plan)

        if not plan:
            plan = [f"步骤{i+1}: 执行任务" for i in range(min(task.estimated_steps, 5))]

        return Thought(
            reasoning=reasoning,
            plan=plan[:5],
            confidence=confidence
        )

    def _try_parse_json_response(self, response: str) -> Optional[Dict]:
        """尝试从 LLM 响应中提取 JSON 对象"""
        # 尝试直接解析
        try:
            parsed = json.loads(response)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        block_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response, re.DOTALL)
        if block_match:
            try:
                parsed = json.loads(block_match.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # 尝试提取第一个 { } 包裹的 JSON
        brace_match = re.search(r'\{.*\}', response, re.DOTALL)
        if brace_match:
            try:
                parsed = json.loads(brace_match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return None

    def _normalize_tool_calls(self, tool_calls_raw: List[Dict]) -> List[Dict]:
        """标准化 OpenAI 格式 tool_calls 为统一内部格式

        输入（OpenAI function-calling）:
          [{"id": "call_1", "type": "function",
            "function": {"name": "server.tool", "arguments": '{"key": "val"}'}}]
        输出:
          [{"id": "call_1", "name": "server.tool", "arguments": {"key": "val"},
            "_server": "server", "_tool_name": "tool"}]
        """
        result = []
        for tc in tool_calls_raw:
            func = tc.get("function", {})
            name = func.get("name", "")
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}
            parts = name.split(".", 1)
            server = parts[0] if len(parts) > 1 else ""
            tool_name = parts[1] if len(parts) > 1 else name
            result.append({
                "id": tc.get("id", ""),
                "name": name,
                "arguments": args,
                "_server": server,
                "_tool_name": tool_name,
            })
        return result

    def _extract_tool_calls(self, response: str) -> Optional[List[Dict]]:
        """从 LLM 响应中提取工具调用（仅 OpenAI 格式）

        OpenAI 格式：
        {"choices": [{"message": {"role": "assistant",
                                       "content": "...",
                                       "tool_calls": [...]}}]}
        """
        try:
            parsed = json.loads(response)
            if not isinstance(parsed, dict):
                return None
            choices = parsed.get("choices", [])
            if not choices:
                return None
            msg = choices[0].get("message", {})
            tool_calls_raw = msg.get("tool_calls", [])
            if not tool_calls_raw:
                return None
            return self._normalize_tool_calls(tool_calls_raw)
        except (json.JSONDecodeError, Exception):
            return None

    def _extract_openai_content(self, response: str) -> Optional[str]:
        """从 OpenAI 格式响应中提取 choices[0].message.content"""
        try:
            parsed = json.loads(response)
            if not isinstance(parsed, dict):
                return None
            choices = parsed.get("choices", [])
            if not choices:
                return None
            return choices[0].get("message", {}).get("content")
        except (json.JSONDecodeError, Exception):
            return None

    def _confidence_from_response(self, response: str, plan: List[str]) -> float:
        """多因子置信度计算"""
        base = 0.3
        step_count = len(plan)

        # 计划步骤数：2-6 步为佳
        if 2 <= step_count <= 6:
            base += 0.2
        elif step_count > 0:
            base += 0.1

        # 响应长度指示思考深度
        length_factor = min(len(response) / 2000, 0.3)
        base += length_factor

        # 关键词标记（思考质量）
        quality_keywords = ["search", "analysis", "compare", "总结", "搜索", "分析", "比较", "因此", "结论"]
        if any(kw in response.lower() for kw in quality_keywords):
            base += 0.1

        # 不确定性标记惩罚
        uncertainty_markers = ["perhaps", "maybe", "might", "不确定", "可能", "也许", "大概"]
        uncertainty_count = sum(1 for m in uncertainty_markers if m in response.lower())
        base -= uncertainty_count * 0.05

        return max(0.3, min(base, 0.95))


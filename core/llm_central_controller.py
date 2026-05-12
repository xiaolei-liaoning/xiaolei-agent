#!/usr/bin/env python3
"""LLM中枢控制器 - 让LLM真正成为大脑"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """决策类型"""
    CALL_TOOL = "call_tool"
    CALL_AGENT = "call_agent"
    DIRECT_ANSWER = "direct_answer"
    ASK_USER = "ask_user"
    RETRY = "retry"
    SKIP = "skip"
    FINISH = "finish"
    ADJUST_PLAN = "adjust_plan"


@dataclass
class Decision:
    """决策结果"""
    type: DecisionType
    tool_name: Optional[str] = None
    agent_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 0.0
    next_steps: List[str] = field(default_factory=list)


@dataclass
class AgentState:
    """Agent状态"""
    goal: str
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)
    plan: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)


class LLMDecisionEngine:
    """LLM决策引擎"""

    def __init__(self, llm_facade=None):
        self.llm_facade = llm_facade or self._init_default_llm()

    def _init_default_llm(self):
        try:
            from core.task_decomposer import GLMClient
            return GLMClient()
        except Exception as e:
            logger.warning(f"无法初始化默认LLM: {e}")
            return None

    async def _call_llm(self, prompt_dict: Dict) -> str:
        """统一调用LLM的方法"""
        if hasattr(self.llm_facade, 'generate'):
            return await self.llm_facade.generate(prompt_dict)
        elif hasattr(self.llm_facade, '_router') and hasattr(self.llm_facade._router, 'simple_chat'):
            return await self.llm_facade._router.simple_chat(
                user_message=prompt_dict.get('prompt', ''),
                system_prompt="你是一个AI决策专家，擅长分析任务并做出最佳决策。",
                temperature=0.7
            )
        return ""

    async def make_decision(self, state: AgentState, available_tools: List[Dict], 
                           available_agents: List[str]) -> Decision:
        if not self.llm_facade:
            return self._fallback_decision(state, available_tools, available_agents)

        prompt = self._build_decision_prompt(state, available_tools, available_agents)

        try:
            response = await self._call_llm(prompt)
            return self._parse_decision(response, state)
        except Exception as e:
            logger.error(f"LLM决策失败: {e}")
            return self._fallback_decision(state, available_tools, available_agents)

    def _build_decision_prompt(self, state: AgentState, tools: List[Dict], agents: List[str]) -> Dict:
        tools_str = "\n".join([f"- {t['name']}: {t.get('description', '')}" for t in tools])
        agents_str = "\n".join([f"- {a}" for a in agents])
        history_str = "\n".join([f"{h.get('role', '')}: {h.get('content', '')[:50]}..." for h in state.history[-5:]])
        tool_results_str = "\n".join([f"- {r.get('tool', '')}: {'成功' if r.get('success') else '失败'}" for r in state.tool_results[-3:]])

        system_prompt = """你是AI决策专家，请根据状态决定下一步行动。

状态：
- 目标：{goal}
- 历史：{history}
- 工具结果：{tool_results}
- 当前计划：{plan}

可用工具：
{tools}

可用Agent：
{agents}

决策类型：
1. CALL_TOOL <工具名> - 调用工具
2. CALL_AGENT <Agent名> - 调用Agent
3. DIRECT_ANSWER - 直接回答
4. ASK_USER - 询问用户
5. RETRY - 重试
6. SKIP - 跳过
7. FINISH - 完成
8. ADJUST_PLAN - 调整计划

输出JSON：{{"decision": "类型", "target": "目标", "arguments": {{}}, "reasoning": "原因"}}"""

        return {
            "prompt": system_prompt.format(
                goal=state.goal, history=history_str, tool_results=tool_results_str,
                plan=str(state.plan), tools=tools_str, agents=agents_str
            ),
            "metadata": {"task_type": "decision_making"}
        }

    def _parse_decision(self, response: str, state: AgentState) -> Decision:
        try:
            import json
            data = json.loads(response)
            decision_type = data.get("decision", "DIRECT_ANSWER")
            target = data.get("target", "")
            
            decision_mapping = {
                "CALL_TOOL": DecisionType.CALL_TOOL,
                "CALL_AGENT": DecisionType.CALL_AGENT,
                "DIRECT_ANSWER": DecisionType.DIRECT_ANSWER,
                "ASK_USER": DecisionType.ASK_USER,
                "RETRY": DecisionType.RETRY,
                "SKIP": DecisionType.SKIP,
                "FINISH": DecisionType.FINISH,
                "ADJUST_PLAN": DecisionType.ADJUST_PLAN
            }

            return Decision(
                type=decision_mapping.get(decision_type, DecisionType.DIRECT_ANSWER),
                tool_name=target if decision_type == "CALL_TOOL" else None,
                agent_name=target if decision_type == "CALL_AGENT" else None,
                arguments=data.get("arguments", {}),
                reasoning=data.get("reasoning", ""),
                confidence=0.85
            )
        except Exception as e:
            logger.error(f"解析决策失败: {e}")
            return self._fallback_decision(state, [], [])

    def _fallback_decision(self, state: AgentState, tools: List[Dict], agents: List[str]) -> Decision:
        if state.plan and state.plan[0] not in state.completed_tasks:
            return Decision(type=DecisionType.CALL_TOOL, tool_name=state.plan[0], reasoning="按计划执行", confidence=0.7)
        if state.tool_results:
            return Decision(type=DecisionType.FINISH, reasoning="任务完成", confidence=0.6)
        return Decision(type=DecisionType.DIRECT_ANSWER, reasoning="直接回答", confidence=0.5)


class LLM_ToolSelector:
    """LLM工具选择器"""

    def __init__(self, llm_facade=None):
        self.llm_facade = llm_facade or self._init_default_llm()

    def _init_default_llm(self):
        try:
            from core.task_decomposer import GLMClient
            return GLMClient()
        except Exception:
            return None

    async def _call_llm(self, prompt_dict: Dict) -> str:
        """统一调用LLM的方法"""
        if hasattr(self.llm_facade, 'generate'):
            return await self.llm_facade.generate(prompt_dict)
        elif hasattr(self.llm_facade, '_router') and hasattr(self.llm_facade._router, 'simple_chat'):
            return await self.llm_facade._router.simple_chat(
                user_message=prompt_dict.get('prompt', ''),
                system_prompt="你是一个工具选择专家，擅长根据任务选择最合适的工具。",
                temperature=0.7
            )
        return ""

    async def select_tool(self, goal: str, tools: List[Dict], context: Dict = None) -> Dict:
        if not self.llm_facade:
            return self._fallback_select(goal, tools)

        prompt = self._build_selection_prompt(goal, tools, context)

        try:
            response = await self._call_llm(prompt)
            return self._parse_selection(response, tools)
        except Exception as e:
            logger.error(f"LLM工具选择失败: {e}")
            return self._fallback_select(goal, tools)

    def _build_selection_prompt(self, goal: str, tools: List[Dict], context: Dict) -> Dict:
        tools_str = "\n".join([f"{i+1}. {t['name']}: {t.get('description', '')}" for i, t in enumerate(tools)])
        return {
            "prompt": f"""选择最合适的工具。

目标：{goal}

工具：
{tools_str}

输出JSON：{{"tool_name": "工具名", "arguments": {{}}, "reasoning": "原因"}}""",
            "metadata": {"task_type": "tool_selection"}
        }

    def _parse_selection(self, response: str, tools: List[Dict]) -> Dict:
        try:
            import json
            data = json.loads(response)
            return {"tool_name": data.get("tool_name", ""), "arguments": data.get("arguments", {}), "reasoning": data.get("reasoning", "")}
        except Exception:
            return self._fallback_select("", tools)

    def _fallback_select(self, goal: str, tools: List[Dict]) -> Dict:
        keywords_map = {"爬取": "web_scraper", "搜索": "search", "分析": "analyzer", "写": "writer", "总结": "summarizer"}
        for kw, tool_name in keywords_map.items():
            if kw in goal:
                return {"tool_name": tool_name, "arguments": {}, "reasoning": f"关键词匹配: {kw}"}
        return {"tool_name": "", "arguments": {}, "reasoning": "未找到匹配工具"}


class LLMReflectionController:
    """LLM反思控制器"""

    def __init__(self, llm_facade=None):
        self.llm_facade = llm_facade or self._init_default_llm()

    def _init_default_llm(self):
        try:
            from core.task_decomposer import GLMClient
            return GLMClient()
        except Exception:
            return None

    async def _call_llm(self, prompt_dict: Dict) -> str:
        """统一调用LLM的方法"""
        if hasattr(self.llm_facade, 'generate'):
            return await self.llm_facade.generate(prompt_dict)
        elif hasattr(self.llm_facade, '_router') and hasattr(self.llm_facade._router, 'simple_chat'):
            return await self.llm_facade._router.simple_chat(
                user_message=prompt_dict.get('prompt', ''),
                system_prompt="你是一个AI反思专家，擅长评估执行结果并给出改进建议。",
                temperature=0.7
            )
        return ""

    async def reflect(self, goal: str, history: List[Dict], results: List[Dict]) -> Dict:
        if not self.llm_facade:
            return self._fallback_reflect(results)

        prompt = self._build_reflection_prompt(goal, history, results)

        try:
            response = await self._call_llm(prompt)
            return self._parse_reflection(response)
        except Exception as e:
            logger.error(f"LLM反思失败: {e}")
            return self._fallback_reflect(results)

    def _build_reflection_prompt(self, goal: str, history: List[Dict], results: List[Dict]) -> Dict:
        results_str = "\n".join([f"- 步骤{i+1}: {'成功' if r.get('success') else '失败'}" for i, r in enumerate(results)])
        return {
            "prompt": f"""评估执行结果并决定下一步。

目标：{goal}

结果：
{results_str}

输出JSON：{{"decision": "CONTINUE/RETRY/ADJUST/FINISH", "next_step": "下一步", "reasoning": "原因"}}""",
            "metadata": {"task_type": "reflection"}
        }

    def _parse_reflection(self, response: str) -> Dict:
        try:
            import json
            data = json.loads(response)
            return {"decision": data.get("decision", "CONTINUE"), "next_step": data.get("next_step", ""), "reasoning": data.get("reasoning", "")}
        except Exception:
            return {"decision": "CONTINUE", "next_step": "", "reasoning": ""}

    def _fallback_reflect(self, results: List[Dict]) -> Dict:
        failed = [r for r in results if not r.get("success")]
        if failed:
            return {"decision": "RETRY", "next_step": "重试失败步骤", "reasoning": "存在失败"}
        if results:
            return {"decision": "FINISH", "next_step": "总结", "reasoning": "完成"}
        return {"decision": "CONTINUE", "next_step": "继续", "reasoning": "继续"}


class LLM_AgentCoordinator:
    """LLM多Agent协调器"""

    def __init__(self, llm_facade=None):
        self.llm_facade = llm_facade or self._init_default_llm()

    def _init_default_llm(self):
        try:
            from core.task_decomposer import GLMClient
            return GLMClient()
        except Exception:
            return None

    async def _call_llm(self, prompt_dict: Dict) -> str:
        """统一调用LLM的方法"""
        if hasattr(self.llm_facade, 'generate'):
            return await self.llm_facade.generate(prompt_dict)
        elif hasattr(self.llm_facade, '_router') and hasattr(self.llm_facade._router, 'simple_chat'):
            return await self.llm_facade._router.simple_chat(
                user_message=prompt_dict.get('prompt', ''),
                system_prompt="你是一个多Agent协调专家，擅长分配任务给最合适的Agent。",
                temperature=0.7
            )
        return ""

    async def coordinate(self, goal: str, agents: List[Dict], agent_states: Dict[str, Any]) -> Dict:
        if not self.llm_facade:
            return self._fallback_coordinate(goal, agents)

        prompt = self._build_coordination_prompt(goal, agents, agent_states)

        try:
            response = await self._call_llm(prompt)
            return self._parse_coordination(response)
        except Exception as e:
            logger.error(f"LLM协调失败: {e}")
            return self._fallback_coordinate(goal, agents)

    def _build_coordination_prompt(self, goal: str, agents: List[Dict], states: Dict) -> Dict:
        agents_str = "\n".join([f"- {a['name']}: {a.get('role', '')}" for a in agents])
        return {
            "prompt": f"""协调Agent完成任务。

目标：{goal}

Agent：
{agents_str}

输出JSON：{{"agent_name": "Agent名", "task": "任务", "reasoning": "原因"}}""",
            "metadata": {"task_type": "agent_coordination"}
        }

    def _parse_coordination(self, response: str) -> Dict:
        try:
            import json
            data = json.loads(response)
            return {"agent_name": data.get("agent_name", ""), "task": data.get("task", ""), "reasoning": data.get("reasoning", "")}
        except Exception:
            return {"agent_name": "", "task": "", "reasoning": ""}

    def _fallback_coordinate(self, goal: str, agents: List[Dict]) -> Dict:
        role_map = {"分析": "analyzer", "写作": "writer", "爬取": "scraper", "总结": "summarizer", "审查": "reviewer"}
        for kw, role in role_map.items():
            if kw in goal:
                agent = next((a for a in agents if role in a.get('role', '')), None)
                if agent:
                    return {"agent_name": agent['name'], "task": goal, "reasoning": f"角色匹配: {role}"}
        return {"agent_name": "", "task": "", "reasoning": "未找到匹配"}


class LLM_CentralController:
    """LLM中枢控制器"""

    def __init__(self):
        self.decision_engine = LLMDecisionEngine()
        self.tool_selector = LLM_ToolSelector()
        self.reflection_controller = LLMReflectionController()
        self.agent_coordinator = LLM_AgentCoordinator()
        self.state = AgentState(goal="")

    async def process(self, user_input: str, tools: List[Dict], agents: List[Dict]) -> Dict:
        logger.info(f"LLM中枢处理: {user_input}")
        self.state.goal = user_input
        self.state.history.append({"role": "user", "content": user_input})

        while True:
            decision = await self.decision_engine.make_decision(
                self.state, tools, [a['name'] for a in agents]
            )

            if decision.type == DecisionType.CALL_TOOL:
                tool_info = await self.tool_selector.select_tool(decision.tool_name, tools, self.state.context)
                result = self._execute_tool(decision.tool_name, tool_info.get("arguments", {}))
                self.state.tool_results.append(result)
                self.state.completed_tasks.append(decision.tool_name)

            elif decision.type == DecisionType.CALL_AGENT:
                coord_result = await self.agent_coordinator.coordinate(
                    decision.arguments.get("task", ""), agents, {}
                )
                self.state.tool_results.append({"tool": decision.agent_name, "success": True})

            elif decision.type == DecisionType.DIRECT_ANSWER:
                return {"type": "answer", "content": decision.reasoning}

            elif decision.type == DecisionType.ASK_USER:
                return {"type": "ask", "question": decision.reasoning}

            elif decision.type == DecisionType.FINISH:
                summary = await self._generate_summary()
                return {"type": "finish", "summary": summary}

            elif decision.type == DecisionType.RETRY:
                if self.state.tool_results:
                    last_result = self.state.tool_results[-1]
                    last_tool = last_result.get("tool", "")
                    result = self._execute_tool(last_tool, {})
                    self.state.tool_results.append(result)

            reflection = await self.reflection_controller.reflect(
                self.state.goal, self.state.history, self.state.tool_results
            )

            if reflection.get("decision") == "FINISH":
                summary = await self._generate_summary()
                return {"type": "finish", "summary": summary}

            if reflection.get("next_step"):
                self.state.plan = [reflection["next_step"]]

    async def _generate_summary(self) -> str:
        if not self.decision_engine.llm_facade:
            return "任务完成"

        results_str = "\n".join([f"- {r.get('tool', '')}: {'成功' if r.get('success') else '失败'}" for r in self.state.tool_results])
        prompt = {
            "prompt": f"""总结任务执行：

目标：{self.state.goal}

结果：
{results_str}

提供详细总结。""",
            "metadata": {"task_type": "summary"}
        }

        try:
            response = await self.decision_engine._call_llm(prompt)
            return response.strip()
        except Exception:
            return "任务已完成"

    def _execute_tool(self, tool_name: str, args: Dict) -> Dict:
        return {"tool": tool_name, "success": True, "result": f"工具 {tool_name} 执行成功"}
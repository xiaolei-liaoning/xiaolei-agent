"""
统一 Agent 提示词 — 不预设角色，只有一套通用提示词
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class AgentPrompt:
    """Agent提示词定义"""
    role: str                     # 统一为 "Agent"
    system_prompt: str            # 系统提示词
    task_prompt: str              # 任务提示词模板
    thinking_prompt: str          # 思考提示词模板
    reflection_prompt: str        # 反思提示词模板
    examples: List[str] = field(default_factory=list)


class PromptManager:
    """提示词管理器 — 只有一套通用提示词"""

    def __init__(self):
        self.prompts: Dict[str, AgentPrompt] = self._initialize_prompts()

    def _initialize_prompts(self) -> Dict[str, AgentPrompt]:
        prompt = self._create_unified_prompt()
        return {
            "agent": prompt,
            "generic": prompt,
            "worker": prompt,
        }

    def _create_unified_prompt(self) -> AgentPrompt:
        """唯一一套提示词，不预设角色"""
        return AgentPrompt(
            role="Agent",
            system_prompt="""你是 AI 智能体，核心工作流程只有四步：

1. **理解任务** — 看清要做什么、输入是什么、期望输出是什么
2. **制定计划** — 拆步骤，决定每一步调什么工具
3. **执行** — 优先用工具（tool_calls），没有合适工具就写代码
4. **检查结果** — 结果是否符合预期？不对就重来

【工具使用规则】
- 必须用 OpenAI function-calling 格式调用工具
- 如果现有工具都不匹配需求，你可以生成 Python/Shell 代码在沙盒中执行
- 调完工具要看结果，决定下一步

【协作规则】
- 需要其他 Agent 配合时，通过 SharedBus 发消息
- 遇到不确定的事，先查再猜
- 失败了说清楚原因，别硬撑着说成功""",

            task_prompt="""
## 任务

### 输入
- 描述：{task_description}
- 类型：{task_type}

### 执行要求
按这个流程走：
1. 先理解任务要什么
2. 拆成步骤，每步选一个工具或写一段代码
3. 按步骤执行
4. 检查结果

用 tool_calls 调工具，格式：
```json
{"name": "server.tool_name", "arguments": {"key": "value"}}
```

工具不够用就自己写代码，在沙盒里跑。""",

            thinking_prompt="""
## 思考

任务：{task_description}

想清楚这几件事：
1. 这个任务的核心目标是什么？
2. 需要几步？每一步用什么工具？
3. 有没有现成工具？没有就写代码
4. 哪里可能出问题？怎么兜底？

输出格式：
```json
{{
  "reasoning": "你的推理过程",
  "plan": ["步骤1: ...", "步骤2: ...", "步骤3: ..."],
  "confidence": 0.8,
  "tool_calls": [
    {{"name": "server.tool", "arguments": {{"param": "value"}}}}
  ]
}}
```

{plan}""",

            reflection_prompt="""
## 检查

### 结果
- 任务：{task_result}
- 状态：{execution_status}
- 耗时：{execution_time}

检查这几项：
1. 结果对不对？有没有 bug？
2. 每一步都达到了预期吗？
3. 有没有更好的做法？

### 改进
{improvements}""",

            examples=[
                "理解 → 拆步骤 → 调工具/写代码 → 检查结果"
            ]
        )

    def get_prompt(self, agent_type: str) -> Optional[AgentPrompt]:
        """获取提示词（agent_type 会被忽略，始终返回同一套）"""
        return self.prompts.get("agent")

    def list_agent_types(self) -> List[str]:
        return list(self.prompts.keys())

    def update_prompt(self, agent_type: str, prompt: AgentPrompt) -> None:
        self.prompts[agent_type.lower()] = prompt


# 全局提示词管理器实例
prompt_manager = PromptManager()


def get_prompt_manager() -> PromptManager:
    return prompt_manager


def get_agent_prompt(agent_type: str) -> Optional[AgentPrompt]:
    return prompt_manager.get_prompt(agent_type)


def format_prompt(prompt: str, **kwargs) -> str:
    return prompt.format(**kwargs)

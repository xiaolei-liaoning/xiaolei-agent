"""
SubagentProfile — 子 Agent 类型定义

每个 SubagentProfile 定义了一种 agentType 的配置：
  - 模型（model）
  - 角色提示（personality + role）
  - 最大 ReAct 轮数（max_rounds）
  - 工具白名单（allowed_tools）

WorkflowRuntime 的 agent() 根据 agentType 查注册表，
将 profile 属性合并到 opts 后委托给 orchestrator.agent()。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SubagentProfile:
    """子 Agent 类型定义

    决定 agent() 用什么模型、什么角色、多少轮次去执行。
    为空则继承调用方默认值。
    """

    name: str                               # 唯一标识 —— "explorer", "analyst", "coder"
    description: str = ""                   # 用途说明，用于文档和自动匹配
    model: str = ""                         # 模型覆盖，空 = 继承 workflow 默认

    # ── 角色/个性注入 ──
    personality: str = ""                   # 注入 WorkAgent.personality
    role: str = ""                          # 注入 WorkAgent.role → system_prompt_for_role()

    # ── 执行限制 ──
    allowed_tools: Optional[List[str]] = None   # 工具白名单，None = 全部可用
    max_rounds: int = 10                        # ReAct 最大轮次
    disallowed_tools: List[str] = field(default_factory=list)  # 拒绝的工具

    # ── 权限/行为 ──
    permission_mode: str = "default"        # 权限模式

    def to_opts(self) -> Dict:
        """转为 orchestrator.agent() 的 opts 字典"""
        opts: Dict = {}
        if self.model:
            opts["model"] = self.model
        if self.personality:
            opts["personality"] = self.personality
        if self.role:
            opts["role"] = self.role
        if self.max_rounds:
            opts["max_rounds"] = self.max_rounds
        return opts

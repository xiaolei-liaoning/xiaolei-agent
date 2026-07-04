"""向后兼容 shim：把 core.agent_v1.* 路由到 core.agent_system.*

V1→V2: V1 兼容层。仅做 import 重定向到 agent_system.py。
  V2 的 unified_agent.run_unified(mode="leader") 是此文件的替代方案。

保留原因: 测试依赖 (tests/test_v1_e2e_integration.py 的 14 处 import)。
  删除前需确保所有 from core.agent_v1 import * 已迁移到 V2 路径。

修复 tests/test_v1_e2e_integration.py 的 14 处 broken import。
"""
from core.agent_system import (
    LLMAgent, AgentRole, AgentMessage, LeaderAgent, V1LeaderPool,
)
from core import agent_system as _m

# 暴露 __all__：agent_system 没 __all__，用 dir() 过滤私有
__all__ = [name for name in dir(_m) if not name.startswith('_')]

# 别名：把 _modules 当成 agent_system 模块本身（部分测试用 M.X 访问）
_modules = _m

# 重导出所有公开对象
from core.agent_system import *  # noqa: F401,F403
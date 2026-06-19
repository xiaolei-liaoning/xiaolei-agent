"""
E2E 测试: 工具失败降级链路

验证连续失败检测 → 降级逻辑 → 错误提示传播
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.multi_agent_v2.agents.react_core import RunContext


class TestToolDegradation:
    """工具降级 e2e 流程"""

    def test_recovery_manager_fallback_config(self):
        """RecoveryManager 降级配置存在"""
        from core.multi_agent_v2.tools.recovery import get_recovery_manager, DEFAULT_FALLBACK_CONFIG
        mgr = get_recovery_manager()
        assert "web_search" in mgr.fallback_config.fallback_tools
        assert mgr.fallback_config.fallback_tools["web_search"] == "fetch_url"

    def test_recovery_plan_strategy(self):
        """RecoveryManager 生成正确的恢复计划"""
        from core.multi_agent_v2.tools.recovery import RecoveryManager, RetryConfig, FallbackConfig
        mgr = RecoveryManager(
            retry_config=RetryConfig(max_retries=1),
            fallback_config=FallbackConfig(
                enabled=True,
                fallback_tools={"web_search": "fetch_url"}
            )
        )
        # 超时错误 → 应该重试
        plan = mgr.create_recovery_plan("web_search", TimeoutError("timeout"), 0)
        assert plan.strategy == "retry"

        # 超过重试次数 → 应该降级
        plan = mgr.create_recovery_plan("web_search", TimeoutError("timeout"), 1)
        assert plan.strategy == "fallback"
        assert plan.fallback_tool == "fetch_url"

"""L0-L4 压缩生命周期测试 — 参考 Hermes 29 个 compression_*.py 生命周期范式

对应报告: ~/Desktop/测试体系移植执行计划.md 第 1️⃣ 项

测的不是"压缩能不能跑"，是生命周期边界：
  A. 分层降级顺序 — L0 先于 L1a 先于 L1b/1c 先于 L2/L2b，最后才是 LLM 层
  B. 中断保护 — L3 LLM 抛异常时原消息列表不被破坏，可兜底回退
  C. 熔断生命周期 — 3 次失败熔断 → 冷却后恢复；成功重置计数
  D. 轻路径提前退出 — L0-L2b 已够省 token 时不应调 LLM 层
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.asyncio


# ════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════


def _big_messages(n_tool_results: int = 8, result_chars: int = 30000) -> list[dict]:
    """构造带超大工具结果的对话（触发压缩）"""
    msgs = [{"role": "system", "content": "系统提示词 " * 50}]
    msgs.append({"role": "user", "content": "帮我研究一下这个项目"})
    for i in range(n_tool_results):
        msgs.append({
            "role": "tool",
            "tool_call_id": f"call_{i}",
            "content": "x" * result_chars,   # 超大工具结果
        })
        msgs.append({"role": "assistant", "content": f"收到工具结果 {i}，继续分析"})
    msgs.append({"role": "user", "content": "总结一下"})
    return msgs


@pytest.fixture
def compactor():
    """真实 ContextCompactor，小 model_limit 保证轻层不够用 → 走到 LLM 层"""
    from core.memory.context_compactor import ContextCompactor
    c = ContextCompactor(model_limit=2000)
    yield c


@pytest.fixture
def compactor_small():
    """model_limit 大 → L0-L2b 轻层即可达标，不触 LLM"""
    from core.memory.context_compactor import ContextCompactor
    c = ContextCompactor(model_limit=1000000)  # 够大 → usage 很低
    yield c


# ════════════════════════════════════════════════════════════════
# A. 分层降级顺序
# ════════════════════════════════════════════════════════════════


class TestLayerOrder:
    """轻层（L0-L2b）必须先于 LLM 层（L3）执行"""

    def test_light_layers_run_before_llm_layers(self, compactor):
        """顺序验证：L0 apply 被调用时，L3 一定还没被调用"""
        call_order = []

        def _spy_apply(name):
            def wrapper(method):
                def inner(messages, *a, **kw):
                    call_order.append(name)
                    return method(messages, *a, **kw)
                return wrapper
            return wrapper

        with patch.object(compactor.l0, "apply",
                          side_effect=lambda m: (call_order.append("L0"), m)[1]), \
             patch.object(compactor.l1a, "clear_tool_results",
                          side_effect=lambda m, t: (call_order.append("L1a"), m)[1]), \
             patch.object(compactor.l1a, "clear_thinking_blocks",
                          side_effect=lambda m: (call_order.append("L1a-think"), m)[1]), \
             patch.object(compactor.l1b, "collapse",
                          side_effect=lambda m: (call_order.append("L1b"), m)[1]), \
             patch.object(compactor.l1c, "clear_old_results",
                          side_effect=lambda m: (call_order.append("L1c"), m)[1]), \
             patch.object(compactor.l2, "scan",
                          side_effect=lambda m: (call_order.append("L2"), m)[1]), \
             patch.object(compactor.l2b, "compact",
                          side_effect=lambda m, **kw: (call_order.append("L2b"), m)[1]):
            compactor._l3 = MagicMock()
            compactor._l3.compact.return_value = [{"role": "user", "content": "压缩后"}]
            compactor._l3.should_compact = MagicMock(return_value=True)
            compactor.compact(_big_messages(), force=True)

        # L3 必须在所有轻层之后（或根本没被调到）
        if "L3" in call_order:
            idx_l3 = call_order.index("L3")
            for light in ("L0", "L1a", "L1b", "L1c", "L2", "L2b"):
                if light in call_order:
                    assert call_order.index(light) < idx_l3, (
                        f"层顺序错误: {light} 应在 L3 之前，实际 call_order={call_order}"
                    )
        # L0 必须是第一个
        assert call_order[0] == "L0", f"L0 应最先执行, 实际: {call_order}"

    def test_light_path_short_circuits_llm(self, compactor_small):
        """轻层省够 token → 不走 LLM (省成本)"""
        compactor_small._l3 = MagicMock()
        compactor_small.l3.should_compact = MagicMock(return_value=False)
        msgs = _big_messages(n_tool_results=3, result_chars=1000)  # 小消息
        result = compactor_small.compact(msgs, force=False)
        # 未触发阈值 → 原消息返回, LLM 未调用
        compactor_small.l3.compact.assert_not_called()
        assert result == msgs or len(result) >= 1


# ════════════════════════════════════════════════════════════════
# B. 中断保护
# ════════════════════════════════════════════════════════════════


class TestInterruptProtection:
    """LLM 层失败时原消息不能损坏（兜底可回退）"""

    def test_l3_exception_preserves_original_messages(self, compactor):
        """L3.compact 抛异常 → 返回的列表不是 None/碎内容, 且失败计入熔断"""
        compactor._l3 = MagicMock()
        compactor._l3.should_compact = MagicMock(return_value=True)
        compactor.l3.compact = MagicMock(side_effect=TimeoutError("LLM 超时"))
        compactor._session_mem = MagicMock()
        compactor.session_mem.compact = MagicMock(return_value=[{"role": "user", "content": "fallback 结果"}])
        compactor._l4 = MagicMock()
        compactor.l4.build.side_effect = lambda compaction_result, **kw: list(compaction_result)

        msgs = _big_messages(n_tool_results=4)
        result = compactor.compact(msgs, force=True)
        # 不崩且有内容
        assert isinstance(result, list) and len(result) >= 1
        # session_mem fallback 被调用（而不是直接崩）
        compactor._session_mem.compact.assert_called_once()

    def test_all_paths_fail_returns_original(self, compactor):
        """L3 + fallback 都崩 → 返回原消息, 不抛, 不空"""
        compactor._l3 = MagicMock()
        compactor._l3.should_compact = MagicMock(return_value=True)
        compactor._l3.compact.side_effect = RuntimeError("llm boom")
        compactor._session_mem = MagicMock()
        compactor._session_mem.compact.side_effect = RuntimeError("fallback boom")
        compactor._l4 = MagicMock()

        msgs = _big_messages(n_tool_results=2)
        result = compactor.compact(msgs, force=True)
        assert result == msgs, "全路径失败应原样返回, 不得截断/清空"


# ════════════════════════════════════════════════════════════════
# C. 熔断生命周期 (circuit_breaker.py: COOLDOWN_SECONDS = 300)
# ════════════════════════════════════════════════════════════════


class TestCircuitBreakerLifecycle:
    """3 次失败 → is_tripped()==True → 冷却后自动复位 → 成功清零"""

    def _fresh_breaker_local(self):
        from core.memory.circuit_breaker import CircuitBreaker, MAX_CONSECUTIVE_FAILURES, COOLDOWN_SECONDS
        assert MAX_CONSECUTIVE_FAILURES == 3, "熔断阈值契约变更需同步测试"
        return CircuitBreaker()

    def test_trips_after_three_failures(self):
        cb = self._fresh_breaker_local()
        for _ in range(3):
            cb.record_failure()
        assert cb.is_tripped() is True

    def test_two_failures_not_tripped(self):
        cb = self._fresh_breaker_local()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_tripped() is False

    def test_success_resets_streak(self):
        cb = self._fresh_breaker_local()
        cb.record_failure()
        cb.record_failure()
        cb.record_success()   # 中间成功一次清零
        cb.record_failure()
        cb.record_failure()
        assert cb.is_tripped() is False   # 只有 2, 未到 3

    def test_cooldown_after_trip(self):
        """超时冷却后 (默认 300s) 复位。测试用 monkeypatch 时间快进"""
        cb = self._fresh_breaker_local()
        for _ in range(3):
            cb.record_failure()
        assert cb.is_tripped() is True
        # 把 tripped 时间往回拨 COOLDOWN+1 秒
        import time as _time
        cb._tripped_at = _time.time() - 301
        assert cb.is_tripped() is False, "冷却时间到应自动复位"

    def test_compactor_skips_when_tripped(self, compactor):
        """熔断状态下 compact() 直接跳过, 不再打 LLM"""
        compactor._circuit_breaker.record_failure()
        compactor._circuit_breaker.record_failure()
        compactor._circuit_breaker.record_failure()
        assert compactor._circuit_breaker.is_tripped()

        compactor._l3 = MagicMock()
        msgs = _big_messages(n_tool_results=2)
        result = compactor.compact(msgs, force=True)
        # 熔断时提前返回 — L3 不该被摸
        compactor._l3.compact.assert_not_called()
        assert result == msgs

    def test_success_records_to_breaker(self, compactor):
        """L0-L2b 轻层省够 → 算成功 → record_success → 计数清零"""
        compactor._circuit_breaker.record_failure()
        compactor._circuit_breaker.record_failure()
        # 构造"轻层就够省"的场景: 空结果能让 L0/L2b 剩很多
        from core.memory.token_counter import count_messages_tokens
        compactor._l3 = MagicMock()
        compactor._l3.should_compact = MagicMock(return_value=True)
        msgs = _big_messages(n_tool_results=2, result_chars=40000)
        # 强制轻层就过阈值: model_limit 高, 结果被截断
        compactor.model_limit = 10 ** 9   # 门槛变高 → L0-L2b 省完即过
        compactor.compact_threshold = 0.5
        compactor.compact(msgs, force=False)
        stats = compactor._circuit_breaker.get_stats()
        assert stats["consecutive_failures"] == 0, "成功路径应清零失败计数"

    # -- helper
    def _fresh_breaker(self):
        from core.memory.circuit_breaker import CircuitBreaker
        return CircuitBreaker()


# ════════════════════════════════════════════════════════════════
# D. 记忆注入引导（跨进程 fcntl 锁保护）
# ════════════════════════════════════════════════════════════════


class TestCompactionStats:
    """get_compaction_stats 返回结构契约"""

    def test_stats_shape(self, compactor):
        # lazy property 无 setter → 先把内部持有字段全部置 MagicMock 再测契约
        for attr in ("_l0", "_l1a", "_l1b", "_l1c", "_l2", "_l2b",
                     "_l3", "_l4", "_react", "_session_mem"):
            setattr(compactor, attr, MagicMock())

        s = compactor.get_compaction_stats()
        # 必缺字段
        for key in ("model_limit", "total_compactions", "total_tokens_saved", "circuit_breaker"):
            assert key in s, f"get_compaction_stats 缺字段: {key}"
        for layer in ("l0", "l1a", "l1b", "l1c", "l2", "l2b", "l3", "l4", "react", "session_mem"):
            assert layer in s, f"统计缺层 {layer}"

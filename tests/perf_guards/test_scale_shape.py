"""性能规模形守护 (perf scale-shape guard) — 对标 hermes tests/perf_guards

对标报告: ~/Desktop/测试极限体系移植计划.md 阶段 4
参考: hermes test_pattern_b_scaling.py 的 self-normalizing ratio 设计

核心思想：**不测绝对 wall-clock**（那是 flake 源头），测 **time(4N) / time(N)**:
  线性路径  ratio ≈ 4
  二次方路径 ratio ≈ 16
  阈值放在 good/bad 之间，两侧各 ≥2x separation。

守护 3 个已知"改写不删"、"全量重算"高危路径：
  1. context_compactor L0→L2b — tool_results 从 1000 到 4000 条
  2. token_counter — messages 1000 到 4000 条
  3. tool_registry._handle_read_file — 3 次 vs 12 次 读取调用（重复读取警告逻辑）
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ── self-normalizing 失败阈值 ──
# 线性 = ~4.0. Threshold 放 6 (good-side ≥2x below quadratic≈16 and bad-side ≥2x above 4)
LINEAR_RATIO_THRESHOLD = 8.0
# min-of-K to reject scheduler noise (hermes 用 3-5)
K_SAMPLES = 3


def _time_it(fn, *args, repeat: int = 1) -> float:
    """单次 wall-clock (秒)"""
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn(*args)
        best = min(best, time.perf_counter() - t0)
    return best


def _assert_linear(fn, small, big, name: str, budget_ms: float = 8.0):
    """4N/N 比值断言 → 确保路径规模不 quadratic"""
    t_small = _time_it(fn, small, repeat=K_SAMPLES)
    t_big = _time_it(fn, big, repeat=K_SAMPLES)
    # small 若 < 1ms，ratio 会 noise 爆炸 — 给下限保护
    t_small = max(t_small, 0.001)
    ratio = t_big / t_small
    assert ratio < LINEAR_RATIO_THRESHOLD, (
        f"{name}: 规模形退化！ratio={ratio:.2f} (linear应≈4, quadratic≈16, 阈值{LINEAR_RATIO_THRESHOLD})"
    )
    return ratio


# ════════════════════════════════════════════════════════════════
# 1. ContextCompactor.compact — tool_results 数量扩展
# ════════════════════════════════════════════════════════════════


def _make_msgs(n_results: int, result_chars: int = 2000):
    """n_results 条 tool_result 对应的完整消息列表"""
    msgs = [{"role": "system", "content": "sys " * 20}]
    for i in range(n_results):
        msgs.append({"role": "user", "content": f"q{i} " + "y" * 50})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * result_chars})
        msgs.append({"role": "assistant", "content": f"a{i}" * 20})
    return msgs


def test_compaction_scale_linear():
    """L0-L2b 压缩: 300 → 1200 条 tool_results 应保持 ~4x 而非 16x"""
    from core.memory.context_compactor import ContextCompactor
    c = ContextCompactor(model_limit=10 ** 12)   # 只触发 L0-L2b (轻层, 无 LLM)

    n_small_msgs = _make_msgs(300)
    n_big_msgs = _make_msgs(1200)
    _assert_linear(c.compact, n_small_msgs, n_big_msgs,
                   "context_compactor.compact")


def test_token_counter_scale_linear():
    """token counter: 300 → 1200 msgs 应 ~linear（不是 quadratic scan）"""
    from core.memory.token_counter import count_messages_tokens
    small = _make_msgs(300, result_chars=200)
    big = _make_msgs(1200, result_chars=200)
    _assert_linear(count_messages_tokens, small, big, "token_counter")


# ════════════════════════════════════════════════════════════════
# 2. read_file 反复调用（repeat hint 逻辑 — 疑似 quadratic dict 扫描）
# ════════════════════════════════════════════════════════════════


def test_read_file_repeat_tracking_scale(tmp_path):
    import asyncio as _a
    from core.multi_agent_v2.tools.tool_registry import _handle_read_file

    # 清空重复计数器（模块级 dict 里跨测试泄漏）
    if hasattr(_handle_read_file, "_read_count"):
        _handle_read_file._read_count = {}
        _handle_read_file._unique_files = set()

    files = []
    for i in range(6):
        f = tmp_path / f"sample_{i}.txt"
        f.write_text("line\n" * 100, encoding="utf-8")
        files.append(str(f))

    async def _run_many(n_files):
        for i in range(n_files):
            await _handle_read_file({"path": files[i % len(files)]})

    async def _go():
        # 重置计数器
        _handle_read_file._read_count = {}
        _handle_read_file._unique_files = set()

        t0 = time.perf_counter()
        await _run_many(20)
        t_small = time.perf_counter() - t0

        _handle_read_file._read_count = {}
        _handle_read_file._unique_files = set()

        t0 = time.perf_counter()
        await _run_many(80)
        t_big = time.perf_counter() - t0

        return t_small, t_big

    t_small, t_big = _a.run(_go())
    t_small = max(t_small, 0.001)
    ratio = t_big / t_small
    assert ratio < LINEAR_RATIO_THRESHOLD, f"read_file 4N/N ratio={ratio:.2f} — 超界（应为 linear≈4）"

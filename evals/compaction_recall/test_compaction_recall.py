"""压缩保真度 Recall Eval — CI smoke + 单元级验证（无真 LLM）

验证 eval 管线自身正确性：
  A. transcript loader / synthetic generator 产出合法 messages
  B. compact_by_policy 三策略输出 token 单调递减 (none ≥ light ≥ full not guaranteed, full ≤ light)
  C. format_report 渲染
  D. fake useRouter 端到端跑通 run_eval (不真调用 judge)
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from evals.compaction_recall.runner import (
    compact_by_policy,
    format_report,
    load_transcript,
    make_synthetic_transcript,
    run_eval,
    POLICIES,
)
from core.memory.token_counter import count_messages_tokens


class _FakeRouter:
    """minimal fake LLM — 用于 run_eval smoke"""
    async def simple_chat(self, prompt, temperature=0.0, max_tokens=100, **kw):
        if "金标准" in prompt:
            return "PASS"
        return "tool result 引用模拟"

    def is_available(self):
        return True


def test_synthetic_transcript_shape():
    msgs = make_synthetic_transcript()
    assert len(msgs) >= 10
    roles = {m["role"] for m in msgs}
    assert roles >= {"system", "user", "tool", "assistant"}


def test_compact_none_unchanged():
    msgs = make_synthetic_transcript(rounds=3, msg_per=1, chars=200)
    out = compact_by_policy(msgs, "none")
    assert out == msgs


def test_compact_light_reduces_tokens():
    """light (L0-L2b, 高限额) 必须省 token 而不调 LLM"""
    msgs = make_synthetic_transcript(rounds=10, msg_per=2, chars=20000)
    out = compact_by_policy(msgs, "light")
    before = count_messages_tokens(msgs)
    after = count_messages_tokens(out)
    assert after < before, f"light 应省 token: {before} → {after}"


def test_format_report_shape():
    results = {
        "none":  {"retained_tokens_pct": 100.0, "questions": 10, "recall_pct": 0.0},
        "light": {"retained_tokens_pct": 60.0, "questions": 10, "recall_pct": 80.0},
        "full":  {"retained_tokens_pct": 30.0, "questions": 10, "recall_pct": 75.0},
    }
    text = format_report(results)
    assert "none" in text and "light" in text and "full" in text


def test_run_eval_fake_llm_smoke():
    """端到端跑通 (fake router + 极小 transcript)"""
    transcript = make_synthetic_transcript(rounds=2, msg_per=1, chars=500)
    questions = [{"q": "第0轮做了什么?", "gold": "path_0", "where": "user msg 0"}]
    router = _FakeRouter()
    results = asyncio.run(run_eval(transcript, questions, POLICIES, router))
    for p in POLICIES:
        r = results[p]
        assert "retained_tokens_pct" in r and "recall_pct" in r and "questions" in r
    # fake router 恒 PASS
    assert results["none"]["recall_pct"] == 100.0

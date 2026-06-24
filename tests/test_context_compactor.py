#!/usr/bin/env python3
"""Context compression system tests — 7-layer Claude Code architecture.

Tests the full pipeline:
  L0  ToolResultBudget       — per-message char limit / disk spill
  L1a API-Level Context Mgmt  — clear_tool_uses + clear_thinking
  L1b CollapseReadSearch      — UI-only tracker (messages pass through)
  L1c Time-Based MC           — gap >60min clear
  L2  CachedMicrocompact      — cache edit metadata (no message modification)
  L2b SnipCompact             — independent snip (first-half + last-quarter)
  L3  LLM Compaction          — compactConversation() with PTL retry
  L4  Post-Compact Rebuild    — buildPostCompactMessages with attachments
  +   Circuit Breaker / Reactive Compact / Session Memory Compaction
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory.token_counter import estimate_tokens, count_messages_tokens, get_context_usage
from core.memory.l0_tool_result_budget import L0ToolResultBudget
from core.memory.l1a_api_context_mgmt import L1aApiContextMgmt
from core.memory.l1b_collapse_read_search import CollapseReadSearchManager
from core.memory.l1c_time_based_mc import L1cTimeBasedMicrocompact
from core.memory.l2_cached_microcompact import L2CachedMicrocompact
from core.memory.l2b_snip_compact import L2bSnipCompact
from core.memory.l3_llm_compaction import L3LLMCompaction
from core.memory.l4_post_compact_rebuild import L4PostCompactRebuild
from core.memory.react_compact import ReactCompact
from core.memory.circuit_breaker import CircuitBreaker
from core.memory.session_memory_compaction import SessionMemoryCompaction
from core.memory.context_compactor import ContextCompactor


def test_token_counter():
    print("=== Test 1: Token Counter ===")
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello") > 0
    assert estimate_tokens("你好世界") > 0
    mixed = estimate_tokens("你好世界 hello")
    assert mixed > 0
    print(f"  CJK+ASCII mix: {mixed} tokens")

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮你的？"},
    ]
    total = count_messages_tokens(messages)
    assert total > 0
    print(f"  Message list: {total} tokens")

    usage = get_context_usage(messages, model_limit=8000)
    assert 0 <= usage <= 100
    print(f"  Usage: {usage:.2f}%")
    print("  PASS\n")


def test_l0_tool_result_budget():
    print("=== Test 2: L0 ToolResultBudget ===")
    l0 = L0ToolResultBudget(max_chars=50)
    msgs = [
        {"role": "tool", "name": "bash", "content": "A" * 500},
        {"role": "tool", "name": "read", "content": "short"},
    ]
    result = l0.apply(msgs)
    assert result[0].get("_spill_path"), "Oversized result should be spilled"
    assert not result[1].get("_spill_path"), "Small result should pass through"
    assert result[0]["_spilled"] is True
    stats = l0.get_stats()
    assert stats["budgeted"] == 1
    assert stats["spilled"] == 1
    print(f"  Budgeted: {stats['budgeted']}, Spilled: {stats['spilled']}")
    print("  PASS\n")


def test_l1a_api_context_mgmt():
    print("=== Test 3: L1a API-Level Context Mgmt ===")
    l1a = L1aApiContextMgmt(max_input_tokens=1000, target_input_tokens=200)
    assert not l1a.should_clear(500)
    assert l1a.should_clear(1500)

    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "tool", "content": "A" * 500, "name": "read"},
        {"role": "tool", "content": "B" * 500, "name": "read"},
        {"role": "assistant", "content": "Done"},
    ]
    result = l1a.clear_tool_results(messages, token_count=1500)
    stats = l1a.get_stats()
    print(f"  Clears: {stats['clears']}, Tokens freed: {stats['tokens_freed']}")
    print("  PASS\n")


def test_l1b_collapse_read_search():
    print("=== Test 4: L1b CollapseReadSearch (UI-only) ===")
    l1b = CollapseReadSearchManager()
    messages = [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "read", "arguments": '{"file_path": "a.py"}'}}
        ]},
        {"role": "tool", "content": "content a", "tool_call_id": "c1", "name": "read"},
        {"role": "assistant", "content": "Done"},
    ]
    result = l1b.collapse(messages)
    stats = l1b.get_stats()
    assert len(result) == len(messages), "L1b is UI-only, messages should pass through"
    print(f"  Messages pass through: {len(messages)} → {len(result)}")
    print(f"  Groups tracked: {stats['groups_tracked']}")
    print("  PASS\n")


def test_l1c_time_based_mc():
    print("=== Test 5: L1c Time-Based MC ===")
    import time
    l1c = L1cTimeBasedMicrocompact(enabled=True, gap_threshold_minutes=0.01, keep_recent=2)
    assert not l1c.should_clear(), "No timestamp → no clear"
    l1c.update_assistant_timestamp(time.time() - 1)
    assert l1c.should_clear(), ">threshold gap → should clear"

    messages = [
        {"role": "system", "content": "system"},
        {"role": "tool", "content": "A" * 500, "name": "read"},
        {"role": "tool", "content": "B" * 500, "name": "read"},
        {"role": "tool", "content": "C" * 500, "name": "read"},
        {"role": "assistant", "content": "Done"},
    ]
    result = l1c.clear_old_results(messages)
    stats = l1c.get_stats()
    assert stats["clears"] > 0
    print(f"  Clears: {stats['clears']}, Tokens freed: {stats['tokens_freed']}")
    print("  PASS\n")


def test_l2_cached_microcompact():
    print("=== Test 6: L2 CachedMicrocompact ===")
    l2 = L2CachedMicrocompact()
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    result = l2.scan(msgs)
    edits = result[0].get("_cache_edits", [])
    print(f"  Cache edits: {len(edits)}")
    assert any(e["target"] == "system" for e in edits), "System should be cached"
    # Verify messages are NOT modified
    assert result[1]["content"] == "Hi", "L2 should not modify message content"
    print("  PASS\n")


def test_l2b_snip_compact():
    print("=== Test 7: L2b SnipCompact ===")
    l2b = L2bSnipCompact(max_chars=50, preserve_last_n_turns=2)
    messages = [
        {"role": "tool", "content": "A" * 500, "name": "bash"},
        {"role": "tool", "content": "B" * 500, "name": "bash"},
        {"role": "tool", "content": "C" * 500, "name": "bash"},
        {"role": "assistant", "content": "Done"},
    ]
    result = l2b.compact(messages)
    stats = l2b.get_stats()
    assert stats["trimmed_count"] > 0
    assert stats["chars_snipped"] > 0
    assert len(result[0]["content"]) < 500, "Message should be snipped"
    print(f"  Trimmed: {stats['trimmed_count']}, Chars snipped: {stats['chars_snipped']}")
    print("  PASS\n")


def test_l3_llm_compaction():
    print("=== Test 8: L3 LLM Compaction ===")
    l3 = L3LLMCompaction(model_limit=8000, compact_threshold=0.5)
    assert not l3.should_compact(2000)
    assert l3.should_compact(5000)

    # Test PTL retry truncation
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "M1"},
        {"role": "assistant", "content": "R1"},
        {"role": "user", "content": "M2"},
        {"role": "assistant", "content": "R2"},
    ]
    truncated = l3._truncate_head_for_ptl_retry(messages)
    assert truncated is not None
    assert len(truncated) < len(messages)
    print(f"  PTL retry: {len(messages)} → {len(truncated)} messages")
    print("  PASS\n")


def test_l4_post_compact_rebuild():
    print("=== Test 9: L4 Post-Compact Rebuild ===")
    l4 = L4PostCompactRebuild()

    compaction_result = {
        "boundary_marker": {"role": "system", "content": "[compacted]", "compact_metadata": {}},
        "summary_messages": [{"role": "user", "content": "Summary text", "is_compact_summary": True}],
        "messages_to_keep": [{"role": "assistant", "content": "Last turn"}],
        "pre_compact_token_count": 100,
        "post_compact_token_count": 50,
        "summary_text": "Summary text",
    }

    result = l4.build(
        compaction_result=compaction_result,
        recent_files=[{"path": "/tmp/test.py", "content": "print('hi')", "timestamp": 1000}],
        skills=[{"name": "test_skill", "path": "/skills/test.md", "content": "# Test skill", "invoked_at": 1000}],
    )
    assert len(result) >= 3
    # Check order: boundary → summary → messages_to_keep → attachments
    assert result[0].get("compact_metadata") is not None, "First should be boundary"
    assert result[1].get("is_compact_summary"), "Second should be summary"
    assert "Restored file" in result[3].get("content", ""), "Should have file attachment"
    info = l4.get_rebuild_info()
    print(f"  Rebuilds: {info['rebuilds']}, Files: {info['files_restored']}, Skills: {info['skills_reinjected']}")
    print("  PASS\n")


def test_circuit_breaker():
    print("=== Test 10: Circuit Breaker ===")
    cb = CircuitBreaker(max_failures=3)
    assert not cb.is_tripped()
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.is_tripped(), "Should trip after 3 failures"
    print(f"  Tripped: {cb.is_tripped()}, Consecutive: {cb.consecutive_failures}")
    cb.record_success()
    assert not cb.is_tripped(), "Should reset after success"
    print(f"  Reset: {cb.is_tripped()}")
    stats = cb.get_stats()
    print(f"  Total failures: {stats['total_failures']}")
    print("  PASS\n")


def test_session_memory_compaction():
    print("=== Test 11: Session Memory Compaction ===")
    sm = SessionMemoryCompaction()
    messages = [
        {"role": "user", "content": "帮我写一个快速排序"},
        {"role": "assistant", "content": "def quicksort(arr): return arr"},
        {"role": "tool", "name": "bash", "content": "Test output"},
        {"role": "user", "content": "加一个测试"},
    ]
    result = sm.compact(messages)
    assert result["summary_text"]
    assert len(result["summary_messages"]) > 0
    print(f"  Summary: {result['summary_text'][:80]}...")
    print("  PASS\n")


def test_context_compactor():
    print("=== Test 12: ContextCompactor (7-layer) ===")
    cc = ContextCompactor(model_limit=8000)
    small = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    result = cc.compact(small)
    stats = cc.get_compaction_stats()
    print(f"  Small msgs: {len(small)} → {len(result)}")
    # Large message set to trigger LLM compaction fallback
    large = [{"role": "system", "content": "system"}]
    for i in range(30):
        large.append({"role": "user", "content": f"Q{i}: " + "x" * 300})
        large.append({"role": "assistant", "content": f"A{i}: " + "y" * 300})
    result_large = cc.compact(large, force=True)
    stats_large = cc.get_compaction_stats()
    print(f"  Large msgs: {len(large)} → {len(result_large)}")
    print(f"  Total compactions: {stats_large['total_compactions']}")
    assert result_large[0]["role"] == "system", "System prompt should be preserved"
    user_msgs = [m for m in result_large if m["role"] == "user"]
    assert len(user_msgs) > 0, "Should preserve user messages"
    print("  PASS\n")


def test_react_compact():
    print("=== Test 13: React Compact ===")
    react = ReactCompact()
    msgs = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]
    result = react.compact(msgs, error_message="prompt_too_long")
    stats = react.get_stats()
    print(f"  Reactive compacts: {stats['reactive_compacts']}")
    print(f"  Total tokens saved: {stats['total_tokens_saved']}")
    print("  PASS\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Context Compression Tests (7-layer architecture)")
    print("=" * 60 + "\n")

    tests = [
        ("Token Counter", test_token_counter),
        ("L0 ToolResultBudget", test_l0_tool_result_budget),
        ("L1a API Context Mgmt", test_l1a_api_context_mgmt),
        ("L1b CollapseReadSearch", test_l1b_collapse_read_search),
        ("L1c Time-Based MC", test_l1c_time_based_mc),
        ("L2 CachedMicrocompact", test_l2_cached_microcompact),
        ("L2b SnipCompact", test_l2b_snip_compact),
        ("L3 LLM Compaction", test_l3_llm_compaction),
        ("L4 Post-Compact Rebuild", test_l4_post_compact_rebuild),
        ("Circuit Breaker", test_circuit_breaker),
        ("Session Memory Compaction", test_session_memory_compaction),
        ("ContextCompactor", test_context_compactor),
        ("React Compact", test_react_compact),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    sys.exit(1 if failed else 0)

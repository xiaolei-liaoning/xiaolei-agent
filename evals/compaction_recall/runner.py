"""压缩保真度 Recall Eval — 量化 7 层压缩"损失多少记忆"

响应报告:
    ~/Desktop/测试极限体系移植计划.md 阶段 2

对标: hermes evals/compaction/{runner,report}.py

核心主张：小雷版 L0-L4 七层压缩比轻层 (L0-L2b) 或无压缩更能"省得聪明"——
	省的 token 更多, 且信息损失更少。用真实 recall 说话, 不是感觉。

## Manual opt-in (需要真 LLM):
    XIAOLEI_REAL_LLM=1 python evals/compaction_recall/runner.py \
        --transcript ~/.xiaolei/history/default_user/2026-09.jsonl \
        --questions 10 --policies none,light,full --out evals/compaction_recall/results/run1

## 用 fake transcript / fake LLM (CI smoke, 无 API key):
    python -m pytest evals/compaction_recall/test_compaction_recall.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from core.memory.context_compactor import ContextCompactor
from core.memory.token_counter import count_messages_tokens


# ════════════════════════════════════════════════════════════════
# 策略矩阵
# ════════════════════════════════════════════════════════════════

POLICIES = ["none", "light", "full"]   # 无压缩 / 仅轻层 L0-L2b / 全链 7层

MODEL_LIMIT_OVERRIDES: Dict[str, Optional[int]] = {
    # policy → ContextCompactor model_limit (fake, 只为跑不同路径)
    "none":  None,            # 不跑压缩
    "light": 10 ** 12,         # 门槛极低 → 轻层 L0-L2b 就够省 (e.g. usage ≤ threshold 但高限额)
    "full":  8000,             # 官方默认 ⇒ 触发 LLM 层
}


# ════════════════════════════════════════════════════════════════
# Transcript 处理
# ════════════════════════════════════════════════════════════════


def load_transcript(path: Path, max_tokens: int = 60000) -> List[Dict[str, Any]]:
    """读 ~/.xiaolei/history JSONL → OpenAI chat 格式 messages"""
    if not path.exists():
        raise FileNotFoundError(f"transcript 不存在: {path} (需先从 ~/.xiaolei/history 复制) ")
    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = row.get("role") or ("user" if row.get("kind") == "user" else "assistant")
        content = row.get("content") or row.get("text") or ""
        msgs.append({"role": role, "content": content})
    # 截到 max_tokens 等量 (按体量粗截)
    out, tok = [], 0
    for m in reversed(msgs):
        out.insert(0, m)
        tok += count_messages_tokens([m])
        if tok >= max_tokens:
            break
    return out


def make_synthetic_transcript(rounds: int = 30, msg_per: int = 4, chars: int = 600) -> List[Dict[str, Any]]:
    """CI smoke 用可复现假 transcript"""
    msgs = [{"role": "system", "content": "你是小雷版agent。"}]
    for i in range(rounds):
        msgs.append({"role": "user", "content": f"第{i}轮: 请读文件 path_{i}.py 里的函数 foo_{i}"})
        for j in range(msg_per):
            msgs.append({
                "role": "tool",
                "tool_call_id": f"call_{i}_{j}",
                "content": f"file_path_{i}_line_{j}: " + "x" * chars,
            })
            msgs.append({"role": "assistant", "content": f"读到了 path_{i}.py 第{j}段, 确认" })
    msgs.append({"role": "user", "content": "总结一下做了什么"})
    return msgs


# ════════════════════════════════════════════════════════════════
# 考题生成 (真 LLM) + 回答 (真 LLM) + judge (真 LLM)
# ════════════════════════════════════════════════════════════════

QUESTION_PROMPT = """从下面的 agent 会话 transcript 里生成 {n} 道事实性回忆题。

考察点（会被压缩掉的区域）：
- 具体的文件路径、PR号、报错字符串、commit 标题
- 决定和理由 / 用户指令 / 最终结果
- 遍布整个 transcript（早/中/晚全部覆盖）
- 答案必须**字面上**出现在 transcript 里

返回严格 JSON 数组: [{{"q": "...", "gold": "...", "where": "引用原文的位置"}}]

TRANSCRIPT:
{transcript}
"""

ANSWER_PROMPT = """基于下面的 context 回答。context 可能已被压缩，信息可能丢失——
如果 context 里找不到答案，就说"不知道"。不要猜。

CONTEXT:
{context}

问题: {q}
"""

JUDGE_PROMPT = """用户问: {q}
金标准答案: {gold}
被测答案: {answer}

被测答案是否包含金标准的核心事实? 回 "PASS" 或 "FAIL:<一句话原因>" (只回一行)
"""

RECOGNIZED_FAIL_TOKEN = "FAIL"


async def generate_questions(
    transcript: List[Dict[str, Any]],
    n: int,
    router,
) -> List[Dict[str, Any]]:
    """LLM 生成 n 道 recall 题"""
    text = "\n".join(
        f"[{m['role']}] {str(m.get('content', ''))[:200]}" for m in transcript
    )[:30000]
    prompt = QUESTION_PROMPT.format(n=n, transcript=text)
    resp = await router.simple_chat(prompt, temperature=0.2, max_tokens=2000)
    # 从 resp 提取 JSON 数组（LLM 可能带前后缀）
    import json as _json
    import re
    m = re.search(r"^\s*\[.*\]\s*$", resp.strip(), re.DOTALL)
    raw = m.group(0) if m else (resp.split("[", 1)[1].rsplit("]", 1)[0] and f"[{resp.split('[',1)[1].rsplit(']',1)[0]}]" if "[" in resp else "")
    if not raw:
        return []
    try:
        qs = _json.loads(raw)
        return [{"q": x.get("q", ""), "gold": x.get("gold", ""), "where": x.get("where", "")} for x in qs][:n]
    except _json.JSONDecodeError:
        return []


async def answer_with_context(q: str, compressed_text: str, router) -> str:
    prompt = ANSWER_PROMPT.format(context=compressed_text[:15000], q=q)
    resp = await router.simple_chat(prompt, temperature=0, max_tokens=300)
    return resp.strip()[:400]


async def judge_answer(q: str, gold: str, answer: str, router) -> bool:
    resp = await router.simple_chat(
        JUDGE_PROMPT.format(q=q, gold=gold, answer=answer),
        temperature=0, max_tokens=30,
    )
    return "PASS" in resp.upper()


# ════════════════════════════════════════════════════════════════
# 压缩策略执行器
# ════════════════════════════════════════════════════════════════


def compact_by_policy(messages: List[Dict], policy: str, real_llm_used: bool = True) -> List[Dict]:
    """policy: none / light / full"""
    if policy == "none":
        return list(messages)
    compactor = ContextCompactor(
        model_limit=MODEL_LIMIT_OVERRIDES[policy] or 8000,
    )
    # light 只用 L0-L2b（绕过 L3/L4）
    if policy == "light":
        return compactor.compact(messages, force=True)   # force 且 model_limit 大, L0-L2b 即过
    return compactor.compact(messages, force=True)


def _to_text(msgs: List[Dict]) -> str:
    return "\n".join(f"[{m.get('role','')}] {str(m.get('content',''))[:400]}" for m in msgs)


# ════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════


async def run_eval(
    transcript: List[Dict],
    questions: List[Dict],
    policies: List[str],
    router,
) -> Dict[str, Any]:
    """一个 transcript × 多策略 → per-policy 打分"""
    results: Dict[str, Any] = {}
    for policy in policies:
        msgs = compact_by_policy(transcript, policy)
        retained_tokens = count_messages_tokens(msgs)
        original_tokens = count_messages_tokens(transcript)
        compressed_text = _to_text(msgs)

        correct, judged = 0, 0
        for qitem in questions:
            answer = await answer_with_context(qitem["q"], compressed_text, router)
            ok = await judge_answer(qitem["q"], qitem["gold"], answer, router)
            judged += 1
            if ok:
                correct += 1
        results[policy] = {
            "retained_tokens_pct": round(100 * retained_tokens / max(1, original_tokens), 1),
            "questions": judged,
            "recall_pct": round(100 * correct / max(1, judged), 1),
        }
    return results


def format_report(results: Dict[str, Any]) -> str:
    lines = ["",
             "═" * 55,
             " 小雷版 L0-L4 压缩保真度 Recall Eval",
             "═" * 55,
             f"  {'策略':<8} {'保留token%':<15} {'recall准确率%':<15}",
             "─" * 55]
    for p, r in results.items():
        q = r.get("questions", 0)
        lines.append(
            f"  {p:<8} {r['retained_tokens_pct']:<15} recall={r['recall_pct']}%  ({q} 题)"
        )
    lines.append("═" * 55)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=False)
    ap.add_argument("--questions", type=int, default=10)
    ap.add_argument("--policies", default="none,light,full")
    ap.add_argument("--out", default="evals/compaction_recall/results/run1")
    ap.add_argument("--synthetic", action="store_true", help="CI smoke: 用假 transcript + fake LLM")
    args = ap.parse_args()

    import asyncio

    async def _go():
        if args.synthetic:
            transcript = make_synthetic_transcript()
        else:
            transcript = load_transcript(Path(args.transcript))

        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if not router or not router.is_available():
            print("❌ 需要真 LLM，配置 API key 后运行", file=sys.stderr)
            sys.exit(2)

        qs = await generate_questions(transcript, args.questions, router)
        if not qs:
            print("考题生成为空", file=sys.stderr)
            sys.exit(2)

        results = await run_eval(transcript, qs, args.policies.split(","), router)
        print(format_report(results))
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(__import__("json").dumps(results, ensure_ascii=False, indent=2))
        print(f"\n💾 写入: {out/'results.json'}")

    asyncio.run(_go())


if __name__ == "__main__":
    main()

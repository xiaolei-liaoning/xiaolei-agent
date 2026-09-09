"""ConversationLedger — 全量对话账本（Hermes 模式）

定位（与 STM/向量库的分工）：
  - STM 短期记忆: 本次会话的"工作台"，可压缩可撕页（B1 会话边界管注入）
  - 向量库:       LLM 提炼后的"有用知识"（偏好/事实/经验）
  - 账本(本文件):  对话原文的"档案室"，append-only 永不删改——
                  STM 撕掉的页、向量库提炼漏掉的细节，这里都翻得回来

存储格式:
  ~/.小雷版小龙虾/history/{user_id}/YYYY-MM.jsonl
  一行一条 JSON: {"ts","session_id","role","content","task"}
  只增不删。按月分文件避免单文件无限膨胀。

读路径:
  search(query, user_id)  → 关键词搜索账本，返回命中条目（含时间/会话/角色）
  recent(user_id, limit)  → 最近 N 条（跨会话回看）

工具入口: tool_registry.search_history → _handle_search_history
"""

import json
import logging
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

HISTORY_ROOT = Path(os.path.expanduser("~/.小雷版小龙虾/history"))

# 单条 content 截断上限——账本是"指路牌"不是"全文转储"，
# 太长的条目（如 2 万字文件写入的 echo）截断存储，需要全文 agent 再 read_file 原产物
MAX_ENTRY_CHARS = 2000


def _safe_user_id(user_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-.@]+", "_", user_id)[:64]


def _ledger_dir(user_id: str) -> Path:
    return HISTORY_ROOT / _safe_user_id(user_id)


def _month_file(user_id: str, dt: Optional[datetime] = None) -> Path:
    dt = dt or datetime.now()
    return _ledger_dir(user_id) / f"{dt.strftime('%Y-%m')}.jsonl"


def _all_ledger_files(user_id: str) -> List[Path]:
    d = _ledger_dir(user_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.jsonl"))


def append_entry(user_id: str, session_id: str, role: str,
                 content: str, task: str = "") -> None:
    """追加一条对话记录到账本（append-only，永不删改）

    失败静默——账本是兜底设施，绝不能因为它挡住主流程。
    """
    if not user_id or not content:
        return
    try:
        d = _ledger_dir(user_id)
        d.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "role": role,
            "content": str(content)[:MAX_ENTRY_CHARS],
            "task": str(task)[:200],
        }
        with open(_month_file(user_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"账本写入失败: {e}")


def _iter_entries(user_id: str, newest_first: bool = False):
    """遍历账本全部条目（按月文件顺序，文件内按行序）"""
    files = _all_ledger_files(user_id)
    if newest_first:
        files = list(reversed(files))
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def search(query: str, user_id: str, limit: int = 10,
           role: str = "") -> List[Dict]:
    """关键词搜索账本（大小写不敏感，多词 AND，BM25 式相关度排序）

    这是 agent "翻老账本" 的主入口——被问"上次说了什么/之前给过什么建议"
    时调 search_history 工具，返回带时间戳和会话 id 的原文条目。

    参考 Hermes hermes_state_search.py 的三件套（简化落地）：
    1. 多词 OR 降级：AND 全命中无结果时，退回"命中词最多"的条目
       （Hermes 教 agent 用 OR——这里直接内置，agent 不用学）
    2. 相关度排序：score = Σ(词频 × IDF) × role权重，替代纯时间倒序，
       治"高频词把真建议挤掉"
    3. 0 命中引导：结果交给 format_hits 输出换词建议（学 Hermes 的
       "No matching sessions found. FTS5 ANDs all terms..."）
    """
    if not query.strip():
        return []
    terms = [t.lower() for t in query.split() if t.strip()]
    if not terms:
        return []

    # ── 第一遍：全量扫描，收集候选 + 计算 IDF ──
    # （3000 条 ~2ms 级，线性扫可承受；真到 GB 级再考虑 FTS5）
    candidates: List[Dict] = []
    doc_freq: Dict[str, int] = {}
    for e in _iter_entries(user_id):
        if role and e.get("role", "") != role:
            continue
        text = f"{e.get('content','')} {e.get('task','')}".lower()
        matched = [t for t in terms if t in text]
        if not matched:
            continue
        candidates.append({"_entry": e, "_text": text, "_matched": matched})
        for t in set(matched):
            doc_freq[t] = doc_freq.get(t, 0) + 1

    if not candidates:
        return []

    # ── 第二遍：打分排序 ──
    # score = Σ_t (tf_t × idf_t) × role_boost × recency_boost
    #   tf  = 该词在条目里出现次数（信息量）
    #   idf = log(1 + N/df)  稀有词权重大（"redis" >> "优化"）
    #   role_boost = 用户原话 ×1.3（"上次我说了什么"场景优先命中 user 行）
    #   recency    = 越新 ×越高（同分时新的在前），上限 ×1.2 不喧宾夺主
    total_docs = max(1, len(candidates))
    newest_ts = candidates[-1]["_entry"].get("ts", "")
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for c in candidates:
        e, text = c["_entry"], c["_text"]
        score = 0.0
        for t in terms:
            tf = text.count(t)
            if tf == 0:
                continue
            idf = math.log(1 + total_docs / max(1, doc_freq.get(t, 1)))
            score += tf * idf
        if not score:
            continue
        if e.get("role") == "user":
            score *= 1.3
        ts = e.get("ts", "")
        if ts and newest_ts and ts[:7] == newest_ts[:7]:
            score *= 1.1
        scored.append((score, c["_entry"]))

    scored.sort(key=lambda x: -x[0])
    hits = [e for _, e in scored[:limit]]
    return hits


def search_or_fallback(query: str, user_id: str, limit: int = 10,
                       role: str = "") -> List[Dict]:
    """search 的 OR 降级版：AND 无结果时按"命中词数"再捞一轮

    Hermes 的查询语法让 agent 自己写 OR；这里内置到代码里——
    "数据库 太慢 优化" 搜不到（原文说"查询接口"）时，命中 1-2 个词的
    条目仍能捞回来，弱化软肋1/软肋2（同义词/错别字）的伤害。
    """
    hits = search(query, user_id, limit=limit, role=role)
    if hits:
        return hits
    terms = [t.lower() for t in query.split() if t.strip()]
    if len(terms) <= 1:
        return []
    return search(" OR ".join(terms), user_id, limit=limit, role=role)


def recent(user_id: str, limit: int = 20, session_id: str = "") -> List[Dict]:
    """最近 N 条（可按会话过滤）——"上次我们聊到哪了"场景

    修复: 取的是"最新 N 条"——先全量收集再取尾部（同月文件内行序是
    时间正序，仅倒月文件序不够）。
    """
    out: List[Dict] = []
    for e in _iter_entries(user_id):
        if session_id and e.get("session_id", "") != session_id:
            continue
        out.append(e)
    return out[-limit:] if limit and len(out) > limit else out


def stats(user_id: str) -> Dict:
    files = _all_ledger_files(user_id)
    total = sum(1 for _ in _iter_entries(user_id))
    span = f"{files[0].stem} ~ {files[-1].stem}" if files else "空"
    return {"files": len(files), "entries": total, "span": span}


def format_hits(hits: List[Dict], query: str = "") -> str:
    """把搜索结果格式化成 agent 可读的文本块

    0 命中时输出换词引导（学 Hermes："FTS5 ANDs all terms by default —
    broaden with OR..."）——让 agent 自己换词重搜，而不是死心。
    """
    if not hits:
        guide = (
            "(账本中未找到相关记录。搜索是多词 AND（全部命中才算），试试:\n"
            "  1. 换成当时对话里的具体词: 专有名词/文件名/版本号/技术名（如 redis、fastapi、账本）\n"
            "  2. 少用抽象大词（优化/改进/建议 单独搜会被大量流水淹没）\n"
            "  3. 减少 关键词 个数——每多一个词命中的面越窄\n"
            "  4. 用 role=\"user\" 只搜用户原话，避开大段回答)"
        )
        if query:
            guide = f"(账本中未找到「{query[:60]}」的相关记录。{guide[1:]}"
        return guide
    lines = [f"找到 {len(hits)} 条历史记录（按相关度排序）:"]
    for e in hits:
        lines.append(
            f"[{e.get('ts','')}] 会话{str(e.get('session_id',''))[-8:]} "
            f"[{e.get('role','?')}] {e.get('content','')[:400]}"
        )
    return "\n".join(lines)

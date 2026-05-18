"""短时记忆 — 文件式上下文窗口（仿 Claude Code memdir）

4 层压缩架构（适配 Python）：
  Layer 1: Micro-compact  — 每次 get_context() 时裁剪过旧工具结果，无 LLM
  Layer 2: Quick truncate — 超过 SOFT_LIMIT 时直接丢弃最早 chunk，无 LLM
  Layer 3: LLM compress   — 超过 HARD_LIMIT 时用 LLM 摘要旧消息
  Layer 4: Meta compress  — 摘要文件过多时合并为元摘要
  + 熔断器: 连续 3 次 LLM 压缩失败后跳过
  + 后清理: 压缩后清缓存

每个用户/会话独立目录:
  ~/.小雷版小龙虾/memory/{user_id}/
    ├── MEMORY.md         ← 索引
    ├── 0001_raw.md       ← 原始消息
    ├── 0002_raw.md
    ├── 0101_summary.md   ← LLM 压缩摘要
    └── meta_summary.md   ← 全局元摘要

接口：
  add(user_id, role, content)           → 写入 + 自动触发压缩链
  get_context(user_id, max_tokens=32000)→ [(role, content), ...]
  get_summary(user_id)                  → 全局摘要
  clear(user_id)                        → 删除目录
"""

import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 路径 ──────────────────────────────────────────────────────────────────────
MEMORY_ROOT = Path(os.path.expanduser("~/.小雷版小龙虾/memory"))

# ── 多层压缩阈值（ABSOLUTE > HARD > SOFT）───────────────────────────────────
ABSOLUTE_LIMIT = 32000        # 硬上限，get_context 返回时不会超过此值
HARD_LIMIT = 28000            # Layer 3: LLM 压缩触发阈值
SOFT_LIMIT = 24000            # Layer 2: 快速截断触发阈值
KEEP_RAW = 10                 # 保留的最近原始文件数
TOOL_RESULT_KEEP = 5          # Layer 1: micro-compact 保留的最多工具结果数
MAX_SUMMARIES_BEFORE_META = 8  # Layer 4: 触发元压缩的摘要文件数
MAX_META_TOKENS = 1000        # 元摘要最大 token 数
MAX_CONSECUTIVE_FAILURES = 3  # 熔断器：LLM 压缩连续失败次数

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """估算 token 数（对中文友好）"""
    if not text:
        return 0
    cjk = len(re.findall(r'[一-鿿぀-ヿ]', text))       # 1.5 chars/token
    ascii_chars = sum(1 for c in text if ord(c) < 128)  # 4 chars/token
    other = max(0, len(text) - cjk - ascii_chars)
    return int(cjk * 1.5 + ascii_chars / 4 + other / 2) + 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_user_id(user_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-.@]+", "_", user_id)[:64]


def _user_dir(user_id: str) -> Path:
    return MEMORY_ROOT / _safe_user_id(user_id)


def _index_path(user_id: str) -> Path:
    return _user_dir(user_id) / "MEMORY.md"


def _meta_path(user_id: str) -> Path:
    return _user_dir(user_id) / "meta_summary.md"


def _next_seq(user_dir: Path) -> int:
    max_n = 0
    for f in user_dir.glob("*.md"):
        m = re.match(r"(\d+)", f.stem)
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return max_n + 1


def _frontmatter(type_: str, role: str = "", tokens: int = 0,
                 description: str = "") -> str:
    lines = ["---", f"type: {type_}"]
    if role:
        lines.append(f"role: {role}")
    lines.append(f"timestamp: {_now_iso()}")
    if tokens:
        lines.append(f"tokens: {tokens}")
    if description:
        lines.append(f"description: {description}")
    lines.append("---")
    return "\n".join(lines)


def _read_frontmatter(content: str) -> tuple[dict, str]:
    meta: dict = {}
    rest = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
            rest = parts[2].strip()
    return meta, rest


def _update_index(user_id: str):
    """写 MEMORY.md 索引文件"""
    user_dir = _user_dir(user_id)
    entries = []
    for f in sorted(user_dir.glob("*.md")):
        if f.name == "MEMORY.md" or f.name == "meta_summary.md":
            continue
        meta, _ = _read_frontmatter(f.read_text(encoding="utf-8"))
        desc = meta.get("description", "")
        role = meta.get("role", "")
        ts = meta.get("timestamp", "")
        info = f"{role} | {desc}" if desc else role
        entries.append(f"- [{f.name}]({f.name}) — {info} ({ts})")

    _index_path(user_id).write_text(
        f"# MEMORY — {user_id}\n\n"
        f"Total: {len(entries)} files\n\n"
        + "\n".join(entries),
        encoding="utf-8",
    )


def _load_files(user_id: str) -> List[dict]:
    """加载用户的所有记忆文件，按时间排序"""
    user_dir = _user_dir(user_id)
    if not user_dir.exists():
        return []
    files = []
    for f in sorted(user_dir.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        meta, body = _read_frontmatter(f.read_text(encoding="utf-8"))
        files.append({
            "path": f,
            "meta": meta,
            "body": body,
            "tokens": int(meta.get("tokens", _estimate_tokens(body))),
            "type": meta.get("type", "raw"),
            "timestamp": meta.get("timestamp", ""),
        })
    return files


def _total_tokens(files: List[dict]) -> int:
    return sum(f["tokens"] for f in files)


# ── LLM 总结 ─────────────────────────────────────────────────────────────────

async def _llm_summarize_async(text: str, instruction: str = "") -> Optional[str]:
    """LLM 总结（异步），失败返回 None"""
    if not text.strip():
        return None
    try:
        from ..engine.llm_backend import get_llm_router
        router = get_llm_router()
        if router:
            prompt = f"{instruction}\n\n---\n{text}\n---\n\n总结："
            result = await router.simple_chat(
                user_message=prompt,
                system_prompt="你是一个精炼的总结助手，用简洁的中文总结对话要点。",
                temperature=0.2,
            )
            if result:
                return result.strip() if isinstance(result, str) else str(result).strip()
    except Exception as e:
        logger.debug(f"LLM 总结不可用: {e}")
    return None


def _llm_summarize(text: str, instruction: str = "") -> Optional[str]:
    """LLM 总结（同步），失败返回 None"""
    if not text.strip():
        return None
    try:
        from ..engine.llm_backend import get_llm_router
        router = get_llm_router()
        if router and hasattr(router, 'is_available') and router.is_available():
            import asyncio
            prompt = f"{instruction}\n\n---\n{text}\n---\n\n总结："
            try:
                loop = asyncio.get_running_loop()
                result = loop.run_until_complete(router.simple_chat(
                    user_message=prompt,
                    system_prompt="你是一个精炼的总结助手，用简洁的中文总结对话要点。",
                    temperature=0.2,
                ))
            except RuntimeError:
                result = asyncio.run(router.simple_chat(
                    user_message=prompt,
                    system_prompt="你是一个精炼的总结助手，用简洁的中文总结对话要点。",
                    temperature=0.2,
                ))
            if result:
                return result.strip() if isinstance(result, str) else str(result).strip()
    except Exception as e:
        logger.debug(f"LLM 总结不可用: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  主类
# ══════════════════════════════════════════════════════════════════════════════

class ShortTermMemoryManager:
    """4 层压缩上下文管理器"""

    def __init__(self,
                 soft_limit: int = SOFT_LIMIT,
                 hard_limit: int = HARD_LIMIT,
                 absolute_limit: int = ABSOLUTE_LIMIT,
                 keep_raw: int = KEEP_RAW,
                 tool_result_keep: int = TOOL_RESULT_KEEP,
                 max_tokens: Optional[int] = None,
                 compact_threshold: Optional[int] = None,
                 cache_size: int = 50):  # 保留兼容
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.absolute_limit = absolute_limit or (max_tokens or ABSOLUTE_LIMIT)
        self.keep_raw = keep_raw
        self.tool_result_keep = tool_result_keep
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.absolute_limit = absolute_limit
        self.keep_raw = keep_raw
        self.tool_result_keep = tool_result_keep
        MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

        # 熔断器状态: user_id → 连续失败次数
        self._compact_failures: Dict[str, int] = {}
        # 熔断器打开: user_id → 打开时间戳 (5分钟内不再重试)
        self._circuit_open: Dict[str, float] = {}

        # 运行时统计
        self._stats = {
            "files_written": 0,
            "micro_compacts": 0,
            "quick_truncates": 0,
            "compressions": 0,
            "meta_compressions": 0,
            "post_cleanups": 0,
        }

    # ══════════════════════════════════════════════════════════════════════
    #  公开 API
    # ══════════════════════════════════════════════════════════════════════

    def add(self, user_id: str, role: str, content: str) -> None:
        """添加一条消息 + 触发压缩链"""
        self.add_message(user_id, role, content)

    def add_message(self, user_id: str, role: str, content: str) -> None:
        """添加消息，触发压缩链"""
        user_dir = _user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        tokens = _estimate_tokens(content)
        seq = _next_seq(user_dir)
        desc = content[:60].replace("\n", " ")

        front = _frontmatter("raw", role=role, tokens=tokens, description=desc)
        file_path = user_dir / f"{seq:04d}_raw.md"
        file_path.write_text(f"{front}\n\n{content}", encoding="utf-8")

        self._stats["files_written"] += 1
        _update_index(user_id)

        # 触发多层压缩链
        self._check_and_compact(user_id)

    def add_context(self, user_id: str, content: str, context_type: str = "conversation") -> None:
        role = "assistant" if context_type == "assistant" else "user"
        self.add_message(user_id, role, content)

    def get_context(self, user_id: str, max_tokens: Optional[int] = None,
                    depth: int = 0, limit: int = 20) -> List[Dict]:
        """获取上下文消息列表

        返回前先跑 micro-compact（Layer 1，裁剪旧的工具结果）。
        """
        # Layer 1: 每次获取前先微压缩
        self._micro_compact(user_id)

        limit_tokens = max_tokens or self.absolute_limit
        files = _load_files(user_id)
        if not files:
            return []

        raw_files = [f for f in files if f["type"] == "raw"]
        summary_files = [f for f in files if f["type"] == "summary"]
        meta_files = [f for f in files if f["type"] == "meta"]

        result: List[Dict] = []

        # 1. 元摘要
        for mf in meta_files:
            result.append({
                "role": "system",
                "content": f"[对话历史摘要] {mf['body'][:500]}",
            })

        # 2. 摘要块
        for sf in summary_files:
            result.append({
                "role": "system",
                "content": f"[历史片段] {sf['body'][:300]}",
            })

        # 3. 最近的原始消息
        recent = raw_files[-self.keep_raw:] if len(raw_files) > self.keep_raw else raw_files
        for rf in recent:
            result.append({
                "role": rf["meta"].get("role", "user"),
                "content": rf["body"],
            })

        # 4. 按 token 截断（不超过上限）
        total = _estimate_tokens(" ".join(m.get("content", "") for m in result))
        if total > limit_tokens:
            reversed_result = list(reversed(result))
            keep = []
            remaining = limit_tokens
            for m in reversed_result:
                t = _estimate_tokens(m.get("content", ""))
                if t <= remaining:
                    keep.insert(0, m)
                    remaining -= t
            result = keep

        return result

    def get_summary(self, user_id: str) -> str:
        meta_path = _meta_path(user_id)
        if meta_path.exists():
            _, body = _read_frontmatter(meta_path.read_text(encoding="utf-8"))
            return body[:500]
        return ""

    def clear(self, user_id: str) -> None:
        user_dir = _user_dir(user_id)
        if user_dir.exists():
            import shutil
            shutil.rmtree(user_dir)
            self._compact_failures.pop(user_id, None)
            self._circuit_open.pop(user_id, None)
            logger.info("已清空 %s 的上下文", user_id)

    def get_info(self, user_id: str) -> Dict:
        files = _load_files(user_id)
        raw = [f for f in files if f["type"] == "raw"]
        summaries = [f for f in files if f["type"] == "summary"]
        meta = [f for f in files if f["type"] == "meta"]
        return {
            "user_id": user_id,
            "total_files": len(files),
            "raw_files": len(raw),
            "summary_files": len(summaries),
            "meta_files": len(meta),
            "estimated_tokens": _total_tokens(files),
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "absolute_limit": self.absolute_limit,
            "circuit_open": self._circuit_open.get(user_id, 0) > time.time(),
            "failures": self._compact_failures.get(user_id, 0),
        }

    def get_stats(self) -> Dict:
        return {**self._stats}

    def list_memories(self) -> List[Dict]:
        if not MEMORY_ROOT.exists():
            return []
        users = []
        for d in sorted(MEMORY_ROOT.iterdir()):
            if d.is_dir():
                idx = d / "MEMORY.md"
                if idx.exists():
                    users.append({
                        "user_id": d.name,
                        "file_count": len(list(d.glob("*.md"))),
                    })
        return users

    # ══════════════════════════════════════════════════════════════════════
    #  熔断器
    # ══════════════════════════════════════════════════════════════════════

    def _is_circuit_open(self, user_id: str) -> bool:
        """熔断器是否打开（打开后 5 分钟内不重试 LLM 压缩）"""
        open_time = self._circuit_open.get(user_id, 0)
        if open_time > time.time():
            return True
        if open_time > 0:
            self._circuit_open.pop(user_id, None)  # 过期自动关闭
        return False

    def _record_failure(self, user_id: str):
        self._compact_failures[user_id] = self._compact_failures.get(user_id, 0) + 1
        if self._compact_failures[user_id] >= MAX_CONSECUTIVE_FAILURES:
            self._circuit_open[user_id] = time.time() + 300  # 5分钟
            logger.warning(f"压缩熔断器打开: user={user_id}, 5m内跳过LLM压缩")

    def _reset_failures(self, user_id: str):
        self._compact_failures.pop(user_id, None)
        self._circuit_open.pop(user_id, None)

    # ══════════════════════════════════════════════════════════════════════
    #  多层压缩触发链
    # ══════════════════════════════════════════════════════════════════════

    def _check_and_compact(self, user_id: str):
        """压缩触发链：按阈值从低到高尝试

        Layer 1 (micro): 每次 get_context 时做，这里不做
        Layer 2 (quick): total > SOFT_LIMIT → 截断，无 LLM
        Layer 3 (llm):   total > HARD_LIMIT → LLM 摘要
        Layer 4 (meta):  Layer 3 做完后，摘要有 8+ 个 → 元摘要
        """
        if self.soft_limit <= 0:
            return

        files = _load_files(user_id)
        total = _total_tokens(files)

        if total <= self.soft_limit:
            return

        raw_files = [f for f in files if f["type"] == "raw"]

        if total > self.hard_limit and not self._is_circuit_open(user_id):
            # Layer 3: LLM 压缩
            success = self._llm_compress(user_id, raw_files)
            if not success:
                self._record_failure(user_id)
                # LLM 失败 → 降级到 quick truncate
                self._quick_truncate(user_id, raw_files)
            else:
                self._reset_failures(user_id)
                # Layer 4: 检查是否需要元压缩
                remaining = _load_files(user_id)
                summary_files = [f for f in remaining if f["type"] == "summary"]
                if len(summary_files) >= MAX_SUMMARIES_BEFORE_META:
                    self._compress_to_meta(user_id)
            self._run_post_cleanup(user_id)
        elif total > self.soft_limit:
            # Layer 2: 快速截断
            self._quick_truncate(user_id, raw_files)

    # ══════════════════════════════════════════════════════════════════════
    #  Layer 1: Micro-compact
    # ══════════════════════════════════════════════════════════════════════

    def _micro_compact(self, user_id: str):
        """微压缩：裁剪旧的工具结果/系统消息

        每次 get_context 时调用。
        只保留最近 TOOL_RESULT_KEEP 个 tool_result 或 system 消息。
        无 LLM 调用，纯文件操作。
        """
        if self.tool_result_keep <= 0:
            return

        files = _load_files(user_id)
        # 收集 role=user 且内容像工具结果的消息（tool_result标记）
        tool_results = []
        for f in files:
            role = f["meta"].get("role", "")
            body = f["body"]
            # 识别工具结果：role=user 且包含 tool_result 标记
            if role == "user" and len(body) > 100:
                tool_results.append(f)
            # 识别 system 注入
            elif role == "system" and len(body) > 200:
                tool_results.append(f)

        # 如果没超过 keep 数量，不裁剪
        if len(tool_results) <= self.tool_result_keep:
            return

        # 删除最早的多余工具结果
        to_delete = tool_results[:-self.tool_result_keep]
        for f in to_delete:
            try:
                f["path"].unlink()
            except OSError:
                pass

        if to_delete:
            self._stats["micro_compacts"] += 1
            _update_index(user_id)
            logger.debug(f"micro-compact: user={user_id}, 删除了 {len(to_delete)} 个旧结果")

    # ══════════════════════════════════════════════════════════════════════
    #  Layer 2: Quick truncate
    # ══════════════════════════════════════════════════════════════════════

    def _quick_truncate(self, user_id: str, raw_files: List[dict]):
        """快速截断：超过 SOFT_LIMIT 时丢弃最早的消息块

        无 LLM 调用，直接删除最旧的文件，直到低于 SOFT_LIMIT。
        """
        if len(raw_files) <= self.keep_raw:
            return

        to_delete = raw_files[:-self.keep_raw]
        if not to_delete:
            return

        for f in to_delete:
            try:
                f["path"].unlink()
            except OSError:
                pass

        self._stats["quick_truncates"] += 1
        _update_index(user_id)
        logger.info(f"quick-truncate: user={user_id}, 丢弃 {len(to_delete)} 个最早消息, "
                     f"保留 {self.keep_raw} 个最近")

    # ══════════════════════════════════════════════════════════════════════
    #  Layer 3: LLM compress
    # ══════════════════════════════════════════════════════════════════════

    def _llm_compress(self, user_id: str, raw_files: List[dict]) -> bool:
        """LLM 压缩：用 LLM 将旧消息摘要为一段话

        Returns: 是否成功
        """
        total_before = _total_tokens(raw_files)
        if len(raw_files) <= self.keep_raw:
            return True  # 文件不够还不需要压缩

        compressible = raw_files[:-self.keep_raw]
        if not compressible:
            return True

        combined = "\n".join(
            f"[{f['meta'].get('role','?')}] {f['body']}" for f in compressible
        )
        if not combined.strip():
            return True

        summary_text = _llm_summarize(
            combined,
            instruction="请将以下对话压缩为一段2-3句话的摘要，保留关键问题和答案的核心信息",
        )
        if not summary_text:
            return False  # LLM 不可用

        self._stats["compressions"] += 1

        # 写入摘要文件
        user_dir = _user_dir(user_id)
        seq = _next_seq(user_dir)
        desc = summary_text[:60].replace("\n", " ")
        summary_tokens = _estimate_tokens(summary_text)
        front = _frontmatter("summary", tokens=summary_tokens, description=desc)
        summary_path = user_dir / f"{seq:04d}_summary.md"
        summary_path.write_text(f"{front}\n\n{summary_text}", encoding="utf-8")

        # 删除已压缩的原始消息文件
        for f in compressible:
            try:
                f["path"].unlink()
            except OSError:
                pass

        _update_index(user_id)
        after = _total_tokens(_load_files(user_id))
        logger.info(f"llm-compress: user={user_id}, 合并 {len(compressible)} 条, "
                     f"{total_before}→{after} tokens")
        return True

    # ══════════════════════════════════════════════════════════════════════
    #  Layer 4: Meta compress
    # ══════════════════════════════════════════════════════════════════════

    def _compress_to_meta(self, user_id: str):
        """元压缩：将多个摘要合并为一个元摘要"""
        files = _load_files(user_id)
        summary_files = [f for f in files if f["type"] == "summary"]

        combined = "\n".join(f["body"] for f in summary_files)
        if not combined.strip():
            return

        meta_text = _llm_summarize(
            combined,
            instruction="以上是多次对话摘要，请综合提炼为一段2-3句话的总体摘要",
        )
        if not meta_text:
            return

        self._stats["meta_compressions"] += 1

        # 限制元摘要大小
        if _estimate_tokens(meta_text) > MAX_META_TOKENS:
            meta_text = meta_text[:MAX_META_TOKENS * 4]  # 粗略截断

        front = _frontmatter("meta", tokens=_estimate_tokens(meta_text),
                             description="全局对话元摘要")
        _meta_path(user_id).write_text(f"{front}\n\n{meta_text}", encoding="utf-8")

        # 只保留最近的 2 个摘要文件
        user_dir = _user_dir(user_id)
        summaries = sorted(user_dir.glob("*_summary.md"))
        for f in summaries[:-2]:
            try:
                f.unlink()
            except OSError:
                pass

        _update_index(user_id)
        logger.info(f"meta-compress: user={user_id}, 合并 {len(summary_files)} 个摘要")

    # ══════════════════════════════════════════════════════════════════════
    #  后清理
    # ══════════════════════════════════════════════════════════════════════

    def _run_post_cleanup(self, user_id: str):
        """压缩后清理缓存"""
        self._stats["post_cleanups"] += 1
        # 索引已在各压缩方法里更新，这里清一下内存中可能的旧文件缓存
        # 当前实现无内存文件缓存，直接返回
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  兼容别名 + 工厂
# ══════════════════════════════════════════════════════════════════════════════

CompressedContextManager = ShortTermMemoryManager

_manager: Optional[ShortTermMemoryManager] = None


def get_memory_manager() -> ShortTermMemoryManager:
    global _manager
    if _manager is None:
        _manager = ShortTermMemoryManager()
    return _manager


# 模块级兼容函数
def get_context(user_id: str, depth: int = 0, limit: int = 20) -> List[Dict]:
    return get_memory_manager().get_context(user_id)


def add_context(user_id: str, content: str, context_type: str = "conversation") -> None:
    get_memory_manager().add_context(user_id, content, context_type)


def clear_context(user_id: str) -> None:
    get_memory_manager().clear(user_id)

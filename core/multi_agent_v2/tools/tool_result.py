"""
统一 Handler 返回格式 — ok()/err() 协议 + 统一输出截断

借鉴 gemini-cli 的 ToolResult{llmContent, error?} 设计。
所有 handler 返回统一格式，_format_tool_result() 只需一条路径解析。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 统一输出截断（注册表层，对标 opencode boundOutput）
# ════════════════════════════════════════════════════════════════

TOOL_OUTPUT_LIMITS: Dict[str, int] = {
    "read": 3000,
    "read_file": 100000,  # ponytail: 从 3000 拉到 100K，避免 agent 反复调用只为了读完一个文件
    "write": 3000,
    "write_file": 3000,
    "edit": 3000,
    "edit_file": 3000,
    "grep": 3000,
    "glob": 3000,
    "search_files": 3000,
    "web_search": 4000,
    "websearch": 4000,
    "fetch_url": 4000,
    "webfetch": 4000,
    "bash": 5000,
    "shell": 5000,
    "execute_shell": 5000,
    "execute_python": 5000,
    "git": 2000,
    "task": 2000,
    "todo": 2000,
    "plan": 2000,
    "write_todos": 2000,
}
DEFAULT_OUTPUT_LIMIT = 3000


def bound_result(tool_name: str, raw: Any) -> Any:
    """注册表层统一截断工具输出

    Args:
        tool_name: 工具名
        raw: handler 原始返回（dict, str, 或 None）

    Returns:
        截断后的结果（保持原格式结构）
    """
    limit = TOOL_OUTPUT_LIMITS.get(tool_name, DEFAULT_OUTPUT_LIMIT)

    if isinstance(raw, dict):
        if "ok" in raw:
            data = raw.get("data", "")
            if isinstance(data, str) and len(data) > limit:
                raw["data"] = _truncate(data, limit, tool_name)
            return raw
        result = raw.get("result", {})
        if isinstance(result, dict):
            content = result.get("content", [])
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    text = first.get("text", "")
                    if isinstance(text, str) and len(text) > limit:
                        first["text"] = _truncate(text, limit, tool_name)
        return raw

    if isinstance(raw, str) and len(raw) > limit:
        return _truncate(raw, limit, tool_name)

    return raw


def _truncate(text: str, max_chars: int, tool_name: str = "") -> str:
    """截断文本，超出部分写入临时文件并给出读取提示（OpenCode 风格）"""
    if len(text) <= max_chars:
        return text

    import tempfile, os
    head_len = int(max_chars * 0.6)
    tail_len = max_chars - head_len - 30
    head = text[:head_len]
    tail = text[-tail_len:] if tail_len > 0 else ""
    truncated_count = len(text) - max_chars

    # 保存完整输出到临时文件
    try:
        tmp_dir = os.path.expanduser("~/.xiaolei/truncated")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, f"{tool_name}_{os.getpid()}.txt")
        with open(tmp_path, 'w') as f:
            f.write(text)
        hint = f"[截断 {truncated_count} 字符 — 完整内容存于工作目录，按需引用]"
    except Exception:
        hint = f"[截断 {truncated_count} 字符]"

    result = f"{head}\n\n... {hint} ...\n\n{tail}"
    logger.info(f"输出截断: {tool_name} {len(text)}→{len(result)}字符, 完整文件: {tmp_path}")
    return result


def ok(
    data: str,
    title: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    extra_contexts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """成功结果 — OpenCode 风格: title(展示) + data(LLM上下文) + metadata(结构化信息)

    ponytail + deepseek: extra_contexts 列表项会作为 user 消息注入下一轮 LLM 输入（addl. observe）。
    工具作者可借此告诉 agent 该如何理解本次结果（如写入摘要、读取分片提示）。
    """
    result: Dict[str, Any] = {"ok": True, "data": data}
    if title:
        result["title"] = title
    if metadata:
        result["metadata"] = metadata
    if extra_contexts:
        result["_extra_contexts"] = extra_contexts
    return result


def err(error: str) -> Dict[str, Any]:
    """失败结果"""
    return {"ok": False, "error": error}


def is_ok(result: Any) -> bool:
    """检查是否成功（兼容新旧格式）"""
    if isinstance(result, dict):
        # 新格式：显式 ok 字段
        if "ok" in result:
            return result["ok"]
        # 旧格式：从 content text 推断
        result_data = result.get("result", {})
        if isinstance(result_data, dict):
            content = result_data.get("content", [])
            if isinstance(content, list) and content:
                text = content[0].get("text", "") if isinstance(content[0], dict) else ""
                # 错误关键词模式
                error_prefixes = ("缺少", "未知", "失败", "被安全策略阻止", "超时", "❌", "错误", "阻止")
                if any(text.startswith(p) or p in text[:30] for p in error_prefixes):
                    return False
        return True
    return True


def from_handler(raw: Any) -> str:
    """从任何 handler 输出提取可读文本（兼容新旧格式）

    支持的格式:
    - 新格式: {"ok": True, "data": "..."} 或 {"ok": False, "error": "..."}
    - 旧格式: {"result": {"content": [{"text": "..."}]}}
    - 纯字符串: "..."
    - None: ""
    """
    if raw is None:
        return ""

    if isinstance(raw, str):
        return raw

    if isinstance(raw, dict):
        # 新格式优先
        if "ok" in raw:
            if raw["ok"]:
                text = raw.get("data", "")
                # 修复: 编辑类工具返回 {ok, data, diff}，diff(新增+/删除-)单独字段，
                # 原实现只取 data("编辑成功:x处") 就返回，diff 被丢弃，
                # LLM 和终端都看不到改动。现在把 diff 一并拼进文本。
                if "diff" in raw:
                    diff = str(raw.get("diff", "")).strip()
                    if diff:
                        text = f"{text}\n\n--- 变更内容 (新增前 + / 删除前 -) ---\n{diff}"
                return text
            else:
                return f"错误: {raw.get('error', '未知错误')}"

        # 旧格式 fallback: {"result": {"content": [{"text": "..."}]}}
        result = raw.get("result", raw)
        if isinstance(result, dict):
            content = result.get("content", [])
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    return first.get("text", str(raw))
            # 尝试 text/output/result 字段
            for key in ("text", "output", "result"):
                if key in result:
                    val = result[key]
                    if isinstance(val, str):
                        return val
                    return str(val)

    return str(raw)


def extract_error(raw: Any) -> str:
    """从 handler 输出提取错误信息"""
    if isinstance(raw, dict):
        if "ok" in raw and not raw["ok"]:
            return raw.get("error", "未知错误")
        result = raw.get("result", {})
        if isinstance(result, dict):
            return result.get("error", "")
        error = raw.get("error", "")
        if error:
            return str(error)
    if isinstance(raw, str) and "错误" in raw[:20]:
        return raw
    return ""

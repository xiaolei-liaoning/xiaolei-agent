"""
统一 Handler 返回格式 — ok()/err() 协议

借鉴 gemini-cli 的 ToolResult{llmContent, error?} 设计。
所有 handler 返回统一格式，_format_tool_result() 只需一条路径解析。
"""
from typing import Any, Dict


def ok(data: str) -> Dict[str, Any]:
    """成功结果"""
    return {"ok": True, "data": data}


def err(error: str) -> Dict[str, Any]:
    """失败结果"""
    return {"ok": False, "error": error}


def is_ok(result: Any) -> bool:
    """检查是否成功"""
    if isinstance(result, dict):
        return result.get("ok", True)  # 无 ok 字段视为成功（兼容旧格式）
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
                return raw.get("data", "")
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

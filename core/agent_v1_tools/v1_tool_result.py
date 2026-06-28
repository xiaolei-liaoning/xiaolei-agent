"""V1 统一 Handler 返回格式 — ok()/err() 协议"""

from typing import Any, Dict


def ok(data: str, **extra) -> Dict[str, Any]:
    r = {"ok": True, "data": data}
    if extra:
        r.update(extra)
    return r


def err(error: str) -> Dict[str, Any]:
    return {"ok": False, "error": error}


def is_ok(result: Any) -> bool:
    if isinstance(result, dict):
        if "ok" in result:
            return result["ok"]
        return True  # ponytail: V1 返回值必含 ok 字段，非 dict 视为 ok
    return True  # ponytail: 同上，非 dict 默认乐观


def from_handler(raw: Any) -> str:
    """从 handler 输出提取可读文本"""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        if "ok" in raw:
            return raw.get("data", "") if raw["ok"] else f"错误: {raw.get('error', '未知错误')}"
        result = raw.get("result", raw)
        if isinstance(result, dict):
            for key in ("text", "output", "result", "content"):
                if key in result:
                    val = result[key]
                    return str(val) if not isinstance(val, str) else val
    return str(raw)


def extract_error(raw: Any) -> str:
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

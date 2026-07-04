"""统一 JSON 解析修复工具 — 所有 LLM→JSON 边界走这里"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def safe_parse_json(raw: Any) -> Dict[str, Any]:
    """安全解析 JSON，自动修复常见 LLM 输出错误"""
    if isinstance(raw, dict):
        return raw
    if not raw or not raw.strip():
        return {}

    # 尝试 1：标准解析
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    repaired = raw

    # a) 移除 // 注释
    repaired = re.sub(r'//[^\n]*', '', repaired)

    # b) 补全未引号包裹的 key：{key: → {"key":
    if re.match(r'^\s*\{?\s*[a-zA-Z_]\w*\s*:', repaired):
        repaired = re.sub(r'(\s*)(\w+)(\s*):', r'\1"\2"\3:', repaired)
        if not repaired.strip().startswith('{'):
            repaired = '{' + repaired
        if not repaired.strip().endswith('}'):
            repaired = repaired + '}'

    # c) 智能单引号→双引号：只换看起来像 JSON 引号的，不换文本内撇号
    _sq = len(re.findall(r"'\w+'\s*:", repaired))  # 'key': 模式
    _dq = len(re.findall(r'"\w+"\s*:', repaired))  # "key": 模式
    _sv = len(re.findall(r':\s*\'[^\']+\'', repaired))  # : 'value' 模式
    if _sq > _dq or (_sv > 0 and _dq > 0):
        # 单引号 style：key 和 value 都换
        repaired = re.sub(r"'([^']+)':", r'"\1":', repaired)
        repaired = re.sub(r":\s*'([^']+)'", r': "\1"', repaired)

    # d) 移除尾随逗号
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

    # 尝试 2：修复后解析
    try:
        return json.loads(repaired)
    except (json.JSONDecodeError, TypeError):
        pass

    # 尝试 3：write_file 特殊修复（被截断的 content）
    if '"path"' in raw:
        path_m = re.search(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        content_m = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)', raw)
        if path_m:
            logger.info(f"正则修复 write_file 参数，path={path_m.group(1)[:60]}")
            content = content_m.group(1) if content_m else raw
            return {"path": path_m.group(1), "content": content}

    logger.warning(f"JSON 修复失败: {raw[:80]}...")
    return {}

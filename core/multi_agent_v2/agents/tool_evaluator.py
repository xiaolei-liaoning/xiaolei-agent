"""工具结果评估与格式化

从 react_core.py 提取，负责：
- 工具执行结果的质量评估
- 结构化格式化输出给 LLM
- 错误类型 → 修复建议映射
"""

import json
import re
from typing import Any, Dict


# ═══════════════════════════════════════════════════════════════════
# 错误类型 → 修复建议映射
# ═══════════════════════════════════════════════════════════════════

ERROR_SUGGESTIONS = {
    "SyntaxError": "检查代码语法，注意缩进和括号匹配",
    "NameError": "检查变量名是否已定义，是否有拼写错误",
    "TypeError": "检查函数参数类型是否正确",
    "KeyError": "检查字典 key 是否存在，使用 .get() 安全访问",
    "FileNotFoundError": "检查文件路径是否正确，文件是否存在",
    "ConnectionError": "网络连接失败，检查 URL 或稍后重试",
    "TimeoutError": "请求超时，尝试简化请求或稍后重试",
    "ModuleNotFoundError": "缺少模块，检查 import 语句或安装依赖",
    "PermissionError": "权限不足，检查文件权限或使用正确路径",
    "JSONDecodeError": "JSON 解析失败，检查返回内容是否为有效 JSON",
    "429": "API 限流，稍后重试",
    "500": "服务器内部错误，稍后重试",
    "404": "资源不存在，检查 URL 是否正确",
}


def get_error_suggestion(error_text: str) -> str:
    """根据错误文本返回修复建议"""
    for err_type, suggestion in ERROR_SUGGESTIONS.items():
        if err_type in error_text:
            return suggestion
    return "检查输入参数，或换用其他工具"


# ═══════════════════════════════════════════════════════════════════
# 工具结果质量评估
# ═══════════════════════════════════════════════════════════════════

def evaluate_tool_result(
    name: str, result_text: str, success: bool, arguments: Dict
) -> str:
    """对工具执行结果进行质量评估，生成结构化评价

    评估维度:
      - 结果是否为空 / 数量是否足够
      - 是否有明显的质量问题
      - 下一步建议（继续 / 重试 / 换方式）

    返回格式: [评估] {emoji} {评价摘要}
    """
    if not success:
        return ""  # 失败时已有错误信息，不再重复评价

    text = result_text.strip() if result_text else ""
    text_len = len(text)

    # ── web_search 评估 ──
    if name == "web_search":
        # 计算搜索结果数（按数字序号或换行段落估算）
        item_count = 0
        numbered = re.findall(r'(?:^|\n)\s*\d+[\.\、]', text)
        if numbered:
            item_count = len(numbered)
        else:
            # 按双换行段落算
            paragraphs = [p for p in text.split("\n\n") if len(p.strip()) > 10]
            item_count = len(paragraphs)

        if item_count == 0:
            return "[评估] ⚠️ 搜索未返回有效结果\n📌 建议：修改查询关键词或换搜索引擎重试"
        elif item_count >= 5:
            return f"[评估] ✅ 搜索成功，找到 {item_count} 条结果\n📌 建议：数据充足，≥5条结果可直接用于生成报告/回答"
        else:
            return f"[评估] ⚠️ 仅找到 {item_count} 条结果，可能不全面\n📌 建议：换个搜索词补充搜索以获取更完整信息"

    # ── fetch_url 评估 ──
    if name == "fetch_url":
        if text_len < 100:
            return "[评估] ⚠️ 获取内容极短（<100字符）\n📌 建议：可能未获取到完整数据，换用 execute_python 或 web_search 重试"
        elif text_len < 500:
            return f"[评估] ⚠️ 内容偏少（{text_len}字符）\n📌 建议：可能只获取到部分信息，可尝试换一个数据源或 URL"
        else:
            len_display = f">{text_len // 1000}k" if text_len > 1000 else str(text_len)
            return f"[评估] ✅ 成功获取网页内容（{len_display}字符），数据量充足\n📌 建议：数据已就绪，可直接分析或生成报告"

    # ── execute_python 评估 ──
    if name == "execute_python":
        if "❌" in text or "Error:" in text or "Traceback" in text:
            return ""
        if text_len < 10 or text == "(无输出)":
            code = arguments.get("code", "") if isinstance(arguments, dict) else ""
            has_print = "print(" in code
            has_return = "return " in code
            if not has_print and not has_return:
                return "[评估] ⚠️ 代码没有 print() 输出\n📌 建议：在代码末尾加 print() 查看结果"
            return "[评估] ⚠️ 代码执行输出为空\n📌 建议：检查代码逻辑，加 print() 调试"
        else:
            return "[评估] ✅ 代码执行成功\n📌 建议：结果已出，可继续下一步处理"

    # ── write_file 评估 ──
    if name == "write_file":
        path = arguments.get("path", "") if isinstance(arguments, dict) else ""
        content = arguments.get("content", "") if isinstance(arguments, dict) else ""
        content_len = len(content)
        if content_len < 100:
            return f"[评估] ⚠️ 写入内容很短（{content_len}字符）\n📌 建议：确认是否为完整文件，如是模板骨架可继续追加内容"
        return f"[评估] ✅ 文件写入成功（{content_len}字符）\n📌 建议：已完成文件创建，可结束任务或继续其他步骤：{path}"

    # ── read_file 评估 ──
    if name == "read_file":
        if text_len == 0:
            return "[评估] ⚠️ 文件为空或无法读取\n📌 建议：检查文件路径和权限"
        elif "权限" in text or "拒绝" in text or "not found" in text.lower():
            return "[评估] ⚠️ 文件读取异常\n📌 建议：检查路径或权限，换用 execute_shell 的 ls/cat 命令"
        return f"[评估] ✅ 文件读取成功（{text_len}字符）\n📌 建议：内容已获取，可基于此继续处理"

    # ── execute_shell 评估 ──
    if name == "execute_shell":
        if "❌" in text or "command not found" in text.lower():
            return ""
        if text_len < 5:
            return "[评估] ✅ 命令执行成功（无输出）"
        return "[评估] ✅ 命令执行成功\n📌 建议：输出已获取，可继续下一步"

    # ── search_files 评估 ──
    if name == "search_files":
        file_count = len(re.findall(r'(?:^|\n)\s*[-•]?\s*[\w./]', text))
        if file_count == 0:
            return "[评估] ⚠️ 未找到匹配的文件\n📌 建议：放宽搜索条件重试"
        elif file_count >= 10:
            return f"[评估] ✅ 找到 {file_count} 个匹配文件，结果充足\n📌 建议：覆盖全面，可直接使用这些文件"
        else:
            return f"[评估] ⚠️ 仅找到 {file_count} 个匹配文件，可能不全面\n📌 建议：调整搜索模式以覆盖更多"

    # ── git 评估 ──
    if name == "git":
        if "fatal" in text.lower() or "error" in text.lower():
            return "[评估] ⚠️ Git 操作异常\n📌 建议：检查仓库状态和配置"
        return "[评估] ✅ Git 操作成功"

    # 通用评估
    if text_len == 0:
        return "[评估] ⚠️ 工具返回结果为空\n📌 建议：检查输入参数是否正确"
    return "[评估] ✅ 工具执行成功\n📌 建议：结果可用，继续下一步"


# ═══════════════════════════════════════════════════════════════════
# 工具结果格式化
# ═══════════════════════════════════════════════════════════════════

def format_tool_result(
    name: str, result: Any, success: bool, arguments: Dict
) -> str:
    """将工具结果格式化为 LLM 可读的结构化文本，质量评估在最前面

    格式:
      成功: [tool_name] OK\n{评估(含建议)}\n\n---\n{结果摘要}
      失败: [tool_name] FAIL\n错误: {error}\n建议: {suggestion}
    """
    MAX_CONTENT = 2500  # 单个结果最大字符数

    if success:
        # 提取结果内容
        raw = result
        if isinstance(raw, dict):
            # 优先取 content / text / output / result 字段
            for key in ("content", "text", "output", "result", "data"):
                if key in raw:
                    raw = raw[key]
                    break
            else:
                raw = json.dumps(raw, ensure_ascii=False, default=str)

        text = str(raw).strip()
        if len(text) > MAX_CONTENT:
            # 智能截断：保留头尾，中间省略
            head = text[: int(MAX_CONTENT * 0.7)]
            tail = text[-int(MAX_CONTENT * 0.2) :]
            text = f"{head}\n\n... [省略 {len(text) - MAX_CONTENT} 字符] ...\n\n{tail}"

        if not text or text == "None" or text == "(无输出)":
            text = "(无输出)"

        # 质量评估（放在结果前面，LLM 第一时间看到）
        evaluation = evaluate_tool_result(name, text, success, arguments)
        if evaluation:
            return f"[{name}] OK\n{evaluation}\n\n---\n{text}"
        return f"[{name}] OK\n{text}"

    else:
        # 失败 — 提取错误 + 给建议
        error_text = ""
        if isinstance(result, dict):
            # 优先级: 顶层 error → data → 嵌套 result.error → result 本身
            error_text = (
                result.get("error", "")
                or result.get("data", "")
                or (result.get("result", {}) or {}).get("error", "")
                or str(result.get("result", ""))[:300]
            )
            # 如果还是空，尝试从 content 字段提取（兼容确认对话框等格式）
            if not error_text:
                error_text = str(result.get("content", ""))[:300] or str(result)[:300]

        suggestion = get_error_suggestion(error_text)

        # 保留原始参数摘要（帮助 LLM 理解上下文）
        args_summary = ""
        if arguments:
            args_str = json.dumps(arguments, ensure_ascii=False, default=str)
            if len(args_str) > 200:
                args_str = args_str[:200] + "..."
            args_summary = f"\n参数: {args_str}"

        return f"[{name}] FAIL\n错误: {error_text}\n建议: {suggestion}{args_summary}"

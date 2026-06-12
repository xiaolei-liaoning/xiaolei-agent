"""
ReActCore — V2 单 Agent 核心执行器

基于 MiddlewareChain 的 ReAct 循环：
  LLM → Tool → Observation → 继续/结束

4层中间件链: [ReActDepth → ReActCore ★ → Reflection → KEPA]

简化点：
  - 去掉 PlanAwareMiddleware（不预设计划）
  - 去掉复杂兜底逻辑（只在必用时触发 LLM 汇总）
  - 去掉了 DynamicStageRouting / DataPipeline / Confidence 等
  - 保留核心：LLM ↔ 工具 ↔ 观察 ↔ 循环
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from .middleware import BaseMiddleware, MiddlewareChain, PlanStep, RunContext

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 10


# ═══════════════════════════════════════════════════════════════════
# 工具结果格式化 — 结构化反馈给 LLM
# ═══════════════════════════════════════════════════════════════════

# 错误类型 → 修复建议映射
_ERROR_SUGGESTIONS = {
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


def _get_error_suggestion(error_text: str) -> str:
    """根据错误文本返回修复建议"""
    for err_type, suggestion in _ERROR_SUGGESTIONS.items():
        if err_type in error_text:
            return suggestion
    return "检查输入参数，或换用其他工具"


def _format_tool_result(
    name: str, result: Any, success: bool, arguments: Dict
) -> str:
    """将工具结果格式化为 LLM 可读的结构化文本

    格式:
      成功: [tool_name] OK\n{结果摘要}
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

        return f"[{name}] OK\n{text}"

    else:
        # 失败 — 提取错误 + 给建议
        error_text = ""
        if isinstance(result, dict):
            error_text = (
                result.get("error", "")
                or result.get("result", {}).get("error", "")
                or str(result.get("result", ""))[:300]
            )
        else:
            error_text = str(result)[:300]

        suggestion = _get_error_suggestion(error_text)

        # 保留原始参数摘要（帮助 LLM 理解上下文）
        args_summary = ""
        if arguments:
            args_str = json.dumps(arguments, ensure_ascii=False, default=str)
            if len(args_str) > 200:
                args_str = args_str[:200] + "..."
            args_summary = f"\n参数: {args_str}"

        return f"[{name}] FAIL\n错误: {error_text}\n建议: {suggestion}{args_summary}"


class ReActCoreMiddleware(BaseMiddleware):
    """ReAct 核心循环：LLM 自主决定调工具还是直接回答"""

    def _get_prefix(self, ctx: RunContext) -> str:
        """从上下文获取Agent前缀"""
        if hasattr(ctx, "_chain") and ctx._chain and hasattr(ctx._chain, "_agent"):
            agent = ctx._chain._agent
            return _get_prefix(agent)
        return ""

    async def on_start(self, ctx: RunContext) -> None:
        """on_start 时发现全部工具并缓存，不做任务筛选"""
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry, _SANDBOX_TOOL_DEFS
        from core.multi_agent_v2.tools.register_new_tools import register_new_tools

        reg = get_tool_registry()
        
        # 先注册新工具
        register_new_tools(reg)
        
        try:
            await asyncio.wait_for(reg.discover_all(), timeout=15)
            ctx._tool_cache = list(reg._tools.values())
            n_builtin = sum(1 for t in ctx._tool_cache if t.server == "__builtin__")
            n_mcp = len(ctx._tool_cache) - n_builtin
            logger.info(f"工具发现完成: {len(ctx._tool_cache)} 个 ({n_builtin} 内置 + {n_mcp} MCP)")
        except asyncio.TimeoutError:
            discovered = list(reg._tools.values())
            if discovered:
                ctx._tool_cache = discovered
                logger.info(f"工具发现部分超时，使用已注册的 {len(ctx._tool_cache)} 个工具")
            else:
                ctx._tool_cache = list(_SANDBOX_TOOL_DEFS)
                logger.warning("工具发现完全超时，仅用内置工具")
        except Exception as e:
            ctx._tool_cache = list(_SANDBOX_TOOL_DEFS)
            logger.debug(f"工具发现异常: {e}")

    async def on_think_start(self, ctx: RunContext) -> None:
        """每轮 LLM 调用"""
        if ctx.interrupted or ctx.react_depth >= ctx.max_iterations:
            return

        # 防御：确保 task_description 是字符串
        if not isinstance(ctx.task_description, str):
            ctx.task_description = str(ctx.task_description) if ctx.task_description else ""

        from core.engine.llm_backend import get_llm_router

        router = get_llm_router()
        if not router.is_available():
            logger.error("❌ LLM 不可用")
            ctx.interrupted = True
            ctx.last_error = "LLM 不可用"
            return

        ctx.react_depth += 1
        ctx.iteration = ctx.react_depth

        # ── 任务感知工具筛选（首轮筛选后缓存复用）──
        tool_cache = getattr(ctx, '_tool_cache', None) or []
        if tool_cache:
            filtered = getattr(ctx, '_filtered_tools', None)
            if filtered is None:
                from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                reg = get_tool_registry()
                try:
                    filtered = await reg.get_tools_for_task(
                        ctx.task_description,
                        max_tools=20,
                        allowed=ctx.allowed_tools,
                        disallowed=ctx.disallowed_tools,
                    )
                except Exception:
                    filtered = tool_cache[:20]
                ctx._filtered_tools = filtered

            # 构建工具定义列表
            raw_defs = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                    "_server": t.server,
                    "_tool_name": t.tool_name,
                }
                for t in filtered
            ]

            # 模型感知 Schema 适配
            from core.multi_agent_v2.tools.schema import get_schema_adapter
            adapter = get_schema_adapter(ctx.model_override)
            ctx.tool_defs = adapter.adapt(raw_defs)
        else:
            ctx.tool_defs = None

        # Add write_todos tool for task tracking
        _write_todos_tool = {
            "type": "function",
            "function": {
                "name": "write_todos",
                "description": "创建和管理任务清单。用于复杂多步骤任务的进度追踪。只在任务有3个以上步骤时使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "todos": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string", "description": "任务描述"},
                                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "description": "任务状态"}
                                },
                                "required": ["content", "status"]
                            },
                            "description": "任务列表"
                        }
                    },
                    "required": ["todos"]
                }
            }
        }
        if ctx.tool_defs is not None:
            ctx.tool_defs.append(_write_todos_tool)

        # 构建消息 — 注入计划进度让 agent 知晓已完成/未完成步骤
        plan_context = _steps_summary(ctx) if ctx.plan else ""

        system_content = (
            "<thinking_style>\n"
            "## 认知策略\n"
            "在采取任何行动之前，你必须先进行系统性思考：\n\n"
            "### Step 1: 分析任务\n"
            "- 用户的**核心目标**是什么？\n"
            "- 哪些信息是**已知的**？哪些是**未知的**？\n"
            "- 任务中是否存在**歧义或不明确**的地方？\n\n"
            "### Step 2: 评估路径\n"
            "- 完成此任务需要哪些**步骤**？\n"
            "- 每个步骤应该使用哪个**工具**？\n"
            "- 是否有**并行执行**的可能（多个无依赖的工具调用）？\n\n"
            "### Step 3: 执行后反思\n"
            "- 工具返回的结果**是否满足预期**？\n"
            "- 是否需要**追加调用**其他工具补充信息？\n"
            "- 当前结果是否足以**生成最终回答**？\n\n"
            "### 关键规则\n"
            "- 如果任务存在歧义，**先调用 ask_clarification 工具澄清**，再执行\n"
            "- 思考过程要**简洁高效**，不要过度纠结\n"
            "- 每轮思考后必须给出**实际响应**（工具调用或最终答案）\n"
            "- **禁止空转**：不要只输出计划/步骤说明而不调用工具，每轮必须有工具调用\n"
            "- **禁止输出描述性文字**：不要输出'我将...'、'首先...'、'步骤1...'等计划描述，直接调用工具\n"
            "- **禁止输出部分代码**：不要输出被截断的代码，必须一次性输出完整代码\n"
            "- **创建文件类任务**：一次性写入完整可运行的代码到 write_file 的 content 参数，不要写多行\n"
            "- **⚠️ 写代码任务的强制路径**：当任务要求'写代码/创建游戏/写HTML/编写XX'时，你的**唯一路径**是：直接调用 write_file(path='~/Desktop/xxx.html', content='完整代码')。**绝对不要**调用 execute_python 来写代码——execute_python 只能执行 Python，不能创建文件，且沙盒会清理临时文件。如果你调用了 execute_python 来写游戏/HTML 代码，一定会失败。\n"
            "</thinking_style>\n\n"
            "<code_generation_workflow>\n"
            "## 代码生成流程（必须遵循）\n"
            "当你需要创建文件（游戏、HTML、脚本等）时，必须严格按照以下流程：\n\n"
            "### 1. 一次性生成完整代码\n"
            "- **不要分步写入**：必须在一次 write_file 调用中写入完整代码\n"
            "- **不要输出计划描述**：直接调用 write_file，不要先说'我将创建...'\n"
            "- **不要截断代码**：必须包含完整的 HTML 结构、CSS 样式、JavaScript 逻辑\n\n"
            "### 2. 代码质量要求\n"
            "- **功能完整**：游戏/应用必须可以正常运行，不要有占位符或 TODO\n"
            "- **视觉美观**：使用现代 CSS 样式（渐变、动画、阴影等）\n"
            "- **交互完整**：所有按钮、点击、输入都必须有响应\n"
            "- **无编译错误**：确保代码语法正确，可以直接在浏览器中运行\n\n"
            "### 3. HTML 文件必须包含\n"
            "- `<!DOCTYPE html>` 声明\n"
            "- `<html>` 和 `</html>` 标签\n"
            "- `<style>` 标签（CSS 样式）\n"
            "- `<script>` 标签（JavaScript 游戏逻辑，不能只有注释！）\n"
            "- 完整的游戏逻辑（初始化、渲染、交互、状态管理）\n\n"
            "### ⚠️ 禁止拆分文件\n"
            "- **禁止将 HTML 和 JS 拆分成两个文件**：游戏必须是单个自包含的 HTML 文件\n"
            "- **所有 JavaScript 必须内联在 `<script>` 标签中**，不要创建单独的 .js 文件\n"
            "- **所有 CSS 必须内联在 `<style>` 标签中**，不要创建单独的 .css 文件\n"
            "- 一次 write_file 调用写入完整文件，content 参数必须包含所有代码\n\n"
            "### 4. 错误恢复\n"
            "- 如果 write_file 返回'内容不完整'错误，必须重新写入完整代码\n"
            "- 如果代码被截断（显示为'...'或'backgrou...'），必须重新生成\n"
            "- 如果 write_file 返回'⚠️ 代码被截断'，说明内容太长被系统截断了\n"
            "  - 用 write_file 继续生成，content 中只写缺失部分（从断点继续）\n"
            "  - 系统会自动追加到已有文件后面\n"
            "  - 不要重复已有内容，只写缺失的标签和代码\n"
            "- **不要告诉用户'需要自行添加代码'**，你必须自己完成所有代码\n"
            "</code_generation_workflow>\n\n"
            "<report_workflow>\n"
            "## 报告/数据页面生成流程（必须遵循）\n"
            "当任务要求生成报告、数据汇总、热搜报告、分析页面、dashboard 等非游戏类文件时：\n\n"
            "### 1. 数据采集（必须先做！）\n"
            "- **禁止凭空编造数据**：报告中的数据必须来自真实抓取\n"
            "- 使用 web_search 搜索相关数据（如：web_search(query='百度热搜')）\n"
            "- 使用 fetch_url 抓取具体网页/API（如：fetch_url(url='https://top.baidu.com/api/board?tab=realtime')）\n"
            "- 确认数据已获取，看到真实内容后，再进入报告生成\n\n"
            "### 2. 生成报告\n"
            "- 使用 write_file 生成 HTML 报告\n"
            "- **报告中必须包含真实数据**（直接嵌入 HTML），不要用占位符或模板\n"
            "- 报告结构：标题、数据列表/表格、来源标注、样式美化\n\n"
            "### 3. 禁止事项\n"
            "- **禁止在 HTML/JS 中调用 fetch_url/web_search**：这些是服务端工具，不是浏览器 API\n"
            "- **禁止跳过数据采集直接生成报告模板**\n"
            "- **禁止用游戏模板替代报告**\n"
            "</report_workflow>\n\n"
            "<task_classification>\n"
            "## 任务类型识别\n"
            "执行前先判断任务类型，使用对应策略：\n\n"
            "| 任务类型 | 关键词 | 执行策略 |\n"
            "|---------|--------|----------|\n"
            "| 创建游戏/应用 | 游戏、猜数字、贪吃蛇、连连看、写一个XX | 直接 write_file 生成完整代码 |\n"
            "| 生成报告/数据页面 | 报告、热搜报告、数据汇总、分析页面、dashboard | **先** web_search/fetch_url 获取数据 → **再** write_file 生成报告 |\n"
            "| 信息查询 | 查一下、搜索、找、百度热搜 | web_search |\n"
            "| 代码执行 | 运行、执行、调试、跑一下 | execute_python |\n\n"
            "**报告类任务的强制路径**：\n"
            "1. 调用 web_search 或 fetch_url 获取真实数据\n"
            "2. 看到工具返回的数据后\n"
            "3. 用 write_file 生成包含真实数据的 HTML 报告\n"
            "**绝对不要**跳过第1步直接生成报告模板！\n"
            "</task_classification>\n\n"
            "<tool_usage>\n"
            "## 工具使用规范\n"
            "- 根据工具的 description 和 parameters 判断何时使用\n"
            "- 一次回复可同时调用多个**无依赖**的工具，减少轮数\n"
            "- 必须调用工具函数来执行操作，**不要只输出命令文本**\n\n"
            "## 联网搜索\n"
            "- 搜索信息: 使用 web_search 工具（推荐 engine='baidu' 用于国内搜索）\n"
            "- 抓取网页: 使用 web_fetch 工具获取URL内容\n"
            "- 获取JSON: 使用 fetch_json 工具获取API数据\n"
            "- 备选方案: fetch_url 工具也可用于获取网页\n"
            "- 搜索百度热搜: 使用 web_search(query='百度热搜', engine='baidu')\n\n"
            "## 代码沙盒\n"
            "- 执行Python代码: 使用 execute_python 工具（沙盒环境，仅用于调试/运行逻辑）\n"
            "- 执行shell命令: 使用 execute_shell 工具\n"
            "- ⚠️ 沙盒无法保存文件，创建游戏/HTML必须用 write_file\n\n"
            "## 内置爬虫（execute_python 隐藏能力）\n"
            "用 execute_python 调用内置爬虫模块获取数据：\n"
            "- from mcp._impl.web_scraper.github_scraper import GitHubScraper; s=GitHubScraper(); s.scrape(action='trending')\n"
            "- from mcp._impl.web_scraper.baidu_scraper import BaiduScraper; s=BaiduScraper(); s.scrape()\n"
            "- from mcp._impl.web_scraper.bilibili_scraper import BilibiliScraper; s=BilibiliScraper(); s.scrape()\n"
            "- from mcp._impl.web_scraper.weibo_scraper import WeiboScraper; s=WeiboScraper(); s.scrape()\n"
            "- from mcp._impl.web_scraper.douyin_scraper import DouyinScraper; s=DouyinScraper(); s.scrape()\n"
            "- ⚠️ 只有上述爬虫模块可用，不要导入 mcp._impl.* 下的其他模块\n"
            "- ⚠️ 写游戏/工具类代码时，直接用标准库（os, sys, json, random, tkinter, pygame 等）\n"
            "- ⚠️ browser_snapshot 只返回无障碍树骨架，不适合数据抓取\n\n"
            "## 输出\n"
            "- **创建游戏/HTML/文件 → 必须用 write_file**，传入 path 和 content 参数\n"
            "- 例如: write_file(path='~/Desktop/game.html', content='完整的HTML代码')\n"
            "- ❌ 禁止用 execute_python 写游戏/HTML（沙盒会清理文件，代码会丢失）\n"
            "- ❌ 禁止用 execute_python 的 open().write() 创建文件\n"
            "- 拿到数据立刻分析使用，最终用文本输出结果\n"
            "- **必须完整输出所有结果，禁止截断或省略！** 搜索/列表类结果必须逐条列出，不得用'更多省略'、'等等'、'...'等方式跳过\n"
            "- **创建游戏时必须生成完整可运行的代码**，包括：\n"
            "  - 完整的 HTML 结构（<!DOCTYPE html>, <html>, <head>, <body>）\n"
            "  - 内联 CSS 样式（<style> 标签）\n"
            "  - 完整的 JavaScript 游戏逻辑（<script> 标签）\n"
            "  - 游戏画面、交互、计分系统\n"
            "  - 示例：植物大战僵尸需要包含：草坪网格、植物选择、僵尸生成、阳光系统、攻击逻辑\n"
            "  - 用一次 write_file 写入完整文件，不要分多次写入\n"
            "- **写入文件后不要输出描述性文字**：不要说'文件已创建'、'你可以通过以下链接查看'，直接结束\n\n"
            "## 代码执行与文件保存流程\n"
            "- **调试代码**：使用 execute_python(mode='sandbox') 在沙盒中调试代码\n"
            "- **保存文件**：sandbox 执行成功后，如果提示'⚠️ 检测到文件写入操作'，必须询问用户确认保存路径\n"
            "- **询问用户**：'代码执行成功，要将文件保存到哪个路径？（推荐：~/Desktop/xxx.ext）'\n"
            "- **写入文件**：用户确认后，使用 write_file(path=用户指定路径, content=完整代码) 写入\n"
            "- **local 模式**：如需直接执行（无沙盒），需用户确认后设置 confirmed=true\n"
            "- **禁止假执行**：不要用 execute_python 的 open().write() 创建文件，sandbox 会清理临时文件\n"
            "</tool_usage>\n\n"
            "<critical_reminders>\n"
            "## 关键提醒\n"
            "1. **澄清优先**: 遇到不确定的问题，先调用 ask_clarification 获取用户确认\n"
            "2. **并行调用**: 无依赖的多个工具调用应放在同一轮中并行执行\n"
            "3. **响应可见**: 每轮思考后必须给出可读的文本响应，不要只进行内部推理\n"
            "4. **语言一致**: 使用与用户相同的语言进行交流（中文用户用中文）\n"
            "5. **结果验证**: 工具返回结果后，先快速验证有效性再继续\n"
            "6. **渐进输出**: 复杂任务分步输出中间结果，最终给出完整总结\n"
            "7. **完整输出**: 搜索结果、列表、数据等必须全部展示，禁止截断、省略或用'更多'代替。用户需要看到每一条结果\n"
            "8. **禁止在生成的HTML中嵌入工具调用**: fetch_url、web_search 等是服务端工具，不是浏览器 API。生成的 HTML 文件中不能包含对这些工具的调用。必须先用工具获取数据，再将数据作为静态内容写入 HTML\n"
            "9. **报告类任务必须先获取数据**: 生成报告/数据页面时，必须先用 web_search 或 fetch_url 获取真实数据，再用 write_file 生成报告。禁止跳过数据采集直接生成模板\n"
            "10. **HTML游戏必须单文件**: 创建游戏/HTML时，所有 JavaScript 和 CSS 必须内联在同一个 HTML 文件中，禁止拆分成 .html + .js + .css 多个文件\n"
            "</critical_reminders>\n\n"
            "<tool_selection>\n"
            "## 工具选择指南\n"
            "根据任务类型选择最合适的工具：\n\n"
            "| 任务类型 | 首选工具 | 备选工具 |\n"
            "|---------|---------|----------|\n"
            "| 搜索信息/查资料 | web_search | fetch_url |\n"
            "| 抓取网页/API数据 | fetch_url | execute_python |\n"
            "| 执行Python脚本/运行代码 | execute_python | execute_shell |\n"
            "| 执行shell命令 | execute_shell | execute_python |\n"
            "| 创建游戏/HTML/文件 | **write_file** | 无 |\n"
            "| **生成报告/数据页面** | **先 web_search → 再 write_file** | fetch_url → write_file |\n"
            "| 读取文件 | execute_python | fetch_url |\n"
            "| 数据分析/图表 | execute_python | rag_search |\n"
            "| 打开应用 | open_app | execute_shell |\n"
            "| 浏览器操作 | browser_* 系列 | execute_python |\n\n"
            "### 重要原则\n"
            "- **创建游戏/HTML/文件必须用 write_file**: 传入 path 和 content，绝对不要用 execute_python\n"
            "- **⚠️ execute_python 无法创建文件**: 沙盒会清理临时文件，用它写游戏/HTML 会丢失所有代码\n"
            "- **创建游戏时**: 必须在一次 write_file 调用中写入完整的代码（Python/HTML+CSS+JS），不要分步写入\n"
            "- **生成报告时**: 必须先用 web_search/fetch_url 获取真实数据，再用 write_file 生成报告\n"
            "- **报告中的数据必须是真实的**: 禁止编造/模拟数据，所有数据必须来自工具获取的结果\n"
            "- **禁止在生成的 HTML 中调用 fetch_url/web_search**: 这些是服务端工具，不是浏览器 API\n"
            "- **execute_python 仅用于**: 在沙盒中执行Python代码、调试逻辑、调用内置爬虫模块\n"
            "- **抓取网页数据优先用爬虫**: 用 execute_python 调用 BaiduScraper/GitHubScraper 等，不要用 Playwright\n"
            "- **减少轮次**: 一轮中并行调用多个无依赖的工具\n"
            "- **不要空转**: 每轮必须调用工具或输出最终答案，不要只描述计划\n"
            "</tool_selection>"
        )
        if plan_context:
            system_content += plan_context
        if ctx.forced_instructions:
            system_content += f"\n\n<forced_instructions>\n{ctx.forced_instructions}\n</forced_instructions>"
            ctx.forced_instructions = ""  # 用完清除
        if ctx.personality_prompt:
            system_content = f"{ctx.personality_prompt}\n\n{system_content}"
        ctx._pending_messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": ctx.task_description},
        ]

        # ── 1. 动态上下文注入（保持 base prompt 静态用于缓存）──
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d, %A")

        dynamic_context = f"\n\n<system_context>\n<current_date>{current_date}</current_date>\n"
        if ctx.tool_results:
            total = len(ctx.tool_results)
            success = sum(1 for r in ctx.tool_results if r.get("success"))
            fail = total - success
            tools_used = list(set(r.get("tool_call", {}).get("name", "") for r in ctx.tool_results))
            dynamic_context += f"<execution_status>已执行{total}轮: {success}成功/{fail}失败, 工具: {', '.join(tools_used[:5])}</execution_status>\n"
        dynamic_context += "</system_context>"
        system_content += dynamic_context

        # ── 2. 反思反馈注入 ──
        if self.agent and hasattr(self.agent, 'temp_memory'):
            reflection = self.agent.temp_memory.get("reflection")
            if reflection:
                problem = reflection.get("problem", "")
                suggestion = reflection.get("suggestion", "")
                if problem:
                    system_content += f"\n\n<reflection>\n上轮反思: {problem}\n建议: {suggestion}\n</reflection>"
            kepa = self.agent.temp_memory.get("kepa_summary")
            if kepa:
                tool = kepa.get("tool", "")
                summary = kepa.get("summary", "")
                if summary:
                    system_content += f"\n\n<kepa_insight>\n工具 {tool} 的结果摘要: {summary}\n</kepa_insight>"

        # ── 2.5 KEPA 知识上下文注入（独立段，不膨胀 task_description）──
        if ctx.knowledge_context:
            system_content += f"\n\n<knowledge_context>\n{ctx.knowledge_context}\n</knowledge_context>"

        # ── 3. 渐进式截断工具结果 ──
        if ctx.tool_results:
            n_results = len(ctx.tool_results)
            for i, r in enumerate(ctx.tool_results):
                tc = r.get("tool_call", {})
                # Progressive truncation: older results get shorter
                age = n_results - i - 1  # 0 = latest, higher = older
                if age > 3:
                    # Very old results: just keep success/fail status
                    tool_content = f"[{tc.get('name', '?')}] {'OK' if r.get('success') else 'FAIL'}"
                elif age > 1:
                    # Older results: truncated to 500 chars
                    raw = _format_tool_result(tc.get('name', ''), r.get('result', r), r.get('success', False), tc.get('arguments', {}))
                    tool_content = raw[:500] + "..." if len(raw) > 500 else raw
                else:
                    # Latest results: full format
                    tool_content = _format_tool_result(tc.get('name', ''), r.get('result', r), r.get('success', False), tc.get('arguments', {}))

                ctx._pending_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.get("id", f"call_{i+1}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("arguments", {})),
                        },
                    }],
                })
                ctx._pending_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{i+1}"),
                    "content": tool_content,
                })

        prefix = self._get_prefix(ctx)
        print(
            f"{prefix}    \033[1;36m🤔 LLM思考第{ctx.react_depth}/{ctx.max_iterations}轮...\033[0m"
        )

        async def _llm_call():
            try:
                llm_timeout = 90 if ctx.react_depth <= 2 else 60
                # 游戏/代码生成任务需要更多 token
                task_lower = ctx.task_description.lower()
                is_code_task = any(kw in task_lower for kw in ["游戏", "html", "代码", "脚本", "python", "javascript", "create", "write", "写"])
                llm_max_tokens = 16000 if (ctx.react_depth <= 2 and is_code_task) else (8000 if ctx.react_depth <= 2 else 4000)
                _model = ctx.model_override or None
                return await asyncio.wait_for(
                    router.chat(
                        ctx._pending_messages,
                        temperature=0.3,
                        max_tokens=llm_max_tokens,
                        tools=ctx.tool_defs or None,
                        model=_model,
                    ),
                    timeout=llm_timeout,
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ 第{ctx.react_depth}轮 LLM调用超时({llm_timeout}s)")
                raise

        try:
            if ctx._chain:
                reply = await ctx._chain.on_wrap_model_call(ctx, _llm_call)
            else:
                reply = await _llm_call()
            ctx._last_reply = reply
        except asyncio.TimeoutError:
            ctx.interrupted = True
            ctx.last_error = "LLM 超时"
        except Exception as e:
            ctx.interrupted = True
            ctx.last_error = str(e)

    async def on_think_end(self, ctx: RunContext) -> None:
        """解析 LLM 回复，执行工具或输出答案"""
        if ctx.interrupted:
            return

        prefix = self._get_prefix(ctx)
        reply = getattr(ctx, "_last_reply", "")
        if not reply:
            logger.warning(f"第{ctx.react_depth}轮 LLM返回空响应")
            if any(r.get("success") for r in ctx.tool_results):
                ctx.final_answer = "已通过工具获取到结果。"
            else:
                ctx.last_error = "LLM返回空响应"
            ctx.interrupted = True
            return

        # 调试：打印 LLM 原始输出（用于调试工具调用解析问题）
        print(f"{prefix}    \033[1;36m📝 LLM原始输出:\033[0m {reply[:500]}...")
        
        tool_calls = self._parse_tool_calls(reply)

        if not tool_calls:
            text = reply.strip()
            # 检测 LLM mock 响应
            if any(sig in text for sig in ["[LLM_MOCK]", "系统正在处理您的请求"]):
                logger.warning("检测到LLM mock/fallback响应")
                # 如果已有成功的工具结果，直接总结输出，不跳过
                if any(r.get("success") for r in ctx.tool_results):
                    logger.info("已有工具结果，尝试直接总结")
                    ctx.task_description += "\n[注意] LLM不可用，但已有工具返回结果。请基于已有结果生成最终回答，完整输出所有内容，不要截断。"
                    return
                ctx.task_description += "\n[注意] 上轮LLM返回了空响应，请重新尝试。"
                return

            # 检测是否是中间步骤说明（而非最终答案）
            is_intermediate_step = False
            # 默认值：后续检测如用到 has_code_block 但未赋值时安全兜底
            has_code_block = "```" in text

            # ── 检测0: 放弃性语言（LLM 试图放弃/逃避）──
            # 注意: "找不到" "无法" 等常用于报告错误，不一定是放弃
            # 只有同时没有工具调用 + 纯放弃性语言时才判定为放弃
            surrender_keywords_strict = [
                "很抱歉", "抱歉", "没办法", "做不到", "不能完成",
                "请告诉我", "请提供", "我不确定", "我无法完成",
                "建议您", "请检查一下", "请您",
            ]
            has_surrender_strict = any(kw in text for kw in surrender_keywords_strict)
            # 轻度放弃词（需要结合是否有工具调用来判断）
            surrender_keywords_mild = ["无法", "找不到", "没有找到", "不存在", "不能"]
            has_surrender_mild = any(kw in text for kw in surrender_keywords_mild)
            # 检查文本中是否有工具调用（即使被标记为放弃，如果有工具调用说明在积极修复）
            has_tool_call_in_text = any(t in text for t in ["write_file(", "execute_python", "execute_shell", "web_search", "browser_"])
            has_action_plan = any(kw in text for kw in ["执行", "运行", "安装", "尝试", "修复", "解决"])
            
            # 严格放弃词 → 直接判定
            # 轻度放弃词 + 无工具调用 + 无行动计划 → 判定为放弃
            is_surrender = has_surrender_strict or (has_surrender_mild and not has_tool_call_in_text and not has_action_plan)
            
            if is_surrender and ctx.tool_results:
                # 有工具结果 + 放弃性语言 → LLM 在逃避，强制结束
                print(f"{prefix}    \033[1;31m🚫 检测到放弃性语言，强制结束\033[0m")
                ctx.final_answer = text
                ctx.interrupted = True
                return

            # ── 检测1: 第一轮无工具调用，纯文本输出 → 几乎肯定是计划，不是最终答案 ──
            if not ctx.tool_results and ctx.react_depth <= 1:
                plan_keywords = ["步骤", "首先", "然后", "接下来", "需要", "使用", "将要",
                                 "计划", "设计", "创建", "实现", "配置", "完成",
                                 "我将", "我会", "现在", "第1步", "第2步", "第一步", "第二步",
                                 "现在开始", "现在我", "下面", "以上", "以下是"]
                has_plan_signal = any(kw in text for kw in plan_keywords)
                has_code_block = "```" in text
                # 检测到 write_file 工具调用（真正的工具调用，不是描述）
                has_tool_call = "write_file" in text and ("path=" in text or "content=" in text or "{" in text)
                # 没有实际代码输出 + 有计划关键词 + 没有工具调用 → 空转
                if has_plan_signal and not has_code_block and not has_tool_call:
                    is_intermediate_step = True
                # 有代码块但无工具结果 + 有计划关键词 → 也是空转（代码只是描述中的示例片段，不是实际写入）
                elif has_code_block and has_plan_signal and not has_tool_call:
                    is_intermediate_step = True
                # 有"第X步"这种格式 → 明确是计划，空转
                elif re.search(r'第\d+步|第[一二三四五六七八九十]+步', text):
                    is_intermediate_step = True

            # ── 检测2: 报告类任务必须先获取数据 ──
            if not is_intermediate_step:
                task_lower = ctx.task_description.lower()
                is_report_task = any(kw in task_lower for kw in 
                    ["报告", "数据报告", "汇总", "热搜报告", "分析页面", "dashboard", "数据页面", "热榜"])
                if is_report_task and not ctx.tool_results and ctx.react_depth <= 1:
                    # 报告任务第一轮必须先获取数据
                    has_fetch = any(t in text for t in ["web_search", "fetch_url"])
                    if not has_fetch:
                        is_intermediate_step = True
                        ctx.forced_instructions = (
                            "这是报告生成任务！你必须先获取数据！\n"
                            "禁止直接生成报告模板！\n"
                            "第一步：调用 web_search(query='百度热搜') 或 fetch_url 获取真实数据\n"
                            "第二步：等工具返回数据后，再用 write_file 生成包含真实数据的报告\n"
                            "现在立即调用 web_search 或 fetch_url 工具获取数据！"
                        )

            # ── 检测3: 短文本 + 包含行动指令关键词 + 没有实际数据输出 → 可能是空转 ──
            if not is_intermediate_step and len(text) < 300:
                action_keywords = ["请用", "请使用", "下一步", "接下来", "然后", "需要", "应该", "可以", "试试", "建议", "推荐"]
                has_action = any(kw in text for kw in action_keywords)
                has_data = any(c.isdigit() for c in text) or "http" in text or "```" in text or len(text) > 150
                if has_action and not has_data:
                    is_intermediate_step = True

            # ── 检测3: 累计空转检测（连续N轮无工具调用）──
            if is_intermediate_step:
                ctx.consecutive_idle_rounds += 1
            else:
                ctx.consecutive_idle_rounds = 0  # 有实质输出，重置计数

            # 连续空转超过2轮 → 直接终止，不再诱导
            if ctx.consecutive_idle_rounds >= 2 and ctx.react_depth < ctx.max_iterations:
                print(f"{prefix}    \033[1;31m🚫 连续{ctx.consecutive_idle_rounds}轮空转，强制结束\033[0m")
                if ctx.tool_results:
                    # 已有工具结果，基于结果生成最终答案
                    ctx.task_description += "\n[注意] LLM连续多轮未调用工具。请基于已有工具结果直接生成最终答案，不要再调用工具。"
                else:
                    ctx.interrupted = True
                    ctx.last_error = "LLM连续多轮未调用工具，任务无法完成"
                return

            if is_intermediate_step and ctx.react_depth < ctx.max_iterations:
                # ── 已有成功工具结果 + LLM 输出描述文字 → 任务已完成，直接结束 ──
                if ctx.tool_results and any(r.get("success") for r in ctx.tool_results):
                    print(f"{prefix}    \033[1;32m✅ 已有工具结果，任务完成，直接结束\033[0m")
                    ctx.final_answer = text
                    ctx.interrupted = True
                    return

                # 没有工具结果的空转，诱导继续执行
                idle_hint = ""
                if ctx.consecutive_idle_rounds >= 1:
                    idle_hint = f"\n⚠️ 你已经连续{ctx.consecutive_idle_rounds + 1}轮没有调用工具了！"
                print(
                    f"{prefix}    \033[1;33m⚠️ LLM返回了计划说明但未调用工具，诱导继续执行\033[0m"
                )
                ctx.forced_instructions = (
                    f"禁止输出计划！你必须立即调用工具！{idle_hint}\n"
                    "不要输出'第1步...'、'首先...'、'我将...'等描述文字！\n"
                    "直接调用 write_file 工具：\n"
                    "write_file(path='~/Desktop/game.html', content='完整的HTML代码')\n"
                    "你的回复必须是工具调用，不能是纯文本！"
                )
                return

            # 完整性校验：生成文件类任务，检查文件是否真的包含可执行代码
            if not ctx.tool_results and ctx.react_depth <= 1:
                # 第一轮无工具结果+纯文本输出 → 不允许直接当最终答案
                is_code_task = any(kw in ctx.task_description.lower() for kw in ["游戏", "html", "代码", "脚本", "python", "写", "创建"])
                if is_code_task and not has_code_block:
                    print(f"{prefix}    \033[1;33m⚠️ 写代码任务需先调用工具，禁止纯文本结束\033[0m")
                    ctx.forced_instructions = (
                        "这是创建文件/游戏任务！\n"
                        "你必须立即调用 write_file 工具，传入 path 和 content 参数。\n"
                        "例如：write_file(path='~/Desktop/game.html', content='完整的HTML代码')\n"
                        "不要输出计划描述，直接调用工具！"
                    )
                    return

            # 完整性校验：写 HTML 文件后检查是否包含 JS 逻辑
            if ctx.tool_results:
                write_results = [r for r in ctx.tool_results
                    if r.get("tool_call", {}).get("name") == "write_file" and r.get("success")]
                if write_results:
                    for wr in write_results:
                        args = wr.get("tool_call", {}).get("arguments", {})
                        path = args.get("path", "") if isinstance(args, dict) else ""
                        content = args.get("content", "") if isinstance(args, dict) else ""
                        if path.endswith(".html"):
                            # ── 磁盘验证：读回实际文件对比 ──
                            actual_content = ""
                            abs_path = os.path.expanduser(path)
                            try:
                                with open(abs_path, "r", encoding="utf-8") as f:
                                    actual_content = f.read()
                            except Exception as e:
                                logger.warning(f"无法读回文件 {path}: {e}")

                            # 对比实际文件 vs 传入内容
                            if actual_content and len(actual_content) < len(content) * 0.5:
                                logger.warning(f"文件 {path} 实际大小({len(actual_content)}) 远小于传入内容({len(content)})，可能写入不完整")
                                ctx.forced_instructions = (
                                    f"文件 {path} 写入不完整！传入了{len(content)}字符但文件只有{len(actual_content)}字符。\n"
                                    "请重新用 write_file 写入完整代码。确保：\n"
                                    "1. content 参数包含完整的 HTML（从 <!DOCTYPE html> 到 </html>）\n"
                                    "2. 包含 <style> CSS样式\n"
                                    "3. 包含 <script> JavaScript游戏逻辑\n"
                                    "4. 不要用省略号或占位符\n"
                                    "直接调用 write_file(path='{path}', content='完整代码')"
                                )
                                return

                            # 用实际文件内容做后续检查
                            check_content = actual_content if actual_content else content
                            content_stripped = check_content.rstrip()
                            is_truncated = (not content_stripped.endswith("</html>") and 
                                          not content_stripped.endswith("</HTML>") and
                                          not content_stripped.endswith("</body>") and
                                          not content_stripped.endswith("</script>"))
                            
                            if is_truncated and len(check_content) < 2000:
                                logger.warning(f"HTML文件 {path} 内容被截断 ({len(check_content)}字符)，末尾: ...{check_content[-50:]}")
                                ctx.forced_instructions = (
                                    f"文件 {path} 内容被截断（只有{len(check_content)}字符），不是完整代码！\n"
                                    "你必须用 write_file 一次性写入完整的 HTML 文件，包括：\n"
                                    "- <!DOCTYPE html> 声明\n"
                                    "- <style> 标签（CSS样式）\n"
                                    "- <script> 标签（JavaScript游戏逻辑）\n"
                                    "- </html> 结束标签\n\n"
                                    "例如：write_file(path='~/Desktop/game.html', content='<!DOCTYPE html>...完整的HTML代码...')\n"
                                    "不要输出计划描述，直接调用工具！"
                                )
                                return
                            
                            has_style = "<style" in check_content
                            has_script = "<script" in check_content
                            has_doctype = "<!doctype" in check_content.lower() or "<!DOCTYPE" in check_content
                            has_closing_html = "</html>" in check_content.lower()
                            
                            # 检查script标签内容是否为空
                            has_script_content = False
                            if has_script:
                                import re as _re
                                script_match = _re.search(r'<script>(.*?)</script>', check_content, _re.DOTALL)
                                if script_match:
                                    script_content = script_match.group(1).strip()
                                    # 排除纯注释或空内容
                                    script_content_clean = _re.sub(r'//.*?$', '', script_content, flags=_re.MULTILINE)
                                    script_content_clean = _re.sub(r'/\*.*?\*/', '', script_content_clean, flags=_re.DOTALL)
                                    has_script_content = len(script_content_clean.strip()) > 10
                            
                            if not has_script or not has_style or not has_doctype or not has_closing_html or not has_script_content:
                                missing = []
                                if not has_doctype: missing.append("DOCTYPE")
                                if not has_script: missing.append("JavaScript逻辑(<script>)")
                                elif not has_script_content: missing.append("JavaScript代码内容(当前只有注释)")
                                if not has_style: missing.append("CSS样式(<style>)")
                                if not has_closing_html: missing.append("</html>结束标签")
                                logger.warning(f"HTML文件 {path} 缺少: {', '.join(missing)}")
                                ctx.forced_instructions = (
                                    f"文件 {path} 不完整，缺少: {', '.join(missing)}\n"
                                    "请重新用 write_file 写入包含完整 HTML 结构的文件。\n"
                                    "你的 <script> 标签中必须包含实际的JavaScript游戏逻辑代码，不能只有注释！\n"
                                    "格式：write_file(path='~/Desktop/game.html', content='<!DOCTYPE html>...')\n"
                                    "你的回复必须是工具调用，不能是纯文本！"
                                )
                                return

            # 完整性校验：如果工具返回了列表类数据，检查 LLM 是否明确表示截断
            if ctx.tool_results and ctx.react_depth < ctx.max_iterations:
                truncated = False
                
                # 只检测明确的截断信号（文本末尾的省略）
                text_stripped = text.rstrip()
                # 1. 文本以省略号结尾（明确表示未完成）
                if text_stripped.endswith("...") or text_stripped.endswith("…"):
                    truncated = True
                # 2. 包含"更多省略"等明确截断表述
                explicit_truncation = ["更多省略", "更多结果省略", "更多话题省略"]
                if any(sig in text for sig in explicit_truncation):
                    truncated = True

                if truncated:
                    print(f"{prefix}    \033[1;33m⚠️ LLM输出被截断，强制要求完整输出\033[0m")
                    # 获取工具返回的完整条目数，注入到提示中
                    last_tool_text = ""
                    for r in reversed(ctx.tool_results):
                        if r.get("success"):
                            raw = r.get("result", {})
                            if isinstance(raw, dict):
                                for key in ("content", "text", "output", "result", "data"):
                                    if key in raw:
                                        last_tool_text = str(raw[key])
                                        break
                            else:
                                last_tool_text = str(raw)
                            break
                    import re as _re
                    item_count = len(_re.findall(r'(?:^|\n)\s*\d+[\.\、]', last_tool_text))
                    ctx.task_description += (
                        f"\n[注意] 上一轮你的回答被截断了！工具返回了 {item_count} 条结果，"
                        f"但你只输出了前几条。你必须完整输出所有 {item_count} 条结果，"
                        f"逐条列出，禁止省略、截断或用'更多'代替。请重新生成完整答案。"
                    )
                    return

            # 纯文本 = 最终答案
            print(f"{prefix}    \033[32m✅ LLM输出最终答案\033[0m")
            ctx.final_answer = text
            ctx.interrupted = True
            return

        # ── 无关工具调用过滤 ──
        # 浏览器工具：只有在已成功调用过 browser_navigate 后才允许
        _browser_was_used = any(
            r.get("tool_call", {}).get("name") == "browser_navigate" and r.get("success")
            for r in ctx.tool_results
        )
        _browser_only_tools = {
            "browser_close", "browser_snapshot", "browser_click", "browser_type",
            "browser_hover", "browser_take_screenshot", "browser_evaluate",
            "browser_fill_form", "browser_select_option", "browser_wait_for",
            "browser_drag", "browser_tabs", "browser_press_key", "browser_resize",
            "browser_file_upload", "browser_network_requests",
        }
        valid_tool_calls = []
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            if name in _browser_only_tools and not _browser_was_used:
                logger.warning(f"阻止无关浏览器工具调用: {name}")
                continue
            valid_tool_calls.append(tc)

        if not valid_tool_calls:
            print(f"{prefix}    \033[1;33m⚠️ 工具调用被过滤（浏览器未打开），强制使用其他工具\033[0m")
            ctx.forced_instructions = (
                "你刚才调用的全都是浏览器工具，但浏览器尚未启动！"
                "请使用 web_search、fetch_url 或 execute_python（内置爬虫）来获取数据，不要使用浏览器相关工具。"
            )
            return

        tool_calls = valid_tool_calls

        # 执行工具调用
        tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
        print(f"{prefix}    \033[1;33m🔧 调用: {', '.join(tool_names)}\033[0m")

        # Separate write_todos from real tool calls
        real_tool_calls = []
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            if name == "write_todos":
                try:
                    args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    todos = args.get("todos", [])
                    if todos:
                        done = sum(1 for t in todos if t.get("status") == "completed")
                        total = len(todos)
                        pending = [t.get("content", "") for t in todos if t.get("status") != "completed"]
                        progress = f"[任务进度] {done}/{total} 完成"
                        if pending:
                            progress += f", 待办: {', '.join(pending[:3])}"
                        ctx.task_description += f"\n{progress}"
                        ctx.tool_results.append({
                            "tool_call": {"name": "write_todos", "arguments": args, "id": tc.get("id", "")},
                            "success": True,
                            "result": {"message": f"任务清单已更新: {done}/{total} 完成"},
                        })
                except (json.JSONDecodeError, TypeError):
                    pass
            else:
                real_tool_calls.append(tc)

        if real_tool_calls:
            results = await self._execute_tool_calls_parallel(real_tool_calls, ctx)
        else:
            results = []

        # Process real tool call results
        for tc, result in zip(real_tool_calls, results):
            name = tc.get("function", {}).get("name", "?")
            ok = result.get("success", False)
            icon = "✅" if ok else "⚠️"
            detail = ""
            if ok:
                result_preview = str(result.get("result", ""))[:80]
                # write_file 也显示结果摘要
                if result_preview:
                    detail = f" → {result_preview[:60]}"
            else:
                # 错误可能在顶层 (MiddlewareChain) 或 result.error 下 (超时/异常)
                err = (
                    result.get("error")
                    or result.get("result", {}).get("error", "")
                    or str(result.get("result", ""))[:60]
                )
                detail = f" {err[:60]}" if err else " (执行失败，无错误信息)"
            print(f"{prefix}    \033[1;32m{icon} {name}{detail}\033[0m")

            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            ok = result.get("success", False)
            quality = result.get("quality", "success" if ok else "fail")
            ctx.tool_results.append(
                {
                    "tool_call": {
                        "name": name,
                        "arguments": args,
                        "id": tc.get("id", ""),
                    },
                    "success": ok,
                    "result": result.get("result", result),
                    "quality": quality,
                    "degraded_from": result.get("degraded_from"),
                }
            )

            # ── write_file 完整性校验：检查代码文件是否完整 ──
            if ok and name == "write_file":
                path = args.get("path", "") if isinstance(args, dict) else ""
                content = args.get("content", "") if isinstance(args, dict) else ""
                
                # ── 磁盘验证：读回实际文件对比 ──
                abs_path = os.path.expanduser(path) if path else ""
                actual_content = ""
                if abs_path:
                    try:
                        with open(abs_path, "r", encoding="utf-8") as f:
                            actual_content = f.read()
                    except Exception as e:
                        logger.warning(f"无法读回文件 {path}: {e}")
                        actual_content = ""

                if not actual_content:
                    # 文件不存在或无法读取 → 强制重写
                    logger.error(f"文件 {path} 写入后无法读取！传入了{len(content)}字符")
                    print(f"{prefix}    \033[1;31m❌ 文件 {path} 写入失败（磁盘上不存在）！\033[0m")
                    ctx.forced_instructions = (
                        f"文件 {path} 写入失败！磁盘上不存在该文件。\n"
                        "请重新调用 write_file 写入完整代码。\n"
                        f"路径: {path}\n"
                        "内容必须包含完整的 HTML/CSS/JavaScript。"
                    )
                elif len(actual_content) < len(content) * 0.5 and len(content) > 100:
                    # 文件比传入内容小很多 → 写入不完整
                    logger.warning(f"文件 {path} 实际大小({len(actual_content)}) 远小于传入内容({len(content)})")
                    print(f"{prefix}    \033[1;33m⚠️ 文件写入不完整: 传入{len(content)}字符, 实际{len(actual_content)}字符\033[0m")
                    ctx.forced_instructions = (
                        f"文件 {path} 写入不完整！传入了{len(content)}字符但文件只有{len(actual_content)}字符。\n"
                        "请重新用 write_file 写入完整代码。"
                    )
                elif content and len(actual_content) < len(content) * 0.8:
                    # 文件略有截断但不算严重
                    logger.info(f"文件 {path} 略有截断: 传入{len(content)}, 实际{len(actual_content)}")
                
                if content:
                    # 根据文件扩展名进行完整性校验
                    needs_regeneration = False
                    missing_parts = []
                    
                    # HTML 文件校验 — 只检查基本结构，不强制 script/style（静态报告不需要）
                    if path.endswith((".html", ".htm")):
                        content_lower = content.lower()
                        has_doctype = "<!doctype" in content_lower or "<!DOCTYPE" in content
                        has_html = "<html" in content_lower
                        
                        # 只有 DOCTYPE 和 html 标签都缺失才需要重新生成
                        if not has_doctype and not has_html:
                            needs_regeneration = True
                            missing_parts.append("基本 HTML 结构 (DOCTYPE + <html>)")
                    
                    # Python 文件校验
                    elif path.endswith(".py"):
                        has_def = "def " in content
                        has_class = "class " in content
                        has_import = "import " in content or "from " in content
                        has_main = 'if __name__' in content or 'def main' in content
                        has_print = "print(" in content
                        
                        # 检查是否只是空壳或简单打印
                        if len(content) < 100 and not has_def and not has_class:
                            needs_regeneration = True
                            missing_parts.append("完整的函数/类定义")
                        if not has_print and not has_def and not has_class:
                            missing_parts.append("实际执行逻辑")
                    
                    # JavaScript/TypeScript 文件校验
                    elif path.endswith((".js", ".ts", ".jsx", ".tsx")):
                        has_function = "function " in content or "=>" in content or "async " in content
                        has_const_let = "const " in content or "let " in content or "var " in content
                        has_export = "export " in content or "module.exports" in content
                        
                        if len(content) < 100 and not has_function:
                            needs_regeneration = True
                            missing_parts.append("函数定义")
                    
                    # CSS 文件校验
                    elif path.endswith((".css", ".scss", ".less")):
                        has_selector = "{" in content and "}" in content
                        has_property = ":" in content
                        
                        if len(content) < 50:
                            needs_regeneration = True
                            missing_parts.append("完整的 CSS 规则")
                    
                    # 通用代码文件校验（太短可能只是占位符）
                    elif len(content) < 50 and any(kw in path for kw in ["game", "Game", "app", "App", "main", "Main"]):
                        needs_regeneration = True
                        missing_parts.append("完整的代码实现")
                    
                    # 生成警告信息
                    if needs_regeneration:
                        logger.warning(f"文件 {path} 内容不完整，缺少: {', '.join(missing_parts)}")
                        print(f"{prefix}    \033[1;33m⚠️ 文件内容不完整，诱导补充完整代码\033[0m")
                        ctx.forced_instructions = (
                            f"文件 {path} 内容不完整！缺少：{', '.join(missing_parts)}\n"
                            f"你必须重新用 write_file 写入完整的代码文件！\n"
                            "使用 write_file(path='原路径', content='完整代码') 重新写入。"
                        )
                    elif missing_parts:
                        # 轻微问题，只警告不强制
                        logger.info(f"文件 {path} 可能缺少: {', '.join(missing_parts)}")
                
                # ── 截断检测：读回文件检查是否缺少闭合标签，注入续写指令 ──
                if actual_content and path.endswith(('.html', '.htm')):
                    actual_lower = actual_content.lower()
                    missing_close = []
                    if '<script' in actual_lower and '</script>' not in actual_lower:
                        missing_close.append("</script>")
                    if '<style' in actual_lower and '</style>' not in actual_lower:
                        missing_close.append("</style>")
                    if '<body' in actual_lower and '</body>' not in actual_lower:
                        missing_close.append("</body>")
                    if '</html>' not in actual_lower:
                        missing_close.append("</html>")
                    
                    if missing_close:
                        print(f"{prefix}    \033[1;33m⚠️ 文件被截断，缺少: {', '.join(missing_close)}，注入续写指令\033[0m")
                        ctx.forced_instructions = (
                            f"代码被截断！文件 {path} 缺少: {', '.join(missing_close)}\n"
                            f"当前文件已有 {len(actual_content)} 字符。\n"
                            "请使用 write_file 继续生成剩余代码。\n"
                            "重要：在 content 参数中只写缺失的部分（从断点继续），不要重复已有内容。\n"
                            f"路径: {path}\n"
                            "示例：write_file(path='同上', content='缺失的HTML/JS代码...')"
                        )
                    # 检测 <script> 只有注释没有实际代码
                    elif '<script' in actual_lower:
                        import re
                        script_match = re.search(r'<script[^>]*>(.*?)</script>', actual_content, re.DOTALL | re.IGNORECASE)
                        if script_match:
                            script_body = script_match.group(1).strip()
                            # 去掉注释后检查是否有实际代码
                            code_only = re.sub(r'//.*?\n', '\n', script_body)
                            code_only = re.sub(r'/\*.*?\*/', '', code_only, flags=re.DOTALL)
                            code_only = code_only.strip()
                            if len(code_only) < 20:
                                print(f"{prefix}    \033[1;33m⚠️ <script> 中只有注释没有实际代码，注入补充指令\033[0m")
                                ctx.forced_instructions = (
                                    f"文件 {path} 的 <script> 标签中只有注释，没有实际的 JavaScript 代码！\n"
                                    "你必须用 write_file 写入包含完整游戏逻辑的代码。\n"
                                    "content 参数必须包含完整的 HTML+CSS+JavaScript，不能只有注释。\n"
                                    f"路径: {path}"
                                )

            # ── Tail Call 自动机：自动执行链式调用（最多 depth=3）──
            tail_call_data = result.get("tail_call")
            if tail_call_data and ok:
                from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                tc_handler = get_tail_call_handler()
                tc_depth = 0
                while tail_call_data and tc_depth < 3:
                    tc_name = tail_call_data.get("tool_name", "")
                    tc_args = tail_call_data.get("arguments", {})
                    if not tc_name:
                        break
                    logger.info(f"Tail Call 自动执行 [{tc_depth+1}/3]: {tc_name}")
                    tc_registry = get_tool_registry()
                    tc_func = tc_registry.get_handler(tc_name)
                    if not tc_func:
                        logger.warning(f"Tail Call: 未找到 handler {tc_name}")
                        break
                    try:
                        tc_result = await tc_func(tc_args)
                        ctx.tool_results.append(
                            {
                                "tool_call": {"name": tc_name, "arguments": tc_args},
                                "success": True,
                                "result": tc_result,
                                "quality": "tail_call",
                            }
                        )
                        # 检查是否有下一个 tail call
                        next_tc = tc_handler.extract_tail_call(tc_result)
                        if next_tc:
                            tail_call_data = {
                                "tool_name": next_tc.tool_name,
                                "arguments": next_tc.arguments,
                            }
                            tc_depth += 1
                        else:
                            tail_call_data = None
                    except Exception as e:
                        logger.warning(f"Tail Call 执行失败: {tc_name} - {e}")
                        break

            # 代码错误修复提示（检查 result 内容，不仅靠 success 标志）
            if ctx.react_depth < ctx.max_iterations:
                raw = str(result.get("result", {}))
                err_text = raw[:500]
                if any(
                    kw in err_text
                    for kw in ["❌", "SyntaxError", "NameError", "TypeError", "ModuleNotFoundError", "ImportError", "Error:"]
                ):
                    # 提取简洁的错误信息
                    error_detail = ""
                    if "❌" in err_text:
                        # 提取 ❌ 后面的错误信息
                        parts = err_text.split("❌")
                        if len(parts) > 1:
                            error_detail = parts[1].strip()[:200]
                    
                    if not error_detail:
                        # 尝试提取常见错误模式
                        import re
                        error_match = re.search(r'(Error|Exception):?\s*([^\n]+)', err_text)
                        if error_match:
                            error_detail = error_match.group(0)[:200]
                        else:
                            error_detail = err_text[:200]
                    
                    # 针对模块导入错误提供具体建议
                    module_hint = ""
                    if "ModuleNotFoundError" in err_text or "ImportError" in err_text:
                        module_hint = (
                            "\n注意：你只能使用系统已安装的模块（os, sys, json, random, tkinter, pygame 等）"
                            "\n不要尝试导入 mcp._impl.* 等内部模块，使用 execute_python 直接写代码"
                        )
                    
                    fix_prompt = (
                        f"\n[代码错误] 上次代码执行失败: {error_detail}"
                        f"{module_hint}\n"
                        f"请检查代码并修复错误后重试。"
                    )
                    ctx.task_description += fix_prompt
                    print(f"{prefix}    \033[1;31m⚠️ 代码出错: {error_detail[:100]}\033[0m")

        # 达到轮次上限且没有 final_answer → 用已有结果
        if ctx.react_depth >= ctx.max_iterations and not ctx.final_answer:
            has_success = any(r.get("success") for r in ctx.tool_results)
            if has_success:
                last = ctx.tool_results[-1]
                text = str(last.get("result", last.get("error", "")))
                ctx.final_answer = text[:500] if text and text != "None" else ""
            if not ctx.final_answer:
                ctx.last_error = "步骤未实际执行任何工具调用"
            ctx.interrupted = True

    _TOOL_TIMEOUTS = {
        "fetch_url": 30,
        "execute_python": 20,
        "execute_shell": 15,
        "write_file": 10,
        "rag_search": 20,
    }
    _DEFAULT_TIMEOUT = 15

    async def _execute(self, tc: dict, ctx: Optional[RunContext] = None) -> dict:
        """执行单个工具调用，支持自动重试 + Tail Call

        Returns:
            dict: 包含 success, result, quality 字段
            - quality: "success" | "partial_success" | "fail" | "timeout" | "retry_success"
        """
        tool_name = tc.get("function", {}).get("name", "")
        # 容错解析 arguments JSON（长代码内容可能含特殊字符）
        try:
            arguments = json.loads(tc.get("function", {}).get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            arguments = {}
            logger.warning(f"工具 {tool_name} 的 arguments JSON 解析失败，使用空参数")
        tool_args = {
            "name": tool_name,
            "arguments": arguments,
            "_tool_name": tool_name,
            "_server": self._lookup_server(tool_name, ctx),
        }
        timeout = self._TOOL_TIMEOUTS.get(tool_name, self._DEFAULT_TIMEOUT)

        # 可重试的工具类型（网络请求、临时错误）
        _RETRYABLE_TOOLS = {"fetch_url", "rag_search", "execute_python"}

        # RecoveryManager 重试决策（可用时优先使用）
        _recovery_mgr = None
        try:
            from core.multi_agent_v2.tools.recovery import get_recovery_manager
            _recovery_mgr = get_recovery_manager()
        except Exception:
            pass

        async def _do_execute():
            if ctx and hasattr(ctx, "_chain") and ctx._chain:
                return await ctx._chain.on_wrap_tool_call(ctx, tool_args)
            return {"success": False, "error": "no chain", "tool_call": tool_args}

        last_error = None
        max_attempts = 2
        if _recovery_mgr:
            max_attempts = _recovery_mgr.retry_config.max_retries + 1
        for attempt in range(max_attempts):
            try:
                result = await asyncio.wait_for(_do_execute(), timeout=timeout)
                # 添加质量标识
                if result.get("success"):
                    result["quality"] = "retry_success" if attempt > 0 else "success"

                    # 检查 Tail Call
                    from core.multi_agent_v2.tools.tail_call import get_tail_call_handler
                    handler = get_tail_call_handler()
                    tail_call = handler.extract_tail_call(result.get("result"))
                    if tail_call:
                        result["tail_call"] = {
                            "tool_name": tail_call.tool_name,
                            "arguments": tail_call.arguments,
                            "reason": tail_call.reason,
                        }
                        logger.info(f"检测到 Tail Call: {tail_call.tool_name}")

                else:
                    # 检查是否是可重试的错误
                    err_text = str(result.get("result", {}).get("error", ""))
                    if _recovery_mgr:
                        # RecoveryManager 分类 + 重试决策
                        try:
                            err_exc = RuntimeError(err_text)
                            plan = _recovery_mgr.create_recovery_plan(tool_name, err_exc, attempt)
                            is_retryable = plan.strategy == "retry"
                        except Exception:
                            is_retryable = False
                    else:
                        # 内联 fallback：关键词匹配
                        is_retryable = tool_name in _RETRYABLE_TOOLS and any(
                            kw in err_text for kw in ["timeout", "connection", "network", "503", "502", "429"]
                        )
                    if is_retryable and attempt < max_attempts - 1:
                        last_error = result
                        # RecoveryManager 指数退避延迟
                        if _recovery_mgr:
                            delay = _recovery_mgr.get_retry_delay(attempt)
                            await asyncio.sleep(delay)
                        continue  # 重试
                    result["quality"] = "fail"
                return result
            except asyncio.TimeoutError:
                if attempt < max_attempts - 1 and tool_name in _RETRYABLE_TOOLS:
                    if _recovery_mgr:
                        delay = _recovery_mgr.get_retry_delay(attempt)
                        await asyncio.sleep(delay)
                    continue  # 超时可重试
                return {
                    "success": False,
                    "result": {"error": f"工具 {tool_name} 执行超时({timeout}s)"},
                    "quality": "timeout",
                }
            except Exception as e:
                if attempt < max_attempts - 1 and tool_name in _RETRYABLE_TOOLS:
                    if _recovery_mgr:
                        delay = _recovery_mgr.get_retry_delay(attempt)
                        await asyncio.sleep(delay)
                    continue  # 异常可重试
                return {"success": False, "result": {"error": str(e)}, "quality": "fail"}

        # 重试后仍失败，返回最后一次错误
        if last_error:
            last_error["quality"] = "fail"
            return last_error
        return {"success": False, "result": {"error": "重试耗尽"}, "quality": "fail"}

    async def _execute_tool_calls_parallel(
        self, tool_calls: list, ctx: RunContext
    ) -> list:
        """并行执行工具调用，支持失败降级

        降级规则（使用 RecoveryManager）：
        - 同一工具连续失败超过3次 → 查询 RecoveryManager 获取降级工具
        - 无降级配置 → 降级为 execute_python 并给出诊断提示
        - 所有工具失败 → 返回错误信息
        """
        tool_fail_counts = ctx.consecutive_failures

        # 获取 RecoveryManager 实例（可用时使用，不可用时降级到硬编码逻辑）
        _recovery_mgr = None
        try:
            from core.multi_agent_v2.tools.recovery import get_recovery_manager
            _recovery_mgr = get_recovery_manager()
        except Exception:
            pass

        async def _run_one(tc):
            tool_name = tc.get("function", {}).get("name", "")
            fail_count = tool_fail_counts.get(tool_name, 0)

            # ── 相同代码重复失败检测 ──
            # 对 execute_python：如果同一段代码已失败2次，直接跳过并注入错误提示
            if tool_name == "execute_python" and ctx:
                try:
                    _args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    _code = _args.get("code", "")
                    if _code:
                        import hashlib
                        _code_hash = hashlib.md5(_code.encode()).hexdigest()[:12]
                        _prev_fails = ctx._failed_code_hashes.get(_code_hash, 0)
                        if _prev_fails >= 2:
                            logger.warning(f"🔄 相同代码已失败{_prev_fails}次，跳过执行: {_code[:60]}...")
                            return {
                                "success": False,
                                "result": {
                                    "error": f"相同代码已失败{_prev_fails}次。请不要重复执行相同代码。\n"
                                    f"建议：如果是创建文件任务，请使用 write_file 工具；\n"
                                    f"如果是执行代码，请修改代码后再试。"
                                },
                                "quality": "fail",
                                "tool_call": {"name": tool_name, "arguments": _args},
                                "_skipped_duplicate": True,
                            }
                except (json.JSONDecodeError, TypeError):
                    pass

            # 连续失败超过3次，降级（execute_python 也包含在内）
            # 注意：write_file 降级时不要降到 execute_python，否则文件永远写不进去
            if fail_count >= 3:
                # 优先用 RecoveryManager 查降级工具
                fallback_tool = None
                if _recovery_mgr:
                    try:
                        fallback_tool = _recovery_mgr.get_fallback_tool(tool_name)
                    except Exception:
                        pass

                if not fallback_tool:
                    # write_file 降级时仍用 write_file（强制重试），不降级到 execute_python
                    if tool_name == "write_file":
                        fallback_tool = "write_file"
                    else:
                        fallback_tool = "execute_python"

                degraded_tc = json.loads(json.dumps(tc))
                degraded_tc["function"]["name"] = fallback_tool
                if fallback_tool == "execute_python":
                    degraded_tc["function"]["arguments"] = json.dumps({
                        "code": f"# 工具 {tool_name} 连续失败{fail_count}次，降级到 {fallback_tool}\nprint('工具降级: {tool_name} → {fallback_tool}，请检查工具配置')"
                    }, ensure_ascii=False)
                else:
                    # 降级到其他工具时，保留原始参数（由目标工具尝试解析）
                    pass
                result = await self._execute(degraded_tc, ctx)
                result["quality"] = "degraded"
                result["degraded_from"] = tool_name
                return result

            try:
                result = await self._execute(tc, ctx)
                if result.get("success"):
                    tool_fail_counts[tool_name] = 0
                else:
                    tool_fail_counts[tool_name] = fail_count + 1
                    # ── 记录失败代码的 hash ──
                    if tool_name == "execute_python" and ctx:
                        try:
                            _args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                            _code = _args.get("code", "")
                            if _code:
                                import hashlib
                                _code_hash = hashlib.md5(_code.encode()).hexdigest()[:12]
                                ctx._failed_code_hashes[_code_hash] = (
                                    ctx._failed_code_hashes.get(_code_hash, 0) + 1
                                )
                        except (json.JSONDecodeError, TypeError):
                            pass
                return result
            except Exception as e:
                tool_fail_counts[tool_name] = fail_count + 1
                return {"success": False, "result": {"error": str(e)}, "quality": "fail"}

        return await asyncio.gather(*[_run_one(tc) for tc in tool_calls])

    @staticmethod
    def _lookup_server(tool_name: str, ctx: RunContext) -> str:
        if not ctx or not ctx.tool_defs or not tool_name:
            return ""
        for td in ctx.tool_defs:
            if td.get("function", {}).get("name") == tool_name:
                return td.get("_server", "")
        return ""

    @staticmethod
    def _parse_tool_calls(reply: str) -> list:
        """容错解析 LLM 工具调用响应

        支持多种格式:
        1. OpenAI 格式: {"choices": [{"message": {"tool_calls": [...]}}]}
        2. 直接格式: {"tool_calls": [...]}
        3. 单个调用: {"name": "...", "arguments": {...}}
        4. Markdown 代码块: ```json\n{"tool_calls": [...]}\n```
        5. 文本中的 JSON: 从文本中提取第一个 JSON 对象
        6. 纯文本工具调用: 工具名 + 参数（适配不支持函数调用的免费模型）
        """
        if not reply or not reply.strip():
            return []

        text = reply.strip()

        # Format 4: Extract from markdown code block
        if "```" in text:
            import re
            code_blocks = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
            for block in code_blocks:
                parsed = ReActCoreMiddleware._try_parse_tool_calls(block.strip())
                if parsed:
                    return parsed

        # Format 5: Extract JSON from text (find first { ... } at top level)
        if not text.startswith("{"):
            import re
            match = re.search(r'\{[\s\S]*"tool_calls"[\s\S]*\}', text)
            if match:
                text = match.group(0)

        # Formats 1, 2, 3: Direct JSON parsing
        result = ReActCoreMiddleware._try_parse_tool_calls(text)
        if result:
            return result

        # Format 6: Plain text tool call fallback (for models without function calling)
        # Pattern: "execute_python\n\"code...\"" or "execute_python\n{...}"
        # Also: search within full text for tool mentions (not just at start)
        import re
        known_tools = ["execute_python", "execute_shell", "write_file", "web_search",
                       "fetch_url", "fetch_json", "rag_search", "open_app",
                       "ask_clarification", "browser_navigate", "browser_click",
                       "browser_snapshot", "write_todos"]
        for tool_name in known_tools:
            # Match: tool_name at start followed by newline or space, then content
            pattern = rf'^{re.escape(tool_name)}\s*\n(.+)$'
            match = re.match(pattern, text, re.DOTALL)
            if match:
                arg_text = match.group(1).strip()
                return ReActCoreMiddleware._build_text_tool_call(tool_name, arg_text)
            # Match: tool_name at start followed by parentheses or quoted string
            pattern2 = rf'^{re.escape(tool_name)}\s*[\("](.+)$'
            match2 = re.match(pattern2, text, re.DOTALL)
            if match2:
                arg_text = match2.group(1).strip().rstrip('")')
                return ReActCoreMiddleware._build_text_tool_call(tool_name, arg_text)
            # Match: tool_name mentioned anywhere in text (e.g. "我将使用 write_file 工具...")
            # Look for pattern: "write_file" followed by code block or path+content info
            # Pattern 3a: tool_name ... ```code block```
            pattern3a = rf'{re.escape(tool_name)}[\s\S]*?```[\s\S]*?```'
            match3a = re.search(pattern3a, text, re.DOTALL)
            if match3a:
                # Extract the code block content as the tool's argument
                code_match = re.search(r'```(?:\w+)?\s*\n([\s\S]*?)```', match3a.group(0))
                if code_match:
                    code = code_match.group(1).strip()
                    return ReActCoreMiddleware._build_text_tool_call(tool_name, code)
            
            # Pattern 3b: tool_name followed by path and/or content (no code block)
            # e.g., "write_file ~/Desktop/game.html\n<!DOCTYPE html>..."
            # e.g., "write_file\npath: ~/Desktop/game.html\ncontent: <!DOCTYPE html>..."
            if tool_name == "write_file":
                # 找到 tool_name 在文本中的位置
                tool_pos = text.find(tool_name)
                if tool_pos >= 0:
                    # 提取 tool_name 之后的所有文本
                    after_tool = text[tool_pos + len(tool_name):].strip()
                    # 跳过可能的括号、冒号、换行
                    after_tool = after_tool.lstrip('(:：\n ')
                    if after_tool and len(after_tool) > 10:
                        return ReActCoreMiddleware._build_text_tool_call(tool_name, after_tool)

        return []

    @staticmethod
    def _build_text_tool_call(tool_name: str, arg_text: str) -> list:
        """从纯文本参数构建工具调用"""
        import re

        def _fix_json_escapes(s: str) -> str:
            """修复 LLM 生成的 JSON 中的无效转义序列"""
            valid_escapes = set('"\\/\bfnrtu')
            result = []
            i = 0
            in_string = False
            while i < len(s):
                ch = s[i]
                if ch == '"' and (i == 0 or s[i-1] != '\\'):
                    in_string = not in_string
                    result.append(ch)
                elif ch == '\\' and in_string and i + 1 < len(s):
                    next_ch = s[i + 1]
                    if next_ch in valid_escapes:
                        result.append(ch)
                    else:
                        # 无效转义 → 双转义 (\\s → \\\\s)
                        result.append('\\')
                        result.append('\\')
                        result.append(next_ch)
                        i += 2  # 跳过这两个字符
                        continue
                else:
                    result.append(ch)
                i += 1
            return ''.join(result)

        # For execute_python: extract the code string
        if tool_name == "execute_python":
            # Remove surrounding quotes if present
            code = arg_text.strip()
            if (code.startswith('"') and code.endswith('"')) or (code.startswith("'") and code.endswith("'")):
                code = code[1:-1]
            # Unescape newlines
            code = code.replace("\\n", "\n").replace("\\t", "\t")
            return [{
                "id": f"call_{int(__import__('time').time())}",
                "type": "function",
                "function": {
                    "name": "execute_python",
                    "arguments": json.dumps({"code": code}),
                }
            }]

        # For execute_shell: extract the command
        if tool_name == "execute_shell":
            cmd = arg_text.strip()
            if (cmd.startswith('"') and cmd.endswith('"')) or (cmd.startswith("'") and cmd.endswith("'")):
                cmd = cmd[1:-1]
            return [{
                "id": f"call_{int(__import__('time').time())}",
                "type": "function",
                "function": {
                    "name": "execute_shell",
                    "arguments": json.dumps({"command": cmd}),
                }
            }]

        # For write_file tool: try to parse path and content
        if tool_name == "write_file":
            import json as _json
            
            # 尝试从 arg_text 中提取 path 和 content
            
            # 格式0: JSON 格式 {"path": "...", "content": "..."}
            arg_stripped = arg_text.strip()
            if arg_stripped.startswith("{") and arg_stripped.endswith("}"):
                try:
                    data = _json.loads(arg_stripped)
                    if isinstance(data, dict) and "path" in data and "content" in data:
                        return [{
                            "id": f"call_{int(__import__('time').time())}",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": _json.dumps({"path": data["path"], "content": data["content"]}),
                            }
                        }]
                except _json.JSONDecodeError:
                    pass  # 继续尝试下面的修复策略

                # JSON 截断修复: LLM 输出被 max_tokens 截断，JSON 不完整
                if not arg_stripped.endswith("}"):
                    # 尝试补全截断的 JSON
                    # 策略: 找到最后一个完整的 "content": " 值，截断并闭合
                    import re as _re
                    # 找到 path 值
                    path_match = _re.search(r'"path"\s*:\s*"([^"]*)"', arg_stripped)
                    # 找到 content 的起始位置
                    content_start = _re.search(r'"content"\s*:\s*"', arg_stripped)
                    if path_match and content_start:
                        path_val = path_match.group(1)
                        content_start_pos = content_start.end()
                        # 从 content 起始到字符串末尾就是 content 值（可能被截断）
                        raw_content = arg_stripped[content_start_pos:]
                        # 移除末尾可能的不完整转义
                        raw_content = raw_content.rstrip('\\')
                        # 修复无效转义
                        raw_content = _fix_json_escapes('"' + raw_content + '"')[1:-1]
                        logger.warning(f"write_file JSON截断修复: path={path_val}, content_len={len(raw_content)}")
                        return [{
                            "id": f"call_{int(__import__('time').time())}",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": _json.dumps({"path": path_val, "content": raw_content}),
                            }
                        }]
            
            # 格式1: path: xxx\ncontent: xxx
            # 格式2: "path", "content"
            # 格式3: (path, content)
            # 格式4: 纯文本作为 content，path 需要从上下文推断
            import re as _re
            
            path = ""
            content = arg_text  # 默认整个文本作为 content
            
            # 尝试提取 path（常见路径模式）
            path_patterns = [
                r'path[=:：]\s*["\']?([^"\'\n]+)["\']?',
                r'["\']([~\/][^"\'\n]+)["\']',
                r'\((["\'][^"\']+["\'])',
            ]
            for pp in path_patterns:
                pm = _re.search(pp, arg_text, _re.IGNORECASE)
                if pm:
                    path = pm.group(1).strip()
                    # 移除 path 部分，剩余作为 content
                    content = arg_text[:pm.start()] + arg_text[pm.end():]
                    break
            
            # 如果没找到 path，尝试从文本开头提取
            if not path:
                # 匹配 ~/Desktop/xxx 或 /Users/xxx/xxx 或 ~/xxx
                path_match = _re.match(r'^(~?\/[^\s\n]+)', arg_text.strip())
                if path_match:
                    path = path_match.group(1)
                    content = arg_text[path_match.end():].strip()
            
            # 清理 content
            content = content.strip()
            # 移除可能的引号包裹
            if (content.startswith('"') and content.endswith('"')) or \
               (content.startswith("'") and content.endswith("'")):
                content = content[1:-1]
            # 还原换行符
            content = content.replace("\\n", "\n").replace("\\t", "\t")
            
            # 如果还是没有有效 content，返回错误提示
            if not content or len(content) < 10:
                return [{
                    "id": f"call_{int(__import__('time').time())}",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({"path": path or arg_text, "content": ""}),
                    }
                }]
            
            return [{
                "id": f"call_{int(__import__('time').time())}",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": path or "~/Desktop/game.html", "content": content}),
                }
            }]

        # Generic: put raw text as first string argument
        return [{
            "id": f"call_{int(__import__('time').time())}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps({"input": arg_text}),
            }
        }]

    @staticmethod
    def _try_parse_tool_calls(text: str) -> list:
        """尝试从 JSON 文本中提取工具调用"""
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(data, dict):
            return []

        # Format 1: OpenAI style
        choices = data.get("choices", [])
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message", {})
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                return tool_calls

        # Format 2: Direct tool_calls
        tool_calls = data.get("tool_calls", [])
        if tool_calls:
            return tool_calls

        # Format 3: Single call (name + arguments at top level)
        if "name" in data and ("arguments" in data or "parameters" in data):
            return [{
                "id": f"call_{int(__import__('time').time())}",
                "type": "function",
                "function": {
                    "name": data["name"],
                    "arguments": json.dumps(data.get("arguments", data.get("parameters", {})), default=str),
                }
            }]

        return []


def build_default_chain() -> MiddlewareChain:
    """构建默认中间件链：Summarization → LoopDetection → Clarification → Todo → Permission → Hook → ReActDepth → ReActCore → Reflection → KEPA"""
    chain = MiddlewareChain()
    from .middlewares import (
        ClarificationMiddleware,
        HookMiddleware,
        KEPAMiddleware,
        LoopDetectionMiddleware,
        PermissionMiddleware,
        ReActDepthMiddleware,
        ReflectionMiddleware,
        TruncationMiddleware,
        TodoMiddleware,
    )

    chain.add(TruncationMiddleware())   # 先压缩旧消息
    chain.add(LoopDetectionMiddleware())   # 双层循环检测
    chain.add(ClarificationMiddleware())   # 澄清请求拦截
    chain.add(TodoMiddleware())            # 任务完整性保护
    chain.add(PermissionMiddleware())      # 三级权限控制 + Shell 安全检查
    chain.add(HookMiddleware())            # 工具调用 Hook 拦截
    chain.add(ReActDepthMiddleware())      # 深度保护 + 连续失败检测
    chain.add(ReActCoreMiddleware())       # ★ ReAct 核心循环
    chain.add(ReflectionMiddleware())      # 定期反思，写入 temp_memory
    chain.add(KEPAMiddleware())            # KEPA 知识闭环
    return chain


def build_configured_chain(
    loop_detection: bool = True,
    clarification: bool = True,
    todo: bool = True,
    permission: bool = True,
    hook: bool = True,
    depth_limit: bool = True,
    reflection: bool = True,
    kepa: bool = True,
    summarization: bool = True,
    loop_warn: int = 3,
    loop_hard: int = 5,
    depth_max: int = 30,
) -> MiddlewareChain:
    """可配置的中间件链构建器

    Args:
        loop_detection: 启用循环检测
        clarification: 启用澄清拦截
        todo: 启用退出保护
        permission: 启用三级权限控制
        hook: 启用 Hook 拦截器
        depth_limit: 启用深度限制
        reflection: 启用反思
        kepa: 启用KEPA知识闭环
        summarization: 启用对话压缩
        loop_warn: 循环警告阈值
        loop_hard: 循环强制停止阈值
        depth_max: 最大深度
    """
    chain = MiddlewareChain()
    from .middlewares import (
        KEPAMiddleware,
        LoopDetectionMiddleware,
        ClarificationMiddleware,
        TodoMiddleware,
        PermissionMiddleware,
        HookMiddleware,
        ReActDepthMiddleware,
        ReflectionMiddleware,
        TruncationMiddleware,
    )

    if summarization:
        chain.add(TruncationMiddleware())
    if loop_detection:
        chain.add(LoopDetectionMiddleware(warn_threshold=loop_warn, hard_limit=loop_hard))
    if clarification:
        chain.add(ClarificationMiddleware())
    if todo:
        chain.add(TodoMiddleware())
    if permission:
        chain.add(PermissionMiddleware())
    if hook:
        chain.add(HookMiddleware())
    if depth_limit:
        mw = ReActDepthMiddleware()
        mw.MAX_DEPTH = depth_max
        chain.add(mw)
    chain.add(ReActCoreMiddleware())  # Core always present
    if reflection:
        chain.add(ReflectionMiddleware())
    if kepa:
        chain.add(KEPAMiddleware())
    return chain


async def _generate_plan(
    task_description: str, ctx: RunContext, retry_context: str = ""
) -> List[PlanStep]:
    """规划阶段 — 两步LLM调用：先理解任务，再制定结构化计划

    第一步：LLM输出自然语言任务拆解（理解阶段）
    第二步：根据工具信息结构化为步骤（规划阶段）
    """
    from core.engine.llm_backend import get_llm_router

    router = get_llm_router()
    if not router or not router.is_available():
        return []

    retry_hint = f"\n【重试背景】{retry_context}\n" if retry_context else ""

    # ── 第一步：理解任务，输出自然语言拆解 ──
    understand_prompt = (
        "请分析以下任务，用自然语言描述应该如何完成。\n\n"
        "要求：\n"
        "- 理解任务的核心目标\n"
        "- 思考需要哪些步骤\n"
        "- 每个步骤用一句话描述\n"
        f"任务：{task_description[:300]}"
        f"{retry_hint}\n"
        "直接输出理解分析，不要编号："
    )
    try:
        understand_resp = await asyncio.wait_for(
            router.chat(
                [{"role": "user", "content": understand_prompt}],
                temperature=0.3,
                max_tokens=300,
            ),
            timeout=10.0,
        )
        understanding = str(understand_resp).strip() if understand_resp else ""
    except Exception:
        understanding = ""

    # ── 第二步：根据理解 + 工具信息，生成结构化计划 ──
    plan_prompt = (
        "根据任务理解和可用工具，将任务拆解为1-2个执行步骤。\n\n"
        "【任务理解】\n"
        f"{understanding if understanding else task_description[:200]}\n\n"
        "【重要规则】\n"
        "- 最多2个步骤，不要拆分过细\n"
        "- 每个步骤只能包含一个工具调用\n"
        "- 抓取网页数据（热搜/新闻/搜索结果）→ 用 execute_python 调用内置爬虫，不要用 Playwright MCP\n"
        "- ⚠️ 请直接输出你的计划，不要输出模板文字\n\n"
        "【可用工具】\n"
        "  execute_python — 执行Python代码（写文件、调用内置爬虫、数据处理等万能工具）\n"
        "  fetch_url — HTTP GET获取网页/API数据\n"
        "  browser_navigate + browser_snapshot — Playwright浏览器（仅用于需要浏览器交互的场景，如填表单、登录）\n"
        "  open_app — 打开Mac应用\n\n"
        "【输出格式】每行一个步骤，格式：步骤|具体描述|工具名\n"
        "⚠️ 「具体描述」必须是针对当前任务的实际内容，不要写'步骤描述'这几个字\n\n"
        "示例（参考格式，不要照抄内容）：\n"
        "任务: 搜索百度热搜 → 步骤|搜索百度热搜获取数据|web_search\n"
        "任务: 写Python脚本到桌面 → 步骤|用Python代码生成游戏文件|execute_python\n"
        "任务: 打开QQ → 步骤|打开QQ应用|open_app\n\n"
        "如果不需要工具：步骤|直接回答\n"
        "开始："
    )
    try:
        resp = await asyncio.wait_for(
            router.chat(
                [{"role": "user", "content": plan_prompt}],
                temperature=0.2,
                max_tokens=500,
            ),
            timeout=15.0,
        )
        text = str(resp).strip() if resp else ""
        if not text or "[LLM_MOCK]" in text:
            return []

        steps: List[PlanStep] = []
        # 模板文本黑名单 - LLM 可能照抄模板
        template_blacklist = {"步骤描述", "具体描述", "任务描述", "描述", "步骤一", "步骤二"}
        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("步骤|"):
                continue
            parts = line.split("|")
            desc = parts[1].strip() if len(parts) > 1 else ""
            tools_str = parts[2].strip() if len(parts) > 2 else ""
            if "直接回答" in desc:
                return []
            # 跳过模板文本（LLM 照抄了示例格式）
            if desc in template_blacklist or len(desc) < 3:
                continue
            tools = (
                [t.strip() for t in tools_str.split(",") if t.strip()]
                if tools_str
                else []
            )
            steps.append(
                PlanStep(index=len(steps) + 1, description=desc, tool_names=tools)
            )
        return steps[:5]
    except Exception:
        return []


def _display_plan(
    ctx: RunContext, header: str = "📋 执行计划", prefix: str = ""
) -> None:
    """显示计划进度条"""
    if not ctx.plan:
        return
    done = sum(1 for s in ctx.plan if s.status == "done")
    total = len(ctx.plan)
    color = "\033[1;34m"
    reset = "\033[0m"

    lines = [f"{prefix}    {color}{header}（{done}/{total}）:{reset}"]
    for step in ctx.plan:
        if step.status == "done":
            icon = "✅"
        elif step.status == "running":
            icon = "➡️"
        elif step.status == "failed":
            icon = "❌"
        else:
            icon = "  "
        desc = step.description.replace("\n", " ")[:60]
        lines.append(f"{prefix}      {icon} {desc}")
    print("\n".join(lines))


def _steps_summary(ctx: RunContext) -> str:
    """生成步骤状态的文本摘要（注入 system prompt）"""
    if not ctx.plan:
        return ""
    lines = ["\n\n【计划进度】"]
    for step in ctx.plan:
        if step.status == "done":
            lines.append(f"  ✅ 第{step.index}步: {step.description}")
        elif step.status == "running":
            lines.append(f"  ➡️  第{step.index}步: {step.description}（当前步骤）")
        elif step.status == "failed":
            lines.append(
                f"  ❌ 第{step.index}步: {step.description} — 失败需重试或跳过"
            )
        else:
            lines.append(f"  ⬜ 第{step.index}步: {step.description}")
    lines.append("— 已完成步骤不要重复做。优先推进未完成的步骤。")
    return "\n".join(lines)


def _update_step_status(ctx: RunContext) -> None:
    """更新步骤状态：检查步骤中指定的工具是否都已调用完成

    增强功能：
    1. 支持语义匹配：步骤描述关键词 vs 工具调用参数
    2. 支持跳过失败步骤
    3. 支持自动重规划（通过 _replan_failed）
    """
    if not ctx.plan:
        return

    # 本轮有工具调用吗
    if not ctx.tool_results:
        return

    # 检查最近一次工具调用的结果中是否包含错误
    last_result = ctx.tool_results[-1]
    last_raw = str(last_result.get("result", last_result.get("error", "")))
    has_error = any(
        marker in last_raw
        for marker in ["❌", "SyntaxError", "NameError", "TypeError", "Error:", "需要", "失败"]
    )

    # 获取当前正在执行的步骤（第一个未完成的步骤）
    done_count = sum(1 for s in ctx.plan if s.status == "done")
    if done_count >= len(ctx.plan):
        return

    current_step = ctx.plan[done_count]

    # 如果有代码错误，标记当前步骤为 failed 并触发重规划
    if has_error:
        if current_step.status != "failed":
            current_step.status = "failed"
            ctx._step_retries[current_step.index] = (
                ctx._step_retries.get(current_step.index, 0) + 1
            )
            print(f"{ctx._get_prefix() if hasattr(ctx, '_get_prefix') else ''}    \033[1;31m❌ 步骤 {current_step.index} 执行失败，将触发重规划\033[0m")
        return

    # 收集所有已调用的工具名称（成功调用）
    called_tools = set()
    succeeded_tools = set()
    for tr in ctx.tool_results:
        tc = tr.get("tool_call", {})
        tool_name = tc.get("name", "")
        if tool_name:
            called_tools.add(tool_name)
            if tr.get("success"):
                succeeded_tools.add(tool_name)

    # 收集所有已调用工具的信息（用于语义匹配）
    called_args_text = ""
    for tr in ctx.tool_results:
        tc = tr.get("tool_call", {})
        args = tc.get("arguments", {})
        if isinstance(args, dict):
            called_args_text += json.dumps(args, ensure_ascii=False) + " "

    # 语义匹配：检查步骤描述与已调用的工具是否匹配
    def _semantic_match(step_desc: str, args_text: str, succeeded_tools_set: set) -> bool:
        # 意图组定义：[意图关键词, 匹配的工具, 参数中必须有的关键词]
        INTENT_GROUPS = [
            (["写", "创建", "生成", "保存"], {"write_file", "execute_python", "execute_script", "execute_shell"}, ["write_file", "创建", "生成", "写入", "保存"]),
            (["搜索", "查", "搜", "查找"], {"web_search", "fetch_url", "fetch_json", "execute_python"}, ["搜索", "查询", "搜索到", "找到", "结果"]),
            (["代码", "程序", "脚本", "运行", "执行"], {"execute_python", "execute_shell", "write_file"}, ["执行", "运行", "代码", "结果"]),
            (["设计", "布局", "界面", "游戏", "布局"], {"write_file", "execute_python"}, ["write_file", "写入", "创建", "文件"]),
            (["爬虫", "抓取", "热搜", "热榜", "爬取"], {"web_search", "fetch_url", "execute_python"}, ["搜索到", "获取到", "结果"]),
            (["文件", "保存", "写入", "读取"], {"write_file", "read_file", "execute_shell"}, ["文件", "写入", "读取"]),
            (["分析", "统计", "数据", "图表"], {"execute_python", "rag_search", "fetch_url"}, [":", "结果", "数据"]),
            (["网页", "页面", "网站", "url"], {"fetch_url", "web_search"}, ["<!DOCTYPE", "<html", "http"]),
        ]
        for keywords, match_tools, args_keywords in INTENT_GROUPS:
            if any(kw in step_desc for kw in keywords):
                # 必须有匹配的工具成功
                if not (succeeded_tools_set & match_tools):
                    continue
                # 参数中必须有对应关键词（避免幻觉）
                if not any(kw in args_text for kw in args_keywords):
                    continue
                return True
        return False

    # 如果步骤指定了工具，检查是否都已调用成功
    if current_step.tool_names:
        step_tools = set(current_step.tool_names)
        # 所有步骤指定的工具都已成功调用，才标记为完成
        if step_tools.issubset(succeeded_tools):
            current_step.status = "done"
        # 语义匹配：步骤描述与成功的工具调用匹配
        elif _semantic_match(current_step.description, called_args_text, succeeded_tools):
            current_step.status = "done"
    else:
        # 没有指定工具：需要语义匹配通过才算完成，不能仅因有成功工具调用就推进
        if _semantic_match(current_step.description, called_args_text, succeeded_tools):
            current_step.status = "done"

    # 兜底：有实质进展且步骤已运行多轮 → 推进
    if current_step.status != "done" and ctx.react_depth >= 3:
        _has_substance = False
        for r in ctx.tool_results:
            if not r.get("success"):
                continue
            name = r.get("tool_call", {}).get("name", "")
            # 只有产出数据的工具才算实质进展
            if name in ("write_file", "web_search", "fetch_url", "fetch_json"):
                _has_substance = True
                break
            if name == "execute_python":
                result_text = str(r.get("result", ""))
                if result_text and result_text != "None" and len(result_text) > 20:
                    _has_substance = True
                    break
        if _has_substance:
            logger.info(f"步骤 {current_step.index} 多轮未推进且有实质进展，兜底标记为 done")
            current_step.status = "done"


async def _replan_failed(ctx: RunContext) -> bool:
    """重新规划失败的步骤，保留已完成步骤"""
    done_descs = [
        f"第{s.index}步: {s.description}" for s in ctx.plan if s.status == "done"
    ]
    failed = [s for s in ctx.plan if s.status == "failed" or s.status == "pending"]
    failed_descs = [f"第{s.index}步: {s.description}" for s in failed]

    error_context = ""
    if ctx.last_error:
        error_context = f"\n错误: {ctx.last_error}"
    if ctx.tool_results:
        last = ctx.tool_results[-1]
        if not last.get("success"):
            error_context += f"\n工具执行错误: {last.get('error', '') or last.get('result', {}).get('error', '')}"

    retry_prompt = (
        "任务需要重新规划后面的步骤。\n\n"
        f"已完成: {', '.join(done_descs) if done_descs else '无'}\n"
        f"失败的步骤: {', '.join(failed_descs) if failed_descs else '需要继续'}"
        f"{error_context}\n\n"
        "请重新规划未完成的步骤，忽略已完成的。\n"
        "输出格式：步骤|步骤描述|预计使用的工具名(逗号分隔,可省略)\n"
        "开始："
    )

    new_steps = await _generate_plan(
        ctx.task_description, ctx, retry_context=retry_prompt
    )
    if not new_steps:
        return False

    # 保留已完成步骤，用新步骤替换未完成的
    kept = [s for s in ctx.plan if s.status == "done"]
    offset = len(kept)
    for i, s in enumerate(new_steps):
        s.index = offset + i + 1
        s.status = "pending"
    ctx.plan = kept + new_steps
    ctx.plan_generation += 1
    return True


def _get_prefix(agent: Any = None) -> str:
    """获取Agent前缀标签"""
    if agent and hasattr(agent, "_agent_label"):
        label = agent._agent_label
        # 截取合适的长度
        short_label = label[:15] if len(label) > 15 else label
        return f"[{short_label}] "
    return ""


async def run_react(
    task_description: str,
    max_rounds: int = 0,
    model: str = "",
    personality_prompt: str = "",
    agent: Any = None,
    allowed_tools: Optional[List[str]] = None,
    disallowed_tools: Optional[List[str]] = None,
) -> dict:
    """快捷入口：直接用 ReActCore 处理任务

    Args:
        task_description: 任务描述
        max_rounds: 最大轮数，0 表示默认 _MAX_ROUNDS
        model: 指定使用的 LLM 模型名
        personality_prompt: Agent 个性/角色提示
        agent: 关联的 WorkAgent 实例
        allowed_tools: 工具白名单（None=不限制）
        disallowed_tools: 工具黑名单
    """
    if max_rounds == 0:
        max_rounds = _MAX_ROUNDS

    ctx = RunContext(task_description)
    ctx.max_iterations = max_rounds
    if model:
        ctx.model_override = model
    if personality_prompt:
        ctx.personality_prompt = personality_prompt
    ctx.allowed_tools = allowed_tools
    ctx.disallowed_tools = disallowed_tools

    chain = build_default_chain()
    if agent:
        chain.bind_agent(agent)

    await chain.on_start(ctx)
    ctx._chain = chain

    # 获取前缀
    prefix = _get_prefix(agent)

    # ── 规划阶段：先制定计划，再执行 ──
    ctx.plan = await _generate_plan(task_description, ctx)
    if ctx.plan:
        _display_plan(ctx, prefix=prefix)
    else:
        print(f"{prefix}    \033[2;37m📋 无显式计划，自动按 ReAct 循环执行\033[0m")

    while not ctx.interrupted and ctx.react_depth < ctx.max_iterations:
        round_idx = ctx.react_depth + 1
        print(
            f"\n{prefix}    \033[1;37m━━━ 第 {round_idx}/{ctx.max_iterations} 轮 ━━━\033[0m"
        )

        # 显示计划进度
        if ctx.plan:
            _display_plan(ctx, prefix=prefix)

        # 全部步骤完成 → 结束
        if ctx.plan and all(s.status == "done" for s in ctx.plan):
            print(f"{prefix}    \033[1;32m✅ 所有计划步骤已完成\033[0m")
            ctx.interrupted = True
            break

        # 检测轮次上限：如果连续 K 轮没有推进计划，直接输出已有结果
        if ctx.react_depth >= 3 and ctx.plan:
            done_count = sum(1 for s in ctx.plan if s.status == "done")
            if done_count == 0 and ctx.react_depth >= 8:
                print(f"{prefix}    \033[1;33m⚠️ 多轮未见推进，提前结束\033[0m")
                ctx.interrupted = True
                break

        # 最后一轮提示
        if ctx.react_depth == ctx.max_iterations - 1:
            print(f"{prefix}    \033[1;31m⚠️ 最后轮次 — 直接输出最终答案\033[0m")
            ctx.task_description += (
                "\n\n[最后轮次] 本轮后结束。如果主要任务已经完成，直接输出结果。"
            )

        # 阶段1: on_think_start（深度检查/KEPA查询）
        hr_start = await chain.on_think_start(ctx)
        if hr_start and hr_start.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_start.reason or "中间件终止(think_start)"
            break
        if hr_start and hr_start.jump_to == "retry":
            continue

        # 阶段2: on_think_end（LLM思考 + 工具执行）
        hr_end = await chain.on_think_end(ctx)
        if hr_end and hr_end.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_end.reason or "中间件终止(think_end)"
            break

        # ── 更新计划步骤状态 ──
        if ctx.plan:
            _update_step_status(ctx)

            # 检测失败步骤并触发重规划
            failed_steps = [s for s in ctx.plan if s.status == "failed"]
            for step in failed_steps:
                retries = ctx._step_retries.get(step.index, 0)
                if retries < 2:  # 最多重试2次
                    replanned = await _replan_failed(ctx)
                    if replanned:
                        print(f"{prefix}    \033[1;33m🔄 步骤 {step.index} 失败，已重新规划\033[0m")
                        break

        # 阶段3: on_tool_end（反思/KEPA决策）
        hr_tool = await chain.on_tool_end(ctx)
        if hr_tool and hr_tool.jump_to == "end":
            ctx.interrupted = True
            ctx.last_error = hr_tool.reason or "中间件终止(tool_end)"
            break
        if hr_tool and hr_tool.jump_to == "retry":
            ctx.task_description += f"\n[重试] {hr_tool.reason}。"

            # 标记重试步骤为 failed，让下次循环检测并 re-plan
            for step in ctx.plan:
                if step.status == "running":
                    step.status = "failed"
                    ctx._step_retries[step.index] = (
                        ctx._step_retries.get(step.index, 0) + 1
                    )
            continue

    await chain.on_finish(ctx)

    # ── 搜索报告自动生成兜底 ──
    # 有搜索数据但未生成文件时，自动生成 HTML 分析报告到桌面
    if not ctx.final_answer:
        _has_search_data = any(
            r.get("tool_call", {}).get("name") in ("web_search", "fetch_url", "fetch_json")
            and r.get("success")
            for r in ctx.tool_results
        )
        _has_report_file = any(
            r.get("tool_call", {}).get("name") == "write_file" and r.get("success")
            for r in ctx.tool_results
        )
        if _has_search_data and not _has_report_file:
            from core.multi_agent_v2.tools.tool_result import from_handler as _fmt_search
            _search_outputs = []
            for tr in ctx.tool_results:
                tc = tr.get("tool_call", {})
                name = tc.get("name", "?")
                if name in ("web_search", "fetch_url", "fetch_json") and tr.get("success"):
                    raw = tr.get("result", "")
                    txt = _fmt_search(raw)
                    if txt and txt != "None" and txt != "(无输出)":
                        _search_outputs.append(f"[{name}] {txt[:3000]}")
            if _search_outputs:
                print(f"{prefix}    \033[1;33m📝 有搜索数据未生成文件，自动生成 HTML 报告...\033[0m")
                _report_prompt = (
                    "基于以下搜索结果数据，生成一份完整的中文 HTML 分析报告。\n\n"
                    "要求：\n"
                    "- 完整的 <!DOCTYPE html> 格式，内嵌 CSS 样式\n"
                    "- 包含标题、发布日期、数据分类、趋势分析、总结\n"
                    "- 样式美观，背景用渐变色，字体优雅\n"
                    "- 所有内容用中文，数据逐条列出（禁止省略或截断）\n"
                    f"数据：\n{chr(10).join(_search_outputs[:3])}\n\n"
                    "直接输出完整的 HTML 代码，不要输出其他内容。"
                )
                try:
                    from core.engine.llm_backend import get_llm_router
                    _router = get_llm_router()
                    if _router and _router.is_available():
                        _html_resp = await asyncio.wait_for(
                            _router.chat(
                                [{"role": "user", "content": _report_prompt}],
                                temperature=0.3,
                                max_tokens=6000,
                            ),
                            timeout=60,
                        )
                        _html_text = str(_html_resp) if _html_resp else ""
                        # 提取 HTML 代码（可能被 markdown 代码块包裹）
                        if "```html" in _html_text:
                            _html_text = _html_text.split("```html")[1].split("```")[0]
                        elif "```" in _html_text:
                            _html_text = _html_text.split("```")[1].split("```")[0]
                        if "<!DOCTYPE html>" in _html_text or "<html" in _html_text:
                            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
                            _reg = get_tool_registry()
                            _wf_handler = _reg.get_handler("write_file")
                            if _wf_handler:
                                _report_path = f"/Users/leiyuxuan/Desktop/baidu_hot_search_report.html"
                                await _wf_handler({"path": _report_path, "content": _html_text})
                                print(f"{prefix}    \033[1;32m✅ 分析报告已生成: {_report_path}\033[0m")
                                ctx.final_answer = f"✅ 分析报告已生成在桌面: baidu_hot_search_report.html"
                            else:
                                ctx.final_answer = _html_text[:2000]
                        elif _html_text:
                            ctx.final_answer = _html_text[:2000]
                except Exception as _e:
                    logger.debug(f"自动生成报告失败: {_e}")

    # 兜底：有工具结果但无 final_answer 时让 LLM 总结
    if not ctx.final_answer and ctx.tool_results:
        from core.multi_agent_v2.tools.tool_result import from_handler as _fmt_result

        outputs = []
        for tr in ctx.tool_results:
            tc = tr.get("tool_call", {})
            name = tc.get("name", "?")
            ok = tr.get("success", False)
            raw = tr.get("result", "")
            txt = _fmt_result(raw)
            if ok and txt and txt != "None" and txt != "(无输出)":
                outputs.append(f"[{name}] {txt[:300]}")
        if outputs:
            summary = "\n\n".join(outputs[:3])
            from core.engine.llm_backend import get_llm_router

            router = get_llm_router()
            try:
                final_resp = await asyncio.wait_for(
                    router.chat(
                        [
                            {
                                "role": "system",
                                "content": "基于工具执行结果，用简洁的中文给出总结回答。直接输出结果，不要输出JSON。",
                            },
                            {
                                "role": "user",
                                "content": f"原始任务: {task_description}\n\n工具执行结果:\n{summary}\n\n请给出最终总结。",
                            },
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                    ),
                    timeout=30,
                )
                text = str(final_resp) if final_resp else ""
                if text and text != "None" and len(text) > 20:
                    ctx.final_answer = text
            except Exception:
                pass
        if not ctx.final_answer:
            from core.multi_agent_v2.tools.tool_result import from_handler as _fmt_result2
            for last in reversed(ctx.tool_results):
                if last.get("success"):
                    raw = last.get("result", "")
                    txt = _fmt_result2(raw)
                    if txt and txt != "None" and txt != "(无输出)":
                        ctx.final_answer = txt[:1000]
                        break

    return {
        "success": bool(ctx.final_answer),
        "answer": ctx.final_answer,
        "iterations": ctx.react_depth,
        "tool_results": ctx.tool_results,
        "error": ctx.last_error,
    }

"""自动化工作流引擎 - Open Claw风格全链路自动化

工业级工作流引擎：
- create_smart_workflow: 自然语言意图识别 → 结构化工作流
  - 站点关键词检测：微博/百度/B站/抖音/知乎/今日头条/豆瓣
  - 分析关键词检测：分析/统计/可视化/图表/趋势/词云
  - 组合检测：爬取+分析+报告自动串联
- execute_workflow: 异步执行工作流步骤
  - 步骤类型：scrape / analyze / automate
  - 支持并行执行（asyncio.gather）
  - 每步记录执行时间和结果
- _execute_automate_step: GUI自动化操作（20+动作）
- _generate_desktop_report: Markdown报告生成到桌面
- _send_notification: osascript系统通知
"""
import asyncio
import json
import logging
import os
import re

# 沙盒查看器记录（延迟导入，避免启动时依赖）
def _record_event(event_type, title, detail="", status="ok"):
    try:
        from cli.sandbox_viewer import get_viewer
        get_viewer().record(event_type, title, detail=detail, status=status)
    except Exception:
        pass
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── 输出目录 ───────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent.parent / "skills" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── 意图识别关键词 ─────────────────────────────────────────────────────────
SITE_KEYWORDS: Dict[str, List[str]] = {
    "微博": ["微博", "weibo"],
    "百度": ["百度", "baidu", "百度热搜"],
    "B站": ["B站", "哔哩哔哩", "bilibili"],
    "抖音": ["抖音", "douyin"],
    "知乎": ["知乎", "zhihu"],
    "今日头条": ["今日头条", "头条"],
    "豆瓣": ["豆瓣", "douban"],
    "GitHub": ["github", "GitHub", "GITHUB", "gitHub", "github.com"],
}

ANALYZE_KEYWORDS: List[str] = [
    "分析", "统计", "可视化", "图表", "趋势", "词云", "柱状图", "饼图",
]

REPORT_KEYWORDS: List[str] = [
    "报告", "保存", "导出", "生成", "桌面",
]

# 计算器关键词
CALCULATOR_KEYWORDS: List[str] = [
    "计算", "加", "减", "乘", "除", "等于", "等于多少",
    "平方", "立方", "开方", "根号",
    "sin", "cos", "tan", "log", "ln",
]

# 代码编写关键词（优先级高于计算器）
CODE_WRITING_KEYWORDS: List[str] = [
    "写一个", "写一段", "编写", "实现", "创建",
    "程序", "脚本", "函数", "类", "模块",
    "代码", "coding", "program",
]

# 问候语关键词
GREETING_KEYWORDS: List[str] = [
    "你好", "您好", "哈喽", "hi", "hello", "嗨", "早上好", "下午好", "晚上好",
    "你是谁", "你叫什么名字", "介绍一下", "认识一下",
    "谢谢", "感谢", "辛苦了",
    "再见", "拜拜", "下次见",
]

# 闲聊关键词
CHAT_KEYWORDS: List[str] = [
    "天气", "时间", "日期", "今天几号", "现在几点",
    "讲个笑话", "讲笑话", "笑话",
    "唱歌", "放首歌",
    "故事", "讲故事",
]

# ─── GUI自动化动作映射 ─────────────────────────────────────────────────────
AUTOMATE_ACTIONS: Dict[str, str] = {
    # 应用/文件操作
    "打开": "open_app",
    "打开应用": "open_app",
    "启动": "open_app",
    "启动应用": "open_app",
    "打开网址": "open_url",
    "打开链接": "open_url",
    "访问": "open_url",
    "退出应用": "quit_app",
    "关闭应用": "quit_app",
    "截屏": "screenshot",
    "截图": "screenshot",
    # 输入操作
    "输入文字": "type_text",
    "打字": "type_text",
    "输入": "type_text",
    "点击文字": "click_text",
    "点击": "click_text",
    "快捷键": "hotkey",
    "按键": "key_press",
    "按键": "key_press",
    # 系统控制
    "通知": "notification",
    "提醒": "notification",
    "等待": "wait",
    "延时": "wait",
    "音量": "volume_adjust",
    "亮度": "brightness_adjust",
    "剪贴板": "get_clipboard",
    "复制": "set_clipboard",
    # 窗口操作
    "切换窗口": "hotkey",
    "全屏": "hotkey",
    "最小化": "hotkey",
    "关闭窗口": "hotkey",
}


# ═══════════════════════════════════════════════════════════════════════════
class AutomationWorkflowEngine:
    """自动化工作流引擎 — Open Claw风格"""

    def __init__(self) -> None:
        self._scraper = None
        self._analyzer = None
        self._automation = None

    # ── MCP 懒加载 ────────────────────────────────────────────────────────
    @property
    def scraper(self):
        """通过 MCP 获取爬虫服务"""
        if self._scraper is None:
            try:
                from core.mcp.awesome_mcp_manager import awesome_mcp_manager
                self._scraper = {
                    "manager": awesome_mcp_manager,
                    "server": "web-scraper",
                }
                logger.info("Web Scraper MCP模块加载成功")
            except ImportError:
                logger.warning("Web Scraper MCP模块加载失败（回退到本地）")
                try:
                    from mcp._impl.web_scraper.handler import scraper_dispatcher
                    self._scraper = scraper_dispatcher
                except ImportError:
                    pass
        return self._scraper

    @property
    def analyzer(self):
        """通过 MCP 获取数据分析服务"""
        if self._analyzer is None:
            try:
                from core.mcp.awesome_mcp_manager import awesome_mcp_manager
                self._analyzer = {"manager": awesome_mcp_manager, "server": "data-analysis"}
                logger.info("Data Analysis MCP模块加载成功")
            except ImportError:
                logger.warning("Data Analysis MCP模块加载失败（回退到本地）")
                try:
                    from mcp._impl.data_analysis.handler import analysis_handler
                    self._analyzer = analysis_handler
                except ImportError:
                    pass
        return self._analyzer

    @property
    def automation(self):
        """通过 MCP 获取高级自动化服务"""
        if self._automation is None:
            try:
                from core.mcp.awesome_mcp_manager import awesome_mcp_manager
                self._automation = {"manager": awesome_mcp_manager, "server": "advanced-automation"}
                logger.info("Advanced Automation MCP模块加载成功")
            except ImportError:
                logger.warning("Advanced Automation MCP模块加载失败（回退到本地）")
                try:
                    from mcp._impl.advanced_automation.handler import automation_hub
                    self._automation = automation_hub
                except ImportError:
                    pass
        return self._automation

    # ══════════════════════════════════════════════════════════════════════
    #  智能意图识别 → 工作流创建
    # ══════════════════════════════════════════════════════════════════════

    def _get_greeting_response(self, user_request: str) -> Optional[str]:
        """根据问候语返回响应消息"""
        greetings = ["你好", "您好", "哈喽", "hi", "hello", "嗨", "早上好", "下午好", "晚上好"]
        introductions = ["你是谁", "你叫什么名字", "介绍一下", "认识一下"]
        thanks = ["谢谢", "感谢", "辛苦了"]
        goodbyes = ["再见", "拜拜", "下次见"]
        
        for g in greetings:
            if g in user_request:
                hour = datetime.now().hour
                if hour < 12:
                    return "早上好！我是小雷版小龙虾 AI Agent，很高兴为你服务！😊"
                elif hour < 18:
                    return "下午好！我是小雷版小龙虾 AI Agent，请问有什么可以帮你的？😊"
                else:
                    return "晚上好！我是小雷版小龙虾 AI Agent，很高兴为你服务！😊"
        
        for i in introductions:
            if i in user_request:
                return "我是小雷版小龙虾 AI Agent，是一款强大的智能助手！我可以帮你：\n\n• 爬取微博、B站、抖音等网站的热门数据\n• 进行数据分析和可视化\n• 发送微信消息\n• 控制电脑应用和系统\n• 执行各种自动化任务\n\n有什么需要帮助的吗？"
        
        for t in thanks:
            if t in user_request:
                return "不客气！能帮到你我很开心！如果还有其他需求随时告诉我！😊"
        
        for g in goodbyes:
            if g in user_request:
                return "再见！祝你一天愉快！有需要随时回来找我！👋"
        
        return None

    async def create_smart_workflow(self, user_request: str) -> Dict[str, Any]:
        """智能识别用户意图并创建结构化工作流

        检测逻辑：
        1. 问候语检测 → 直接回复
        2. 站点关键词 → 爬取步骤
        3. 分析关键词 → 分析步骤（自动检测图表类型）
        4. 报告关键词 / 有分析 → 生成报告标记
        5. 组合检测：爬取+分析+报告自动串联
        6. 兜底：识别为GUI自动化操作
        """
        # 保存原始请求供后续代码降级使用
        self._last_user_request = user_request
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        workflow: Dict[str, Any] = {
            "name": f"智能工作流_{ts}",
            "description": user_request,
            "steps": [],
            "parallel_groups": [],  # 支持并行执行组
            "generate_report": False,
        }

        # ── 0. 问候语检测（优先级最高）──
        greeting_response = self._get_greeting_response(user_request)
        if greeting_response:
            workflow["steps"].append({
                "type": "automate",
                "action": "notification",
                "params": {
                    "title": "小雷版小龙虾",
                    "message": greeting_response,
                },
                "description": "问候语响应",
            })
            return {"success": True, "workflow": workflow}

        # ── 1. 站点检测 ──
        detected_sites: List[str] = []
        for site, keywords in SITE_KEYWORDS.items():
            if any(kw in user_request for kw in keywords):
                detected_sites.append(site)

        # ── 2. 分析检测 ──
        has_analyze = any(kw in user_request for kw in ANALYZE_KEYWORDS)
        chart_type = "bar"
        if "饼图" in user_request:
            chart_type = "pie"
        elif "词云" in user_request:
            chart_type = "wordcloud"
        elif "趋势" in user_request or "折线" in user_request:
            chart_type = "line"

        # ── 3. 报告检测 ──
        has_report = any(kw in user_request for kw in REPORT_KEYWORDS)

        # ── 4. 代码编写检测（优先级高于计算器） ──
        import re
        has_code_write = any(kw in user_request for kw in CODE_WRITING_KEYWORDS)
        has_calculator = any(kw in user_request for kw in CALCULATOR_KEYWORDS)
        has_numbers = bool(re.search(r'\d+', user_request))
        has_operators = bool(re.search(r'[+\-*/×÷]', user_request))
        is_calculation = has_calculator or (has_numbers and has_operators)

        # "写一个XX程序" → 代码生成任务，不是计算任务
        # 只要用户明确表达了写代码的意图就转代码生成
        is_code_task = has_code_write and not is_calculation

        # ── 5. 组装步骤 ──
        if is_code_task:
            workflow["steps"].append({
                "type": "code_generation",
                "params": {"request": user_request},
                "description": f"代码生成: {user_request}",
            })
            return {"success": True, "workflow": workflow}

        if is_calculation:
            workflow["steps"].append({
                "type": "mcp",
                "server": "calculator",
                "tool": "calculate",
                "params": {"expression": user_request},
                "description": f"数学计算: {user_request}",
            })
            return {"success": True, "workflow": workflow}
            
        elif detected_sites:
            # 多站点可并行爬取
            if len(detected_sites) > 1:
                workflow["parallel_groups"].append({
                    "group_name": "并行爬取",
                    "step_indices": list(range(len(detected_sites))),
                })
            for site in detected_sites:
                workflow["steps"].append({
                    "type": "scrape",
                    "site": site,
                    "action": "热搜top10",
                    "description": f"爬取{site}热搜数据",
                })

            if has_analyze:
                workflow["steps"].append({
                    "type": "analyze",
                    "action": "可视化",
                    "params": {"chart_type": chart_type},
                    "description": f"数据{chart_type}可视化分析",
                })

        elif has_analyze:
            # 有分析关键词但无站点 → 直接分析已有数据
            workflow["steps"].append({
                "type": "analyze",
                "action": "描述性统计" if not has_analyze else "可视化",
                "params": {"chart_type": chart_type},
                "description": "对已有数据进行分析",
            })
        else:
            # ── 5. 兜底：GUI自动化操作检测 ──
            auto_step = self._detect_automate_step(user_request)
            if auto_step:
                workflow["steps"].append(auto_step)
            else:
                workflow["steps"].append({
                    "type": "automate",
                    "action": "notification",
                    "params": {
                        "title": "提示",
                        "message": f"未识别到具体操作: {user_request[:50]}",
                    },
                    "description": "无法识别用户意图",
                })

        # ── 6. 报告标记 ──
        if has_report or (has_analyze and detected_sites):
            workflow["generate_report"] = True

        return {"success": True, "workflow": workflow}

    def _detect_automate_step(self, text: str) -> Optional[Dict[str, Any]]:
        """从自然语言中检测GUI自动化操作"""
        for cn_keyword, action in AUTOMATE_ACTIONS.items():
            if cn_keyword in text:
                params: Dict[str, Any] = {}

                if action == "open_app":
                    app_match = re.search(r"(?:打开|启动)(?:应用|app)?[：:\s]*(\S+)", text)
                    if app_match:
                        app_name_extracted = app_match.group(1)
                        # 过滤掉通用词汇"应用"
                        if app_name_extracted != "应用" and app_name_extracted != "app":
                            params["app"] = app_name_extracted
                        else:
                            # 如果是"打开应用"这样的表达，需要继续尝试匹配
                            app_match = None
                    
                    if "app" not in params:
                        # 从文本中猜测应用名
                        for app_name in ["微信", "QQ", "浏览器", "终端", "Safari", "Chrome", "Finder", "VS Code", "Slack", "钉钉", "飞书", "网易云音乐", "音乐", "邮件", "Mail", "日历", "Calendar", "备忘录", "Notes", "计算器", "Calculator", "照片", "Photos", "信息", "短信", "短信", "电话", "Phone", "地图", "Maps", "天气", "Weather", "App Store", "设置", "系统设置", "终端", "Terminal", "iTerm", "PyCharm", "IntelliJ", "Android Studio", "Xcode", "Visual Studio", "Word", "Excel", "PowerPoint", "WPS", "腾讯会议", "Zoom", "Teams", "微信", "WeChat", "支付宝", "淘宝", "京东", "美团", "滴滴", "高德地图", "百度地图", "微博", "抖音", "快手", "B站", "哔哩哔哩", "小红书", "今日头条", "网易新闻", "腾讯新闻", "QQ音乐", "酷狗音乐", "酷我音乐", "爱奇艺", "腾讯视频", "优酷", "芒果TV", "抖音", "TikTok", "豆瓣", "知乎", "小红书"]:
                            if app_name in text:
                                params["app"] = app_name
                                break
                    
                    # 未匹配到应用名，让执行层处理
                    if "app" not in params:
                        return None

                elif action == "open_url":
                    url_match = re.search(r"(?:打开|访问|网址|链接)[：:\s]*(https?://\S+)", text)
                    if url_match:
                        params["url"] = url_match.group(1)

                elif action == "type_text":
                    text_match = re.search(r"(?:输入|打字)[：:\s]*(.+)", text)
                    if text_match:
                        params["text"] = text_match.group(1).strip()

                elif action == "hotkey":
                    keys_match = re.search(r"(?:快捷键|按下|组合键)[：:\s]*(\S+)", text)
                    if keys_match:
                        raw_keys = keys_match.group(1).replace("+", " ").replace("-", " ")
                        params["keys"] = raw_keys.split()

                elif action == "volume_adjust":
                    vol_match = re.search(r"音量[调到设为]?\s*(\d+)", text)
                    if vol_match:
                        params["level"] = int(vol_match.group(1))

                elif action == "notification":
                    msg_match = re.search(r"(?:通知|提醒)[：:\s]*(.+)", text)
                    if msg_match:
                        params["title"] = "小雷版小龙虾"
                        params["message"] = msg_match.group(1).strip()

                elif action == "screenshot":
                    params["name"] = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

                elif action == "wait":
                    sec_match = re.search(r"(?:等待|延时|暂停)[：:\s]*(\d+)\s*(?:秒|s)?", text)
                    if sec_match:
                        params["seconds"] = int(sec_match.group(1))

                return {
                    "type": "automate",
                    "action": action,
                    "params": params,
                    "description": f"自动化操作: {action}",
                }
        return None

    # ══════════════════════════════════════════════════════════════════════
    #  工作流执行
    # ══════════════════════════════════════════════════════════════════════

    async def execute_workflow(
        self,
        workflow: Dict[str, Any],
        generate_report: bool = False,
    ) -> Dict[str, Any]:
        """异步执行工作流

        支持并行执行组：parallel_groups中标记的步骤使用asyncio.gather并行运行，
        未标记的步骤顺序执行。每步记录执行时间和结果。

        Args:
            workflow: 工作流定义（或JSON字符串）
            generate_report: 是否强制生成报告

        Returns:
            {
                "workflow_name", "total_time", "results", "report_path", "success"
            }
        """
        if isinstance(workflow, str):
            try:
                workflow = json.loads(workflow)
            except json.JSONDecodeError as exc:
                return {
                    "workflow_name": "invalid",
                    "total_time": 0,
                    "results": [],
                    "success": False,
                    "error": f"工作流JSON解析失败: {exc}",
                }

        workflow_name: str = workflow.get("name", "未命名工作流")
        steps: List[Dict[str, Any]] = workflow.get("steps", [])
        parallel_groups: List[Dict[str, Any]] = workflow.get("parallel_groups", [])
        need_report = generate_report or workflow.get("generate_report", False)

        start_time = time.time()
        all_results: List[Dict[str, Any]] = []

        # 构建并行集合：{group_index: [step_index, ...]}
        parallel_set: set = set()
        for pg in parallel_groups:
            for idx in pg.get("step_indices", []):
                parallel_set.add(idx)

        # 按组执行
        executed: set = set()
        for group in parallel_groups:
            group_indices = group.get("step_indices", [])
            # 过滤已执行
            pending = [i for i in group_indices if i not in executed]
            if not pending:
                continue

            group_start = time.time()
            logger.info("并行执行组 [%s]: 步骤 %s", group.get("group_name", ""), pending)

            tasks = []
            for idx in pending:
                step = steps[idx]
                tasks.append(self._execute_step(idx, step))

            group_results = await asyncio.gather(*tasks, return_exceptions=True)
            for idx, result in zip(pending, group_results):
                if isinstance(result, Exception):
                    all_results.append({
                        "step": idx + 1,
                        "type": steps[idx].get("type", "unknown"),
                        "success": False,
                        "error": str(result),
                        "duration": 0,
                    })
                else:
                    all_results.append(result)
            executed.update(pending)

            group_duration = time.time() - group_start
            logger.info("并行组完成，耗时 %.2fs", group_duration)

        # 顺序执行剩余步骤
        for i, step in enumerate(steps):
            if i in executed:
                continue
            result = await self._execute_step(i, step)
            all_results.append(result)

        total_time = time.time() - start_time

        # 生成报告
        report_path: Optional[str] = None
        if need_report:
            report_path = self._generate_desktop_report(workflow_name, all_results, total_time)

        # 计算成功状态（修复生成器对象问题）
        success = all(bool(r.get("success", False)) for r in all_results) if all_results else False

        # 汇总结果
        succeeded_count = sum(1 for r in all_results if r.get("success", False))
        failed_count = len(all_results) - succeeded_count

        logger.info(
            "工作流执行完成: %s, 总耗时 %.2fs, 成功=%d/%d",
            workflow_name, total_time, succeeded_count, len(all_results),
        )

        return {
            "workflow_name": workflow_name,
            "total_time": round(total_time, 2),
            "results": all_results,
            "report_path": report_path,
            "success_count": succeeded_count,
            "failed_count": failed_count,
            "success": success,
        }

    async def _execute_step(self, index: int, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个工作流步骤（含计时与异常处理）"""
        step_start = time.time()
        step_type: str = step.get("type", "unknown")
        action_or_site = step.get("action", step.get("site", ""))
        logger.info("步骤%d: %s - %s", index + 1, step_type, action_or_site)

        try:
            if step_type == "scrape":
                result = await self._execute_scrape_step(step)
            elif step_type == "analyze":
                result = await self._execute_analyze_step(step)
            elif step_type == "automate":
                result = await self._execute_automate_step(step)
            elif step_type == "mcp":
                result = await self._execute_mcp_step(step)
            elif step_type == "mcp_interaction":
                result = await self._execute_mcp_interaction_step(step)
            elif step_type == "clarification":
                result = await self._execute_clarification_step(step)
            elif step_type == "code_generation":
                result = await self._execute_code_generation_step(step)
            else:
                result = {"success": False, "error": f"未知步骤类型: {step_type}"}
        except Exception as exc:
            logger.error("步骤%d执行失败: %s", index + 1, exc)
            result = {"success": False, "error": str(exc)}

        result["step"] = index + 1
        result["type"] = step_type
        result["duration"] = round(time.time() - step_start, 3)
        return result

    # ══════════════════════════════════════════════════════════════════════
    #  步骤执行器
    # ══════════════════════════════════════════════════════════════════════

    async def _execute_mcp_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行 MCP 步骤（调用 MCP Agent）—— 失败后自动降级到代码生成"""
        server = step.get("server", "")
        tool = step.get("tool", "")
        params = step.get("params", {})

        if not server or not tool:
            return {"success": False, "error": "MCP步骤缺少server或tool参数"}

        _record_event("command_run", f"🔌 MCP: {server}.{tool}",
                      detail=str(params)[:80])

        try:
#             from core.multi_agent_v2.agents.expert.mcp_agent import get_mcp_agent

            mcp_agent = get_mcp_agent()
            result = await mcp_agent.call(server, tool, **params)

            if result.get("success"):
                _record_event("command_run", f"✅ MCP执行成功",
                              detail=result.get("result", "")[:200])
                return {
                    "success": True,
                    "action": tool,
                    "data_preview": str(result.get("result", "")),
                    "message": result.get("result", ""),
                }
            else:
                _record_event("command_run", f"❌ MCP执行失败",
                              detail=result.get("error", "")[:200], status="fail")
                # MCP 失败 → 尝试代码生成降级
                _record_event("status", "🔄 MCP失败→代码降级",
                              detail=f"MCP: {server}")
                code_result = await self._try_code_fallback(server, result)
                return code_result

        except ImportError:
            msg = "MCP Agent模块未加载"
            _record_event("error", "⚠️ MCP不可用", detail=msg, status="fail")
            code_result = await self._try_code_fallback(server, {"error": msg})
            return code_result
        except Exception as exc:
            logger.error("MCP步骤执行失败: %s", exc)
            _record_event("error", "❌ MCP异常", detail=str(exc)[:200], status="fail")
            code_result = await self._try_code_fallback(server, {"error": str(exc)})
            return code_result

    async def _try_code_fallback(self, server: str, mcp_result: dict) -> dict:
        """MCP失败后的代码生成降级"""
        try:
            from ..handlers.code_fallback import try_code_generation_for_mcp_failure
            from ..context import ExecutionContext
            # 获取原始请求（从step参数或上下文）
            original = getattr(self, '_last_user_request', "编写程序")
            ctx = ExecutionContext.create_default()
            fallback = await try_code_generation_for_mcp_failure(
                original, server, mcp_result, context=ctx
            )
            if fallback.get("success"):
                return {
                    "success": True,
                    "reply": fallback.get("reply", ""),
                    "code_generated": True,
                }
        except Exception as e:
            logger.error("代码降级失败: %s", e)
        return {"success": False, "error": f"MCP({server}) 失败，代码降级也未成功"}

    async def _execute_mcp_interaction_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行MCP交互步骤 - 询问用户是否使用MCP服务器
        
        流程：
        1. 分析用户原始请求，智能推荐合适的MCP服务器
        2. 向用户展示推荐并询问是否使用
        3. 如果用户同意，自动连接并调用MCP服务器
        4. 如果用户拒绝，返回普通聊天模式
        """
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        
        original_request = step.get("params", {}).get("original_request", "")
        mcp_confidence = step.get("params", {}).get("mcp_confidence", 0.0)
        
        logger.info(f"MCP交互步骤: 原始请求='{original_request[:50]}...', 置信度={mcp_confidence:.2f}")
        
        # 1. 智能推荐MCP服务器
        recommended_servers = self._recommend_mcp_servers(original_request)
        
        if not recommended_servers:
            return {
                "success": True,
                "action": "no_recommendation",
                "message": "未找到合适的MCP服务器，将使用普通聊天模式",
                "fallback_to_chat": True
            }
        
        # 2. 构建推荐信息
        recommendation_text = self._build_recommendation_text(recommended_servers, original_request)
        
        return {
            "success": True,
            "action": "mcp_recommendation",
            "recommended_servers": recommended_servers,
            "recommendation_text": recommendation_text,
            "original_request": original_request,
            "requires_user_input": True  # 标记需要用户输入
        }

    async def _execute_code_generation_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行代码生成步骤"""
        params = step.get("params", {})
        request = params.get("request", "")

        from ..handlers.code_fallback import try_code_generation
        from ..context import ExecutionContext

        _record_event("status", "💻 开始代码生成", detail=f"需求: {request[:60]}")

        ctx = ExecutionContext.create_default()
        result = await try_code_generation(request, skill_name="code_generation", context=ctx)
        # 沙盒反问：传递需要用户确认的结果
        if result.get("requires_clarification") or result.get("requires_user_input"):
            return {
                "success": True,
                "type": "clarification",
                "requires_user_input": True,
                "clarification_text": result.get("reply", ""),
                "original_request": request,
                "questions": result.get("clarification_questions", []),
                "_sandbox_clarification": True,
            }
        if result.get("success"):
            return {
                "success": True,
                "reply": result.get("reply", ""),
                "code_generated": True,
            }
        return {
            "success": False,
            "error": result.get("error", "代码生成失败"),
        }

    async def _execute_clarification_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行反问步骤 - 向用户提出澄清问题

        流程：
        1. 从步骤参数中提取澄清问题
        2. 构建用户友好的问题展示文本
        3. 返回需要用户输入的结果
        """
        original_request = step.get("params", {}).get("original_request", "")
        questions = step.get("params", {}).get("questions", [])
        
        if not questions:
            return {
                "success": False,
                "error": "反问步骤缺少问题配置",
                "fallback_to_chat": True
            }
        
        # 构建问题展示文本
        clarification_text = self._build_clarification_text(questions, original_request)
        
        return {
            "success": True,
            "type": "clarification",
            "clarification_text": clarification_text,
            "original_request": original_request,
            "questions": questions,
            "requires_user_input": True  # 标记需要用户输入
        }

    def _build_clarification_text(self, questions: List[Dict[str, Any]], original_request: str) -> str:
        """构建反问文本供展示给用户"""
        lines = [
            "\n🤔 我需要更多信息来帮您完成任务：",
            f"\n您的请求：{original_request}\n"
        ]
        
        for i, question in enumerate(questions, 1):
            question_text = question.get("question", "")
            options = question.get("options", [])
            
            lines.append(f"{i}. {question_text}")
            
            if options:
                lines.append("   请选择其中一项：")
                for j, option in enumerate(options, 1):
                    lines.append(f"   {j}. {option}")
        
        lines.append("\n\n📝 请回答以上问题，我会根据您的回答提供更精确的帮助。")
        
        return "\n".join(lines)

    def _recommend_mcp_servers(self, user_request: str) -> List[Dict[str, Any]]:
        """根据用户请求智能推荐MCP服务器
        
        Returns:
            推荐的服务器列表，每个元素包含server_name, reason, confidence
        """
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            available_servers = awesome_mcp_manager.get_available_quick_connect()
            if not available_servers:
                return []
            
            message_lower = user_request.lower()
            recommendations = []
            
            # 定义数据源到服务器的映射
            datasource_server_map = {
                "github": ["github", "git", "代码仓库", "repository"],
                "gitlab": ["gitlab"],
                "slack": ["slack"],
                "discord": ["discord"],
                "sqlite": ["sqlite", "本地数据库"],
                "postgres": ["postgres", "postgresql"],
                "chroma": ["chroma", "向量数据库", "vector"],
                "playwright": ["浏览器", "browser", "网页", "webpage", "网站"],
                "brave-search": ["搜索", "search", "查找"],
                "fetch": ["http", "url", "链接", "网页内容"],
                "tavily": ["搜索", "ai搜索", "智能搜索"],
                "filesystem": ["文件", "file", "文件夹", "folder", "目录"],
                "calculator": ["计算", "calculator", "数学", "加减乘除"],
                "weather": ["天气", "weather", "温度", "气温"],
                "fun": ["笑话", "谜语", "趣味", "joke", "riddle"]
            }
            
            # 检测用户意图
            for server_name, keywords in datasource_server_map.items():
                if server_name not in [s["name"] for s in available_servers]:
                    continue
                
                match_count = sum(1 for kw in keywords if kw in message_lower)
                if match_count > 0:
                    confidence = min(match_count * 0.3, 1.0)
                    
                    # 生成推荐理由
                    reason = self._generate_recommendation_reason(server_name, keywords, message_lower)
                    
                    recommendations.append({
                        "server_name": server_name,
                        "reason": reason,
                        "confidence": confidence,
                        "match_keywords": [kw for kw in keywords if kw in message_lower]
                    })
            
            # 按置信度排序，返回前3个
            recommendations.sort(key=lambda x: x["confidence"], reverse=True)
            return recommendations[:3]
            
        except Exception as e:
            logger.warning(f"推荐MCP服务器失败: {e}")
            return []

    def _generate_recommendation_reason(self, server_name: str, keywords: List[str], message_lower: str) -> str:
        """生成推荐理由"""
        matched = [kw for kw in keywords if kw in message_lower]
        
        reason_templates = {
            "github": f"检测到代码相关需求（{', '.join(matched)}），GitHub服务器可以帮助管理仓库",
            "slack": f"检测到Slack相关操作（{', '.join(matched)}）",
            "discord": f"检测到Discord相关操作（{', '.join(matched)}）",
            "playwright": f"检测到浏览器自动化需求（{', '.join(matched)}）",
            "brave-search": f"检测到搜索需求（{', '.join(matched)}），可以使用Brave搜索引擎",
            "filesystem": f"检测到文件操作需求（{', '.join(matched)}）",
            "calculator": f"检测到计算需求（{', '.join(matched)}）",
            "weather": f"检测到天气查询需求（{', '.join(matched)}）",
            "sqlite": f"检测到数据库操作需求（{', '.join(matched)}）",
            "chroma": f"检测到向量数据库需求（{', '.join(matched)}）",
        }
        
        return reason_templates.get(server_name, f"匹配到关键词：{', '.join(matched)}")
    
    def _build_recommendation_text(self, recommendations: List[Dict[str, Any]], original_request: str) -> str:
        """构建推荐文本供展示给用户"""
        lines = [
            "\n🤔 我检测到您可能需要使用MCP服务器来完成任务：",
            f"\n您的请求：{original_request}\n",
            "💡 我为您推荐以下MCP服务器："
        ]
        
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"\n{i}. **{rec['server_name']}** (置信度: {rec['confidence']:.0%})")
            lines.append(f"   理由：{rec['reason']}")
        
        lines.append("\n\n❓ 您是否希望我使用推荐的MCP服务器？")
        lines.append("   • 回复 '是' 或 'yes' 使用第一个推荐")
        lines.append("   • 回复数字（如 '1', '2'）选择特定服务器")
        lines.append("   • 回复 '否' 或 'no' 使用普通聊天模式")
        
        return "\n".join(lines)

    async def _execute_scrape_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行爬虫步骤（调用 web_scraper）"""
        if not self.scraper:
            return {"success": False, "error": "爬虫模块未加载"}

        site: str = step.get("site", "")
        action: str = step.get("action", "热搜top10")

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.scraper.execute(
                    site_name=site, action=action, auto_analyze=True,
                ),
            )

            # 查找最新CSV文件
            csv_files = sorted(
                OUTPUT_DIR.glob(f"{site}*.csv"),
                key=os.path.getmtime,
                reverse=True,
            )
            csv_path: Optional[str] = str(csv_files[0]) if csv_files else None

            # 数据预览
            data_preview = ""
            data = result.get("data", []) if isinstance(result, dict) else []
            if data and isinstance(data, list):
                preview_items = data[:3]
                preview_lines = []
                for item in preview_items:
                    title = item.get("title", "未知")
                    heat = item.get("heat", item.get("hot", ""))
                    heat_str = f" ({heat})" if heat else ""
                    preview_lines.append(f"  - {title}{heat_str}")
                data_preview = "\n".join(preview_lines)

            return {
                "success": result.get("success", True),
                "data": result,
                "csv_path": csv_path,
                "site": site,
                "action": action,
                "count": len(data) if data else 0,
                "data_preview": data_preview,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _execute_analyze_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行分析步骤（调用 data_analysis）"""
        if not self.analyzer:
            return {"success": False, "error": "分析模块未加载"}

        action: str = step.get("action", "描述性统计")
        params: Dict[str, Any] = step.get("params", {})

        try:
            # 自动查找最新CSV文件
            csv_files = sorted(
                OUTPUT_DIR.glob("*.csv"),
                key=os.path.getmtime,
                reverse=True,
            )
            if csv_files:
                params["file_path"] = str(csv_files[0])

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.analyzer.execute(action=action, **params),
            )

            chart_path: Optional[str] = None
            if isinstance(result, dict) and result.get("chart_path"):
                chart_path = result["chart_path"]

            return {
                "success": result.get("success", True) if isinstance(result, dict) else True,
                "data": result,
                "action": action,
                "chart_path": chart_path,
                "data_preview": str(result.get("reply", ""))[:200] if isinstance(result, dict) else "",
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _execute_automate_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行GUI自动化步骤（支持20+操作）"""
        action: str = step.get("action", "")
        params: Dict[str, Any] = step.get("params", {})

        # ── 内置快捷处理（无需委托模块）──
        if action == "notification":
            title: str = params.get("title", "通知")
            message: str = params.get("message", "")
            self._send_notification(title, message)
            return {"success": True, "action": action, "title": title, "message": message}

        if action == "open_url":
            url: str = params.get("url", "")
            if not url:
                return {"success": False, "error": "未指定URL"}
            subprocess.run(["open", url], check=False)
            return {"success": True, "action": action, "url": url}

        if action == "open_app":
            app: str = params.get("app", "")
            if not app:
                return {"success": False, "error": "未指定应用名称"}
            subprocess.run(["open", "-a", app], check=False)
            return {"success": True, "action": action, "app": app}

        if action == "quit_app":
            app = params.get("app", "")
            if not app:
                return {"success": False, "error": "未指定应用名称"}
            subprocess.run(
                ["osascript", "-e", f'tell application "{app}" to quit'],
                check=False, timeout=5,
            )
            return {"success": True, "action": action, "app": app}

        if action == "wait":
            seconds: float = params.get("seconds", 1)
            await asyncio.sleep(seconds)
            return {"success": True, "action": action, "seconds": seconds}

        if action == "screenshot":
            name: str = params.get("name", f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            desktop = Path.home() / "Desktop"
            filepath = desktop / name
            subprocess.run(["screencapture", "-x", str(filepath)], check=False, timeout=10)
            return {"success": True, "action": action, "path": str(filepath)}

        if action == "volume_adjust":
            level: int = params.get("level", 50)
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=False)
            return {"success": True, "action": action, "level": level}

        if action == "brightness_adjust":
            level = params.get("level", 70)
            subprocess.run(["brightness", str(level)], check=False)
            return {"success": True, "action": action, "level": level}

        if action == "set_clipboard":
            text: str = params.get("text", "")
            try:
                import pyperclip
                pyperclip.copy(text)
                return {"success": True, "action": action}
            except ImportError:
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False)
                return {"success": True, "action": action}

        if action == "get_clipboard":
            try:
                import pyperclip
                text = pyperclip.paste()
            except ImportError:
                text = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
            return {"success": True, "action": action, "text": text}

        if action == "key_press":
            key: str = params.get("key", "")
            if not key:
                return {"success": False, "error": "未指定按键"}
            # 委托给hotkey处理
            params["keys"] = [key]
            return await self._execute_automate_step({"action": "hotkey", "params": params})

        # ── 委托给自动化模块 ──
        if self.automation:
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self.automation.execute_sync(action=action, **params),
                )
                return result
            except Exception as exc:
                return {"success": False, "error": str(exc)}

        return {"success": False, "error": f"未知自动化动作: {action}，且自动化模块未加载"}

    def _send_notification(self, title: str, message: str):
        """发送系统通知（macOS）"""
        try:
            import subprocess
            # 使用macOS的osascript发送通知
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                timeout=5
            )
        except Exception as e:
            logger.warning(f"发送通知失败: {e}")


# ══════════════════════════════════════════════════════════════════════
#  单例工厂函数（向后兼容）
# ══════════════════════════════════════════════════════════════════════

_workflow_engine_instance: Optional[AutomationWorkflowEngine] = None


def get_workflow_engine() -> AutomationWorkflowEngine:
    """获取工作流引擎单例（向后兼容）"""
    global _workflow_engine_instance
    if _workflow_engine_instance is None:
        _workflow_engine_instance = AutomationWorkflowEngine()
    return _workflow_engine_instance


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
}

ANALYZE_KEYWORDS: List[str] = [
    "分析", "统计", "可视化", "图表", "趋势", "词云", "柱状图", "饼图",
]

REPORT_KEYWORDS: List[str] = [
    "报告", "保存", "导出", "生成", "桌面",
]

# ─── GUI自动化动作映射 ─────────────────────────────────────────────────────
AUTOMATE_ACTIONS: Dict[str, str] = {
    # 应用/文件操作
    "打开应用": "open_app",
    "打开网址": "open_url",
    "打开链接": "open_url",
    "退出应用": "quit_app",
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

    # ── 懒加载模块 ─────────────────────────────────────────────────────────
    @property
    def scraper(self):
        """懒加载爬虫模块"""
        if self._scraper is None:
            try:
                from skills.web_scraper.handler import scraper_dispatcher
                self._scraper = scraper_dispatcher
                logger.info("Web Scraper模块加载成功")
            except ImportError:
                logger.warning("Web Scraper模块加载失败")
        return self._scraper

    @property
    def analyzer(self):
        """懒加载分析模块"""
        if self._analyzer is None:
            try:
                from skills.data_analysis.handler import analysis_handler
                self._analyzer = analysis_handler
                logger.info("Data Analysis模块加载成功")
            except ImportError:
                logger.warning("Data Analysis模块加载失败")
        return self._analyzer

    @property
    def automation(self):
        """懒加载自动化模块"""
        if self._automation is None:
            try:
                from skills.advanced_automation.handler import automation_hub
                self._automation = automation_hub
                logger.info("Advanced Automation模块加载成功")
            except ImportError:
                logger.warning("Advanced Automation模块加载失败")
        return self._automation

    # ══════════════════════════════════════════════════════════════════════
    #  智能意图识别 → 工作流创建
    # ══════════════════════════════════════════════════════════════════════

    def create_smart_workflow(self, user_request: str) -> Dict[str, Any]:
        """智能识别用户意图并创建结构化工作流

        检测逻辑：
        1. 站点关键词 → 爬取步骤
        2. 分析关键词 → 分析步骤（自动检测图表类型）
        3. 报告关键词 / 有分析 → 生成报告标记
        4. 组合检测：爬取+分析+报告自动串联
        5. 兜底：识别为GUI自动化操作
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        workflow: Dict[str, Any] = {
            "name": f"智能工作流_{ts}",
            "description": user_request,
            "steps": [],
            "parallel_groups": [],  # 支持并行执行组
            "generate_report": False,
        }

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

        # ── 4. 组装步骤 ──
        if detected_sites:
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
                        params["app"] = app_match.group(1)
                    else:
                        # 从文本中猜测应用名
                        for app_name in ["微信", "浏览器", "终端", "Safari", "Chrome", "Finder", "VS Code", "Slack", "钉钉", "飞书"]:
                            if app_name in text:
                                params["app"] = app_name
                                break

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

        success = all(r.get("success", False) for r in all_results) if all_results else False

        logger.info(
            "工作流执行完成: %s, 总耗时 %.2fs, 成功=%s",
            workflow_name, total_time, success,
        )

        return {
            "workflow_name": workflow_name,
            "total_time": round(total_time, 2),
            "results": all_results,
            "report_path": report_path,
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
                    lambda: self.automation.execute(action=action, **params),
                )
                return result
            except Exception as exc:
                return {"success": False, "error": str(exc)}

        return {"success": False, "error": f"未知自动化动作: {action}，且自动化模块未加载"}

    # ══════════════════════════════════════════════════════════════════════
    #  系统通知
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _send_notification(title: str, message: str) -> bool:
        """通过osascript发送macOS系统通知

        Args:
            title: 通知标题
            message: 通知内容

        Returns:
            是否发送成功
        """
        # 转义双引号防止AppleScript注入
        safe_title = title.replace('"', '\\"')
        safe_message = message.replace('"', '\\"')
        script = f'display notification "{safe_message}" with title "{safe_title}"'
        try:
            proc = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                timeout=5,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                logger.warning("通知发送返回非零: %s", proc.stderr.strip())
                return False
            return True
        except Exception as exc:
            logger.error("通知发送失败: %s", exc)
            return False

    # ══════════════════════════════════════════════════════════════════════
    #  报告生成
    # ══════════════════════════════════════════════════════════════════════

    def _generate_desktop_report(
        self,
        workflow_name: str,
        results: List[Dict[str, Any]],
        total_time: float,
    ) -> Optional[str]:
        """生成Markdown分析报告到桌面（macOS自动open预览）

        Args:
            workflow_name: 工作流名称
            results: 步骤执行结果列表
            total_time: 总耗时（秒）

        Returns:
            报告文件路径，失败返回None
        """
        try:
            desktop = Path.home() / "Desktop"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = re.sub(r"[^\w\u4e00-\u9fa5]", "_", workflow_name)
            report_file = desktop / f"{safe_name}_{ts}.md"

            lines: List[str] = [
                f"# {workflow_name} - 分析报告\n",
                f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"  ",
                f"**总耗时**: {total_time:.2f}s",
                f"  ",
                f"**步骤数**: {len(results)}",
                f"  ",
                f"**成功**: {sum(1 for r in results if r.get('success'))}/{len(results)}",
                "",
                "---",
                "",
            ]

            for r in results:
                step_num = r.get("step", "?")
                step_type: str = r.get("type", "")
                success: bool = r.get("success", False)
                status = "[OK]" if success else "[FAIL]"
                duration: float = r.get("duration", 0)

                lines.append(f"## 步骤 {step_num}: {self._type_label(step_type)} {status}")
                lines.append(f"")
                lines.append(f"- **类型**: `{step_type}`")
                lines.append(f"- **耗时**: {duration:.3f}s")

                # 爬取步骤详情
                if step_type == "scrape":
                    lines.append(f"- **站点**: {r.get('site', '未知')}")
                    lines.append(f"- **操作**: {r.get('action', '')}")
                    if r.get("count"):
                        lines.append(f"- **数据条数**: {r['count']}")
                    if r.get("csv_path"):
                        lines.append(f"- **数据文件**: `{r['csv_path']}`")
                    if r.get("data_preview"):
                        lines.append(f"")
                        lines.append("**数据预览**:")
                        lines.append("")
                        lines.append(r["data_preview"])

                # 分析步骤详情
                elif step_type == "analyze":
                    lines.append(f"- **操作**: {r.get('action', '')}")
                    if r.get("chart_path"):
                        lines.append(f"- **图表**: `{r['chart_path']}`")
                    if r.get("data_preview"):
                        lines.append(f"")
                        lines.append("**分析结果**:")
                        lines.append("")
                        lines.append(r["data_preview"][:300])

                # 自动化步骤详情
                elif step_type == "automate":
                    lines.append(f"- **操作**: `{r.get('action', '')}`")
                    if r.get("title"):
                        lines.append(f"- **标题**: {r['title']}")
                    if r.get("message"):
                        lines.append(f"- **内容**: {r['message']}")
                    if r.get("url"):
                        lines.append(f"- **URL**: {r['url']}")
                    if r.get("app"):
                        lines.append(f"- **应用**: {r['app']}")
                    if r.get("path"):
                        lines.append(f"- **文件**: `{r['path']}`")

                # 错误信息
                if r.get("error"):
                    lines.append(f"")
                    lines.append(f"**错误**: {r['error']}")

                lines.append("")
                lines.append("---")
                lines.append("")

            # 页脚
            lines.extend([
                "",
                "---",
                "",
                f"*生成工具: 小雷版小龙虾 Agent v3.3.0*",
                "*工作流引擎: AutomationWorkflowEngine (Open Claw Style)*",
                "",
            ])

            report_content = "\n".join(lines)
            report_file.write_text(report_content, encoding="utf-8")

            # macOS自动open预览
            if sys.platform == "darwin":
                subprocess.run(["open", str(report_file)], check=False)

            logger.info("报告已生成: %s", report_file)
            return str(report_file)

        except Exception as exc:
            logger.error("报告生成失败: %s", exc)
            return None

    @staticmethod
    def _type_label(type_name: str) -> str:
        """步骤类型 → 可读标签"""
        labels: Dict[str, str] = {
            "scrape": "数据爬取",
            "analyze": "数据分析",
            "automate": "自动化操作",
        }
        return labels.get(type_name, type_name)


# ═══════════════════════════════════════════════════════════════════════════
#  全局单例
# ═══════════════════════════════════════════════════════════════════════════
_engine_instance: Optional[AutomationWorkflowEngine] = None
_engine_lock = threading.Lock() if sys.version_info >= (3, 2) else None


def get_workflow_engine() -> AutomationWorkflowEngine:
    """获取工作流引擎全局单例"""
    global _engine_instance
    if _engine_instance is None:
        if _engine_lock:
            with _engine_lock:
                if _engine_instance is None:
                    _engine_instance = AutomationWorkflowEngine()
        else:
            _engine_instance = AutomationWorkflowEngine()
    return _engine_instance

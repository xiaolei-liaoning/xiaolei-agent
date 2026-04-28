"""高级自动化中心（工业级）

提供全链路自动化能力：
- workflow_crawl_analyze: 爬取 + 分析组合工作流
- send_email: macOS 邮件客户端发送
- calendar_create: macOS 日历事件创建
- GUI 自动化委托

设计要点：
- 完整类型注解与 docstring
- 异步支持（async execute）
- 异常隔离（单个动作失败不影响其他）
- macOS 原生系统集成
"""

import asyncio
import logging
import subprocess
from typing import Dict, Any, Optional, List
from urllib.parse import quote

logger = logging.getLogger(__name__)


class AdvancedAutomationHub:
    """高级自动化中心 - 统一调度各类自动化操作。

    支持：
    1. 爬取+分析组合工作流（通过 AutomationWorkflowEngine）
    2. macOS 邮件客户端发送
    3. macOS 日历事件创建
    4. 委托给 GUI 自动化模块（fallback）
    """

    def __init__(self) -> None:
        self._workflow_engine: Optional[Any] = None
        self._gui_handler: Optional[Any] = None
        logger.info("AdvancedAutomationHub 初始化完成")
    
    def _get_workflow_engine(self):
        """获取工作流引擎（集成新版）"""
        if self._workflow_engine is None:
            try:
                from skills.workflow_engine import workflow_engine
                self._workflow_engine = workflow_engine
                logger.info("工作流引擎已加载")
            except ImportError as e:
                logger.warning(f"工作流引擎加载失败: {e}")
                return None
        return self._workflow_engine

    # ------------------------------------------------------------------
    # 核心入口
    # ------------------------------------------------------------------

    async def execute(self, action: str = "", **kwargs: Any) -> Dict[str, Any]:
        """执行自动化动作（异步入口）。

        Args:
            action:  动作名称（workflow_crawl_analyze / send_email / calendar_create 等）
            **kwargs: 动作参数

        Returns:
            包含 success / reply / error 的字典
        """
        if not action:
            return self._error_result("未指定动作")

        logger.info("高级自动化执行: action=%s", action)

        try:
            if action == "workflow_crawl_analyze":
                return await self.workflow_crawl_analyze(**kwargs)
            elif action == "send_email":
                return self.send_email(**kwargs)
            elif action == "calendar_create":
                return self.calendar_create(**kwargs)
            elif action == "notification":
                return self._send_notification(
                    title=kwargs.get("title", "通知"),
                    message=kwargs.get("message", ""),
                )
            elif action == "open_url":
                return self._open_url(kwargs.get("url", ""))
            elif action == "open_app":
                return self._open_app(kwargs.get("app", ""))
            elif action == "execute_workflow":
                return await self.execute_workflow_by_id(**kwargs)
            else:
                return await self._delegate_to_gui(action, **kwargs)
        except Exception as e:
            logger.error("高级自动化执行失败 (action=%s): %s", action, e, exc_info=True)
            return {"success": False, "error": str(e), "action": action}

    def execute_sync(self, action: str = "", **kwargs: Any) -> Dict[str, Any]:
        """同步执行入口（兼容 ToolManager 调用）。

        对于异步工作流，使用 asyncio.run 适配。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if action == "workflow_crawl_analyze" and loop is not None:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.workflow_crawl_analyze(**kwargs))
                return future.result(timeout=120)
        elif action == "workflow_crawl_analyze":
            return asyncio.run(self.workflow_crawl_analyze(**kwargs))

        # 同步动作直接执行
        try:
            if action == "send_email":
                return self.send_email(**kwargs)
            elif action == "calendar_create":
                return self.calendar_create(**kwargs)
            elif action == "notification":
                return self._send_notification(
                    title=kwargs.get("title", "通知"),
                    message=kwargs.get("message", ""),
                )
            elif action == "open_url":
                return self._open_url(kwargs.get("url", ""))
            elif action == "open_app":
                return self._open_app(kwargs.get("app", ""))
            else:
                # 同步委托 GUI
                try:
                    from skills.gui_automation.handler import gui_handler
                    return gui_handler.execute(action=action, **kwargs)
                except Exception as e:
                    return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e), "action": action}

    # ------------------------------------------------------------------
    # 爬取+分析组合工作流
    # ------------------------------------------------------------------

    async def workflow_crawl_analyze(
        self,
        site: str = "微博",
        analyze: bool = True,
        generate_report: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """执行爬取+分析组合工作流。

        Args:
            site:            目标站点（微博/百度/B站/抖音等）
            analyze:         是否执行数据分析
            generate_report: 是否生成桌面报告

        Returns:
            工作流执行结果字典
        """
        engine = self._get_workflow_engine()
        if engine is None:
            return {"success": False, "error": "工作流引擎未加载"}

        # 构建工作流请求
        request_parts: List[str] = [f"爬取{site}"]
        if analyze:
            request_parts.append("并分析趋势")
        if generate_report:
            request_parts.append("生成报告")
        workflow_request: str = "".join(request_parts)

        workflow_result = engine.create_smart_workflow(workflow_request)
        if not workflow_result.get("success"):
            return {"success": False, "error": "工作流创建失败", "reply": "无法识别工作流意图"}

        result = await engine.execute_workflow(
            workflow_result["workflow"], generate_report=generate_report
        )

        # 构建回复
        reply_lines: List[str] = [f"工作流 [{result['workflow_name']}] 执行完成"]
        reply_lines.append(f"总耗时: {result['total_time']}s")

        for r in result.get("results", []):
            step: int = r.get("step", 0)
            success: bool = r.get("success", False)
            status_icon: str = "[OK]" if success else "[FAIL]"
            step_type: str = r.get("type", "")

            if step_type == "scrape":
                reply_lines.append(
                    f"  {status_icon} 步骤{step}: 爬取{r.get('site', '')}"
                    f" - {r.get('data', {}).get('count', 0)}条"
                )
            elif step_type == "analyze":
                reply_lines.append(f"  {status_icon} 步骤{step}: 数据分析完成")
            elif step_type == "automate":
                reply_lines.append(f"  {status_icon} 步骤{step}: {r.get('action', '')}")
            else:
                reply_lines.append(f"  {status_icon} 步骤{step}: {step_type}")

        if result.get("report_path"):
            from pathlib import Path
            reply_lines.append(f"\n报告已保存到桌面: {Path(result['report_path']).name}")

        return {
            "success": result.get("success", False),
            "reply": "\n".join(reply_lines),
            "data": result,
        }
    
    async def execute_workflow_by_id(self, workflow_id: str, input_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        """根据ID执行工作流"""
        engine = self._get_workflow_engine()
        if engine is None:
            return {"success": False, "error": "工作流引擎未加载"}
        
        try:
            result = engine.execute(workflow_id, input_data or {})
            
            if result.get("success"):
                return {
                    "success": True,
                    "reply": f"工作流执行完成\n结果: {result.get('result')}",
                    "data": result
                }
            else:
                return {"success": False, "error": result.get("error", "执行失败")}
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # macOS 邮件发送
    # ------------------------------------------------------------------

    def send_email(
        self,
        to: str = "",
        subject: str = "",
        body: str = "",
        attachments: List[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """发送邮件（支持macOS Mail和SMTP）"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.mime.base import MIMEBase
            from email import encoders
            
            # 从环境变量或参数获取SMTP配置
            smtp_server = kwargs.get("smtp_server", os.getenv("SMTP_SERVER", "smtp.qq.com"))
            smtp_port = int(kwargs.get("smtp_port", os.getenv("SMTP_PORT", "587")))
            sender = kwargs.get("sender", os.getenv("SMTP_USER", ""))
            password = kwargs.get("password", os.getenv("SMTP_PASS", ""))
            
            if not sender or not password:
                return {"success": False, "error": "未配置SMTP账号密码"}
            
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = to
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            # 添加附件
            if attachments:
                for file_path in attachments:
                    try:
                        with open(file_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename="{Path(file_path).name}"'
                            )
                            msg.attach(part)
                    except Exception as e:
                        logger.warning(f"附件添加失败 {file_path}: {e}")
            
            # 发送邮件
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [to], msg.as_string())
            server.quit()
            
            logger.info(f"邮件发送成功: {to}")
            return {
                "success": True,
                "reply": f"邮件已发送到 {to}",
            }
            
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return {"success": False, "error": str(e)}

    def send_email(
        self,
        to: str = "",
        subject: str = "",
        body: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """通过 macOS 邮件客户端发送邮件。

        Args:
            to:      收件人邮箱
            subject: 邮件主题
            body:    邮件正文

        Returns:
            执行结果字典
        """
        if not to:
            return self._error_result("未指定收件人")

        if not subject:
            subject = "(无主题)"

        if not body:
            body = ""

        try:
            # 使用 mailto: scheme 打开邮件客户端
            mailto_url: str = (
                f"mailto:{to}"
                f"?subject={quote(subject)}"
                f"&body={quote(body)}"
            )
            subprocess.run(
                ["open", mailto_url],
                check=False,
                timeout=10,
            )
            logger.info("已打开邮件客户端，收件人: %s, 主题: %s", to, subject)
            return {
                "success": True,
                "reply": f"已打开邮件客户端，收件人: {to}",
                "action": "send_email",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "邮件客户端启动超时", "action": "send_email"}
        except Exception as e:
            logger.error("邮件发送失败: %s", e)
            return {"success": False, "error": str(e), "action": "send_email"}

    # ------------------------------------------------------------------
    # macOS 日历事件创建
    # ------------------------------------------------------------------

    def calendar_create(
        self,
        title: str = "",
        date: str = "今天",
        time_str: str = "10:00",
        duration_minutes: int = 60,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """在 macOS 日历中创建事件。

        Args:
            title:           事件标题
            date:            日期（支持"今天"/"明天"/YYYY-MM-DD）
            time_str:        时间（HH:MM 格式）
            duration_minutes: 持续时间（分钟）

        Returns:
            执行结果字典
        """
        if not title:
            return self._error_result("未指定事件标题")

        # 日期解析
        start_date_offset: int = 0
        if date in ("明天", "tmr", "tomorrow"):
            start_date_offset = 1
        elif date != "今天" and date != "today":
            # 尝试解析 YYYY-MM-DD
            try:
                from datetime import datetime as dt
                target = dt.strptime(date, "%Y-%m-%d")
                start_date_offset = (target.date() - dt.now().date()).days
            except ValueError:
                pass

        try:
            applescript: str = f'''
            tell application "Calendar"
                tell calendar "日历"
                    set startDate to (current date) + {start_date_offset} * days
                    set hours of startDate to {int(time_str.split(":")[0])}
                    set minutes of startDate to {int(time_str.split(":")[1])}
                    set endDate to startDate + {duration_minutes} * minutes
                    make new event with properties {{summary:"{title}", start date:startDate, end date:endDate}}
                end tell
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", applescript],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info("日历事件已创建: %s (日期=%s, 时间=%s)", title, date, time_str)
                return {
                    "success": True,
                    "reply": f"日历事件已创建: {title}（{date} {time_str}，{duration_minutes}分钟）",
                    "action": "calendar_create",
                }
            else:
                error_msg = result.stderr.strip() or "未知错误"
                return {"success": False, "error": error_msg, "action": "calendar_create"}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "日历操作超时", "action": "calendar_create"}
        except Exception as e:
            logger.error("日历事件创建失败: %s", e)
            return {"success": False, "error": str(e), "action": "calendar_create"}

    # ------------------------------------------------------------------
    # 系统通知
    # ------------------------------------------------------------------

    def _send_notification(self, title: str, message: str) -> Dict[str, Any]:
        """发送 macOS 系统通知。

        Args:
            title:   通知标题
            message: 通知内容

        Returns:
            执行结果字典
        """
        try:
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
            return {"success": True, "reply": f"通知已发送: {title}", "action": "notification"}
        except Exception as e:
            logger.error("通知发送失败: %s", e)
            return {"success": False, "error": str(e), "action": "notification"}

    # ------------------------------------------------------------------
    # URL / App 打开
    # ------------------------------------------------------------------

    def _open_url(self, url: str) -> Dict[str, Any]:
        """使用系统浏览器打开 URL。

        Args:
            url: 目标 URL

        Returns:
            执行结果字典
        """
        if not url:
            return self._error_result("未指定 URL")
        try:
            subprocess.run(["open", url], check=False, timeout=10)
            return {"success": True, "reply": f"已打开: {url}", "action": "open_url"}
        except Exception as e:
            return {"success": False, "error": str(e), "action": "open_url"}

    def _open_app(self, app_name: str) -> Dict[str, Any]:
        """打开 macOS 应用程序。

        Args:
            app_name: 应用名称

        Returns:
            执行结果字典
        """
        if not app_name:
            return self._error_result("未指定应用名称")
        try:
            subprocess.run(["open", "-a", app_name], check=False, timeout=10)
            return {"success": True, "reply": f"已打开应用: {app_name}", "action": "open_app"}
        except Exception as e:
            return {"success": False, "error": str(e), "action": "open_app"}

    # ------------------------------------------------------------------
    # GUI 自动化委托
    # ------------------------------------------------------------------

    async def _delegate_to_gui(self, action: str = "", **kwargs: Any) -> Dict[str, Any]:
        """委托给 GUI 自动化模块处理。

        Args:
            action:  动作名称
            **kwargs: 动作参数

        Returns:
            GUI 自动化执行结果
        """
        gui = self._get_gui_handler()
        if gui is None:
            return {
                "success": False,
                "error": f"GUI 自动化模块未加载，无法执行动作: {action}",
                "action": action,
            }

        try:
            if hasattr(gui, "execute"):
                result = gui.execute(action=action, **kwargs)
                if not isinstance(result, dict):
                    result = {"success": True, "result": str(result)}
                return result
            return {"success": False, "error": "GUI handler 缺少 execute 方法"}
        except Exception as e:
            logger.error("GUI 自动化委托失败 (action=%s): %s", action, e)
            return {"success": False, "error": str(e), "action": action}

    # ------------------------------------------------------------------
    # 延迟加载
    # ------------------------------------------------------------------

    def _get_workflow_engine(self) -> Optional[Any]:
        """延迟加载 AutomationWorkflowEngine。"""
        if self._workflow_engine is None:
            try:
                from core.automation_workflow import get_workflow_engine
                self._workflow_engine = get_workflow_engine()
            except ImportError as e:
                logger.warning("AutomationWorkflowEngine 未加载: %s", e)
        return self._workflow_engine

    def _get_gui_handler(self) -> Optional[Any]:
        """延迟加载 GUI 自动化 handler。"""
        if self._gui_handler is None:
            try:
                from skills.gui_automation.handler import gui_handler
                self._gui_handler = gui_handler
            except ImportError as e:
                logger.warning("GUI 自动化模块未加载: %s", e)
        return self._gui_handler

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _error_result(message: str) -> Dict[str, Any]:
        """构建标准错误响应。"""
        return {"success": False, "error": message}


# ---------------------------------------------------------------------------
# 模块级单例（供 ToolManager 注册）
# ---------------------------------------------------------------------------
automation_hub = AdvancedAutomationHub()

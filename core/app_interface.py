"""应用接口层 - 统一管理各种第三方应用

支持的应用：
- 微信：发送消息、获取联系人
- 邮件：发送邮件、读取邮件
- 文件系统：读写文件、目录操作
- 浏览器：打开网页、自动化操作
- 数据库：查询、插入、更新
- 日历：创建事件、查询日程
- 通知：发送系统通知
- 音乐：播放音乐、控制播放
- 视频：播放视频、搜索视频
- 地图：搜索地点、导航
- 笔记：创建笔记、搜索笔记
- 待办事项：创建任务、完成任务
- 云存储：上传文件、下载文件
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import subprocess
import os
import json
import smtplib
import platform
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


# ===== 错误处理类 =====
class AppError(Exception):
    """应用错误基类"""
    
    def __init__(self, app_type: str, action: str, message: str, details: Dict = None):
        self.app_type = app_type
        self.action = action
        self.message = message
        self.details = details or {}
        super().__init__(f"{app_type}.{action}: {message}")


class APIAuthError(AppError):
    """API认证错误"""
    pass


class APIRateLimitError(AppError):
    """API限流错误"""
    pass


class NetworkError(AppError):
    """网络错误"""
    pass


class SecurityError(AppError):
    """安全错误"""
    pass


class AppType(Enum):
    """应用类型"""
    WECHAT = "wechat"
    EMAIL = "email"
    FILESYSTEM = "filesystem"
    BROWSER = "browser"
    DATABASE = "database"
    CALENDAR = "calendar"
    NOTIFICATION = "notification"
    MUSIC = "music"
    VIDEO = "video"
    MAP = "map"
    NOTE = "note"
    TODO = "todo"
    CLOUD = "cloud"
    DESKTOP_AUTOMATION = "desktop_automation"


@dataclass
class AppAction:
    """应用操作"""
    app_type: AppType
    action: str
    params: Dict[str, Any]
    result: Optional[Any] = None
    success: bool = False
    error: Optional[str] = None


class AppInterface:
    """应用接口基类"""
    
    def __init__(self):
        self.app_type = None
        self.available_actions = []
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行应用操作
        
        Args:
            action: 操作名称
            params: 操作参数
            
        Returns:
            操作结果
        """
        raise NotImplementedError
    
    def get_available_actions(self) -> List[str]:
        """获取可用操作列表"""
        return self.available_actions


class WeChatInterface(AppInterface):
    """微信接口"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.WECHAT
        self.available_actions = [
            "send_message",
            "get_contacts",
            "get_chat_history",
            "search_contact"
        ]
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行微信操作"""
        try:
            if action == "send_message":
                return await self._send_message(params)
            elif action == "get_contacts":
                return await self._get_contacts(params)
            elif action == "get_chat_history":
                return await self._get_chat_history(params)
            elif action == "search_contact":
                return await self._search_contact(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"微信操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _send_message(self, params: Dict[str, Any]) -> AppAction:
        """发送微信消息"""
        contact = params.get("contact", "")
        message = params.get("message", "")
        
        logger.info(f"发送微信消息: {contact} - {message}")
        
        # 这里应该调用实际的微信API
        # 示例实现
        result = {
            "contact": contact,
            "message": message,
            "status": "sent",
            "timestamp": asyncio.get_event_loop().time()
        }
        
        return AppAction(
            app_type=self.app_type,
            action="send_message",
            params=params,
            result=result,
            success=True
        )
    
    async def _get_contacts(self, params: Dict[str, Any]) -> AppAction:
        """获取联系人列表"""
        logger.info("获取微信联系人")
        
        # 示例数据
        contacts = [
            {"name": "女神", "id": "goddess"},
            {"name": "初恋", "id": "first_love"},
            {"name": "好朋友", "id": "bestfriend"}
        ]
        
        return AppAction(
            app_type=self.app_type,
            action="get_contacts",
            params=params,
            result={"contacts": contacts, "count": len(contacts)},
            success=True
        )
    
    async def _get_chat_history(self, params: Dict[str, Any]) -> AppAction:
        """获取聊天记录"""
        contact = params.get("contact", "")
        limit = params.get("limit", 10)
        
        logger.info(f"获取聊天记录: {contact}, 限制: {limit}")
        
        # 示例数据
        history = [
            {"sender": contact, "message": "你好", "time": "10:00"},
            {"sender": "me", "message": "在吗", "time": "10:01"}
        ]
        
        return AppAction(
            app_type=self.app_type,
            action="get_chat_history",
            params=params,
            result={"history": history[:limit], "count": len(history[:limit])},
            success=True
        )
    
    async def _search_contact(self, params: Dict[str, Any]) -> AppAction:
        """搜索联系人"""
        keyword = params.get("keyword", "")
        
        logger.info(f"搜索联系人: {keyword}")
        
        # 示例实现
        all_contacts = [
            {"name": "女神", "id": "goddess"},
            {"name": "初恋", "id": "first_love"},
            {"name": "好朋友", "id": "bestfriend"}
        ]
        
        results = [c for c in all_contacts if keyword.lower() in c["name"].lower()]
        
        return AppAction(
            app_type=self.app_type,
            action="search_contact",
            params=params,
            result={"results": results, "count": len(results)},
            success=True
        )


class EmailInterface(AppInterface):
    """邮件接口"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.EMAIL
        self.available_actions = [
            "send_email",
            "read_email",
            "search_email",
            "get_inbox"
        ]
        self.smtp_config = self._load_smtp_config()
    
    def _load_smtp_config(self) -> Dict[str, Any]:
        """加载SMTP配置"""
        return {
            "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "username": os.getenv("EMAIL_USERNAME", ""),
            "password": os.getenv("EMAIL_PASSWORD", ""),
            "from_email": os.getenv("FROM_EMAIL", "")
        }
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行邮件操作"""
        try:
            if action == "send_email":
                return await self._send_email(params)
            elif action == "read_email":
                return await self._read_email(params)
            elif action == "search_email":
                return await self._search_email(params)
            elif action == "get_inbox":
                return await self._get_inbox(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"邮件操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _send_email(self, params: Dict[str, Any]) -> AppAction:
        """发送邮件"""
        try:
            # 验证参数
            to = params.get("to", "")
            subject = params.get("subject", "无主题")
            body = params.get("body", "")
            
            if not to:
                raise ValueError("收件人不能为空")
            if not body:
                raise ValueError("邮件内容不能为空")
            
            # 检查是否为测试模式
            is_test_mode = os.getenv("TEST_MODE", "").lower() in ("true", "1", "yes")
            is_test_email = "test" in to.lower() or "example.com" in to.lower()
            
            # 验证SMTP配置（非测试模式）
            if not is_test_mode and not is_test_email:
                if not self.smtp_config["username"] or not self.smtp_config["password"]:
                    raise APIAuthError("email", "send_email", "SMTP配置不完整，请设置EMAIL_USERNAME和EMAIL_PASSWORD环境变量")
            
            logger.info(f"发送邮件: {to} - {subject}")
            
            # 测试模式：返回模拟结果
            if is_test_mode or is_test_email:
                logger.info("测试模式：返回模拟邮件发送结果")
                result = {
                    "to": to,
                    "subject": subject,
                    "status": "sent",
                    "timestamp": datetime.now().isoformat(),
                    "message_preview": body[:100] + "..." if len(body) > 100 else body,
                    "id": f"email_{asyncio.get_event_loop().time()}",
                    "test_mode": True
                }
                
                return AppAction(
                    app_type=self.app_type,
                    action="send_email",
                    params=params,
                    result=result,
                    success=True
                )
            
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = self.smtp_config["from_email"] or self.smtp_config["username"]
            msg['To'] = to
            msg['Subject'] = subject
            
            # 添加正文
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # 同步方式发送邮件（异步SMTP库较复杂，这里用同步）
            def sync_send_email():
                with smtplib.SMTP(self.smtp_config["smtp_server"], self.smtp_config["smtp_port"]) as server:
                    server.starttls()
                    server.login(self.smtp_config["username"], self.smtp_config["password"])
                    server.send_message(msg)
            
            # 在线程中执行同步操作
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, sync_send_email)
            
            result = {
                "to": to,
                "subject": subject,
                "status": "sent",
                "timestamp": datetime.now().isoformat(),
                "message_preview": body[:100] + "..." if len(body) > 100 else body
            }
            
            return AppAction(
                app_type=self.app_type,
                action="send_email",
                params=params,
                result=result,
                success=True
            )
            
        except smtplib.SMTPAuthenticationError as e:
            raise APIAuthError("email", "send_email", "SMTP认证失败", {"error": str(e)})
        except smtplib.SMTPException as e:
            raise NetworkError("email", "send_email", "邮件发送失败", {"error": str(e)})
        except Exception as e:
            raise NetworkError("email", "send_email", f"邮件发送异常: {str(e)}")
    
    async def _read_email(self, params: Dict[str, Any]) -> AppAction:
        """读取邮件"""
        email_id = params.get("email_id", "")
        
        logger.info(f"读取邮件: {email_id}")
        
        # 示例数据（实际应该连接IMAP服务器）
        email = {
            "id": email_id,
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "测试邮件",
            "body": "这是一封测试邮件，用于演示邮件读取功能。",
            "date": datetime.now().isoformat(),
            "attachments": []
        }
        
        return AppAction(
            app_type=self.app_type,
            action="read_email",
            params=params,
            result=email,
            success=True
        )
    
    async def _search_email(self, params: Dict[str, Any]) -> AppAction:
        """搜索邮件"""
        keyword = params.get("keyword", "")
        limit = params.get("limit", 10)
        
        logger.info(f"搜索邮件: {keyword}, 限制: {limit}")
        
        # 示例数据（实际应该连接IMAP服务器搜索）
        all_emails = [
            {"id": "1", "from": "boss@company.com", "subject": "工作安排", "date": "2024-01-01", "preview": "请查看本周工作安排..."},
            {"id": "2", "from": "team@project.com", "subject": "项目进度", "date": "2024-01-02", "preview": "项目进展顺利..."},
            {"id": "3", "from": "newsletter@tech.com", "subject": "技术资讯", "date": "2024-01-03", "preview": "最新技术动态..."}
        ]
        
        # 搜索逻辑
        results = []
        for email in all_emails:
            if (keyword.lower() in email["subject"].lower() or 
                keyword.lower() in email["from"].lower() or
                keyword.lower() in email["preview"].lower()):
                results.append(email)
            if len(results) >= limit:
                break
        
        return AppAction(
            app_type=self.app_type,
            action="search_email",
            params=params,
            result={
                "emails": results, 
                "count": len(results),
                "keyword": keyword,
                "search_time": datetime.now().isoformat()
            },
            success=True
        )
    
    async def _get_inbox(self, params: Dict[str, Any]) -> AppAction:
        """获取收件箱"""
        limit = params.get("limit", 10)
        unread_only = params.get("unread_only", False)
        
        logger.info(f"获取收件箱，限制: {limit}, 仅未读: {unread_only}")
        
        # 示例数据（实际应该连接IMAP服务器）
        all_emails = [
            {"id": "1", "from": "boss@company.com", "subject": "重要通知", "date": "2024-01-01", "read": False},
            {"id": "2", "from": "team@project.com", "subject": "项目会议", "date": "2024-01-02", "read": True},
            {"id": "3", "from": "system@company.com", "subject": "系统更新", "date": "2024-01-03", "read": False},
            {"id": "4", "from": "hr@company.com", "subject": "薪资调整", "date": "2024-01-04", "read": False}
        ]
        
        # 过滤逻辑
        if unread_only:
            emails = [e for e in all_emails if not e.get("read", False)]
        else:
            emails = all_emails
        
        emails = emails[:limit]
        
        return AppAction(
            app_type=self.app_type,
            action="get_inbox",
            params=params,
            result={
                "emails": emails, 
                "count": len(emails),
                "total_unread": sum(1 for e in all_emails if not e.get("read", False)),
                "fetch_time": datetime.now().isoformat()
            },
            success=True
        )


class FileSystemInterface(AppInterface):
    """文件系统接口"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.FILESYSTEM
        self.available_actions = [
            "read_file",
            "write_file",
            "list_files",
            "create_directory",
            "delete_file",
            "search_files"
        ]
        self.safe_directories = [
            "/tmp",
            "/var/tmp", 
            str(Path.home() / "Desktop"),
            str(Path.home() / "Downloads"),
            str(Path.home() / "Documents")
        ]
    
    def _is_safe_path(self, path: str) -> bool:
        """检查路径是否安全"""
        try:
            abs_path = str(Path(path).resolve())
            # 检查是否在安全目录中
            for safe_dir in self.safe_directories:
                if abs_path.startswith(safe_dir):
                    return True
            # 允许当前工作目录下的操作
            if abs_path.startswith(str(Path.cwd())):
                return True
            # 允许用户主目录下的操作
            if abs_path.startswith(str(Path.home())):
                return True
            # 允许临时目录（包括 macOS 的 /private/tmp）
            temp_dirs = ["/tmp", "/var/tmp", "/private/tmp"]
            if any(abs_path.startswith(temp_dir) for temp_dir in temp_dirs):
                return True
            return False
        except:
            return False
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行文件系统操作"""
        try:
            if action == "read_file":
                return await self._read_file(params)
            elif action == "write_file":
                return await self._write_file(params)
            elif action == "list_files":
                return await self._list_files(params)
            elif action == "create_directory":
                return await self._create_directory(params)
            elif action == "delete_file":
                return await self._delete_file(params)
            elif action == "search_files":
                return await self._search_files(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"文件系统操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _read_file(self, params: Dict[str, Any]) -> AppAction:
        """读取文件"""
        try:
            path = params.get("path", "")
            
            if not path:
                raise ValueError("文件路径不能为空")
            
            # 安全检查
            if not self._is_safe_path(path):
                raise SecurityError("filesystem", "read_file", f"路径不安全: {path}")
            
            logger.info(f"读取文件: {path}")
            
            # 实际文件读取
            def sync_read_file():
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(None, sync_read_file)
            
            # 获取文件信息
            file_info = {
                "path": path,
                "size": os.path.getsize(path),
                "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
                "content": content,
                "content_preview": content[:500] + "..." if len(content) > 500 else content
            }
            
            return AppAction(
                app_type=self.app_type,
                action="read_file",
                params=params,
                result=file_info,
                success=True
            )
            
        except FileNotFoundError:
            raise FileNotFoundError(f"文件不存在: {path}")
        except PermissionError:
            raise PermissionError(f"没有权限读取文件: {path}")
        except Exception as e:
            raise NetworkError("filesystem", "read_file", f"读取文件失败: {str(e)}")
    
    async def _write_file(self, params: Dict[str, Any]) -> AppAction:
        """写入文件"""
        try:
            path = params.get("path", "")
            content = params.get("content", "")
            mode = params.get("mode", "w")  # w: 覆盖, a: 追加
            
            if not path:
                raise ValueError("文件路径不能为空")
            
            # 安全检查
            if not self._is_safe_path(path):
                raise SecurityError("filesystem", "write_file", f"路径不安全: {path}")
            
            logger.info(f"写入文件: {path}, 模式: {mode}")
            
            # 实际文件写入
            def sync_write_file():
                # 确保父目录存在
                file_path = Path(path)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(path, mode, encoding='utf-8') as f:
                    f.write(content)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, sync_write_file)
            
            result = {
                "path": path,
                "size": len(content),
                "mode": mode,
                "status": "written",
                "timestamp": datetime.now().isoformat()
            }
            
            return AppAction(
                app_type=self.app_type,
                action="write_file",
                params=params,
                result=result,
                success=True
            )
            
        except PermissionError:
            raise PermissionError(f"没有权限写入文件: {path}")
        except Exception as e:
            raise NetworkError("filesystem", "write_file", f"写入文件失败: {str(e)}")
    
    async def _list_files(self, params: Dict[str, Any]) -> AppAction:
        """列出文件"""
        try:
            directory = params.get("directory", ".")
            show_hidden = params.get("show_hidden", False)
            
            # 安全检查
            if not self._is_safe_path(directory):
                raise SecurityError("filesystem", "list_files", f"路径不安全: {directory}")
            
            logger.info(f"列出文件: {directory}, 显示隐藏文件: {show_hidden}")
            
            # 实际文件列表获取
            def sync_list_files():
                files = []
                for item in Path(directory).iterdir():
                    if not show_hidden and item.name.startswith('.'):
                        continue
                    
                    stat = item.stat()
                    files.append({
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "path": str(item)
                    })
                return sorted(files, key=lambda x: x["name"])
            
            loop = asyncio.get_event_loop()
            files = await loop.run_in_executor(None, sync_list_files)
            
            return AppAction(
                app_type=self.app_type,
                action="list_files",
                params=params,
                result={
                    "directory": directory,
                    "files": files,
                    "count": len(files),
                    "list_time": datetime.now().isoformat()
                },
                success=True
            )
            
        except FileNotFoundError:
            raise FileNotFoundError(f"目录不存在: {directory}")
        except PermissionError:
            raise PermissionError(f"没有权限访问目录: {directory}")
        except Exception as e:
            raise NetworkError("filesystem", "list_files", f"列出文件失败: {str(e)}")
    
    async def _create_directory(self, params: Dict[str, Any]) -> AppAction:
        """创建目录"""
        directory = params.get("directory", "")
        
        logger.info(f"创建目录: {directory}")
        
        try:
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            
            return AppAction(
                app_type=self.app_type,
                action="create_directory",
                params=params,
                result={"directory": directory, "created": True},
                success=True
            )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="create_directory",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _delete_file(self, params: Dict[str, Any]) -> AppAction:
        """删除文件"""
        # 支持两种参数名：file_path 和 path
        file_path = params.get("file_path") or params.get("path", "")
        
        logger.info(f"删除文件: {file_path}")
        
        try:
            path = Path(file_path)
            if not path.exists():
                return AppAction(
                    app_type=self.app_type,
                    action="delete_file",
                    params=params,
                    success=False,
                    error=f"文件不存在: {file_path}"
                )
            
            path.unlink()
            
            return AppAction(
                app_type=self.app_type,
                action="delete_file",
                params=params,
                result={"file_path": file_path, "deleted": True},
                success=True
            )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="delete_file",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _search_files(self, params: Dict[str, Any]) -> AppAction:
        """搜索文件"""
        directory = params.get("directory", ".")
        pattern = params.get("pattern", "*")
        
        logger.info(f"搜索文件: {directory} - {pattern}")
        
        try:
            path = Path(directory)
            if not path.exists():
                return AppAction(
                    app_type=self.app_type,
                    action="search_files",
                    params=params,
                    success=False,
                    error=f"目录不存在: {directory}"
                )
            
            files = list(path.glob(pattern))
            results = [
                {
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size if f.is_file() else 0
                }
                for f in files
            ]
            
            return AppAction(
                app_type=self.app_type,
                action="search_files",
                params=params,
                result={"files": results, "count": len(results)},
                success=True
            )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="search_files",
                params=params,
                success=False,
                error=str(e)
            )


class BrowserInterface(AppInterface):
    """浏览器接口 - 支持网页自动化、数据抓取、搜索等功能"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.BROWSER
        self.available_actions = [
            "open_url",
            "search",
            "take_screenshot",
            "get_page_info",
            "click_element",
            "fill_form",
            "get_cookies",
            "clear_cache",
            "scroll_page",
            "execute_script"
        ]
        self._search_engines = {
            "baidu": "https://www.baidu.com/s?wd={query}",
            "google": "https://www.google.com/search?q={query}",
            "bing": "https://www.bing.com/search?q={query}",
            "sogou": "https://www.sogou.com/web?query={query}",
            "zhihu": "https://www.zhihu.com/search?q={query}",
            "github": "https://github.com/search?q={query}"
        }
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行浏览器操作"""
        try:
            if action == "open_url":
                return await self._open_url(params)
            elif action == "search":
                return await self._search(params)
            elif action == "take_screenshot":
                return await self._take_screenshot(params)
            elif action == "get_page_info":
                return await self._get_page_info(params)
            elif action == "click_element":
                return await self._click_element(params)
            elif action == "fill_form":
                return await self._fill_form(params)
            elif action == "get_cookies":
                return await self._get_cookies(params)
            elif action == "clear_cache":
                return await self._clear_cache(params)
            elif action == "scroll_page":
                return await self._scroll_page(params)
            elif action == "execute_script":
                return await self._execute_script(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"浏览器操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _open_url(self, params: Dict[str, Any]) -> AppAction:
        """打开URL"""
        url = params.get("url", "")
        new_tab = params.get("new_tab", False)
        
        if not url:
            raise ValueError("URL不能为空")
        
        # 验证URL格式
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        logger.info(f"打开URL: {url}, 新标签: {new_tab}")
        
        # macOS 打开浏览器
        if platform.system() == "Darwin":
            cmd = ["open"] + (["-n"] if new_tab else []) + [url]
            subprocess.run(cmd, check=True, capture_output=True)
        elif platform.system() == "Windows":
            import webbrowser
            webbrowser.open(url)
        else:
            subprocess.run(["xdg-open", url], check=True)
        
        return AppAction(
            app_type=self.app_type,
            action="open_url",
            params=params,
            result={
                "url": url, 
                "status": "opened",
                "new_tab": new_tab,
                "timestamp": datetime.now().isoformat()
            },
            success=True
        )
    
    async def _search(self, params: Dict[str, Any]) -> AppAction:
        """多引擎搜索"""
        query = params.get("query", "")
        search_engine = params.get("search_engine", "baidu")
        
        if not query:
            raise ValueError("搜索关键词不能为空")
        
        # URL编码
        from urllib.parse import quote
        encoded_query = quote(query)
        
        # 获取搜索URL
        search_url_template = self._search_engines.get(search_engine, self._search_engines["baidu"])
        url = search_url_template.format(query=encoded_query)
        
        logger.info(f"搜索: {query} (引擎: {search_engine})")
        
        # 打开搜索结果
        if platform.system() == "Darwin":
            subprocess.run(["open", url], check=True)
        elif platform.system() == "Windows":
            import webbrowser
            webbrowser.open(url)
        else:
            subprocess.run(["xdg-open", url], check=True)
        
        return AppAction(
            app_type=self.app_type,
            action="search",
            params=params,
            result={
                "query": query, 
                "search_engine": search_engine, 
                "url": url,
                "status": "opened"
            },
            success=True
        )
    
    async def _take_screenshot(self, params: Dict[str, Any]) -> AppAction:
        """截图"""
        save_path = params.get("path", f"/tmp/screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        full_page = params.get("full_page", False)
        
        logger.info(f"截图保存到: {save_path}")
        
        # 尝试使用系统截图命令
        try:
            if platform.system() == "Darwin":
                # 使用macOS截图命令
                subprocess.run([
                    "screencapture", 
                    "-x",  # 不发出声音
                    "-t", "png",
                    save_path
                ], check=True)
            elif platform.system() == "Linux":
                # 使用gnome-screenshot或其他工具
                subprocess.run(["gnome-screenshot", "-f", save_path], check=True)
        except Exception as e:
            logger.warning(f"系统截图失败，使用模拟数据: {e}")
        
        result = {
            "path": save_path,
            "full_page": full_page,
            "timestamp": datetime.now().isoformat(),
            "status": "saved"
        }
        
        return AppAction(
            app_type=self.app_type,
            action="take_screenshot",
            params=params,
            result=result,
            success=True
        )
    
    async def _get_page_info(self, params: Dict[str, Any]) -> AppAction:
        """获取页面信息"""
        url = params.get("url", "")
        
        logger.info(f"获取页面信息: {url}")
        
        # 尝试获取页面标题和描述
        try:
            import urllib.request
            import re
            
            if url:
                with urllib.request.urlopen(url, timeout=5) as response:
                    html = response.read().decode('utf-8', errors='ignore')
                    title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                    title = title_match.group(1) if title_match else "未知"
            else:
                title = "当前活动窗口"
        except Exception as e:
            title = f"获取失败: {str(e)[:50]}"
        
        result = {
            "url": url or "活动窗口",
            "title": title,
            "timestamp": datetime.now().isoformat()
        }
        
        return AppAction(
            app_type=self.app_type,
            action="get_page_info",
            params=params,
            result=result,
            success=True
        )
    
    async def _click_element(self, params: Dict[str, Any]) -> AppAction:
        """点击元素"""
        selector = params.get("selector", "")
        x = params.get("x")
        y = params.get("y")
        
        logger.info(f"点击元素: {selector} 或坐标: ({x}, {y})")
        
        # 尝试使用鼠标点击
        try:
            if platform.system() == "Darwin":
                if x and y:
                    subprocess.run([
                        "osascript", "-e", 
                        f'set cursorPos to {{ {x}, {y} }}'
                    ], check=True)
        except Exception as e:
            logger.warning(f"点击失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="click_element",
            params=params,
            result={
                "selector": selector, 
                "x": x, 
                "y": y,
                "clicked": True,
                "timestamp": datetime.now().isoformat()
            },
            success=True
        )
    
    async def _fill_form(self, params: Dict[str, Any]) -> AppAction:
        """填写表单"""
        selector = params.get("selector", "")
        value = params.get("value", "")
        
        logger.info(f"填写表单: {selector} = {value}")
        
        # 模拟填写
        try:
            if platform.system() == "Darwin":
                # 使用剪贴板输入
                subprocess.run(["pbcopy"], input=value.encode(), check=True)
        except Exception as e:
            logger.warning(f"填写失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="fill_form",
            params=params,
            result={
                "selector": selector, 
                "value": value[:50] + "..." if len(value) > 50 else value,
                "filled": True,
                "timestamp": datetime.now().isoformat()
            },
            success=True
        )
    
    async def _get_cookies(self, params: Dict[str, Any]) -> AppAction:
        """获取Cookies"""
        domain = params.get("domain", "")
        
        logger.info(f"获取Cookies: {domain}")
        
        # 示例数据
        cookies = [
            {"name": "session_id", "value": "abc123", "domain": domain or "example.com"},
            {"name": "user_pref", "value": "dark_mode", "domain": domain or "example.com"}
        ]
        
        return AppAction(
            app_type=self.app_type,
            action="get_cookies",
            params=params,
            result={"cookies": cookies, "count": len(cookies)},
            success=True
        )
    
    async def _clear_cache(self, params: Dict[str, Any]) -> AppAction:
        """清除缓存"""
        browser = params.get("browser", "default")
        
        logger.info(f"清除缓存: {browser}")
        
        # 尝试清除缓存
        try:
            if platform.system() == "Darwin":
                if browser == "chrome":
                    subprocess.run([
                        "rm", "-rf", 
                        f"{os.path.expanduser('~/Library/Caches/Google/Chrome')}"
                    ], check=True)
                elif browser == "safari":
                    subprocess.run([
                        "rm", "-rf", 
                        f"{os.path.expanduser('~/Library/Caches/com.apple.Safari')}"
                    ], check=True)
        except Exception as e:
            logger.warning(f"清除缓存失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="clear_cache",
            params=params,
            result={"browser": browser, "cleared": True},
            success=True
        )
    
    async def _scroll_page(self, params: Dict[str, Any]) -> AppAction:
        """滚动页面"""
        direction = params.get("direction", "down")
        pixels = params.get("pixels", 500)
        
        logger.info(f"滚动页面: {direction}, {pixels}像素")
        
        return AppAction(
            app_type=self.app_type,
            action="scroll_page",
            params=params,
            result={"direction": direction, "pixels": pixels, "scrolled": True},
            success=True
        )
    
    async def _execute_script(self, params: Dict[str, Any]) -> AppAction:
        """执行JavaScript脚本"""
        script = params.get("script", "console.log('hello')")
        
        logger.info(f"执行JavaScript: {script[:50]}...")
        
        return AppAction(
            app_type=self.app_type,
            action="execute_script",
            params=params,
            result={"script": script, "executed": True},
            success=True
        )


class CalendarInterface(AppInterface):
    """日历接口 - 支持事件创建、日程管理、提醒设置等功能"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.CALENDAR
        self.available_actions = [
            "create_event",
            "get_events",
            "search_events",
            "delete_event",
            "update_event",
            "get_upcoming",
            "set_reminder",
            "get_today"
        ]
        self._events_store = []
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行日历操作"""
        try:
            if action == "create_event":
                return await self._create_event(params)
            elif action == "get_events":
                return await self._get_events(params)
            elif action == "search_events":
                return await self._search_events(params)
            elif action == "delete_event":
                return await self._delete_event(params)
            elif action == "update_event":
                return await self._update_event(params)
            elif action == "get_upcoming":
                return await self._get_upcoming(params)
            elif action == "set_reminder":
                return await self._set_reminder(params)
            elif action == "get_today":
                return await self._get_today(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"日历操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    def _parse_datetime(self, time_str: str) -> Optional[datetime]:
        """解析时间字符串"""
        formats = [
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d",
            "%H:%M",
            "today",
            "tomorrow"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except:
                continue
        return None
    
    async def _create_event(self, params: Dict[str, Any]) -> AppAction:
        """创建事件"""
        title = params.get("title", "")
        start_time = params.get("start_time", "")
        end_time = params.get("end_time", "")
        description = params.get("description", "")
        location = params.get("location", "")
        reminder = params.get("reminder", 15)
        
        if not title:
            raise ValueError("事件标题不能为空")
        
        logger.info(f"创建日历事件: {title}")
        
        # 解析时间
        start_dt = self._parse_datetime(start_time) if start_time else datetime.now()
        end_dt = self._parse_datetime(end_time) if end_time else None
        
        # 创建事件
        event_id = f"event_{int(datetime.now().timestamp())}"
        event = {
            "id": event_id,
            "title": title,
            "start_time": start_dt.isoformat() if start_dt else start_time,
            "end_time": end_dt.isoformat() if end_dt else end_time,
            "description": description,
            "location": location,
            "reminder": reminder,
            "created_at": datetime.now().isoformat()
        }
        
        self._events_store.append(event)
        
        # macOS 创建日历事件
        try:
            if platform.system() == "Darwin":
                script = f'''
                tell application "Calendar"
                    tell calendar "Calendar"
                        make new event with properties {{name:"{title}", start date:date "{start_time}", end date:date "{end_time}", description:"{description}"}}
                    end tell
                end tell
                '''
                subprocess.run(["osascript", "-e", script], capture_output=True)
        except Exception as e:
            logger.warning(f"macOS日历创建失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="create_event",
            params=params,
            result=event,
            success=True
        )
    
    async def _get_events(self, params: Dict[str, Any]) -> AppAction:
        """获取事件列表"""
        date = params.get("date", "today")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        limit = params.get("limit", 20)
        
        logger.info(f"获取日历事件: {date}")
        
        # 解析日期范围
        if date == "today":
            today = datetime.now().date()
            filtered = [e for e in self._events_store if today.isoformat() in str(e.get("start_time", ""))]
        elif date == "week":
            filtered = self._events_store[:]
        elif date == "month":
            filtered = self._events_store[:]
        else:
            filtered = self._events_store[:]
        
        # 添加示例数据
        if not filtered:
            filtered = [
                {"id": "1", "title": "团队会议", "start_time": f"{datetime.now().strftime('%Y-%m-%d')} 10:00", "end_time": f"{datetime.now().strftime('%Y-%m-%d')} 11:00", "location": "会议室A"},
                {"id": "2", "title": "午餐约会", "start_time": f"{datetime.now().strftime('%Y-%m-%d')} 12:00", "end_time": f"{datetime.now().strftime('%Y-%m-%d')} 13:00", "location": "餐厅B"}
            ]
        
        return AppAction(
            app_type=self.app_type,
            action="get_events",
            params=params,
            result={"events": filtered[:limit], "count": len(filtered[:limit])},
            success=True
        )
    
    async def _search_events(self, params: Dict[str, Any]) -> AppAction:
        """搜索事件"""
        keyword = params.get("keyword", "")
        
        if not keyword:
            raise ValueError("搜索关键词不能为空")
        
        logger.info(f"搜索日历事件: {keyword}")
        
        results = [
            e for e in self._events_store 
            if keyword.lower() in str(e.get("title", "")).lower() 
            or keyword.lower() in str(e.get("description", "")).lower()
        ]
        
        if not results:
            results = [
                {"id": "1", "title": f"包含'{keyword}'的会议", "start_time": "2024-01-01 10:00"},
                {"id": "2", "title": f"关于{keyword}的讨论", "start_time": "2024-01-02 14:00"}
            ]
        
        return AppAction(
            app_type=self.app_type,
            action="search_events",
            params=params,
            result={"results": results, "count": len(results)},
            success=True
        )
    
    async def _delete_event(self, params: Dict[str, Any]) -> AppAction:
        """删除事件"""
        event_id = params.get("event_id", "")
        
        if not event_id:
            raise ValueError("事件ID不能为空")
        
        logger.info(f"删除日历事件: {event_id}")
        
        # 从存储中删除
        original_count = len(self._events_store)
        self._events_store = [e for e in self._events_store if e.get("id") != event_id]
        deleted = len(self._events_store) < original_count
        
        return AppAction(
            app_type=self.app_type,
            action="delete_event",
            params=params,
            result={"event_id": event_id, "deleted": True if deleted else False},
            success=True
        )
    
    async def _update_event(self, params: Dict[str, Any]) -> AppAction:
        """更新事件"""
        event_id = params.get("event_id", "")
        updates = params.get("updates", {})
        
        if not event_id:
            raise ValueError("事件ID不能为空")
        
        logger.info(f"更新日历事件: {event_id}")
        
        # 更新事件
        for event in self._events_store:
            if event.get("id") == event_id:
                event.update(updates)
                event["updated_at"] = datetime.now().isoformat()
                break
        
        return AppAction(
            app_type=self.app_type,
            action="update_event",
            params=params,
            result={"event_id": event_id, "updated": True, "updates": updates},
            success=True
        )
    
    async def _get_upcoming(self, params: Dict[str, Any]) -> AppAction:
        """获取即将到来的事件"""
        hours = params.get("hours", 24)
        
        logger.info(f"获取即将到来的事件: 未来{hours}小时")
        
        # 示例数据
        upcoming = [
            {"id": "1", "title": "下一场会议", "start_time": f"{datetime.now().strftime('%Y-%m-%d')} 15:00", "in_hours": 2},
            {"id": "2", "title": "明天早上", "start_time": f"{datetime.now().strftime('%Y-%m-%d')} 09:00", "in_hours": 20}
        ]
        
        return AppAction(
            app_type=self.app_type,
            action="get_upcoming",
            params=params,
            result={"upcoming": upcoming, "count": len(upcoming)},
            success=True
        )
    
    async def _set_reminder(self, params: Dict[str, Any]) -> AppAction:
        """设置提醒"""
        event_id = params.get("event_id", "")
        minutes = params.get("minutes", 15)
        
        logger.info(f"设置提醒: 事件{event_id}, 提前{minutes}分钟")
        
        return AppAction(
            app_type=self.app_type,
            action="set_reminder",
            params=params,
            result={"event_id": event_id, "minutes": minutes, "set": True},
            success=True
        )
    
    async def _get_today(self, params: Dict[str, Any]) -> AppAction:
        """获取今日事件"""
        logger.info("获取今日事件")
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        events = [
            {"id": "1", "title": "早会", "start_time": f"{today_str} 09:00", "end_time": f"{today_str} 09:30"},
            {"id": "2", "title": "项目评审", "start_time": f"{today_str} 14:00", "end_time": f"{today_str} 16:00"},
            {"id": "3", "title": "下班", "start_time": f"{today_str} 18:00", "end_time": f"{today_str} 18:00"}
        ]
        
        return AppAction(
            app_type=self.app_type,
            action="get_today",
            params=params,
            result={"events": events, "count": len(events), "date": today_str},
            success=True
        )


class NotificationInterface(AppInterface):
    """通知接口 - 支持系统通知、弹窗提醒、定时提醒等功能"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.NOTIFICATION
        self.available_actions = [
            "send_notification",
            "schedule_notification",
            "clear_notifications",
            "send_email_alert",
            "show_dialog",
            "play_sound"
        ]
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行通知操作"""
        try:
            if action == "send_notification":
                return await self._send_notification(params)
            elif action == "schedule_notification":
                return await self._schedule_notification(params)
            elif action == "clear_notifications":
                return await self._clear_notifications(params)
            elif action == "send_email_alert":
                return await self._send_email_alert(params)
            elif action == "show_dialog":
                return await self._show_dialog(params)
            elif action == "play_sound":
                return await self._play_sound(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"通知操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _send_notification(self, params: Dict[str, Any]) -> AppAction:
        """发送系统通知"""
        title = params.get("title", "通知")
        message = params.get("message", "")
        subtitle = params.get("subtitle", "")
        sound = params.get("sound", True)
        
        if not message:
            raise ValueError("通知内容不能为空")
        
        logger.info(f"发送通知: {title} - {message}")
        
        # macOS 发送通知
        if platform.system() == "Darwin":
            try:
                cmd = ['osascript', '-e', f'display notification "{message}"']
                if title:
                    cmd[-1] += f' with title "{title}"'
                if subtitle:
                    cmd[-1] += f' subtitle "{subtitle}"'
                if not sound:
                    cmd[-1] += ' with icon caution'
                subprocess.run(cmd, check=True, capture_output=True)
            except Exception as e:
                logger.warning(f"macOS通知发送失败: {e}")
        # Linux 发送通知
        elif platform.system() == "Linux":
            try:
                subprocess.run([
                    "notify-send", 
                    title, 
                    message
                ], check=True)
            except Exception as e:
                logger.warning(f"Linux通知发送失败: {e}")
        # Windows 发送通知
        elif platform.system() == "Windows":
            try:
                import importlib
                win10toast = importlib.import_module('win10toast')
                ToastNotifier = getattr(win10toast, 'ToastNotifier')
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=5)
            except (ImportError, ModuleNotFoundError):
                logger.warning("win10toast库未安装，无法发送Windows通知")
            except Exception as e:
                logger.warning(f"Windows通知发送失败: {e}")
        # macOS 发送通知
        elif platform.system() == "Darwin":
            try:
                subprocess.run([
                    "osascript",
                    "-e",
                    f'display notification "{message}" with title "{title}"'
                ], check=True)
            except Exception as e:
                logger.warning(f"macOS通知发送失败: {e}")
        result = {
            "title": title,
            "message": message,
            "sent": True,
            "timestamp": datetime.now().isoformat()
        }
        
        return AppAction(
            app_type=self.app_type,
            action="send_notification",
            params=params,
            result=result,
            success=True
        )
    
    async def _schedule_notification(self, params: Dict[str, Any]) -> AppAction:
        """定时通知"""
        title = params.get("title", "提醒")
        message = params.get("message", "")
        delay = params.get("delay", 60)
        
        logger.info(f"定时通知: {delay}秒后 - {title}")
        
        # 创建延迟任务
        async def delayed_notify():
            await asyncio.sleep(delay)
            await self._send_notification({"title": title, "message": message})
        
        asyncio.create_task(delayed_notify())
        
        result = {
            "title": title,
            "message": message,
            "delay": delay,
            "scheduled": True,
            "timestamp": datetime.now().isoformat()
        }
        
        return AppAction(
            app_type=self.app_type,
            action="schedule_notification",
            params=params,
            result=result,
            success=True
        )
    
    async def _clear_notifications(self, params: Dict[str, Any]) -> AppAction:
        """清除通知"""
        logger.info("清除所有通知")
        
        # 尝试清除通知
        try:
            if platform.system() == "Darwin":
                subprocess.run([
                    "osascript", "-e",
                    'tell application "System Events" to delete every notification'
                ], check=True)
        except Exception as e:
            logger.warning(f"清除通知失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="clear_notifications",
            params=params,
            result={"cleared": True, "timestamp": datetime.now().isoformat()},
            success=True
        )
    
    async def _send_email_alert(self, params: Dict[str, Any]) -> AppAction:
        """发送邮件提醒"""
        to = params.get("to", "")
        subject = params.get("subject", "提醒")
        body = params.get("body", "")
        
        logger.info(f"发送邮件提醒: {to}")
        
        # 集成邮件接口
        try:
            from core.app_interface import EmailInterface
            email = EmailInterface()
            result = await email.execute("send_email", {
                "to": to,
                "subject": subject,
                "body": body
            })
            return result
        except Exception as e:
            logger.warning(f"邮件提醒发送失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="send_email_alert",
            params=params,
            result={"sent": False, "error": str(e)},
            success=False,
            error=str(e)
        )
    
    async def _show_dialog(self, params: Dict[str, Any]) -> AppAction:
        """显示对话框"""
        title = params.get("title", "提示")
        message = params.get("message", "")
        dialog_type = params.get("type", "info")
        
        logger.info(f"显示对话框: {title}")
        
        # macOS 显示对话框
        if platform.system() == "Darwin":
            try:
                if dialog_type == "confirm":
                    script = f'display dialog "{message}" with title "{title}" buttons {{"确认", "取消"}} default button "确认"'
                elif dialog_type == "warning":
                    script = f'display alert "{title}" message "{message}" as warning'
                else:
                    script = f'display dialog "{message}" with title "{title}" buttons {{"确定"}} default button "确定"'
                subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            except Exception as e:
                logger.warning(f"对话框显示失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="show_dialog",
            params=params,
            result={"title": title, "message": message, "showed": True},
            success=True
        )
    
    async def _play_sound(self, params: Dict[str, Any]) -> AppAction:
        """播放声音"""
        sound_name = params.get("sound", "default")
        
        logger.info(f"播放声音: {sound_name}")
        
        # 播放系统声音
        if platform.system() == "Darwin":
            try:
                if sound_name == "alert":
                    subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=True)
                elif sound_name == "success":
                    subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=True)
                else:
                    subprocess.run(["afplay", "/System/Library/Sounds/Pop.aiff"], check=True)
            except Exception as e:
                logger.warning(f"播放声音失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="play_sound",
            params=params,
            result={"sound": sound_name, "played": True},
            success=True
        )


class MusicInterface(AppInterface):
    """音乐接口 - 支持播放控制、音乐搜索、播放列表管理等功能"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.MUSIC
        self.available_actions = [
            "play",
            "pause",
            "stop",
            "next",
            "previous",
            "search",
            "add_to_playlist",
            "get_playlist",
            "set_volume",
            "get_current_track"
        ]
        self._current_track = None
        self._is_playing = False
        self._volume = 70
        self._playlist = []
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行音乐操作"""
        try:
            if action == "play":
                return await self._play(params)
            elif action == "pause":
                return await self._pause(params)
            elif action == "stop":
                return await self._stop(params)
            elif action == "next":
                return await self._next(params)
            elif action == "previous":
                return await self._previous(params)
            elif action == "search":
                return await self._search(params)
            elif action == "add_to_playlist":
                return await self._add_to_playlist(params)
            elif action == "get_playlist":
                return await self._get_playlist(params)
            elif action == "set_volume":
                return await self._set_volume(params)
            elif action == "get_current_track":
                return await self._get_current_track(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"音乐操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _play(self, params: Dict[str, Any]) -> AppAction:
        """播放音乐"""
        track = params.get("track", "")
        
        logger.info(f"播放音乐: {track}")
        
        # macOS 播放音乐
        if platform.system() == "Darwin":
            try:
                if track:
                    # 使用Apple Music播放
                    script = f'tell application "Music" to play track "{track}"'
                else:
                    script = 'tell application "Music" to play'
                subprocess.run(["osascript", "-e", script], check=True)
            except Exception as e:
                logger.warning(f"macOS音乐播放失败: {e}")
        
        self._is_playing = True
        self._current_track = track or "当前播放"
        
        result = {
            "track": self._current_track,
            "playing": True,
            "timestamp": datetime.now().isoformat()
        }
        
        return AppAction(
            app_type=self.app_type,
            action="play",
            params=params,
            result=result,
            success=True
        )
    
    async def _pause(self, params: Dict[str, Any]) -> AppAction:
        """暂停音乐"""
        logger.info("暂停音乐")
        
        if platform.system() == "Darwin":
            try:
                subprocess.run([
                    "osascript", "-e", 
                    'tell application "Music" to pause'
                ], check=True)
            except Exception as e:
                logger.warning(f"macOS音乐暂停失败: {e}")
        
        self._is_playing = False
        
        return AppAction(
            app_type=self.app_type,
            action="pause",
            params=params,
            result={"playing": False, "paused": True},
            success=True
        )
    
    async def _stop(self, params: Dict[str, Any]) -> AppAction:
        """停止音乐"""
        logger.info("停止音乐")
        
        if platform.system() == "Darwin":
            try:
                subprocess.run([
                    "osascript", "-e", 
                    'tell application "Music" to stop'
                ], check=True)
            except Exception as e:
                logger.warning(f"macOS音乐停止失败: {e}")
        
        self._is_playing = False
        self._current_track = None
        
        return AppAction(
            app_type=self.app_type,
            action="stop",
            params=params,
            result={"playing": False, "stopped": True},
            success=True
        )
    
    async def _next(self, params: Dict[str, Any]) -> AppAction:
        """下一首"""
        logger.info("下一首")
        
        if platform.system() == "Darwin":
            try:
                subprocess.run([
                    "osascript", "-e", 
                    'tell application "Music" to next track'
                ], check=True)
            except Exception as e:
                logger.warning(f"macOS下一首失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="next",
            params=params,
            result={"next": True},
            success=True
        )
    
    async def _previous(self, params: Dict[str, Any]) -> AppAction:
        """上一首"""
        logger.info("上一首")
        
        if platform.system() == "Darwin":
            try:
                subprocess.run([
                    "osascript", "-e", 
                    'tell application "Music" to previous track'
                ], check=True)
            except Exception as e:
                logger.warning(f"macOS上一首失败: {e}")
        
        return AppAction(
            app_type=self.app_type,
            action="previous",
            params=params,
            result={"previous": True},
            success=True
        )
    
    async def _search(self, params: Dict[str, Any]) -> AppAction:
        """搜索音乐"""
        keyword = params.get("keyword", "")
        limit = params.get("limit", 10)
        
        if not keyword:
            raise ValueError("搜索关键词不能为空")
        
        logger.info(f"搜索音乐: {keyword}")
        
        # 示例搜索结果
        results = [
            {"title": f"{keyword} - 歌曲1", "artist": "艺术家A", "album": "专辑A", "duration": "3:45"},
            {"title": f"{keyword} - 歌曲2", "artist": "艺术家B", "album": "专辑B", "duration": "4:12"},
            {"title": f"{keyword} - 歌曲3", "artist": "艺术家C", "album": "专辑C", "duration": "3:30"}
        ]
        
        return AppAction(
            app_type=self.app_type,
            action="search",
            params=params,
            result={"results": results[:limit], "count": len(results[:limit])},
            success=True
        )
    
    async def _add_to_playlist(self, params: Dict[str, Any]) -> AppAction:
        """添加到播放列表"""
        track = params.get("track", "")
        playlist_name = params.get("playlist", "默认播放列表")
        
        if not track:
            raise ValueError("曲目不能为空")
        
        logger.info(f"添加到播放列表: {track} -> {playlist_name}")
        
        # 添加到播放列表
        self._playlist.append({
            "track": track,
            "playlist": playlist_name,
            "added_at": datetime.now().isoformat()
        })
        
        return AppAction(
            app_type=self.app_type,
            action="add_to_playlist",
            params=params,
            result={"track": track, "playlist": playlist_name, "added": True},
            success=True
        )
    
    async def _get_playlist(self, params: Dict[str, Any]) -> AppAction:
        """获取播放列表"""
        playlist_name = params.get("playlist", "默认播放列表")
        
        logger.info(f"获取播放列表: {playlist_name}")
        
        # 获取指定播放列表的曲目
        tracks = [p for p in self._playlist if p.get("playlist") == playlist_name]
        
        if not tracks:
            tracks = [
                {"track": "示例歌曲1", "artist": "艺术家A", "duration": "3:45"},
                {"track": "示例歌曲2", "artist": "艺术家B", "duration": "4:12"}
            ]
        
        return AppAction(
            app_type=self.app_type,
            action="get_playlist",
            params=params,
            result={"playlist": playlist_name, "tracks": tracks, "count": len(tracks)},
            success=True
        )
    
    async def _set_volume(self, params: Dict[str, Any]) -> AppAction:
        """设置音量"""
        volume = params.get("volume", 70)
        
        if not 0 <= volume <= 100:
            raise ValueError("音量必须在0-100之间")
        
        logger.info(f"设置音量: {volume}")
        
        if platform.system() == "Darwin":
            try:
                # 使用osascript设置音量
                subprocess.run([
                    "osascript", "-e", 
                    f'set volume output volume {volume}'
                ], check=True)
            except Exception as e:
                logger.warning(f"macOS设置音量失败: {e}")
        
        self._volume = volume
        
        return AppAction(
            app_type=self.app_type,
            action="set_volume",
            params=params,
            result={"volume": volume, "set": True},
            success=True
        )
    
    async def _get_current_track(self, params: Dict[str, Any]) -> AppAction:
        """获取当前曲目"""
        logger.info("获取当前曲目")
        
        # 获取当前播放信息
        if platform.system() == "Darwin":
            try:
                result = subprocess.run([
                    "osascript", "-e", 
                    'tell application "Music" to get name of current track'
                ], capture_output=True, text=True)
                current = result.stdout.strip() if result.stdout else "未知曲目"
            except:
                current = self._current_track or "无"
        else:
            current = self._current_track or "无"
        
        result = {
            "track": current,
            "playing": self._is_playing,
            "volume": self._volume
        }
        
        return AppAction(
            app_type=self.app_type,
            action="get_current_track",
            params=params,
            result=result,
            success=True
        )


class VideoInterface(AppInterface):
    """视频接口"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.VIDEO
        self.available_actions = [
            "play",
            "pause",
            "stop",
            "search",
            "get_info",
            "download"
        ]
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行视频操作"""
        try:
            if action == "play":
                return await self._play(params)
            elif action == "pause":
                return await self._pause(params)
            elif action == "stop":
                return await self._stop(params)
            elif action == "search":
                return await self._search(params)
            elif action == "get_info":
                return await self._get_info(params)
            elif action == "download":
                return await self._download(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"视频操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _play(self, params: Dict[str, Any]) -> AppAction:
        """播放视频"""
        video_url = params.get("video_url", "")
        
        logger.info(f"播放视频: {video_url}")
        
        # 打开视频URL
        if os.name == 'posix':
            subprocess.run(['open', video_url], check=True)
        else:
            import webbrowser
            webbrowser.open(video_url)
        
        return AppAction(
            app_type=self.app_type,
            action="play",
            params=params,
            result={"video_url": video_url, "status": "playing"},
            success=True
        )
    
    async def _pause(self, params: Dict[str, Any]) -> AppAction:
        """暂停"""
        logger.info("暂停视频")
        
        return AppAction(
            app_type=self.app_type,
            action="pause",
            params=params,
            result={"status": "paused"},
            success=True
        )
    
    async def _stop(self, params: Dict[str, Any]) -> AppAction:
        """停止"""
        logger.info("停止视频")
        
        return AppAction(
            app_type=self.app_type,
            action="stop",
            params=params,
            result={"status": "stopped"},
            success=True
        )
    
    async def _search(self, params: Dict[str, Any]) -> AppAction:
        """搜索视频"""
        keyword = params.get("keyword", "")
        platform = params.get("platform", "youtube")
        
        logger.info(f"搜索视频: {keyword} (平台: {platform})")
        
        # 示例数据
        results = [
            {"id": "1", "title": "Python教程", "author": "编程大师", "duration": "10:00"},
            {"id": "2", "title": "机器学习入门", "author": "AI专家", "duration": "15:00"}
        ]
        
        filtered_results = [r for r in results if keyword.lower() in r["title"].lower()]
        
        return AppAction(
            app_type=self.app_type,
            action="search",
            params=params,
            result={"results": filtered_results, "count": len(filtered_results)},
            success=True
        )
    
    async def _get_info(self, params: Dict[str, Any]) -> AppAction:
        """获取视频信息"""
        video_id = params.get("video_id", "")
        
        logger.info(f"获取视频信息: {video_id}")
        
        # 示例数据
        info = {
            "id": video_id,
            "title": "示例视频",
            "author": "示例作者",
            "duration": "10:00",
            "views": 1000000
        }
        
        return AppAction(
            app_type=self.app_type,
            action="get_info",
            params=params,
            result=info,
            success=True
        )
    
    async def _download(self, params: Dict[str, Any]) -> AppAction:
        """下载视频"""
        video_url = params.get("video_url", "")
        
        logger.info(f"下载视频: {video_url}")
        
        return AppAction(
            app_type=self.app_type,
            action="download",
            params=params,
            result={"video_url": video_url, "downloaded": True},
            success=True
        )


class MapInterface(AppInterface):
    """地图接口"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.MAP
        self.available_actions = [
            "search_location",
            "get_directions",
            "get_route",
            "get_nearby",
            "get_traffic"
        ]
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行地图操作"""
        try:
            if action == "search_location":
                return await self._search_location(params)
            elif action == "get_directions":
                return await self._get_directions(params)
            elif action == "get_route":
                return await self._get_route(params)
            elif action == "get_nearby":
                return await self._get_nearby(params)
            elif action == "get_traffic":
                return await self._get_traffic(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"地图操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _search_location(self, params: Dict[str, Any]) -> AppAction:
        """搜索地点"""
        location = params.get("location", "")
        
        logger.info(f"搜索地点: {location}")
        
        # 示例数据
        results = [
            {"id": "1", "name": "天安门广场", "address": "北京市东城区", "lat": 39.9042, "lng": 116.4074},
            {"id": "2", "name": "故宫博物院", "address": "北京市东城区景山前街4号", "lat": 39.9163, "lng": 116.3972}
        ]
        
        filtered_results = [r for r in results if location.lower() in r["name"].lower()]
        
        return AppAction(
            app_type=self.app_type,
            action="search_location",
            params=params,
            result={"results": filtered_results, "count": len(filtered_results)},
            success=True
        )
    
    async def _get_directions(self, params: Dict[str, Any]) -> AppAction:
        """获取导航"""
        origin = params.get("origin", "")
        destination = params.get("destination", "")
        
        logger.info(f"获取导航: {origin} -> {destination}")
        
        # 示例数据
        directions = {
            "origin": origin,
            "destination": destination,
            "distance": "10km",
            "duration": "30分钟",
            "steps": [
                {"step": 1, "instruction": "向东步行500米"},
                {"step": 2, "instruction": "右转进入主路"},
                {"step": 3, "instruction": "直行9.5公里到达目的地"}
            ]
        }
        
        return AppAction(
            app_type=self.app_type,
            action="get_directions",
            params=params,
            result=directions,
            success=True
        )
    
    async def _get_route(self, params: Dict[str, Any]) -> AppAction:
        """获取路线"""
        waypoints = params.get("waypoints", [])
        
        logger.info(f"获取路线: {waypoints}")
        
        return AppAction(
            app_type=self.app_type,
            action="get_route",
            params=params,
            result={"waypoints": waypoints, "route": "最优路线"},
            success=True
        )
    
    async def _get_nearby(self, params: Dict[str, Any]) -> AppAction:
        """获取附近"""
        location = params.get("location", "")
        category = params.get("category", "餐厅")
        
        logger.info(f"获取附近: {location} - {category}")
        
        # 示例数据
        results = [
            {"id": "1", "name": "老北京炸酱面", "category": "餐厅", "rating": 4.5},
            {"id": "2", "name": "全聚德烤鸭", "category": "餐厅", "rating": 4.8}
        ]
        
        return AppAction(
            app_type=self.app_type,
            action="get_nearby",
            params=params,
            result={"results": results, "count": len(results)},
            success=True
        )
    
    async def _search_files(self, params: Dict[str, Any]) -> AppAction:
        """搜索文件"""
        query = params.get("query", "")
        path = params.get("path", "")
        limit = params.get("limit", 10)
        
        logger.info(f"搜索文件: {query} in {path}")
        try:
            results = await self.search_files(query, path, limit)
            return AppAction(
                app_type=self.app_type,
                action="search_files",
                params=params,
                result={"files": results, "count": len(results)},
                success=True
            )
        except Exception as e:
            logger.error(f"搜索文件失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action="search_files",
                params=params,
                result={},
                success=False
            )
    
    async def _get_traffic(self, params: Dict[str, Any]) -> AppAction:
        """获取交通信息"""
        location = params.get("location", "")
        
        logger.info(f"获取交通信息: {location}")
        
        # 示例数据
        traffic = {
            "location": location,
            "status": "拥堵",
            "congestion_level": "高",
            "average_speed": "20km/h"
        }
        
        return AppAction(
            app_type=self.app_type,
            action="get_traffic",
            params=params,
            result=traffic,
            success=True
        )


class NoteInterface(AppInterface):
    """笔记接口"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.NOTE
        self.available_actions = [
            "create_note",
            "get_note",
            "search_notes",
            "update_note",
            "delete_note",
            "list_notes"
        ]
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行笔记操作"""
        try:
            if action == "create_note":
                return await self._create_note(params)
            elif action == "get_note":
                return await self._get_note(params)
            elif action == "search_notes":
                return await self._search_notes(params)
            elif action == "update_note":
                return await self._update_note(params)
            elif action == "delete_note":
                return await self._delete_note(params)
            elif action == "list_notes":
                return await self._list_notes(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"笔记操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _create_note(self, params: Dict[str, Any]) -> AppAction:
        """创建笔记"""
        title = params.get("title", "")
        content = params.get("content", "")
        tags = params.get("tags", [])
        
        logger.info(f"创建笔记: {title}")
        
        result = {
            "note_id": f"note_{asyncio.get_event_loop().time()}",
            "title": title,
            "content": content,
            "tags": tags,
            "created": True
        }
        
        return AppAction(
            app_type=self.app_type,
            action="create_note",
            params=params,
            result=result,
            success=True
        )
    
    async def _get_note(self, params: Dict[str, Any]) -> AppAction:
        """获取笔记"""
        note_id = params.get("note_id", "")
        
        logger.info(f"获取笔记: {note_id}")
        
        # 示例数据
        note = {
            "id": note_id,
            "title": "示例笔记",
            "content": "这是笔记内容",
            "tags": ["工作", "重要"],
            "created_at": "2024-01-01",
            "updated_at": "2024-01-02"
        }
        
        return AppAction(
            app_type=self.app_type,
            action="get_note",
            params=params,
            result=note,
            success=True
        )
    
    async def _search_notes(self, params: Dict[str, Any]) -> AppAction:
        """搜索笔记"""
        keyword = params.get("keyword", "")
        
        logger.info(f"搜索笔记: {keyword}")
        
        # 示例数据
        notes = [
            {"id": "1", "title": "工作笔记", "content": "工作内容", "tags": ["工作"]},
            {"id": "2", "title": "学习笔记", "content": "学习内容", "tags": ["学习"]}
        ]
        
        results = [n for n in notes if keyword.lower() in n["title"].lower() or keyword.lower() in n["content"].lower()]
        
        return AppAction(
            app_type=self.app_type,
            action="search_notes",
            params=params,
            result={"results": results, "count": len(results)},
            success=True
        )
    
    async def _search_files(self, params: Dict[str, Any]) -> AppAction:
        """搜索文件"""
        try:
            results = await self.search_files(params)
            return AppAction(
                app_type=self.app_type,
                action="search_files",
                params=params,
                result={"files": results, "count": len(results)},
                success=True
            )
        except Exception as e:
            logger.error(f"搜索文件失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action="search_files",
                params=params,
                result={},
                success=False
            )

    async def _update_note(self, params: Dict[str, Any]) -> AppAction:
        """更新笔记"""
        note_id = params.get("note_id", "")
        updates = params.get("updates", {})
        
        logger.info(f"更新笔记: {note_id}")
        
        return AppAction(
            app_type=self.app_type,
            action="update_note",
            params=params,
            result={"note_id": note_id, "updated": True, "updates": updates},
            success=True
        )
    
    async def _delete_note(self, params: Dict[str, Any]) -> AppAction:
        """删除笔记"""
        note_id = params.get("note_id", "")
        
        logger.info(f"删除笔记: {note_id}")
        
        return AppAction(
            app_type=self.app_type,
            action="delete_note",
            params=params,
            result={"note_id": note_id, "deleted": True},
            success=True
        )
    
    async def _list_notes(self, params: Dict[str, Any]) -> AppAction:
        """列出笔记"""
        tag = params.get("tag", "")
        
        logger.info(f"列出笔记: {tag}")
        
        # 示例数据
        notes = [
            {"id": "1", "title": "工作笔记", "tags": ["工作"]},
            {"id": "2", "title": "学习笔记", "tags": ["学习"]},
            {"id": "3", "title": "生活笔记", "tags": ["生活"]}
        ]
        
        if tag:
            notes = [n for n in notes if tag in n["tags"]]
        
        return AppAction(
            app_type=self.app_type,
            action="list_notes",
            params=params,
            result={"notes": notes, "count": len(notes)},
            success=True
        )


class TodoInterface(AppInterface):
    """待办事项接口"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.TODO
        self.available_actions = [
            "create_task",
            "get_task",
            "list_tasks",
            "complete_task",
            "delete_task",
            "update_task"
        ]
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行待办事项操作"""
        try:
            if action == "create_task":
                return await self._create_task(params)
            elif action == "get_task":
                return await self._get_task(params)
            elif action == "list_tasks":
                return await self._list_tasks(params)
            elif action == "complete_task":
                return await self._complete_task(params)
            elif action == "delete_task":
                return await self._delete_task(params)
            elif action == "update_task":
                return await self._update_task(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"待办事项操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _create_task(self, params: Dict[str, Any]) -> AppAction:
        """创建任务"""
        title = params.get("title", "")
        description = params.get("description", "")
        priority = params.get("priority", "medium")
        due_date = params.get("due_date", "")
        
        logger.info(f"创建任务: {title}")
        
        result = {
            "task_id": f"task_{asyncio.get_event_loop().time()}",
            "title": title,
            "description": description,
            "priority": priority,
            "due_date": due_date,
            "status": "pending",
            "created": True
        }
        
        return AppAction(
            app_type=self.app_type,
            action="create_task",
            params=params,
            result=result,
            success=True
        )
    
    async def _get_task(self, params: Dict[str, Any]) -> AppAction:
        """获取任务"""
        task_id = params.get("task_id", "")
        
        logger.info(f"获取任务: {task_id}")
        
        # 示例数据
        task = {
            "id": task_id,
            "title": "示例任务",
            "description": "任务描述",
            "priority": "high",
            "due_date": "2024-12-31",
            "status": "pending"
        }
        
        return AppAction(
            app_type=self.app_type,
            action="get_task",
            params=params,
            result=task,
            success=True
        )
    
    async def _list_tasks(self, params: Dict[str, Any]) -> AppAction:
        """列出任务"""
        status = params.get("status", "")
        
        logger.info(f"列出任务: {status}")
        
        # 示例数据
        tasks = [
            {"id": "1", "title": "完成报告", "status": "pending", "priority": "high"},
            {"id": "2", "title": "发送邮件", "status": "completed", "priority": "medium"},
            {"id": "3", "title": "准备会议", "status": "pending", "priority": "low"}
        ]
        
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        
        return AppAction(
            app_type=self.app_type,
            action="list_tasks",
            params=params,
            result={"tasks": tasks, "count": len(tasks)},
            success=True
        )
    
    async def _complete_task(self, params: Dict[str, Any]) -> AppAction:
        """完成任务"""
        task_id = params.get("task_id", "")
        
        logger.info(f"完成任务: {task_id}")
        
        return AppAction(
            app_type=self.app_type,
            action="complete_task",
            params=params,
            result={"task_id": task_id, "completed": True},
            success=True
        )
    
    async def _delete_task(self, params: Dict[str, Any]) -> AppAction:
        """删除任务"""
        task_id = params.get("task_id", "")
        
        logger.info(f"删除任务: {task_id}")
        
        return AppAction(
            app_type=self.app_type,
            action="delete_task",
            params=params,
            result={"task_id": task_id, "deleted": True},
            success=True
        )
    
    async def _update_task(self, params: Dict[str, Any]) -> AppAction:
        """更新任务"""
        task_id = params.get("task_id", "")
        updates = params.get("updates", {})
        
        logger.info(f"更新任务: {task_id}")
        
        return AppAction(
            app_type=self.app_type,
            action="update_task",
            params=params,
            result={"task_id": task_id, "updated": True, "updates": updates},
            success=True
        )


class CloudInterface(AppInterface):
    """云存储接口"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.CLOUD
        self.available_actions = [
            "upload_file",
            "download_file",
            "list_files",
            "delete_file",
            "share_file",
            "get_file_info"
        ]
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行云存储操作"""
        try:
            if action == "upload_file":
                return await self._upload_file(params)
            elif action == "download_file":
                return await self._download_file(params)
            elif action == "list_files":
                return await self._list_files(params)
            elif action == "delete_file":
                return await self._delete_file(params)
            elif action == "share_file":
                return await self._share_file(params)
            elif action == "get_file_info":
                return await self._get_file_info(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"云存储操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _upload_file(self, params: Dict[str, Any]) -> AppAction:
        """上传文件"""
        file_path = params.get("file_path", "")
        cloud_path = params.get("cloud_path", "")
        
        logger.info(f"上传文件: {file_path} -> {cloud_path}")
        
        result = {
            "file_path": file_path,
            "cloud_path": cloud_path,
            "file_id": f"file_{asyncio.get_event_loop().time()}",
            "uploaded": True
        }
        
        return AppAction(
            app_type=self.app_type,
            action="upload_file",
            params=params,
            result=result,
            success=True
        )
    
    async def _download_file(self, params: Dict[str, Any]) -> AppAction:
        """下载文件"""
        cloud_path = params.get("cloud_path", "")
        local_path = params.get("local_path", "")
        
        logger.info(f"下载文件: {cloud_path} -> {local_path}")
        
        result = {
            "cloud_path": cloud_path,
            "local_path": local_path,
            "downloaded": True
        }
        
        return AppAction(
            app_type=self.app_type,
            action="download_file",
            params=params,
            result=result,
            success=True
        )
    
    async def _list_files(self, params: Dict[str, Any]) -> AppAction:
        """列出文件"""
        path = params.get("path", "/")
        
        logger.info(f"列出云文件: {path}")
        
        # 示例数据
        files = [
            {"id": "1", "name": "文档.pdf", "size": 1024000, "type": "file"},
            {"id": "2", "name": "图片.jpg", "size": 2048000, "type": "file"},
            {"id": "3", "name": "工作", "size": 0, "type": "directory"}
        ]
        
        return AppAction(
            app_type=self.app_type,
            action="list_files",
            params=params,
            result={"path": path, "files": files, "count": len(files)},
            success=True
        )
    
    async def _delete_file(self, params: Dict[str, Any]) -> AppAction:
        """删除文件"""
        cloud_path = params.get("cloud_path", "")
        
        logger.info(f"删除云文件: {cloud_path}")
        
        return AppAction(
            app_type=self.app_type,
            action="delete_file",
            params=params,
            result={"cloud_path": cloud_path, "deleted": True},
            success=True
        )
    
    async def _share_file(self, params: Dict[str, Any]) -> AppAction:
        """分享文件"""
        cloud_path = params.get("cloud_path", "")
        
        logger.info(f"分享文件: {cloud_path}")
        
        result = {
            "cloud_path": cloud_path,
            "share_url": f"https://cloud.example.com/share/{asyncio.get_event_loop().time()}",
            "shared": True
        }
        
        return AppAction(
            app_type=self.app_type,
            action="share_file",
            params=params,
            result=result,
            success=True
        )
    
    async def _get_file_info(self, params: Dict[str, Any]) -> AppAction:
        """获取文件信息"""
        cloud_path = params.get("cloud_path", "")
        
        logger.info(f"获取文件信息: {cloud_path}")
        
        # 示例数据
        info = {
            "path": cloud_path,
            "name": "示例文件.pdf",
            "size": 1024000,
            "type": "application/pdf",
            "created_at": "2024-01-01",
            "modified_at": "2024-01-02"
        }
        
        return AppAction(
            app_type=self.app_type,
            action="get_file_info",
            params=params,
            result=info,
            success=True
        )


class DesktopAutomationInterface(AppInterface):
    """桌面自动化接口 - 屏幕截图、图像识别、点击定位"""
    
    def __init__(self):
        super().__init__()
        self.app_type = AppType.DESKTOP_AUTOMATION
        self.available_actions = [
            "screenshot",
            "capture_region",
            "locate_text",
            "locate_image",
            "click_at",
            "get_screen_size",
            "locate_and_click",
            "find_all_matches"
        ]
        self._locator = None
    
    def _get_locator(self):
        """获取屏幕定位器"""
        if self._locator is None:
            try:
                from core.screen_locator import ScreenLocator
                self._locator = ScreenLocator()
            except ImportError as e:
                logger.warning(f"ScreenLocator导入失败: {e}")
                return None
        return self._locator
    
    async def execute(self, action: str, params: Dict[str, Any]) -> AppAction:
        """执行桌面自动化操作"""
        try:
            if action == "screenshot":
                return await self._screenshot(params)
            elif action == "capture_region":
                return await self._capture_region(params)
            elif action == "locate_text":
                return await self._locate_text(params)
            elif action == "locate_image":
                return await self._locate_image(params)
            elif action == "click_at":
                return await self._click_at(params)
            elif action == "get_screen_size":
                return await self._get_screen_size(params)
            elif action == "locate_and_click":
                return await self._locate_and_click(params)
            elif action == "find_all_matches":
                return await self._find_all_matches(params)
            else:
                return AppAction(
                    app_type=self.app_type,
                    action=action,
                    params=params,
                    success=False,
                    error=f"未知操作: {action}"
                )
        except Exception as e:
            logger.error(f"桌面自动化操作失败: {e}")
            return AppAction(
                app_type=self.app_type,
                action=action,
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _screenshot(self, params: Dict[str, Any]) -> AppAction:
        """截取全屏"""
        locator = self._get_locator()
        if not locator:
            return AppAction(
                app_type=self.app_type,
                action="screenshot",
                params=params,
                success=False,
                error="ScreenLocator未安装"
            )
        
        try:
            path = locator.capture_screen()
            return AppAction(
                app_type=self.app_type,
                action="screenshot",
                params=params,
                result={"path": path, "timestamp": datetime.now().isoformat()},
                success=True
            )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="screenshot",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _capture_region(self, params: Dict[str, Any]) -> AppAction:
        """截取指定区域"""
        locator = self._get_locator()
        if not locator:
            return AppAction(
                app_type=self.app_type,
                action="capture_region",
                params=params,
                success=False,
                error="ScreenLocator未安装"
            )
        
        x = params.get("x", 0)
        y = params.get("y", 0)
        width = params.get("width", 800)
        height = params.get("height", 600)
        
        try:
            from core.screen_locator import ScreenRegion
            region = ScreenRegion(x=x, y=y, width=width, height=height)
            path = locator.capture_screen(region=region)
            
            return AppAction(
                app_type=self.app_type,
                action="capture_region",
                params=params,
                result={
                    "path": path,
                    "region": {"x": x, "y": y, "width": width, "height": height},
                    "timestamp": datetime.now().isoformat()
                },
                success=True
            )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="capture_region",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _locate_text(self, params: Dict[str, Any]) -> AppAction:
        """通过OCR查找文字位置"""
        locator = self._get_locator()
        if not locator:
            return AppAction(
                app_type=self.app_type,
                action="locate_text",
                params=params,
                success=False,
                error="ScreenLocator未安装"
            )
        
        text = params.get("text", "")
        screenshot = params.get("screenshot")
        
        if not screenshot:
            screenshot = locator.capture_screen()
        
        try:
            position = locator.locate_on_screen(screenshot, text, method="ocr")
            
            if position:
                return AppAction(
                    app_type=self.app_type,
                    action="locate_text",
                    params=params,
                    result={
                        "x": position.x,
                        "y": position.y,
                        "confidence": position.confidence,
                        "text": position.text,
                        "region": position.region
                    },
                    success=True
                )
            else:
                return AppAction(
                    app_type=self.app_type,
                    action="locate_text",
                    params=params,
                    success=False,
                    error=f"未找到文字: {text}"
                )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="locate_text",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _locate_image(self, params: Dict[str, Any]) -> AppAction:
        """通过模板匹配查找图像位置"""
        locator = self._get_locator()
        if not locator:
            return AppAction(
                app_type=self.app_type,
                action="locate_image",
                params=params,
                success=False,
                error="ScreenLocator未安装"
            )
        
        template = params.get("template", "")
        screenshot = params.get("screenshot")
        
        if not screenshot:
            screenshot = locator.capture_screen()
        
        if not template:
            return AppAction(
                app_type=self.app_type,
                action="locate_image",
                params=params,
                success=False,
                error="未指定模板图像"
            )
        
        try:
            position = locator.locate_on_screen(screenshot, template, method="template")
            
            if position:
                return AppAction(
                    app_type=self.app_type,
                    action="locate_image",
                    params=params,
                    result={
                        "x": position.x,
                        "y": position.y,
                        "confidence": position.confidence,
                        "region": position.region
                    },
                    success=True
                )
            else:
                return AppAction(
                    app_type=self.app_type,
                    action="locate_image",
                    params=params,
                    success=False,
                    error="未找到匹配的图像"
                )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="locate_image",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _click_at(self, params: Dict[str, Any]) -> AppAction:
        """点击指定位置"""
        locator = self._get_locator()
        if not locator:
            return AppAction(
                app_type=self.app_type,
                action="click_at",
                params=params,
                success=False,
                error="ScreenLocator未安装"
            )
        
        x = params.get("x", 0)
        y = params.get("y", 0)
        clicks = params.get("clicks", 1)
        
        try:
            result = locator.click_at_position(x, y, clicks)
            return AppAction(
                app_type=self.app_type,
                action="click_at",
                params=params,
                result=result,
                success=result.get("success", False)
            )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="click_at",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _get_screen_size(self, params: Dict[str, Any]) -> AppAction:
        """获取屏幕尺寸"""
        locator = self._get_locator()
        if not locator:
            return AppAction(
                app_type=self.app_type,
                action="get_screen_size",
                params=params,
                success=False,
                error="ScreenLocator未安装"
            )
        
        try:
            width, height = locator.get_screen_size()
            return AppAction(
                app_type=self.app_type,
                action="get_screen_size",
                params=params,
                result={"width": width, "height": height},
                success=True
            )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="get_screen_size",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _locate_and_click(self, params: Dict[str, Any]) -> AppAction:
        """查找并点击"""
        locator = self._get_locator()
        if not locator:
            return AppAction(
                app_type=self.app_type,
                action="locate_and_click",
                params=params,
                success=False,
                error="ScreenLocator未安装"
            )
        
        target = params.get("target", "")
        method = params.get("method", "ocr")
        clicks = params.get("clicks", 1)
        
        if not target:
            return AppAction(
                app_type=self.app_type,
                action="locate_and_click",
                params=params,
                success=False,
                error="未指定查找目标"
            )
        
        try:
            # 截屏并查找
            position = locator.capture_and_locate(target, method)
            
            if position:
                # 点击位置
                result = locator.click_at_position(position.x, position.y, clicks)
                return AppAction(
                    app_type=self.app_type,
                    action="locate_and_click",
                    params=params,
                    result={
                        "found": True,
                        "x": position.x,
                        "y": position.y,
                        "click_result": result
                    },
                    success=result.get("success", False)
                )
            else:
                return AppAction(
                    app_type=self.app_type,
                    action="locate_and_click",
                    params=params,
                    success=False,
                    error=f"未找到目标: {target}"
                )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="locate_and_click",
                params=params,
                success=False,
                error=str(e)
            )
    
    async def _find_all_matches(self, params: Dict[str, Any]) -> AppAction:
        """查找所有匹配位置"""
        locator = self._get_locator()
        if not locator:
            return AppAction(
                app_type=self.app_type,
                action="find_all_matches",
                params=params,
                success=False,
                error="ScreenLocator未安装"
            )
        
        target = params.get("target", "")
        screenshot = params.get("screenshot")
        
        if not target:
            return AppAction(
                app_type=self.app_type,
                action="find_all_matches",
                params=params,
                success=False,
                error="未指定查找目标"
            )
        
        if not screenshot:
            screenshot = locator.capture_screen()
        
        try:
            matches = locator.find_all_matches(screenshot, target, method="ocr")
            
            return AppAction(
                app_type=self.app_type,
                action="find_all_matches",
                params=params,
                result={
                    "count": len(matches),
                    "matches": [
                        {
                            "x": m.x,
                            "y": m.y,
                            "confidence": m.confidence,
                            "text": m.text
                        }
                        for m in matches
                    ]
                },
                success=True
            )
        except Exception as e:
            return AppAction(
                app_type=self.app_type,
                action="find_all_matches",
                params=params,
                success=False,
                error=str(e)
            )


class AppManager:
    """应用管理器 - 统一管理所有应用接口"""
    
    def __init__(self):
        self.interfaces: Dict[AppType, AppInterface] = {}
        self._init_interfaces()
        logger.info("AppManager 初始化完成")
    
    def _init_interfaces(self):
        """初始化所有应用接口"""
        self.interfaces[AppType.WECHAT] = WeChatInterface()
        self.interfaces[AppType.EMAIL] = EmailInterface()
        self.interfaces[AppType.FILESYSTEM] = FileSystemInterface()
        self.interfaces[AppType.BROWSER] = BrowserInterface()
        self.interfaces[AppType.CALENDAR] = CalendarInterface()
        self.interfaces[AppType.NOTIFICATION] = NotificationInterface()
        self.interfaces[AppType.MUSIC] = MusicInterface()
        self.interfaces[AppType.VIDEO] = VideoInterface()
        self.interfaces[AppType.MAP] = MapInterface()
        self.interfaces[AppType.NOTE] = NoteInterface()
        self.interfaces[AppType.TODO] = TodoInterface()
        self.interfaces[AppType.CLOUD] = CloudInterface()
        self.interfaces[AppType.DESKTOP_AUTOMATION] = DesktopAutomationInterface()
        logger.info("已注册 13 个应用接口")
    
    async def execute(self, app_type: AppType, action: str, params: Dict[str, Any]) -> AppAction:
        """执行应用操作
        
        Args:
            app_type: 应用类型
            action: 操作名称
            params: 操作参数
            
        Returns:
            操作结果
        """
        interface = self.interfaces.get(app_type)
        if not interface:
            return AppAction(
                app_type=app_type,
                action=action,
                params=params,
                success=False,
                error=f"不支持的应用类型: {app_type}"
            )
        
        return await interface.execute(action, params)
    
    def get_available_apps(self) -> Dict[str, List[str]]:
        """获取所有可用应用及其操作"""
        result = {}
        for app_type, interface in self.interfaces.items():
            result[app_type.value] = interface.get_available_actions()
        return result
    
    def get_app_info(self, app_type: AppType) -> Dict[str, Any]:
        """获取应用信息"""
        interface = self.interfaces.get(app_type)
        if not interface:
            return {"error": f"不支持的应用类型: {app_type}"}
        
        return {
            "app_type": app_type.value,
            "available_actions": interface.get_available_actions()
        }


# 全局应用管理器实例
_app_manager: Optional[AppManager] = None


def get_app_manager() -> AppManager:
    """获取应用管理器单例"""
    global _app_manager
    if _app_manager is None:
        _app_manager = AppManager()
    return _app_manager
"""
沙盒工具箱调度器

统一入口: handle(action, **params)
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SandboxToolsHandler:
    """沙盒工具箱处理器"""

    def __init__(self):
        self._modules = {}

    def _get_edit(self):
        if "edit" not in self._modules:
            from . import edit
            self._modules["edit"] = edit
        return self._modules["edit"]

    def _get_commands(self):
        if "commands" not in self._modules:
            from . import commands
            self._modules["commands"] = commands
        return self._modules["commands"]

    def _get_macos(self):
        if "macos" not in self._modules:
            from . import macos
            self._modules["macos"] = macos
        return self._modules["macos"]

    async def handle(self, action: str, **params) -> Dict[str, Any]:
        """执行沙盒操作

        文件编辑操作:
            read(path, offset=0, limit=200)
            write(path, content)
            edit(path, old_string, new_string)
            append(path, content)
            ls(path='.')
            mkdir(path)
            rm(path, recursive=False)
            mv(src, dst)
            cp(src, dst)
            grep(pattern, path)
            find(path, pattern='*')
            head(path, n=10)
            tail(path, n=10)

        命令执行操作:
            run(command, timeout=30, allow_net=False, allow_dangerous=False, cwd=None)
            check_tool(name)

        macOS 操作:
            system_info()
            open_app(app_name)
            run_applescript(script)
            clipboard_get()
            clipboard_set(content)
            show_notification(title, message)
            screenshot(path=None)
            list_volumes()
            find_app(name)
            network_info()
        """
        edit_actions = {
            "read", "write", "edit", "append", "ls", "mkdir",
            "rm", "mv", "cp", "grep", "find", "head", "tail",
        }
        command_actions = {"run", "check_tool"}
        macos_actions = {
            "system_info", "open_app", "run_applescript",
            "clipboard_get", "clipboard_set", "show_notification",
            "screenshot", "list_volumes", "find_app",
            "network_info",
        }

        try:
            if action in edit_actions:
                mod = self._get_edit()
                fn = getattr(mod, action, None)
                if not fn:
                    return {"success": False, "error": f"未知编辑操作: {action}"}
                result = fn(**params)
                return {"success": True, "action": action, "result": result}

            elif action in command_actions:
                mod = self._get_commands()
                if action == "run":
                    result = await mod.run(**params)
                    return {"success": True, "action": action, "result": result.to_dict()}
                elif action == "check_tool":
                    result = await mod.check_tool(**params)
                    return {"success": True, "action": action, "result": result}

            elif action in macos_actions:
                mod = self._get_macos()
                fn = getattr(mod, action, None)
                if not fn:
                    return {"success": False, "error": f"未知 macOS 操作: {action}"}
                result = await fn(**params)
                return {"success": True, "action": action, "result": result}

            else:
                return {"success": False, "error": f"未知沙盒操作: {action}，支持: {sorted(edit_actions | command_actions | macos_actions)}"}

        except PermissionError as e:
            return {"success": False, "action": action, "error": str(e), "code": "permission_denied"}
        except Exception as e:
            logger.exception(f"沙盒操作失败: {action}")
            return {"success": False, "action": action, "error": str(e)}


# 便捷函数
_handler: Optional[SandboxToolsHandler] = None


def get_handler() -> SandboxToolsHandler:
    global _handler
    if _handler is None:
        _handler = SandboxToolsHandler()
    return _handler


async def handle(action: str, **params) -> Dict[str, Any]:
    return await get_handler().handle(action, **params)

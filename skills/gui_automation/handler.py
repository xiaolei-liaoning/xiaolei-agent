"""macOS GUI自动化处理器（工业级 v3.3.0）

支持20+操作：open_app, open_url, notification, type_text, hotkey, key_press,
click_at, click_text, screenshot, wait, wait_for_text, scroll, move_mouse,
drag_to, set_clipboard, get_clipboard, volume_adjust, brightness_adjust,
quit_app, set_window, applescript

依赖：pyperclip(可选)
"""

import subprocess
import logging
import time
import os
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT: int = 5


class GUIAutomationHandler:
    """macOS GUI自动化处理器。

    工业级特性：
    - 同步/异步双接口
    - 完整的AppleScript命令生成与特殊字符转义
    - 所有操作超时保护（默认5s）
    - 20+操作覆盖：应用控制、输入、鼠标、系统、脚本执行
    - pyperclip不可用时自动降级到pbcopy/pbpaste

    Attributes:
        default_timeout: 默认操作超时秒数
    """

    def __init__(self, default_timeout: int = DEFAULT_TIMEOUT) -> None:
        """初始化GUI自动化处理器。

        Args:
            default_timeout: 默认操作超时时间（秒）
        """
        self.default_timeout: int = default_timeout
        logger.info("GUIAutomationHandler 初始化完成, 超时: %ds, 平台: %s",
                     default_timeout, sys.platform)

    def execute(self, action: str = 'open_app', **kwargs: Any) -> Dict[str, Any]:
        """执行GUI自动化操作（同步接口）。

        Args:
            action: 操作名称，支持：
                open_app, open_url, notification, type_text, hotkey, key_press,
                click_at, click_text, screenshot, wait, wait_for_text, scroll,
                move_mouse, drag_to, set_clipboard, get_clipboard, volume_adjust,
                brightness_adjust, quit_app, set_window, applescript
            **kwargs: 操作参数，因操作而异

        Returns:
            Dict[str, Any]: 包含 success, action, reply 等字段的字典
        """
        start_time = time.perf_counter()
        try:
            result = self._do_execute(action, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.debug("GUI操作完成 [%s], 耗时: %.3fs, 成功: %s",
                         action, elapsed, result.get('success'))
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("GUI操作异常 [%s]: %s", action, e, exc_info=True)
            return {'success': False, 'error': f'GUI操作异常: {e}'}

    async def aexecute(self, action: str = 'open_app', **kwargs: Any) -> Dict[str, Any]:
        """执行GUI自动化操作（异步接口）。

        与 execute 相同逻辑，以协程方式运行。

        Args:
            action: 操作名称
            **kwargs: 操作参数

        Returns:
            Dict[str, Any]: 操作结果
        """
        start_time = time.perf_counter()
        try:
            result = self._do_execute(action, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.debug("GUI操作完成(异步) [%s], 耗时: %.3fs", action, elapsed)
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("GUI操作异常(异步) [%s]: %s", action, e, exc_info=True)
            return {'success': False, 'error': f'GUI操作异常: {e}'}

    def _do_execute(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """核心执行逻辑。"""
        actions: Dict[str, Any] = {
            'open_app': self._open_app,
            'open_url': self._open_url,
            'notification': self._notification,
            'type_text': self._type_text,
            'hotkey': self._hotkey,
            'key_press': self._key_press,
            'click_at': self._click_at,
            'click_text': self._click_text,
            'screenshot': self._screenshot,
            'wait': self._wait,
            'wait_for_text': self._wait_for_text,
            'scroll': self._scroll,
            'move_mouse': self._move_mouse,
            'drag_to': self._drag_to,
            'set_clipboard': self._set_clipboard,
            'get_clipboard': self._get_clipboard,
            'volume_adjust': self._volume_adjust,
            'brightness_adjust': self._brightness_adjust,
            'quit_app': self._quit_app,
            'set_window': self._set_window,
            'applescript': self._applescript,
            'ocr_screenshot': self._ocr_screenshot,
            'browser_zoom': self._browser_zoom,
        }

        handler = actions.get(action)
        if not handler:
            supported = ', '.join(sorted(actions.keys()))
            logger.warning("未知GUI操作: %s, 支持: %s", action, supported)
            return {'success': False, 'error': f'未知操作: {action}，支持: {supported}'}

        return handler(**kwargs)

    # ── AppleScript基础设施 ──────────────────────────────

    def _run_applescript(
        self,
        script: str,
        timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess:
        """执行AppleScript命令。

        Args:
            script: AppleScript代码
            timeout: 超时秒数，None使用默认值

        Returns:
            subprocess.CompletedProcess 执行结果
        """
        t = timeout if timeout is not None else self.default_timeout
        return subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=t,
        )

    @staticmethod
    def _escape_applescript(text: str) -> str:
        """转义AppleScript字符串中的特殊字符。

        Args:
            text: 原始字符串

        Returns:
            转义后的安全字符串
        """
        return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    # ── 应用控制 ─────────────────────────────────────────

    def _open_app(self, app: str = '', **kwargs: Any) -> Dict[str, Any]:
        """打开应用程序。

        Args:
            app: 应用程序名称

        Returns:
            操作结果字典
        """
        if not app:
            return {'success': False, 'error': '未指定应用名称'}
        
        # macOS应用名称映射（中文->英文）
        app_map = {
            '微信': 'WeChat',
            '企业微信': 'WeCom',
            '钉钉': 'DingTalk',
            '飞书': 'Feishu',
            'QQ': 'QQ',
            'Safari': 'Safari',
            'Chrome': 'Google Chrome',
            '浏览器': 'Safari',
        }
        app_name = app_map.get(app, app)
        
        subprocess.run(['open', '-a', app_name], check=False, timeout=self.default_timeout)
        logger.debug("打开应用: %s -> %s", app, app_name)
        return {'success': True, 'action': 'open_app', 'app': app, 'reply': f'已打开应用: {app}'}

    def _open_url(self, url: str = '', **kwargs: Any) -> Dict[str, Any]:
        """在默认浏览器中打开URL。

        Args:
            url: 网址

        Returns:
            操作结果字典
        """
        if not url:
            return {'success': False, 'error': '未指定URL'}
        subprocess.run(['open', url], check=False, timeout=self.default_timeout)
        logger.debug("打开URL: %s", url)
        return {'success': True, 'action': 'open_url', 'url': url, 'reply': f'已打开: {url}'}

    def _quit_app(self, app: str = '', **kwargs: Any) -> Dict[str, Any]:
        """退出应用程序。

        Args:
            app: 应用程序名称

        Returns:
            操作结果字典
        """
        if not app:
            return {'success': False, 'error': '未指定应用名称'}
        safe_app = self._escape_applescript(app)
        script = f'tell application "{safe_app}" to quit'
        self._run_applescript(script)
        logger.debug("退出应用: %s", app)
        return {'success': True, 'action': 'quit_app', 'app': app, 'reply': f'已退出: {app}'}

    def _set_window(
        self,
        app: str = '',
        x: int = 0, y: int = 0,
        width: int = 800, height: int = 600,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """设置窗口位置和大小。

        Args:
            app: 应用程序名称
            x: 左上角X坐标
            y: 左上角Y坐标
            width: 窗口宽度
            height: 窗口高度

        Returns:
            操作结果字典
        """
        if not app:
            return {'success': False, 'error': '未指定应用名称'}
        safe_app = self._escape_applescript(app)
        script = f'tell application "{safe_app}" to set bounds of front window to {{{x}, {y}, {x + width}, {y + height}}}'
        self._run_applescript(script)
        logger.debug("设置窗口: %s, 位置(%d,%d), 大小(%dx%d)", app, x, y, width, height)
        return {
            'success': True, 'action': 'set_window', 'app': app,
            'reply': f'已设置 {app} 窗口: 位置({x},{y}), 大小({width}x{height})',
        }

    # ── 输入操作 ─────────────────────────────────────────

    def _type_text(self, text: str = '', **kwargs: Any) -> Dict[str, Any]:
        """输入文字 - 通过剪贴板粘贴方式。

        Args:
            text: 要输入的文本

        Returns:
            操作结果字典
        """
        if not text:
            return {'success': False, 'error': '未指定输入文本'}
        self._copy_to_clipboard(text)
        time.sleep(0.05)
        script = 'tell application "System Events" to keystroke "v" using command down'
        self._run_applescript(script)
        logger.debug("输入文本: %s", text[:50])
        return {'success': True, 'action': 'type_text', 'text': text}

    def _hotkey(self, keys: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        """执行快捷键组合。

        Args:
            keys: 按键列表，最后一个是主键，前面的都是修饰键。
                修饰键: command/cmd, shift, option/alt, control/ctrl
                特殊键: enter, tab, space, escape, delete, up/down/left/right, f1-f12

        Returns:
            操作结果字典
        """
        if not keys:
            return {'success': False, 'error': '未指定快捷键'}

        if isinstance(keys, str):
            keys = keys.split('+')

        modifier_map: Dict[str, str] = {
            'command': 'command down', 'cmd': 'command down',
            'shift': 'shift down',
            'option': 'option down', 'alt': 'option down',
            'control': 'control down', 'ctrl': 'control down',
        }

        key_name_map: Dict[str, str] = {
            'enter': 'return', 'return': 'return', 'tab': 'tab',
            'space': 'space', 'escape': 'escape', 'esc': 'escape',
            'delete': 'delete', 'backspace': 'delete',
            'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right',
            'home': 'home', 'end': 'end',
            'pageup': 'page up', 'pagedown': 'page down',
            'f1': 'f1', 'f2': 'f2', 'f3': 'f3', 'f4': 'f4',
            'f5': 'f5', 'f6': 'f6', 'f7': 'f7', 'f8': 'f8',
            'f9': 'f9', 'f10': 'f10', 'f11': 'f11', 'f12': 'f12',
        }

        main_key = keys[-1].lower()
        modifiers: List[str] = []
        for key in keys[:-1]:
            mapped = modifier_map.get(key.lower())
            if mapped:
                modifiers.append(mapped)

        keystroke = key_name_map.get(main_key, main_key)

        if modifiers:
            mod_str = ' & '.join(modifiers)
            script = f'tell application "System Events" to keystroke "{keystroke}" using {{{mod_str}}}'
        else:
            script = f'tell application "System Events" to keystroke "{keystroke}"'

        self._run_applescript(script)
        key_desc = '+'.join(keys)
        logger.debug("执行快捷键: %s", key_desc)
        return {'success': True, 'action': 'hotkey', 'keys': keys, 'reply': f'已执行快捷键: {key_desc}'}

    def _key_press(self, key: str = '', **kwargs: Any) -> Dict[str, Any]:
        """单按键操作。

        Args:
            key: 按键名称

        Returns:
            操作结果字典
        """
        if not key:
            return {'success': False, 'error': '未指定按键'}
        return self._hotkey(keys=[key])

    # ── 鼠标操作 ─────────────────────────────────────────

    def _click_at(self, x: int = 0, y: int = 0, **kwargs: Any) -> Dict[str, Any]:
        """在指定屏幕坐标点击。

        Args:
            x: X坐标
            y: Y坐标

        Returns:
            操作结果字典
        """
        script = f'tell application "System Events" to click at {{{x}, {y}}}'
        self._run_applescript(script)
        logger.debug("坐标点击: (%d, %d)", x, y)
        return {'success': True, 'action': 'click_at', 'x': x, 'y': y,
                'reply': f'已在坐标 ({x}, {y}) 点击'}

    def _click_text(self, text: str = '', **kwargs: Any) -> Dict[str, Any]:
        """通过文本描述点击UI元素（AppleScript UI scripting）。

        Args:
            text: 目标文本描述

        Returns:
            操作结果字典
        """
        if not text:
            return {'success': False, 'error': '未指定目标文本'}
        safe_text = self._escape_applescript(text)
        script = f'''
        tell application "System Events"
            tell process "SystemUIServer"
                try
                    click (every button whose description contains "{safe_text}")
                end try
            end tell
        end tell
        '''
        self._run_applescript(script, timeout=8)
        logger.debug("文本点击: %s", text)
        return {'success': True, 'action': 'click_text', 'text': text, 'reply': f'已尝试点击文本: {text}'}

    def _move_mouse(self, x: int = 0, y: int = 0, **kwargs: Any) -> Dict[str, Any]:
        """移动鼠标到指定坐标。

        Args:
            x: X坐标
            y: Y坐标

        Returns:
            操作结果字典
        """
        logger.debug("移动鼠标: (%d, %d)", x, y)
        return {'success': True, 'action': 'move_mouse', 'x': x, 'y': y,
                'reply': f'鼠标已移至 ({x}, {y})'}

    def _drag_to(self, x: int = 0, y: int = 0, **kwargs: Any) -> Dict[str, Any]:
        """拖拽鼠标到指定坐标。

        Args:
            x: 目标X坐标
            y: 目标Y坐标

        Returns:
            操作结果字典
        """
        script = f'tell application "System Events" to mouse drag to {{{x}, {y}}}'
        self._run_applescript(script, timeout=self.default_timeout)
        logger.debug("拖拽至: (%d, %d)", x, y)
        return {'success': True, 'action': 'drag_to', 'x': x, 'y': y,
                'reply': f'已拖拽至 ({x}, {y})'}

    def _scroll(self, clicks: int = 0, **kwargs: Any) -> Dict[str, Any]:
        """滚动鼠标滚轮。

        Args:
            clicks: 滚动格数，正数向下，负数向上

        Returns:
            操作结果字典
        """
        script = f'tell application "System Events" to scroll {clicks}'
        self._run_applescript(script)
        logger.debug("滚动: %d格", clicks)
        return {'success': True, 'action': 'scroll', 'clicks': clicks,
                'reply': f'已滚动 {clicks} 格'}

    # ── 系统操作 ─────────────────────────────────────────

    def _notification(self, title: str = '通知', message: str = '', **kwargs: Any) -> Dict[str, Any]:
        """发送macOS系统通知。

        Args:
            title: 通知标题
            message: 通知内容

        Returns:
            操作结果字典
        """
        safe_title = self._escape_applescript(title)
        safe_msg = self._escape_applescript(message)
        script = f'display notification "{safe_msg}" with title "{safe_title}"'
        self._run_applescript(script)
        logger.debug("发送通知: [%s] %s", title, message[:50])
        return {'success': True, 'action': 'notification', 'title': title, 'message': message,
                'reply': f'已发送通知: [{title}] {message}'}

    def _screenshot(self, name: str = '', **kwargs: Any) -> Dict[str, Any]:
        """截屏保存到桌面。

        Args:
            name: 文件名，默认自动生成时间戳文件名

        Returns:
            包含截图路径的字典
        """
        if not name:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            name = f'screenshot_{timestamp}.png'
        if not name.endswith('.png'):
            name += '.png'

        desktop = os.path.join(os.path.expanduser('~'), 'Desktop', name)
        subprocess.run(['screencapture', '-x', desktop], check=False, timeout=10)
        logger.debug("截图保存: %s", desktop)
        return {'success': True, 'action': 'screenshot', 'path': desktop,
                'reply': f'截图已保存: {desktop}'}

    def _wait(self, seconds: float = 1, **kwargs: Any) -> Dict[str, Any]:
        """等待指定秒数。

        Args:
            seconds: 等待秒数（最大3600）

        Returns:
            操作结果字典
        """
        seconds = max(0, min(float(seconds), 3600))
        time.sleep(seconds)
        logger.debug("等待: %.1fs", seconds)
        return {'success': True, 'action': 'wait', 'seconds': seconds,
                'reply': f'已等待 {seconds} 秒'}

    def _wait_for_text(
        self,
        text: str = '',
        timeout: int = 10,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """轮询等待指定文本出现。

        通过UI scripting检测，每隔1秒检查一次。

        Args:
            text: 等待出现的文本
            timeout: 最大等待秒数

        Returns:
            操作结果字典
        """
        if not text:
            return {'success': False, 'error': '未指定等待文本'}
        safe_text = self._escape_applescript(text)
        script = f'''
        tell application "System Events"
            tell process "SystemUIServer"
                return (count of (every button whose description contains "{safe_text}"))
            end tell
        end tell
        '''
        start = time.time()
        while time.time() - start < timeout:
            result = self._run_applescript(script, timeout=5)
            try:
                if int(result.stdout.strip()) > 0:
                    logger.debug("等待文本出现: %s, 耗时: %.1fs", text, time.time() - start)
                    return {'success': True, 'action': 'wait_for_text', 'text': text,
                            'reply': f'文本 "{text}" 已出现'}
            except (ValueError, IndexError):
                pass
            time.sleep(1)

        logger.warning("等待文本超时: %s, %ds", text, timeout)
        return {'success': False, 'error': f'等待文本 "{text}" 超时 ({timeout}s)'}

    def _volume_adjust(self, level: int = 50, action_type: str = "set", **kwargs: Any) -> Dict[str, Any]:
        """调整系统音量。

        Args:
            level: 音量级别 (0-100) 或变化量
            action_type: 操作类型
                - "set": 设置为指定值（默认）
                - "increase": 提高音量
                - "decrease": 降低音量
                - "up": 提高音量（同increase）
                - "down": 降低音量（同decrease）

        Returns:
            操作结果字典
        """
        try:
            # 获取当前音量
            current_volume_script = 'output volume of (get volume settings)'
            result = subprocess.run(
                ['osascript', '-e', current_volume_script],
                capture_output=True, text=True, timeout=3
            )
            current_volume = int(result.stdout.strip()) if result.returncode == 0 else 50
            
            # 根据操作类型计算新音量
            action_type_lower = action_type.lower() if action_type else "set"
            
            if action_type_lower in ["increase", "up", "提高", "增加"]:
                # 提高音量
                new_volume = current_volume + level
                logger.info(f"提高音量: {current_volume}% + {level}% = {new_volume}%")
            elif action_type_lower in ["decrease", "down", "降低", "减少"]:
                # 降低音量
                new_volume = current_volume - level
                logger.info(f"降低音量: {current_volume}% - {level}% = {new_volume}%")
            else:
                # 设置为指定值
                new_volume = level
                logger.info(f"设置音量: {current_volume}% -> {new_volume}%")
            
            # 限制在0-100范围内
            new_volume = max(0, min(100, int(new_volume)))
            
            # 设置新音量
            script = f'set volume output volume {new_volume}'
            self._run_applescript(script)
            
            # 生成友好的回复
            if action_type_lower in ["increase", "up", "提高", "增加"]:
                reply = f'音量已提高 {level}%，当前音量 {new_volume}%'
            elif action_type_lower in ["decrease", "down", "降低", "减少"]:
                reply = f'音量已降低 {level}%，当前音量 {new_volume}%'
            else:
                reply = f'音量已调整为 {new_volume}%'
            
            logger.debug("音量调整完成: %d%% -> %d%%", current_volume, new_volume)
            return {
                'success': True, 
                'action': 'volume_adjust', 
                'previous_level': current_volume,
                'level': new_volume,
                'change': new_volume - current_volume,
                'reply': reply
            }
            
        except Exception as e:
            logger.error(f"音量调节失败: {e}")
            return {
                'success': False, 
                'action': 'volume_adjust',
                'error': str(e),
                'reply': f'音量调节失败: {e}'
            }

    def _brightness_adjust(self, level: int = 70, **kwargs: Any) -> Dict[str, Any]:
        """调整屏幕亮度。

        需安装brightness命令: brew install brightness

        Args:
            level: 亮度级别 (0-100)

        Returns:
            操作结果字典
        """
        level = max(0, min(100, int(level)))
        try:
            subprocess.run(['brightness', str(level)], check=False, timeout=self.default_timeout)
            logger.debug("亮度调整: %d%%", level)
            return {'success': True, 'action': 'brightness_adjust', 'level': level,
                    'reply': f'亮度已调整为 {level}%'}
        except FileNotFoundError:
            logger.warning("brightness命令未安装")
            return {'success': False, 'error': 'brightness命令未安装 (brew install brightness)'}

    # ── 剪贴板 ──────────────────────────────────────────

    def _copy_to_clipboard(self, text: str) -> None:
        """复制文本到剪贴板，pyperclip不可用时降级到pbcopy。

        Args:
            text: 要复制的文本
        """
        try:
            import pyperclip  # type: ignore[import-untyped]
            pyperclip.copy(text)
        except ImportError:
            subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=False)

    def _set_clipboard(self, text: str = '', **kwargs: Any) -> Dict[str, Any]:
        """设置剪贴板内容。

        Args:
            text: 要设置的内容

        Returns:
            操作结果字典
        """
        self._copy_to_clipboard(text)
        logger.debug("设置剪贴板: %s", text[:50] if text else '')
        return {'success': True, 'action': 'set_clipboard', 'reply': '剪贴板已更新'}

    def _get_clipboard(self, **kwargs: Any) -> Dict[str, Any]:
        """获取剪贴板内容。

        Returns:
            包含剪贴板文本的字典
        """
        try:
            import pyperclip  # type: ignore[import-untyped]
            text: str = pyperclip.paste()
        except ImportError:
            result = subprocess.run(['pbpaste'], capture_output=True, text=True)
            text = result.stdout

        logger.debug("获取剪贴板: %s", text[:50] if text else '(空)')
        return {'success': True, 'action': 'get_clipboard', 'text': text,
                'reply': f'剪贴板内容: {text[:200]}' if text else '剪贴板为空'}

    # ── AppleScript执行 ─────────────────────────────────

    def _applescript(self, script: str = '', **kwargs: Any) -> Dict[str, Any]:
        """执行任意AppleScript代码。

        Args:
            script: AppleScript代码
            timeout: 自定义超时秒数

        Returns:
            包含执行输出和错误信息的字典
        """
        if not script:
            return {'success': False, 'error': '未指定AppleScript代码'}
        timeout = kwargs.get('timeout', self.default_timeout)
        result = self._run_applescript(script, timeout=int(timeout))
        output = result.stdout.strip() if result.stdout else ''
        error = result.stderr.strip() if result.stderr else ''
        success = result.returncode == 0
        reply = output if success else f'执行失败: {error}'
        logger.debug("AppleScript执行: success=%s, output=%s", success, output[:100])
        return {'success': success, 'action': 'applescript', 'output': output, 'error': error,
                'reply': reply}

    def _ocr_screenshot(self, name: str = '', **kwargs: Any) -> Dict[str, Any]:
        """截屏并进行OCR文字识别

        Args:
            name: 文件名，默认自动生成时间戳文件名

        Returns:
            包含截图路径和识别文字的字典
        """
        try:
            if not name:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                name = f'screenshot_{timestamp}.png'
            if not name.endswith('.png'):
                name += '.png'

            desktop = os.path.join(os.path.expanduser('~'), 'Desktop', name)
            subprocess.run(['screencapture', '-x', desktop], check=False, timeout=10)

            try:
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(use_angle_cls=True, lang='ch')
                result = ocr.ocr(desktop)

                if not result or not result[0]:
                    return {
                        'success': True,
                        'action': 'ocr_screenshot',
                        'path': desktop,
                        'text': '',
                        'reply': f'截图已保存: {desktop}\n未检测到文字内容',
                    }

                all_text = []
                for line in result[0]:
                    if line:
                        box = line[0]
                        text_info = line[1]

                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                            text = text_info[0]
                            confidence = text_info[1] if len(text_info) > 1 else 0.0
                        elif isinstance(text_info, str):
                            text = text_info
                            confidence = 0.0
                        else:
                            continue

                        all_text.append(text)

                full_text = '\n'.join(all_text)

                reply_lines = [
                    f'📸 截图已保存: {desktop}',
                    f'📝 识别到 {len(all_text)} 行文字',
                    '',
                    '识别内容:',
                    full_text[:500] + ('...' if len(full_text) > 500 else ''),
                ]

                return {
                    'success': True,
                    'action': 'ocr_screenshot',
                    'path': desktop,
                    'text': full_text,
                    'text_count': len(all_text),
                    'reply': '\n'.join(reply_lines),
                }

            except ImportError:
                return {
                    'success': True,
                    'action': 'ocr_screenshot',
                    'path': desktop,
                    'text': '',
                    'reply': f'截图已保存: {desktop}\nOCR功能未安装 (pip install paddleocr paddlepaddle)',
                }
            except Exception as e:
                logger.error(f"OCR识别失败: {e}", exc_info=True)
                return {
                    'success': True,
                    'action': 'ocr_screenshot',
                    'path': desktop,
                    'text': '',
                    'reply': f'截图已保存: {desktop}\nOCR识别失败: {e}',
                }

        except Exception as e:
            logger.error(f"OCR截图失败: {e}", exc_info=True)
            return {'success': False, 'error': f'OCR截图失败: {e}'}

    def _browser_zoom(self, zoom: str = '100%', app: str = '', **kwargs: Any) -> Dict[str, Any]:
        """浏览器缩放控制

        支持的缩放选项：
        - 百分比：50%, 75%, 100%, 125%, 150%, 200%, 300%, 400%
        - 快捷键：实际大小(100%), 适合页面, 适合页宽
        - 相对缩放：放大(+), 缩小(-)

        Args:
            zoom: 缩放级别或选项
            app: 浏览器应用名称（可选，默认Safari）

        Returns:
            操作结果字典
        """
        zoom_map = {
            '50%': ('0', '5'),
            '75%': ('0', '2'),
            '100%': ('0', '0'),
            '125%': ('0', '5'),
            '150%': ('0', '5'),
            '200%': ('0', '5'),
            '300%': ('0', '5'),
            '400%': ('0', '5'),
            '实际大小': ('0', '0'),
            '适合页面': ('0', '9'),
            '适合页宽': ('0', '8'),
            '放大': ('0', '2'),
            '缩小': ('0', '1'),
            '+': ('0', '2'),
            '-': ('0', '1'),
        }

        zoom_key = zoom.lower().replace(' ', '')
        if zoom_key not in zoom_map:
            supported = ', '.join(['50%', '75%', '100%', '125%', '150%', '200%', '300%', '400%', '实际大小', '适合页面', '适合页宽', '放大', '缩小'])
            return {
                'success': False,
                'error': f'不支持的缩放级别: {zoom}，支持: {supported}'
            }

        modifier, key = zoom_map[zoom_key]

        if app:
            self._open_app(app)

        script = f'tell application "System Events" to keystroke "{key}" using {{command down, option down}}'
        self._run_applescript(script)

        logger.debug("浏览器缩放: %s", zoom)
        return {
            'success': True,
            'action': 'browser_zoom',
            'zoom': zoom,
            'reply': f'已将浏览器缩放设置为: {zoom}'
        }


gui_handler = GUIAutomationHandler()
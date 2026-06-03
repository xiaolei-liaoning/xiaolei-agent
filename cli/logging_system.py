"""简化日志系统 - CLI专用

提供简洁的日志记录功能，支持不同级别和输出格式。
支持同时输出到终端和日志文件。
"""

import sys
import time
from datetime import datetime
from enum import Enum
from typing import Optional
from pathlib import Path

from cli.colors import CliColors, ansi


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class SimpleLogger:
    """简化日志类 - 支持双终端输出"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _ensure_init(self):
        """延迟初始化 - 确保只在首次使用时初始化"""
        if not SimpleLogger._initialized:
            self._level = LogLevel.INFO
            self._show_timestamp = True
            self._log_file = None
            self._log_to_console = True
            SimpleLogger._initialized = True
    
    def set_level(self, level: LogLevel):
        """设置日志级别"""
        self._ensure_init()
        self._level = level
    
    def set_log_file(self, filepath: str):
        """设置日志文件"""
        self._ensure_init()
        # 确保日志目录存在
        log_dir = Path(filepath).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = filepath
    
    def set_log_to_console(self, enable: bool):
        """设置是否输出到终端"""
        self._ensure_init()
        self._log_to_console = enable
    
    def _format_message(self, level: LogLevel, message: str, with_color: bool = True) -> str:
        """格式化日志消息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        level_colors = {
            LogLevel.DEBUG: ansi['gray'],
            LogLevel.INFO: ansi['cyan'],
            LogLevel.WARNING: ansi['yellow'],
            LogLevel.ERROR: ansi['red'],
            LogLevel.SUCCESS: ansi['green'],
        }

        level_icons = {
            LogLevel.DEBUG: "🔍",
            LogLevel.INFO: "ℹ️",
            LogLevel.WARNING: "⚠️",
            LogLevel.ERROR: "❌",
            LogLevel.SUCCESS: "✅",
        }

        color = level_colors.get(level, ansi['white'])
        icon = level_icons.get(level, "📝")

        if with_color:
            if self._show_timestamp:
                return f"{timestamp} | {color}{icon} {level.value}{ansi['end']} | {message}"
            return f"{color}{icon} {level.value}{ansi['end']} | {message}"
        else:
            # 无颜色版本，用于日志文件
            if self._show_timestamp:
                return f"{timestamp} | {icon} {level.value} | {message}"
            return f"{icon} {level.value} | {message}"
    
    def _write(self, level: LogLevel, message: str):
        """写入日志"""
        self._ensure_init()
        # 输出到终端（带颜色）
        if self._log_to_console:
            print(self._format_message(level, message, with_color=True))
        
        # 输出到日志文件（无颜色）
        if self._log_file:
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(self._format_message(level, message, with_color=False) + "\n")
            except Exception as e:
                # 如果写入失败，尝试输出到终端
                if self._log_to_console:
                    print(f"❌ 日志写入失败: {e}")
    
    def debug(self, message: str):
        """调试日志"""
        self._ensure_init()
        if self._level.value <= LogLevel.DEBUG.value:
            self._write(LogLevel.DEBUG, message)
    
    def info(self, message: str):
        """信息日志"""
        self._ensure_init()
        if self._level.value <= LogLevel.INFO.value:
            self._write(LogLevel.INFO, message)
    
    def warning(self, message: str):
        """警告日志"""
        self._ensure_init()
        if self._level.value <= LogLevel.WARNING.value:
            self._write(LogLevel.WARNING, message)
    
    def error(self, message: str):
        """错误日志"""
        self._ensure_init()
        if self._level.value <= LogLevel.ERROR.value:
            self._write(LogLevel.ERROR, message)
    
    def success(self, message: str):
        """成功日志"""
        self._ensure_init()
        if self._level.value <= LogLevel.SUCCESS.value:
            self._write(LogLevel.SUCCESS, message)


def get_logger() -> SimpleLogger:
    """获取日志实例"""
    return SimpleLogger()


def init_logger(log_file: str = None, log_to_console: bool = True):
    """初始化日志系统 - 控制台只显示 WARNING+，文件记录 INFO+"""
    import logging

    # 清理所有已存在的 logging handler
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.root.setLevel(logging.INFO)

    # 文件 handler（记录所有 INFO 及以上）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
        file_handler.setLevel(logging.INFO)
        logging.root.addHandler(file_handler)

    # 控制台 handler（只显示 WARNING 及以上，避免 INFO 日志刷屏）
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s'))
        console_handler.setLevel(logging.WARNING)
        logging.root.addHandler(console_handler)
    elif log_file:
        # 只有文件日志（双终端模式下控制台无日志输出）
        pass
    else:
        # 纯控制台且无文件：只显示 WARNING+
        logging.basicConfig(
            level=logging.WARNING,
            format='%(asctime)s | %(levelname)s | %(message)s'
        )

    # 初始化我们的日志系统
    logger = get_logger()
    if log_file:
        logger.set_log_file(log_file)
    logger.set_log_to_console(log_to_console)
    if not log_to_console:
        from cli.logging_system import LogLevel
        logger.set_level(LogLevel.WARNING)
    
    return logger


# 便捷函数
def log_debug(message: str):
    get_logger().debug(message)


def log_info(message: str):
    get_logger().info(message)


def log_warning(message: str):
    get_logger().warning(message)


def log_error(message: str):
    get_logger().error(message)


def log_success(message: str):
    get_logger().success(message)
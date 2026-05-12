"""
增强型日志系统 - 彩色输出、分级显示、性能监控
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional
from colorama import init, Fore, Back, Style

# 初始化colorama（Windows兼容）
init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    # 颜色映射
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Back.WHITE + Style.BRIGHT,
    }
    
    # Emoji映射
    EMOJIS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️ ',
        'ERROR': '❌',
        'CRITICAL': '🔥',
    }
    
    def __init__(self, fmt=None, datefmt=None, use_color=True):
        super().__init__(fmt, datefmt)
        self.use_color = use_color
    
    def format(self, record):
        # 保存原始级别
        original_levelname = record.levelname
        
        if self.use_color:
            # 添加颜色和Emoji
            color = self.COLORS.get(record.levelname, '')
            emoji = self.EMOJIS.get(record.levelname, '')
            record.levelname = f"{color}{emoji} {record.levelname}{Style.RESET_ALL}"
        
        # 格式化
        result = super().format(record)
        
        # 恢复原始级别
        record.levelname = original_levelname
        
        return result


class PerformanceFilter(logging.Filter):
    """性能过滤器 - 标记慢操作"""
    
    def __init__(self, slow_threshold=1.0):
        super().__init__()
        self.slow_threshold = slow_threshold
    
    def filter(self, record):
        # 如果日志包含执行时间信息，标记慢操作
        if hasattr(record, 'execution_time'):
            if record.execution_time > self.slow_threshold:
                record.msg = f"🐢 [慢操作] {record.msg}"
            else:
                record.msg = f"⚡ [快速] {record.msg}"
        return True


class ModuleFilter(logging.Filter):
    """模块过滤器 - 按模块名过滤"""
    
    def __init__(self, allowed_modules=None):
        super().__init__()
        self.allowed_modules = allowed_modules or []
    
    def filter(self, record):
        if not self.allowed_modules:
            return True
        
        # 检查模块名是否在允许列表中
        for module in self.allowed_modules:
            if module in record.name:
                return True
        return False


def setup_enhanced_logging(
    level=logging.INFO,
    log_file: Optional[str] = None,
    enable_performance_tracking: bool = True,
    enable_module_filter: bool = False,
    allowed_modules: Optional[list] = None,
    enable_console: bool = True
):
    """
    设置增强型日志系统
    
    Args:
        level: 日志级别
        log_file: 日志文件路径（None则不写入文件）
        enable_performance_tracking: 启用性能追踪
        enable_module_filter: 启用模块过滤
        allowed_modules: 允许的模块列表
        enable_console: 是否启用控制台输出
    """
    
    # 创建根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除现有handlers
    root_logger.handlers.clear()
    
    # === 控制台Handler（彩色输出）===
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        
        # 彩色格式
        colored_format = ColoredFormatter(
            fmt='%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s',
            datefmt='%H:%M:%S',
            use_color=True
        )
        console_handler.setFormatter(colored_format)
        
        # 添加性能过滤器
        if enable_performance_tracking:
            perf_filter = PerformanceFilter(slow_threshold=1.0)
            console_handler.addFilter(perf_filter)
        
        # 添加模块过滤器
        if enable_module_filter and allowed_modules:
            module_filter = ModuleFilter(allowed_modules)
            console_handler.addFilter(module_filter)
        
        root_logger.addHandler(console_handler)
    
    # === 文件Handler（普通格式）===
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        # 文件格式（不含颜色）
        file_format = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)
    
    # === 错误日志单独文件 ===
    if log_file:
        error_log_file = log_file.replace('.log', '_error.log')
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_format)
        root_logger.addHandler(error_handler)
    
    return root_logger


class TimerLogger:
    """计时日志器 - 自动记录执行时间"""
    
    def __init__(self, logger_name: str = "timer"):
        self.logger = logging.getLogger(logger_name)
        self.start_time = None
    
    def start(self, message: str = "开始执行"):
        """开始计时"""
        self.start_time = datetime.now()
        self.logger.info(f"⏱️  {message}")
    
    def stop(self, message: str = "执行完成"):
        """停止计时并记录"""
        if self.start_time is None:
            self.logger.warning("⚠️  未启动计时器")
            return
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        extra = {'execution_time': elapsed}
        
        if elapsed > 1.0:
            self.logger.warning(f"⏱️  {message} (耗时: {elapsed:.2f}s)", extra=extra)
        else:
            self.logger.info(f"⏱️  {message} (耗时: {elapsed:.3f}s)", extra=extra)
        
        self.start_time = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.stop("执行失败")
        else:
            self.stop("执行成功")


# 便捷函数
def get_logger(name: str = None) -> logging.Logger:
    """获取logger实例"""
    if name:
        return logging.getLogger(name)
    return logging.getLogger()


def log_performance(func):
    """装饰器：自动记录函数执行时间"""
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        timer = TimerLogger(func.__qualname__)
        
        with timer:
            result = func(*args, **kwargs)
        
        return result
    
    return wrapper


# 自动初始化
if __name__ != "__main__":
    # 检查环境变量决定是否启用控制台输出
    enable_console = os.environ.get("AGENT_ENABLE_CONSOLE_LOG", "true").lower() != "false"
    log_file = os.environ.get("AGENT_LOG_FILE", "logs/app.log")
    
    # 默认配置
    setup_enhanced_logging(
        level=logging.INFO,
        log_file=log_file,
        enable_performance_tracking=True,
        enable_console=enable_console
    )

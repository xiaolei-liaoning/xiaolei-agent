#!/usr/bin/env python3
"""
定时任务模块：执行定期清理和维护任务
"""

import time
import threading
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Callable

from core.cache_manager import get_cache_manager
from core.memory_optimizer import get_memory_optimizer

logger = logging.getLogger(__name__)

class ScheduledTask:
    """定时任务"""
    
    def __init__(self, name: str, interval: int, callback: Callable, args: tuple = (), kwargs: dict = {}):
        """初始化定时任务
        
        Args:
            name: 任务名称
            interval: 执行间隔（秒）
            callback: 回调函数
            args: 回调函数参数
            kwargs: 回调函数关键字参数
        """
        self.name = name
        self.interval = interval
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.last_run = datetime.now()
        self.next_run = self.last_run + timedelta(seconds=interval)
        self.running = False
    
    def should_run(self) -> bool:
        """检查是否应该执行任务
        
        Returns:
            是否应该执行任务
        """
        return datetime.now() >= self.next_run
    
    def run(self):
        """执行任务"""
        if self.running:
            return
        
        self.running = True
        try:
            logger.info(f"开始执行任务: {self.name}")
            self.callback(*self.args, **self.kwargs)
            self.last_run = datetime.now()
            self.next_run = self.last_run + timedelta(seconds=self.interval)
            logger.info(f"任务执行完成: {self.name}")
        except Exception as e:
            logger.error(f"任务执行失败: {self.name}, 错误: {e}")
        finally:
            self.running = False

class ScheduledTaskManager:
    """定时任务管理器"""
    
    def __init__(self):
        """初始化定时任务管理器"""
        self.tasks = []
        self.running = False
        self.thread = None
        logger.info("定时任务管理器初始化完成")
    
    def add_task(self, task: ScheduledTask):
        """添加定时任务
        
        Args:
            task: 定时任务
        """
        self.tasks.append(task)
        logger.info(f"添加定时任务: {task.name}")
    
    def start(self):
        """启动定时任务管理器"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("定时任务管理器已启动")
    
    def stop(self):
        """停止定时任务管理器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("定时任务管理器已停止")
    
    def _run_loop(self):
        """运行循环"""
        while self.running:
            for task in self.tasks:
                if task.should_run():
                    task.run()
            time.sleep(1)
    
    def get_tasks(self) -> List[ScheduledTask]:
        """获取所有定时任务
        
        Returns:
            定时任务列表
        """
        return self.tasks

# 定期清理任务
def cleanup_cache():
    """清理缓存"""
    try:
        cache_manager = get_cache_manager()
        # 清理内存缓存
        memory_stats = cache_manager.get_stats("memory")
        logger.info(f"内存缓存统计: {memory_stats}")
        
        # 清理磁盘缓存
        disk_stats = cache_manager.get_stats("disk")
        logger.info(f"磁盘缓存统计: {disk_stats}")
        
        # 如果缓存使用超过80%，则清理最久未使用的缓存
        if memory_stats.get("usage", 0) > 80:
            cache_manager.clear("memory")
            logger.info("清理内存缓存")
        
        if disk_stats.get("usage", 0) > 80:
            cache_manager.clear("disk")
            logger.info("清理磁盘缓存")
    except Exception as e:
        logger.error(f"清理缓存失败: {e}")

def cleanup_memory():
    """清理内存"""
    try:
        memory_optimizer = get_memory_optimizer()
        # 执行内存优化
        memory_optimizer.optimize()
        
        # 获取内存使用摘要
        memory_summary = memory_optimizer.get_memory_summary()
        logger.info(f"内存使用摘要: {memory_summary}")
    except Exception as e:
        logger.error(f"清理内存失败: {e}")

def cleanup_logs():
    """清理日志"""
    try:
        # 这里只是一个示例，实际使用时需要根据日志系统进行清理
        logger.info("清理日志")
        # 实际日志清理代码
    except Exception as e:
        logger.error(f"清理日志失败: {e}")

def cleanup_database():
    """清理数据库"""
    try:
        # 这里只是一个示例，实际使用时需要根据数据库进行清理
        logger.info("清理数据库")
        # 实际数据库清理代码
    except Exception as e:
        logger.error(f"清理数据库失败: {e}")

# 全局定时任务管理器实例
scheduled_task_manager = ScheduledTaskManager()

def get_scheduled_task_manager() -> ScheduledTaskManager:
    """获取定时任务管理器实例
    
    Returns:
        ScheduledTaskManager实例
    """
    return scheduled_task_manager

# 初始化定时任务
def init_scheduled_tasks():
    """初始化定时任务"""
    # 添加缓存清理任务（每5分钟执行一次）
    cache_cleanup_task = ScheduledTask(
        name="缓存清理",
        interval=300,
        callback=cleanup_cache
    )
    scheduled_task_manager.add_task(cache_cleanup_task)
    
    # 添加内存清理任务（每10分钟执行一次）
    memory_cleanup_task = ScheduledTask(
        name="内存清理",
        interval=600,
        callback=cleanup_memory
    )
    scheduled_task_manager.add_task(memory_cleanup_task)
    
    # 添加日志清理任务（每小时执行一次）
    log_cleanup_task = ScheduledTask(
        name="日志清理",
        interval=3600,
        callback=cleanup_logs
    )
    scheduled_task_manager.add_task(log_cleanup_task)
    
    # 添加数据库清理任务（每天执行一次）
    database_cleanup_task = ScheduledTask(
        name="数据库清理",
        interval=86400,
        callback=cleanup_database
    )
    scheduled_task_manager.add_task(database_cleanup_task)
    
    # 启动定时任务管理器
    scheduled_task_manager.start()
    logger.info("定时任务初始化完成")
#!/usr/bin/env python3
"""
定期清理任务管理器

实现定期清理系统

负责定期清理系统中的无用数据和缓存，保持系统健康
"""

import logging
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional
from core.alert_manager import get_alert_manager

logger = logging.getLogger(__name__)


class ScheduledCleanupManager:
    """定期清理管理器"""
    
    def __init__(self):
        """初始化清理管理器"""
        self._running = False
        self._thread = None
        self._cleanup_tasks = []
        self._last_run = {}
        
        # 清理任务配置
        self._cleanup_config = {
            "old_chat_history": {
                "enabled": True,
                "interval": 3600 * 24,  # 每天运行一次
                "keep_days": 30,  # 保留30天
            },
            "cache_memory": {
                "enabled": True,
                "interval": 3600,  # 每小时运行一次
            },
            "monitoring_metrics": {
                "enabled": True,
                "interval": 3600 * 12,  # 每12小时运行一次
                "keep_hours": 168,  # 保留168小时（7天）
            },
            "alerts": {
                "enabled": True,
                "interval": 3600 * 24 * 7,  # 每周运行一次
                "keep_days": 30,  # 保留30天
            },
            "log_files": {
                "enabled": True,
                "interval": 3600 * 24,  # 每天运行一次
                "keep_days": 7,  # 保留7天
            },
            "temp_files": {
                "enabled": True,
                "interval": 3600 * 6,  # 每6小时运行一次
                "keep_hours": 24,  # 保留24小时
            },
            "bfs_context": {
                "enabled": True,
                "interval": 3600 * 4,  # 每4小时运行一次
                "keep_hours": 48,  # 保留48小时
            }
        }
        
        # 注册默认清理任务
        self._register_default_tasks()
        logger.info("定期清理管理器初始化完成")
    
    def _register_default_tasks(self):
        """注册默认清理任务"""
        self.register_task("old_chat_history", self._cleanup_old_chat_history)
        self.register_task("cache_memory", self._cleanup_cache_memory)
        self.register_task("monitoring_metrics", self._cleanup_monitoring_metrics)
        self.register_task("alerts", self._cleanup_alerts)
        self.register_task("log_files", self._cleanup_log_files)
        self.register_task("temp_files", self._cleanup_temp_files)
        self.register_task("bfs_context", self._cleanup_bfs_context)
    
    def register_task(self, task_name: str, task_func: Callable, interval: Optional[int] = None):
        """注册清理任务
        
        Args:
            task_name: 任务名称
            task_func: 任务函数
            interval: 执行间隔（秒），如果为None则使用配置中的间隔
        """
        task_config = self._cleanup_config.get(task_name, {})
        task_interval = interval or task_config.get("interval", 3600)
        
        self._cleanup_tasks.append({
            "name": task_name,
            "func": task_func,
            "interval": task_interval,
            "enabled": task_config.get("enabled", True)
        })
        
        logger.info(f"已注册清理任务: {task_name}")
    
    def unregister_task(self, task_name: str):
        """注销清理任务"""
        self._cleanup_tasks = [
            t for t in self._cleanup_tasks if t["name"] != task_name
        ]
        logger.info(f"已注销清理任务: {task_name}")
    
    def start(self):
        """启动清理任务"""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self._thread.start()
            logger.info("定期清理任务已启动")
    
    def stop(self):
        """停止清理任务"""
        if self._running:
            self._running = False
            if self._thread:
                self._thread.join()
            logger.info("定期清理任务已停止")
    
    def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                self._run_cleanup_tasks()
                # 每分钟检查一次是否需要执行清理
                time.sleep(60)
            except Exception as e:
                logger.error(f"清理循环执行失败: {e}")
                time.sleep(60)
    
    def _run_cleanup_tasks(self):
        """运行清理任务"""
        now = time.time()
        
        for task in self._cleanup_tasks:
            task_name = task["name"]
            task_func = task["func"]
            task_interval = task["interval"]
            task_enabled = task["enabled"]
            
            if not task_enabled:
                continue
            
            last_run = self._last_run.get(task_name, 0)
            
            if now - last_run >= task_interval:
                try:
                    logger.info(f"执行清理任务: {task_name}")
                    result = task_func()
                    self._last_run[task_name] = now
                    
                    if result:
                        logger.info(f"清理任务完成: {task_name}: {result}")
                except Exception as e:
                    logger.error(f"清理任务失败: {task_name}: {e}")
    
    def _cleanup_old_chat_history(self) -> Dict[str, Any]:
        """清理旧的聊天历史记录"""
        try:
            from core.database import get_db_session
            from core.database import ChatHistory
            
            config = self._cleanup_config.get("old_chat_history", {})
            keep_days = config.get("keep_days", 30)
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            
            with get_db_session() as session:
                # 统计需要删除的记录数
                count = session.query(ChatHistory).filter(ChatHistory.created_at < cutoff_date).count()
                
                # 删除旧记录
                session.query(ChatHistory).filter(ChatHistory.created_at < cutoff_date).delete(synchronize_session=False)
                
                logger.info(f"清理了 {count} 条旧聊天历史记录")
                return {"task": "old_chat_history", "deleted_count": count}
        except Exception as e:
            logger.error(f"清理聊天历史失败: {e}")
            return {"task": "old_chat_history", "error": str(e)}
    
    def _cleanup_cache_memory(self) -> Dict[str, Any]:
        """清理内存缓存"""
        try:
            from core.cache_manager import get_cache_manager
            cache_mgr = get_cache_manager()
            
            # 清理过期缓存
            for cache_type in ["memory", "disk"]:
                cache_mgr._cleanup_expired(cache_type)
            
            # 获取缓存统计
            stats = cache_mgr.get_stats("memory")
            
            logger.info(f"清理缓存: {stats['total']} 条记录")
            return {"task": "cache_memory", "memory_stats": stats}
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            return {"task": "cache_memory", "error": str(e)}
    
    def _cleanup_monitoring_metrics(self) -> Dict[str, Any]:
        """清理监控指标"""
        try:
            from core.monitoring import monitoring_manager
            
            config = self._cleanup_config.get("monitoring_metrics", {})
            keep_hours = config.get("keep_hours", 168)
            cutoff_timestamp = time.time() - (keep_hours * 3600)
            
            # 清理过期的监控数据
            cleaned_count = 0
            for metric_type in monitoring_manager.metrics:
                original_len = len(monitoring_manager.metrics[metric_type])
                monitoring_manager.metrics[metric_type] = [
                    m for m in monitoring_manager.metrics[metric_type]
                    if m.get("timestamp", 0) >= cutoff_timestamp
                ]
                cleaned_count += original_len - len(monitoring_manager.metrics[metric_type])
            
            logger.info(f"清理了 {cleaned_count} 条监控指标")
            return {"task": "monitoring_metrics", "cleaned_count": cleaned_count}
        except Exception as e:
            logger.error(f"清理监控指标失败: {e}")
            return {"task": "monitoring_metrics", "error": str(e)}
    
    def _cleanup_alerts(self) -> Dict[str, Any]:
        """清理告警记录"""
        try:
            alert_mgr = get_alert_manager()
            config = self._cleanup_config.get("alerts", {})
            keep_days = config.get("keep_days", 30)
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            
            # 清理已解决且超过保留期的告警
            alert_mgr.alert_history = [
                a for a in alert_mgr.alert_history
                if (a.get("status") != "resolved" or
                    datetime.fromisoformat(a.get("timestamp")) >= cutoff_date)
            ]
            
            cleaned_count = 0  # 这里可以添加统计逻辑
            
            logger.info("清理告警记录完成")
            return {"task": "alerts", "cleaned_count": cleaned_count}
        except Exception as e:
            logger.error(f"清理告警记录失败: {e}")
            return {"task": "alerts", "error": str(e)}
    
    def _cleanup_log_files(self) -> Dict[str, Any]:
        """清理日志文件"""
        try:
            import glob
            
            config = self._cleanup_config.get("log_files", {})
            keep_days = config.get("keep_days", 7)
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            
            cleaned_count = 0
            
            # 清理 data 目录下的日志文件
            log_patterns = [
                "data/*.log",
                "data/monitoring*.log",
                "logs/*.log"
            ]
            
            for pattern in log_patterns:
                for log_file in glob.glob(pattern):
                    try:
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
                        if file_mtime < cutoff_date:
                            os.remove(log_file)
                            cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"删除日志文件失败 {log_file}: {e}")
            
            logger.info(f"清理了 {cleaned_count} 个日志文件")
            return {"task": "log_files", "cleaned_count": cleaned_count}
        except Exception as e:
            logger.error(f"清理日志文件失败: {e}")
            return {"task": "log_files", "error": str(e)}
    
    def _cleanup_temp_files(self) -> Dict[str, Any]:
        """清理临时文件"""
        try:
            import tempfile
            import shutil
            
            config = self._cleanup_config.get("temp_files", {})
            keep_hours = config.get("keep_hours", 24)
            cutoff_date = datetime.now() - timedelta(hours=keep_hours)
            
            cleaned_count = 0
            
            # 清理系统临时目录
            temp_dirs = [
                tempfile.gettempdir(),
                "/tmp",
                "temp"
            ]
            
            for temp_dir in temp_dirs:
                if not os.path.exists(temp_dir):
                    continue
                
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    try:
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(item_path))
                        if file_mtime < cutoff_date:
                            if os.path.isfile(item_path):
                                os.remove(item_path)
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                            cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"删除临时文件失败 {item_path}: {e}")
            
            logger.info(f"清理了 {cleaned_count} 个临时文件/目录")
            return {"task": "temp_files", "cleaned_count": cleaned_count}
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")
            return {"task": "temp_files", "error": str(e)}
    
    def _cleanup_bfs_context(self) -> Dict[str, Any]:
        """清理BFS上下文数据"""
        try:
            from core.database import get_db_session
            from core.database import BFSContextNode
            
            config = self._cleanup_config.get("bfs_context", {})
            keep_hours = config.get("keep_hours", 48)
            cutoff_date = datetime.now() - timedelta(hours=keep_hours)
            
            with get_db_session() as session:
                # 删除旧的上下文节点
                count = session.query(BFSContextNode).filter(BFSContextNode.updated_at < cutoff_date).count()
                session.query(BFSContextNode).filter(BFSContextNode.updated_at < cutoff_date).delete(synchronize_session=False)
                
                logger.info(f"清理了 {count} 条BFS上下文节点")
                return {"task": "bfs_context", "deleted_count": count}
        except Exception as e:
            logger.error(f"清理BFS上下文失败: {e}")
            return {"task": "bfs_context", "error": str(e)}
    
    def run_task_now(self, task_name: str) -> Dict[str, Any]:
        """立即运行指定的清理任务
        
        Args:
            task_name: 任务名称
            
        Returns:
            任务执行结果
        """
        for task in self._cleanup_tasks:
            if task["name"] == task_name:
                try:
                    result = task["func"]()
                    self._last_run[task_name] = time.time()
                    return result
                except Exception as e:
                    logger.error(f"立即执行清理任务失败: {task_name}: {e}")
                    return {"task": task_name, "error": str(e)}
        
        return {"task": task_name, "error": "任务未找到"}
    
    def get_task_status(self) -> Dict[str, Any]:
        """获取清理任务状态
        
        Returns:
            任务状态字典
        """
        status = {}
        for task in self._cleanup_tasks:
            task_name = task["name"]
            last_run = self._last_run.get(task_name)
            status[task_name] = {
                "enabled": task["enabled"],
                "interval": task["interval"],
                "last_run": datetime.fromtimestamp(last_run).isoformat() if last_run else None,
                "next_run": datetime.fromtimestamp(last_run + task["interval"]).isoformat() if last_run else None
            }
        return status


# 全局清理管理器实例
cleanup_manager = ScheduledCleanupManager()


def get_cleanup_manager() -> ScheduledCleanupManager:
    """获取清理管理器实例"""
    return cleanup_manager

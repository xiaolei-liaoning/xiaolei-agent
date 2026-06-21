#!/usr/bin/env python3
"""内存优化模块"""

import gc
import psutil
import logging
import tracemalloc
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

# 配置日志
logger = logging.getLogger(__name__)

# 告警功能已集成到 core.monitoring.monitoring 中


class MemoryOptimizer:
    """内存优化器"""
    
    def __init__(self):
        """初始化内存优化器"""
        self.start_time = datetime.now()
        self.memory_usage_history = []
        self.peak_memory = 0
        self.enable_tracemalloc = False
        self.optimization_interval = 60  # 默认优化间隔（秒）
        self.optimization_thread = None
        self.running = False
        self.memory_snapshots = []  # 内存快照，用于检测内存泄漏
        self.last_optimization_time = datetime.now()
        self.alert_threshold = 90  # 内存使用告警阈值（%）
        self.history_data = []  # 历史数据，用于自动调优
        self.auto_tuning_enabled = True  # 是否启用自动调优
        
        # 告警功能通过 monitoring 模块提供
        
        # 根据实际系统配置自动调整内存阈值
        self.memory_threshold = self._calculate_memory_threshold()
        logger.info(f"根据系统配置自动设置内存阈值: {self.memory_threshold}MB")
    
    def _calculate_memory_threshold(self) -> int:
        """根据系统配置计算内存阈值"""
        try:
            # 获取系统总内存
            total_memory = psutil.virtual_memory().total / (1024 * 1024)  # 转换为MB
            
            # 根据总内存设置合理的阈值
            if total_memory < 4096:  # 小于4GB
                return int(total_memory * 0.7)  # 使用70%内存
            elif total_memory < 8192:  # 4GB-8GB
                return int(total_memory * 0.75)  # 使用75%内存
            elif total_memory < 16384:  # 8GB-16GB
                return int(total_memory * 0.8)  # 使用80%内存
            else:  # 16GB以上
                return int(total_memory * 0.85)  # 使用85%内存
        except Exception as e:
            logger.error("计算内存阈值失败: %s", e)
            return 500  # 默认值
    
    def start(self):
        """启动内存优化器"""
        logger.info("内存优化器已启动")
        
        # 启动内存追踪
        if self.enable_tracemalloc:
            tracemalloc.start()
        
        # 记录初始内存使用
        self._record_memory_usage()
        
        # 启动定期优化线程
        self.running = True
        self.optimization_thread = threading.Thread(target=self._optimization_loop, daemon=True)
        self.optimization_thread.start()
    
    def stop(self):
        """停止内存优化器"""
        self.running = False
        if self.optimization_thread:
            self.optimization_thread.join(timeout=5)
        
        if self.enable_tracemalloc:
            tracemalloc.stop()
        logger.info("内存优化器已停止")
    
    def _auto_tune(self):
        """基于历史数据自动调优"""
        try:
            if not self.auto_tuning_enabled or len(self.history_data) < 10:
                return
            
            # 分析历史数据
            recent_data = self.history_data[-10:]
            avg_memory = sum(d['memory'] for d in recent_data) / len(recent_data)
            avg_cpu = sum(d['cpu'] for d in recent_data) / len(recent_data)
            avg_load = sum(d['load'] for d in recent_data) / len(recent_data)
            avg_memory_percent = sum(d.get('memory_percent', 0) for d in recent_data) / len(recent_data)
            
            # 计算内存使用趋势
            memory_trend = []
            for i in range(1, len(recent_data)):
                memory_diff = recent_data[i]['memory'] - recent_data[i-1]['memory']
                memory_trend.append(memory_diff)
            
            # 计算内存使用变化率
            memory_change_rate = sum(memory_trend) / len(memory_trend) if memory_trend else 0
            
            # 根据历史数据调整优化策略
            # 1. 调整内存阈值
            if memory_change_rate > 5 and avg_memory > self.memory_threshold * 0.7:
                # 内存使用持续增长且较高，降低阈值
                new_threshold = int(self.memory_threshold * 0.85)
                if new_threshold < 100:
                    new_threshold = 100
                logger.info(f"自动调优: 降低内存阈值从 {self.memory_threshold}MB 到 {new_threshold}MB")
                self.memory_threshold = new_threshold
            elif memory_change_rate < -2 and avg_memory < self.memory_threshold * 0.6:
                # 内存使用持续下降且较低，提高阈值
                new_threshold = int(self.memory_threshold * 1.15)
                max_threshold = self._calculate_memory_threshold()
                if new_threshold > max_threshold:
                    new_threshold = max_threshold
                logger.info(f"自动调优: 提高内存阈值从 {self.memory_threshold}MB 到 {new_threshold}MB")
                self.memory_threshold = new_threshold
            
            # 2. 调整优化间隔
            if (avg_cpu > 75 or avg_load > 1.8) or avg_memory_percent > 85:
                # 系统负载较高或内存紧张，增加优化间隔
                new_interval = min(180, self.optimization_interval * 1.3)
                logger.info(f"自动调优: 增加优化间隔从 {self.optimization_interval}秒 到 {int(new_interval)}秒")
                self.optimization_interval = int(new_interval)
            elif (avg_cpu < 25 and avg_load < 0.4) and avg_memory_percent < 60:
                # 系统负载较低且内存充足，减少优化间隔
                new_interval = max(10, self.optimization_interval * 0.7)
                logger.info(f"自动调优: 减少优化间隔从 {self.optimization_interval}秒 到 {int(new_interval)}秒")
                self.optimization_interval = int(new_interval)
            
            # 3. 调整告警阈值
            if avg_memory_percent > 75:
                # 内存使用持续较高，降低告警阈值
                new_alert_threshold = min(85, self.alert_threshold - 2)
                if new_alert_threshold != self.alert_threshold:
                    logger.info(f"自动调优: 降低告警阈值从 {self.alert_threshold}% 到 {new_alert_threshold}%")
                    self.alert_threshold = new_alert_threshold
            elif avg_memory_percent < 60:
                # 内存使用持续较低，提高告警阈值
                new_alert_threshold = max(90, self.alert_threshold + 2)
                if new_alert_threshold != self.alert_threshold:
                    logger.info(f"自动调优: 提高告警阈值从 {self.alert_threshold}% 到 {new_alert_threshold}%")
                    self.alert_threshold = new_alert_threshold
        except Exception as e:
            logger.error("自动调优失败: %s", e)
    
    def _optimization_loop(self):
        """定期优化循环"""
        while self.running:
            try:
                # 记录当前系统状态
                current_memory = self.get_current_memory_usage()
                memory_percent = psutil.virtual_memory().percent
                cpu_percent = psutil.cpu_percent(interval=0.1)
                load_avg = psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0
                
                # 记录历史数据
                self.history_data.append({
                    "timestamp": datetime.now(),
                    "memory": current_memory or 0,
                    "memory_percent": memory_percent,
                    "cpu": cpu_percent,
                    "load": load_avg,
                    "interval": self.optimization_interval
                })
                
                # 限制历史数据数量
                if len(self.history_data) > 100:
                    self.history_data = self.history_data[-100:]
                
                # 根据系统负载调整优化策略
                self._adjust_optimization_strategy()
                
                # 执行内存优化
                self.optimize()
                
                # 检查内存告警
                self._check_memory_alert()
                
                # 检查内存泄漏
                self._detect_memory_leaks()
                
                # 自动调优
                self._auto_tune()
                
                # 等待下一次优化
                time.sleep(self.optimization_interval)
            except Exception as e:
                logger.error("优化循环错误: %s", e)
                time.sleep(5)
    
    def set_memory_threshold(self, threshold: float):
        """设置内存使用阈值
        
        Args:
            threshold: 内存阈值（MB）
        """
        self.memory_threshold = threshold
        logger.info(f"内存阈值已设置为: {threshold}MB")
    
    def set_optimization_interval(self, interval: int):
        """设置优化间隔
        
        Args:
            interval: 优化间隔（秒）
        """
        self.optimization_interval = interval
        logger.info(f"优化间隔已设置为: {interval}秒")
    
    def _record_memory_usage(self):
        """记录内存使用情况"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_usage = {
                "timestamp": datetime.now().isoformat(),
                "rss": memory_info.rss / (1024 * 1024),  # 转换为MB
                "vms": memory_info.vms / (1024 * 1024),
                "peak": self.peak_memory / (1024 * 1024)
            }
            
            self.memory_usage_history.append(memory_usage)
            
            # 限制历史记录数量
            if len(self.memory_usage_history) > 1000:
                self.memory_usage_history = self.memory_usage_history[-1000:]
            
            # 更新峰值内存
            if memory_info.rss > self.peak_memory:
                self.peak_memory = memory_info.rss
        except Exception as e:
            logger.error("记录内存使用失败: %s", e)
    
    def _adjust_optimization_strategy(self):
        """根据系统负载调整优化策略"""
        try:
            # 获取系统负载
            load_avg = psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent
            
            # 综合考虑CPU、内存和负载情况
            if (load_avg > 2.0 or cpu_percent > 80) and memory_percent < 70:
                # 高CPU负载但内存充足时，减少优化频率
                self.optimization_interval = 120
            elif (load_avg > 1.0 or cpu_percent > 50) and memory_percent < 80:
                # 中等CPU负载且内存充足时，保持默认频率
                self.optimization_interval = 60
            elif memory_percent > 85:
                # 内存紧张时，增加优化频率
                self.optimization_interval = 15
            else:
                # 低负载时，适度增加优化频率
                self.optimization_interval = 30
            
            logger.debug(f"调整优化策略: 负载={load_avg:.2f}, CPU={cpu_percent:.1f}%, 内存={memory_percent:.1f}%, 优化间隔={self.optimization_interval}秒")
                
        except Exception as e:
            logger.error("调整优化策略失败: %s", e)
    
    def optimize(self):
        """执行内存优化"""
        try:
            # 记录优化开始时间
            start_time = datetime.now()
            
            # 执行垃圾回收
            collected = gc.collect()
            logger.debug(f"垃圾回收: 回收了 {collected} 个对象")
            
            # 记录优化后的内存使用
            self._record_memory_usage()
            
            # 检查内存使用情况
            memory_usage = self.get_current_memory_usage()
            if memory_usage and memory_usage > self.memory_threshold:
                logger.warning(f"内存使用超过阈值: {memory_usage:.2f}MB > {self.memory_threshold}MB")
                self._aggressive_optimization()
            
            # 记录优化结束时间
            self.last_optimization_time = datetime.now()
            logger.debug(f"内存优化完成，耗时: {(self.last_optimization_time - start_time).total_seconds():.2f}秒")
            
        except Exception as e:
            logger.error("内存优化失败: %s", e)
    
    def _aggressive_optimization(self):
        """执行激进的内存优化"""
        try:
            # 强制垃圾回收
            gc.collect()
            
            # 清理缓存
            self._clear_caches()
            
            logger.info("执行了激进的内存优化")
        except Exception as e:
            logger.error("激进内存优化失败: %s", e)
    
    def _clear_caches(self):
        """清理缓存"""
        try:
            # 清理一些可能的缓存
            import sys
            if hasattr(sys, 'modules'):
                # 清理模块缓存（谨慎使用）
                for module_name in list(sys.modules.keys()):
                    if module_name.startswith('__pycache__'):
                        del sys.modules[module_name]
        except Exception as e:
            logger.error("清理缓存失败: %s", e)
    
    def _check_memory_alert(self):
        """检查内存使用异常并发出告警（通过 monitoring 模块）"""
        try:
            from core.monitoring.monitoring import get_monitor
            monitor = get_monitor()
            
            memory_percent = psutil.virtual_memory().percent
            current_memory = self.get_current_memory_usage()

            # 检查内存使用百分比
            if memory_percent > self.alert_threshold:
                logger.warning(f"内存使用告警: {memory_percent:.1f}%，超过阈值 {self.alert_threshold}%")
            
            # 检查进程内存使用
            if current_memory and current_memory > self.memory_threshold:
                logger.warning(f"进程内存使用告警: {current_memory:.2f}MB，超过阈值 {self.memory_threshold}MB")
                
        except Exception as e:
            logger.debug("检查内存告警失败: %s", e)
    
    def _detect_memory_leaks(self):
        """检测内存泄漏"""
        try:
            current_memory = self.get_current_memory_usage()
            if current_memory:
                # 记录内存快照
                process = psutil.Process()
                memory_info = process.memory_info()
                snapshot = {
                    "timestamp": datetime.now(),
                    "memory": current_memory,
                    "rss": memory_info.rss / (1024 * 1024),
                    "vms": memory_info.vms / (1024 * 1024),
                    "memory_percent": psutil.virtual_memory().percent,
                    "cpu_percent": process.cpu_percent(interval=0.1),
                    "num_threads": process.num_threads(),
                    "open_files": len(process.open_files())
                }
                self.memory_snapshots.append(snapshot)
                
                # 限制快照数量
                if len(self.memory_snapshots) > 30:
                    self.memory_snapshots = self.memory_snapshots[-30:]
                
                # 检测内存泄漏
                if len(self.memory_snapshots) >= 15:
                    # 计算内存增长趋势
                    memory_values = [s['memory'] for s in self.memory_snapshots]
                    rss_values = [s['rss'] for s in self.memory_snapshots]
                    vms_values = [s['vms'] for s in self.memory_snapshots]
                    
                    # 计算增长趋势
                    increasing_count = 0
                    total_growth = 0
                    for i in range(len(memory_values)-1):
                        if memory_values[i+1] > memory_values[i]:
                            increasing_count += 1
                            total_growth += memory_values[i+1] - memory_values[i]
                    
                    # 计算增长比例
                    growth_ratio = increasing_count / (len(memory_values) - 1)
                    avg_growth = total_growth / (len(memory_values) - 1) if len(memory_values) > 1 else 0
                    
                    # 计算内存使用波动率
                    memory_std = self._calculate_standard_deviation(memory_values)
                    memory_cv = memory_std / (sum(memory_values) / len(memory_values)) if memory_values else 0
                    
                    # 检测内存泄漏
                    if growth_ratio > 0.75 and avg_growth > 3:
                        # 75%以上的时间内存都在增长，且平均每次增长超过3MB
                        leak_severity = self._assess_leak_severity(avg_growth, growth_ratio, memory_cv)
                        
                        # 生成详细的内存泄漏报告
                        report = self._generate_leak_report(leak_severity, avg_growth, growth_ratio, memory_cv)
                        logger.warning(report)
                        
                        # 记录内存泄漏告警（通过 monitoring 模块记录）
                        alert = {
                            "id": len(self.alerts) + 1 if hasattr(self, 'alerts') else 1,
                            "timestamp": datetime.now().isoformat(),
                            "metric": "memory_leak",
                            "value": avg_growth,
                            "threshold": 3,
                            "status": "active",
                            "severity": leak_severity,
                            "details": report
                        }
                        # 告警通过 monitoring 模块统一处理
                    
                    # 检测内存使用峰值
                    current_peak = max(memory_values)
                    if current_peak > self.peak_memory / (1024 * 1024) * 1.1:
                        # 内存使用峰值增长超过10%
                        logger.warning(f"内存使用峰值增长: 当前峰值={current_peak:.2f}MB, 历史峰值={self.peak_memory / (1024 * 1024):.2f}MB")
                        self.peak_memory = current_peak * 1024 * 1024
        except Exception as e:
            logger.error("检测内存泄漏失败: %s", e)
    
    def _calculate_standard_deviation(self, values):
        """计算标准差"""
        if not values:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
    
    def _assess_leak_severity(self, avg_growth, growth_ratio, memory_cv):
        """评估内存泄漏的严重程度"""
        severity = "低"
        if avg_growth > 10 and growth_ratio > 0.9:
            severity = "严重"
        elif avg_growth > 5 and growth_ratio > 0.8:
            severity = "中高"
        elif avg_growth > 3 and growth_ratio > 0.75:
            severity = "中等"
        return severity
    
    def _generate_leak_report(self, severity, avg_growth, growth_ratio, memory_cv):
        """生成内存泄漏报告"""
        report = f"""可能存在内存泄漏:
严重程度: {severity}
平均增长率: {avg_growth:.2f}MB/次
增长比例: {growth_ratio:.2f}
内存使用波动率: {memory_cv:.2f}
建议: {self._get_leak_recommendation(severity)}
"""
        return report
    
    def _get_leak_recommendation(self, severity):
        """获取内存泄漏建议"""
        if severity == "严重":
            return "立即检查代码，可能存在严重的内存泄漏问题，建议重启服务"
        elif severity == "中高":
            return "检查最近的代码变更，可能存在内存泄漏，建议优化内存使用"
        elif severity == "中等":
            return "监控内存使用情况，可能存在轻微的内存泄漏"
        else:
            return "继续监控内存使用情况"
    
    @property
    def alerts(self):
        """获取告警列表"""
        if not hasattr(self, '_alerts'):
            self._alerts = []
        return self._alerts
    
    def get_current_memory_usage(self) -> Optional[float]:
        """获取当前内存使用情况
        
        Returns:
            当前内存使用量（MB）
        """
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return memory_info.rss / (1024 * 1024)  # 转换为MB
        except Exception as e:
            logger.error("获取内存使用失败: %s", e)
            return None
    
    def get_memory_usage_history(self) -> list:
        """获取内存使用历史
        
        Returns:
            内存使用历史列表
        """
        return self.memory_usage_history
    
    def get_recent_memory_history(self, hours: int = 1) -> list:
        """获取最近几小时的内存使用历史
        
        Args:
            hours: 小时数
            
        Returns:
            最近几小时的内存使用历史
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [h for h in self.memory_usage_history if datetime.fromisoformat(h['timestamp']) >= cutoff_time]
    
    def get_peak_memory(self) -> float:
        """获取峰值内存使用
        
        Returns:
            峰值内存使用量（MB）
        """
        return self.peak_memory / (1024 * 1024)  # 转换为MB
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """获取内存使用摘要
        
        Returns:
            内存使用摘要
        """
        current = self.get_current_memory_usage()
        peak = self.get_peak_memory()
        
        return {
            "current": current,
            "peak": peak,
            "threshold": self.memory_threshold,
            "optimization_interval": self.optimization_interval,
            "uptime": (datetime.now() - self.start_time).total_seconds(),
            "history_count": len(self.memory_usage_history),
            "last_optimization": self.last_optimization_time.isoformat()
        }


# 全局内存优化器实例
memory_optimizer = MemoryOptimizer()

def get_memory_optimizer() -> MemoryOptimizer:
    """获取内存优化器实例
    
    Returns:
        MemoryOptimizer实例
    """
    return memory_optimizer
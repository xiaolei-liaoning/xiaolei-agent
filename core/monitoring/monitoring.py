"""监控和指标收集模块

实现系统监控和性能指标收集
"""

# ⚠️ DEPRECATED: 此模块未被核心流程使用


import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List

import psutil

logger = logging.getLogger(__name__)


class MonitoringManager:
    """监控管理器"""

    def __init__(self, interval: int = 5):
        self.interval = interval
        self.metrics = {
            "cpu": [],
            "memory": [],
            "disk": [],
            "network": [],
            "tasks": [],
            "responses": [],
            "agents": [],
            "system": [],
            "errors": [],
            "alarms": [],
        }
        self._running = False
        self._thread = None
        # 日志文件配置
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
        )
        self.log_file = os.path.join(data_dir, "monitoring.log")
        self.alarm_file = os.path.join(data_dir, "alarms.json")
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        # 告警配置
        self.alarm_config = {
            "cpu": {
                "threshold": 80.0,  # CPU使用率阈值
                "duration": 30,  # 持续时间（秒）
                "enabled": True,
            },
            "memory": {
                "threshold": 90.0,  # 内存使用率阈值
                "duration": 30,  # 持续时间（秒）
                "enabled": True,
            },
            "disk": {
                "threshold": 95.0,  # 磁盘使用率阈值
                "duration": 30,  # 持续时间（秒）
                "enabled": True,
            },
            "tasks": {
                "failure_rate": 0.3,  # 任务失败率阈值
                "window": 10,  # 统计窗口（任务数）
                "enabled": True,
            },
            "responses": {
                "error_rate": 0.3,  # 响应错误率阈值
                "window": 10,  # 统计窗口（响应数）
                "enabled": True,
            },
        }

        # 告警状态
        self.alarm_status = {
            "cpu": False,
            "memory": False,
            "disk": False,
            "tasks": False,
            "responses": False,
        }

        # 告警计数
        self.alarm_counters = {
            "cpu": 0,
            "memory": 0,
            "disk": 0,
            "tasks": 0,
            "responses": 0,
        }

        logger.info("监控管理器初始化完成")

    def start(self):
        """启动监控"""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._collect_metrics, daemon=True)
            self._thread.start()
            logger.info("监控已启动")

    def stop(self):
        """停止监控"""
        if self._running:
            self._running = False
            if self._thread:
                self._thread.join()
            logger.info("监控已停止")

    def _collect_metrics(self):
        """收集指标"""
        while self._running:
            try:
                # 收集系统指标
                self._collect_system_metrics()
                # 检测告警
                self._check_alarms()
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"收集指标失败: {e}")
                time.sleep(self.interval)

    def _collect_system_metrics(self):
        """收集系统指标"""
        timestamp = time.time()

        # CPU 使用率
        cpu_percent = psutil.cpu_percent(interval=0.1)
        self.metrics["cpu"].append({"timestamp": timestamp, "value": cpu_percent})

        # 内存使用率
        memory = psutil.virtual_memory()
        self.metrics["memory"].append(
            {
                "timestamp": timestamp,
                "value": memory.percent,
                "available": memory.available,
                "total": memory.total,
            }
        )

        # 磁盘使用率
        disk = psutil.disk_usage("/")
        self.metrics["disk"].append(
            {
                "timestamp": timestamp,
                "value": disk.percent,
                "free": disk.free,
                "total": disk.total,
            }
        )

        # 网络流量
        net_io = psutil.net_io_counters()
        self.metrics["network"].append(
            {
                "timestamp": timestamp,
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
            }
        )

        # 限制每个指标的长度
        for key in self.metrics:
            if len(self.metrics[key]) > 1000:  # 保留1000个数据点
                self.metrics[key] = self.metrics[key][-1000:]

    def record_task(self, task_type: str, status: str, duration: float):
        """记录任务执行情况

        Args:
            task_type: 任务类型
            status: 任务状态
            duration: 执行时间
        """
        timestamp = time.time()
        self.metrics["tasks"].append(
            {
                "timestamp": timestamp,
                "task_type": task_type,
                "status": status,
                "duration": duration,
            }
        )
        self._log_event("task", f"Task {task_type} {status} in {duration:.2f}s")

    def record_response(self, endpoint: str, status_code: int, duration: float):
        """记录响应情况

        Args:
            endpoint: 端点
            status_code: 状态码
            duration: 响应时间
        """
        timestamp = time.time()
        self.metrics["responses"].append(
            {
                "timestamp": timestamp,
                "endpoint": endpoint,
                "status_code": status_code,
                "duration": duration,
            }
        )
        self._log_event(
            "response", f"Endpoint {endpoint} {status_code} in {duration:.2f}s"
        )

    def record_agent_status(self, agent_id: str, status: str, active_tasks: int):
        """记录Agent状态

        Args:
            agent_id: Agent ID
            status: 状态
            active_tasks: 活跃任务数
        """
        timestamp = time.time()
        self.metrics["agents"].append(
            {
                "timestamp": timestamp,
                "agent_id": agent_id,
                "status": status,
                "active_tasks": active_tasks,
            }
        )

    def record_system_event(self, event_type: str, message: str):
        """记录系统事件

        Args:
            event_type: 事件类型
            message: 事件消息
        """
        timestamp = time.time()
        self.metrics["system"].append(
            {"timestamp": timestamp, "event_type": event_type, "message": message}
        )
        self._log_event("system", f"{event_type}: {message}")

    def record_error(self, error_type: str, message: str, traceback: str = None):
        """记录错误事件

        Args:
            error_type: 错误类型
            message: 错误消息
            traceback: 错误堆栈
        """
        timestamp = time.time()
        self.metrics["errors"].append(
            {
                "timestamp": timestamp,
                "error_type": error_type,
                "message": message,
                "traceback": traceback,
            }
        )
        self._log_event("error", f"{error_type}: {message}")

    def _check_alarms(self):
        """检测告警"""
        timestamp = time.time()

        # 检测CPU告警
        if self.alarm_config["cpu"]["enabled"] and self.metrics["cpu"]:
            recent_cpu = [
                m["value"]
                for m in self.metrics["cpu"][
                    -int(self.alarm_config["cpu"]["duration"] / self.interval) :
                ]
            ]
            if recent_cpu and all(
                cpu > self.alarm_config["cpu"]["threshold"] for cpu in recent_cpu
            ):
                if not self.alarm_status["cpu"]:
                    self._trigger_alarm(
                        "cpu",
                        f"CPU使用率超过阈值 {self.alarm_config['cpu']['threshold']}%",
                        {
                            "threshold": self.alarm_config["cpu"]["threshold"],
                            "current_value": recent_cpu[-1],
                            "duration": self.alarm_config["cpu"]["duration"],
                        },
                    )
            else:
                if self.alarm_status["cpu"]:
                    self._clear_alarm("cpu")

        # 检测内存告警
        if self.alarm_config["memory"]["enabled"] and self.metrics["memory"]:
            recent_memory = [
                m["value"]
                for m in self.metrics["memory"][
                    -int(self.alarm_config["memory"]["duration"] / self.interval) :
                ]
            ]
            if recent_memory and all(
                mem > self.alarm_config["memory"]["threshold"] for mem in recent_memory
            ):
                if not self.alarm_status["memory"]:
                    self._trigger_alarm(
                        "memory",
                        f"内存使用率超过阈值 {self.alarm_config['memory']['threshold']}%",
                        {
                            "threshold": self.alarm_config["memory"]["threshold"],
                            "current_value": recent_memory[-1],
                            "available": self.metrics["memory"][-1]["available"],
                        },
                    )
            else:
                if self.alarm_status["memory"]:
                    self._clear_alarm("memory")

        # 检测磁盘告警
        if self.alarm_config["disk"]["enabled"] and self.metrics["disk"]:
            current_disk = self.metrics["disk"][-1]["value"]
            if current_disk > self.alarm_config["disk"]["threshold"]:
                if not self.alarm_status["disk"]:
                    self._trigger_alarm(
                        "disk",
                        f"磁盘使用率超过阈值 {self.alarm_config['disk']['threshold']}%",
                        {
                            "threshold": self.alarm_config["disk"]["threshold"],
                            "current_value": current_disk,
                            "free": self.metrics["disk"][-1]["free"],
                        },
                    )
            else:
                if self.alarm_status["disk"]:
                    self._clear_alarm("disk")

        # 检测任务失败率告警
        if self.alarm_config["tasks"]["enabled"] and self.metrics["tasks"]:
            recent_tasks = self.metrics["tasks"][
                -self.alarm_config["tasks"]["window"] :
            ]
            if len(recent_tasks) >= self.alarm_config["tasks"]["window"]:
                failure_rate = sum(
                    1 for t in recent_tasks if t["status"] == "failed"
                ) / len(recent_tasks)
                if failure_rate > self.alarm_config["tasks"]["failure_rate"]:
                    if not self.alarm_status["tasks"]:
                        self._trigger_alarm(
                            "tasks",
                            f"任务失败率超过阈值 {self.alarm_config['tasks']['failure_rate']*100}%",
                            {
                                "threshold": self.alarm_config["tasks"]["failure_rate"],
                                "current_value": failure_rate,
                                "window": self.alarm_config["tasks"]["window"],
                            },
                        )
                else:
                    if self.alarm_status["tasks"]:
                        self._clear_alarm("tasks")

        # 检测响应错误率告警
        if self.alarm_config["responses"]["enabled"] and self.metrics["responses"]:
            recent_responses = self.metrics["responses"][
                -self.alarm_config["responses"]["window"] :
            ]
            if len(recent_responses) >= self.alarm_config["responses"]["window"]:
                error_rate = sum(
                    1 for r in recent_responses if r["status_code"] >= 400
                ) / len(recent_responses)
                if error_rate > self.alarm_config["responses"]["error_rate"]:
                    if not self.alarm_status["responses"]:
                        self._trigger_alarm(
                            "responses",
                            f"响应错误率超过阈值 {self.alarm_config['responses']['error_rate']*100}%",
                            {
                                "threshold": self.alarm_config["responses"][
                                    "error_rate"
                                ],
                                "current_value": error_rate,
                                "window": self.alarm_config["responses"]["window"],
                            },
                        )
                else:
                    if self.alarm_status["responses"]:
                        self._clear_alarm("responses")

    def _trigger_alarm(self, alarm_type: str, message: str, details: dict):
        """触发告警

        Args:
            alarm_type: 告警类型
            message: 告警消息
            details: 告警详情
        """
        timestamp = time.time()
        alarm = {
            "timestamp": timestamp,
            "type": alarm_type,
            "message": message,
            "details": details,
            "status": "triggered",
        }

        self.metrics["alarms"].append(alarm)
        self.alarm_status[alarm_type] = True
        self.alarm_counters[alarm_type] += 1

        # 记录告警到日志
        self._log_event("alarm", f"[{alarm_type.upper()}] {message}")

        # 发送告警通知
        self._send_alarm_notification(alarm)

        # 保存告警记录
        self._save_alarms()

        logger.warning(f"告警触发: {alarm_type} - {message}")

    def _clear_alarm(self, alarm_type: str):
        """清除告警

        Args:
            alarm_type: 告警类型
        """
        timestamp = time.time()
        alarm = {
            "timestamp": timestamp,
            "type": alarm_type,
            "message": f"{alarm_type} 告警已清除",
            "status": "cleared",
        }

        self.metrics["alarms"].append(alarm)
        self.alarm_status[alarm_type] = False

        # 记录告警清除到日志
        self._log_event("alarm", f"[{alarm_type.upper()}] 告警已清除")

        # 发送告警清除通知
        self._send_alarm_notification(alarm)

        # 保存告警记录
        self._save_alarms()

        logger.info(f"告警清除: {alarm_type}")

    def _send_alarm_notification(self, alarm: dict):
        """发送告警通知

        Args:
            alarm: 告警信息
        """
        # 这里可以添加邮件、短信、消息推送等通知方式
        # 目前只记录到日志
        notification_message = f"告警通知: {alarm['type']} - {alarm['message']}"
        if "details" in alarm:
            notification_message += f" - 详情: {alarm['details']}"

        logger.info(notification_message)

    def _save_alarms(self):
        """保存告警记录"""
        try:
            with open(self.alarm_file, "w") as f:
                json.dump(
                    {
                        "timestamp": time.time(),
                        "alarms": self.metrics["alarms"],
                        "alarm_status": self.alarm_status,
                        "alarm_counters": self.alarm_counters,
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"保存告警记录失败: {e}")

    def _log_event(self, event_type: str, message: str):
        """记录事件到日志文件

        Args:
            event_type: 事件类型
            message: 事件消息
        """
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{event_type.upper()}] {message}\n"

        try:
            with open(self.log_file, "a") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"写入日志失败: {e}")

    def get_metrics(
        self, metric_type: str = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取指标

        Args:
            metric_type: 指标类型
            limit: 限制数量

        Returns:
            指标列表
        """
        if metric_type:
            return self.metrics.get(metric_type, [])[-limit:]
        return self.metrics

    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要

        Returns:
            指标摘要
        """
        summary = {}

        # CPU 摘要
        if self.metrics["cpu"]:
            cpu_values = [
                m["value"] for m in self.metrics["cpu"][-60:]
            ]  # 最近60个数据点
            summary["cpu"] = {
                "average": sum(cpu_values) / len(cpu_values),
                "max": max(cpu_values),
                "min": min(cpu_values),
            }

        # 内存摘要
        if self.metrics["memory"]:
            memory_values = [m["value"] for m in self.metrics["memory"][-60:]]
            summary["memory"] = {
                "average": sum(memory_values) / len(memory_values),
                "max": max(memory_values),
                "min": min(memory_values),
                "available": self.metrics["memory"][-1]["available"],
            }

        # 磁盘摘要
        if self.metrics["disk"]:
            summary["disk"] = {
                "usage": self.metrics["disk"][-1]["value"],
                "free": self.metrics["disk"][-1]["free"],
                "total": self.metrics["disk"][-1]["total"],
            }

        # 任务摘要
        if self.metrics["tasks"]:
            recent_tasks = self.metrics["tasks"][-100:]
            success_count = sum(1 for t in recent_tasks if t["status"] == "completed")
            failure_count = sum(1 for t in recent_tasks if t["status"] == "failed")
            avg_duration = (
                sum(t["duration"] for t in recent_tasks) / len(recent_tasks)
                if recent_tasks
                else 0
            )

            summary["tasks"] = {
                "total": len(recent_tasks),
                "success": success_count,
                "failure": failure_count,
                "avg_duration": avg_duration,
            }

        # 响应摘要
        if self.metrics["responses"]:
            recent_responses = self.metrics["responses"][-100:]
            success_count = sum(
                1 for r in recent_responses if 200 <= r["status_code"] < 300
            )
            error_count = sum(1 for r in recent_responses if r["status_code"] >= 400)
            avg_duration = (
                sum(r["duration"] for r in recent_responses) / len(recent_responses)
                if recent_responses
                else 0
            )

            summary["responses"] = {
                "total": len(recent_responses),
                "success": success_count,
                "error": error_count,
                "avg_duration": avg_duration,
            }

        return summary

    def save_metrics(self, file_path: str = None):
        """保存指标到文件

        Args:
            file_path: 文件路径
        """
        if file_path is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
            )
            file_path = os.path.join(data_dir, "metrics.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        try:
            with open(file_path, "w") as f:
                json.dump(
                    {
                        "timestamp": time.time(),
                        "metrics": self.metrics,
                        "summary": self.get_summary(),
                    },
                    f,
                    indent=2,
                )
            logger.info(f"指标已保存到 {file_path}")
        except Exception as e:
            logger.error(f"保存指标失败: {e}")

    def load_metrics(self, file_path: str = None):
        """从文件加载指标

        Args:
            file_path: 文件路径
        """
        if file_path is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
            )
            file_path = os.path.join(data_dir, "metrics.json")
        try:
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    data = json.load(f)
                    self.metrics = data.get("metrics", self.metrics)
                logger.info(f"指标已从 {file_path} 加载")
        except Exception as e:
            logger.error(f"加载指标失败: {e}")

    def get_alarm_status(self) -> Dict[str, bool]:
        """获取告警状态

        Returns:
            告警状态字典
        """
        return self.alarm_status

    def get_alarm_counters(self) -> Dict[str, int]:
        """获取告警计数

        Returns:
            告警计数字典
        """
        return self.alarm_counters

    def get_recent_alarms(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的告警

        Args:
            limit: 限制数量

        Returns:
            告警列表
        """
        return self.metrics["alarms"][-limit:]

    def configure_alarm(self, alarm_type: str, **kwargs):
        """配置告警

        Args:
            alarm_type: 告警类型
            **kwargs: 告警配置参数
        """
        if alarm_type in self.alarm_config:
            for key, value in kwargs.items():
                if key in self.alarm_config[alarm_type]:
                    self.alarm_config[alarm_type][key] = value
            logger.info(
                f"告警配置已更新: {alarm_type} = {self.alarm_config[alarm_type]}"
            )
        else:
            logger.error(f"未知的告警类型: {alarm_type}")

    def enable_alarm(self, alarm_type: str, enabled: bool):
        """启用或禁用告警

        Args:
            alarm_type: 告警类型
            enabled: 是否启用
        """
        if alarm_type in self.alarm_config:
            self.alarm_config[alarm_type]["enabled"] = enabled
            logger.info(f"告警 {alarm_type} 已{'启用' if enabled else '禁用'}")
        else:
            logger.error(f"未知的告警类型: {alarm_type}")


# 全局监控管理器实例
monitoring_manager = MonitoringManager()

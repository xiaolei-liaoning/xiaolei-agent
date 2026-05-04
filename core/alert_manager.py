#!/usr/bin/env python3
"""
告警管理器：处理系统各种异常的告警通知
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """告警类型"""
    # 系统资源
    MEMORY_PERCENT = "memory_percent"
    MEMORY_USED = "memory_used"
    CPU_PERCENT = "cpu_percent"
    DISK_USAGE = "disk_usage"
    # 响应性能
    RESPONSE_TIME = "response_time"
    REQUEST_RATE = "request_rate"
    ERROR_RATE = "error_rate"
    # 数据库
    DB_CONNECTION_COUNT = "db_connection_count"
    DB_QUERY_TIME = "db_query_time"
    # 缓存
    CACHE_HIT_RATE = "cache_hit_rate"
    CACHE_SIZE = "cache_size"
    # Agent系统
    AGENT_QUEUE_LENGTH = "agent_queue_length"
    AGENT_TASK_TIMEOUT = "agent_task_timeout"
    AGENT_ERROR_COUNT = "agent_error_count"
    # 网络
    NETWORK_LATENCY = "network_latency"
    NETWORK_ERRORS = "network_errors"
    # 业务
    USER_ACTIVITY_DROP = "user_activity_drop"
    RAG_RECALL_RATE = "rag_recall_rate"
    SKILL_MATCH_RATE = "skill_match_rate"


class AlertManager:
    """增强版告警管理器"""
    
    def __init__(self):
        """初始化告警管理器"""
        self.alerts = []
        self.alert_history = []
        
        # 增强的告警阈值配置（支持不同级别的阈值）
        self.alert_thresholds = {
            # 系统资源
            "memory_percent": {
                "warning": 75,
                "error": 85,
                "critical": 95
            },
            "memory_used": {
                "warning": 0,
                "error": 0,
                "critical": 0
            },
            "cpu_percent": {
                "warning": 70,
                "error": 85,
                "critical": 95
            },
            "disk_usage": {
                "warning": 75,
                "error": 85,
                "critical": 95
            },
            # 响应性能
            "response_time": {
                "warning": 1000,
                "error": 3000,
                "critical": 5000
            },
            "request_rate": {
                "warning": 0,
                "error": 0,
                "critical": 0
            },
            "error_rate": {
                "warning": 1,
                "error": 5,
                "critical": 10
            },
            # 数据库
            "db_connection_count": {
                "warning": 50,
                "error": 80,
                "critical": 100
            },
            "db_query_time": {
                "warning": 100,
                "error": 500,
                "critical": 1000
            },
            # 缓存
            "cache_hit_rate": {
                "warning": 80,
                "error": 60,
                "critical": 40
            },
            "cache_size": {
                "warning": 400,
                "error": 450,
                "critical": 490
            },
            # Agent系统
            "agent_queue_length": {
                "warning": 20,
                "error": 50,
                "critical": 100
            },
            "agent_task_timeout": {
                "warning": 5,
                "error": 10,
                "critical": 20
            },
            "agent_error_count": {
                "warning": 3,
                "error": 10,
                "critical": 20
            },
            # 网络
            "network_latency": {
                "warning": 100,
                "error": 300,
                "critical": 500
            },
            "network_errors": {
                "warning": 5,
                "error": 20,
                "critical": 50
            },
            # 业务
            "user_activity_drop": {
                "warning": 20,
                "error": 40,
                "critical": 60
            },
            "rag_recall_rate": {
                "warning": 70,
                "error": 50,
                "critical": 30
            },
            "skill_match_rate": {
                "warning": 70,
                "error": 50,
                "critical": 30
            }
        }
        
        # 告警方向：对于某些指标，低于阈值才告警
        self.threshold_direction = {
            "cache_hit_rate": "below",
            "rag_recall_rate": "below",
            "skill_match_rate": "below"
        }
        
        self.notification_methods = []
        self.silence_periods = {
            "critical": 60,
            "error": 120,
            "warning": 300,
            "info": 600
        }
        self.last_alert_time = {}
        self.alert_counter = 0
        
        logger.info("增强版告警管理器初始化完成")
    
    def add_notification_method(self, method: Callable):
        """添加通知方法"""
        self.notification_methods.append(method)
        logger.info(f"添加通知方法: {method.__name__}")
    
    def check_alert(self, metric_name: str, value: float) -> Optional[Dict]:
        """检查是否需要告警（支持多级告警）"""
        if metric_name not in self.alert_thresholds:
            return None
        
        thresholds = self.alert_thresholds[metric_name]
        direction = self.threshold_direction.get(metric_name, "above")
        
        # 确定告警级别
        alert_level = None
        
        if direction == "above":
            if value >= thresholds.get("critical", float('inf')):
                alert_level = AlertLevel.CRITICAL
            elif value >= thresholds.get("error", float('inf')):
                alert_level = AlertLevel.ERROR
            elif value >= thresholds.get("warning", float('inf')):
                alert_level = AlertLevel.WARNING
        else:
            if value <= thresholds.get("critical", -float('inf')):
                alert_level = AlertLevel.CRITICAL
            elif value <= thresholds.get("error", -float('inf')):
                alert_level = AlertLevel.ERROR
            elif value <= thresholds.get("warning", -float('inf')):
                alert_level = AlertLevel.WARNING
        
        if alert_level is None:
            return None
        
        # 检查是否在静默期
        current_time = datetime.now().timestamp()
        silence_key = f"{metric_name}_{alert_level.value}"
        
        if silence_key in self.last_alert_time:
            silence_period = self.silence_periods.get(alert_level.value, 300)
            if current_time - self.last_alert_time[silence_key] < silence_period:
                return None
        
        # 创建告警
        self.alert_counter += 1
        alert = {
            "id": self.alert_counter,
            "timestamp": datetime.now().isoformat(),
            "metric": metric_name,
            "value": value,
            "threshold": thresholds.get(alert_level.value, 0),
            "level": alert_level.value,
            "status": "active",
            "direction": direction
        }
        
        self.alerts.append(alert)
        self.alert_history.append(alert)
        self.last_alert_time[silence_key] = current_time
        
        # 限制告警历史数量
        if len(self.alert_history) > 10000:
            self.alert_history = self.alert_history[-10000:]
        
        # 限制活跃告警数量
        if len(self.alerts) > 1000:
            self.alerts = self.alerts[-1000:]
        
        return alert
    
    async def send_alert(self, alert: Dict):
        """发送告警通知"""
        try:
            # 构建告警消息
            message = self._format_alert_message(alert)
            logger.warning(f"发送{alert['level']}级别告警: {message}")
            
            # 通过所有通知方法发送告警
            for method in self.notification_methods:
                try:
                    await method(message, alert)
                except Exception as e:
                    logger.error(f"发送告警失败: {e}")
        except Exception as e:
            logger.error(f"处理告警失败: {e}")
    
    def _format_alert_message(self, alert: Dict) -> str:
        """格式化告警消息"""
        metric_names = {
            "memory_percent": "内存使用率",
            "memory_used": "内存使用量",
            "cpu_percent": "CPU使用率",
            "disk_usage": "磁盘使用率",
            "response_time": "响应时间",
            "request_rate": "请求速率",
            "error_rate": "错误率",
            "db_connection_count": "数据库连接数",
            "db_query_time": "数据库查询时间",
            "cache_hit_rate": "缓存命中率",
            "cache_size": "缓存大小",
            "agent_queue_length": "Agent队列长度",
            "agent_task_timeout": "Agent任务超时数",
            "agent_error_count": "Agent错误数",
            "network_latency": "网络延迟",
            "network_errors": "网络错误数",
            "user_activity_drop": "用户活跃度下降",
            "rag_recall_rate": "RAG召回率",
            "skill_match_rate": "技能匹配率"
        }
        
        units = {
            "memory_percent": "%",
            "memory_used": "MB",
            "cpu_percent": "%",
            "disk_usage": "%",
            "response_time": "ms",
            "request_rate": "req/s",
            "error_rate": "%",
            "db_connection_count": "个",
            "db_query_time": "ms",
            "cache_hit_rate": "%",
            "cache_size": "个",
            "agent_queue_length": "个",
            "agent_task_timeout": "次",
            "agent_error_count": "次",
            "network_latency": "ms",
            "network_errors": "次",
            "user_activity_drop": "%",
            "rag_recall_rate": "%",
            "skill_match_rate": "%"
        }
        
        level_emojis = {
            "critical": "🔴",
            "error": "🟠",
            "warning": "🟡",
            "info": "🟢"
        }
        
        metric_name = metric_names.get(alert["metric"], alert["metric"])
        unit = units.get(alert["metric"], "")
        emoji = level_emojis.get(alert["level"], "")
        direction_text = "超过" if alert["direction"] == "above" else "低于"
        
        return f"{emoji}【{alert['level'].upper()}告警】{metric_name}异常: 当前值 {alert['value']:.2f}{unit}，{direction_text}阈值 {alert['threshold']}{unit}"
    
    def get_active_alerts(self, level: Optional[str] = None) -> List[Dict]:
        """获取活跃告警（支持按级别过滤）"""
        active_alerts = [alert for alert in self.alerts if alert["status"] == "active"]
        if level:
            active_alerts = [alert for alert in active_alerts if alert["level"] == level]
        return active_alerts
    
    def get_alert_history(self, limit: int = 100, level: Optional[str] = None) -> List[Dict]:
        """获取告警历史（支持按级别过滤）"""
        history = self.alert_history
        if level:
            history = [alert for alert in history if alert["level"] == level]
        return history[-limit:]
    
    def resolve_alert(self, alert_id: int):
        """解决告警"""
        for alert in self.alerts:
            if alert["id"] == alert_id:
                alert["status"] = "resolved"
                alert["resolved_at"] = datetime.now().isoformat()
                logger.info(f"告警已解决: {alert_id}")
                break
    
    def resolve_all_alerts(self):
        """解决所有活跃告警"""
        count = 0
        for alert in self.alerts:
            if alert["status"] == "active":
                alert["status"] = "resolved"
                alert["resolved_at"] = datetime.now().isoformat()
                count += 1
        logger.info(f"已解决 {count} 个活跃告警")
    
    def set_threshold(self, metric_name: str, level: str, threshold: float):
        """设置告警阈值（支持设置不同级别的阈值）"""
        if metric_name in self.alert_thresholds:
            if level in self.alert_thresholds[metric_name]:
                self.alert_thresholds[metric_name][level] = threshold
                logger.info(f"设置{metric_name}的{level}级别告警阈值为: {threshold}")
    
    def get_thresholds(self) -> Dict[str, Any]:
        """获取所有告警阈值"""
        return self.alert_thresholds
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取告警统计信息"""
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        active_counts = {}
        today_counts = {}
        
        for level in ["critical", "error", "warning", "info"]:
            active_counts[level] = len([a for a in self.alerts if a["status"] == "active" and a["level"] == level])
            today_counts[level] = len([a for a in self.alert_history if datetime.fromisoformat(a["timestamp"]) >= today and a["level"] == level])
        
        return {
            "active_alerts": len(self.get_active_alerts()),
            "active_by_level": active_counts,
            "today_by_level": today_counts,
            "total_history": len(self.alert_history)
        }

# 通知方法实现
async def console_notification(message: str, alert: Dict):
    """控制台通知"""
    print(f"[告警通知] {message}")


async def log_notification(message: str, alert: Dict):
    """日志通知"""
    log_levels = {
        "critical": logger.critical,
        "error": logger.error,
        "warning": logger.warning,
        "info": logger.info
    }
    log_func = log_levels.get(alert["level"], logger.warning)
    log_func(message)


async def file_notification(message: str, alert: Dict):
    """文件通知（写入告警日志文件）"""
    try:
        import os
        log_dir = "data"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "alerts.log")
        
        with open(log_file, "a", encoding="utf-8") as f:
            timestamp = datetime.now().isoformat()
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        logger.error(f"写入告警文件失败: {e}")


async def email_notification(message: str, alert: Dict):
    """邮件通知（可配置的SMTP）"""
    try:
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        
        smtp_server = os.getenv("SMTP_SERVER", "smtp.aoksend.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        recipients = os.getenv("ALERT_EMAILS", "").split(",")
        
        if not smtp_user or not smtp_password or not recipients:
            logger.warning("邮件通知未配置，跳过")
            return
        
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        
        msg = MIMEText(message, 'plain', 'utf-8')
        msg['From'] = Header(smtp_user)
        msg['To'] = Header(", ".join(recipients))
        msg['Subject'] = Header(f"[{alert['level'].upper()}] 系统告警通知")
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipients, msg.as_string())
        server.quit()
        
        logger.info(f"邮件通知发送成功到: {recipients}")
    except Exception as e:
        logger.error(f"发送邮件通知失败: {e}")


async def wechat_notification(message: str, alert: Dict):
    """企业微信/微信通知"""
    try:
        import os
        import requests
        from dotenv import load_dotenv
        
        load_dotenv()
        
        webhook_url = os.getenv("WECHAT_WEBHOOK", "")
        
        if not webhook_url:
            logger.warning("微信通知未配置，跳过")
            return
        
        payload = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }
        
        response = requests.post(webhook_url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("微信通知发送成功")
        else:
            logger.error(f"微信通知发送失败: {response.status_code}")
    except Exception as e:
        logger.error(f"发送微信通知失败: {e}")


async def dingtalk_notification(message: str, alert: Dict):
    """钉钉通知"""
    try:
        import os
        import requests
        from dotenv import load_dotenv
        
        load_dotenv()
        
        webhook_url = os.getenv("DINGTALK_WEBHOOK", "")
        
        if not webhook_url:
            logger.warning("钉钉通知未配置，跳过")
            return
        
        payload = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }
        
        response = requests.post(webhook_url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("钉钉通知发送成功")
        else:
            logger.error(f"钉钉通知发送失败: {response.status_code}")
    except Exception as e:
        logger.error(f"发送钉钉通知失败: {e}")


async def feishu_notification(message: str, alert: Dict):
    """飞书通知"""
    try:
        import os
        import requests
        from dotenv import load_dotenv
        
        load_dotenv()
        
        webhook_url = os.getenv("FEISHU_WEBHOOK", "")
        
        if not webhook_url:
            logger.warning("飞书通知未配置，跳过")
            return
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": message
            }
        }
        
        response = requests.post(webhook_url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("飞书通知发送成功")
        else:
            logger.error(f"飞书通知发送失败: {response.status_code}")
    except Exception as e:
        logger.error(f"发送飞书通知失败: {e}")


async def sms_notification(message: str, alert: Dict):
    """短信通知（Twilio）"""
    try:
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        
        twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        twilio_from = os.getenv("TWILIO_FROM", "")
        twilio_to = os.getenv("TWILIO_TO", "")
        
        if not all([twilio_account_sid, twilio_auth_token, twilio_from, twilio_to]):
            logger.warning("短信通知未配置，跳过")
            return
        
        from twilio.rest import Client
        
        client = Client(twilio_account_sid, twilio_auth_token)
        msg = client.messages.create(
            body=message[:1600],  # 短信长度限制
            from_=twilio_from,
            to=twilio_to
        )
        
        logger.info(f"短信通知发送成功: {msg.sid}")
    except ImportError:
        logger.warning("twilio库未安装，跳过短信通知")
    except Exception as e:
        logger.error(f"发送短信通知失败: {e}")


async def telegram_notification(message: str, alert: Dict):
    """Telegram通知"""
    try:
        import os
        import requests
        from dotenv import load_dotenv
        
        load_dotenv()
        
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        
        if not bot_token or not chat_id:
            logger.warning("Telegram通知未配置，跳过")
            return
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("Telegram通知发送成功")
        else:
            logger.error(f"Telegram通知发送失败: {response.status_code}")
    except Exception as e:
        logger.error(f"发送Telegram通知失败: {e}")


# 全局告警管理器实例
alert_manager = AlertManager()

# 注册通知方法（默认只注册控制台和日志通知，其他需要配置后才会启用）
alert_manager.add_notification_method(console_notification)
alert_manager.add_notification_method(log_notification)
alert_manager.add_notification_method(file_notification)


def setup_alert_notifications():
    """设置告警通知（根据环境变量配置启用通知方法）"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    if os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"):
        alert_manager.add_notification_method(email_notification)
        logger.info("已启用邮件通知")
    
    if os.getenv("WECHAT_WEBHOOK"):
        alert_manager.add_notification_method(wechat_notification)
        logger.info("已启用微信通知")
    
    if os.getenv("DINGTALK_WEBHOOK"):
        alert_manager.add_notification_method(dingtalk_notification)
        logger.info("已启用钉钉通知")
    
    if os.getenv("FEISHU_WEBHOOK"):
        alert_manager.add_notification_method(feishu_notification)
        logger.info("已启用飞书通知")
    
    if os.getenv("TWILIO_ACCOUNT_SID"):
        alert_manager.add_notification_method(sms_notification)
        logger.info("已启用短信通知")
    
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        alert_manager.add_notification_method(telegram_notification)
        logger.info("已启用Telegram通知")


# 导出告警管理器
def get_alert_manager() -> AlertManager:
    """获取告警管理器实例"""
    return alert_manager
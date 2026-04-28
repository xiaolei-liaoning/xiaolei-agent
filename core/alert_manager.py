#!/usr/bin/env python3
"""
告警管理器：处理内存使用异常的告警通知
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class AlertManager:
    """告警管理器"""
    
    def __init__(self):
        """初始化告警管理器"""
        self.alerts = []
        self.alert_history = []
        self.alert_thresholds = {
            "memory_percent": 90,  # 内存使用百分比阈值
            "memory_used": 0,  # 内存使用量阈值（MB）
            "cpu_percent": 80,  # CPU使用百分比阈值
            "response_time": 5000  # 响应时间阈值（ms）
        }
        self.notification_methods = []
        self.silence_period = 300  # 告警静默期（秒）
        self.last_alert_time = {}
        logger.info("告警管理器初始化完成")
    
    def add_notification_method(self, method):
        """添加通知方法"""
        self.notification_methods.append(method)
        logger.info(f"添加通知方法: {method.__name__}")
    
    def check_alert(self, metric_name: str, value: float) -> Optional[Dict]:
        """检查是否需要告警"""
        if metric_name not in self.alert_thresholds:
            return None
        
        threshold = self.alert_thresholds[metric_name]
        if value > threshold:
            # 检查是否在静默期
            current_time = datetime.now().timestamp()
            if metric_name in self.last_alert_time:
                if current_time - self.last_alert_time[metric_name] < self.silence_period:
                    return None
            
            # 创建告警
            alert = {
                "id": len(self.alerts) + 1,
                "timestamp": datetime.now().isoformat(),
                "metric": metric_name,
                "value": value,
                "threshold": threshold,
                "status": "active"
            }
            
            self.alerts.append(alert)
            self.alert_history.append(alert)
            self.last_alert_time[metric_name] = current_time
            
            # 限制告警历史数量
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-1000:]
            
            return alert
        
        return None
    
    async def send_alert(self, alert: Dict):
        """发送告警通知"""
        try:
            # 构建告警消息
            message = self._format_alert_message(alert)
            logger.warning(f"发送告警: {message}")
            
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
            "response_time": "响应时间"
        }
        
        metric_name = metric_names.get(alert["metric"], alert["metric"])
        unit = "%" if alert["metric"] in ["memory_percent", "cpu_percent"] else "MB" if alert["metric"] == "memory_used" else "ms"
        
        return f"【告警】{metric_name}异常: 当前值 {alert['value']:.2f}{unit}，超过阈值 {alert['threshold']}{unit}"
    
    def get_active_alerts(self) -> List[Dict]:
        """获取活跃告警"""
        return [alert for alert in self.alerts if alert["status"] == "active"]
    
    def get_alert_history(self) -> List[Dict]:
        """获取告警历史"""
        return self.alert_history
    
    def resolve_alert(self, alert_id: int):
        """解决告警"""
        for alert in self.alerts:
            if alert["id"] == alert_id:
                alert["status"] = "resolved"
                alert["resolved_at"] = datetime.now().isoformat()
                logger.info(f"告警已解决: {alert_id}")
                break
    
    def set_threshold(self, metric_name: str, threshold: float):
        """设置告警阈值"""
        if metric_name in self.alert_thresholds:
            self.alert_thresholds[metric_name] = threshold
            logger.info(f"设置{metric_name}告警阈值为: {threshold}")
    
    def get_thresholds(self) -> Dict[str, float]:
        """获取告警阈值"""
        return self.alert_thresholds

# 默认通知方法
async def console_notification(message: str, alert: Dict):
    """控制台通知"""
    print(f"[告警通知] {message}")

async def log_notification(message: str, alert: Dict):
    """日志通知"""
    logger.warning(message)

async def email_notification(message: str, alert: Dict):
    """邮件通知"""
    try:
        # 使用AOKSend免费SMTP服务
        logger.info(f"发送邮件通知: {message}")
        
        # 实际邮件发送代码
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        
        # AOKSend SMTP配置
        smtp_server = "smtp.aoksend.com"
        smtp_port = 587
        smtp_user = "your_email@example.com"  # 替换为您的AOKSend账户邮箱
        smtp_password = "your_password"  # 替换为您的AOKSend密码
        recipient = "recipient@example.com"  # 替换为接收告警的邮箱
        
        msg = MIMEText(message, 'plain', 'utf-8')
        msg['From'] = Header(smtp_user)
        msg['To'] = Header(recipient)
        msg['Subject'] = Header("系统告警通知")
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [recipient], msg.as_string())
        server.quit()
        
        logger.info("邮件通知发送成功")
    except Exception as e:
        logger.error(f"发送邮件通知失败: {e}")

async def sms_notification(message: str, alert: Dict):
    """短信通知"""
    try:
        # 使用Twilio短信服务
        logger.info(f"发送短信通知: {message}")
        
        # 实际短信发送代码
        # 注册Twilio账号获取以下信息：https://www.twilio.com/
        # from twilio.rest import Client
        # 
        # account_sid = "your_account_sid"  # 替换为您的Twilio账户SID
        # auth_token = "your_auth_token"  # 替换为您的Twilio认证令牌
        # client = Client(account_sid, auth_token)
        # 
        # message = client.messages.create(
        #     body=message,
        #     from_="+1234567890",  # 替换为您的Twilio号码
        #     to="+861234567890"  # 替换为接收告警的手机号
        # )
        # 
        # logger.info(f"短信通知发送成功: {message.sid}")
    except Exception as e:
        logger.error(f"发送短信通知失败: {e}")

# 全局告警管理器实例
alert_manager = AlertManager()
alert_manager.add_notification_method(console_notification)
alert_manager.add_notification_method(log_notification)
alert_manager.add_notification_method(email_notification)
alert_manager.add_notification_method(sms_notification)

# 导出告警管理器
def get_alert_manager() -> AlertManager:
    """获取告警管理器实例"""
    return alert_manager
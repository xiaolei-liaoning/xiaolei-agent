"""第三方应用监控模块"""
import time
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class AppMonitor:
    """应用监控类"""
    
    def __init__(self):
        """初始化监控器"""
        self.metrics = {}
        self.request_logs = []
        self.max_logs = 1000
    
    def start_request(self, app_name: str, action: str) -> Dict[str, Any]:
        """开始请求监控
        
        Args:
            app_name: 应用名称
            action: 操作名称
            
        Returns:
            请求上下文
        """
        if app_name not in self.metrics:
            self.metrics[app_name] = {
                'total_requests': 0,
                'success_requests': 0,
                'failed_requests': 0,
                'total_time': 0,
                'last_request': None,
                'health_status': 'healthy'
            }
        
        request_id = f"{app_name}_{int(time.time() * 1000)}"
        request_context = {
            'request_id': request_id,
            'app_name': app_name,
            'action': action,
            'start_time': time.time(),
            'start_time_str': datetime.now().isoformat()
        }
        
        return request_context
    
    def end_request(self, request_context: Dict[str, Any], success: bool, response: Dict[str, Any] = None) -> None:
        """结束请求监控
        
        Args:
            request_context: 请求上下文
            success: 是否成功
            response: 响应数据
        """
        end_time = time.time()
        duration = end_time - request_context['start_time']
        
        app_name = request_context['app_name']
        action = request_context['action']
        
        # 更新指标
        self.metrics[app_name]['total_requests'] += 1
        self.metrics[app_name]['total_time'] += duration
        self.metrics[app_name]['last_request'] = datetime.now().isoformat()
        
        if success:
            self.metrics[app_name]['success_requests'] += 1
            self.metrics[app_name]['health_status'] = 'healthy'
        else:
            self.metrics[app_name]['failed_requests'] += 1
            # 连续失败5次标记为不健康
            if self.metrics[app_name]['failed_requests'] >= 5:
                self.metrics[app_name]['health_status'] = 'unhealthy'
        
        # 记录请求日志
        log_entry = {
            'request_id': request_context['request_id'],
            'app_name': app_name,
            'action': action,
            'start_time': request_context['start_time_str'],
            'end_time': datetime.now().isoformat(),
            'duration': round(duration, 3),
            'success': success,
            'response': response
        }
        
        self.request_logs.append(log_entry)
        # 保持日志数量在限制内
        if len(self.request_logs) > self.max_logs:
            self.request_logs = self.request_logs[-self.max_logs:]
        
        logger.info(f"第三方应用请求: {app_name}.{action} - 耗时: {duration:.3f}s - 成功: {success}")
    
    def get_metrics(self, app_name: str = None) -> Dict[str, Any]:
        """获取监控指标
        
        Args:
            app_name: 应用名称，None表示所有应用
            
        Returns:
            监控指标
        """
        if app_name:
            return self.metrics.get(app_name, {})
        return self.metrics
    
    def get_request_logs(self, app_name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取请求日志
        
        Args:
            app_name: 应用名称，None表示所有应用
            limit: 限制数量
            
        Returns:
            请求日志列表
        """
        if app_name:
            logs = [log for log in self.request_logs if log['app_name'] == app_name]
        else:
            logs = self.request_logs
        
        return logs[-limit:]
    
    def get_health_status(self, app_name: str) -> str:
        """获取应用健康状态
        
        Args:
            app_name: 应用名称
            
        Returns:
            健康状态
        """
        return self.metrics.get(app_name, {}).get('health_status', 'unknown')
    
    def get_average_response_time(self, app_name: str) -> float:
        """获取平均响应时间
        
        Args:
            app_name: 应用名称
            
        Returns:
            平均响应时间
        """
        metrics = self.metrics.get(app_name, {})
        total_requests = metrics.get('total_requests', 0)
        total_time = metrics.get('total_time', 0)
        
        if total_requests == 0:
            return 0
        
        return round(total_time / total_requests, 3)


# 全局监控实例
app_monitor = AppMonitor()
#!/usr/bin/env python3
"""
可视化监控Dashboard
实时显示QPS、延迟、错误率等关键指标
"""
import sys
import time
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, '.')


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self._metrics = {
            'qps': [],
            'latency': [],
            'errors': [],
            'agents_active': [],
            'memory_usage': [],
            'cpu_usage': [],
        }
        self._start_time = time.time()
        self._request_count = 0
        self._error_count = 0
    
    def record_request(self, latency_ms: float, success: bool = True):
        """记录请求"""
        self._request_count += 1
        if not success:
            self._error_count += 1
        
        now = time.time()
        self._metrics['latency'].append((now, latency_ms))
        self._metrics['errors'].append((now, 1 if not success else 0))
        
        # 保留最近100个数据点
        if len(self._metrics['latency']) > 100:
            self._metrics['latency'].pop(0)
            self._metrics['errors'].pop(0)
    
    def record_agent_count(self, count: int):
        """记录活跃Agent数量"""
        now = time.time()
        self._metrics['agents_active'].append((now, count))
        if len(self._metrics['agents_active']) > 100:
            self._metrics['agents_active'].pop(0)
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        now = time.time()
        
        # 计算QPS（最近10秒）
        qps_window = 10
        recent_requests = [t for t, _ in self._metrics['latency'] if t > now - qps_window]
        qps = len(recent_requests) / qps_window
        
        # 计算平均延迟
        if self._metrics['latency']:
            avg_latency = sum(l for _, l in self._metrics['latency'][-50:]) / min(50, len(self._metrics['latency']))
        else:
            avg_latency = 0
        
        # 计算错误率
        if self._request_count > 0:
            error_rate = (self._error_count / self._request_count) * 100
        else:
            error_rate = 0
        
        # 获取活跃Agent数
        active_agents = self._metrics['agents_active'][-1][1] if self._metrics['agents_active'] else 0
        
        uptime = now - self._start_time
        
        return {
            'timestamp': datetime.now().isoformat(),
            'uptime': self._format_uptime(uptime),
            'qps': round(qps, 2),
            'avg_latency_ms': round(avg_latency, 2),
            'error_rate': round(error_rate, 2),
            'total_requests': self._request_count,
            'total_errors': self._error_count,
            'active_agents': active_agents,
            'latency_history': self._metrics['latency'][-20:],
            'error_history': self._metrics['errors'][-20:],
        }
    
    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """格式化运行时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class DashboardServer:
    """Dashboard服务器"""
    
    def __init__(self):
        self._collector = MetricsCollector()
        self._running = False
    
    async def start(self):
        """启动服务器"""
        self._running = True
        print("🚀 监控Dashboard已启动")
        
        # 模拟数据收集
        asyncio.create_task(self._simulate_metrics())
        
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self):
        """停止服务器"""
        self._running = False
        print("🛑 监控Dashboard已停止")
    
    async def _simulate_metrics(self):
        """模拟指标数据"""
        import random
        while self._running:
            # 模拟请求
            latency = random.uniform(10, 200)
            success = random.random() > 0.05  # 5%错误率
            self._collector.record_request(latency, success)
            
            # 模拟活跃Agent数
            agents = random.randint(5, 20)
            self._collector.record_agent_count(agents)
            
            await asyncio.sleep(0.1)
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取Dashboard数据"""
        return self._collector.get_metrics()


def generate_html_dashboard(data: Dict[str, Any]) -> str:
    """生成HTML仪表板"""
    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 小雷版小龙虾Agent监控</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; color: #fff; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .header h1 {{ font-size: 2.5rem; margin-bottom: 10px; background: linear-gradient(90deg, #00d4ff, #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .header p {{ color: #94a3b8; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .card {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); border-radius: 16px; padding: 24px; border: 1px solid rgba(255,255,255,0.1); }}
        .card:hover {{ transform: translateY(-2px); transition: transform 0.2s; }}
        .card-title {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 10px; }}
        .card-value {{ font-size: 2.5rem; font-weight: 700; }}
        .card-unit {{ font-size: 1rem; color: #94a3b8; margin-left: 5px; }}
        
        .status-good {{ color: #22c55e; }}
        .status-warning {{ color: #f59e0b; }}
        .status-danger {{ color: #ef4444; }}
        
        .chart-container {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); border-radius: 16px; padding: 24px; border: 1px solid rgba(255,255,255,0.1); }}
        .chart-title {{ font-size: 1.2rem; margin-bottom: 20px; }}
        
        .mini-chart {{ height: 100px; display: flex; align-items: flex-end; gap: 4px; }}
        .bar {{ background: linear-gradient(180deg, #00d4ff, #7c3aed); border-radius: 4px; transition: height 0.3s; }}
        .bar-error {{ background: linear-gradient(180deg, #ef4444, #dc2626); }}
        
        .footer {{ text-align: center; margin-top: 30px; color: #64748b; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🦞 小雷版小龙虾Agent监控</h1>
            <p>实时系统指标监控 | 更新时间: {data['timestamp']}</p>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="card-title">系统运行时间</div>
                <div class="card-value status-good">{data['uptime']}</div>
            </div>
            <div class="card">
                <div class="card-title">QPS（每秒请求数）</div>
                <div class="card-value {'status-good' if data['qps'] < 50 else 'status-warning'}">
                    {data['qps']}<span class="card-unit">req/s</span>
                </div>
            </div>
            <div class="card">
                <div class="card-title">平均延迟</div>
                <div class="card-value {'status-good' if data['avg_latency_ms'] < 100 else 'status-warning'}">
                    {data['avg_latency_ms']}<span class="card-unit">ms</span>
                </div>
            </div>
            <div class="card">
                <div class="card-title">错误率</div>
                <div class="card-value {'status-good' if data['error_rate'] < 5 else 'status-danger'}">
                    {data['error_rate']}<span class="card-unit">%</span>
                </div>
            </div>
            <div class="card">
                <div class="card-title">总请求数</div>
                <div class="card-value">{data['total_requests']}</div>
            </div>
            <div class="card">
                <div class="card-title">活跃Agent数</div>
                <div class="card-value status-good">{data['active_agents']}</div>
            </div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">📊 延迟趋势（最近20个请求）</div>
            <div class="mini-chart">
                {''.join([f'<div class="bar" style="height:{min(l/2, 100)}%"></div>' for _, l in data['latency_history']])}
            </div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">❌ 错误趋势（最近20个请求）</div>
            <div class="mini-chart">
                {''.join([f'<div class="bar {"bar-error" if e else "bar"}" style="height:{e*100}%"></div>' for _, e in data['error_history']])}
            </div>
        </div>
        
        <div class="footer">
            <p>小雷版小龙虾AI Agent v3.3.1 | 性能监控Dashboard</p>
        </div>
    </div>
</body>
</html>
"""


async def main():
    """主函数"""
    server = DashboardServer()
    task = asyncio.create_task(server.start())
    
    # 等待1秒收集数据
    await asyncio.sleep(1)
    
    # 获取数据并生成HTML
    data = server.get_dashboard_data()
    html = generate_html_dashboard(data)
    
    # 保存到文件
    with open('dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("✅ Dashboard已生成: dashboard.html")
    print("\n📊 当前指标:")
    print(f"   QPS: {data['qps']} req/s")
    print(f"   延迟: {data['avg_latency_ms']} ms")
    print(f"   错误率: {data['error_rate']}%")
    print(f"   活跃Agent: {data['active_agents']}")
    print(f"   运行时间: {data['uptime']}")
    
    await server.stop()


if __name__ == "__main__":
    asyncio.run(main())

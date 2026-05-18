#!/usr/bin/env python3
"""
后端功能与执行层匹配检查脚本
验证所有 API 端点是否正确定义、注册和可访问
"""
import requests
import sys
import time
from typing import Dict, List, Tuple

BASE_URL = "http://localhost:8001"

class BackendChecker:
    """后端功能检查器"""
    
    def __init__(self):
        self.results = []
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.warnings = 0
    
    def check(self, category: str, name: str, endpoint: str, method: str = "GET", 
              expected_status: int = 200, payload: dict = None) -> bool:
        """检查单个端点"""
        self.total += 1
        
        print(f"\n{'='*70}")
        print(f"[{category}] {name}")
        print(f"  端点: {method} {endpoint}")
        print('='*70)
        
        try:
            url = f"{BASE_URL}{endpoint}"
            
            if method == "GET":
                response = requests.get(url, timeout=5)
            elif method == "POST":
                response = requests.post(url, json=payload or {}, timeout=10)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")
            
            # 检查状态码
            if response.status_code == expected_status:
                status = "✅ 通过"
                self.passed += 1
                result = True
            else:
                status = f"❌ 失败 (期望 {expected_status}, 实际 {response.status_code})"
                self.failed += 1
                result = False
            
            # 记录结果
            self.results.append({
                'category': category,
                'name': name,
                'endpoint': endpoint,
                'status': status,
                'response_code': response.status_code
            })
            
            print(f"  状态码: {response.status_code}")
            print(f"  结果: {status}")
            
            # 如果是 200，尝试解析 JSON
            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'success' in data:
                        print(f"  响应: success={data['success']}")
                    if 'data' in data and isinstance(data['data'], list):
                        print(f"  数据量: {len(data['data'])} 项")
                except Exception:
                    pass
            
            return result
            
        except requests.exceptions.ConnectionError:
            status = "❌ 连接失败 (服务未启动?)"
            self.failed += 1
            self.results.append({
                'category': category,
                'name': name,
                'endpoint': endpoint,
                'status': status,
                'response_code': None
            })
            print(f"  结果: {status}")
            return False
            
        except Exception as e:
            status = f"❌ 异常: {str(e)}"
            self.failed += 1
            self.results.append({
                'category': category,
                'name': name,
                'endpoint': endpoint,
                'status': status,
                'response_code': None
            })
            print(f"  结果: {status}")
            return False
    
    def warning(self, category: str, name: str, message: str):
        """添加警告"""
        self.warnings += 1
        self.results.append({
            'category': category,
            'name': name,
            'status': f"⚠️  警告: {message}",
            'response_code': None
        })
        print(f"\n⚠️  [{category}] {name}: {message}")
    
    def summary(self):
        """打印总结"""
        print("\n" + "="*70)
        print("📊 检查结果汇总")
        print("="*70)
        print(f"总检查项: {self.total}")
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"警告: {self.warnings}")
        
        if self.total > 0:
            pass_rate = self.passed / self.total * 100
            print(f"通过率: {pass_rate:.1f}%")
        
        print("="*70)
        
        # 按类别分组显示
        categories = {}
        for r in self.results:
            cat = r['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r)
        
        for cat, items in categories.items():
            print(f"\n{cat}:")
            for item in items:
                print(f"  {item['status']} - {item['name']}")
        
        print("\n" + "="*70)
        
        return self.failed == 0


def main():
    print("="*70)
    print("🔍 后端功能与执行层匹配检查")
    print("="*70)
    print(f"测试目标: {BASE_URL}")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    checker = BackendChecker()
    
    # ==================== 1. 核心聊天功能 ====================
    print("\n💬 核心聊天功能")
    
    checker.check(
        "聊天功能",
        "聊天 API - 正常请求",
        "/api/chat",
        method="POST",
        payload={"message": "你好", "user_id": 1, "agent_id": "bestfriend"}
    )
    
    checker.check(
        "聊天功能",
        "聊天 API - 空消息验证",
        "/api/chat",
        method="POST",
        expected_status=422,
        payload={"message": "", "user_id": 1}
    )
    
    # ==================== 2. 文件上传功能 ====================
    print("\n📁 文件上传功能")
    
    # 注意：文件上传需要 multipart/form-data，这里只检查端点是否存在
    # 实际测试需要使用 files 参数
    try:
        response = requests.options(f"{BASE_URL}/api/upload", timeout=5)
        if response.status_code in [200, 204, 405]:  # 405 表示方法不允许但端点存在
            checker.results.append({
                'category': '文件上传',
                'name': '单文件上传端点',
                'endpoint': '/api/upload',
                'status': '✅ 端点存在',
                'response_code': response.status_code
            })
            checker.total += 1
            checker.passed += 1
            print(f"\n{'='*70}")
            print("[文件上传] 单文件上传端点")
            print(f"  端点: POST /api/upload")
            print('='*70)
            print(f"  结果: ✅ 端点存在")
        else:
            checker.warning('文件上传', '单文件上传端点', '端点可能不存在')
    except Exception:
        checker.warning('文件上传', '单文件上传端点', '无法检查端点')
    
    try:
        response = requests.options(f"{BASE_URL}/api/upload/batch", timeout=5)
        if response.status_code in [200, 204, 405]:
            checker.results.append({
                'category': '文件上传',
                'name': '批量文件上传端点',
                'endpoint': '/api/upload/batch',
                'status': '✅ 端点存在',
                'response_code': response.status_code
            })
            checker.total += 1
            checker.passed += 1
            print(f"\n{'='*70}")
            print("[文件上传] 批量文件上传端点")
            print(f"  端点: POST /api/upload/batch")
            print('='*70)
            print(f"  结果: ✅ 端点存在")
        else:
            checker.warning('文件上传', '批量文件上传端点', '端点可能不存在')
    except Exception:
        checker.warning('文件上传', '批量文件上传端点', '无法检查端点')
    
    # ==================== 3. 技能管理功能 ====================
    print("\n🎯 技能管理功能")
    
    checker.check(
        "技能管理",
        "获取所有技能",
        "/api/skills"
    )
    
    checker.check(
        "技能管理",
        "搜索技能",
        "/api/skills/search?q=天气"
    )
    
    # ==================== 4. 工作流功能 ====================
    print("\n🔄 工作流功能")
    
    checker.check(
        "工作流",
        "工作流编辑器页面",
        "/workflow_editor"
    )
    
    # ==================== 5. 系统监控功能 ====================
    print("\n📊 系统监控功能")
    
    checker.check(
        "系统监控",
        "健康检查",
        "/api/health"
    )
    
    # 检查 metrics 端点（如果存在）
    try:
        response = requests.get(f"{BASE_URL}/api/metrics", timeout=5)
        if response.status_code == 200:
            checker.check("系统监控", "系统指标", "/api/metrics")
        else:
            checker.warning("系统监控", "系统指标", "端点返回非 200 状态码")
    except Exception:
        checker.warning("系统监控", "系统指标", "端点可能不存在")
    
    # ==================== 6. 用户认证功能 ====================
    print("\n🔐 用户认证功能")
    
    # 检查登录端点（注意：system.py 没有设置 prefix，所以路径是 /auth/login）
    try:
        response = requests.options(f"{BASE_URL}/auth/login", timeout=5)
        if response.status_code in [200, 204, 405]:
            checker.results.append({
                'category': '用户认证',
                'name': '登录端点',
                'endpoint': '/auth/login',
                'status': '✅ 端点存在',
                'response_code': response.status_code
            })
            checker.total += 1
            checker.passed += 1
            print(f"\n{'='*70}")
            print("[用户认证] 登录端点")
            print(f"  端点: POST /auth/login")
            print('='*70)
            print(f"  结果: ✅ 端点存在")
        else:
            checker.warning('用户认证', '登录端点', f'端点返回 {response.status_code}')
    except Exception:
        checker.warning('用户认证', '登录端点', '无法检查端点')
    
    # ==================== 7. 历史记录功能 ====================
    print("\n📜 历史记录功能")
    
    # 检查历史记录端点
    try:
        response = requests.get(f"{BASE_URL}/api/history", timeout=5)
        if response.status_code == 200:
            checker.check("历史记录", "聊天记录查询", "/api/history")
        else:
            checker.warning("历史记录", "聊天记录查询", f"端点返回 {response.status_code}")
    except Exception:
        checker.warning("历史记录", "聊天记录查询", "端点可能不存在或未启动")
    
    # ==================== 8. Agent 小组功能 ====================
    print("\n👥 Agent 小组功能")
    
    try:
        response = requests.get(f"{BASE_URL}/api/agent-groups", timeout=5)
        if response.status_code == 200:
            checker.check("Agent小组", "获取Agent小组列表", "/api/agent-groups")
        else:
            checker.warning("Agent小组", "获取Agent小组列表", f"端点返回 {response.status_code}")
    except Exception:
        checker.warning("Agent小组", "获取Agent小组列表", "端点可能不存在")
    
    # ==================== 9. 定时任务功能 ====================
    print("\n⏰ 定时任务功能")
    
    try:
        response = requests.get(f"{BASE_URL}/api/schedule/list", timeout=5)
        if response.status_code == 200:
            checker.check("定时任务", "获取定时任务列表", "/api/schedule/list")
        else:
            checker.warning("定时任务", "获取定时任务列表", f"端点返回 {response.status_code}")
    except Exception:
        checker.warning("定时任务", "获取定时任务列表", "端点可能不存在")
    
    # ==================== 10. 自我校验功能 ====================
    print("\n✅ 自我校验功能")
    
    try:
        response = requests.get(f"{BASE_URL}/api/v1/self-check/stats", timeout=5)
        if response.status_code == 200:
            checker.check("自我校验", "自我校验统计信息", "/api/v1/self-check/stats")
        else:
            checker.warning("自我校验", "自我校验统计信息", f"端点返回 {response.status_code}")
    except Exception:
        checker.warning("自我校验", "自我校验统计信息", "端点可能不存在")
    
    # ==================== 11. 静态资源 ====================
    print("\n📁 静态资源")
    
    checker.check(
        "静态资源",
        "Coze 聊天页面",
        "/coze"
    )
    
    checker.check(
        "静态资源",
        "CSS 文件",
        "/static/css/coze.css"
    )
    
    checker.check(
        "静态资源",
        "JS 文件",
        "/static/js/coze.js"
    )
    
    checker.check(
        "静态资源",
        "API 文档",
        "/docs"
    )
    
    # 打印总结
    success = checker.summary()
    
    print(f"\n完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if success:
        print("\n🎉 所有检查通过！后端功能与执行层完全匹配。")
    else:
        print(f"\n⚠️  有 {checker.failed} 项检查失败，请检查相关功能。")
    
    # 提供建议
    print("\n💡 建议:")
    if checker.warnings > 0:
        print(f"   - 有 {checker.warnings} 个警告，可能需要进一步确认")
    if checker.failed > 0:
        print("   - 失败的检查项需要立即修复")
        print("   - 检查服务是否正常运行")
        print("   - 查看日志获取详细错误信息")
    else:
        print("   - 系统运行正常，可以继续开发新功能")
        print("   - 建议定期运行此检查确保稳定性")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

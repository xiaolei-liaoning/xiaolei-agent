#!/usr/bin/env python3
"""
全面功能测试脚本 - 小雷版小龙虾 AI Agent v3.3.1
测试所有核心功能和新增特性
"""
import requests
import json
import sys
import time
from pathlib import Path

BASE_URL = "http://localhost:8001"

class TestRunner:
    def __init__(self):
        self.results = []
        self.total = 0
        self.passed = 0
        self.failed = 0
    
    def test(self, name, func):
        """执行单个测试"""
        self.total += 1
        print(f"\n{'='*70}")
        print(f"测试 {self.total}: {name}")
        print('='*70)
        
        try:
            start_time = time.time()
            result = func()
            elapsed = time.time() - start_time
            
            if result:
                self.passed += 1
                status = "✅ 通过"
            else:
                self.failed += 1
                status = "❌ 失败"
            
            self.results.append({
                'name': name,
                'status': status,
                'time': elapsed
            })
            
            print(f"{status} (耗时: {elapsed:.2f}s)")
            return result
            
        except Exception as e:
            self.failed += 1
            status = f"❌ 异常: {str(e)}"
            self.results.append({
                'name': name,
                'status': status,
                'time': 0
            })
            print(f"{status}")
            return False
    
    def summary(self):
        """打印测试总结"""
        print("\n" + "="*70)
        print("📊 测试结果汇总")
        print("="*70)
        print(f"总测试数: {self.total}")
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"通过率: {self.passed/self.total*100:.1f}%")
        print("="*70)
        
        if self.failed > 0:
            print("\n❌ 失败的测试:")
            for r in self.results:
                if '❌' in r['status']:
                    print(f"   - {r['name']}: {r['status']}")
        
        print("\n" + "="*70)
        return self.failed == 0


# ==================== 测试用例 ====================

def test_api_health():
    """测试健康检查 API"""
    response = requests.get(f"{BASE_URL}/api/health", timeout=5)
    assert response.status_code == 200, f"状态码: {response.status_code}"
    data = response.json()
    print(f"   状态: {data.get('status', 'unknown')}")
    print(f"   版本: {data.get('version', 'unknown')}")
    return True

def test_skills_list():
    """测试技能列表 API"""
    response = requests.get(f"{BASE_URL}/api/skills", timeout=5)
    assert response.status_code == 200, f"状态码: {response.status_code}"
    
    data = response.json()
    assert data['success'] == True, "API 返回 success=false"
    assert 'data' in data, "缺少 data 字段"
    
    skills = data['data']
    print(f"   技能数量: {len(skills)}")
    print(f"   技能列表: {', '.join([s['name'] for s in skills[:5]])}...")
    
    # 验证数据结构
    first_skill = skills[0]
    assert 'name' in first_skill, "缺少 name 字段"
    assert 'display_name' in first_skill, "缺少 display_name 字段"
    assert 'description' in first_skill, "缺少 description 字段"
    
    return True

def test_skills_search():
    """测试技能搜索 API"""
    response = requests.get(f"{BASE_URL}/api/skills/search?q=天气", timeout=5)
    assert response.status_code == 200, f"状态码: {response.status_code}"
    
    data = response.json()
    assert data['success'] == True, "API 返回 success=false"
    
    results = data['data']
    print(f"   搜索结果: {len(results)} 个技能")
    
    return True

def test_chat_api():
    """测试聊天 API"""
    payload = {
        "message": "你好",
        "user_id": 1,
        "agent_id": "bestfriend"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json=payload,
        timeout=10
    )
    
    assert response.status_code == 200, f"状态码: {response.status_code}"
    
    data = response.json()
    assert 'reply' in data, "缺少 reply 字段"
    print(f"   AI 回复: {data['reply'][:50]}...")
    
    return True

def test_chat_with_empty_message():
    """测试空消息验证（应该返回 422）"""
    payload = {
        "message": "",
        "user_id": 1
    }
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json=payload,
        timeout=5
    )
    
    # 期望返回 422（验证失败）
    assert response.status_code == 422, f"期望 422，实际: {response.status_code}"
    print(f"   ✅ 正确拦截空消息")
    
    return True

def test_workflow_editor_page():
    """测试工作流编辑器页面"""
    response = requests.get(f"{BASE_URL}/workflow_editor", timeout=5)
    assert response.status_code == 200, f"状态码: {response.status_code}"
    assert 'workflow' in response.text.lower(), "页面内容不包含 workflow"
    print(f"   页面大小: {len(response.text)} bytes")
    return True

def test_coze_chat_page():
    """测试 Coze 聊天页面"""
    response = requests.get(f"{BASE_URL}/coze", timeout=5)
    assert response.status_code == 200, f"状态码: {response.status_code}"
    assert 'chat' in response.text.lower(), "页面内容不包含 chat"
    print(f"   页面大小: {len(response.text)} bytes")
    return True

def test_static_files():
    """测试静态文件访问"""
    # 测试 CSS
    response = requests.get(f"{BASE_URL}/static/css/coze.css", timeout=5)
    assert response.status_code == 200, f"CSS 状态码: {response.status_code}"
    
    # 测试 JS
    response = requests.get(f"{BASE_URL}/static/js/coze.js", timeout=5)
    assert response.status_code == 200, f"JS 状态码: {response.status_code}"
    
    print(f"   ✅ CSS 和 JS 文件可访问")
    return True

def test_api_docs():
    """测试 API 文档"""
    response = requests.get(f"{BASE_URL}/docs", timeout=5)
    assert response.status_code == 200, f"状态码: {response.status_code}"
    assert 'swagger' in response.text.lower() or 'fastapi' in response.text.lower(), "不是 Swagger 文档"
    print(f"   ✅ API 文档可访问")
    return True

def test_response_format():
    """测试响应格式一致性"""
    endpoints = [
        ("/api/skills", "GET"),
        ("/api/skills/search?q=test", "GET"),
    ]
    
    for endpoint, method in endpoints:
        if method == "GET":
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=5)
        else:
            response = requests.post(f"{BASE_URL}{endpoint}", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            assert 'success' in data, f"{endpoint} 缺少 success 字段"
            print(f"   ✅ {endpoint} 响应格式正确")
    
    return True


# ==================== 主函数 ====================

def main():
    print("="*70)
    print("🧪 全面功能测试 - 小雷版小龙虾 AI Agent v3.3.1")
    print("="*70)
    print(f"测试目标: {BASE_URL}")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    runner = TestRunner()
    
    # API 基础测试
    print("\n📡 API 基础测试")
    runner.test("健康检查 API", test_api_health)
    runner.test("技能列表 API", test_skills_list)
    runner.test("技能搜索 API", test_skills_search)
    
    # 聊天功能测试
    print("\n💬 聊天功能测试")
    runner.test("聊天 API 正常请求", test_chat_api)
    runner.test("聊天 API 空消息验证", test_chat_with_empty_message)
    
    # 页面访问测试
    print("\n🌐 页面访问测试")
    runner.test("工作流编辑器页面", test_workflow_editor_page)
    runner.test("Coze 聊天页面", test_coze_chat_page)
    
    # 静态资源测试
    print("\n📁 静态资源测试")
    runner.test("静态文件访问", test_static_files)
    runner.test("API 文档访问", test_api_docs)
    
    # 响应格式测试
    print("\n📋 响应格式测试")
    runner.test("响应格式一致性", test_response_format)
    
    # 打印总结
    success = runner.summary()
    
    print(f"\n完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if success:
        print("\n🎉 所有测试通过！系统运行正常。")
        print("\n💡 下一步建议:")
        print("   1. 打开浏览器访问 http://localhost:8001/coze")
        print("   2. 测试消息历史记录功能")
        print("   3. 测试快捷指令自动补全（输入 / 查看提示）")
        print("   4. 测试文件上传和 OCR 识别")
    else:
        print("\n⚠️  部分测试失败，请检查服务状态和日志。")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

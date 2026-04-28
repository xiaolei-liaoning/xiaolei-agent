#!/usr/bin/env python3
"""
前端功能自动化测试脚本
测试所有最近修复的功能
"""
import requests
import json
import sys
import time

BASE_URL_8000 = "http://localhost:8000"
BASE_URL_8001 = "http://localhost:8001"

def test_api_endpoint(base_url, endpoint, expected_status=200, description=""):
    """测试 API 端点"""
    try:
        response = requests.get(f"{base_url}{endpoint}", timeout=5)
        
        if response.status_code != expected_status:
            return False, f"❌ {description or endpoint} - 状态码: {response.status_code} (期望 {expected_status})"
        
        if expected_status == 200:
            data = response.json()
            if not data.get('success'):
                return False, f"❌ {description or endpoint} - API 返回 success=false"
            if 'data' not in data:
                return False, f"❌ {description or endpoint} - 缺少 data 字段"
            
            skill_count = len(data['data']) if isinstance(data['data'], list) else 0
            return True, f"✅ {description or endpoint} - 成功 (返回 {skill_count} 个技能)"
        
        return True, f"✅ {description or endpoint} - 状态码: {response.status_code}"
        
    except requests.exceptions.ConnectionError:
        return False, f"❌ {description or endpoint} - 无法连接到服务器"
    except Exception as e:
        return False, f"❌ {description or endpoint} - 错误: {str(e)}"

def test_consistency():
    """测试两个端口的 API 数据一致性"""
    try:
        resp_8000 = requests.get(f"{BASE_URL_8000}/api/skills", timeout=5)
        resp_8001 = requests.get(f"{BASE_URL_8001}/api/skills", timeout=5)
        
        if resp_8000.status_code != 200 or resp_8001.status_code != 200:
            return False, "❌ 端口数据一致性 - 至少一个端口返回非 200 状态码"
        
        data_8000 = resp_8000.json()
        data_8001 = resp_8001.json()
        
        # 比较技能数量
        count_8000 = len(data_8000.get('data', []))
        count_8001 = len(data_8001.get('data', []))
        
        if count_8000 != count_8001:
            return False, f"❌ 端口数据一致性 - 技能数量不一致 (8000: {count_8000}, 8001: {count_8001})"
        
        return True, f"✅ 端口数据一致性 - 两个端口都返回 {count_8000} 个技能"
        
    except Exception as e:
        return False, f"❌ 端口数据一致性 - 错误: {str(e)}"

def main():
    print("=" * 70)
    print("🧪 前端功能修复自动化测试")
    print("=" * 70)
    print()
    
    results = []
    
    # 测试1: 端口 8001 技能列表 API
    print("测试 1/6: 端口 8001 技能列表 API")
    passed, msg = test_api_endpoint(
        BASE_URL_8001, 
        "/api/skills", 
        description="端口 8001 /api/skills"
    )
    results.append(("端口8001技能列表", passed))
    print(f"  {msg}\n")
    
    # 测试2: 端口 8000 技能列表 API
    print("测试 2/6: 端口 8000 技能列表 API")
    passed, msg = test_api_endpoint(
        BASE_URL_8000, 
        "/api/skills", 
        description="端口 8000 /api/skills"
    )
    results.append(("端口8000技能列表", passed))
    print(f"  {msg}\n")
    
    # 测试3: 技能搜索 API
    print("测试 3/6: 技能搜索 API")
    passed, msg = test_api_endpoint(
        BASE_URL_8001, 
        "/api/skills/search?q=天气", 
        description="技能搜索"
    )
    results.append(("技能搜索API", passed))
    print(f"  {msg}\n")
    
    # 测试4: 健康检查
    print("测试 4/6: 健康检查 API")
    passed, msg = test_api_endpoint(
        BASE_URL_8001, 
        "/api/health", 
        description="健康检查"
    )
    results.append(("健康检查", passed))
    print(f"  {msg}\n")
    
    # 测试5: 工作流编辑器页面
    print("测试 5/6: 工作流编辑器页面")
    try:
        response = requests.get(f"{BASE_URL_8001}/workflow_editor", timeout=5)
        if response.status_code == 200 and 'workflow' in response.text.lower():
            passed = True
            msg = "✅ 工作流编辑器页面 - 可访问"
        else:
            passed = False
            msg = f"❌ 工作流编辑器页面 - 状态码: {response.status_code}"
    except Exception as e:
        passed = False
        msg = f"❌ 工作流编辑器页面 - 错误: {str(e)}"
    
    results.append(("工作流编辑器页面", passed))
    print(f"  {msg}\n")
    
    # 测试6: 端口数据一致性
    print("测试 6/6: 端口数据一致性")
    passed, msg = test_consistency()
    results.append(("端口数据一致性", passed))
    print(f"  {msg}\n")
    
    # 统计结果
    print("=" * 70)
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    failed_count = total - passed_count
    pass_rate = (passed_count / total * 100) if total > 0 else 0
    
    print(f"📊 测试结果汇总:")
    print(f"   总测试项: {total}")
    print(f"   通过: {passed_count}")
    print(f"   失败: {failed_count}")
    print(f"   通过率: {pass_rate:.1f}%")
    print("=" * 70)
    
    if failed_count > 0:
        print("\n❌ 失败的测试:")
        for name, passed in results:
            if not passed:
                print(f"   - {name}")
        
        print("\n💡 建议:")
        print("   1. 确保后端服务已启动 (python main.py)")
        print("   2. 检查端口 8000 和 8001 是否被占用")
        print("   3. 查看后端日志获取详细错误信息")
        print("   4. 重启服务后重新运行测试")
    else:
        print("\n🎉 所有测试通过！")
        print("\n✅ 下一步操作:")
        print("   1. 打开浏览器访问 http://localhost:8001/workflow_editor")
        print("   2. 按 Ctrl+Shift+R 强制刷新页面")
        print("   3. 打开开发者工具 (F12) 查看控制台")
        print("   4. 验证无错误信息且技能列表正常加载")
    
    print("=" * 70)
    
    # 退出码: 0=全部通过, 1=有失败
    sys.exit(0 if failed_count == 0 else 1)

if __name__ == "__main__":
    main()

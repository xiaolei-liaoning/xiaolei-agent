#!/usr/bin/env python3
"""Agent小组API完整功能测试

包含:
- 单元测试: 参数验证
- 集成测试: API端点测试
- 审计日志测试: 操作记录验证

运行方式: python3 test_agent_groups_full.py
"""

import requests
import json
import sys
import time

BASE_URL = 'http://localhost:8001'

def print_header(text):
    print('\n' + '='*60)
    print(text)
    print('='*60)

def print_test(test_num, name, category="集成"):
    print(f'\n✅ 测试{test_num}: {name} [{category}]')

class TestResult:
    """测试结果统计"""
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def record_pass(self, test_name):
        self.total += 1
        self.passed += 1
        print(f'  ✅ 通过: {test_name}')
    
    def record_fail(self, test_name, error_msg):
        self.total += 1
        self.failed += 1
        self.errors.append((test_name, error_msg))
        print(f'  ❌ 失败: {test_name} - {error_msg}')

def test_parameter_validation(result: TestResult):
    """测试参数验证功能"""
    print_header('参数验证测试')
    
    # 测试1: 无效Agent成员
    print_test(1, '验证无效Agent成员', '单元')
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '测试小组',
            'members': ['InvalidAgent'],  # 无效成员
            'strategy': 'priority'
        })
        if r.status_code == 422:  # 验证错误
            result.record_pass('无效Agent成员验证')
        else:
            result.record_fail('无效Agent成员验证', f'期望422,实际{r.status_code}')
    except Exception as e:
        result.record_fail('无效Agent成员验证', str(e))
    
    # 测试2: 成员重复
    print_test(2, '验证成员重复', '单元')
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '测试小组',
            'members': ['Checker', 'Checker'],  # 重复成员
            'strategy': 'priority'
        })
        if r.status_code == 422:
            result.record_pass('成员重复验证')
        else:
            result.record_fail('成员重复验证', f'期望422,实际{r.status_code}')
    except Exception as e:
        result.record_fail('成员重复验证', str(e))
    
    # 测试3: 名称唯一性
    print_test(3, '验证名称唯一性', '单元')
    try:
        # 先创建一个小组
        r1 = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '唯一性测试小组',
            'members': ['Checker'],
            'strategy': 'priority'
        })
        if r1.status_code == 201:
            # 尝试创建同名小组
            r2 = requests.post(f'{BASE_URL}/api/agent-groups', json={
                'name': '唯一性测试小组',  # 同名
                'members': ['Scraper'],
                'strategy': 'priority'
            })
            if r2.status_code == 409:
                result.record_pass('名称唯一性验证')
                # 清理测试数据
                group_id = r1.json()['id']
                requests.delete(f'{BASE_URL}/api/agent-groups/{group_id}')
            else:
                result.record_fail('名称唯一性验证', f'期望409,实际{r2.status_code}')
        else:
            result.record_fail('名称唯一性验证', f'创建初始小组失败: {r1.status_code}')
    except Exception as e:
        result.record_fail('名称唯一性验证', str(e))
    
    # 测试4: 无效策略
    print_test(4, '验证无效策略', '单元')
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '测试小组',
            'members': ['Checker'],
            'strategy': 'invalid_strategy'  # 无效策略
        })
        if r.status_code == 422:
            result.record_pass('无效策略验证')
        else:
            result.record_fail('无效策略验证', f'期望422,实际{r.status_code}')
    except Exception as e:
        result.record_fail('无效策略验证', str(e))
    
    # 测试5: 名称格式验证
    print_test(5, '验证名称格式', '单元')
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': 'A',  # 太短
            'members': ['Checker'],
            'strategy': 'priority'
        })
        if r.status_code == 422:
            result.record_pass('名称格式验证')
        else:
            result.record_fail('名称格式验证', f'期望422,实际{r.status_code}')
    except Exception as e:
        result.record_fail('名称格式验证', str(e))
    
    # 测试6: 成员数量限制
    print_test(6, '验证成员数量限制', '单元')
    try:
        # 创建超过10个成员的小组
        members = ['Checker', 'Scraper', 'Vulnerability', 'Summarizer', 
                   'DataAnalysis', 'NLP', 'TextAnalyzer', 'Planning', 
                   'Processor', 'Transformer', 'Scanner']  # 11个成员
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '测试小组',
            'members': members,
            'strategy': 'priority'
        })
        if r.status_code == 422:
            result.record_pass('成员数量限制验证')
        else:
            result.record_fail('成员数量限制验证', f'期望422,实际{r.status_code}')
    except Exception as e:
        result.record_fail('成员数量限制验证', str(e))

def test_api_endpoints(result: TestResult):
    """测试API端点功能"""
    print_header('API端点测试')
    
    # 测试7: 健康检查
    print_test(7, '健康检查', '集成')
    try:
        r = requests.get(f'{BASE_URL}/api/health')
        data = r.json()
        if data['status'] == 'healthy':
            result.record_pass('健康检查')
        else:
            result.record_fail('健康检查', f'状态异常: {data["status"]}')
    except Exception as e:
        result.record_fail('健康检查', str(e))
    
    # 测试8: 获取小组列表
    print_test(8, '获取小组列表', '集成')
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups')
        data = r.json()
        if data['total'] >= 3:
            result.record_pass('获取小组列表')
        else:
            result.record_fail('获取小组列表', f'小组数量不足: {data["total"]}')
    except Exception as e:
        result.record_fail('获取小组列表', str(e))
    
    # 测试9: 创建新小组
    print_test(9, '创建新小组', '集成')
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '完整测试小组',
            'members': ['Checker', 'Scraper'],
            'strategy': 'priority',
            'circuit_breaker': True,
            'elastic_scaling': False
        })
        data = r.json()
        if r.status_code == 201 and data['status'] == '离线':
            result.record_pass('创建新小组')
            return data['id']  # 返回group_id供后续测试使用
        else:
            result.record_fail('创建新小组', f'状态异常: {r.status_code}')
            return None
    except Exception as e:
        result.record_fail('创建新小组', str(e))
        return None
    
    # 测试10-16需要使用创建的group_id,因此单独处理
    return None

def test_crud_operations(result: TestResult):
    """测试CRUD操作"""
    print_header('CRUD操作测试')
    
    # 先创建一个小组用于测试
    print('\n  准备: 创建测试小组')
    r = requests.post(f'{BASE_URL}/api/agent-groups', json={
        'name': 'CRUD测试小组',
        'members': ['Checker', 'Scraper'],
        'strategy': 'priority'
    })
    if r.status_code != 201:
        print('  ⚠️  无法创建测试小组,跳过CRUD测试')
        return
    
    group_id = r.json()['id']
    print(f'  ✅ 创建成功: {group_id}')
    
    # 测试10: 获取小组详情
    print_test(10, '获取小组详情', '集成')
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups/{group_id}')
        if r.status_code == 200 and r.json()['id'] == group_id:
            result.record_pass('获取小组详情')
        else:
            result.record_fail('获取小组详情', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('获取小组详情', str(e))
    
    # 测试11: 更新小组
    print_test(11, '更新小组配置', '集成')
    try:
        r = requests.put(f'{BASE_URL}/api/agent-groups/{group_id}', json={
            'name': 'CRUD测试小组(已更新)',
            'members': ['Checker', 'Scraper', 'NLP'],
            'strategy': 'least_load'
        })
        if r.status_code == 200 and len(r.json()['members']) == 3:
            result.record_pass('更新小组配置')
        else:
            result.record_fail('更新小组配置', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('更新小组配置', str(e))
    
    # 测试12: 启动小组
    print_test(12, '启动小组', '集成')
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups/{group_id}/start')
        if r.status_code == 200 and r.json()['status'] == '运行中':
            result.record_pass('启动小组')
        else:
            result.record_fail('启动小组', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('启动小组', str(e))
    
    # 测试13: 停止小组
    print_test(13, '停止小组', '集成')
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups/{group_id}/stop')
        if r.status_code == 200 and r.json()['status'] == '休眠':
            result.record_pass('停止小组')
        else:
            result.record_fail('停止小组', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('停止小组', str(e))
    
    # 测试14: 删除小组
    print_test(14, '删除小组', '集成')
    try:
        r = requests.delete(f'{BASE_URL}/api/agent-groups/{group_id}')
        if r.status_code == 200 and r.json()['success'] == True:
            result.record_pass('删除小组')
        else:
            result.record_fail('删除小组', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('删除小组', str(e))
    
    # 测试15: 验证删除
    print_test(15, '验证删除', '集成')
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups/{group_id}')
        if r.status_code == 404:
            result.record_pass('验证删除')
        else:
            result.record_fail('验证删除', f'期望404,实际{r.status_code}')
    except Exception as e:
        result.record_fail('验证删除', str(e))

def test_audit_logs(result: TestResult):
    """测试审计日志功能"""
    print_header('审计日志测试')
    
    # 准备: 创建一个小组
    print('\n  准备: 创建测试小组')
    r = requests.post(f'{BASE_URL}/api/agent-groups', json={
        'name': '审计测试小组',
        'members': ['Checker'],
        'strategy': 'priority'
    })
    if r.status_code != 201:
        print('  ⚠️  无法创建测试小组,跳过审计日志测试')
        return
    
    group_id = r.json()['id']
    print(f'  ✅ 创建成功: {group_id}')
    time.sleep(0.1)  # 等待日志记录
    
    # 执行一些操作
    requests.put(f'{BASE_URL}/api/agent-groups/{group_id}', json={'name': '审计测试小组(已更新)'})
    requests.post(f'{BASE_URL}/api/agent-groups/{group_id}/start')
    requests.post(f'{BASE_URL}/api/agent-groups/{group_id}/stop')
    
    # 测试16: 获取审计日志
    print_test(16, '获取审计日志', '集成')
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups/audit-logs')
        data = r.json()
        if data['success'] == True and data['total'] > 0:
            result.record_pass('获取审计日志')
        else:
            result.record_fail('获取审计日志', f'日志为空')
    except Exception as e:
        result.record_fail('获取审计日志', str(e))
    
    # 测试17: 筛选审计日志
    print_test(17, '筛选审计日志', '集成')
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups/audit-logs', params={
            'group_id': group_id,
            'action': 'CREATE'
        })
        data = r.json()
        if data['success'] == True and data['total'] >= 1:
            result.record_pass('筛选审计日志')
        else:
            result.record_fail('筛选审计日志', f'筛选结果: {data["total"]}')
    except Exception as e:
        result.record_fail('筛选审计日志', str(e))
    
    # 测试18: 验证审计日志内容
    print_test(18, '验证审计日志内容', '集成')
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups/audit-logs', params={
            'group_id': group_id
        })
        data = r.json()
        if data['total'] >= 4:  # CREATE + UPDATE + START + STOP
            result.record_pass('验证审计日志内容')
        else:
            result.record_fail('验证审计日志内容', f'日志数量不足: {data["total"]}')
    except Exception as e:
        result.record_fail('验证审计日志内容', str(e))
    
    # 清理测试数据
    requests.delete(f'{BASE_URL}/api/agent-groups/{group_id}')

def main():
    print_header(' Agent小组API完整功能测试')
    print('测试覆盖:')
    print('  - 参数验证测试 (6项)')
    print('  - API端点测试 (2项)')
    print('  - CRUD操作测试 (6项)')
    print('  - 审计日志测试 (3项)')
    print('总计: 17项测试')
    
    result = TestResult()
    
    try:
        # 执行测试
        test_parameter_validation(result)
        test_api_endpoints(result)
        test_crud_operations(result)
        test_audit_logs(result)
        
        # 输出结果
        print_header(' 测试完成')
        print(f'总计: {result.total} 项测试')
        print(f'通过: {result.passed} 项 ✅')
        print(f'失败: {result.failed} 项 ❌')
        print(f'通过率: {result.passed/result.total*100:.1f}%')
        
        if result.errors:
            print('\n 失败详情:')
            for test_name, error_msg in result.errors:
                print(f'  - {test_name}: {error_msg}')
        
        if result.failed == 0:
            print('\n 所有测试通过!')
            return 0
        else:
            print(f'\n️  {result.failed}项测试失败')
            return 1
            
    except Exception as e:
        print(f'\n❌ 测试执行异常: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())

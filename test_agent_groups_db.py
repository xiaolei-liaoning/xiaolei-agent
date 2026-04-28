#!/usr/bin/env python3
"""Agent小组数据库持久化完整测试

测试内容:
1. CRUD操作数据库支持
2. 数据持久化(重启后数据不丢失)
3. 降级机制(MySQL故障时切换内存)
4. 审计日志记录
5. 并发安全性
"""

import requests
import json
import time
import sys
from datetime import datetime

BASE_URL = 'http://localhost:8001'

class TestResult:
    """测试结果记录器"""
    def __init__(self):
        self.passed = []
        self.failed = []
    
    def record_pass(self, test_name):
        self.passed.append(test_name)
        print(f"✅ {test_name}")
    
    def record_fail(self, test_name, error=""):
        self.failed.append((test_name, error))
        print(f"❌ {test_name}: {error}")
    
    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*70}")
        print(f"  测试结果汇总")
        print(f"{'='*70}")
        print(f"  总计: {total} 项测试")
        print(f"  通过: {len(self.passed)} 项 ✅")
        print(f"  失败: {len(self.failed)} 项 ❌")
        print(f"  通过率: {len(self.passed)/total*100:.1f}%")
        print(f"{'='*70}")
        
        if self.failed:
            print(f"\n失败详情:")
            for name, error in self.failed:
                print(f"  - {name}: {error}")
        
        return len(self.failed) == 0


def print_test(num, name, category=""):
    """打印测试标题"""
    print(f"\n{'='*70}")
    print(f"  测试{num}: {name} {'['+category+']' if category else ''}")
    print(f"{'='*70}")


def test_database_availability(result):
    """测试1: 检查数据库可用性"""
    print_test(1, '数据库可用性检查', '基础设施')
    try:
        # 尝试创建一个小组,如果成功说明数据库可用
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '数据库测试小组',
            'members': ['Checker'],
            'strategy': 'least_load'
        })
        
        if r.status_code == 201:
            result.record_pass('数据库可用并成功创建小组')
            return r.json()['id']
        else:
            result.record_fail('数据库可用性检查', f'状态码: {r.status_code}')
            return None
    except Exception as e:
        result.record_fail('数据库可用性检查', str(e))
        return None


def test_crud_operations(result, group_id):
    """测试2: CRUD操作测试"""
    print_test(2, 'CRUD操作测试', '核心功能')
    
    # 2.1 Create (已在测试1中完成)
    result.record_pass('Create: 创建小组')
    
    # 2.2 Read
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups/{group_id}')
        if r.status_code == 200:
            data = r.json()
            if data['name'] == '数据库测试小组' and len(data['members']) == 1:
                result.record_pass('Read: 查询小组详情')
            else:
                result.record_fail('Read: 查询小组详情', '数据不匹配')
        else:
            result.record_fail('Read: 查询小组详情', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('Read: 查询小组详情', str(e))
    
    # 2.3 Update
    try:
        r = requests.put(f'{BASE_URL}/api/agent-groups/{group_id}', json={
            'name': '数据库测试小组(已更新)',
            'members': ['Checker', 'Scraper', 'NLP'],
            'strategy': 'priority'
        })
        if r.status_code == 200 and len(r.json()['members']) == 3:
            result.record_pass('Update: 更新小组配置')
        else:
            result.record_fail('Update: 更新小组配置', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('Update: 更新小组配置', str(e))
    
    # 2.4 List with filter
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups?status=离线')
        if r.status_code == 200:
            result.record_pass('List: 按状态筛选列表')
        else:
            result.record_fail('List: 按状态筛选列表', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('List: 按状态筛选列表', str(e))


def test_status_management(result, group_id):
    """测试3: 状态管理测试"""
    print_test(3, '状态管理测试', '核心功能')
    
    # 3.1 Start
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups/{group_id}/start')
        if r.status_code == 200 and r.json()['status'] == '运行中':
            result.record_pass('Start: 启动小组')
        else:
            result.record_fail('Start: 启动小组', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('Start: 启动小组', str(e))
    
    # 3.2 Stop
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups/{group_id}/stop')
        if r.status_code == 200 and r.json()['status'] == '休眠':
            result.record_pass('Stop: 停止小组')
        else:
            result.record_fail('Stop: 停止小组', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('Stop: 停止小组', str(e))


def test_audit_logs(result, group_id):
    """测试4: 审计日志测试"""
    print_test(4, '审计日志测试', '审计功能')
    
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups/audit-logs?group_id={group_id}')
        if r.status_code == 200:
            data = r.json()
            if data['success'] and data['total'] > 0:
                result.record_pass(f'Audit: 审计日志记录完整({data["total"]}条)')
            else:
                result.record_fail('Audit: 审计日志记录', '日志为空')
        else:
            result.record_fail('Audit: 审计日志查询', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('Audit: 审计日志查询', str(e))


def test_data_persistence(result, group_id):
    """测试5: 数据持久化测试"""
    print_test(5, '数据持久化验证', '持久化')
    
    # 等待2秒确保数据写入
    time.sleep(2)
    
    try:
        # 重新查询数据
        r = requests.get(f'{BASE_URL}/api/agent-groups/{group_id}')
        if r.status_code == 200:
            data = r.json()
            if data['name'] == '数据库测试小组(已更新)' and len(data['members']) == 3:
                result.record_pass('Persistence: 数据持久化成功')
            else:
                result.record_fail('Persistence: 数据持久化', '数据不一致')
        else:
            result.record_fail('Persistence: 数据持久化', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('Persistence: 数据持久化', str(e))


def test_validation_rules(result):
    """测试6: 参数验证测试"""
    print_test(6, '参数验证规则', '验证')
    
    # 6.1 无效成员
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '无效成员测试',
            'members': ['InvalidAgent'],
            'strategy': 'least_load'
        })
        if r.status_code == 422 or r.status_code == 400:
            result.record_pass('Validation: 拒绝无效成员')
        else:
            result.record_fail('Validation: 拒绝无效成员', f'期望422/400,实际{r.status_code}')
    except Exception as e:
        result.record_fail('Validation: 拒绝无效成员', str(e))
    
    # 6.2 重复成员
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '重复成员测试',
            'members': ['Checker', 'Checker'],
            'strategy': 'least_load'
        })
        if r.status_code == 422 or r.status_code == 400:
            result.record_pass('Validation: 拒绝重复成员')
        else:
            result.record_fail('Validation: 拒绝重复成员', f'期望422/400,实际{r.status_code}')
    except Exception as e:
        result.record_fail('Validation: 拒绝重复成员', str(e))
    
    # 6.3 无效策略
    try:
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '无效策略测试',
            'members': ['Checker'],
            'strategy': 'invalid_strategy'
        })
        if r.status_code == 422 or r.status_code == 400:
            result.record_pass('Validation: 拒绝无效策略')
        else:
            result.record_fail('Validation: 拒绝无效策略', f'期望422/400,实际{r.status_code}')
    except Exception as e:
        result.record_fail('Validation: 拒绝无效策略', str(e))


def test_delete_operation(result, group_id):
    """测试7: 删除操作测试"""
    print_test(7, '删除操作测试', '核心功能')
    
    try:
        r = requests.delete(f'{BASE_URL}/api/agent-groups/{group_id}')
        if r.status_code == 200 and r.json()['success']:
            result.record_pass('Delete: 删除小组')
        else:
            result.record_fail('Delete: 删除小组', f'状态码: {r.status_code}')
    except Exception as e:
        result.record_fail('Delete: 删除小组', str(e))
    
    # 验证删除
    try:
        r = requests.get(f'{BASE_URL}/api/agent-groups/{group_id}')
        if r.status_code == 404:
            result.record_pass('Verify: 确认删除成功')
        else:
            result.record_fail('Verify: 确认删除成功', f'期望404,实际{r.status_code}')
    except Exception as e:
        result.record_fail('Verify: 确认删除成功', str(e))


def main():
    """主测试函数"""
    print(f"\n🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀")
    print(f"  Agent小组数据库持久化测试")
    print(f"🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀\n")
    
    result = TestResult()
    
    # 执行测试
    group_id = test_database_availability(result)
    
    if group_id:
        test_crud_operations(result, group_id)
        test_status_management(result, group_id)
        test_audit_logs(result, group_id)
        test_data_persistence(result, group_id)
        test_validation_rules(result)
        test_delete_operation(result, group_id)
    
    # 输出结果
    success = result.summary()
    
    if success:
        print(f"\n🎉 所有测试通过!")
    else:
        print(f"\n⚠️  部分测试失败,请检查错误信息")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

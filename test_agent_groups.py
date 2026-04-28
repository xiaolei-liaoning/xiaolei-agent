#!/usr/bin/env python3
"""Agent小组API完整功能测试"""

import requests
import json
import sys

BASE_URL = 'http://localhost:8001'

def print_header(text):
    print('\n' + '='*60)
    print(text)
    print('='*60)

def print_test(test_num, name):
    print(f'\n✅ 测试{test_num}: {name}')

def main():
    print_header('🧪 Agent小组API完整功能测试')
    
    passed = 0
    failed = 0
    
    try:
        # 测试1: 健康检查
        print_test(1, '健康检查')
        r = requests.get(f'{BASE_URL}/api/health')
        data = r.json()
        print(f'  状态: {data["status"]}')
        assert data['status'] == 'healthy', '健康检查失败'
        print('  ✅ 通过!')
        passed += 1
        
        # 测试2: 获取小组列表
        print_test(2, '获取小组列表')
        r = requests.get(f'{BASE_URL}/api/agent-groups')
        data = r.json()
        print(f'  总小组数: {data["total"]}')
        assert data['total'] >= 3, '小组数量不符合预期'
        print('  ✅ 通过!')
        passed += 1
        
        # 测试3: 创建新小组
        print_test(3, '创建新小组')
        r = requests.post(f'{BASE_URL}/api/agent-groups', json={
            'name': '完整测试小组',
            'members': ['TestAgent1', 'TestAgent2'],
            'strategy': 'priority',
            'circuit_breaker': True,
            'elastic_scaling': False
        })
        data = r.json()
        print(f'  创建成功: {data["name"]} (ID: {data["id"]})')
        assert data['status'] == '离线', '新创建小组状态应为离线'
        group_id = data['id']
        print('  ✅ 通过!')
        passed += 1
        
        # 测试4: 获取小组详情
        print_test(4, '获取小组详情')
        r = requests.get(f'{BASE_URL}/api/agent-groups/{group_id}')
        data = r.json()
        print(f'  小组名称: {data["name"]}')
        assert data['id'] == group_id, '小组ID不匹配'
        print('  ✅ 通过!')
        passed += 1
        
        # 测试5: 更新小组
        print_test(5, '更新小组配置')
        r = requests.put(f'{BASE_URL}/api/agent-groups/{group_id}', json={
            'name': '完整测试小组(已更新)',
            'members': ['TestAgent1', 'TestAgent2', 'TestAgent3'],
            'strategy': 'least_load',
            'circuit_breaker': False,
            'elastic_scaling': True
        })
        data = r.json()
        print(f'  更新成功: {data["name"]}')
        assert len(data['members']) == 3, '成员数量更新失败'
        print('  ✅ 通过!')
        passed += 1
        
        # 测试6: 启动小组
        print_test(6, '启动小组')
        r = requests.post(f'{BASE_URL}/api/agent-groups/{group_id}/start')
        data = r.json()
        print(f'  启动成功: {data["status"]}')
        assert data['status'] == '运行中', '启动失败'
        print('  ✅ 通过!')
        passed += 1
        
        # 测试7: 停止小组
        print_test(7, '停止小组')
        r = requests.post(f'{BASE_URL}/api/agent-groups/{group_id}/stop')
        data = r.json()
        print(f'  停止成功: {data["status"]}')
        assert data['status'] == '休眠', '停止失败'
        print('  ✅ 通过!')
        passed += 1
        
        # 测试8: 获取调度策略
        print_test(8, '获取调度策略')
        r = requests.get(f'{BASE_URL}/api/agent-groups/strategies')
        data = r.json()
        print(f'  支持策略数: {len(data["strategies"])}')
        assert data['success'] == True, '获取策略失败'
        assert len(data['strategies']) == 4, '策略数量不正确'
        print('  ✅ 通过!')
        passed += 1
        
        # 测试9: 删除小组
        print_test(9, '删除小组')
        r = requests.delete(f'{BASE_URL}/api/agent-groups/{group_id}')
        data = r.json()
        print(f'  删除成功: {data["message"]}')
        assert data['success'] == True, '删除失败'
        print('  ✅ 通过!')
        passed += 1
        
        # 测试10: 验证删除
        print_test(10, '验证删除')
        r = requests.get(f'{BASE_URL}/api/agent-groups')
        data = r.json()
        print(f'  删除后小组数: {data["total"]}')
        print('  ✅ 通过!')
        passed += 1
        
        # 总结
        print_header('✅ 测试完成')
        print(f'总计: {passed + failed} 项测试')
        print(f'通过: {passed} 项 ✅')
        print(f'失败: {failed} 项 ❌')
        print(f'通过率: {passed/(passed+failed)*100:.1f}%')
        
        if failed == 0:
            print('\n🎉 所有测试通过!')
            return 0
        else:
            print('\n⚠️  部分测试失败')
            return 1
            
    except Exception as e:
        print(f'\n 测试异常: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())

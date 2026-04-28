#!/usr/bin/env python3
"""OpenClaw工作流引擎技能测试脚本

测试所有核心功能:
1. 创建工作流
2. 验证工作流
3. 获取模板
4. 列出工作流
5. 性能分析
6. 版本管理
7. 导入导出
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from skills.openclaw.handler import get_openclaw_handler


def print_section(title: str):
    """打印分节标题"""
    print('\n' + '='*60)
    print(f'  {title}')
    print('='*60)


def test_create_workflow():
    """测试1: 创建工作流"""
    print_section('测试1: 创建工作流')
    
    handler = get_openclaw_handler()
    
    workflow_def = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "scrape", "type": "tool", "action": "web_scraper", "params": {"url": "https://example.com"}},
            {"id": "analyze", "type": "llm", "model": "gpt-4", "prompt": "分析{{scrape}}的内容"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from_node": "start", "to_node": "scrape"},
            {"from_node": "scrape", "to_node": "analyze"},
            {"from_node": "analyze", "to_node": "end"}
        ]
    }
    
    result = handler.execute('create',
        workflow_id='test_workflow_1',
        definition=workflow_def,
        description='测试工作流 - 网页爬取与分析',
        tags=['测试', '爬虫', '分析']
    )
    
    if result['success']:
        print(f"✅ 工作流创建成功")
        print(f"   ID: {result['workflow_id']}")
        print(f"   文件: {result['file_path']}")
        return True
    else:
        print(f"❌ 工作流创建失败: {result['error']}")
        return False


def test_validate_workflow():
    """测试2: 验证工作流"""
    print_section('测试2: 验证工作流')
    
    handler = get_openclaw_handler()
    
    # 测试有效的工作流
    valid_wf = {
        "nodes": [
            {"id": "node1", "type": "task"},
            {"id": "node2", "type": "task"}
        ],
        "edges": [
            {"from_node": "node1", "to_node": "node2"}
        ]
    }
    
    result = handler.execute('validate', definition=valid_wf)
    if result['success']:
        print(f"✅ 有效工作流验证通过")
        print(f"   节点数: {result['stats']['node_count']}")
        print(f"   边数: {result['stats']['edge_count']}")
    else:
        print(f"❌ 验证失败: {result['errors']}")
        return False
    
    # 测试无效的工作流(缺少必需字段)
    invalid_wf = {
        "nodes": [
            {"type": "task"}  # 缺少id
        ],
        "edges": []
    }
    
    result = handler.execute('validate', definition=invalid_wf)
    if not result['success']:
        print(f"✅ 无效工作流正确被拒绝")
        print(f"   错误: {result['errors']}")
        return True
    else:
        print(f"❌ 无效工作流未被检测到")
        return False


def test_get_template():
    """测试3: 获取模板"""
    print_section('测试3: 获取模板')
    
    handler = get_openclaw_handler()
    
    templates = ['data_pipeline', 'web_scraper_flow', 'analysis_report', 'multi_agent_coordination']
    
    for template_name in templates:
        result = handler.execute('template', template_name=template_name)
        if result['success']:
            template = result['template']
            print(f"✅ 模板 '{template_name}' 获取成功")
            print(f"   名称: {template['name']}")
            print(f"   描述: {template['description']}")
            print(f"   节点数: {len(template['definition']['nodes'])}")
        else:
            print(f"❌ 模板 '{template_name}' 获取失败: {result['error']}")
            return False
    
    # 测试不存在的模板
    result = handler.execute('template', template_name='non_existent')
    if not result['success']:
        print(f"✅ 不存在的模板正确被拒绝")
        return True
    else:
        print(f"❌ 不存在的模板未被检测到")
        return False


def test_list_workflows():
    """测试4: 列出工作流"""
    print_section('测试4: 列出工作流')
    
    handler = get_openclaw_handler()
    
    result = handler.execute('list')
    if result['success']:
        print(f"✅ 工作流列表获取成功")
        print(f"   总数: {result['total']}")
        for wf in result['workflows']:
            print(f"   - {wf['id']}: {wf['description']} (状态: {wf['status']})")
        return True
    else:
        print(f"❌ 获取工作流列表失败: {result.get('error', '未知错误')}")
        return False


def test_analyze_performance():
    """测试5: 性能分析"""
    print_section('测试5: 性能分析')
    
    handler = get_openclaw_handler()
    
    result = handler.execute('analyze', workflow_id='test_workflow_1')
    if result['success']:
        analysis = result['analysis']
        print(f"✅ 性能分析完成")
        print(f"   总节点数: {analysis['total_nodes']}")
        print(f"   总边数: {analysis['total_edges']}")
        print(f"   最大深度: {analysis['max_depth']}")
        print(f"   节点类型分布: {analysis['node_types']}")
        
        if analysis['issues']:
            print(f"   ⚠️  发现问题:")
            for issue in analysis['issues']:
                print(f"      - [{issue['type']}] {issue['message']}")
        
        if analysis['recommendations']:
            print(f"   💡 优化建议:")
            for rec in analysis['recommendations']:
                print(f"      - {rec}")
        
        return True
    else:
        print(f"❌ 性能分析失败: {result['error']}")
        return False


def test_version_management():
    """测试6: 版本管理"""
    print_section('测试6: 版本管理')
    
    handler = get_openclaw_handler()
    
    # 创建版本1.0.0
    result = handler.execute('version', workflow_id='test_workflow_1', version_action='create', version='1.0.0')
    if result['success']:
        print(f"✅ 版本 1.0.0 创建成功")
    else:
        print(f"❌ 版本创建失败: {result['error']}")
        return False
    
    # 创建版本1.1.0
    result = handler.execute('version', workflow_id='test_workflow_1', version_action='create', version='1.1.0')
    if result['success']:
        print(f"✅ 版本 1.1.0 创建成功")
    else:
        print(f"❌ 版本创建失败: {result['error']}")
        return False
    
    # 列出所有版本
    result = handler.execute('version', workflow_id='test_workflow_1', version_action='list')
    if result['success']:
        print(f"✅ 版本列表获取成功")
        print(f"   版本数量: {len(result['versions'])}")
        for v in result['versions']:
            print(f"   - {v['version']} (创建时间: {v['created_at'][:19]})")
    else:
        print(f"❌ 版本列表获取失败: {result['error']}")
        return False
    
    # 回滚到1.0.0
    result = handler.execute('version', workflow_id='test_workflow_1', version_action='rollback', version='1.0.0')
    if result['success']:
        print(f"✅ 回滚到版本 1.0.0 成功")
        return True
    else:
        print(f"❌ 回滚失败: {result['error']}")
        return False


def test_export_import():
    """测试7: 导入导出"""
    print_section('测试7: 导入导出')
    
    handler = get_openclaw_handler()
    
    # 导出为JSON
    result = handler.execute('export', workflow_id='test_workflow_1', format='json')
    if result['success']:
        print(f"✅ JSON导出成功")
        print(f"   格式: {result['format']}")
        exported_data = result['data']
    else:
        print(f"❌ JSON导出失败: {result['error']}")
        return False
    
    # 导出为XML
    result = handler.execute('export', workflow_id='test_workflow_1', format='xml')
    if result['success']:
        print(f"✅ XML导出成功")
        print(f"   格式: {result['format']}")
        print(f"   内容长度: {len(result['data'])} 字符")
    else:
        print(f"❌ XML导出失败: {result['error']}")
        return False
    
    # 保存导出的JSON用于导入测试
    export_file = Path('/tmp/test_workflow_export.json')
    with open(export_file, 'w', encoding='utf-8') as f:
        json.dump(exported_data, f, ensure_ascii=False, indent=2)
    
    # 导入工作流
    result = handler.execute('import', file_path=str(export_file))
    if result['success']:
        print(f"✅ 工作流导入成功")
        print(f"   导入ID: {result['workflow_id']}")
        return True
    else:
        print(f"❌ 导入失败: {result['error']}")
        return False


def test_delete_workflow():
    """测试8: 删除工作流"""
    print_section('测试8: 删除工作流')
    
    handler = get_openclaw_handler()
    
    # 先创建一个临时工作流用于删除测试
    workflow_def = {
        "nodes": [{"id": "temp", "type": "start"}],
        "edges": []
    }
    
    result = handler.execute('create',
        workflow_id='temp_workflow_for_delete',
        definition=workflow_def,
        description='临时工作流'
    )
    
    if not result['success']:
        print(f"❌ 创建临时工作流失败: {result['error']}")
        return False
    
    # 删除工作流
    result = handler.execute('delete', workflow_id='temp_workflow_for_delete')
    if result['success']:
        print(f"✅ 工作流删除成功")
        print(f"   消息: {result['message']}")
        return True
    else:
        print(f"❌ 删除失败: {result['error']}")
        return False


def main():
    """运行所有测试"""
    print('\n' + '🚀'*30)
    print('  OpenClaw工作流引擎技能测试')
    print('🚀'*30)
    
    tests = [
        ('创建工作流', test_create_workflow),
        ('验证工作流', test_validate_workflow),
        ('获取模板', test_get_template),
        ('列出工作流', test_list_workflows),
        ('性能分析', test_analyze_performance),
        ('版本管理', test_version_management),
        ('导入导出', test_export_import),
        ('删除工作流', test_delete_workflow),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n❌ 测试 '{test_name}' 执行异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # 汇总结果
    print_section('测试结果汇总')
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = '✅ 通过' if success else '❌ 失败'
        print(f"{status} - {test_name}")
    
    print(f"\n总计: {total} 项测试")
    print(f"通过: {passed} 项 ✅")
    print(f"失败: {total - passed} 项 ❌")
    print(f"通过率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 项测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())

# OpenClaw工作流引擎 - 快速开始指南

## 🚀 5分钟快速上手

### 1. 导入技能
```python
from skills.openclaw.handler import get_openclaw_handler

handler = get_openclaw_handler()
```

### 2. 使用模板创建工作流
```python
# 获取数据处理模板
template = handler.execute('template', template_name='data_pipeline')

# 查看模板结构
print(template['template']['definition'])
```

### 3. 创建自定义工作流
```python
result = handler.execute('create',
    workflow_id='my_first_workflow',
    definition={
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "task1", "type": "tool", "action": "web_scraper"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from_node": "start", "to_node": "task1"},
            {"from_node": "task1", "to_node": "end"}
        ]
    },
    description='我的第一个工作流'
)

print(f"✅ 创建成功: {result['workflow_id']}")
```

### 4. 验证工作流
```python
validation = handler.execute('validate', 
    definition={...}  # 你的工作流定义
)

if validation['success']:
    print("✅ 验证通过")
else:
    print(f"❌ 验证失败: {validation['errors']}")
```

### 5. 性能分析
```python
analysis = handler.execute('analyze', workflow_id='my_first_workflow')

print(f"节点数量: {analysis['analysis']['total_nodes']}")
print(f"最大深度: {analysis['analysis']['max_depth']}")
print(f"优化建议: {analysis['analysis']['recommendations']}")
```

### 6. 版本管理
```python
# 创建版本
handler.execute('version', 
    workflow_id='my_first_workflow',
    version_action='create',
    version='1.0.0'
)

# 列出所有版本
versions = handler.execute('version',
    workflow_id='my_first_workflow',
    version_action='list'
)

# 回滚到指定版本
handler.execute('version',
    workflow_id='my_first_workflow',
    version_action='rollback',
    version='1.0.0'
)
```

### 7. 导出和分享
```python
# 导出为JSON
export_result = handler.execute('export',
    workflow_id='my_first_workflow',
    format='json'
)

# 保存到文件
import json
with open('my_workflow.json', 'w') as f:
    json.dump(export_result['data'], f, indent=2)
```

---

## 📚 常用操作速查

| 操作 | 代码示例 |
|------|----------|
| **创建工作流** | `handler.execute('create', workflow_id='wf', definition={...})` |
| **列出工作流** | `handler.execute('list')` |
| **删除工作流** | `handler.execute('delete', workflow_id='wf')` |
| **获取模板** | `handler.execute('template', template_name='data_pipeline')` |
| **验证工作流** | `handler.execute('validate', definition={...})` |
| **性能分析** | `handler.execute('analyze', workflow_id='wf')` |
| **创建版本** | `handler.execute('version', workflow_id='wf', version_action='create', version='1.0.0')` |
| **导出JSON** | `handler.execute('export', workflow_id='wf', format='json')` |
| **导入工作流** | `handler.execute('import', file_path='path/to/file.json')` |

---

## 🎯 内置模板说明

### 1. data_pipeline (数据处理流水线)
**适用场景**: 数据采集 → 清洗 → 转换 → 存储

**节点结构**:
```
collect (web_scraper) → clean (filter) → transform → store (database)
```

### 2. web_scraper_flow (网页爬取流程)
**适用场景**: URL输入 → 爬取 → 解析 → 输出

**节点结构**:
```
input (start) → scrape (web_scraper) → parse (LLM) → output (end)
```

### 3. analysis_report (分析报告生成)
**适用场景**: 数据输入 → 分析 → 可视化 → 报告

**节点结构**:
```
data (start) → analyze (data_analysis) → visualize (chart) → report (LLM) → end
```

### 4. multi_agent_coordination (多Agent协调)
**适用场景**: 任务分发 → 并行处理 → 结果汇总

**节点结构**:
```
dispatcher → agent1 (parallel) → agent2 (parallel) → aggregator → end
```

---

## 💡 最佳实践

### 1. 使用模板快速开始
不要从零开始创建工作流,先使用内置模板,然后根据需要修改。

### 2. 定期性能分析
每周运行一次性能分析,及时发现潜在问题。

### 3. 版本管理规范
- 每次重大修改前创建新版本
- 版本号采用语义化格式 (major.minor.patch)
- 保留至少3个历史版本用于回滚

### 4. 工作流命名规范
- 使用有意义的ID: `user_data_pipeline_v2`
- 添加详细描述
- 使用标签分类: `['爬虫', '数据分析']`

### 5. 错误处理
```python
result = handler.execute('create', ...)
if not result['success']:
    print(f"创建失败: {result['error']}")
    # 处理错误
```

---

## ❓ 常见问题

### Q1: 如何检查工作流是否有循环依赖?
```python
validation = handler.execute('validate', definition=workflow_def)
if 'warnings' in validation:
    for warning in validation['warnings']:
        if '循环依赖' in warning:
            print("检测到循环依赖!")
```

### Q2: 如何发现孤立节点?
```python
analysis = handler.execute('analyze', workflow_id='my_wf')
for issue in analysis['analysis']['issues']:
    if '孤立节点' in issue['message']:
        print(f"发现孤立节点: {issue['nodes']}")
```

### Q3: 工作流太深怎么办?
如果 `max_depth > 10`,建议:
- 拆分为多个子工作流
- 使用并行节点减少串行深度
- 考虑使用循环节点替代重复节点

### Q4: 如何备份工作流?
```python
# 导出所有工作流
workflows = handler.execute('list')
for wf in workflows['workflows']:
    export = handler.execute('export', workflow_id=wf['id'], format='json')
    with open(f"backup/{wf['id']}.json", 'w') as f:
        json.dump(export['data'], f, indent=2)
```

---

## 🔗 相关文档

- [完整SKILL.md文档](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/skills/openclaw/SKILL.md)
- [集成报告](file:///Users/leiyuxuan/Desktop/逝去的白月光/OPENCLAW_INTEGRATION_REPORT.md)
- [测试脚本](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/test_openclaw_skill.py)

---

**最后更新**: 2026-04-28  
**版本**: 1.0.0

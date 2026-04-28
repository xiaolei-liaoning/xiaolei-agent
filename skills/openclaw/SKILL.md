# OpenClaw 网格工作流引擎增强技能

## 技能信息

| 属性 | 值 |
|------|------|
| **名称** | OpenClaw工作流引擎 |
| **版本** | 1.0.0 |
| **分类** | 自动化工具 / 工作流管理 |
| **描述** | 提供高级网格工作流功能,包括模板库、版本管理、性能分析和导入导出 |
| **作者** | 小雷版小龙虾团队 |
| **创建时间** | 2026-04-28 |

## 功能特性

### ✅ 核心功能
- **工作流管理**: 创建、删除、列出工作流
- **模板库**: 内置4种常用工作流模板
- **版本控制**: 支持工作流版本管理和回滚
- **性能分析**: 自动检测瓶颈并提供优化建议
- **导入导出**: 支持JSON/XML格式互转

### ✅ 高级特性
- **循环依赖检测**: 自动识别潜在的无限循环
- **孤立节点检测**: 发现未连接的节点
- **深度分析**: 计算工作流执行路径深度
- **智能推荐**: 基于工作流结构给出优化建议

## 支持的操作

| 操作 | 描述 | 必需参数 | 可选参数 |
|------|------|----------|----------|
| `create` | 创建工作流 | workflow_id, definition | description, tags |
| `execute` | 执行工作流 | workflow_id 或 definition | input_data |
| `validate` | 验证工作流定义 | definition | - |
| `list` | 列出所有工作流 | - | tag, status |
| `delete` | 删除工作流 | workflow_id | - |
| `template` | 获取模板 | template_name | - |
| `version` | 版本管理 | workflow_id, action | version |
| `analyze` | 性能分析 | workflow_id | - |
| `export` | 导出工作流 | workflow_id | format (json/xml) |
| `import` | 导入工作流 | file_path | - |

## 内置模板

### 1. data_pipeline (数据处理流水线)
```
数据采集 → 清洗 → 转换 → 存储
```
适用场景: 网页爬取后的数据处理流程

### 2. web_scraper_flow (网页爬取流程)
```
URL输入 → 爬取 → 解析 → 输出
```
适用场景: 自动化网页内容提取

### 3. analysis_report (分析报告生成)
```
数据输入 → 分析 → 可视化 → 报告
```
适用场景: 自动生成数据分析报告

### 4. multi_agent_coordination (多Agent协调)
```
任务分发 → 并行处理 → 结果汇总
```
适用场景: 多Agent协同完成任务

## 使用示例

### 创建工作流
```python
from skills.openclaw.handler import get_openclaw_handler

handler = get_openclaw_handler()

result = handler.execute('create',
    workflow_id='my_workflow',
    definition={
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "scrape", "type": "tool", "action": "web_scraper"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from_node": "start", "to_node": "scrape"},
            {"from_node": "scrape", "to_node": "end"}
        ]
    },
    description='我的第一个工作流',
    tags=['爬虫', '测试']
)
```

### 获取模板
```python
result = handler.execute('template', template_name='data_pipeline')
print(result['template']['definition'])
```

### 性能分析
```python
result = handler.execute('analyze', workflow_id='my_workflow')
print(f"节点数量: {result['analysis']['total_nodes']}")
print(f"潜在问题: {result['analysis']['issues']}")
print(f"优化建议: {result['analysis']['recommendations']}")
```

### 版本管理
```python
# 创建新版本
handler.execute('version', workflow_id='my_workflow', action='create', version='1.1.0')

# 列出所有版本
versions = handler.execute('version', workflow_id='my_workflow', action='list')

# 回滚到指定版本
handler.execute('version', workflow_id='my_workflow', action='rollback', version='1.0.0')
```

### 导出工作流
```python
# 导出为JSON
result = handler.execute('export', workflow_id='my_workflow', format='json')

# 导出为XML
result = handler.execute('export', workflow_id='my_workflow', format='xml')
```

## 工作流定义格式

```json
{
  "nodes": [
    {
      "id": "node1",
      "type": "task",
      "action": "calculate",
      "params": {
        "a": 10,
        "b": 5,
        "operation": "add"
      }
    },
    {
      "id": "node2", 
      "type": "llm",
      "model": "gpt-4",
      "prompt": "分析{{node1}}的结果"
    }
  ],
  "edges": [
    {"from_node": "node1", "to_node": "node2"}
  ]
}
```

## 节点类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `start` | 开始节点 | 工作流入口 |
| `end` | 结束节点 | 工作流出口 |
| `task` | 任务节点 | 数据处理、计算等 |
| `llm` | LLM节点 | 调用大语言模型 |
| `tool` | 工具节点 | 调用已注册的技能 |
| `condition` | 条件节点 | 分支逻辑判断 |
| `loop` | 循环节点 | 数组/次数/条件循环 |
| `parallel` | 并行节点 | 并行执行多个子任务 |

## 与现有工作流引擎的关系

### 互补关系
- **workflow_engine.py**: 核心执行引擎,负责实际的工作流运行
- **openclaw/handler.py**: 管理层,提供工作流的CRUD、版本控制、模板等功能

### 集成方式
OpenClaw技能可以作为工作流的管理层,与现有的 `workflow_engine.py` 配合使用:
1. 使用OpenClaw创建和管理工作流定义
2. 调用 `workflow_engine.py` 执行工作流
3. 使用OpenClaw进行性能分析和优化

## 依赖声明

### Python依赖
- 无额外依赖(使用Python标准库)

### 系统依赖
- 需要访问 `workflows/openclaw/` 目录的读写权限

## 注意事项

1. **工作流ID唯一性**: 每个工作流必须有唯一的ID
2. **节点ID唯一性**: 同一工作流内节点ID不能重复
3. **循环依赖**: 系统会检测循环依赖,但允许 intentional cycles(如循环节点)
4. **版本管理**: 版本采用语义化版本号(SemVer 2.0)
5. **文件大小**: 大型工作流建议使用外部存储(数据库)

## 最佳实践

### 1. 使用模板快速开始
```python
# 先获取模板
template = handler.execute('template', template_name='data_pipeline')

# 修改后创建自己的工作流
workflow_def = template['template']['definition']
workflow_def['nodes'].append({...})  # 添加自定义节点

handler.execute('create', workflow_id='my_custom_wf', definition=workflow_def)
```

### 2. 定期性能分析
```python
# 每周运行一次性能分析
result = handler.execute('analyze', workflow_id='production_workflow')
if result['analysis']['issues']:
    print("发现潜在问题,建议优化")
```

### 3. 版本管理规范
```python
# 每次重大修改前创建新版本
handler.execute('version', workflow_id='wf', action='create', version='2.0.0')

# 如果出现问题,快速回滚
handler.execute('version', workflow_id='wf', action='rollback', version='1.9.0')
```

## 故障排查

### 问题1: 工作流创建失败
**症状**: 返回 `success: false`, error提示验证失败  
**解决**: 检查 `errors` 字段,常见原因:
- 节点缺少 `id` 字段
- 边引用了不存在的节点
- 节点ID重复

### 问题2: 性能分析显示深度过大
**症状**: `max_depth > 10`  
**解决**: 
- 将工作流拆分为多个子工作流
- 使用并行节点减少串行深度
- 考虑使用循环节点替代重复节点

### 问题3: 检测到孤立节点
**症状**: `issues` 中包含孤立节点警告  
**解决**: 
- 检查是否忘记连接某些节点
- 如果是有意的(如注释节点),可以忽略

## 更新日志

### v1.0.0 (2026-04-28)
- ✅ 初始版本发布
- ✅ 支持10种核心操作
- ✅ 内置4个工作流模板
- ✅ 版本管理和性能分析
- ✅ JSON/XML导出支持

## 许可证

本项目遵循 MIT 许可证

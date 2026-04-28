# XMI到多任务工作流转换器使用指南

## 📖 概述

这个工具可以将XMI文件（UML活动图、BPMN流程等）自动转换为可执行的多任务处理提示词或JSON格式的工作流定义。

## 🚀 快速开始

### 1. 基本用法

```python
from skills.xmi_converter import convert_xmi_to_workflow

# 方式1: 从文件路径转换
result = convert_xmi_to_workflow(
    xmi_file_path="path/to/your/workflow.xmi",
    output_format="prompt"  # 或 "json"
)
print(result)

# 方式2: 从字符串内容转换
xmi_content = open("workflow.xmi").read()
result = convert_xmi_to_workflow(xmi_content=xmi_content)
print(result)
```

### 2. 输出格式

#### 格式A: 多任务提示词（默认）
生成人类可读的执行步骤说明：

```markdown
# 多任务工作流执行计划

**工作流名称**: 数据分析工作流
**节点数量**: 8
**生成时间**: 2026-04-21T18:30:00

## 执行步骤

### 步骤 1: 开始
- **类型**: start

### 步骤 2: 获取用户输入
- **类型**: task
- **描述**: 接收用户的分析需求

### 步骤 3: 查询天气数据
- **类型**: tool
- **调用工具**: weather_api

### 步骤 4: 数据预处理
- **类型**: task
- **描述**: 清洗和格式化数据

...
```

#### 格式B: JSON工作流
生成可直接执行的JSON格式：

```json
{
  "id": "wf_20260421_183000",
  "name": "数据分析工作流",
  "description": "...",
  "nodes": [
    {
      "id": "start",
      "name": "开始",
      "type": "start",
      "config": {...}
    },
    ...
  ],
  "edges": [...],
  "created_at": "2026-04-21T18:30:00"
}
```

## 📋 支持的XMI类型

### ✅ 已支持
- UML活动图 (Activity Diagram)
- BPMN业务流程 (Business Process)
- 通用XMI节点和边

### 🔧 节点类型映射

| XMI类型 | 转换后类型 | 说明 |
|---------|-----------|------|
| InitialNode | start | 开始节点 |
| FinalNode / ActivityFinalNode | end | 结束节点 |
| Action | task | 普通任务 |
| CallOperationAction | tool | 工具调用 |
| DecisionNode | condition | 条件判断 |
| ForkNode | parallel | 并行分支 |
| JoinNode | join | 并行合并 |
| Task | task | 任务 |
| ServiceTask | tool | 服务调用 |

## 💡 使用场景

t## 场景1: AI能分析XMI，但无法直接执行工作流

**问题**:
```
用户上传XMI文件 → AI分析内容 → 但不知道如何执行
```

**解决方案**:
```python
# 1. 解析XMI
from skills.xmi_converter import convert_xmi_to_workflow

xmi_file = "my_workflow.xmi"
prompt = convert_xmi_to_workflow(xmi_file_path=xmi_file)

# 2. 将生成的提示词发给AI
ai_response = call_llm(f"""
请按照以下工作流执行任务：

{prompt}

现在开始执行步骤1...
""")
```

### 场景2: 将XMI导入到工作流引擎

```python
# 转换为JSON格式
json_workflow = convert_xmi_to_workflow(
    xmi_file_path="workflow.xmi",
    output_format="json"
)

# 保存到工作流目录
import json
from pathlib import Path

workflow_dir = Path("workflows")
workflow_file = workflow_dir / f"{json_workflow['id']}.json"
with open(workflow_file, 'w') as f:
    json.dump(json.loads(json_workflow), f, indent=2)

print(f"✅ 工作流已保存: {workflow_file}")
```

### 场景3: 批量转换多个XMI文件

```python
from pathlib import Path

xmi_dir = Path("xmi_files")
for xmi_file in xmi_dir.glob("*.xmi"):
    print(f"处理: {xmi_file.name}")
    
    try:
        # 默认转换为多任务提示词
        prompt = convert_xmi_to_workflow(xmi_file_path=str(xmi_file))
        
        # 保存为文本文件
        output_file = xmi_file.with_suffix('.txt')
        with open(output_file, 'w') as f:
            f.write(prompt)
        
        # 可选：转换为JSON格式
        # json_workflow = convert_xmi_to_workflow(
        #     xmi_file_path=str(xmi_file),
        #     output_format="json"
        # )
        # json_output_file = xmi_file.with_suffix('.json')
        # with open(json_output_file, 'w') as f:
        #     f.write(json_workflow)
        
        print(f"✅ 已转换: {output_file.name}")
    except Exception as e:
        print(f"❌ 失败: {e}")
```

## 🔧 高级用法

### 自定义解析器

```python
from skills.xmi_converter import XMIParser, WorkflowConverter

# 1. 解析XMI
parser = XMIParser(xmi_file_path="workflow.xmi")
parsed_data = parser.parse()

# 2. 查看解析结果
print(f"节点数: {len(parsed_data['nodes'])}")
print(f"边数: {len(parsed_data['edges'])}")
print(f"元数据: {parsed_data['metadata']}")

# 3. 自定义转换
converter = WorkflowConverter(parsed_data)
prompt = converter.convert_to_multitask_prompt()
```

### 错误处理

```python
try:
    result = convert_xmi_to_workflow(xmi_file_path="invalid.xmi")
except FileNotFoundError:
    print("文件不存在")
except Exception as e:
    print(f"解析失败: {e}")
    import traceback
    traceback.print_exc()
```

## 📊 示例

### 示例1: 简单线性流程

**输入XMI**:
```xml
<uml:Activity name="问候流程">
    <node xmi:type="uml:InitialNode" name="开始"/>
    <node xmi:type="uml:Action" name="说你好"/>
    <node xmi:type="uml:ActivityFinalNode" name="结束"/>
</uml:Activity>
```

**输出提示词**:
```markdown
# 多任务工作流执行计划

**工作流名称**: 问候流程

## 执行步骤

### 步骤 1: 开始
- **类型**: start

### 步骤 2: 说你好
- **类型**: task

### 步骤 3: 结束
- **类型**: end
```

### 示例2: 带条件的分支流程

**输入XMI**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
    <uml:Activity name="年龄判断流程">
        <node xmi:type="uml:DecisionNode" name="判断年龄" id="decision"/>
        <node xmi:type="uml:Action" name="成人处理" id="adult"/>
        <node xmi:type="uml:Action" name="儿童处理" id="child"/>
        <edge source="decision" target="adult">
            <guard specification="age >= 18"/>
        </edge>
        <edge source="decision" target="child">
            <guard specification="age < 18"/>
        </edge>
    </uml:Activity>
</xmi:XMI>
```

**输出提示词**:
```markdown
## 条件分支

- **如果** age >= 18: 执行 adult
- **如果** age < 18: 执行 child
```

## 🎯 与Agent集成

### 在聊天API中使用

```python
@app.post("/api/chat")
async def chat(request: ChatRequest):
    message = request.message
    
    # 检测是否包含XMI文件
    if has_xmi_attachment(message):
        xmi_content = extract_xmi(message)
        
        # 转换为多任务提示词
        workflow_prompt = convert_xmi_to_workflow(xmi_content=xmi_content)
        
        # 执行工作流
        result = await execute_workflow(workflow_prompt)
        
        return ChatResponse(reply=result)
    
    # 普通聊天逻辑
    ...
```

### 在工作流编辑器中使用

```python
# 前端上传XMI文件
@app.post("/api/workflow/import-xmi")
async def import_xmi(file: UploadFile):
    xmi_content = await file.read()
    
    # 转换
    json_workflow = convert_xmi_to_workflow(
        xmi_content=xmi_content.decode('utf-8'),
        output_format="json"
    )
    
    # 保存
    workflow_data = json.loads(json_workflow)
    save_workflow(workflow_data)
    
    return {"success": True, "workflow_id": workflow_data['id']}
```

## ❓ 常见问题

### Q1: XMI文件解析失败？

**检查**:
1. XML格式是否正确
2. 编码是否为UTF-8
3. 命名空间是否标准

**解决**:
```python
# 尝试手动修复XML
import xml.etree.ElementTree as ET
try:
    tree = ET.parse("workflow.xmi")
    print("XML格式正确")
except ET.ParseError as e:
    print(f"XML错误: {e}")
```

### Q2: 节点类型为"unknown"？

**原因**: XMI中使用了不支持的节点类型

**解决**: 在`_map_node_type`方法中添加映射：
```python
type_mapping['YourCustomType'] = 'task'
```

### Q3: 边（连接关系）丢失？

**检查**: XMI中边的source和target属性是否正确

**调试**:
```python
parser = XMIParser(xmi_file_path="workflow.xmi")
parsed = parser.parse()
print("边:", parsed['edges'])
```

## 📝 最佳实践

1. **标准化XMI**: 使用标准的UML或BPMN工具导出XMI
2. **添加描述**: 在节点中添加documentation元素，便于理解
3. **测试转换**: 先在小型XMI文件上测试，确认转换正确
4. **保存中间结果**: 保留解析后的JSON，便于调试

## 🔗 相关资源

- [UML规范](https://www.omg.org/spec/UML/)
- [BPMN规范](https://www.omg.org/spec/BPMN/)
- [XMI规范](https://www.omg.org/spec/XMI/)

---

**版本**: v1.0  
**最后更新**: 2026-04-21  
**作者**: 小雷版小龙虾团队
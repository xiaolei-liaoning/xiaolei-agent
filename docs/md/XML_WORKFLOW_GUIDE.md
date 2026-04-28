# XML工作流映射系统使用说明

## 🎯 功能概述

XML工作流映射系统允许您直接执行XML格式的工作流，无需先转换为JSON文件。系统会自动将XML结构映射为可执行的JSON格式，然后直接执行。

## ✨ 核心特性

### 1. **直接执行**
- ✅ 无需保存为JSON文件
- ✅ 内存中直接映射和执行
- ✅ 提高执行效率

### 2. **完整的节点支持**
- ✅ `start` - 开始节点
- ✅ `llm` - LLM节点
- ✅ `tool` - 工具节点
- ✅ `condition` - 条件节点
- ✅ `end` - 结束节点

### 3. **智能映射**
- ✅ XML结构到JSON结构的自动映射
- ✅ 配置参数的自动转换
- ✅ 连线关系的自动处理

### 4. **变量替换**
- ✅ 支持`{{input}}`引用用户输入
- ✅ 支持`{{node_id}}`引用节点结果
- ✅ 支持嵌套变量`{{key.subkey}}`

## 📋 XML格式规范

### 基础结构
```xml
<?xml version="1.0" encoding="UTF-8"?>
<workflow name="工作流名称" description="工作流描述">
    <nodes>
        <!-- 节点定义 -->
    </nodes>
    <edges>
        <!-- 连线定义 -->
    </edges>
</workflow>
```

### 节点类型

#### 1. 开始节点 (start)
```xml
<node id="start" type="start">
    <config>
        <input>用户输入</input>
    </config>
</node>
```

#### 2. LLM节点 (llm)
```xml
<node id="llm_node" type="llm">
    <config>
        <prompt>用户说：{{input}}。请友好回复。</prompt>
        <model>glm-4-flash</model>
    </config>
</node>
```

#### 3. 工具节点 (tool)
```xml
<node id="tool_node" type="tool">
    <config>
        <tool>weather</tool>
        <params>
            <city>北京</city>
        </params>
    </config>
</node>
```

#### 4. 条件节点 (condition)
```xml
<node id="condition_node" type="condition">
    <config>
        <condition>{{previous_result}} == 'yes'</condition>
    </config>
</node>
```

#### 5. 结束节点 (end)
```xml
<node id="end" type="end">
    <config>
        <output>{{llm_node}}</output>
    </config>
</node>
```

### 连线定义
```xml
<edges>
    <edge source="start" target="llm_node" condition=""/>
    <edge source="llm_node" target="end" condition=""/>
</edges>
```

## 🚀 使用方法

### 方法1: 直接执行XML工作流

```python
import asyncio
from skills.workflow_engine import workflow_engine

async def execute_xml_workflow():
    # XML工作流内容
    xml_workflow = """<?xml version="1.0" encoding="UTF-8"?>
<workflow name="我的工作流" description="示例工作流">
    <nodes>
        <node id="start" type="start">
            <config><input>用户输入</input></config>
        </node>
        <node id="llm" type="llm">
            <config>
                <prompt>用户说：{{input}}。请回复。</prompt>
                <model>glm-4-flash</model>
            </config>
        </node>
        <node id="end" type="end">
            <config><output>{{llm}}</output></config>
        </node>
    </nodes>
    <edges>
        <edge source="start" target="llm" condition=""/>
        <edge source="llm" target="end" condition=""/>
    </edges>
</workflow>"""
    
    # 执行工作流
    result = await workflow_engine.execute_xml_workflow(
        xml_workflow, 
        {"input": "你好"}
    )
    
    if result["success"]:
        print(f"结果: {result['result']}")
    else:
        print(f"错误: {result['error']}")

# 运行
asyncio.run(execute_xml_workflow())
```

### 方法2: 使用XML映射器

```python
from core.xml_workflow_mapper import xml_workflow_mapper

# 解析XML工作流
parse_result = xml_workflow_mapper.parse_xml_workflow(xml_content)

if parse_result["success"]:
    workflow = parse_result["workflow"]
    print(f"工作流名称: {workflow['name']}")
    print(f"节点数量: {len(workflow['nodes'])}")
    print(f"连线数量: {len(workflow['edges'])}")
```

## 📊 测试结果

所有测试均通过 ✅

### 测试1: 基础对话工作流
- ✅ 状态: 成功
- ✅ 变量替换: 正常
- ✅ LLM调用: 正常
- ✅ 结果返回: 正常

### 测试2: 多步骤工作流
- ✅ 状态: 成功
- ✅ 多节点执行: 正常
- ✅ 数据传递: 正常
- ✅ 结果整合: 正常

### 测试3: 条件分支工作流
- ✅ 状态: 成功
- ✅ 条件判断: 正常
- ✅ 分支执行: 正常
- ✅ 结果返回: 正常

### 测试4: 工具调用工作流
- ✅ 状态: 成功
- ✅ 工具调用: 正常
- ✅ 参数传递: 正常
- ✅ 结果返回: 正常

## 🔧 高级功能

### 1. 嵌套配置
```xml
<node id="tool_node" type="tool">
    <config>
        <tool>web_scraper</tool>
        <params>
            <site>weibo</site>
            <action>hot_search</action>
            <top_n>10</top_n>
        </params>
    </config>
</node>
```

### 2. 条件分支
```xml
<edges>
    <edge source="condition_node" target="branch_a" condition="true"/>
    <edge source="condition_node" target="branch_b" condition="false"/>
</edges>
```

### 3. 多变量引用
```xml
<node id="llm" type="llm">
    <config>
        <prompt>用户说：{{input}}。工具结果：{{tool_result}}。请综合回复。</prompt>
        <model>glm-4-flash</model>
    </config>
</node>
```

## 📝 注意事项

1. **节点ID唯一性**: 确保所有节点的ID都是唯一的
2. **连线有效性**: 确保所有连线的source和target都指向存在的节点
3. **开始和结束节点**: 每个工作流必须有且仅有一个开始节点和一个结束节点
4. **变量命名**: 变量名区分大小写，确保引用的变量名与节点ID一致
5. **XML格式**: 确保XML格式正确，所有标签都正确闭合

## 🎯 最佳实践

1. **命名规范**: 使用有意义的节点ID，如`start`, `llm_response`, `end`
2. **注释说明**: 在workflow的description中添加工作流说明
3. **错误处理**: 检查执行结果的success字段，处理可能的错误
4. **日志记录**: 使用logger记录工作流执行过程
5. **测试验证**: 执行前先进行测试，确保工作流逻辑正确

## 🔍 故障排除

### 问题1: XML解析失败
**原因**: XML格式错误
**解决**: 检查XML语法，确保所有标签正确闭合

### 问题2: 节点映射失败
**原因**: 节点类型不支持或配置错误
**解决**: 检查节点类型是否在支持列表中，配置是否正确

### 问题3: 变量替换失败
**原因**: 变量名不匹配或上下文缺失
**解决**: 检查变量名是否与节点ID一致，确保上下文数据完整

### 问题4: 执行失败
**原因**: 工作流逻辑错误或依赖服务不可用
**解决**: 检查工作流逻辑，确认依赖服务（如LLM、工具）可用

## 📚 相关文件

- `core/xml_workflow_mapper.py` - XML映射器实现
- `skills/workflow_engine.py` - 工作流引擎
- `test_xml_complete.py` - 完整测试脚本
- `test_xml_direct_execution.py` - 直接执行测试

## 🎉 总结

XML工作流映射系统提供了强大而灵活的工作流执行能力，支持直接执行XML格式的工作流，无需预先转换为JSON文件。系统具有完整的节点支持、智能映射和变量替换功能，能够满足各种复杂的工作流需求。
# 工具调用智能回复 - 快速参考

## 🚀 5分钟上手

### 1. 基础用法

```python
from core.tool_result_formatter import ToolResultFormatter

formatter = ToolResultFormatter(enable_self_check=True)

response = await formatter.format_response(
    user_query="帮我处理这些文件",
    tool_result={
        "tool_name": "file_processor",
        "success": True,
        "result": {"output_path": "/Users/xxx/Desktop/output.pdf"},
        "execution_time": 3.5,
        "timestamp": "2026-04-28T18:00:00"
    }
)

print(response.full_reply)
```

### 2. 输出格式

```
✅ 已完成文件处理

📋 **概述**
[处理了什么，得到了什么]

⏱️ **耗时**
[执行耗时]秒

📁 **文件位置**
[文件路径]

🕐 **完成时间**
[日期时间]

💡 **下一步建议**
[后续操作建议]
```

---

## ⚙️ 配置速查

### 初始化配置

```python
# 启用自检（高质量，较慢）
formatter = ToolResultFormatter(
    enable_self_check=True,
    pass_score=80
)

# 关闭自检（快速，无质量保障）
formatter = ToolResultFormatter(enable_self_check=False)
```

### 场景推荐

| 场景 | enable_self_check | pass_score | 说明 |
|------|------------------|-----------|------|
| 日常使用 | False | - | 追求速度 |
| 重要操作 | True | 85 | 高质量要求 |
| 调试模式 | True | 75 | 详细日志 |

---

## 📊 关键API

### format_response

```python
response = await formatter.format_response(
    user_query="用户请求",      # 必填
    tool_result={},             # 必填
    context=None,               # 可选上下文
    enable_self_check=None      # 覆盖默认设置
)
```

### 返回对象

```python
response.overview          # 概述
response.execution_time    # 耗时
response.file_location     # 文件位置
response.completion_time   # 完成时间
response.full_reply        # 完整回复
response.is_success        # 是否成功
response.quality_score     # 质量评分
```

---

## 💡 常用示例

### 文件处理

```python
tool_result = {
    "tool_name": "pdf_merger",
    "success": True,
    "result": {
        "processed_files": 5,
        "output_path": "/Users/xxx/Desktop/merged.pdf",
        "total_pages": 120
    },
    "execution_time": 3.5,
    "timestamp": datetime.now().isoformat()
}
```

### API调用

```python
tool_result = {
    "tool_name": "weather_api",
    "success": True,
    "result": {
        "city": "北京",
        "temperature": 25,
        "condition": "晴"
    },
    "execution_time": 1.2,
    "timestamp": datetime.now().isoformat()
}
```

### 失败场景

```python
tool_result = {
    "tool_name": "file_converter",
    "success": False,
    "error": "文件格式不支持",
    "result": {},
    "execution_time": 0.3,
    "timestamp": datetime.now().isoformat()
}
```

---

## 🔧 集成到TaskExecutor

```python
# 在 core/task_executor.py 中
from .tool_result_formatter import get_tool_result_formatter

class TaskExecutor:
    def __init__(self):
        self.formatter = get_tool_result_formatter(enable_self_check=False)
    
    async def execute_task(self, task):
        # ... 执行工具 ...
        
        tool_result = {
            "tool_name": task.tool_name,
            "success": success,
            "result": result_data,
            "execution_time": elapsed_time,
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.formatter.format_response(
            user_query=task.user_query,
            tool_result=tool_result
        )
        
        return response.full_reply  # 返回智能回复
```

---

## 📈 性能指标

| 指标 | 无自检 | 有自检 |
|------|--------|--------|
| 平均耗时 | 5-8秒 | 25-35秒 |
| 质量评分 | 未知 | 70-90分 |
| 内存占用 | <1MB | <1MB |

---

## ❓ 常见问题

### Q1: 如何提升速度？

**A**: 关闭自检
```python
formatter = ToolResultFormatter(enable_self_check=False)
```

### Q2: 文件路径未显示？

**A**: 确保工具返回正确的字段名
```python
result = {
    "output_path": "/path/to/file",  # 或 file_path, path
}
```

### Q3: 如何自定义回复格式？

**A**: 修改 [_build_generation_prompt](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/core/tool_result_formatter.py#L270-L335) 方法

---

## 📚 更多资源

- **完整指南**: [TOOL_RESULT_FORMATTER_GUIDE.md](./TOOL_RESULT_FORMATTER_GUIDE.md)
- **测试报告**: [TOOL_RESULT_FORMATTER_TEST_REPORT.md](./TOOL_RESULT_FORMATTER_TEST_REPORT.md)
- **测试代码**: [tests/test_tool_result_formatter.py](../tests/test_tool_result_formatter.py)

---

**版本**: 1.0.0  
**更新**: 2026-04-28

# 沙盒隔离执行 - 快速参考

## 🚀 快速开始

### 1. 基本使用

```python
from tools.tool_manager import ToolManager

tm = ToolManager.get_instance()

# 执行Python代码
result = await tm.execute_in_sandbox(
    code="print('Hello World')",
    language="python"
)
```

### 2. 带上下文变量

```python
result = await tm.execute_in_sandbox(
    code="print(f'你好, {name}!')",
    language="python",
    context={"name": "张三"}
)
```

### 3. 自定义资源限制

```python
result = await tm.execute_in_sandbox(
    code="your_code_here",
    language="python",
    timeout=10,           # 10秒超时
    max_memory_mb=256     # 256MB内存限制
)
```

## 📋 支持的语言

| 语言 | 参数 | 要求 |
|------|------|------|
| Python | `"python"` | 无 |
| JavaScript | `"javascript"` | 需要Node.js |
| Shell | `"shell"` | 无 |

## 🔒 安全特性

### 禁止的模块
`os`, `sys`, `subprocess`, `socket`, `requests`, `urllib`, `pickle`, `sqlite3` 等20+个危险模块

### 禁止的函数
`eval()`, `exec()`, `__import__()`, `compile()`

### 禁止的Shell命令
`rm -rf /`, `mkfs`, `dd`, Fork炸弹等

## 📊 返回结果

```python
{
    "success": True/False,      # 是否成功
    "result": "...",            # 执行结果
    "stdout": "...",            # 标准输出
    "stderr": "...",            # 标准错误
    "exit_code": 0,             # 退出码
    "execution_time": 0.123,    # 执行时间（秒）
    "status": "completed",      # 状态
    "sandbox_id": "abc123",     # 沙盒ID
    "error": None               # 错误信息
}
```

## ⚠️ 常见错误

### 1. 超时错误
```python
# 原因：代码执行时间超过timeout限制
result["status"] == "timeout"
# 解决：增加timeout值或优化代码
```

### 2. 安全拦截
```python
# 原因：尝试导入禁止的模块或使用危险的函数
result["error"] == "禁止导入模块: os"
# 解决：移除危险代码
```

### 3. 内存超限
```python
# 原因：使用的内存超过max_memory_mb限制
# 解决：增加内存限制或优化代码
```

## 🧪 测试

```bash
# 运行完整测试
python test_sandbox_integration.py

# 运行基础沙盒测试
python test_sandbox.py
```

## 💡 最佳实践

1. **始终设置超时**：避免无限等待
2. **限制内存使用**：根据任务复杂度调整
3. **检查执行结果**：处理失败情况
4. **不信任用户输入**：即使经过LLM处理也要在沙盒中执行

## 📖 更多信息

- [完整集成指南](SANDBOX_INTEGRATION_GUIDE.md)
- [沙盒执行器源码](core/sandbox_executor.py)
- [工具管理器源码](tools/tool_manager.py)
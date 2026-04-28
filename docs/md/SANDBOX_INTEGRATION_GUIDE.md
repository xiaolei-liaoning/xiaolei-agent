# 沙盒隔离执行集成指南

## 📋 概述

本项目已集成完整的代码沙盒隔离执行系统，所有代码执行操作都在安全隔离的环境中进行，防止恶意代码对系统造成损害。

## ✅ 已完成集成

### 1. 沙盒执行器核心功能

位置：`core/sandbox_executor.py`

**支持的语言**：
- Python（完整支持）
- JavaScript（需要Node.js）
- Shell命令（受限执行）

**安全特性**：
- ✅ 禁止导入危险模块（os, sys, subprocess, socket等20+个模块）
- ✅ 禁止使用危险函数（eval, exec, __import__, compile）
- ✅ 资源限制（超时、内存、CPU、输出大小）
- ✅ 进程组隔离（setsid）
- ✅ 环境变量限制（PATH, PYTHONPATH, HOME）
- ✅ 自动清理临时文件
- ✅ 强制终止能力

### 2. 工具管理器集成

位置：`tools/tool_manager.py`

**新增功能**：
- `execute_in_sandbox()` - 异步沙盒执行方法
- `code_sandbox` 工具 - 统一的代码执行入口

**使用方法**：

```python
from tools.tool_manager import ToolManager

tm = ToolManager.get_instance()

# 方法1：直接调用沙盒执行
result = await tm.execute_in_sandbox(
    code="print('Hello World')",
    language="python",
    timeout=30,
    max_memory_mb=512
)

# 方法2：通过工具注册表调用
handler = tm.get_tool("code_sandbox")
result = await handler.execute(
    code="print('Hello World')",
    language="python"
)
```

## 🚀 使用示例

### 示例1：执行Python代码

```python
from tools.tool_manager import ToolManager

tm = ToolManager.get_instance()

# 简单计算
result = await tm.execute_in_sandbox(
    code="""
result = 2 + 3 * 4
print(f"计算结果: {result}")
""",
    language="python"
)

print(result)
# {
#   "success": true,
#   "result": "计算结果: 14\n",
#   "stdout": "计算结果: 14\n",
#   "stderr": "",
#   "execution_time": 0.023,
#   "status": "completed"
# }
```

### 示例2：带上下文变量的执行

```python
# 注入变量到沙盒环境
result = await tm.execute_in_sandbox(
    code="""
greeting = f"你好, {username}! 你今年{age}岁。"
print(greeting)
""",
    language="python",
    context={
        "username": "张三",
        "age": 25
    }
)
```

### 示例3：执行JavaScript代码

```python
result = await tm.execute_in_sandbox(
    code="""
const numbers = [1, 2, 3, 4, 5];
const sum = numbers.reduce((a, b) => a + b, 0);
console.log(`总和: ${sum}`);
""",
    language="javascript"
)
```

### 示例4：执行Shell命令

```python
result = await tm.execute_in_sandbox(
    code="echo 'Hello from Shell' && ls -la /tmp | head -5",
    language="shell",
    timeout=10
)
```

### 示例5：自定义资源限制

```python
result = await tm.execute_in_sandbox(
    code="import time; time.sleep(60)",  # 尝试长时间运行
    language="python",
    timeout=5,  # 5秒超时
    max_memory_mb=128  # 限制128MB内存
)

# 结果会是超时状态
# {
#   "success": false,
#   "status": "timeout",
#   "error": "执行超时（5秒）"
# }
```

## 🔒 安全防护

### 1. 模块导入限制

以下模块被禁止导入：
```python
# ❌ 这些会触发安全错误
import os
import sys
import subprocess
import socket
import requests
import urllib
import pickle
import sqlite3
# ... 等20+个危险模块
```

### 2. 危险函数限制

```python
# ❌ 这些函数被禁止使用
eval("1+1")
exec("print('hack')")
__import__("os")
compile("code", "<string>", "exec")
```

### 3. Shell命令限制

```python
# ❌ 这些命令被禁止
rm -rf /
mkfs
dd if=/dev/zero of=/dev/sda
:(){:|:&};:  # Fork炸弹
> /dev/sda
```

### 4. 代码长度限制

最大代码长度：**10,000字符**

## 📊 执行结果格式

所有沙盒执行返回统一格式：

```python
{
    "success": bool,           # 是否成功
    "result": str,             # 执行结果（stdout）
    "stdout": str,             # 标准输出
    "stderr": str,             # 标准错误
    "exit_code": int,          # 退出码
    "execution_time": float,   # 执行时间（秒）
    "status": str,             # 状态：completed/failed/timeout/killed
    "sandbox_id": str,         # 沙盒ID
    "error": str               # 错误信息（如果失败）
}
```

## 🔧 高级配置

### 修改默认资源限制

编辑 `core/sandbox_executor.py` 中的 `ResourceLimits` 类：

```python
@dataclass
class ResourceLimits:
    timeout: int = 30              # 超时时间（秒）
    max_memory_mb: int = 512       # 最大内存（MB）
    max_cpu_percent: float = 80.0  # 最大CPU使用率
    max_output_size_kb: int = 1024 # 最大输出大小（KB）
    allow_network: bool = False    # 是否允许网络访问
    allowed_paths: List[str] = field(default_factory=list)
    forbidden_modules: List[str] = [...]  # 禁止的模块列表
```

### 修改安全级别

```python
from core.sandbox_executor import get_sandbox_executor, SecurityLevel

# Level 1: 基础隔离（默认）
sandbox = get_sandbox_executor(SecurityLevel.LEVEL_1)

# Level 2: 容器隔离（需要Docker）
sandbox = get_sandbox_executor(SecurityLevel.LEVEL_2)

# Level 3: 虚拟机隔离（最高安全性）
sandbox = get_sandbox_executor(SecurityLevel.LEVEL_3)
```

## 🧪 测试沙盒

运行内置测试：

```bash
cd 小雷版小龙虾agent
python test_sandbox.py
```

测试包括：
- ✅ Python代码执行
- ✅ JavaScript代码执行
- ✅ Shell命令执行
- ✅ 资源限制测试
- ✅ 安全拦截测试
- ✅ 并发执行测试

## 📝 最佳实践

### 1. 始终设置合理的超时时间

```python
# ✅ 好的做法
result = await tm.execute_in_sandbox(code, timeout=30)

# ❌ 避免无限等待
result = await tm.execute_in_sandbox(code, timeout=999999)
```

### 2. 限制内存使用

```python
# 根据任务复杂度调整
result = await tm.execute_in_sandbox(
    code,
    max_memory_mb=128  # 简单任务
)

result = await tm.execute_in_sandbox(
    code,
    max_memory_mb=1024  # 复杂数据分析
)
```

### 3. 检查执行结果

```python
result = await tm.execute_in_sandbox(code)

if result["success"]:
    print("执行成功:", result["result"])
else:
    print("执行失败:", result["error"])
    print("错误输出:", result["stderr"])
```

### 4. 不要信任用户输入的代码

即使用户输入经过LLM处理，也应该在沙盒中执行：

```python
# AI生成的代码也要在沙盒中执行
user_request = "帮我计算斐波那契数列前10项"
ai_generated_code = await llm.generate_code(user_request)

# ✅ 安全执行
result = await tm.execute_in_sandbox(ai_generated_code)
```

## ⚠️ 注意事项

1. **JavaScript执行需要Node.js**：确保系统已安装Node.js
2. **沙盒不是万能的**：虽然提供了多层保护，但仍建议只执行可信来源的代码
3. **性能开销**：沙盒执行比普通执行慢约10-20%，这是安全性的代价
4. **临时文件**：沙盒会在 `/tmp/agent_sandbox` 创建临时文件，会自动清理
5. **网络访问**：默认禁用网络访问，如需启用需修改 `ResourceLimits.allow_network=True`

## 🔗 相关文档

- [沙盒执行器源码](core/sandbox_executor.py)
- [工具管理器源码](tools/tool_manager.py)
- [沙盒测试用例](test_sandbox.py)
- [多智能体系统文档](多智能体系统文档.md)

## 📞 技术支持

如有问题，请查看：
1. 日志文件中的沙盒执行记录
2. 浏览器控制台的错误信息
3. 运行 `python test_sandbox.py` 进行诊断
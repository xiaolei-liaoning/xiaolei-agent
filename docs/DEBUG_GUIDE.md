# 调试指南

## 🛠️ 调试工具总览

本系统提供了一套完整的调试工具链，帮助您快速定位和解决问题。

---

## 1. 增强日志系统

### 1.1 基本使用

```python
from core.enhanced_logger import setup_enhanced_logging, get_logger

# 初始化日志系统
setup_enhanced_logging(
    level=logging.DEBUG,  # 日志级别
    log_file="logs/app.log",  # 日志文件
    enable_performance_tracking=True  # 启用性能追踪
)

# 获取logger
logger = get_logger("my_module")

# 记录日志（自动彩色输出）
logger.debug("调试信息")      # 🔍 青色
logger.info("普通信息")       # ✅ 绿色
logger.warning("警告信息")    # ⚠️ 黄色
logger.error("错误信息")      # ❌ 红色
logger.critical("严重错误")   # 🔥 红底白字
```

### 1.2 性能追踪

```python
from core.enhanced_logger import TimerLogger

# 方法1：手动计时
timer = TimerLogger("my_operation")
timer.start("开始处理数据")
# ... 你的代码 ...
timer.stop("数据处理完成")

# 方法2：上下文管理器（推荐）
with TimerLogger("database_query"):
    # 你的代码
    result = db.query()

# 输出示例：
# ⏱️  开始处理数据
# ⏱️  数据处理完成 (耗时: 0.234s)
```

### 1.3 装饰器方式

```python
from core.enhanced_logger import log_performance

@log_performance
def slow_function():
    time.sleep(1)
    return "done"

# 调用时自动记录执行时间
slow_function()
```

---

## 2. 交互式调试工具

### 2.1 对象检查

```python
from tools.debug_helper import quick_inspect

# 快速检查任何对象
obj = MyClass()
quick_inspect(obj)

# 输出示例：
# ============================================================
# 🔍 对象检查: MyClass
# ============================================================
# 类型: <class 'MyClass'>
# ID: 140234567890
# 大小: 256 bytes
# 
# 📋 属性 (5个):
#   - name: str = 'test'
#   - age: int = 25
#   ...
# 
# ⚙️  方法 (3个):
#   - greet()
#   - save()
#   ...
# ============================================================
```

### 2.2 函数调用追踪

```python
from tools.debug_helper import DebugHelper

def my_function(x, y):
    return x + y

# 追踪函数调用
DebugHelper.trace_call(my_function, 10, 20)

# 输出：
# 📞 调用追踪: my_function
#    参数: args=(10, 20), kwargs={}
# ✅ 返回: 30
```

### 2.3 条件断点

```python
from tools.debug_helper import breakpoint_if

for i in range(100):
    # 只在i==50时中断
    breakpoint_if(i == 50, "到达第50次循环")
    
    # 你的代码
    process(i)
```

### 2.4 调试上下文

```python
from tools.debug_helper import debug_context

with debug_context("数据处理"):
    # 你的代码
    data = load_data()
    result = process(data)
    save(result)

# 输出：
# 🔧 [数据处理] 开始执行...
# ✅ [数据处理] 完成 (耗时: 1.234s)
```

---

## 3. 热重载开发模式

### 3.1 启动开发模式

```bash
# 标准开发模式（代码修改自动重启）
./start.sh --dev

# 开发+调试模式
./start.sh --dev --debug
```

### 3.2 工作原理

1. 监听 `core/`, `skills/`, `tools/` 目录
2. 检测到 `.py` 文件变化
3. 自动重启服务（2秒冷却期）
4. 保持WebSocket连接不断

### 3.3 自定义监听目录

```bash
python3 dev_mode.py --watch core skills tests
```

---

## 4. 性能分析工具

### 4.1 函数性能分析

```python
from tools.profiler import quick_profile

def my_function():
    # 你的代码
    pass

# 分析函数性能（执行100次）
quick_profile(my_function, num_calls=100)

# 输出详细的性能统计
```

### 4.2 基准测试

```python
from tools.profiler import quick_benchmark

def fast_function():
    return sum(range(1000))

# 基准测试（执行1000次）
avg_time = quick_benchmark(fast_function, iterations=1000)

# 输出：
# 📈 基准测试结果: fast_function
#    迭代次数: 1000
#    平均时间: 0.123ms
#    最短时间: 0.098ms
#    最长时间: 0.456ms
```

### 4.3 性能对比

```python
from tools.profiler import PerformanceProfiler

profiler = PerformanceProfiler()

# 对比多个实现
results = profiler.compare_functions([
    implementation_v1,
    implementation_v2,
    implementation_v3
], num_calls=100)

# 自动找出最快的实现
```

### 4.4 装饰器方式

```python
from tools.profiler import profile_decorator

@profile_decorator
def my_function():
    # 你的代码
    pass

# 每次调用都会输出性能分析
my_function()
```

### 4.5 命令行性能分析

```bash
# 运行性能分析模式
./start.sh --profile

# 查看可视化报告
pip install snakeviz
snakeviz profile.stats
```

---

## 5. VS Code调试配置

### 5.1 创建launch.json

在 `.vscode/` 目录下创建 `launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: 当前文件",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Python: main.py",
      "type": "python",
      "request": "launch",
      "module": "main",
      "console": "integratedTerminal",
      "env": {
        "LOG_LEVEL": "DEBUG"
      }
    },
    {
      "name": "Python: pytest",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "tests/",
        "-v"
      ],
      "console": "integratedTerminal"
    }
  ]
}
```

### 5.2 使用断点调试

1. 在代码行号左侧点击设置断点（红点）
2. 按 `F5` 启动调试
3. 程序会在断点处暂停
4. 查看变量、调用栈等信息
5. 使用调试控制按钮继续执行

---

## 6. 常见调试场景

### 6.1 API调用失败

```python
from core.enhanced_logger import get_logger

logger = get_logger("api_client")

try:
    response = call_api()
    logger.info(f"API调用成功: {response.status_code}")
except Exception as e:
    logger.error(f"API调用失败: {e}", exc_info=True)  # exc_info=True包含堆栈
```

### 6.2 性能瓶颈定位

```python
from tools.profiler import timer_context

with timer_context("数据库查询"):
    results = db.query_complex()

with timer_context("数据处理"):
    processed = process(results)

# 查看哪个环节最慢
```

### 6.3 内存泄漏排查

```python
import tracemalloc
from tools.debug_helper import quick_inspect

# 开始追踪
tracemalloc.start()

# 你的代码
obj = create_large_object()

# 检查内存使用
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

print("[ Top 10 内存占用 ]")
for stat in top_stats[:10]:
    print(stat)

# 检查对象
quick_inspect(obj)
```

### 6.4 并发问题调试

```python
import threading
from core.enhanced_logger import get_logger

logger = get_logger("thread_debug")

def thread_func(name):
    logger.info(f"线程 {name} 启动")
    # 你的代码
    logger.info(f"线程 {name} 完成")

# 创建并启动线程
threads = []
for i in range(5):
    t = threading.Thread(target=thread_func, args=(f"Thread-{i}",))
    threads.append(t)
    t.start()

# 等待所有线程完成
for t in threads:
    t.join()
```

---

## 7. 调试最佳实践

### ✅ 推荐做法

1. **使用合适的日志级别**
   - DEBUG: 详细调试信息
   - INFO: 一般信息
   - WARNING: 警告但不影响运行
   - ERROR: 错误但程序继续
   - CRITICAL: 严重错误，程序可能崩溃

2. **添加上下文信息**
   ```python
   logger.info(f"处理用户 {user_id} 的请求", extra={'user_id': user_id})
   ```

3. **使用结构化日志**
   ```python
   logger.info("任务完成", extra={
       'task_id': task_id,
       'duration': duration,
       'status': 'success'
   })
   ```

4. **定期清理调试代码**
   - 移除临时的print语句
   - 删除不需要的断点
   - 关闭DEBUG日志级别

### ❌ 避免做法

1. **不要在生产环境使用DEBUG级别**
2. **不要在日志中记录敏感信息**（密码、token等）
3. **不要过度使用日志**（影响性能）
4. **不要忘记移除调试代码**

---

## 8. 故障排查清单

### 问题：日志没有输出

- [ ] 检查日志级别设置是否正确
- [ ] 确认logger名称是否正确
- [ ] 检查是否有过滤器阻止了日志

### 问题：热重载不工作

- [ ] 确认使用的是 `--dev` 模式
- [ ] 检查文件是否在监听目录中
- [ ] 查看控制台是否有错误信息

### 问题：性能分析结果不准确

- [ ] 确保多次运行取平均值
- [ ] 排除首次运行的预热时间
- [ ] 检查是否有外部因素干扰（网络、磁盘IO）

---

## 📚 相关资源

- [Python logging文档](https://docs.python.org/3/library/logging.html)
- [cProfile性能分析](https://docs.python.org/3/library/profile.html)
- [VS Code Python调试](https://code.visualstudio.com/docs/python/debugging)

---

**Happy Debugging! 🐛➡️✅**

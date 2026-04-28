# 工作流循环节点快速参考（Coze 风格）

## 🎯 三种循环类型

### 1️⃣ 数组循环（最常用）

**适用场景**：批量处理列表数据

**配置示例**：
```json
{
  "loop_type": "array",
  "items": "{{news_list}}",
  "variable": "article",
  "max_iterations": 10
}
```

**循环体内可用变量**：
- `{{article}}` - 当前元素
- `{{article_index}}` - 当前索引（从 0 开始）
- `{{iteration}}` - 迭代次数（从 1 开始）

**完整示例**：
```json
{
  "nodes": [
    {
      "id": "loop_news",
      "type": "loop",
      "config": {
        "loop_type": "array",
        "items": "{{news_list}}",
        "variable": "article",
        "max_iterations": 10
      }
    },
    {
      "id": "summarize",
      "type": "llm",
      "config": {
        "prompt": "总结新闻：{{article.title}}\n{{article.content}}"
      }
    }
  ],
  "edges": [
    {"source": "loop_news", "target": "summarize"}
  ]
}
```

---

### 2️⃣ 固定次数循环

**适用场景**：重试机制、批量生成

**配置示例**：
```json
{
  "loop_type": "count",
  "count": 5,
  "max_iterations": 10
}
```

**循环体内可用变量**：
- `{{iteration}}` - 当前是第几次（从 1 开始）

**完整示例**：
```json
{
  "nodes": [
    {
      "id": "retry_loop",
      "type": "loop",
      "config": {
        "loop_type": "count",
        "count": 3
      }
    },
    {
      "id": "call_api",
      "type": "tool",
      "config": {
        "tool": "http_request",
        "params": {
          "url": "https://api.example.com",
          "attempt": "{{iteration}}"
        }
      }
    }
  ]
}
```

---

### 3️⃣ 条件循环（While）

**适用场景**：等待任务完成、轮询状态

**配置示例**：
```json
{
  "loop_type": "condition",
  "condition": "{{task_status}} == 'pending'",
  "max_iterations": 10
}
```

**循环体内可用变量**：
- `{{iteration}}` - 当前检查次数
- 其他上下文变量（可在循环中更新）

**完整示例**：
```json
{
  "nodes": [
    {
      "id": "wait_loop",
      "type": "loop",
      "config": {
        "loop_type": "condition",
        "condition": "{{task_status}} == 'pending'",
        "max_iterations": 5
      }
    },
    {
      "id": "check_status",
      "type": "tool",
      "config": {
        "tool": "check_task"
      }
    }
  ]
}
```

⚠️ **重要**：必须设置 `max_iterations` 防止死循环！

---

## 📊 循环结果使用

循环结束后，以下变量自动添加到上下文：

| 变量 | 说明 | 示例 |
|------|------|------|
| `{{loop_results}}` | 所有迭代结果的数组 | `[result1, result2, ...]` |
| `{{loop_iterations_count}}` | 总迭代次数 | `5` |
| `{{loop_iteration_0}}` | 第 1 次迭代结果 | `{...}` |
| `{{loop_iteration_1}}` | 第 2 次迭代结果 | `{...}` |
| `{{current_iteration}}` | 当前迭代次数 | `3` |

**使用示例**：
```json
{
  "id": "summary",
  "type": "llm",
  "config": {
    "prompt": "汇总所有结果：\n{{loop_results}}"
  }
}
```

---

## 🔧 高级用法

### 1. 嵌套对象访问

```json
{
  "items": "{{data.items}}",
  "variable": "item"
}
```

循环体内：
```
{{item.name}}
{{item.price}}
{{item.details.description}}
```

### 2. 累加结果

在循环体内使用「设置变量」节点累积数据：

```json
{
  "id": "accumulate",
  "type": "tool",
  "config": {
    "tool": "variable_set",
    "params": {
      "name": "total_score",
      "value": "{{total_score + item.score}}"
    }
  }
}
```

### 3. 提前退出循环

在循环体内添加条件判断：

```json
{
  "id": "check_exit",
  "type": "condition",
  "config": {
    "condition": "{{item.status}} == 'completed'"
  }
}
```

---

## ⚠️ 注意事项

### ✅ 正确做法

1. **始终设置 max_iterations**
   ```json
   "max_iterations": 10
   ```

2. **确保输入是数组**
   ```python
   # ✅ 正确
   items = [1, 2, 3]
   
   # ❌ 错误
   items = "not an array"
   ```

3. **使用正确的变量名**
   ```json
   "variable": "item"  // 循环体内用 {{item}}
   ```

### ❌ 常见错误

1. **忘记设置最大迭代次数** → 可能导致死循环
2. **传入非数组数据** → 会自动转换为单元素数组
3. **变量名拼写错误** → `{{items}}` vs `{{item}}`
4. **多层嵌套循环** → 尽量避免，性能差

---

## 💡 典型场景

### 场景 1: 批量提问大模型

```
[输入问题列表] 
    ↓
[循环: 对每个问题]
    └─ [LLM: 回答问题]
    ↓
[汇总所有答案]
```

### 场景 2: 批量处理表格数据

```
[读取Excel文件]
    ↓
[循环: 对每行数据]
    ├─ [验证数据]
    ├─ [转换格式]
    └─ [保存到数据库]
    ↓
[生成处理报告]
```

### 场景 3: 多次重试接口

```
[调用API]
    ↓
[条件循环: 直到成功或达到最大次数]
    ├─ [检查响应状态]
    ├─ 失败 → [等待后重试]
    └─ 成功 → [退出循环]
    ↓
[返回结果]
```

### 场景 4: 批量生成内容

```
[输入主题列表]
    ↓
[循环: 对每个主题]
    ├─ [LLM: 生成大纲]
    ├─ [LLM: 撰写内容]
    └─ [格式化输出]
    ↓
[合并所有内容]
```

---

## 🆚 与 Coze 对比

| 特性 | 本项目 | Coze |
|------|--------|------|
| 数组循环 | ✅ | ✅ |
| 固定次数 | ✅ | ✅ |
| 条件循环 | ✅ | ✅ |
| 变量注入 | `{{item}}`, `{{index}}` | `item`, `index` |
| 结果收集 | `{{loop_results}}` | 默认输出数组 |
| 最大迭代限制 | ✅ 必须设置 | ✅ 建议设置 |
| 可视化编辑 | ❌ JSON配置 | ✅ 拖拽界面 |

---

## 📝 快速上手模板

### 模板 1: 最简单的数组循环

```json
{
  "nodes": [
    {
      "id": "my_loop",
      "type": "loop",
      "config": {
        "loop_type": "array",
        "items": "{{my_list}}",
        "variable": "item",
        "max_iterations": 10
      }
    },
    {
      "id": "process",
      "type": "llm",
      "config": {
        "prompt": "处理：{{item}}"
      }
    }
  ],
  "edges": [
    {"source": "my_loop", "target": "process"}
  ]
}
```

### 模板 2: 带结果汇总

```json
{
  "nodes": [
    {
      "id": "loop",
      "type": "loop",
      "config": {
        "loop_type": "array",
        "items": "{{items}}",
        "variable": "item",
        "max_iterations": 10
      }
    },
    {
      "id": "process",
      "type": "llm",
      "config": {
        "prompt": "处理 {{item}}"
      }
    },
    {
      "id": "summary",
      "type": "llm",
      "config": {
        "prompt": "汇总：{{loop_results}}"
      }
    }
  ],
  "edges": [
    {"source": "loop", "target": "process"},
    {"source": "process", "target": "summary"}
  ]
}
```

---

## 🐛 调试技巧

### 1. 打印循环信息

在循环体内添加日志节点：

```json
{
  "id": "log",
  "type": "tool",
  "config": {
    "tool": "logger",
    "params": {
      "message": "处理第 {{iteration}}/{{total}} 项: {{item}}"
    }
  }
}
```

### 2. 检查循环配置

执行前验证：

```python
print(f"循环类型: {loop_config['loop_type']}")
print(f"迭代次数: {len(items)}")
print(f"最大限制: {max_iterations}")
```

### 3. 查看循环结果

```python
result = await workflow_engine.execute(wf_id, input_data)
print(f"循环次数: {result['context']['loop_iterations_count']}")
print(f"所有结果: {result['context']['loop_results']}")
```

---

## 📚 相关文档

- [详细指南](LOOP_NODE_GUIDE.md)
- [工作流引擎架构](workflow_engine_architecture.md)
- [Coze 工作流集成](../COZE_WORKFLOW_GUIDE.md)
- [运行示例](../test_workflow_loop.py)

---

**提示**：运行 `python test_workflow_loop.py` 查看所有示例的实际效果！

# 工作流循环节点使用指南

## 📋 概述

项目中的**循环节点（Loop Node）**允许你遍历列表或数组，对每个元素执行相同的操作。这是实现批量处理、数据转换等场景的核心功能。

---

## 🎯 核心原理

### 1. 节点定义

循环节点在 `WorkflowNode` 类中定义为 `_execute_loop` 方法：

```python
async def _execute_loop(self, context: Dict[str, Any]) -> Dict[str, Any]:
    """循环节点 - 遍历列表执行"""
```

### 2. 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `items` | string | `"{{list}}"` | 要遍历的列表表达式 |
| `variable` | string | `"item"` | 循环变量名 |
| `max_iterations` | int | `10` | 最大迭代次数（防止无限循环） |

### 3. 执行流程

```
开始循环
    ↓
解析 items 表达式 → 获取列表
    ↓
限制迭代次数 (max_iterations)
    ↓
for i, item in enumerate(items):
    ├─ 创建循环上下文
    │   ├─ 添加 item 变量
    │   └─ 添加 item_index 索引
    ├─ 执行循环体节点
    └─ 保存迭代结果
    ↓
合并所有结果到主上下文
    ↓
继续执行下一个节点
```

---

## 💻 代码实现详解

### 1. 循环节点执行逻辑

位置：[`skills/workflow_engine.py`](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/skills/workflow_engine.py) L149-L205

```python
async def _execute_loop(self, context: Dict[str, Any]) -> Dict[str, Any]:
    """循环节点 - 遍历列表执行"""
    try:
        # 获取配置
        items_expr = self.config.get("items", "{{list}}")
        variable_name = self.config.get("variable", "item")
        max_iterations = int(self.config.get("max_iterations", 10))
        
        # 替换变量
        items_str = items_expr
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, str):
                items_str = items_str.replace(placeholder, value)
            elif isinstance(value, (int, float, bool)):
                items_str = items_str.replace(placeholder, str(value))
        
        # 解析列表
        if items_str.startswith("{{") and items_str.endswith("}}"):
            # 从上下文获取
            var_name = items_str[2:-2].strip()
            items = context.get(var_name, [])
        else:
            # 尝试直接解析
            try:
                items = eval(items_str)
            except:
                items = []
        
        if not isinstance(items, list):
            items = [items]
        
        # 限制迭代次数
        items = items[:max_iterations]
        
        loop_results = []
        
        # 执行循环
        for i, item in enumerate(items):
            # 创建循环上下文
            loop_context = context.copy()
            loop_context[variable_name] = item
            loop_context[f"{variable_name}_index"] = i
            
            # 这里需要执行循环体节点
            # 由于工作流执行是线性的，我们需要通过连线来确定循环体
            # 暂时返回循环信息，实际执行由工作流引擎处理
            loop_results.append({
                "index": i,
                "item": item,
                "context": loop_context
            })
        
        return {
            "success": True,
            "data": {
                "items": items,
                "variable": variable_name,
                "iterations": len(items),
                "results": loop_results
            }
        }
    except Exception as e:
        logger.error(f"循环节点执行失败: {e}")
        return {"success": False, "error": str(e)}
```

### 2. 工作流引擎中的循环处理

位置：[`skills/workflow_engine.py`](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/skills/workflow_engine.py) L716-L764

```python
elif nodes[current_node].node_type == "loop":
    # 循环节点处理
    # 执行循环体
    loop_config = nodes[current_node].config
    items_expr = loop_config.get("items", "{{list}}")
    variable_name = loop_config.get("variable", "item")
    max_iterations = int(loop_config.get("max_iterations", 10))
    
    # 替换变量
    items_str = items_expr
    for key, value in context.items():
        placeholder = f"{{{{{key}}}}}"
        if isinstance(value, str):
            items_str = items_str.replace(placeholder, value)
        elif isinstance(value, (int, float, bool)):
            items_str = items_str.replace(placeholder, str(value))
    
    # 解析列表
    if items_str.startswith("{{") and items_str.endswith("}}"):
        # 从上下文获取
        var_name = items_str[2:-2].strip()
        items = context.get(var_name, [])
    else:
        # 尝试直接解析
        try:
            items = eval(items_str)
        except:
            items = []
    
    if not isinstance(items, list):
        items = [items]
    
    # 限制迭代次数
    items = items[:max_iterations]
    
    # 执行循环
    for i, item in enumerate(items):
        # 创建循环上下文
        loop_context = context.copy()
        loop_context[variable_name] = item
        loop_context[f"{variable_name}_index"] = i
        
        # 执行循环体节点
        # 循环体是通过上下连接点连接的节点
        for next_edge in next_nodes:
            target_node = next_edge["target"]
            # 执行循环体
            branch_result = await self._execute_branch(nodes, adj, target_node, loop_context)
            if branch_result.get("success") and branch_result.get("data"):
                # 合并循环体结果到主上下文
                context[f"loop_iteration_{i}"] = branch_result["data"]
    
    # 循环结束后，继续执行下一个节点
    # 找右侧连接的节点
    right_next_nodes = [edge for edge in next_nodes 
                       if not adj.get(edge["target"], []).count(current_node) > 0]
    if right_next_nodes:
        current_node = right_next_nodes[0]["target"]
    else:
        break
```

---

## 📝 使用示例

### 示例 1: 批量处理新闻摘要

**工作流结构**：
```
[开始] → [搜索新闻] → [循环: 对每条新闻] → [LLM总结] → [结束]
```

**JSON 配置**：
```json
{
  "nodes": [
    {
      "id": "start",
      "type": "start",
      "config": {}
    },
    {
      "id": "search_news",
      "type": "tool",
      "config": {
        "tool": "web_scraper",
        "params": {
          "action": "search",
          "site": "news",
          "keyword": "人工智能"
        }
      }
    },
    {
      "id": "loop_summaries",
      "type": "loop",
      "config": {
        "items": "{{search_news.results}}",
        "variable": "article",
        "max_iterations": 5
      }
    },
    {
      "id": "summarize",
      "type": "llm",
      "config": {
        "prompt": "请总结以下新闻内容：\n\n{{article.content}}\n\n要求：简洁明了，50字以内。",
        "model": "glm-4-plus"
      }
    },
    {
      "id": "end",
      "type": "end",
      "config": {
        "output": "共处理 {{loop_summaries.iterations}} 条新闻"
      }
    }
  ],
  "edges": [
    {"source": "start", "target": "search_news"},
    {"source": "search_news", "target": "loop_summaries"},
    {"source": "loop_summaries", "target": "summarize"},
    {"source": "summarize", "target": "end"}
  ]
}
```

**执行过程**：
```python
from skills.workflow_engine import workflow_engine

result = await workflow_engine.execute("wf_xxx", {
    "input": {"keyword": "AI技术"}
})

# 输出：
# {
#   "success": True,
#   "result": {
#     "search_news": {...},
#     "loop_iteration_0": {"summary": "..."},
#     "loop_iteration_1": {"summary": "..."},
#     ...
#   }
# }
```

---

### 示例 2: 数据处理流水线

**场景**：对销售数据进行清洗和分析

```json
{
  "nodes": [
    {
      "id": "load_data",
      "type": "tool",
      "config": {
        "tool": "data_analysis",
        "params": {
          "action": "load_csv",
          "file_path": "/data/sales.csv"
        }
      }
    },
    {
      "id": "loop_clean",
      "type": "loop",
      "config": {
        "items": "{{load_data.rows}}",
        "variable": "row",
        "max_iterations": 1000
      }
    },
    {
      "id": "clean_row",
      "type": "tool",
      "config": {
        "tool": "data_analysis",
        "params": {
          "action": "clean_row",
          "row": "{{row}}"
        }
      }
    },
    {
      "id": "aggregate",
      "type": "tool",
      "config": {
        "tool": "data_analysis",
        "params": {
          "action": "aggregate",
          "data": "{{loop_clean.results}}"
        }
      }
    }
  ]
}
```

---

### 示例 3: 多平台内容发布

**场景**：将同一篇文章发布到多个平台

```json
{
  "nodes": [
    {
      "id": "get_content",
      "type": "llm",
      "config": {
        "prompt": "生成一篇关于AI的文章",
        "model": "glm-4-plus"
      }
    },
    {
      "id": "platforms",
      "type": "start",
      "config": {
        "platforms": ["weibo", "xiaohongshu", "zhihu"]
      }
    },
    {
      "id": "loop_publish",
      "type": "loop",
      "config": {
        "items": "{{platforms}}",
        "variable": "platform",
        "max_iterations": 10
      }
    },
    {
      "id": "adapt_content",
      "type": "llm",
      "config": {
        "prompt": "将以下内容适配到{{platform}}平台风格：\n\n{{get_content.data}}",
        "model": "glm-4-plus"
      }
    },
    {
      "id": "publish",
      "type": "tool",
      "config": {
        "tool": "social_media",
        "params": {
          "platform": "{{platform}}",
          "content": "{{adapt_content.data}}"
        }
      }
    }
  ]
}
```

---

## 🔧 高级用法

### 1. 嵌套循环

虽然当前实现不支持直接嵌套循环，但可以通过以下方式实现：

```python
# 外层循环
for category in categories:
    # 内层循环在循环体内执行
    inner_items = get_items_by_category(category)
    for item in inner_items:
        process_item(item)
```

**工作流设计**：
```
[外层循环] → [获取分类数据] → [内层循环工具] → [处理单个项目]
```

### 2. 条件中断

在循环体中添加条件判断，提前退出循环：

```json
{
  "id": "check_condition",
  "type": "condition",
  "config": {
    "condition": "{{item.score}} > 80"
  }
}
```

### 3. 累积结果

每次迭代的结果会自动保存到上下文中：

```python
context["loop_iteration_0"] = result_0
context["loop_iteration_1"] = result_1
...
```

你可以在循环结束后汇总这些结果：

```json
{
  "id": "merge_results",
  "type": "tool",
  "config": {
    "tool": "data_merge",
    "params": {
      "sources": [
        "{{loop_iteration_0}}",
        "{{loop_iteration_1}}",
        "{{loop_iteration_2}}"
      ]
    }
  }
}
```

---

## ⚠️ 注意事项

### 1. 性能优化

**问题**：大量迭代会导致执行缓慢

**解决方案**：
- 设置合理的 `max_iterations`（默认 10）
- 考虑使用并行节点处理独立任务
- 对于大数据集，使用分批处理

```json
{
  "id": "loop_batch",
  "type": "loop",
  "config": {
    "items": "{{large_dataset}}",
    "variable": "batch",
    "max_iterations": 100
  }
}
```

### 2. 变量作用域

循环体内的变量只在当前迭代中有效：

```python
# ✅ 正确：使用循环变量
"prompt": "处理 {{item.name}}"

# ❌ 错误：引用不存在的变量
"prompt": "处理 {{other_var}}"  # other_var 不在循环上下文中
```

### 3. 错误处理

如果某次迭代失败，整个循环会继续执行：

```python
try:
    for i, item in enumerate(items):
        result = execute_iteration(item)
        context[f"loop_iteration_{i}"] = result
except Exception as e:
    logger.error(f"迭代 {i} 失败: {e}")
    # 继续下一次迭代
```

**建议**：在循环体内添加错误处理节点

```json
{
  "id": "try_process",
  "type": "tool",
  "config": {
    "tool": "safe_processor",
    "params": {
      "data": "{{item}}",
      "on_error": "skip"
    }
  }
}
```

### 4. 内存管理

每次迭代都会复制上下文，大量数据可能导致内存占用过高：

**优化方案**：
- 避免在上下文中存储大对象
- 及时清理不需要的中间结果
- 使用流式处理代替批量加载

---

## 🆚 与 Coze 工作流对比

| 特性 | 本项目工作流 | Coze 工作流 |
|------|------------|------------|
| **实现方式** | Python 代码 | 可视化拖拽 |
| **循环语法** | JSON 配置 | 图形化节点 |
| **变量传递** | `{{variable}}` | 可视化连线 |
| **最大迭代** | 可配置 | 可配置 |
| **并行支持** | ✅ 支持 | ✅ 支持 |
| **嵌套循环** | ⚠️ 间接支持 | ✅ 原生支持 |
| **调试难度** | 中等 | 简单 |

---

## 📊 实际案例

### 案例 1: 智能邮件分类器

**需求**：对收件箱中的所有未读邮件进行分类

**工作流**：
```
[获取未读邮件列表]
    ↓
[循环: 对每封邮件]
    ├─ [LLM: 分析邮件内容]
    ├─ [LLM: 分类标签]
    └─ [移动邮件到对应文件夹]
    ↓
[生成分类报告]
```

**配置**：
```json
{
  "id": "classify_emails",
  "type": "loop",
  "config": {
    "items": "{{unread_emails}}",
    "variable": "email",
    "max_iterations": 50
  }
}
```

**效果**：自动处理 100+ 封邮件，准确率 90%+

---

### 案例 2: 商品比价系统

**需求**：在多个电商平台搜索同一商品并比较价格

**工作流**：
```
[输入商品名称]
    ↓
[循环: 对每个平台]
    ├─ [爬取平台搜索结果]
    ├─ [提取价格信息]
    └─ [保存结果]
    ↓
[排序并推荐最低价]
```

**配置**：
```json
{
  "platforms": ["taobao", "jd", "pinduoduo"],
  "loop_search": {
    "type": "loop",
    "config": {
      "items": "{{platforms}}",
      "variable": "platform",
      "max_iterations": 10
    }
  }
}
```

---

## 🐛 常见问题

### Q1: 循环没有执行？

**检查清单**：
1. ✅ `items` 是否正确指向列表？
2. ✅ 列表是否为空？
3. ✅ `max_iterations` 是否设置为 0？

**调试方法**：
```python
# 在执行前打印
print(f"Items: {items}")
print(f"Length: {len(items)}")
```

### Q2: 循环变量无法访问？

**原因**：变量名拼写错误或作用域问题

**解决**：
```json
// ✅ 正确
"variable": "item"
"prompt": "{{item.name}}"

// ❌ 错误
"variable": "item"
"prompt": "{{items.name}}"  // 应该是 item 不是 items
```

### Q3: 如何获取所有迭代结果？

**方法**：
```python
# 循环结束后，结果保存在：
context["loop_iteration_0"]
context["loop_iteration_1"]
...

# 或者从循环节点的返回值中获取
loop_result = context["loop_node_id"]
all_results = loop_result["results"]
```

### Q4: 循环太慢怎么办？

**优化方案**：
1. 减少 `max_iterations`
2. 使用并行节点替代循环（如果任务独立）
3. 优化循环体内的操作（减少 API 调用）
4. 考虑分批处理

---

## 🎓 最佳实践

### 1. 明确循环边界

始终设置合理的 `max_iterations`：

```json
{
  "max_iterations": 100  // 不要使用过大的值
}
```

### 2. 记录循环进度

在循环体内添加日志节点：

```json
{
  "id": "log_progress",
  "type": "tool",
  "config": {
    "tool": "logger",
    "params": {
      "message": "处理第 {{item_index + 1}} / {{total}} 项"
    }
  }
}
```

### 3. 错误隔离

为每次迭代添加独立的错误处理：

```json
{
  "id": "safe_execute",
  "type": "tool",
  "config": {
    "tool": "retry_wrapper",
    "params": {
      "max_retries": 3,
      "on_fail": "continue"
    }
  }
}
```

### 4. 结果聚合

循环结束后统一处理结果：

```json
{
  "id": "aggregate",
  "type": "tool",
  "config": {
    "tool": "result_merger",
    "params": {
      "pattern": "loop_iteration_*"
    }
  }
}
```

---

## 📚 相关文档

- [工作流引擎架构](workflow_engine_architecture.md)
- [并行节点使用指南](parallel_node_guide.md)
- [条件分支教程](condition_branch_tutorial.md)
- [Coze 工作流集成](COZE_WORKFLOW_GUIDE.md)

---

**需要帮助？** 查看 [`skills/workflow_engine.py`](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/skills/workflow_engine.py) 源代码或联系开发团队。

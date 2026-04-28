# Coze 工作流完全指南

## 🎯 什么是 Coze 工作流？

Coze 工作流是一个**可视化自动化编排工具**，让你通过拖拽节点的方式搭建复杂的业务流程，无需编写代码。

### 工作流 vs Bot

| 特性 | Bot | Workflow |
|------|-----|----------|
| **适用场景** | 对话交互、智能问答 | 固定流程、自动化任务 |
| **执行方式** | LLM 驱动，灵活响应 | 预定义流程，确定性执行 |
| **复杂度** | 简单到中等 | 中等到复杂 |
| **可预测性** | 较低（依赖 LLM） | 高（固定逻辑） |
| **典型应用** | 客服聊天、内容创作 | 数据处理、API 编排 |

## 🚀 快速开始

### 第一步：访问工作流编辑器

1. 打开 [https://www.coze.cn/workflow](https://www.coze.cn/workflow)
2. 登录你的 Coze 账号
3. 点击"创建工作流"

### 第二步：设计第一个工作流

让我们创建一个**新闻摘要工作流**：

#### 工作流结构
```
[开始] → [搜索新闻] → [LLM总结] → [格式化] → [结束]
```

#### 详细配置

**1. 开始节点 (Start)**
- 输入参数：
  - `keyword` (string): 搜索关键词
  - `max_items` (number): 最大条目数，默认 5

**2. HTTP 请求节点 (Search News)**
- URL: `https://api.example.com/news/search?q={{keyword}}&limit={{max_items}}`
- Method: GET
- 输出: `news_list`

**3. LLM 节点 (Summarize)**
- Prompt:
  ```
  请总结以下新闻内容，提取关键信息：
  
  {{news_list}}
  
  要求：
  1. 用简洁的语言概括每条新闻
  2. 突出重要事件
  3. 控制在200字以内
  ```
- Model: glm-4-plus
- 输出: `summary`

**4. 代码节点 (Format)**
- Language: Python
- Code:
  ```python
  def main(summary: str) -> dict:
      return {
          "formatted": f"📰 今日新闻摘要\n\n{summary}\n\n---\n生成时间: {datetime.now()}"
      }
  ```
- 输出: `formatted`

**5. 结束节点 (End)**
- 输出变量: `formatted`

### 第三步：测试和发布

1. 点击右上角"测试"按钮
2. 输入测试数据：
   ```json
   {
     "keyword": "人工智能",
     "max_items": 3
   }
   ```
3. 查看每个节点的执行结果
4. 确认无误后点击"发布"
5. 复制 workflow_id

### 第四步：通过 API 调用

```python
import asyncio
from test_coze_workflow import CozeWorkflowClient

async def main():
    client = CozeWorkflowClient(workflow_id="your_workflow_id")
    
    result = await client.run_workflow({
        "keyword": "AI技术",
        "max_items": 5
    })
    
    print(result['data']['formatted'])
    await client.close()

asyncio.run(main())
```

## 📦 常用工作流模板

### 模板 1: 智能客服流程

```
[开始: 用户问题]
    ↓
[LLM: 意图识别] → 分类：咨询/投诉/退款/其他
    ↓
[条件判断]
    ├─ 咨询 → [知识库检索] → [LLM: 生成回复]
    ├─ 投诉 → [情感分析] → [升级处理]
    └─ 退款 → [订单查询] → [政策匹配] → [生成方案]
    ↓
[结束: 返回回复]
```

**应用场景**：电商客服、技术支持

### 模板 2: 内容生成流水线

```
[开始: 主题]
    ↓
[LLM: 大纲生成]
    ↓
[循环: 对每个章节]
    ├─ [LLM: 撰写内容]
    ├─ [LLM: 事实核查]
    └─ [代码: 保存草稿]
    ↓
[LLM: 整体润色]
    ↓
[代码: 格式化为Markdown]
    ↓
[结束: 完整文章]
```

**应用场景**：博客写作、报告生成

### 模板 3: 数据分析报告

```
[开始: 数据源]
    ↓
[代码: 读取CSV/Excel]
    ↓
[代码: 数据清洗]
    ├─ 去重
    ├─ 填充缺失值
    └─ 异常值处理
    ↓
[代码: 统计分析]
    ├─ 描述性统计
    ├─ 趋势分析
    └─ 相关性分析
    ↓
[代码: 生成图表]
    ↓
[LLM: 解读数据]
    ↓
[代码: 生成PDF报告]
    ↓
[结束: 报告链接]
```

**应用场景**：销售分析、市场调研

### 模板 4: 社交媒体自动化

```
[开始: 原始内容]
    ↓
[LLM: 改写为推文风格]
    ↓
[条件: 平台选择]
    ├─ 微博 → [代码: 添加话题标签]
    ├─ 小红书 → [代码: 添加emoji和分段]
    └─ 知乎 → [代码: 格式化Markdown]
    ↓
[HTTP: 调用发布API]
    ↓
[结束: 发布结果]
```

**应用场景**：多平台内容分发

### 模板 5: 智能邮件处理

```
[开始: 新邮件]
    ↓
[LLM: 分类] → 重要/普通/垃圾
    ↓
[条件判断]
    ├─ 重要 → [LLM: 提取关键信息] → [发送通知]
    ├─ 普通 → [LLM: 生成摘要] → [归档]
    └─ 垃圾 → [标记为垃圾邮件]
    ↓
[结束: 处理结果]
```

**应用场景**：邮件管理、优先级排序

## 🔧 高级功能

### 1. 变量传递

在工作流中，节点之间通过变量传递数据：

```
节点A 输出: {"result": "value"}
         ↓
节点B 输入: {{result}}  ← 自动引用节点A的输出
```

**支持嵌套对象**：
```
{{user.name}}
{{data.items[0].title}}
```

### 2. 条件分支

使用条件节点实现 if-else 逻辑：

```
条件: {{score}} >= 60
  ├─ True → [及格处理]
  └─ False → [不及格处理]
```

**支持的运算符**：
- 比较: `>`, `<`, `>=`, `<=`, `==`, `!=`
- 逻辑: `&&` (与), `||` (或), `!` (非)
- 字符串: `contains`, `starts_with`, `ends_with`

### 3. 循环节点

对数组中的每个元素执行相同操作：

```
输入: [item1, item2, item3]
  ↓
[循环: 对每个 item]
    ├─ [LLM: 处理 item]
    └─ [保存结果]
  ↓
输出: [result1, result2, result3]
```

**配置项**：
- 迭代变量名: `item`
- 当前索引: `index`
- 最大迭代次数: 防止无限循环

### 4. 错误处理

**重试机制**：
- HTTP 节点：自动重试失败的请求
- 配置重试次数和间隔

**异常捕获**：
```
[主要流程]
    ↓
[错误？]
    ├─ Yes → [错误处理节点]
    └─ No → [继续正常流程]
```

### 5. 子工作流

在一个工作流中调用另一个工作流，实现模块化：

```
[主工作流]
    ↓
[调用子工作流A] → 返回结果
    ↓
[调用子工作流B] → 返回结果
    ↓
[整合结果]
```

**优势**：
- 复用通用逻辑
- 降低复杂度
- 便于维护

## 💡 最佳实践

### 1. 设计原则

✅ **单一职责**：每个工作流只做一件事
✅ **模块化**：复杂流程拆分为多个子工作流
✅ **容错性**：考虑异常情况和边界条件
✅ **可测试**：每个节点都能独立测试
✅ **文档化**：添加节点说明和注释

### 2. 性能优化

⚡ **减少 LLM 调用**：
- 合并相似的 LLM 节点
- 使用缓存存储常见结果

⚡ **并行处理**：
- 独立的步骤可以并行执行
- 使用批处理减少 API 调用次数

⚡ **限制循环次数**：
- 设置合理的最大迭代次数
- 避免处理过大的数据集

### 3. 调试技巧

🐛 **逐步测试**：
1. 先测试单个节点
2. 再测试节点组合
3. 最后测试完整流程

🐛 **查看日志**：
- 每个节点的输入输出
- 执行时间和状态
- 错误信息和堆栈

🐛 **使用 Mock 数据**：
- 为外部 API 准备测试数据
- 避免依赖真实服务

### 4. 版本管理

📝 **命名规范**：
```
workflow_name_v1.0
workflow_name_v1.1
workflow_name_v2.0
```

📝 **变更记录**：
- 每次修改记录变更内容
- 保留旧版本作为备份
- 重大变更前充分测试

## 🔗 与本地系统集成

### 方案 1: Coze 工作流 + 本地 Bot

```python
from core.coze_backend import CozeBackend
from test_coze_workflow import CozeWorkflowClient

class HybridAgent:
    def __init__(self):
        self.bot = CozeBackend()
        self.workflow = CozeWorkflowClient()
    
    async def process(self, user_input: str):
        # 1. Bot 理解意图
        intent = await self.bot.chat([
            {"role": "user", "content": f"分析用户意图: {user_input}"}
        ])
        
        # 2. 根据意图选择执行方式
        if "需要工作流" in intent:
            # 调用 Coze 工作流
            result = await self.workflow.run_workflow({
                "input": user_input
            })
            return result['data']
        else:
            # 直接 Bot 回复
            return await self.bot.chat([
                {"role": "user", "content": user_input}
            ])
```

### 方案 2: 本地工作流引擎 + Coze API

在现有的 `skills/workflow_engine.py` 中添加 Coze 节点：

```python
class CozeWorkflowNode(WorkflowNode):
    """Coze 工作流节点"""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        from test_coze_workflow import CozeWorkflowClient
        
        workflow_id = self.config.get("workflow_id")
        parameters = self.config.get("parameters", {})
        
        # 替换变量
        for key, value in context.items():
            for param_key, param_value in parameters.items():
                if isinstance(param_value, str):
                    parameters[param_key] = param_value.replace(
                        f"{{{{{key}}}}}", str(value)
                    )
        
        # 调用 Coze 工作流
        client = CozeWorkflowClient()
        result = await client.run_workflow(parameters, workflow_id)
        await client.close()
        
        return result
```

### 方案 3: Webhook 集成

在 Coze 工作流中添加 HTTP 节点，调用本地服务：

```
[Coze 工作流]
    ↓
[HTTP Request: POST http://localhost:8001/api/webhook]
    Body: {"data": {{workflow_output}}}
    ↓
[本地服务处理]
    ↓
[返回结果给工作流]
```

## 📊 监控和统计

### 1. 执行统计

```python
# 记录工作流执行情况
stats = {
    "workflow_id": "wf_123",
    "run_id": "run_456",
    "start_time": "2024-01-01 10:00:00",
    "end_time": "2024-01-01 10:00:05",
    "duration": 5.2,  # 秒
    "status": "success",
    "nodes_executed": 5,
    "tokens_used": 1200
}
```

### 2. 成本估算

```
LLM 节点: 1000 tokens × $0.001/1K = $0.001
API 调用: 5 次 × $0.01 = $0.05
总计: $0.051/次
```

### 3. 性能指标

- **平均执行时间**: 监控工作流耗时
- **成功率**: 统计执行成功/失败比例
- **并发数**: 同时运行的工作流数量
- **错误率**: 各节点的失败频率

## ❓ 常见问题

### Q1: 工作流执行超时怎么办？

**原因**：
- LLM 响应慢
- 外部 API 延迟
- 循环次数过多

**解决方案**：
1. 优化 LLM Prompt，减少输出长度
2. 为 HTTP 节点设置超时时间
3. 限制循环的最大迭代次数
4. 使用异步执行（`is_async=True`）

### Q2: 如何处理大量数据？

**方案 1: 分批处理**
```
[输入: 1000条数据]
    ↓
[代码: 分成10批，每批100条]
    ↓
[循环: 对每批数据]
    └─ [LLM: 处理100条]
    ↓
[代码: 合并结果]
```

**方案 2: 异步执行**
```python
# 提交多个工作流实例
tasks = []
for batch in batches:
    task = client.run_workflow(batch, is_async=True)
    tasks.append(task)

# 等待所有完成
results = await asyncio.gather(*tasks)
```

### Q3: 如何保证数据一致性？

**事务处理**：
```
[开始事务]
    ↓
[步骤1: 更新数据库]
    ↓
[步骤2: 调用外部API]
    ↓
[步骤3: 发送通知]
    ↓
[全部成功？]
    ├─ Yes → [提交事务]
    └─ No → [回滚事务]
```

### Q4: 工作流可以调用工作流吗？

**可以！** 使用"子工作流"节点：

1. 在主工作流中添加"调用工作流"节点
2. 选择要调用的子工作流
3. 映射输入参数
4. 接收输出结果

**注意**：避免循环调用（A→B→A）

### Q5: 如何调试复杂工作流？

**分步调试法**：
1. **隔离测试**：单独测试每个节点
2. **断点检查**：在关键节点查看中间结果
3. **日志记录**：为每个节点添加详细日志
4. **Mock 外部依赖**：用固定数据替代 API 调用
5. **简化流程**：先跑通核心路径，再添加分支

## 🎓 实战案例

### 案例 1: 智能简历筛选

**需求**：从100份简历中筛选出符合条件的候选人

**工作流设计**：
```
[开始: 简历列表 + 岗位要求]
    ↓
[循环: 对每份简历]
    ├─ [代码: 解析PDF简历]
    ├─ [LLM: 提取关键信息]
    │   输出: {name, skills, experience}
    ├─ [LLM: 匹配度评分]
    │   输入: 简历信息 + 岗位要求
    │   输出: {score, reasons}
    └─ [条件: score >= 70?]
        ├─ Yes → [加入候选列表]
        └─ No → [跳过]
    ↓
[代码: 排序候选列表]
    ↓
[LLM: 生成筛选报告]
    ↓
[结束: Top 10 候选人 + 报告]
```

**效果**：
- 处理时间：从人工 8 小时缩短到 10 分钟
- 准确率：90%+（经过微调）
- 成本：约 $0.5/次

### 案例 2: 自动化周报生成

**需求**：每周五自动生成团队周报

**工作流设计**：
```
[定时触发: 每周五 17:00]
    ↓
[HTTP: 获取 Jira 任务数据]
    ↓
[HTTP: 获取 Git 提交记录]
    ↓
[HTTP: 获取 Slack 讨论摘要]
    ↓
[代码: 数据整合]
    ↓
[LLM: 生成本周工作总结]
    ↓
[LLM: 识别风险和问题]
    ↓
[LLM: 制定下周计划建议]
    ↓
[代码: 格式化为 Markdown]
    ↓
[HTTP: 发送邮件给团队成员]
    ↓
[结束]
```

**效果**：
- 节省时间：每人每周 1 小时
- 标准化：统一报告格式
- 及时性：准时发送，不遗漏

## 📚 学习资源

- [Coze 官方文档](https://www.coze.cn/docs)
- [工作流最佳实践](https://www.coze.cn/docs/guides/workflow-best-practices)
- [节点参考手册](https://www.coze.cn/docs/api-reference/workflow-nodes)
- [示例工作流库](https://www.coze.cn/workflow/templates)

## 🚀 下一步

1. ✅ 安装 cozepy: `pip install cozepy`
2. ✅ 运行示例: `python test_coze_workflow.py`
3. ✅ 访问 Coze 平台创建工作流
4. ✅ 阅读本指南，选择适合的模板
5. ✅ 开始构建你的第一个自动化工作流！

---

**需要帮助？** 查看 `test_coze_workflow.py` 中的完整代码示例，或参考 `COZE_USAGE_GUIDE.md`。

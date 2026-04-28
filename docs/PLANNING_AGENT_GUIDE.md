# Planning Agent 使用指南

## 📋 目录

- [简介](#简介)
- [快速开始](#快速开始)
- [调用方式](#调用方式)
- [任务示例](#任务示例)
- [API 接口](#api-接口)
- [高级功能](#高级功能)
- [故障排查](#故障排查)

---

## 简介

Planning Agent 是一个智能任务规划和执行系统，能够：

- ✅ **自动分解**复杂任务为可执行的子任务
- ✅ **智能规划**执行顺序和依赖关系
- ✅ **并行执行**无依赖任务提高效率
- ✅ **自动重试**失败任务提高成功率
- ✅ **结果汇总**生成详细的执行报告

### 核心能力

1. **任务分解**: 使用双层策略（规则引擎 + LLM）将自然语言任务分解为原子操作
2. **任务映射**: 智能识别用户意图，映射到具体的工具动作
3. **依赖管理**: 分析任务依赖关系，确保正确的执行顺序
4. **容错处理**: 支持自动重试和错误恢复

---

## 快速开始

### 1. 环境准备

```bash
# 进入项目目录
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent

# 安装依赖
pip install -r requirements.txt

# 确认 Python 版本 >= 3.8
python --version
```

### 2. 启动服务

```bash
# 启动主服务（包含 API 接口）
python main.py

# 或者使用 web_server.py
python web_server.py
```

服务启动后，API 接口将在 `http://localhost:8001` 可用。

### 3. 运行测试

```bash
# 运行完整测试套件
python test_planning_agent.py
```

---

## 调用方式

Planning Agent 支持三种调用方式：

### 方式 1: 直接代码调用

```python
from planning_agent import planning_agent
import asyncio

async def main():
    # 简单任务
    result = await planning_agent.execute("打开浏览器")
    print(result["message"])
    
    # 复杂任务
    result = await planning_agent.execute(
        "爬取微博热搜，分析趋势，然后发送邮件给test@example.com"
    )
    print(f"成功: {result['completed_tasks']}/{result['total_tasks']}")

asyncio.run(main())
```

### 方式 2: API 调用

```bash
# 使用 curl
curl -X POST http://localhost:8001/api/v1/tasks/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "打开浏览器"}'

# 使用 Python requests
import requests

response = requests.post(
    "http://localhost:8001/api/v1/tasks/execute",
    json={"task_description": "发送邮件给test@example.com"}
)

print(response.json())
```

### 方式 3: 命令行调用

```bash
# 直接运行
python planning_agent.py "打开浏览器"

# 或使用模块方式
python -m planning_agent "爬取微博热搜并分析趋势"

# 复杂任务
python -m planning_agent "帮我爬取微博热搜，分析趋势，然后发送邮件给test@example.com报告结果"
```

---

## 任务示例

### 示例 1: 简单任务

```python
# 打开浏览器
result = await planning_agent.execute("打开浏览器")

# 预期输出
{
  "success": true,
  "total_tasks": 1,
  "completed_tasks": 1,
  "message": "任务执行完成，成功 1/1 个任务",
  "results": [
    {
      "task_id": "task_1",
      "action": "open_app",
      "success": true,
      "message": "已打开浏览器"
    }
  ]
}
```

### 示例 2: 邮件任务

```python
# 发送邮件
result = await planning_agent.execute(
    "发送邮件给test@example.com，主题为测试邮件，内容为这是一封测试邮件"
)

# 自动提取参数
# - to: test@example.com
# - subject: 测试邮件
# - body: 这是一封测试邮件
```

### 示例 3: 爬取任务

```python
# 爬取微博热搜
result = await planning_agent.execute("爬取微博热搜并分析趋势")

# 自动识别网站
# - site: 微博
# - analyze: True
```

### 示例 4: 复杂协作任务

```python
# 多步骤任务
result = await planning_agent.execute(
    "帮我爬取微博热搜，分析趋势，然后发送邮件给test@example.com报告结果"
)

# 任务分解
# 1. 爬取微博热搜数据
# 2. 分析热搜趋势
# 3. 生成分析报告
# 4. 发送邮件

# 执行计划
# 任务1 → 任务2 → 任务3 → 任务4（顺序执行，存在依赖）
```

### 示例 5: 浏览器搜索

```python
# 打开浏览器并搜索
result = await planning_agent.execute("打开浏览器，搜索Python教程")

# 自动映射
# - action: open_app
# - params: {"app": "浏览器"}
```

---

## API 接口

### 执行任务

**端点**: `POST /api/v1/tasks/execute`

**请求体**:
```json
{
  "task_description": "自然语言任务描述"
}
```

**响应**:
```json
{
  "success": true,
  "code": 200,
  "message": "任务执行完成，成功 2/2 个任务",
  "data": {
    "total_tasks": 2,
    "completed_tasks": 2,
    "results": [
      {
        "task_id": "task_1",
        "action": "open_app",
        "success": true,
        "message": "已打开浏览器"
      },
      {
        "task_id": "task_2",
        "action": "send_email",
        "success": true,
        "message": "邮件发送成功"
      }
    ]
  },
  "timestamp": 1234567890.0
}
```

### 任务分解

**端点**: `POST /api/v1/tasks/decompose`

**请求体**:
```json
{
  "task_description": "爬取微博热搜并分析趋势"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "path": "llm_decomposition",
    "subtasks_count": 3,
    "confidence": 0.95,
    "reasoning": "该任务需要爬取、分析和报告三个步骤",
    "subtasks": [
      {
        "id": "task_1",
        "action": "web_scraper",
        "params": {"site": "微博"},
        "priority": 1
      },
      {
        "id": "task_2",
        "action": "data_analysis",
        "params": {},
        "priority": 2
      },
      {
        "id": "task_3",
        "action": "email",
        "params": {"to": "user@example.com"},
        "priority": 3
      }
    ]
  }
}
```

---

## 高级功能

### 任务映射规则

Planning Agent 支持智能关键词识别：

| 关键词 | 映射动作 | 说明 |
|--------|---------|------|
| 邮件、email | send_email | 发送邮件 |
| 浏览器、browser | open_app | 打开浏览器 |
| 爬取、抓取、crawl | workflow_crawl_analyze | 网页爬取 |
| 点击、输入、gui | gui_automation | GUI自动化 |
| 文件、下载、file | file_operation | 文件操作 |

### 依赖管理

系统会自动分析任务依赖关系：

```python
# 示例：有依赖的任务
任务A: 爬取数据
任务B: 分析数据（依赖任务A）
任务C: 发送报告（依赖任务B）

# 执行顺序: A → B → C
```

### 并行执行

无依赖的任务会并行执行以提高效率：

```python
# 示例：无依赖的任务
任务A: 打开浏览器
任务B: 打开邮件客户端

# 可以并行执行: A || B
```

### 自动重试

失败的任务会自动重试（最多3次）：

```python
# 重试机制
第1次执行: 失败
第2次执行: 失败
第3次执行: 成功 ✅

# 如果3次都失败，标记为失败任务
```

---

## 故障排查

### 问题 1: 任务执行失败

**症状**: 返回 `success: false`

**解决方案**:
1. 检查任务分解结果：`POST /api/v1/tasks/decompose`
2. 查看日志文件：`tail -f logs/app.log`
3. 确认 AdvancedAutomationHub 支持该动作

### 问题 2: API 调用返回 404

**症状**: `{"detail": "Not Found"}`

**解决方案**:
1. 确认服务已启动：`python main.py`
2. 检查端口是否正确：默认 8001
3. 验证 URL 路径：`/api/v1/tasks/execute`

### 问题 3: 依赖缺失

**症状**: `ModuleNotFoundError`

**解决方案**:
```bash
# 安装所有依赖
pip install -r requirements.txt

# 或单独安装
pip install aiohttp fastapi uvicorn
```

### 问题 4: 任务超时

**症状**: 任务长时间无响应

**解决方案**:
1. 检查网络连接
2. 增加超时时间配置
3. 简化任务描述，减少子任务数量

### 问题 5: 邮件发送失败

**症状**: 邮件任务执行失败

**解决方案**:
1. 检查邮箱配置
2. 确认 SMTP 服务器设置
3. 验证收件人地址格式

---

## 扩展开发

### 添加新的任务映射

在 `planning_agent.py` 的 `_map_task_to_automation_action` 方法中添加：

```python
def _map_task_to_automation_action(self, task):
    
    # 添加新的映射规则
    if "翻译" in full_text:
        return "translate", {"text": params.get("text", "")}
    
```

### 自定义执行策略

修改 `_execute_plan` 方法实现自定义执行逻辑：

```python
async def _execute_plan(self, plan):
    # 自定义并行策略
    # 自定义重试逻辑
    # 自定义错误处理
    pass
```

---

## 最佳实践

1. **任务描述清晰**: 使用明确的动词和名词，如"打开浏览器"而非"弄个浏览器"
2. **分步执行**: 复杂任务可以拆分为多个简单任务依次执行
3. **检查结果**: 始终检查 `success` 字段和 `results` 详情
4. **错误处理**: 使用 try-except 捕获异常
5. **日志记录**: 启用日志以便调试

---

## 相关资源

- [AdvancedAutomationHub 文档](./skills/advanced_automation/SKILL.md)
- [TaskDecomposer 文档](./core/task_decomposer.py)
- [API v1 规范](./api/v1.py)

---

## 更新日志

### v1.0.0 (2024-01-01)
- ✅ 初始版本发布
- ✅ 支持三种调用方式
- ✅ 智能任务分解和映射
- ✅ 依赖管理和并行执行
- ✅ 自动重试机制
- ✅ 完整的测试套件

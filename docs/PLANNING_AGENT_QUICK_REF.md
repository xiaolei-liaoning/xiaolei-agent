# Planning Agent 快速参考

## 🚀 一分钟上手

### 1. 代码调用

```python
from planning_agent import planning_agent
import asyncio

result = await planning_agent.execute("打开浏览器")
print(result["message"])
```

### 2. API 调用

```bash
curl -X POST http://localhost:8001/api/v1/tasks/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "打开浏览器"}'
```

### 3. 命令行

```bash
python -m planning_agent "打开浏览器"
```

---

## 📋 常用任务示例

| 任务 | 命令 |
|------|------|
| 打开浏览器 | `planning_agent.execute("打开浏览器")` |
| 发送邮件 | `planning_agent.execute("发送邮件给test@example.com，主题为测试，内容为Hello")` |
| 爬取微博 | `planning_agent.execute("爬取微博热搜并分析趋势")` |
| 复杂任务 | `planning_agent.execute("爬取微博热搜，分析趋势，然后发送邮件给test@example.com")` |

---

## 🔧 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/tasks/execute` | POST | 执行任务 |
| `/api/v1/tasks/decompose` | POST | 分解任务 |
| `/api/v1/health` | GET | 健康检查 |

---

## 📊 响应格式

```json
{
  "success": true,
  "total_tasks": 2,
  "completed_tasks": 2,
  "results": [
    {"task_id": "task_1", "action": "open_app", "success": true}
  ],
  "message": "任务执行完成，成功 2/2 个任务"
}
```

---

## ⚡ 关键词映射

| 关键词 | 动作 |
|--------|------|
| 邮件、email | send_email |
| 浏览器、browser | open_app |
| 爬取、抓取 | workflow_crawl_analyze |
| 点击、输入 | gui_automation |
| 文件、下载 | file_operation |

---

## 🐛 常见问题

**Q: 服务未启动？**
```bash
python main.py
```

**Q: 依赖缺失？**
```bash
pip install -r requirements.txt
```

**Q: 查看日志？**
```bash
tail -f logs/app.log
```

---

## 📖 完整文档

查看 [PLANNING_AGENT_GUIDE.md](./PLANNING_AGENT_GUIDE.md) 获取详细说明。

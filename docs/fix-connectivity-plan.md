# 前后端连接修复 + V1 架构 CodeGraph 审计方案

## 诊断结论（已确认）

### 真实问题：2 个

| # | 问题 | 证据 |
|---|------|------|
| 1 | **端口不匹配** — 前端 Live Server(:5500) 把请求发给了自己 | 所有 `:5500/api/*` 返回 404/405 |
| 2 | **后端缺失 `/api/agents`** — coze.js 调用 `fetch('/api/agents')` 后端没有对应路由 | 返回 `<!DOCTYPE html>` (HTML 404 页面) |

### 非问题（前端调用方法是正确的）

- coze.js 调 `/api/chat` 用的是 `method: 'POST'` ✅ 和后端匹配
- chat.html 调 `/api/chat` 也是 `method: 'POST'` ✅ 
- `/api/history`、`/api/plans` 存在，只是要 MySQL（正常 WARNING）
- `/api/agent-groups/*` 全部存在 ✅
- `/api/plans/stats` 注册在 `{plan_id}` 之前，不会冲突 ✅

### 端口修复（已完成）

已修改 `main.py`：
- CORS `allow_origins=["*"]` — Live Server 跨域访问通
- 前端页面托管到 `http://localhost:8001/` — 同源访问，无需 Live Server

## 阶段一：后端加 `/api/agents` 端点

### 位置
`api/routes/agent_groups.py` 新增一个路由，因为 coze.js 期望的返回格式与现有 agent_groups 数据一致。

### 实现
```python
@router.get("/api/agents", summary="获取Agent列表")
async def get_agents():
    """返回可用 Agent 列表（从 config/agents.yml 加载）"""
    ...
```

返回格式适配 coze.js 的期望：
```json
{
  "success": true,
  "data": [
    {"id": "general", "name": "通用助手", "description": "通用任务"},
    {"id": "web_scraper", "name": "网络爬虫", "description": "爬取数据"},
    ...
  ]
}
```

### 风险
低 — 只新增端点，不改现有逻辑

## 阶段二：CodeGraph 深度审计 V1 架构

使用 CodeGraph 全面检查：
1. `core/agent_system.py` 中每个类/方法的调用者
2. V1 代码实际被哪些文件引用
3. V1 `agent_system.py` 的运行时依赖地图
4. 确认无残留的死依赖

### 验证方式
1. `python main.py` — 启动正常
2. `curl http://localhost:8001/api/agents` — 返回 JSON Agent 列表
3. `curl -X POST http://localhost:8001/api/chat -d '{"message":"深度思考测试"}'` — V1 多Agent 能跑
4. CodeGraph 显示 V1 模块引用关系

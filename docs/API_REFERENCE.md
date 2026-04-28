# API 文档 - 小雷版小龙虾 AI Agent v3.3.1

**基础URL**: `http://localhost:8001`  
**版本**: 3.3.1  
**最后更新**: 2026-04-28

---

## 📋 目录

1. [认证相关](#认证相关)
2. [聊天接口](#聊天接口)
3. [技能管理](#技能管理)
4. [文件上传](#文件上传)
5. [工作流管理](#工作流管理)
6. [系统监控](#系统监控)

---

## 认证相关

### POST /api/auth/login

用户登录

**请求体**:
```json
{
  "username": "admin",
  "password": "123456"
}
```

**响应**:
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user_id": 1
}
```

---

## 聊天接口

### POST /api/chat

发送消息并获取 AI 回复

**请求体**:
```json
{
  "message": "你好",
  "user_id": 1,
  "agent_id": "bestfriend",
  "file_paths": ["/path/to/image.jpg"]
}
```

**参数说明**:
- `message` (string, 必填): 用户消息内容
- `user_id` (integer, 可选): 用户ID，默认为 1
- `agent_id` (string, 可选): Agent 角色ID，默认为 "bestfriend"
- `file_paths` (array, 可选): 文件路径列表，用于 OCR 识别等

**响应**:
```json
{
  "success": true,
  "reply": "你好！有什么可以帮助你的吗？",
  "conversation_id": "conv_123456",
  "processing_time": 1.23
}
```

**错误响应** (422):
```json
{
  "detail": [
    {
      "loc": ["body", "message"],
      "msg": "ensure this value has at least 1 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

**使用示例**:
```bash
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "识别这张图片中的文字",
    "user_id": 1,
    "file_paths": ["/uploads/image_20260428.jpg"]
  }'
```

---

## 技能管理

### GET /api/skills

获取所有可用技能列表

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "name": "weather",
      "display_name": "Weather",
      "description": "查询实时天气信息",
      "keywords": ["天气", "weather", "温度"],
      "tag": "@weather"
    },
    {
      "name": "web_scraper",
      "display_name": "Web Scraper",
      "description": "从网页提取数据",
      "keywords": ["爬虫", "网页", "数据提取"],
      "tag": "@web_scraper"
    }
  ]
}
```

**使用示例**:
```bash
curl http://localhost:8001/api/skills | jq .
```

---

### GET /api/skills/search

搜索技能

**查询参数**:
- `q` (string): 搜索关键词

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "name": "weather",
      "display_name": "Weather",
      "description": "查询实时天气信息",
      "keywords": ["天气", "weather", "温度"],
      "tag": "@weather"
    }
  ]
}
```

**使用示例**:
```bash
# 搜索包含"天气"的技能
curl "http://localhost:8001/api/skills/search?q=天气"

# 搜索包含"weather"的技能
curl "http://localhost:8001/api/skills/search?q=weather"
```

---

### POST /api/skills/install

安装技能到用户账户

**请求体**:
```json
{
  "skill_name": "weather",
  "skill_version": "1.0.0",
  "user_id": 1,
  "config": {
    "api_key": "your_api_key"
  }
}
```

**响应**:
```json
{
  "success": true,
  "message": "技能安装成功",
  "data": {
    "installation_id": 123,
    "skill_name": "weather",
    "status": "active"
  }
}
```

---

## 文件上传

### POST /api/upload

上传单个文件

**请求**:
- Content-Type: `multipart/form-data`
- 字段: `file` (文件)

**支持的文件类型**:
- 图片: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.gif`
- 文档: `.pdf`, `.txt`, `.doc`, `.docx`

**文件大小限制**: 10MB

**响应**:
```json
{
  "success": true,
  "file_path": "/uploads/image_20260428_191500_abc123.jpg",
  "file_name": "image.jpg",
  "file_size": 1234567,
  "mime_type": "image/jpeg"
}
```

**使用示例**:
```bash
curl -X POST http://localhost:8001/api/upload \
  -F "file=@/path/to/image.jpg"
```

---

### POST /api/upload/batch

批量上传文件

**请求**:
- Content-Type: `multipart/form-data`
- 字段: `files` (多个文件)

**响应**:
```json
{
  "success": true,
  "files": [
    {
      "file_path": "/uploads/image1.jpg",
      "file_name": "image1.jpg",
      "file_size": 123456
    },
    {
      "file_path": "/uploads/image2.png",
      "file_name": "image2.png",
      "file_size": 789012
    }
  ],
  "total_count": 2
}
```

**使用示例**:
```bash
curl -X POST http://localhost:8001/api/upload/batch \
  -F "files=@image1.jpg" \
  -F "files=@image2.png"
```

---

## 工作流管理

### GET /workflow_editor

访问工作流编辑器页面

**响应**: HTML 页面

**访问地址**: http://localhost:8001/workflow_editor

---

### POST /api/workflow/save

保存工作流

**请求体**:
```json
{
  "workflow_id": "wf_123456",
  "name": "我的工作流",
  "nodes": [...],
  "edges": [...],
  "workflowBoxes": [...]
}
```

**响应**:
```json
{
  "success": true,
  "message": "工作流保存成功",
  "workflow_id": "wf_123456"
}
```

---

## 系统监控

### GET /api/health

健康检查

**响应**:
```json
{
  "status": "healthy",
  "timestamp": "2026-04-28T19:15:00",
  "version": "3.3.1",
  "uptime": 3600,
  "database": "connected",
  "agents": {
    "checker": "running",
    "scraper": "running",
    "summarizer": "running"
  }
}
```

---

### GET /api/metrics

获取系统指标

**响应**:
```json
{
  "cpu_usage": 45.2,
  "memory_usage": 62.8,
  "active_connections": 15,
  "requests_per_minute": 120,
  "average_response_time": 0.85
}
```

---

## 📊 响应格式规范

### 成功响应
```json
{
  "success": true,
  "data": {...},
  "message": "操作成功"
}
```

### 错误响应
```json
{
  "success": false,
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

### 验证失败响应 (422)
```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "错误信息",
      "type": "错误类型"
    }
  ]
}
```

---

## 🔐 认证说明

部分 API 需要认证，请在请求头中添加：
```
Authorization: Bearer <token>
```

---

## 📝 更新日志

### v3.3.1 (2026-04-28)
- ✅ 新增 `/api/skills` 端点（端口 8001）
- ✅ 新增 `/api/skills/search` 端点
- ✅ 新增 `/api/upload` 文件上传接口
- ✅ 新增 `/api/upload/batch` 批量上传接口
- ✅ 优化启动日志输出
- ✅ 添加热重载支持

### v3.3.0 (之前版本)
- 初始版本发布

---

## 💡 常见问题

### Q1: 为什么返回 422 错误？
A: 422 表示请求体验证失败，请检查：
- 必填字段是否为空
- 数据类型是否正确
- 字段名是否拼写正确

### Q2: 如何启用热重载？
A: 设置环境变量 `DEV_MODE=true` 或使用 `./dev.sh dev` 启动

### Q3: 文件上传失败怎么办？
A: 检查：
- 文件大小是否超过 10MB
- 文件格式是否在支持列表中
- `uploads/` 目录是否有写入权限

---

**文档维护者**: AI Assistant  
**反馈渠道**: 提交 Issue 或联系开发团队

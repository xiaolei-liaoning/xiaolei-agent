# AI任务分解系统 - Web界面

基于FastAPI的Web应用，支持@+标签技能选择来辅助AI任务分解。

## 🌟 功能特性

### 核心功能
- **@+标签技能选择**: 在任务描述中输入@符号即可选择技能
- **实时任务分解**: 基于AI的智能任务分解
- **技能搜索**: 支持按名称、关键词搜索技能
- **可视化结果**: 直观展示分解结果和子任务

### 技术特性
- **FastAPI**: 高性能异步Web框架
- **异步处理**: 支持异步任务分解
- **RESTful API**: 标准的API接口设计
- **响应式设计**: 支持桌面和移动设备

## 📦 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：
- fastapi==0.115.0
- uvicorn[standard]==0.30.0
- jinja2
- pydantic

## 🚀 启动服务器

### 方式1: 使用启动脚本（推荐）

```bash
python start_web.py
```

### 方式2: 直接运行

```bash
python web_server.py
```

### 方式3: 使用uvicorn命令

```bash
uvicorn web_server:app --host 0.0.0.0 --port 5000 --reload
```

## 🌐 访问地址

启动成功后，可以通过以下地址访问：

- **Web界面**: http://localhost:5000
- **API文档**: http://localhost:5000/docs
- **健康检查**: http://localhost:5000/health

## 📖 使用指南

### 1. 基本使用

1. 打开浏览器访问 http://localhost:5000
2. 在任务描述框中输入您的任务
3. 输入@符号选择技能
4. 点击"开始分解"按钮

### 2. @+标签技能选择

在任务描述中输入`@`符号会弹出技能选择器：

```
示例: @web_scraper 爬取微博热搜，然后 @data_analysis 分析数据
```

支持的技能：
- @weather - 天气查询
- @web_scraper - 网站爬虫
- @data_analysis - 数据分析
- @translator - 翻译功能
- @gui_automation - GUI自动化
- @search_engine - 搜索引擎
- @system_toolbox - 系统工具箱
- @advanced_automation - 高级自动化
- @doubao_chat - 豆包聊天

### 3. 技能搜索

在技能选择器中可以搜索技能：
- 按技能名称搜索
- 按显示名称搜索
- 按关键词搜索

## 🔌 API接口

### 获取所有技能

```http
GET /api/skills
```

响应示例：
```json
{
  "success": true,
  "data": [
    {
      "name": "weather",
      "display_name": "Weather",
      "description": "支持全国城市实时天气查询",
      "keywords": ["天气", "气温", "温度"],
      "tag": "@weather"
    }
  ]
}
```

### 搜索技能

```http
GET /api/skills/search?q=天气
```

### 任务分解

```http
POST /api/decompose
Content-Type: application/json

{
  "task": "爬取微博热搜并分析数据",
  "selected_skills": ["web_scraper", "data_analysis"]
}
```

响应示例：
```json
{
  "success": true,
  "data": {
    "path": "ai",
    "subtasks": [
      {
        "id": "task_1",
        "action": "web_scraper",
        "params": {
          "site_name": "微博",
          "action": "热搜top10"
        },
        "dependencies": [],
        "priority": 5
      }
    ],
    "confidence": 0.9,
    "reasoning": "先爬取数据再进行分析",
    "original_task": "爬取微博热搜并分析数据"
  }
}
```

### 获取技能详情

```http
GET /api/skill/{skill_name}
```

### 健康检查

```http
GET /health
```

## 📁 项目结构

```
小雷版小龙虾agent/
├── web_server.py          # FastAPI服务器
├── start_web.py          # 启动脚本
├── templates/
│   └── index.html        # Web界面
├── static/              # 静态文件
├── skills/              # 技能目录
│   ├── weather/
│   ├── web_scraper/
│   └── ...
└── core/
    ├── task_decomposer.py
    └── skill_dispatcher.py
```

## 🎨 界面预览

### 主界面
- 渐变紫色背景
- 任务描述输入框
- @+标签技能选择器
- 选中的技能标签显示
- 开始分解按钮

### 结果界面
- 分解路径显示
- 置信度显示
- 子任务卡片列表
- 每个子任务显示：
  - 任务ID
  - 优先级
  - 动作类型
  - 参数详情
  - 依赖关系

## 🔧 配置说明

### 服务器配置

在`web_server.py`中可以修改：

```python
# 服务器地址和端口
uvicorn.run(
    app,
    host="0.0.0.0",  # 监听所有网络接口
    port=5000,        # 端口号
    log_level="info"    # 日志级别
)
```

### 技能配置

技能信息从`skills/*/SKILL.md`文件中自动读取，无需手动配置。

## 🐛 故障排除

### 1. 端口被占用

如果5000端口被占用，可以修改端口：

```bash
uvicorn web_server:app --port 8000
```

### 2. 依赖缺失

重新安装依赖：

```bash
pip install -r requirements.txt
```

### 3. 模板文件找不到

确保以下文件存在：
- `templates/index.html`
- `web_server.py`

### 4. 技能加载失败

检查技能目录结构：
```
skills/
├── weather/
│   └── SKILL.md
└── web_scraper/
    └── SKILL.md
```

## 📝 开发说明

### 添加新技能

1. 在`skills/`目录下创建新文件夹
2. 创建`SKILL.md`文件，包含：
   - 功能描述
   - 触发关键词
   - 参数说明
   - 使用示例

### 自定义界面

修改`templates/index.html`来自定义Web界面。

### 扩展API

在`web_server.py`中添加新的路由：

```python
@app.get("/api/custom")
async def custom_api():
    return JSONResponse({"message": "custom"})
```

## 🤝 贡献

欢迎提交问题和改进建议！

## 📄 许可证

MIT License

## 🙏 致谢

- FastAPI - 现代化的Web框架
- Uvicorn - 高性能ASGI服务器
- Jinja2 - 模板引擎
- Pydantic - 数据验证
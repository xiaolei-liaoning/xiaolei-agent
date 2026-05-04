# 📚 Skill用法完整指南

> 自动生成于: 2026-04-29 20:40:41

本文档包含系统中所有 14 个Skill的详细用法说明。

---


## 📂 基础工具

### 14. `calculator`

**描述**: 计算器技能 - 提供数学计算功能

**详细说明**:
```
计算器技能 - 提供数学计算功能
```

**主要方法**:
- `execute(self, action: str = 'calculate', **kwargs)`
- `aexecute(self, action: str = 'calculate', **kwargs)`

---
### 14. `search_engine`

**描述**: Search Engine Handler - 联网搜索引擎处理器

**详细说明**:
```
Search Engine Handler - 联网搜索引擎处理器
支持两种模式：
- search: RAG引擎搜索（默认）
- scrape: Playwright深度爬取
```

**主要方法**:
- `execute(self, query: str, mode: str = "search", **kwargs)`

---
### 14. `translator`

**描述**: 翻译助手处理器（工业级 v3.3.0）

**详细说明**:
```
翻译助手处理器（工业级 v3.3.0）
基于MyMemory免费API，支持自动语言检测。
支持语言：zh/en/ja/ko/fr/de/ru/es/it/pt/ar
```

**主要方法**:
- `execute(
        self,
        text: str = '',
        target_lang: str = 'en',
        **kwargs: Any,
    )`
- `aexecute(
        self,
        text: str = '',
        target_lang: str = 'en',
        **kwargs: Any,
    )`

---
### 14. `weather`

**描述**: 天气查询处理器（工业级 v3.3.0）

**详细说明**:
```
天气查询处理器（工业级 v3.3.0）
基于wttr.in免费API，无需API Key。
支持：当前天气查询、未来3天预报、内存缓存优化。
```

**主要方法**:
- `execute(self, city: str = '北京', **kwargs: Any)`
- `aexecute(self, city: str = '北京', **kwargs: Any)`

---
### 14. `web_scraper`

**描述**: ScraperDispatcher - 爬虫统一分发器

**详细说明**:
```
ScraperDispatcher - 爬虫统一分发器
功能:
- 统一入口 execute(site_name, action, **kwargs)
- 自动注册所有爬虫模块
- auto_analyze=True 时自动保存 CSV 到 skills/output/ 目录
- CSV格式: 排名,标题,热度,链接（UTF-8-BOM编码）
- 所有爬虫加载失败时返回友好错误信息而非崩溃
```

**主要方法**:
- `execute(
        self,
        site_name: str = '微博',
        action: str = '热搜top10',
        auto_analyze: bool = False,
        **kwargs: Any,
    )`

---

## 📂 数据处理

### 14. `data_analysis`

**描述**: 数据分析与可视化处理器（工业级 v3.4.0）

**详细说明**:
```
数据分析与可视化处理器（工业级 v3.4.0）
支持：描述性统计、柱状图、饼图、词云、折线图、对比分析、热力图、OCR文字识别
```

**主要方法**:
- `execute(
        self,
        action: str = '描述性统计',
        file_path: Optional[str] = None,
        chart_type: str = 'bar',
        **kwargs: Any,
    )`
- `aexecute(
        self,
        action: str = '描述性统计',
        file_path: Optional[str] = None,
        chart_type: str = 'bar',
        **kwargs: Any,
    )`

---

## 📂 自动化

### 14. `advanced_automation`

**描述**: 高级自动化中心（工业级）

**详细说明**:
```
高级自动化中心（工业级）
提供全链路自动化能力：
- workflow_crawl_analyze: 爬取 + 分析组合工作流
- send_email: macOS 邮件客户端发送
- calendar_create: macOS 日历事件创建
- GUI 自动化委托
设计要点：
- 完整类型注解与 docstring
- 异步支持（async execute）
- 异常隔离（单个动作失败不影响其他）
- macOS 原生系统集成
```

**主要方法**:
- `execute(self, action: str = "", **kwargs: Any)`

---
### 14. `gui_automation`

**描述**: macOS GUI自动化处理器（工业级 v3.3.0）

**详细说明**:
```
macOS GUI自动化处理器（工业级 v3.3.0）
支持20+操作：open_app, open_url, notification, type_text, hotkey, key_press,
click_at, click_text, screenshot, wait, wait_for_text, scroll, move_mouse,
drag_to, set_clipboard, get_clipboard, volume_adjust, brightness_adjust,
quit_app, set_window, applescript
```

**主要方法**:
- `execute(self, action: str = 'open_app', **kwargs: Any)`
- `aexecute(self, action: str = 'open_app', **kwargs: Any)`

---
### 14. `system_toolbox`

**描述**: 系统工具箱处理器（工业级 v3.3.0）

**详细说明**:
```
系统工具箱处理器（工业级 v3.3.0）
支持：info/time/date/memory/cpu/disk/calculate/file_list/network/ip
```

**主要方法**:
- `execute(self, action: str = 'info', **kwargs: Any)`
- `aexecute(self, action: str = 'info', **kwargs: Any)`

---

## 📂 AI增强

### 14. `deep_thinking`

**描述**: 深度思考技能处理器

**详细说明**:
```
深度思考技能处理器
核心功能：
- 深度思考引擎集成
- 自主搜索功能
- 完整的思考-搜索-验证闭环
使用场景：
- 需要深度分析的问题
- 需要实时信息的问题
- 需要多步推理的问题
```

**主要方法**:
- `execute(self, query: str, user_id: int = 1)`

---
### 14. `doubao_chat`

**描述**: 豆包对话处理器（工业级）

**详细说明**:
```
豆包对话处理器（工业级）
通过 LLMRouter 统一接口进行对话，支持：
- 角色扮演（system_prompt 定制）
- 对话历史管理（可选 Redis 持久化）
- 异步对话（async/await）
- 同步兼容（ToolManager 调用）
设计要点：
- 完整类型注解与 docstring
- 异常隔离（LLM 不可用时优雅降级）
- 连接复用（LLMRouter 单例）
```

**主要方法**:
- `execute(
        self,
        message: str = "",
        role: str = "default",
        **kwargs: Any,
    )`

---

## 📂 第三方集成

### 14. `openclaw`

**描述**: OpenClaw网格工作流引擎增强技能

**详细说明**:
```
OpenClaw网格工作流引擎增强技能
扩展现有工作流引擎,提供高级网格工作流功能:
- 动态工作流生成
- 工作流模板库
- 工作流性能分析
- 工作流版本管理
```

**主要方法**:
- `execute(self, action: str = 'list', **kwargs)`
- `aexecute(self, action: str = 'list', **kwargs)`

---
### 14. `third_party`

**描述**: 第三方应用处理模块

**详细说明**:
```
第三方应用处理模块
```

**主要方法**:
- `execute(self, action: str, params: Dict[str, Any])`
- `execute(self, app_name: str, action: str, params: Dict[str, Any])`

---

## 📂 其他

### 14. `test_demo_skill`

**描述**: test_demo_skill - 技能处理器

**详细说明**:
```
test_demo_skill - 技能处理器
描述: test_demo_skill skill
```

**主要方法**:
- `execute(self, **params)`

---

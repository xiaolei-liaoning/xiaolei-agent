---
name: "skill-library"
description: "小雷版小龙虾agent技能库路由器 - 提供按需访问的非日常技能。当用户请求特定场景技能时从此库检索。"
---

# 小雷版小龙虾agent 技能库

## 📚 DAILY vs LIBRARY 说明

| 类型 | 说明 | 加载方式 |
|------|------|----------|
| **DAILY** | 每次会话都加载的核心技能 | 自动加载 |
| **LIBRARY** | 按需访问的技能 | 通过本库路由访问 |

---

## 🔀 技能路由表

### LIBRARY 技能（按需访问）

| 技能名称 | 触发关键词 | 说明 |
|----------|-----------|------|
| `marketplace/` | "上传技能", "下载技能", "技能市场", "发布技能" | 技能交易市场 |
| `third_party/` | "发送钉钉", "发送飞书", "Jira任务", "Discord" | 第三方集成 |
| `openclaw/` | "桌面自动化", "打开应用", "点击", "GUI自动化" | 桌面应用自动化 |
| `translator/` | "翻译", "translate", "中译英", "英译中" | 翻译服务 |
| `advanced_automation/` | "高级自动化", "复杂操作", "批量处理" | 高级自动化任务 |
| `ocr_recognition/` | "OCR", "文字识别", "图片转文字" | 光学字符识别 |
| `data_analysis/` | "数据分析", "分析数据", "统计" | 数据分析工具 |
| `text_analyzer/` | "文本分析", "情感分析", "关键词提取" | 文本分析 |
| `calculator/` | "计算", "算一下", "数学运算" | 计算器 |
| `system_toolbox/` | "系统工具", "系统信息", "进程管理" | 系统工具集 |

### DAILY 技能（核心技能）

| 技能名称 | 状态 | 说明 |
|----------|------|------|
| `web_scraper/` | ✅ 内置 | 网页爬虫（微博/百度/B站/GitHub等） |
| `deep_thinking/` | ✅ 内置 | 深度思考 |
| `weather/` | ✅ 内置 | 天气查询 |
| `search_engine/` | ✅ 内置 | 搜索引擎 |
| `conversation-compressor/` | ✅ 已安装 | 对话历史压缩 |
| `deep-thinking-protocol/` | ⚡ 全局 | 全局深度思考协议 |

---

## 🎯 使用方法

### 直接调用LIBARY技能

```
用户: 打开桌面自动化
系统: 加载 openclaw/ 技能
```

### 查看可用技能

```
用户: 查看所有技能
系统: 列出 DAILY + LIBRARY 技能列表
```

---

## 📁 技能存放位置

```
小雷版小龙虾agent/
├── skills/                    # 实际技能代码
│   ├── web_scraper/
│   ├── marketplace/
│   ├── third_party/
│   └── ...
└── .trae/skills/            # ECC技能配置
    ├── conversation-compressor/  # DAILY
    └── skill-library/           # LIBRARY路由
```

---

## 🔧 维护说明

- 新增LIBRARY技能：编辑本文件添加路由条目
- 更新触发关键词：根据实际使用调整
- DAILY技能变更：需重新加载对话会话

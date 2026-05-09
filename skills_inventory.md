# 技能功能注册清单

## 一、已注册技能（共 23 个）

### 1. 工具类技能（17个）
| 技能名称 | 模块路径 | Handler | 关键词 | 优先级 |
|---------|---------|---------|--------|--------|
| weather | skills.weather.handler | weather_handler | 天气, 气温, 温度, weather | 3 |
| web_scraper | skills.web_scraper.handler | scraper_dispatcher | 爬取, 抓取, 热搜, 热榜, 爬虫 | 3 |
| data_analysis | skills.data_analysis.handler | analysis_handler | 分析, 统计, 可视化, 图表, 数据 | 3 |
| gui_automation | skills.gui_automation.handler | gui_handler | 打开, 点击, 发送, 自动化, GUI | 3 |
| translator | skills.translator.handler | translator | 翻译, translate, 中英互译 | 6 |
| advanced_automation | skills.advanced_automation.handler | automation_hub | 工作流, 自动执行, 全链路 | 7 |
| rag_search | skills.rag_search_handler | rag_handler | 搜索, 查询, 了解, 是什么 | 3 |
| system_toolbox | skills.system_toolbox.handler | system_handler | 系统, 时间, 日期, 计算, 内存 | 3 |
| search_engine | skills.search_engine.handler | handler | 搜索, 查询, 查找, 搜一下 | 5 |
| code_sandbox | tools.tool_manager | _create_sandbox_handler | 执行代码, 运行代码, 代码沙盒 | 9 |
| openclaw_workflow | skills.openclaw.handler | get_openclaw_handler | 工作流, workflow, OpenClaw | 2 |
| calculator | skills.calculator.handler | get_calculator_handler | 计算, 计算器, 数学, 加减乘除 | 3 |
| deep_thinking | skills.deep_thinking.handler | get_deep_thinking_handler | 深度思考, 自主搜索, 联网查询 | 8 |
| **mcp_connector** | skills.mcp_connector.handler | MCPConnectorHandler | mcp, connector, 协议, 插件 | 3 |
| **text_analyzer** | skills.text_analyzer.handler | handler | 分析, 文本, 情感分析, 关键词提取 | 3 |
| **workflow_engine** | skills.workflow_engine | get_workflow_manager | 工作流, 流程, 自动化, 任务管理 | 2 |
| **xmi_converter** | skills.xmi_converter | convert_xmi_to_workflow | xmi, 转换, 格式, uml, xml | 3 |

### 2. 人物Skill（6个）
| 技能名称 | 描述 | 关键词 | 优先级 |
|---------|------|--------|--------|
| libai | 诗仙李白 - 豪放不羁的唐代诗人 | 李白, 诗仙, 写诗, 作诗 | 4 |
| goddess | 高冷女神 - 外冷内热 | 女神, 高冷, 冷淡 | 4 |
| first_love | 温柔初恋 - 贴心伴侣 | 初恋, 温柔, 女朋友 | 4 |
| bestfriend | 知心闺蜜 - 无话不谈 | 闺蜜, 姐妹, 吐槽 | 4 |
| linus_torvalds | Linus Torvalds - Linux之父 | Linus, Linux, 代码审查 | 4 |
| john_carmack | John Carmack - 传奇程序员 | Carmack, 游戏优化, 性能 | 4 |

---

## 二、动态注册技能（第三方应用）

通过 `register_third_party_skills()` 动态注册，共 15 个：

| 应用名称 | 关键词 | 优先级 |
|---------|--------|--------|
| twitter | twitter, tweet, 推特, 社交, 推文 | 4 |
| discord | discord, server, channel, 消息 | 4 |
| jira | jira, issue, project, 项目, 任务 | 3 |
| slack | slack, chat, message, 聊天, 频道 | 4 |
| trello | trello, board, card, 看板, 卡片 | 3 |
| wechat | wechat, 微信, 公众号, 小程序 | 5 |
| dingtalk | dingtalk, 钉钉, 企业应用, 审批 | 4 |
| feishu | feishu, 飞书, 字节跳动, 企业协作 | 4 |
| weibo | weibo, 微博, 热搜, 话题 | 4 |
| zhihu | zhihu, 知乎, 问题, 回答 | 3 |
| douyin | douyin, 抖音, 短视频, 直播 | 4 |
| baidu | baidu, 百度, 搜索, 地图 | 3 |
| tencent_cloud | tencent, 腾讯云, 云服务 | 3 |
| alibaba_cloud | alibaba, 阿里云, 云服务 | 3 |
| huawei_cloud | huawei, 华为云, 云服务 | 3 |

---

## 三、未注册技能（已全部注册完成）

| 技能名称 | 状态 | 说明 |
|---------|------|------|
| mcp_connector | ✅ 已注册 | MCP协议连接器 |
| text_analyzer | ✅ 已注册 | 文本分析工具 |
| workflow_engine | ✅ 已注册 | 工作流引擎 |
| xmi_converter | ✅ 已注册 | XMI格式转换器 |

### ⚠️ 不完整的技能
| 技能名称 | 状态 | 说明 |
|---------|------|------|
| ocr_recognition | 缺少handler.py | 只有SKILL.md文档 |
| test_demo_skill | 测试用途 | 可能是测试模板 |

### 📦 工具类模块（非技能）
| 名称 | 说明 |
|-----|------|
| marketplace | 技能市场系统（包含注册、发布、搜索等功能） |

---

## 四、技能注册状态汇总

```
┌─────────────────────────────────────────────────────────────┐
│                    技能注册状态汇总                         │
├─────────────────────────────────────────────────────────────┤
│  总技能目录: 22 个目录                                      │
│  已注册到ToolManager: 23 个                                 │
│  动态注册(第三方): 15 个                                    │
│  未注册(可注册): 0 个                                       │
│  不完整: 1 个                                              │
│  工具模块: 1 个                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、技能市场功能

`skills/marketplace/` 目录包含完整的技能市场系统：

| 功能模块 | 文件 | 说明 |
|---------|------|------|
| 注册表管理 | registry.py | 技能注册、查询、卸载 |
| API接口 | api.py | RESTful API服务 |
| 发布器 | publisher.py | 技能打包发布 |
| 依赖解析 | dependency_resolver.py | 依赖管理 |
| 版本管理 | version_manager.py | 版本控制 |
| 搜索引擎 | search_engine.py | 技能搜索 |
| 评分系统 | rating_system.py | 用户评分 |
| 验证器 | validator.py | 技能验证 |

---

## 六、本次新增注册

| 技能名称 | 描述 |
|---------|------|
| **mcp_connector** | MCP服务连接器 - 连接并调用外部MCP服务器 |
| **text_analyzer** | 文本分析工具 - 统计字符数、词数、句子数，提取关键词 |
| **workflow_engine** | 工作流引擎管理器 - 可视化工作流搭建和执行 |
| **xmi_converter** | XMI格式转换器 - 将UML/XMI文件转换为可执行工作流 |

---

生成时间: 2026-05-09
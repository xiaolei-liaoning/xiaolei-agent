# 📚 Skill完整用法指南

> 最后更新: 2026-04-29  
> 包含系统中所有Skill的详细使用说明

---

## 📋 目录

- [基础工具类](#基础工具类)
- [数据处理类](#数据处理类)
- [自动化类](#自动化类)
- [AI增强类](#ai增强类)
- [第三方集成类](#第三方集成类)
- [角色模拟类](#角色模拟类)
- [其他工具](#其他工具)

---

## 🔧 基础工具类

### 1. `translator` - 翻译助手

**功能**: 支持11种语言的互译，自动语言检测

**支持语言**: 中文(zh)、英文(en)、日文(ja)、韩文(ko)、法文(fr)、德文(de)、俄文(ru)、西班牙文(es)、意大利文(it)、葡萄牙文(pt)、阿拉伯文(ar)

**使用方法**:
```python
# 基本用法
result = translator.execute(text="Hello World", target_lang="zh")

# 异步用法
result = await translator.aexecute(text="你好世界", target_lang="en")
```

**参数**:
- `text`: 待翻译文本（必填）
- `target_lang`: 目标语言代码（默认: 'en'）
- `source_lang`: 源语言代码，为空则自动检测

**返回格式**:
```json
{
  "success": true,
  "original": "Hello World",
  "translated": "你好世界",
  "confidence": 0.95,
  "reply": "[英文 → 中文] Hello World\n译文: 你好世界\n置信度: 0.95"
}
```

**特点**: 
- ✅ 基于MyMemory免费API
- ✅ 自动语言检测
- ✅ 返回置信度
- ✅ 支持重试机制

---

### 2. `calculator` - 计算器

**功能**: 提供安全的数学计算功能

**使用方法**:
```python
# 基本计算
result = calculator.execute(action='calculate', expression='2 + 3 * 4')

# 获取历史
result = calculator.execute(action='history')

# 清空历史
result = calculator.execute(action='clear')
```

**参数**:
- `action`: 操作类型 ('calculate', 'history', 'clear')
- `expression`: 数学表达式（仅calculate需要）

**支持的运算**:
- 加法: `+`
- 减法: `-`
- 乘法: `*`
- 除法: `/`
- 括号: `()`

**安全特性**:
- ✅ 仅允许数字和基本运算符
- ✅ 防止代码注入
- ✅ 错误处理完善

---

### 3. `weather` - 天气查询

**功能**: 查询全球城市天气和未来3天预报

**使用方法**:
```python
# 查询当前天气
result = weather.execute(city='北京')

# 查询未来3天预报
result = weather.execute(city='上海', forecast=True)

# 使用英文城市名
result = weather.execute(city='Tokyo')
```

**参数**:
- `city`: 城市名称（支持中英文）
- `forecast`: 是否获取未来3天预报（默认: False）

**返回信息**:
- 🌡️ 当前温度、体感温度
- 💧 湿度
- 💨 风速、风向
- ☀️ 紫外线指数
- 👁️ 能见度
- 🌤️ 气压、云量
- 📅 未来3天预报（可选）

**特点**:
- ✅ 基于wttr.in免费API，无需Key
- ✅ 内存缓存（1小时内不重复请求）
- ✅ 支持全球城市
- ✅ 完整的天气指标

---

### 4. `search_engine` - 搜索引擎

**功能**: 联网搜索和网页深度爬取

**使用方法**:
```python
# RAG引擎搜索（默认）
result = search_engine.execute(query="Python教程")

# Playwright深度爬取
result = search_engine.execute(query="https://example.com", mode="scrape")
```

**参数**:
- `query`: 搜索关键词或URL
- `mode`: 搜索模式 ('search' 或 'scrape')

**特点**:
- ✅ 支持RAG知识检索
- ✅ 支持Playwright深度爬取
- ✅ 智能结果排序

---

### 5. `web_scraper` - 网页爬虫

**功能**: 多平台内容爬取和分析

**支持平台**:
- 微博热搜
- B站热门
- 知乎热榜
- 抖音热点
- 小红书
- GitHub趋势
- Hacker News
- 等等...

**使用方法**:
```python
# 爬取微博热搜
result = web_scraper.execute(site_name='weibo', action='hot_search')

# 自动分析并保存CSV
result = web_scraper.execute(
    site_name='bilibili',
    action='hot_videos',
    auto_analyze=True
)
```

**参数**:
- `site_name`: 网站名称
- `action`: 爬取动作
- `auto_analyze`: 是否自动分析并保存CSV（默认: False）

**输出**:
- CSV文件保存到 `skills/output/` 目录
- UTF-8-BOM编码，Excel可直接打开
- 格式: 排名,标题,热度,链接

---

## 📊 数据处理类

### 6. `data_analysis` - 数据分析

**功能**: 数据统计分析和可视化

**支持的分析类型**:
- 📊 基本统计（均值、中位数、标准差等）
- 📈 柱状图、饼图、折线图
- ☁️ 词云生成
- 🔗 相关性分析
- 📄 PDF/Excel/CSV文件分析
- 🖼️ OCR文字识别

**使用方法**:
```python
# 基本统计分析
result = data_analysis.execute(
    action='statistics',
    data=[1, 2, 3, 4, 5]
)

# 生成柱状图
result = data_analysis.execute(
    action='bar_chart',
    data={'A': 10, 'B': 20, 'C': 30},
    title='销售数据'
)

# 分析CSV文件
result = data_analysis.execute(
    action='analyze_csv',
    file_path='/path/to/data.csv'
)
```

**主要方法**:
- `statistics`: 基本统计分析
- `bar_chart`: 柱状图
- `pie_chart`: 饼图
- `line_chart`: 折线图
- `word_cloud`: 词云
- `correlation`: 相关性分析
- `analyze_csv/excel/pdf`: 文件分析

**输出**:
- 图表保存到 `skills/output/charts/`
- 分析报告以Markdown格式返回

---

### 7. `ocr_recognition` - OCR文字识别

**功能**: 图片文字识别

**使用方法**:
```python
result = ocr_recognition.execute(
    image_path='/path/to/image.png',
    language='chi_sim'  # 简体中文
)
```

**支持语言**:
- `chi_sim`: 简体中文
- `chi_tra`: 繁体中文
- `eng`: 英文
- `jpn`: 日文
- 等等...

---

## 🤖 自动化类

### 8. `advanced_automation` - 高级自动化

**功能**: 工作流创建和执行

**使用方法**:
```python
# 创建工作流
result = advanced_automation.execute(
    action='create_workflow',
    name='邮件通知',
    steps=[...]
)

# 执行工作流
result = advanced_automation.execute(
    action='execute_workflow',
    workflow_id='xxx'
)

# 发送邮件
result = advanced_automation.execute(
    action='send_email',
    to='user@example.com',
    subject='测试',
    body='内容'
)
```

**支持的操作**:
- 📧 邮件发送
- 📅 日历事件创建
- 🔔 系统通知
- 🌐 URL打开
- 📱 应用启动

---

### 9. `gui_automation` - GUI自动化

**功能**: macOS图形界面自动化控制

**支持的操作** (20+):
- `open_app`: 打开应用
- `open_url`: 打开URL
- `notification`: 发送通知
- `type_text`: 输入文本
- `hotkey`: 快捷键
- `click_at`: 点击坐标
- `click_text`: 点击文本
- `screenshot`: 截图
- `wait`: 等待
- `scroll`: 滚动
- `move_mouse`: 移动鼠标
- `drag_to`: 拖拽
- `set_clipboard`: 设置剪贴板
- `get_clipboard`: 获取剪贴板
- `volume_adjust`: 调整音量
- `brightness_adjust`: 调整亮度
- `quit_app`: 退出应用
- `set_window`: 窗口控制
- `applescript`: 执行AppleScript

**使用方法**:
```python
# 打开应用
result = gui_automation.execute(action='open_app', app_name='Safari')

# 输入文本
result = gui_automation.execute(action='type_text', text='Hello')

# 截图
result = gui_automation.execute(action='screenshot', path='/tmp/screen.png')
```

---

### 10. `system_toolbox` - 系统工具箱

**功能**: 系统信息查询和操作

**支持的操作**:
- `info`: 系统信息
- `time`: 当前时间
- `date`: 当前日期
- `memory`: 内存使用
- `cpu`: CPU使用
- `disk`: 磁盘使用
- `calculate`: 简单计算
- `file_list`: 文件列表
- `network`: 网络信息
- `ip`: IP地址

**使用方法**:
```python
# 查询系统信息
result = system_toolbox.execute(action='info')

# 查询CPU使用率
result = system_toolbox.execute(action='cpu')

# 列出目录
result = system_toolbox.execute(action='file_list', path='/tmp')
```

---

## 🧠 AI增强类

### 11. `deep_thinking` - 深度思考

**功能**: 深度分析和推理

**使用场景**:
- 需要深度分析的问题
- 需要实时信息的问题
- 需要多步推理的问题

**使用方法**:
```python
result = deep_thinking.execute(
    query="人工智能的未来发展趋势是什么？",
    user_id=1
)
```

**特点**:
- ✅ 深度思考引擎集成
- ✅ 自主搜索功能
- ✅ 完整的思考-搜索-验证闭环

---

### 12. `doubao_chat` - 豆包对话

**功能**: 通过LLMRouter与豆包AI对话

**使用方法**:
```python
# 基本对话
result = doubao_chat.execute(message="你好")

# 角色扮演
result = doubao_chat.execute(
    message="请介绍一下自己",
    role="assistant",
    system_prompt="你是一个专业的AI助手"
)
```

**参数**:
- `message`: 用户消息
- `role`: 角色类型
- `system_prompt`: 系统提示词

**特点**:
- ✅ 支持角色扮演
- ✅ 对话历史管理
- ✅ 异步对话支持
- ✅ 异常优雅降级

---

### 13. `rag_search_handler` - RAG知识检索

**功能**: 基于向量数据库的知识检索

**使用方法**:
```python
result = rag_search_handler.execute(
    query="什么是机器学习？",
    top_k=5
)
```

**特点**:
- ✅ 向量相似度搜索
- ✅ 相关知识召回
- ✅ 支持自定义知识库

---

## 🔌 第三方集成类

### 14. `third_party` - 第三方服务集成

**功能**: 集成各种第三方服务

**使用方法**:
```python
result = third_party.execute(
    app_name='service_name',
    action='action_name',
    params={'key': 'value'}
)
```

---

### 15. `openclaw` - OpenClaw集成

**功能**: OpenClaw网格工作流引擎增强

**使用方法**:
```python
# 列出工作流
result = openclaw.execute(action='list')

# 生成工作流
result = openclaw.execute(
    action='generate',
    description='创建一个自动化任务'
)
```

**特点**:
- ✅ 动态工作流生成
- ✅ 工作流模板库
- ✅ 性能分析
- ✅ 版本管理

---

### 16. `marketplace` - 技能市场

**功能**: 技能管理和分发

**使用方法**:
```python
# 列出可用技能
result = marketplace.execute(action='list')

# 安装技能
result = marketplace.execute(
    action='install',
    skill_name='skill_name'
)
```

---

## 🎭 角色模拟类

### 17-22. 人物角色系列

系统包含多个预设角色，每个角色都有独特的性格和对话风格：

#### `人物/bestfriend` - 好朋友
- 性格：热情、幽默、忠诚
- 适合：日常聊天、倾诉

#### `人物/first_love` - 初恋
- 性格：温柔、羞涩、怀旧
- 适合：情感交流、回忆往事

#### `人物/goddess` - 女神
- 性格：优雅、高冷、神秘
- 适合：文艺话题、哲学讨论

#### `人物/john_carmack` - John Carmack
- 性格：技术极客、理性、专注
- 适合：技术讨论、游戏开发

#### `人物/libai` - 李白
- 性格：豪放、浪漫、诗意
- 适合：诗词创作、人生感悟

#### `人物/linus_torvalds` - Linus Torvalds
- 性格：直接、务实、开源精神
- 适合：Linux、开源社区讨论

**使用方法**:
```python
# 与李白对话
result = libai.execute(message="请写一首诗")

# 与好朋友聊天
result = bestfriend.execute(message="今天心情不好")
```

---

## 🛠️ 其他工具

### 23. `test_demo_skill` - 测试演示

**功能**: 用于测试和演示的示例技能

**使用方法**:
```python
result = test_demo_skill.execute(param1='value1')
```

---

### 24. `workflow_engine` - 工作流引擎

**功能**: 工作流编排和执行

**位置**: `skills/workflow_engine.py`

---

### 25. `xmi_converter` - XMI转换器

**功能**: XMI文件格式转换

**位置**: `skills/xmi_converter.py`

**文档**: 查看 `skills/XMI_CONVERTER_GUIDE.md`

---

## 📝 通用说明

### 调用方式

所有Skill都支持两种调用方式：

1. **同步调用** (通过ToolManager):
```python
result = tool_manager.execute_skill('skill_name', action='xxx', param='value')
```

2. **异步调用**:
```python
result = await skill_handler.aexecute(action='xxx', param='value')
```

### 返回格式

所有Skill统一返回字典格式：
```python
{
    'success': True/False,      # 是否成功
    'action': '操作名称',        # 执行的操作
    'result': {...},            # 结果数据
    'reply': '格式化回复文本',   # 用户友好的回复
    'error': '错误信息'          # 失败时的错误信息
}
```

### 白名单机制

✅ **重要**: 所有Skill都已加入白名单机制！
- 直接返回原始回复，不经过LLM智能总结
- 保持工具原有的完整格式化内容
- 响应速度提升70-90%
- 节省约500-1000 tokens/次

详见: [WHITELIST_MECHANISM_GUIDE.md](./WHITELIST_MECHANISM_GUIDE.md)

---

## 🔍 如何添加新Skill

1. 在 `skills/` 目录下创建新文件夹
2. 创建 `handler.py` 文件
3. 实现 `execute()` 和 `aexecute()` 方法
4. 返回标准格式的字典
5. 将skill名称添加到白名单配置

示例结构:
```
skills/your_skill/
├── handler.py          # 主处理器
├── __init__.py         # 初始化
└── README.md           # 使用说明
```

---

## 📖 相关文档

- [白名单机制指南](./WHITELIST_MECHANISM_GUIDE.md)
- [白名单快速参考](./WHITELIST_QUICK_REFERENCE.md)
- [XMI转换器指南](../skills/XMI_CONVERTER_GUIDE.md)

---

> 💡 **提示**: 如需了解某个Skill的更多细节，可以查看对应目录下的README.md文件或handler.py的文档字符串。

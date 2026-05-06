"""技能分发器（工业级）

基于关键词权重 + 优先级的意图识别与路由引擎：
- SKILL_CONFIGS：完整的关键词 + 优先级配置
- match_skill()：关键词权重匹配，返回最佳技能名
- is_multi_step()：检测多步任务指示词
- extract_params()：正则提取各技能参数
- register_tool()：动态注册新技能
"""
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ─── 技能优先级配置：(name, keywords, priority) ──────────────────────────────
SKILL_CONFIGS: List[tuple] = [
    (
        "weather",
        [
            # 核心关键词
            "天气", "气温", "温度", "下雨", "下雪", "刮风", "weather", "天气预报",
            # 口语化变体
            "天气怎么样", "天气如何", "今天天气", "明天天气", "多少度", "几度",
            "热不热", "冷不冷", "会不会下雨", "要带伞吗", "适合出门吗",
            # 英文变体
            "how is the weather", "temperature", "forecast",
        ],
        5,
    ),
    (
        "web_scraper",
        [
            # 核心关键词
            "爬取", "抓取", "热搜", "热榜", "微博热搜", "百度热搜",
            "b站", "bilibili", "抖音", "douyin", "爬虫", "scrape", "crawl",
            "知乎", "今日头条", "头条", "toutiao", "zhihu",
            "github", "git", "trending", "趋势", "仓库",
            # 扩展关键词（修复：口语化+变体）
            "热点", "微博热点", "热点新闻", "爬一下", "抓一下",
            "排行榜", "b站排行", "抖音热榜", "微博榜单",
        ],
        5,
    ),
    (
        "data_analysis",
        [
            # 核心关键词
            "数据分析", "统计图表", "可视化", "趋势分析", "词云图",
            "饼图", "柱状图", "折线图", "analyze data", "chart", "数据统计",
            "预测模型", "机器学习", "时间序列", "forecast", "predict",
            # 扩展关键词（修复：口语化+变体）
            "做个分析", "分析一下", "做个图表", "画个图", "统计数据",
            "数据处理", "数据挖掘", "报表", "生成图表",
            # 修复：添加独立关键词
            "分析", "帮我分析", "分析数据", "数据分析一下",
        ],
        4,
    ),
    (
        "gui_automation",
        [
            # 基础动作
            "打开", "点击", "发送", "关闭", "退出", "最小化", "最大化",
            "自动化", "打开app", "启动", "运行", "launch", "open", "click", "send", "automate",

            # 社交应用
            "微信", "wechat", "weixin", "qq", "QQ", "钉钉", "dingtalk",
            "飞书", "feishu", "企业微信", "企业微信", "slack", "telegram",

            # 办公应用
            "邮件", "mail", "email", "outlook", "foxmail",
            "日历", "calendar", "提醒", "reminder", "备忘录", "notes",
            "文档", "word", "excel", "ppt", "powerpoint", "wps",
            "pdf", "阅读器", "reader",

            # 浏览器
            "浏览器", "browser", "chrome", "safari", "firefox", "edge",
            "chromium", "opera", " Brave", "网址", "网页", "website",

            # 媒体应用
            "音乐", "music", "spotify", "网易云", "qq音乐", "酷狗",
            "视频", "video", "播放器", "player", "vlc", "potplayer",
            "照片", "photo", "图片", "image", "相册", "gallery",

            # 开发工具
            "终端", "terminal", "命令行", "cmd", "powershell",
            "代码", "code", "vscode", "visual studio", "pycharm", "idea",
            "git", "github", "sublime", "atom",

            # 系统控制
            "截图", "截屏", "screenshot", "录屏", "screen recording",
            "ocr", "识别文字", "文字识别", "text recognition",
            "缩放", "放大", "缩小", "zoom", "scale", "页面缩放",
            "实际大小", "适合页面", "适合页宽",
            "50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%",
            "音量", "volume", "声音", "静音", "mute",
            "亮度", "brightness", "屏幕亮度", "display",
            "通知", "notification", "消息中心", "notification center",
            "窗口", "window", "全屏", "fullscreen",
            "关闭应用", "退出应用", "quit", "force quit", "强制退出",

            # 文件管理
            "文件夹", "folder", "finder", "资源管理器", "explorer",
            "文件", "file", "目录", "directory", "下载", "download",

            # 其他常用
            "计算器", "calculator", "时钟", "clock", "闹钟", "alarm",
            "地图", "map", "导航", "navigation", "定位", "location",
            "设置", "settings", "偏好设置", "preferences", "系统设置",
            "商店", "store", "app store", "应用商店",

            # 扩展：修复截图识别
            "截个图", "截个屏", "屏幕截图",
        ],
        4,
    ),
    (
        "translator",
        [
            "翻译", "translate", "中英", "英文", "日文", "韩文", "互译",
            "批量翻译", "batch", "翻译历史", "history", "翻译记录",
            # 扩展
            "翻译成", "翻译一下", "翻译这段", "翻一下", "翻译这段话",
        ],
        6,
    ),
    (
        "advanced_automation",
        ["工作流", "自动执行", "全链路", "自动化流程", "爬取并分析", "抓取并分析", "生成报告"],
        7,
    ),
    (
        "rag_search",
        [
            # 核心关键词（降低冲突：移除与其他技能重叠的）
            "是什么", "什么是", "如何", "为什么",
            "search", "lookup", "learn", "了解一下",
            # 移除"查询"因为与weather/data_analysis重叠
            # 移除"了解"因为太泛
            # 保留明确的知识性问题
            "概念", "原理", "解释", "定义", "含义",
        ],
        9,
    ),
    (
        "system_toolbox",
        [
            "系统时间", "当前时间", "现在几点", "日期", "今天几号", "星期几",
            "内存使用", "磁盘空间", "cpu使用率", "系统信息", "hostname",
            "进程列表", "网络连接", "网速测试", "ip地址",
            "文件列表", "文件夹内容", "目录结构",
            "屏幕分辨率", "鼠标位置",
        ],
        3,
    ),
    (
        "multi_step",
        # 修复：移除"帮我"，它太宽泛会导致误触发
        ["先", "然后", "接着", "再", "最后", "之后", "并且", "同时",
         "完成以下", "执行以下", "多步", "第一步", "第二步",
         "接下来", "之后帮我",
        ],
        6,
    ),
    (
        "deep_thinking",
        ["深度思考", "自主搜索", "联网查询", "最新信息", "研究一下", "详细分析", "深入探讨", "最新动态", "最新消息", "现在怎么样", "最近趋势", "2026年", "2025年"],
        8,
    ),
    (
        "chat",
        ["你好", "嗨", "hello", "hi", "谢谢", "再见", "你是谁", "无聊", "好无聊", "聊天", "闲聊"],
        1,
    ),
    (
        "text_analyzer",
        ["分析文本", "文本分析", "拆解文本", "提取概要", "生成标题", "长文本", "文本总结", "analyze text", "text analysis", "summarize"],
        7,
    ),
]

# 多步任务指示词
_MULTI_STEP_INDICATORS = [
    "先", "然后", "接着", "再", "最后", "之后", "并且", "同时",
    "再帮我", "还有", "还要", "查完", "做完", "接下来",
]

# ─── 翻译目标语言映射 ────────────────────────────────────────────────────────
_LANG_MAP = {
    "英文": "en", "英语": "en", "english": "en",
    "中文": "zh", "汉语": "zh", "chinese": "zh",
    "日文": "ja", "日语": "ja", "japanese": "ja",
    "韩文": "ko", "韩语": "ko", "korean": "ko",
    "法文": "fr", "法语": "fr", "french": "fr",
    "德文": "de", "德语": "de", "german": "de",
    "西班牙文": "es", "西班牙语": "es",
}

# P1修复2：意图到技能的明确映射表（用于快速路由和调试）
_INTENT_SKILL_MAP = {
    # 数学计算 → chat（由LLM处理）
    "math_calculation": {"keywords": ["加", "减", "乘", "除", "等于", "计算", "+", "-", "*", "/"], "skill": "chat"},

    # 闲聊问候 → chat
    "greeting": {"keywords": ["你好", "嗨", "hello", "hi", "在吗"], "skill": "chat"},

    # 天气查询 → weather（优化：降低阈值，让单个关键词也能触发）
    "weather_query": {
        "keywords": ["天气", "气温", "温度", "下雨", "下雪", "刮风", "预报", "天气怎么样", "天气如何",
                     "多少度", "几度", "会不会下雨", "热不热", "冷不冷"],
        "skill": "weather",
        "min_hits": 1  # 天气关键词强，单个即可触发
    },

    # 网页爬取 → web_scraper
    "web_scraping": {
        "keywords": ["热搜", "热榜", "爬取", "抓取", "微博", "抖音", "知乎", "b站", "github",
                     "热点", "排行榜", "爬虫"],
        "skill": "web_scraper",
        "min_hits": 1
    },

    # 系统信息 → system_toolbox
    "system_info": {"keywords": ["系统时间", "内存", "磁盘", "cpu", "进程", "网络", "现在几点", "今天几号"], "skill": "system_toolbox"},

    # 翻译 → translator
    "translation": {
        "keywords": ["翻译", "translate", "中英互译", "翻译成", "翻一下", "翻译这段"],
        "skill": "translator",
        "min_hits": 1
    },

    # GUI自动化 → gui_automation（优化：扩大关键词范围）
    "gui_control": {
        "keywords": ["打开", "点击", "截图", "截屏", "音量", "亮度", "微信", "浏览器", "关闭",
                     "截个图", "截个屏", "飞书", "钉钉", "邮件", "日历"],
        "skill": "gui_automation",
        "min_hits": 1
    },

    # 数据分析 → data_analysis（新增）
    "data_analysis": {
        "keywords": ["数据分析", "分析一下", "统计", "可视化", "图表", "做个分析", "做个图表",
                     "画个图", "柱状图", "饼图", "折线图", "词云"],
        "skill": "data_analysis",
        "min_hits": 1
    },

    # RAG搜索 → rag_search
    "knowledge_search": {
        "keywords": ["是什么", "如何", "为什么", "了解一下", "概念", "原理", "解释", "定义"],
        "skill": "rag_search",
        "min_hits": 1
    },

    # 深度思考 → deep_thinking
    "deep_analysis": {"keywords": ["深度思考", "自主搜索", "最新信息", "分析一下", "研究一下", "最新动态"], "skill": "deep_thinking"},

    # 多步任务 → multi_step（优化：只有明确的多步指示词才触发）
    "multi_step_task": {
        "keywords": ["先", "然后", "接着", "再", "最后", "下一步", "接下来", "第一步", "第二步"],
        "skill": "multi_step",
        "min_hits": 2  # 提高阈值，必须有明确的多步指示词
    },

    # 文本分析 → text_analyzer
    "text_analysis": {"keywords": ["分析文本", "拆解", "提取概要", "生成标题", "文本分析", "长文本", "主要观点", "段落"], "skill": "text_analyzer"},
}


class SkillDispatcher:
    """基于关键词权重 + 优先级的意图识别和技能路由"""

    def __init__(self):
        self.skill_configs: List[tuple] = list(SKILL_CONFIGS)
        self._dynamic_registry: Dict[str, Dict[str, Any]] = {}

    # ── 动态注册 ─────────────────────────────────────────────────────────────
    def register_tool(self, name: str, keywords: List[str] = None,
                      priority: int = 3, description: str = ""):
        """动态注册新技能（运行时添加）"""
        self._dynamic_registry[name] = {
            "keywords": keywords or [],
            "priority": priority,
            "description": description,
        }
        logger.info("动态注册技能: %s (priority=%d)", name, priority)

    # ── 意图匹配 ─────────────────────────────────────────────────────────────
    def match_skill(self, message: str) -> str:
        """基于关键词权重匹配，返回最佳技能名 - 优化版

        score = 命中关键词数 × 优先级

        优化：
        1. @skill名格式最高优先级
        2. 多步任务检测优先（防止关键词权重覆盖）
        3. 否定处理
        4. 意图映射表快速路径
        """
        message_lower = message.lower()

        # 优化1：先检查@skill名格式（最高优先级）
        import re
        at_skill_match = re.match(r'@(\w+)\s', message_lower)
        if at_skill_match:
            skill_name = at_skill_match.group(1)
            skill_names = [c[0] for c in self.skill_configs] + list(self._dynamic_registry.keys())
            if skill_name in skill_names:
                logger.debug("技能匹配: '%s' -> %s (at格式)", message[:40], skill_name)
                return skill_name

        # 优化2：多步任务检测（优先于意图映射表，防止关键词权重覆盖）
        if self.is_multi_step(message):
            logger.debug("检测到多步任务指示词，优先选择multi_step技能")
            return "multi_step"

        # 优化3：否定处理
        has_neg, intent_after_neg = self.has_negation(message)
        if has_neg and intent_after_neg:
            matched_skill = self.match_skill(intent_after_neg)
            if matched_skill != "chat":
                logger.debug(f"否定处理：从'{message}'提取意图'{intent_after_neg}' -> {matched_skill}")
                return matched_skill

        # 优化4：意图映射表快速路径（支持min_hits）
        for intent_name, config in _INTENT_SKILL_MAP.items():
            keywords = config["keywords"]
            skill = config["skill"]
            min_hits = config.get("min_hits", 2)  # 默认需要2个关键词

            hits = sum(1 for kw in keywords if kw.lower() in message_lower)
            if hits >= min_hits:
                logger.debug(f"意图映射快速路由: {intent_name} -> {skill} (hits={hits}, min={min_hits})")
                return skill

        best_match = "chat"
        best_score = 0
        best_is_third_party = False

        # 检查动态注册的第三方应用技能
        # 关键修复：只有明确提到应用名称时才调用第三方应用
        # 优化：先收集所有第三方应用的名称，避免每次都遍历
        third_party_apps = {
            name: config for name, config in self._dynamic_registry.items()
            if name.startswith("third_party_")
        }
        
        # 如果没有第三方应用，跳过这段逻辑
        if not third_party_apps:
            pass  # 继续静态配置检查
        else:
            # 构建快速查找的应用名称集合
            app_names_in_message = set()
            chinese_names_map = {
                'twitter': ['推特'],
                'wechat': ['微信'],
                'dingtalk': ['钉钉'],
                'feishu': ['飞书'],
                'weibo': ['微博'],
                'zhihu': ['知乎'],
                'douyin': ['抖音'],
                'github': ['github', 'git'],
                'discord': ['discord'],
                'jira': ['jira'],
            }
            
            # 检查消息中是否包含任何第三方应用名称
            for app_name in third_party_apps.keys():
                app_key = app_name.replace("third_party_", "")
                if app_key.lower() in message_lower:
                    app_names_in_message.add(app_name)
                # 检查中文名称
                for cn_names in chinese_names_map.get(app_key, []):
                    if cn_names in message_lower:
                        app_names_in_message.add(app_name)
            
            # 只有消息中包含第三方应用名称时才遍历
            for name, config in third_party_apps.items():
                if name not in app_names_in_message:
                    continue
                    
                app_name = name.replace("third_party_", "")
                
                # 严格模式：必须明确提到应用名称（英文或中文）
                has_app_name_en = app_name.lower() in message_lower
                
                # 检查是否有对应的中文名称
                has_app_name_cn = any(cn in message_lower for cn in chinese_names_map.get(app_name, []))
                
                # 只有明确提到应用名称才考虑
                if has_app_name_en or has_app_name_cn:
                    hits = sum(1 for kw in config["keywords"] if kw.lower() in message_lower)
                    score = hits * config.get("priority", 3)
                    
                    # 额外加分：如果同时命中多个相关关键词
                    if hits >= 2:
                        score *= 1.5  # 提高分数
                    
                    # 第三方应用技能优先级更高
                    if score > best_score or (score == best_score and not best_is_third_party):
                        best_score = score
                        best_match = name
                        best_is_third_party = True

        # 静态配置
        for name, keywords, priority in self.skill_configs:
            hits = sum(1 for kw in keywords if kw.lower() in message_lower)
            score = hits * priority
            if score > best_score:
                best_score = score
                best_match = name
                best_is_third_party = False

        # 其他动态注册的技能
        for name, config in self._dynamic_registry.items():
            if not name.startswith("third_party_") and name not in [c[0] for c in self.skill_configs]:
                hits = sum(1 for kw in config["keywords"] if kw.lower() in message_lower)
                score = hits * config.get("priority", 3)
                if score > best_score:
                    best_score = score
                    best_match = name
                    best_is_third_party = False

        # 最终保护：如果最佳匹配是第三方应用但没有明确意图，回退到chat
        if best_is_third_party and best_score < 6:  # 阈值设为6（2个关键词×优先级3）
            logger.debug("第三方应用匹配分数过低 (%d)，回退到chat", best_score)
            best_match = "chat"
            best_is_third_party = False

        # **新增**: 精确匹配优化 - 如果输入已经是技能名称,直接返回
        all_skills = [c[0] for c in self.skill_configs] + list(self._dynamic_registry.keys())
        if message_lower in [s.lower() for s in all_skills]:
            # 找到精确匹配的技能名(忽略大小写)
            for skill_name in all_skills:
                if skill_name.lower() == message_lower:
                    logger.debug("精确匹配技能: '%s' -> %s", message, skill_name)
                    return skill_name

        logger.debug("技能匹配: '%s' -> %s (score=%d, is_third_party=%s)", message[:40], best_match, best_score, best_is_third_party)
        return best_match

    # ── 多步检测 ─────────────────────────────────────────────────────────────
    def is_multi_step(self, message: str) -> bool:
        """检测多步任务指示词（优化版）

        规则：
        1. 检测明确的序列模式：先...然后、先...再、先...接着
        2. 检测"X之后Y"模式
        3. 检测"接着"、"然后"等单一步骤指示词 + 技能关键词
        """
        message_lower = message.lower()

        # 明确的序列模式（最高优先级）
        multi_step_patterns = [
            "先", "然后", "接着", "再", "最后",
        ]

        # 检查是否包含序列模式
        pattern_count = sum(1 for p in multi_step_patterns if p in message_lower)

        # 如果有2个及以上序列词，或者有明确的"先...然后"等模式
        if pattern_count >= 2:
            return True

        # 检查明确的序列模式
        explicit_patterns = [
            ("先", "然后"), ("先", "接着"), ("先", "再"),
            ("然后", "接着"), ("之后", "再"), ("接着", "再"),
        ]
        for p1, p2 in explicit_patterns:
            if p1 in message_lower and p2 in message_lower:
                return True

        # 检查"X之后Y"模式
        if "之后" in message_lower or "做完" in message_lower or "查完" in message_lower:
            skill_keywords = ["爬", "抓", "翻译", "分析", "生成", "查", "看"]
            if any(kw in message_lower for kw in skill_keywords):
                return True

        # 修复：单一步骤指示词（接着/然后）+ 技能关键词 也算多步
        if "接着" in message_lower or "然后" in message_lower or "再" in message_lower:
            skill_keywords = ["爬", "抓", "翻译", "分析", "生成", "查", "看", "生成报告"]
            if any(kw in message_lower for kw in skill_keywords):
                return True

        return False

    # ── 多Agent模式检测 ────────────────────────────────────────────────────────
    def is_multi_agent_required(self, message: str) -> bool:
        """检测是否需要使用多Agent模式（深度思考场景）
        
        触发条件：
        1. 明确提到"深度思考"、"自主搜索"等
        2. 需要多步协作的复杂任务
        3. 需要多个技能配合完成的任务
        """
        message_lower = message.lower()
        
        # 明确的深度思考触发词
        deep_thinking_triggers = [
            "深度思考", "自主搜索", "联网查询", "最新信息", 
            "研究一下", "详细分析", "深入探讨", "最新动态",
            "综合分析", "全面评估", "系统分析", "多维度分析"
        ]
        
        # 检查是否有深度思考触发词
        if any(trigger in message_lower for trigger in deep_thinking_triggers):
            logger.debug("检测到深度思考触发词，需要多Agent模式")
            return True
        
        # 检查是否需要多技能协作
        skill_keywords = [
            ("爬取", "分析"), ("抓取", "分析"), ("搜索", "分析"),
            ("收集", "整理"), ("获取", "分析"), ("下载", "分析"),
            ("分析", "生成"), ("整理", "生成"), ("收集", "生成")
        ]
        
        for kw1, kw2 in skill_keywords:
            if kw1 in message_lower and kw2 in message_lower:
                logger.debug(f"检测到多技能协作需求: {kw1} + {kw2}")
                return True
        
        # 检查是否有明确的多步复杂任务指示
        complex_task_patterns = [
            "帮我完成", "帮我做", "帮我研究", "帮我分析",
            "制定方案", "提供建议", "给出方案", "综合评估"
        ]
        
        if any(pattern in message_lower for pattern in complex_task_patterns):
            # 需要配合其他关键词
            additional_keywords = ["报告", "分析", "研究", "方案", "建议", "总结"]
            if any(kw in message_lower for kw in additional_keywords):
                logger.debug("检测到复杂任务需求，需要多Agent模式")
                return True
        
        return False

    # ── 否定检测 ─────────────────────────────────────────────────────────────
    def has_negation(self, message: str) -> tuple:
        """检测否定词，返回(是否有否定, 否定后的意图)

        规则：
        1. 检测"不要"、"别"、"不是"等否定词
        2. 返回否定词后面的内容作为真实意图
        """
        import re

        # 否定词模式（按优先级排序）
        negation_patterns = [
            (r"不要(.+?)，我要(.+)", 2),  # 不要X，我要Y -> 取Y
            (r"别(.+?)，帮我(.+)", 2),     # 别X，帮我Y -> 取Y
            (r"不是(.+?)，是(.+)", 2),     # 不是X，是Y -> 取Y
            (r"不要(.+)", 1),              # 不要X -> 取X
            (r"别(.+)", 1),               # 别X -> 取X
        ]

        for pattern, group_idx in negation_patterns:
            match = re.search(pattern, message)
            if match:
                groups = match.groups()
                if len(groups) >= group_idx:
                    intent = groups[group_idx - 1]
                    if intent and intent.strip():
                        return True, intent.strip()

        return False, None
    
    # P1修复4：添加调试方法，查看技能匹配详情
    def debug_match(self, message: str) -> Dict[str, Any]:
        """调试技能匹配过程，返回详细的匹配信息
        
        Returns:
            {
                "message": 原始消息,
                "matched_skill": 最终匹配的技能,
                "intent_map_hits": 意图映射表的命中情况,
                "keyword_scores": 各技能的关键词得分,
                "third_party_check": 第三方应用检查结果
            }
        """
        message_lower = message.lower()
        result = {
            "message": message,
            "matched_skill": None,
            "intent_map_hits": [],
            "keyword_scores": {},
            "third_party_check": {}
        }
        
        # 检查意图映射表
        for intent_name, config in _INTENT_SKILL_MAP.items():
            keywords = config["keywords"]
            skill = config["skill"]
            hits = [kw for kw in keywords if kw.lower() in message_lower]
            
            if hits:
                result["intent_map_hits"].append({
                    "intent": intent_name,
                    "skill": skill,
                    "hit_keywords": hits,
                    "hit_count": len(hits),
                    "would_route": len(hits) >= 2
                })
        
        # 检查静态配置的关键词得分
        for name, keywords, priority in self.skill_configs:
            hits = sum(1 for kw in keywords if kw.lower() in message_lower)
            score = hits * priority
            if hits > 0:
                result["keyword_scores"][name] = {
                    "hits": hits,
                    "priority": priority,
                    "score": score
                }
        
        # 执行完整匹配
        final_skill = self.match_skill(message)
        result["matched_skill"] = final_skill
        
        return result

    # ── 参数提取 ─────────────────────────────────────────────────────────────
    def extract_params(self, message: str, skill_name: str) -> Dict[str, Any]:
        """正则提取各技能参数"""
        params: Dict[str, Any] = {}

        # 去除@skill前缀
        import re
        clean_message = re.sub(r'@\w+\s', '', message)

        if skill_name == "weather":
            self._extract_weather_params(clean_message, params)

        elif skill_name == "web_scraper":
            self._extract_scraper_params(clean_message, params)

        elif skill_name == "translator":
            self._extract_translator_params(clean_message, params)

        elif skill_name == "system_toolbox":
            self._extract_system_params(clean_message, params)

        elif skill_name == "gui_automation":
            self._extract_gui_params(clean_message, params)

        elif skill_name.startswith("third_party_"):
            app_name = skill_name.replace("third_party_", "")
            self._extract_third_party_params(app_name, clean_message, params)

        return params

    # ── third_party 参数 ─────────────────────────────────────────────────────
    def _extract_third_party_params(self, app_name: str, message: str, params: Dict):
        """提取第三方应用参数"""
        if app_name == "github":
            # 提取GitHub相关参数
            import re
            if "repo" in message or "repository" in message:
                # 提取所有者和仓库名
                match = re.search(r"(?:repo|repository)[\s:]*([\w-]+)/([\w-]+)", message)
                if match:
                    params["owner"] = match.group(1)
                    params["repo"] = match.group(2)
                params["action"] = "get_repo"
            elif "list" in message or "repos" in message:
                # 提取用户名
                match = re.search(r"(?:list|repos)[\s:]*([\w-]+)", message)
                if match:
                    params["username"] = match.group(1)
                params["action"] = "list_repos"
            elif "user" in message:
                # 提取用户名
                match = re.search(r"(?:user|profile)[\s:]*([\w-]+)", message)
                if match:
                    params["username"] = match.group(1)
                params["action"] = "get_user"
            elif "search" in message:
                # 提取搜索关键词
                match = re.search(r"(?:search)[\s:]*(.+)", message)
                if match:
                    params["query"] = match.group(1).strip()
                params["action"] = "search_repos"
        elif app_name == "slack":
            # 提取Slack相关参数
            import re
            if "send" in message and "message" in message:
                # 提取频道和消息内容
                match = re.search(r"(?:send|message)[\s:]*to[\s:]*([#@\w-]+)[\s:]*[:：](.+)", message)
                if match:
                    params["channel"] = match.group(1)
                    params["message"] = match.group(2).strip()
                params["action"] = "send_message"
        elif app_name == "trello":
            # 提取Trello相关参数
            import re
            if "create" in message and "card" in message:
                # 提取看板和卡片信息
                match = re.search(r"(?:create|add)[\s:]*card[\s:]*(.+)[\s:]*to[\s:]*(.+)", message)
                if match:
                    params["card_name"] = match.group(1).strip()
                    params["board_name"] = match.group(2).strip()
                params["action"] = "create_card"

    # ── weather 参数 ─────────────────────────────────────────────────────────
    @staticmethod
    def _extract_weather_params(message: str, params: Dict):
        city_patterns = [
            r"([\u4e00-\u9fa5]{2,10})(?:天气|气温|温度)",
            r"(?:查|看|问)(?:一)?下([\u4e00-\u9fa5]{2,10})",
            r"([\u4e00-\u9fa5]{2,5})(?:的)?(?:天气|气温)",
        ]
        for pattern in city_patterns:
            match = re.search(pattern, message)
            if match:
                params["city"] = match.group(1)
                break

    # ── web_scraper 参数 ─────────────────────────────────────────────────────
    @staticmethod
    def _extract_scraper_params(message: str, params: Dict):
        message_lower = message.lower()
        
        # 智能识别站点
        site_keywords = {
            "微博": ["微博", "weibo"],
            "百度": ["百度", "baidu"],
            "B站": ["b站", "bilibili", "哔哩哔哩"],
            "抖音": ["抖音", "douyin"],
            "知乎": ["知乎", "zhihu"],
            "今日头条": ["今日头条", "头条", "toutiao"],
            "GitHub": ["github", "git", "hub", "trending"],
        }
        
        site_name = params.get("site_name")
        if not site_name:
            for site, keywords in site_keywords.items():
                if any(kw in message_lower for kw in keywords):
                    params["site_name"] = site
                    break

        # 智能识别操作类型
        action_keywords = {
            "热搜top10": ["热搜", "热榜", "热门", "top10", "排行", "趋势"],
            "搜索": ["搜索", "查找", "搜一下"],
            "热门": ["热门视频", "热门话题"],
        }
        
        action = params.get("action")
        if not action:
            for action_type, keywords in action_keywords.items():
                if any(kw in message_lower for kw in keywords):
                    params["action"] = action_type
                    break
        
        # 提取搜索关键词
        if "搜索" in message or "搜" in message:
            keyword_patterns = [
                r"搜索\s*(.+?)(?:视频|内容|$)",
                r"搜\s*(.+?)(?:视频|内容|$)",
                r"查找\s*(.+?)(?:视频|内容|$)",
            ]
            for pattern in keyword_patterns:
                match = re.search(pattern, message)
                if match:
                    params["keyword"] = match.group(1).strip()
                    break
        
        # 提取返回数量
        top_n_match = re.search(r"(?:top|前)(\d+)", message_lower)
        if top_n_match:
            params["top_n"] = int(top_n_match.group(1))
        elif "热搜" in message and "top" not in message_lower:
            params["top_n"] = 10  # 默认返回10条

    # ── translator 参数 ──────────────────────────────────────────────────────
    @staticmethod
    def _extract_translator_params(message: str, params: Dict):
        # 提取翻译文本（引号内 or 去掉"翻译"关键字）
        text_match = re.search(r"['\"'\"`](.+?)['\"'\"`]", message)
        if text_match:
            params["text"] = text_match.group(1)
        else:
            params["text"] = re.sub(r"(翻译|translate|把|帮我|成|给).{0,4}", "", message).strip()

        # 提取目标语言
        for lang_name, lang_code in _LANG_MAP.items():
            if lang_name in message:
                params["target_lang"] = lang_code
                break
        
        # 设置默认目标语言为中文
        if "target_lang" not in params:
            params["target_lang"] = "zh"

    # ── system_toolbox 参数 ──────────────────────────────────────────────────
    @staticmethod
    def _extract_system_params(message: str, params: Dict):
        action_map = {
            "时间": ["时间", "几点", "时刻", "time"],
            "日期": ["日期", "今天", "星期", "周几", "date"],
            "内存": ["内存", "memory", "ram"],
            "磁盘": ["磁盘", "硬盘", "disk", "storage"],
            "计算": ["计算", "等于", "加", "减", "乘", "除", "calc"],
            "cpu": ["cpu", "处理器", "processor"],
            "系统信息": ["系统信息", "hostname", "主机名", "架构", "architecture"],
            "屏幕尺寸": ["屏幕尺寸", "分辨率", "resolution"],
            "鼠标位置": ["鼠标位置", "mouse", "光标"],
            "文件列表": ["文件", "file", "文件夹", "directory", "文件夹列表", "ls"],
            "进程列表": ["进程", "process", "进程列表", "ps"],
            "网络": ["网络", "network"],
            "网速": ["网速", "network speed"],
            "ip": ["ip", "公网ip", "外网ip"],
        }
        for action, keywords in action_map.items():
            if any(kw in message for kw in keywords):
                params["action"] = action
                break

    # ── gui_automation 参数 ──────────────────────────────────────────────────
    @staticmethod
    def _extract_gui_params(message: str, params: Dict):
        message_lower = message.lower()
        
        # 智能识别：优先检查明确的功能关键词
        # 音量控制（优先级最高，因为有明确的"音量"关键词）
        if "音量" in message or "volume" in message_lower:
            params["action"] = "volume_adjust"
            import re
            
            # 判断是相对调节还是绝对设置
            increase_keywords = ["提高", "增加", "调高", "加大", "up", "increase", " louder"]
            decrease_keywords = ["降低", "减少", "调低", "减小", "down", "decrease", "quieter"]
            
            if any(kw in message for kw in increase_keywords):
                params["action_type"] = "increase"
                # 提取增量，默认10%
                match = re.search(r'(\d+)[%\s]*', message)
                params["level"] = int(match.group(1)) if match else 10
            elif any(kw in message for kw in decrease_keywords):
                params["action_type"] = "decrease"
                match = re.search(r'(\d+)[%\s]*', message)
                params["level"] = int(match.group(1)) if match else 10
            else:
                # 绝对设置
                params["action_type"] = "set"
                match = re.search(r'(\d+)%', message)
                if match:
                    params["level"] = int(match.group(1))
                else:
                    params["level"] = 50  # 默认50%
            return

        # 亮度控制（优先级高，因为有明确的"亮度"关键词）
        if "亮度" in message or "brightness" in message_lower:
            params["action"] = "brightness_adjust"
            import re
            
            # 判断是相对调节还是绝对设置
            increase_keywords = ["提高", "增加", "调高", "加大", "up", "increase", "brighter"]
            decrease_keywords = ["降低", "减少", "调低", "减小", "down", "decrease", "darker"]
            
            if any(kw in message for kw in increase_keywords):
                params["action_type"] = "increase"
                match = re.search(r'(\d+)[%\s]*', message)
                params["level"] = int(match.group(1)) if match else 10
            elif any(kw in message for kw in decrease_keywords):
                params["action_type"] = "decrease"
                match = re.search(r'(\d+)[%\s]*', message)
                params["level"] = int(match.group(1)) if match else 10
            else:
                # 绝对设置
                params["action_type"] = "set"
                match = re.search(r'(\d+)%', message)
                if match:
                    params["level"] = int(match.group(1))
                else:
                    params["level"] = 70  # 默认70%
            return

        # 浏览器缩放（只有在明确提到缩放相关词汇时才识别）
        zoom_keywords = ["缩放", "放大", "缩小", "zoom", "scale", "页面缩放",
                        "实际大小", "适合页面", "适合页宽"]
        if any(kw in message for kw in zoom_keywords):
            params["action"] = "browser_zoom"
            
            # 提取缩放级别
            zoom_map = {
                "50%": "50%", "75%": "75%", "100%": "100%", "125%": "125%",
                "150%": "150%", "200%": "200%", "300%": "300%", "400%": "400%",
                "实际大小": "实际大小", "适合页面": "适合页面", "适合页宽": "适合页宽",
                "放大": "放大", "缩小": "缩小"
            }
            for zoom_name, zoom_value in zoom_map.items():
                if zoom_name in message:
                    params["zoom"] = zoom_value
                    break
            
            # 提取浏览器应用
            if "safari" in message_lower:
                params["app"] = "Safari"
            elif "chrome" in message_lower:
                params["app"] = "Chrome"
            return

        # 应用控制
        app_map = {
            "微信": ["微信", "wechat", "weixin"],
            "QQ": ["qq", "QQ"],
            "邮件": ["邮件", "mail", "email"],
            "日历": ["日历", "calendar"],
            "浏览器": ["浏览器", "browser", "chrome", "safari"],
            "Safari": ["safari"],
        }
        for app, keywords in app_map.items():
            if any(kw in message for kw in keywords):
                params["action"] = "open_app"
                params["app"] = app
                break

        # 通知
        if "通知" in message or "notification" in message_lower:
            params["action"] = "notification"

        # 截图
        if "截图" in message or "截屏" in message or "screenshot" in message_lower:
            params["action"] = "screenshot"

        # OCR识别
        if "ocr" in message_lower or "识别文字" in message:
            params["action"] = "ocr_screenshot"

        # 关闭/退出应用
        if "关闭" in message or "退出" in message or "quit" in message_lower:
            params["action"] = "quit_app"


# 全局单例实例
_skill_dispatcher_instance: Optional[SkillDispatcher] = None


def get_skill_dispatcher() -> SkillDispatcher:
    """获取技能分发器单例实例
    
    Returns:
        SkillDispatcher: 技能分发器实例
    """
    global _skill_dispatcher_instance
    if _skill_dispatcher_instance is None:
        _skill_dispatcher_instance = SkillDispatcher()
    return _skill_dispatcher_instance

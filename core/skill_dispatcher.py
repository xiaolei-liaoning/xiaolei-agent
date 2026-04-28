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
        ["天气", "气温", "温度", "下雨", "下雪", "刮风", "weather", "天气预报"],
        5,
    ),
    (
        "web_scraper",
        [
            "爬取", "抓取", "热搜", "热榜", "微博热搜", "百度热搜",
            "b站", "bilibili", "抖音", "douyin", "爬虫", "scrape", "crawl",
            "知乎", "今日头条", "头条", "toutiao", "zhihu",
            "github", "git", "trending", "趋势", "仓库",
        ],
        5,
    ),
    (
        "data_analysis",
        [
            "分析", "统计", "可视化", "图表", "趋势", "词云",
            "饼图", "柱状图", "analyze", "chart", "数据",
            "预测", "机器学习", "ml", "predict", "forecast", "时间序列",
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
        ],
        4,
    ),
    (
        "translator",
        [
            "翻译", "translate", "中英", "英文", "日文", "韩文", "互译",
            "批量翻译", "batch", "翻译历史", "history", "翻译记录",
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
        ["搜索", "查询", "了解", "是什么", "什么是", "如何", "怎么", "为什么", "search", "lookup", "learn"],
        3,
    ),
    (
        "doubao_chat",
        ["豆包", "doubao", "对话"],
        2,
    ),
    (
        "system_toolbox",
        [
            "系统", "时间", "日期", "计算", "内存", "磁盘", "system", "sys",
            "进程", "process", "网络", "network", "网速", "ip", "cpu",
            "文件", "file", "文件夹", "directory", "文件夹列表",
            "系统信息", "hostname", "主机名", "处理器", "架构",
            "屏幕尺寸", "分辨率", "鼠标位置", "mouse",
        ],
        3,
    ),
    (
        "multi_step",
        ["先", "然后", "接着", "再", "最后", "之后", "并", "和", "同时", "帮我", "完成以下", "执行", "多步"],
        6,
    ),
    (
        "deep_thinking",
        ["深度思考", "自主搜索", "联网查询", "最新信息", "分析一下", "研究一下", "了解一下", "详细分析", "深入探讨", "最新动态", "最新消息", "现在怎么样", "今天", "最近", "2026", "2025"],
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
    "再帮我", "还有", "还要", "查完", "做完",
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
        """基于关键词权重匹配，返回最佳技能名

        score = 命中关键词数 × 优先级
        
        修复：只有当用户明确提到第三方应用名称时才调用，避免误触发
        """
        message_lower = message.lower()
        best_match = "chat"
        best_score = 0
        best_is_third_party = False

        # 检查@skill名格式
        import re
        at_skill_match = re.match(r'@(\w+)\s', message_lower)
        if at_skill_match:
            skill_name = at_skill_match.group(1)
            # 检查技能是否存在
            skill_names = [c[0] for c in self.skill_configs] + list(self._dynamic_registry.keys())
            if skill_name in skill_names:
                logger.debug("技能匹配: '%s' -> %s (at格式)", message[:40], skill_name)
                return skill_name

        # 检查动态注册的第三方应用技能
        # 关键修复：只有明确提到应用名称时才调用第三方应用
        for name, config in self._dynamic_registry.items():
            if name.startswith("third_party_"):
                app_name = name.replace("third_party_", "")
                
                # 严格模式：必须明确提到应用名称（英文或中文）
                has_app_name_en = app_name.lower() in message_lower
                
                # 检查是否有对应的中文名称
                chinese_names = {
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
                
                has_app_name_cn = any(cn in message_lower for cn in chinese_names.get(app_name, []))
                
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

        logger.debug("技能匹配: '%s' -> %s (score=%d, is_third_party=%s)", message[:40], best_match, best_score, best_is_third_party)
        return best_match

    # ── 多步检测 ─────────────────────────────────────────────────────────────
    def is_multi_step(self, message: str) -> bool:
        """检测多步任务指示词"""
        return any(ind in message for ind in _MULTI_STEP_INDICATORS)

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
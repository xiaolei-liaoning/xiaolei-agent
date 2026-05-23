"""关键词提取器 - 门面模式

将实际的提取算法委托给 `keyword_extractors/` 下的策略模块。
提供与之前完全相同的公开 API。

用法:
    from core.search.keyword_extractor import get_keyword_extractor
    extractor = get_keyword_extractor()
    result = await extractor.extract("用户输入文本")
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import Counter

from .keyword_extractors import (
    KeywordInfo,
    ExtractedEntities,
    ExtractionResult,
    EntityExtractor as _EntityExtractor,
    TfidfExtractor as _TfidfExtractor,
    TextrankExtractor as _TextrankExtractor,
    Bm25Extractor as _Bm25Extractor,
    CombinedExtractor as _CombinedExtractor,
    LlmExtractor as _LlmExtractor,
)
from .keyword_extractors.base import (
    normalize_keyword,
    categorize_word,
    post_process_keywords,
    diversify_keywords,
    detect_domain,
    adjust_extraction_strategy,
)

logger = logging.getLogger(__name__)

# =========================================================================
# 重新导出数据类，确保
#   from .keyword_extractor import KeywordInfo
#   from .keyword_extractor import ExtractedEntities
#   from .keyword_extractor import ExtractionResult
# 仍然可用
# =========================================================================
KeywordInfo = KeywordInfo
ExtractedEntities = ExtractedEntities
ExtractionResult = ExtractionResult

__all__ = [
    "KeywordInfo",
    "ExtractedEntities",
    "ExtractionResult",
    "KeywordExtractor",
    "get_keyword_extractor",
]


class KeywordExtractor:
    """关键词提取器（门面）

    对外保持与之前完全相同的接口；内部将具体算法委托给
    `keyword_extractors/` 下的策略类。
    """

    def __init__(self):
        self.router = None  # 延迟初始化，避免循环依赖

        # 策略实例（延迟创建）
        self._entity_extractor = _EntityExtractor()
        self._tfidf_extractor: Optional[_TfidfExtractor] = None
        self._textrank_extractor: Optional[_TextrankExtractor] = None
        self._bm25_extractor: Optional[_Bm25Extractor] = None
        self._combined_extractor: Optional[_CombinedExtractor] = None
        self._llm_extractor: Optional[_LlmExtractor] = None

        # 动作词库（支持中英文）
        self.action_words = {
            # 中文动作词
            "查询", "搜索", "查找", "获取", "爬取", "抓取", "下载", "上传",
            "发送", "接收", "创建", "删除", "修改", "更新", "编辑",
            "打开", "关闭", "启动", "停止", "运行", "执行",
            "分析", "统计", "计算", "对比", "比较", "评估",
            "翻译", "转换", "格式化", "整理", "归类", "排序",
            "播放", "暂停", "跳过", "收藏", "分享", "点赞",
            "阅读", "写作", "记录", "保存", "备份", "恢复",
            "提醒", "通知", "警告", "报警", "监控", "检测",
            # 英文动作词
            "search", "find", "get", "crawl", "scrape", "download", "upload",
            "send", "receive", "create", "delete", "modify", "update", "edit",
            "open", "close", "start", "stop", "run", "execute",
            "analyze", "statistics", "calculate", "compare", "evaluate",
            "translate", "convert", "format", "organize", "classify", "sort",
            "play", "pause", "skip", "collect", "share", "like",
            "read", "write", "record", "save", "backup", "restore",
            "remind", "notify", "warn", "alert", "monitor", "detect"
        }

        # 目标词库（支持中英文）
        self.target_words = {
            # 中文目标词
            "天气", "新闻", "热搜", "热榜", "股票", "基金", "汇率",
            "邮件", "微信", "短信", "电话", "文件", "图片", "视频",
            "音乐", "电影", "书籍", "文章", "报告", "数据",
            "日程", "任务", "待办", "笔记", "备忘录", "清单",
            "网站", "网页", "链接", "URL", "地址", "位置",
            "价格", "销量", "排名", "评分", "评论", "反馈",
            # 英文目标词
            "weather", "news", "hot search", "hot list", "stock", "fund", "exchange rate",
            "email", "wechat", "message", "phone", "file", "image", "video",
            "music", "movie", "book", "article", "report", "data",
            "schedule", "task", "todo", "note", "memo", "list",
            "website", "webpage", "link", "URL", "address", "location",
            "price", "sales", "ranking", "rating", "comment", "feedback"
        }

        # 停用词（增强版 - 400+常用停用词，支持中英文）
        self.stopwords: Set[str] = {
            # 中文停用词
            "的", "了", "在", "是", "我", "有", "和", "就",
            "不", "人", "都", "一", "一个", "上", "也", "很",
            "到", "说", "要", "去", "你", "会", "着", "没有",
            "看", "好", "自己", "这", "他", "她", "它", "们",
            "那", "些", "什么", "怎么", "如何", "为什么",
            "可以", "能够", "需要", "想要", "希望", "请",
            "帮", "帮忙", "帮我", "给我", "为我",
            # 代词
            "这个", "那个", "这些", "那些", "这里", "那里",
            "哪里", "谁", "哪儿", "哪", "某", "各", "每",
            "其", "此", "彼", "之", "乎", "者", "也",
            # 连词和介词
            "与", "及", "或", "但", "而", "且", "因", "因为",
            "所以", "如果", "虽然", "但是", "然而", "因此",
            "从", "向", "对", "对于", "关于", "通过", "根据",
            "按照", "依照", "依据", "鉴于", "除了", "包括",
            # 助词
            "吗", "呢", "吧", "啊", "呀", "哦", "嘛", "啦",
            "呗", "咯", "哈", "嗯", "哎", "唉", "哇", "噢",
            "呐", "呦", "嘿", "呵", "嘻",
            # 副词
            "非常", "特别", "十分", "极其", "相当", "比较",
            "稍微", "略微", "大概", "也许", "可能", "应该",
            "已经", "曾经", "正在", "将要", "马上", "立刻",
            "渐渐", "逐渐", "慢慢", "快快", "常常", "经常",
            "偶尔", "有时", "总是", "一直", "从来", "从未",
            # 动词（通用）
            "做", "作", "让", "叫", "使", "用", "以", "被",
            "把", "将", "给", "对", "为", "同", "和", "跟",
            "来", "去", "回", "过", "起", "出", "进",
            # 数量词
            "一些", "很多", "许多", "大量", "少量", "几个",
            "第一", "第二", "第三", "最后", "首先", "其次",
            "然后", "接着", "再", "又", "还", "更", "最",
            # 时间词（通用）
            "现在", "当时", "那时", "今天", "明天", "昨天",
            "今年", "明年", "去年", "本月", "上月", "下月",
            "刚才", "刚刚", "之前", "之后", "以后",
            # 其他常见无意义词
            "东西", "事情", "问题", "情况", "方面", "部分",
            "内容", "信息", "资料", "数据", "结果", "方式",
            "方法", "手段", "途径", "过程", "步骤", "环节",
            # 语气词和感叹词
            "真的", "确实", "当然", "肯定", "一定", "必须",
            "绝对", "完全", "彻底", "根本", "简直", "实在",
            # 程度副词
            "太", "超", "极", "甚", "颇", "蛮", "挺",
            "稍", "略", "微", "有点", "有些", "些许",
            # 否定词
            "没", "未", "非", "莫", "勿", "别", "休",
            "毋", "弗", "无", "否",
            # 疑问词
            "何", "啥", "咋", "岂", "焉", "安", "孰",
            "胡", "曷", "奚", "恶", "乌",
            # 方位词
            "里", "外", "内", "中", "间", "旁", "边",
            "前", "后", "左", "右", "东", "西", "南", "北",
            # 量词
            "个", "只", "条", "张", "本", "件", "位",
            "次", "回", "趟", "遍", "番", "阵", "场",
            # 英文停用词
            "the", "a", "an", "and", "or", "but", "if", "because",
            "as", "what", "which", "this", "that", "these", "those",
            "then", "just", "so", "than", "such", "both", "through",
            "about", "for", "is", "of", "while", "during", "to", "from",
            "in", "on", "at", "by", "with", "around", "against", "between",
            "into", "through", "after", "before", "above", "below", "up",
            "down", "in", "out", "off", "over", "under", "again", "further",
            "then", "once", "here", "there", "when", "where", "why", "how",
            "all", "any", "both", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same",
            "so", "than", "too", "very", "s", "t", "can", "will",
            "don", "should", "now", "i", "me", "my", "myself", "we",
            "our", "ours", "ourselves", "you", "your", "yours", "yourself",
            "yourselves", "he", "him", "his", "himself", "she", "her",
            "hers", "herself", "it", "its", "itself", "they", "them",
            "their", "theirs", "themselves"
        }

        # 领域词典（可扩展 - 增强版，支持中英文）
        self.domain_dictionary: Dict[str, List[str]] = {
            "tech": ["人工智能", "机器学习", "深度学习", "神经网络", "大数据",
                    "云计算", "区块链", "物联网", "5G", "算法", "Python", "Java",
                    "前端", "后端", "数据库", "API", "微服务", "容器化", "Docker",
                    "Kubernetes", "DevOps", "敏捷开发", "版本控制", "Git",
                    "AI", "machine learning", "deep learning", "neural network", "big data",
                    "cloud computing", "blockchain", "IoT", "5G", "algorithm", "Python", "Java",
                    "frontend", "backend", "database", "API", "microservice", "containerization", "Docker",
                    "Kubernetes", "DevOps", "agile development", "version control", "Git"],
            "weather": ["天气", "气温", "降雨", "风力", "湿度", "空气质量", "PM2.5",
                       "紫外线", "能见度", "气压", "温度", "晴朗", "多云", "阴天",
                       "小雨", "中雨", "大雨", "暴雨", "雪", "雾", "霾", "雷阵雨",
                       "weather", "temperature", "rainfall", "wind force", "humidity", "air quality", "PM2.5",
                       "ultraviolet", "visibility", "air pressure", "temperature", "sunny", "cloudy", "overcast",
                       "light rain", "moderate rain", "heavy rain", "rainstorm", "snow", "fog", "haze", "thunderstorm"],
            "finance": ["股票", "基金", "汇率", "利率", "通胀", "股市", "债券",
                       "期货", "期权", "外汇", "黄金", "原油", "比特币", "数字货币",
                       "银行", "贷款", "信用卡", "理财", "投资", "收益", "风险",
                       "stock", "fund", "exchange rate", "interest rate", "inflation", "stock market", "bond",
                       "futures", "options", "forex", "gold", "crude oil", "bitcoin", "digital currency",
                       "bank", "loan", "credit card", "wealth management", "investment", "return", "risk"],
            "medical": ["健康", "疾病", "治疗", "药物", "医院", "医生", "症状",
                       "诊断", "手术", "康复", "预防", "疫苗", "体检", "营养",
                       "运动", "健身", "减肥", "养生", "中医", "西医",
                       "health", "disease", "treatment", "medicine", "hospital", "doctor", "symptom",
                       "diagnosis", "surgery", "rehabilitation", "prevention", "vaccine", "physical examination", "nutrition",
                       "exercise", "fitness", "weight loss", "health preservation", "traditional Chinese medicine", "Western medicine"],
            "entertainment": ["电影", "电视剧", "综艺", "音乐", "游戏", "动漫",
                             "明星", "演员", "歌手", "导演", "编剧", "票房", "评分",
                             "演唱会", "直播", "短视频", "B站", "抖音", "微博",
                             "movie", "TV series", "variety show", "music", "game", "anime",
                             "star", "actor", "singer", "director", "screenwriter", "box office", "rating",
                             "concert", "live stream", "short video", "Bilibili", "Douyin", "Weibo"],
            "education": ["学习", "考试", "课程", "教材", "培训", "教育", "学校",
                         "大学", "研究生", "博士", "硕士", "本科", "专科", "高中",
                         "初中", "小学", "幼儿园", "老师", "学生", "作业", "论文",
                         "learning", "exam", "course", "textbook", "training", "education", "school",
                         "university", "graduate student", "PhD", "master", "undergraduate", "junior college", "high school",
                         "middle school", "elementary school", "kindergarten", "teacher", "student", "homework", "thesis"],
            "travel": ["旅游", "旅行", "酒店", "机票", "火车", "高铁", "地铁",
                      "公交", "出租车", "自驾", "景点", "门票", "导游", "攻略",
                      "签证", "护照", "行李", "住宿", "餐饮", "美食", "购物",
                      "travel", "trip", "hotel", "flight ticket", "train", "high-speed rail", "subway",
                      "bus", "taxi", "self-driving", "scenic spot", "ticket", "tour guide", "travel guide",
                      "visa", "passport", "luggage", "accommodation", "dining", "food", "shopping"],
            "shopping": ["购物", "电商", "淘宝", "京东", "拼多多", "天猫", "亚马逊",
                        "价格", "折扣", "优惠", "促销", "包邮", "退货", "换货",
                        "评价", "销量", "品牌", "质量", "快递", "物流", "配送",
                        "shopping", "e-commerce", "Taobao", "JD", "Pinduoduo", "Tmall", "Amazon",
                        "price", "discount", "promotion", "sales", "free shipping", "return", "exchange",
                        "review", "sales volume", "brand", "quality", "express", "logistics", "delivery"]
        }

        logger.info("KeywordExtractor 初始化完成（优化版）")

    # ------------------------------------------------------------------ #
    # 策略实例懒加载
    # ------------------------------------------------------------------ #

    def _ensure_extractors(self):
        """确保所有策略提取器已初始化"""
        if self._tfidf_extractor is None:
            self._tfidf_extractor = _TfidfExtractor(
                stopwords=self.stopwords,
                action_words=self.action_words,
                target_words=self.target_words,
            )
        if self._textrank_extractor is None:
            self._textrank_extractor = _TextrankExtractor(
                stopwords=self.stopwords,
                action_words=self.action_words,
                target_words=self.target_words,
            )
        if self._bm25_extractor is None:
            self._bm25_extractor = _Bm25Extractor(
                stopwords=self.stopwords,
                action_words=self.action_words,
                target_words=self.target_words,
            )
        if self._combined_extractor is None:
            self._combined_extractor = _CombinedExtractor(
                stopwords=self.stopwords,
                action_words=self.action_words,
                target_words=self.target_words,
            )
        if self._llm_extractor is None:
            self._llm_extractor = _LlmExtractor(router=self.router)

    # ------------------------------------------------------------------ #
    # 公开 API
    # ------------------------------------------------------------------ #

    async def extract(self, text: str) -> ExtractionResult:
        """从长文本中提取关键词和实体

        Args:
            text: 用户输入的长文本

        Returns:
            提取结果
        """
        logger.info("开始提取关键词，文本长度: %d", len(text))

        # 1. 文本预处理
        cleaned_text = self._preprocess_text(text)

        # 2. 提取实体
        entities = self._entity_extractor.extract(cleaned_text)

        # 3. 提取关键词（多层级）
        keywords = await self._extract_keywords(cleaned_text)

        # 4. 分类关键词
        action_words, target_words = self._classify_keywords(keywords)

        # 5. 识别主要意图
        main_intent = self._identify_intent(action_words, target_words, entities)

        # 6. 生成摘要
        summary = self._generate_summary(cleaned_text, keywords)

        # 7. 计算置信度
        confidence = self._calculate_confidence(keywords, entities, main_intent)

        result = ExtractionResult(
            keywords=keywords,
            entities=entities,
            main_intent=main_intent,
            action_words=action_words,
            target_words=target_words,
            summary=summary,
            confidence=confidence,
        )

        logger.info("关键词提取完成，提取到 %d 个关键词，置信度: %.2f",
                    len(keywords), confidence)

        return result

    # ------------------------------------------------------------------ #
    # 内部方法（原有逻辑保持不变）
    # ------------------------------------------------------------------ #

    def _preprocess_text(self, text: str) -> str:
        """文本预处理"""
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 去除特殊字符（保留中文、英文、数字、常见标点）
        text = re.sub(r'[^\w\s一-鿿.,;:!?()""\'\-\']', '', text)
        # 标准化标点
        text = text.replace('，', ',').replace('。', '.').replace('！', '!')
        text = text.replace('？', '?').replace('；', ';').replace('：', ':')
        return text.strip()

    async def _extract_keywords(self, text: str) -> List[KeywordInfo]:
        """提取关键词（多层级方法 - 优化版）

        委托给各个策略提取器，然后融合结果。
        """
        self._ensure_extractors()

        try:
            # 检测文本所属领域
            domain = detect_domain(text, self.domain_dictionary)
            logger.info(f"检测到文本领域: {domain}")

            # 根据领域调整提取策略
            strategy = adjust_extraction_strategy(domain)

            # 方法1: TF-IDF
            tfidf_keywords = self._tfidf_extractor.extract(text)

            # 方法2: TextRank
            try:
                textrank_keywords = self._textrank_extractor.extract(text)
            except Exception as e:
                logger.warning("TextRank提取失败: %s，使用频率方法", e)
                textrank_keywords = []

            # 方法3: BM25
            try:
                bm25_keywords = self._bm25_extractor.extract(text)
            except Exception as e:
                logger.warning("BM25提取失败: %s", e)
                bm25_keywords = []

            # 方法4: TF-IDF + TextRank 结合
            try:
                combined_keywords = self._combined_extractor.extract(text)
            except Exception as e:
                logger.warning("TF-IDF+TextRank结合提取失败: %s", e)
                combined_keywords = []

            # 方法5: LLM
            try:
                llm_keywords = await self._llm_extractor.extract(text)
            except Exception as e:
                logger.warning("LLM提取失败: %s", e)
                llm_keywords = []

            # 融合结果（优化的加权融合策略）
            all_keywords = {}

            for kw in tfidf_keywords:
                key = normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        all_keywords[key].score = max(
                            all_keywords[key].score,
                            kw.score * 0.5 * strategy["weight_adjustment"]
                        )

            for kw in textrank_keywords:
                key = normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        all_keywords[key].score = max(
                            all_keywords[key].score,
                            kw.score * 0.7 * strategy["weight_adjustment"]
                        )

            for kw in bm25_keywords:
                key = normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        all_keywords[key].score = max(
                            all_keywords[key].score,
                            kw.score * 0.8 * strategy["weight_adjustment"]
                        )

            for kw in combined_keywords:
                key = normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        all_keywords[key].score = max(
                            all_keywords[key].score,
                            kw.score * 0.85 * strategy["weight_adjustment"]
                        )

            for kw in llm_keywords:
                key = normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        all_keywords[key].score = max(
                            all_keywords[key].score,
                            kw.score * 0.9 * strategy["weight_adjustment"]
                        )

            # 后处理：去重、排序、过滤
            result = list(all_keywords.values())
            result = post_process_keywords(result, text, self.stopwords)

            return result[:strategy["top_k"]]

        except Exception as e:
            logger.error("关键词提取失败: %s", e)
            return []

    def _classify_keywords(self, keywords: List[KeywordInfo]) -> Tuple[List[str], List[str]]:
        """分类关键词为动作词和目标词"""
        action_words = []
        target_words = []

        for kw in keywords:
            if kw.category == "动作" or kw.word in self.action_words:
                action_words.append(kw.word)
            elif kw.category == "对象" or kw.word in self.target_words:
                target_words.append(kw.word)

        return action_words, target_words

    def _identify_intent(self,
                         action_words: List[str],
                         target_words: List[str],
                         entities: ExtractedEntities) -> str:
        """识别主要意图"""
        if not action_words:
            return "chat"

        intent_mapping = {
            "查询": "query", "搜索": "search", "查找": "search",
            "获取": "fetch", "爬取": "scrape", "抓取": "scrape",
            "发送": "send", "创建": "create", "删除": "delete",
            "分析": "analyze", "翻译": "translate", "播放": "play",
            "打开": "open", "关闭": "close",
            "search": "search", "find": "search", "get": "fetch",
            "crawl": "scrape", "scrape": "scrape", "send": "send",
            "create": "create", "delete": "delete", "analyze": "analyze",
            "translate": "translate", "play": "play", "open": "open",
            "close": "close",
        }

        for action in action_words:
            if action in intent_mapping:
                return intent_mapping[action]

        if target_words:
            target = target_words[0]
            if "天气" in target or "weather" in target:
                return "query_weather"
            elif "邮件" in target or "email" in target:
                return "send_email"
            elif "微信" in target or "wechat" in target:
                return "send_wechat"
            elif "热搜" in target or "热榜" in target or "hot search" in target or "hot list" in target:
                return "scrape_hot"

        return "general"

    def _generate_summary(self, text: str, keywords: List[KeywordInfo]) -> str:
        """生成文本摘要"""
        sentences = re.split(r'[。！？.!?\n]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return text[:100]

        keyword_words = set(kw.word for kw in keywords[:10])

        best_sentence = ""
        max_score = 0

        for sentence in sentences:
            score = sum(1 for kw in keyword_words if kw in sentence)
            if score > max_score:
                max_score = score
                best_sentence = sentence

        return best_sentence if best_sentence else sentences[0]

    def _calculate_confidence(self,
                              keywords: List[KeywordInfo],
                              entities: ExtractedEntities,
                              intent: str) -> float:
        """计算提取置信度"""
        confidence = 0.5

        if len(keywords) >= 5:
            confidence += 0.2
        elif len(keywords) >= 3:
            confidence += 0.1

        total_entities = (
            len(entities.persons) + len(entities.locations)
            + len(entities.times) + len(entities.numbers)
        )
        if total_entities >= 3:
            confidence += 0.15
        elif total_entities >= 1:
            confidence += 0.05

        if intent != "chat" and intent != "general":
            confidence += 0.1

        high_quality_kw = sum(1 for kw in keywords if kw.score > 0.5)
        if high_quality_kw >= 3:
            confidence += 0.1

        return min(confidence, 1.0)

    def to_params(self, result: ExtractionResult) -> Dict[str, Any]:
        """将提取结果转换为技能参数"""
        params = {}

        if result.entities.locations:
            params["location"] = result.entities.locations[0]
        if result.entities.times:
            params["time"] = result.entities.times[0]
        if result.entities.numbers:
            params["count"] = result.entities.numbers[0]
        if result.entities.urls:
            params["url"] = result.entities.urls[0]
        if result.entities.emails:
            params["email"] = result.entities.emails[0]

        if result.action_words:
            params["action"] = result.action_words[0]
        if result.target_words:
            params["target"] = result.target_words[0]

        params["intent"] = result.main_intent

        return params

    def expand_keywords(self,
                        keywords: List[KeywordInfo],
                        text: str) -> List[KeywordInfo]:
        """关键词扩展功能 - 基于领域词典和相关性扩展关键词"""
        if not keywords:
            return []

        expanded = list(keywords)
        expanded_words = {kw.word for kw in expanded}

        for kw in keywords:
            related_words = self._find_related_words(kw.word)

            for related_word in related_words:
                if related_word not in expanded_words and related_word in text:
                    position = text.find(related_word)
                    position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5
                    score = kw.score * 0.6 * position_weight
                    expanded.append(KeywordInfo(
                        word=related_word,
                        score=score,
                        category=kw.category,
                        position=position,
                    ))
                    expanded_words.add(related_word)

        expanded.sort(key=lambda x: x.score, reverse=True)
        return expanded[:20]

    def _find_related_words(self, keyword: str) -> List[str]:
        """基于领域词典查找相关词"""
        related = []

        for domain, words in self.domain_dictionary.items():
            if keyword in words:
                related.extend([w for w in words if w != keyword])
                break

        if not related:
            related = self._get_semantic_similar_words(keyword)

        return related[:5]

    def _get_semantic_similar_words(self, keyword: str) -> List[str]:
        """获取语义相似词（简化版）"""
        synonym_map = {
            "天气": ["气温", "温度", "气候", "气象"],
            "搜索": ["查找", "查询", "检索", "搜寻"],
            "学习": ["教育", "培训", "课程", "知识"],
            "音乐": ["歌曲", "歌手", "专辑", "演唱会"],
            "电影": ["影片", "影视", "院线", "票房"],
            "购物": ["购买", "电商", "网购", "消费"],
            "旅游": ["旅行", "出游", "度假", "观光"],
            "健康": ["医疗", "养生", "保健", "健身"],
        }

        return synonym_map.get(keyword, [])


# 单例模式
_keyword_extractor: Optional[KeywordExtractor] = None


def get_keyword_extractor() -> KeywordExtractor:
    """获取关键词提取器单例"""
    global _keyword_extractor
    if _keyword_extractor is None:
        _keyword_extractor = KeywordExtractor()
    return _keyword_extractor

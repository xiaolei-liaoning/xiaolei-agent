"""关键词提取器 - 从长篇文本中提取关键信息（优化版）

特性：
- 多层级关键词提取（TF-IDF + TextRank + BM25 + LLM）
- 智能分句与去噪
- 实体识别（人名、地名、时间、数字等）
- 意图关键词提取
- 参数结构化提取
- **新增优化**：
  - 增强的停用词库（200+常用停用词）
  - jieba精准分词
  - BM25算法支持
  - 关键词去重和规范化
  - 领域词典扩展
  - 优化的权重融合策略
"""

import logging
import re
import math
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class KeywordInfo:
    """关键词信息"""
    word: str              # 关键词
    score: float           # 重要性分数
    category: str          # 类别（动作/对象/地点/时间/人物/其他）
    position: int          # 在原文中的位置


@dataclass
class ExtractedEntities:
    """提取的实体"""
    persons: List[str]     # 人名
    locations: List[str]   # 地点
    times: List[str]       # 时间
    numbers: List[str]     # 数字
    organizations: List[str]  # 组织
    urls: List[str]        # URL链接
    emails: List[str]      # 邮箱


@dataclass
class ExtractionResult:
    """提取结果"""
    keywords: List[KeywordInfo]        # 关键词列表
    entities: ExtractedEntities        # 实体信息
    main_intent: str                   # 主要意图
    action_words: List[str]            # 动作词
    target_words: List[str]            # 目标词
    summary: str                       # 文本摘要
    confidence: float                  # 置信度


class KeywordExtractor:
    """关键词提取器"""
    
    def __init__(self):
        self.router = None  # 延迟初始化，避免循环依赖
        
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
            # 基础停用词
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
            "刚才", "刚刚", "刚才", "之前", "之后", "以后",
            
            # 其他常见无意义词
            "东西", "事情", "问题", "情况", "方面", "部分",
            "内容", "信息", "资料", "数据", "结果", "方式",
            "方法", "手段", "途径", "过程", "步骤", "环节",
            
            # 新增：语气词和感叹词
            "真的", "确实", "当然", "肯定", "一定", "必须",
            "绝对", "完全", "彻底", "根本", "简直", "实在",
            
            # 新增：程度副词
            "太", "超", "极", "甚", "颇", "蛮", "挺",
            "稍", "略", "微", "有点", "有些", "些许",
            
            # 新增：否定词
            "没", "未", "非", "莫", "勿", "别", "休",
            "毋", "弗", "不", "无", "否",
            
            # 新增：疑问词
            "何", "啥", "咋", "岂", "焉", "安", "孰",
            "胡", "曷", "奚", "恶", "乌",
            
            # 新增：方位词
            "里", "外", "内", "中", "间", "旁", "边",
            "前", "后", "左", "右", "东", "西", "南", "北",
            
            # 新增：量词
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
        entities = self._extract_entities(cleaned_text)
        
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
            confidence=confidence
        )
        
        logger.info("关键词提取完成，提取到 %d 个关键词，置信度: %.2f", 
                   len(keywords), confidence)
        
        return result
    
    def _preprocess_text(self, text: str) -> str:
        """文本预处理
        
        Args:
            text: 原始文本
            
        Returns:
            清理后的文本
        """
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text)
        
        # 去除特殊字符（保留中文、英文、数字、常见标点）
        text = re.sub(r'[^\w\s\u4e00-\u9fff.,;:!?()""\'\-\']', '', text)
        
        # 标准化标点
        text = text.replace('，', ',').replace('。', '.').replace('！', '!')
        text = text.replace('？', '?').replace('；', ';').replace('：', ':')
        
        return text.strip()
    
    def _extract_entities(self, text: str) -> ExtractedEntities:
        """提取实体信息
        
        Args:
            text: 文本
            
        Returns:
            实体信息
        """
        entities = ExtractedEntities(
            persons=[],
            locations=[],
            times=[],
            numbers=[],
            organizations=[],
            urls=[],
            emails=[]
        )
        
        # 提取URL
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        entities.urls = re.findall(url_pattern, text)
        
        # 提取邮箱
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        entities.emails = re.findall(email_pattern, text)
        
        # 提取数字（包括小数、百分比）
        number_pattern = r'\d+\.?\d*%?'
        entities.numbers = re.findall(number_pattern, text)
        
        # 提取时间表达式（简化版）
        time_patterns = [
            r'\d{4}年\d{1,2}月\d{1,2}日',
            r'\d{1,2}月\d{1,2}日',
            r'今天|明天|后天|昨天|前天',
            r'早上|上午|中午|下午|晚上|凌晨',
            r'\d{1,2}点\d{0,2}',
            r'本周|下周|上周|本月|下月|上月',
            r'今年|明年|去年'
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, text)
            entities.times.extend(matches)
        
        # 提取地点（基于常见地点词）
        location_keywords = [
            '北京', '上海', '广州', '深圳', '杭州', '成都', '重庆',
            '南京', '武汉', '西安', '天津', '苏州', '青岛', '大连'
        ]
        for loc in location_keywords:
            if loc in text:
                entities.locations.append(loc)
        
        # 提取组织名（简化版，基于常见后缀）
        org_patterns = [
            r'[\u4e00-\u9fff]{2,10}(公司|集团|企业|学校|医院|银行)',
            r'[\u4e00-\u9fff]{2,10}(大学|学院|中学|小学)'
        ]
        for pattern in org_patterns:
            matches = re.findall(pattern, text)
            entities.organizations.extend(matches)
        
        return entities
    
    async def _extract_keywords(self, text: str) -> List[KeywordInfo]:
        """提取关键词（多层级方法 - 优化版）
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        try:
            # 检测文本所属领域
            domain = self._detect_domain(text)
            logger.info(f"检测到文本领域: {domain}")
            
            # 根据领域调整提取策略
            strategy = self._adjust_extraction_strategy(domain)
            
            # 方法1: 基于jieba分词 + TF-IDF（优化版）
            tfidf_keywords = self._extract_by_tfidf_jieba(text)
            
            # 方法2: 基于TextRank（如果有networkx）
            try:
                textrank_keywords = self._extract_by_textrank(text)
            except Exception as e:
                logger.warning("TextRank提取失败: %s，使用频率方法", e)
                textrank_keywords = []
            
            # 方法3: 基于BM25（新增）
            try:
                bm25_keywords = self._extract_by_bm25(text)
            except Exception as e:
                logger.warning("BM25提取失败: %s", e)
                bm25_keywords = []
            
            # 方法4: 基于TF-IDF和TextRank结合（新增）
            try:
                combined_keywords = self._extract_by_tfidf_textank_combined(text)
            except Exception as e:
                logger.warning("TF-IDF+TextRank结合提取失败: %s", e)
                combined_keywords = []
            
            # 方法5: 基于LLM语义理解（如果可用）
            try:
                llm_keywords = await self._extract_by_llm(text)
            except Exception as e:
                logger.warning("LLM提取失败: %s", e)
                llm_keywords = []
            
            # 合并结果（优化的加权融合策略）
            all_keywords = {}
            
            # 融合策略：优先保留高分关键词，避免简单覆盖
            for kw in tfidf_keywords:
                key = self._normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        # 取最大值，但给予TF-IDF较低权重（0.5）
                        all_keywords[key].score = max(
                            all_keywords[key].score, 
                            kw.score * 0.5 * strategy["weight_adjustment"]
                        )
            
            for kw in textrank_keywords:
                key = self._normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        # TextRank权重较高（0.7）
                        all_keywords[key].score = max(
                            all_keywords[key].score, 
                            kw.score * 0.7 * strategy["weight_adjustment"]
                        )
            
            for kw in bm25_keywords:
                key = self._normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        # BM25权重高（0.8），适合短文本
                        all_keywords[key].score = max(
                            all_keywords[key].score, 
                            kw.score * 0.8 * strategy["weight_adjustment"]
                        )
            
            for kw in combined_keywords:
                key = self._normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        # 结合算法权重高（0.85）
                        all_keywords[key].score = max(
                            all_keywords[key].score, 
                            kw.score * 0.85 * strategy["weight_adjustment"]
                        )
            
            for kw in llm_keywords:
                key = self._normalize_keyword(kw.word)
                if key and len(key) >= strategy["min_word_length"]:
                    if key not in all_keywords:
                        all_keywords[key] = kw
                    else:
                        # LLM权重最高（0.9），语义理解最准确
                        all_keywords[key].score = max(
                            all_keywords[key].score, 
                            kw.score * 0.9 * strategy["weight_adjustment"]
                        )
            
            # 后处理：去重、排序、过滤
            result = list(all_keywords.values())
            result = self._post_process_keywords(result, text)
            
            # 根据领域策略返回相应数量的关键词
            return result[:strategy["top_k"]]
            
        except Exception as e:
            logger.error("关键词提取失败: %s", e)
            # 降级方案：返回空列表
            return []
    
    def _normalize_keyword(self, keyword: str) -> str:
        """规范化关键词
        
        Args:
            keyword: 原始关键词
            
        Returns:
            规范化后的关键词
        """
        if not keyword:
            return ""
        
        # 去除首尾空白
        keyword = keyword.strip()
        
        # 转换为小写（英文）
        keyword = keyword.lower()
        
        # 去除常见标点
        keyword = re.sub(r'[^\w\u4e00-\u9fff]', '', keyword)
        
        return keyword
    
    def _post_process_keywords(self, keywords: List[KeywordInfo], text: str) -> List[KeywordInfo]:
        """后处理关键词列表
        
        Args:
            keywords: 关键词列表
            text: 原文
            
        Returns:
            处理后的关键词列表
        """
        if not keywords:
            return []
        
        # 1. 去除重复（基于规范化后的关键词）
        seen = set()
        unique_keywords = []
        for kw in keywords:
            normalized = self._normalize_keyword(kw.word)
            if normalized and normalized not in seen and len(normalized) >= 2:
                seen.add(normalized)
                unique_keywords.append(kw)
        
        # 2. 过滤低质量关键词
        filtered = []
        for kw in unique_keywords:
            # 长度检查
            if len(kw.word) < 2 or len(kw.word) > 20:
                continue
            
            # 分数检查（过滤极低分）
            if kw.score < 0.01:
                continue
            
            # 停用词二次检查
            if kw.word in self.stopwords:
                continue
            
            filtered.append(kw)
        
        # 3. 按分数重新排序
        filtered.sort(key=lambda x: x.score, reverse=True)
        
        # 4. 多样性检查（确保不同类别的关键词）
        diversified = self._diversify_keywords(filtered)
        
        return diversified
    
    def _diversify_keywords(self, keywords: List[KeywordInfo], max_per_category: int = 3) -> List[KeywordInfo]:
        """多样化关键词选择，避免单一类别过多
        
        Args:
            keywords: 已排序的关键词列表
            max_per_category: 每个类别最多选择的数量
            
        Returns:
            多样化的关键词列表
        """
        category_count = {}
        result = []
        
        for kw in keywords:
            category = kw.category
            count = category_count.get(category, 0)
            
            if count < max_per_category:
                result.append(kw)
                category_count[category] = count + 1
                
                # 如果已经收集了足够的关键词，提前退出
                if len(result) >= 15:
                    break
        
        return result
    
    def _extract_by_tfidf_jieba(self, text: str) -> List[KeywordInfo]:
        """基于jieba分词和TF-IDF提取关键词（优化版）
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        try:
            import jieba.analyse
            
            # 使用jieba的TF-IDF提取
            # allowPOS: 只保留名词、动词、形容词等有意义的词性
            keywords_with_weights = jieba.analyse.extract_tags(
                text, 
                topK=30, 
                withWeight=True,
                allowPOS=('n', 'nr', 'ns', 'nt', 'nz', 'v', 'a')  # 名词、人名、地名、机构名、动词、形容词
            )
            
            keywords = []
            for word, weight in keywords_with_weights:
                # 过滤停用词
                if word in self.stopwords or len(word) < 2:
                    continue
                
                # 计算位置权重
                position = text.find(word)
                position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5
                
                # 综合分数
                score = weight * position_weight
                
                # 判断类别
                category = self._categorize_word(word)
                
                keywords.append(KeywordInfo(
                    word=word,
                    score=score,
                    category=category,
                    position=position
                ))
            
            return keywords
            
        except ImportError:
            logger.warning("jieba.analyse未安装，使用基础方法")
            return self._extract_by_frequency(text)
        except Exception as e:
            logger.error("jieba TF-IDF提取失败: %s", e)
            return self._extract_by_frequency(text)
    
    def _extract_by_frequency(self, text: str) -> List[KeywordInfo]:
        """基于词频提取关键词（优化版 - 使用jieba分词）
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        try:
            import jieba
        except ImportError:
            logger.warning("jieba未安装，使用简单分词")
            return self._extract_by_frequency_simple(text)
        
        # 使用jieba精准模式分词
        words = jieba.lcut(text)
        
        # 过滤停用词和短词
        filtered_words = [w for w in words if w not in self.stopwords and len(w) >= 2]
        
        if not filtered_words:
            return []
        
        # 计算词频
        word_freq = Counter(filtered_words)
        
        # 转换为KeywordInfo
        keywords = []
        for word, freq in word_freq.most_common(30):
            # 计算位置权重（越靠前越重要）
            position = text.find(word)
            position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5
            
            # 综合分数
            score = freq * position_weight
            
            # 判断类别
            category = self._categorize_word(word)
            
            keywords.append(KeywordInfo(
                word=word,
                score=score,
                category=category,
                position=position
            ))
        
        return keywords
    
    def _extract_by_frequency_simple(self, text: str) -> List[KeywordInfo]:
        """基于简单分词的词频提取（降级方案）
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        # 简单分词（按字符和常见分隔符）
        words = re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{3,}', text)
        
        # 过滤停用词
        filtered_words = [w for w in words if w not in self.stopwords and len(w) >= 2]
        
        if not filtered_words:
            return []
        
        # 计算词频
        word_freq = Counter(filtered_words)
        
        # 转换为KeywordInfo
        keywords = []
        for word, freq in word_freq.most_common(30):
            # 计算位置权重（越靠前越重要）
            position = text.find(word)
            position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5
            
            # 综合分数
            score = freq * position_weight
            
            # 判断类别
            category = self._categorize_word(word)
            
            keywords.append(KeywordInfo(
                word=word,
                score=score,
                category=category,
                position=position
            ))
        
        return keywords
    
    def _extract_by_bm25(self, text: str, k1: float = 1.5, b: float = 0.75) -> List[KeywordInfo]:
        """基于BM25算法提取关键词
        
        BM25比TF-IDF更适合短文本搜索，考虑了文档长度归一化
        
        Args:
            text: 文本
            k1: BM25参数，控制词频饱和点（默认1.5）
            b: BM25参数，控制长度归一化（默认0.75）
            
        Returns:
            关键词列表
        """
        try:
            import jieba
        except ImportError:
            logger.warning("jieba未安装，跳过BM25提取")
            return []
        
        # 分词
        words = jieba.lcut(text)
        
        # 过滤停用词和短词
        filtered_words = [w for w in words if w not in self.stopwords and len(w) >= 2]
        
        if not filtered_words:
            return []
        
        # 计算词频
        word_freq = Counter(filtered_words)
        
        # 文档长度（词数）
        doc_length = len(filtered_words)
        
        # 平均文档长度（这里简化为当前文档长度）
        avg_doc_length = doc_length
        
        # 计算BM25分数
        keywords = []
        for word, freq in word_freq.items():
            # BM25公式简化版（单文档场景）
            # BM25 = IDF * (TF * (k1 + 1)) / (TF + k1 * (1 - b + b * doc_len/avg_doc_len))
            
            # 简化IDF：假设所有词都在语料库中出现过
            idf = math.log((1 + len(word_freq)) / (1 + freq)) + 1
            
            # TF部分
            tf_numerator = freq * (k1 + 1)
            tf_denominator = freq + k1 * (1 - b + b * (doc_length / avg_doc_length))
            tf_score = tf_numerator / tf_denominator
            
            # BM25分数
            bm25_score = idf * tf_score
            
            # 位置权重
            position = text.find(word)
            position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5
            
            # 综合分数
            score = bm25_score * position_weight
            
            # 判断类别
            category = self._categorize_word(word)
            
            keywords.append(KeywordInfo(
                word=word,
                score=score,
                category=category,
                position=position
            ))
        
        # 按分数排序
        keywords.sort(key=lambda x: x.score, reverse=True)
        
        return keywords[:20]
    
    def _extract_by_textrank(self, text: str) -> List[KeywordInfo]:
        """基于TextRank算法提取关键词（优化版 - 使用jieba分词）
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        try:
            import networkx as nx
            import jieba
        except ImportError as e:
            logger.warning("依赖未安装，跳过TextRank提取: %s", e)
            return []
        
        # 使用jieba精准模式分词
        words = jieba.lcut(text)
        
        # 过滤停用词和短词，只保留有意义的词性
        filtered_words = [
            w for w in words 
            if w not in self.stopwords 
            and len(w) >= 2
            and not w.isdigit()  # 排除纯数字
        ]
        
        if not filtered_words:
            return []
        
        # 构建共现图
        window_size = 5
        graph = nx.Graph()
        
        for i in range(len(filtered_words)):
            word = filtered_words[i]
            if word not in graph:
                graph.add_node(word, weight=0)
            
            # 添加共现边
            for j in range(i + 1, min(i + window_size, len(filtered_words))):
                neighbor = filtered_words[j]
                if word != neighbor:  # 避免自环
                    if graph.has_edge(word, neighbor):
                        graph[word][neighbor]['weight'] += 1
                    else:
                        graph.add_edge(word, neighbor, weight=1)
        
        # 计算TextRank
        try:
            scores = nx.pagerank(graph, weight='weight', alpha=0.85, max_iter=100)
        except Exception as e:
            logger.error("TextRank计算失败: %s", e)
            return []
        
        # 转换为KeywordInfo
        keywords = []
        for word, score in scores.items():
            category = self._categorize_word(word)
            position = text.find(word)
            
            # 位置权重
            position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5
            
            # 综合分数
            final_score = score * position_weight
            
            keywords.append(KeywordInfo(
                word=word,
                score=final_score,
                category=category,
                position=position
            ))
        
        # 按分数排序
        keywords.sort(key=lambda x: x.score, reverse=True)
        
        return keywords[:20]
    
    def _extract_by_tfidf_textank_combined(self, text: str) -> List[KeywordInfo]:
        """结合TF-IDF和TextRank算法提取关键词
        
        综合两种算法的优势，提高关键词提取的准确性
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        # 获取TF-IDF关键词
        tfidf_keywords = self._extract_by_tfidf_jieba(text)
        
        # 获取TextRank关键词
        textrank_keywords = self._extract_by_textrank(text)
        
        # 合并结果
        combined_keywords = {}
        
        # 权重分配
        for kw in tfidf_keywords:
            key = self._normalize_keyword(kw.word)
            if key:
                combined_keywords[key] = kw.score * 0.4
        
        for kw in textrank_keywords:
            key = self._normalize_keyword(kw.word)
            if key:
                if key in combined_keywords:
                    combined_keywords[key] += kw.score * 0.6
                else:
                    combined_keywords[key] = kw.score * 0.6
        
        # 转换为KeywordInfo
        result = []
        for word, score in combined_keywords.items():
            category = self._categorize_word(word)
            position = text.find(word)
            result.append(KeywordInfo(
                word=word,
                score=score,
                category=category,
                position=position
            ))
        
        # 排序
        result.sort(key=lambda x: x.score, reverse=True)
        return result[:15]
    
    async def _extract_by_llm(self, text: str) -> List[KeywordInfo]:
        """基于LLM提取关键词
        
        Args:
            text: 文本
            
        Returns:
            关键词列表
        """
        # 延迟初始化router
        if self.router is None:
            from .llm_backend import get_llm_router
            self.router = get_llm_router()
        
        prompt = f"""请从以下文本中提取关键信息，包括：
1. 主要动作（用户想做什么）
2. 目标对象（针对什么）
3. 关键参数（时间、地点、数量等）
4. 重要实体（人名、地名、组织等）

文本：{text[:500]}

请以JSON格式返回（不要用代码块）：
{{
  "actions": ["动作1", "动作2"],
  "targets": ["目标1", "目标2"],
  "parameters": {{
    "time": ["时间1"],
    "location": ["地点1"],
    "quantity": ["数量1"]
  }},
  "entities": {{
    "persons": ["人名1"],
    "locations": ["地点1"],
    "organizations": ["组织1"]
  }}
}}

注意：
1. 只返回JSON，不要其他内容
2. 如果没有某类信息，返回空数组或空对象
3. 尽量简洁，每类最多3-5个"""
        
        try:
            response = await self.router.simple_chat(
                user_message=prompt,
                system_prompt="你是关键词提取助手，只返回JSON格式",
                temperature=0.3,
            )
            
            if not response or not response.strip():
                return []
            
            # 解析JSON
            import json
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            data = json.loads(response)
            
            # 转换为KeywordInfo
            keywords = []
            
            # 处理动作
            for action in data.get("actions", []):
                keywords.append(KeywordInfo(
                    word=action,
                    score=0.9,
                    category="动作",
                    position=text.find(action)
                ))
            
            # 处理目标
            for target in data.get("targets", []):
                keywords.append(KeywordInfo(
                    word=target,
                    score=0.85,
                    category="对象",
                    position=text.find(target)
                ))
            
            # 处理参数
            params = data.get("parameters", {})
            for param_type, values in params.items():
                for value in values:
                    keywords.append(KeywordInfo(
                        word=value,
                        score=0.8,
                        category=param_type,
                        position=text.find(value)
                    ))
            
            # 处理实体
            entities = data.get("entities", {})
            for entity_type, values in entities.items():
                for value in values:
                    keywords.append(KeywordInfo(
                        word=value,
                        score=0.85,
                        category=entity_type,
                        position=text.find(value)
                    ))
            
            return keywords
            
        except Exception as e:
            logger.error("LLM关键词提取失败: %s", e)
            return []
    
    def _classify_keywords(self, keywords: List[KeywordInfo]) -> Tuple[List[str], List[str]]:
        """分类关键词为动作词和目标词
        
        Args:
            keywords: 关键词列表
            
        Returns:
            (动作词列表, 目标词列表)
        """
        action_words = []
        target_words = []
        
        for kw in keywords:
            if kw.category == "动作" or kw.word in self.action_words:
                action_words.append(kw.word)
            elif kw.category == "对象" or kw.word in self.target_words:
                target_words.append(kw.word)
        
        return action_words, target_words
    
    def _categorize_word(self, word: str) -> str:
        """判断词语类别
        
        Args:
            word: 词语
            
        Returns:
            类别
        """
        if word in self.action_words:
            return "动作"
        elif word in self.target_words:
            return "对象"
        elif any(time_word in word for time_word in ['年', '月', '日', '点', '周']):
            return "时间"
        elif any(loc in word for loc in ['北京', '上海', '广州', '深圳']):
            return "地点"
        else:
            return "其他"
    
    def _detect_domain(self, text: str) -> str:
        """检测文本所属领域
        
        Args:
            text: 文本
            
        Returns:
            领域名称
        """
        domain_scores = {}
        
        # 计算每个领域的匹配度
        for domain, keywords in self.domain_dictionary.items():
            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 1
            domain_scores[domain] = score
        
        # 找出得分最高的领域
        if domain_scores:
            best_domain = max(domain_scores, key=domain_scores.get)
            if domain_scores[best_domain] > 0:
                return best_domain
        
        return "general"
    
    def _adjust_extraction_strategy(self, domain: str) -> dict:
        """根据领域调整提取策略
        
        Args:
            domain: 领域名称
            
        Returns:
            调整后的参数
        """
        strategies = {
            "tech": {
                "min_word_length": 2,
                "top_k": 15,
                "weight_adjustment": 1.2  # 技术领域关键词权重调整
            },
            "finance": {
                "min_word_length": 2,
                "top_k": 12,
                "weight_adjustment": 1.1
            },
            "medical": {
                "min_word_length": 2,
                "top_k": 12,
                "weight_adjustment": 1.1
            },
            "entertainment": {
                "min_word_length": 2,
                "top_k": 15,
                "weight_adjustment": 1.0
            },
            "education": {
                "min_word_length": 2,
                "top_k": 12,
                "weight_adjustment": 1.0
            },
            "travel": {
                "min_word_length": 2,
                "top_k": 12,
                "weight_adjustment": 1.0
            },
            "shopping": {
                "min_word_length": 2,
                "top_k": 12,
                "weight_adjustment": 1.0
            },
            "weather": {
                "min_word_length": 2,
                "top_k": 10,
                "weight_adjustment": 1.1
            },
            "general": {
                "min_word_length": 2,
                "top_k": 12,
                "weight_adjustment": 1.0
            }
        }
        
        return strategies.get(domain, strategies["general"])
    
    def _identify_intent(self, action_words: List[str], 
                        target_words: List[str],
                        entities: ExtractedEntities) -> str:
        """识别主要意图
        
        Args:
            action_words: 动作词列表
            target_words: 目标词列表
            entities: 实体信息
            
        Returns:
            主要意图
        """
        # 基于动作词判断意图
        if not action_words:
            return "chat"  # 默认对话
        
        # 映射动作词到意图（支持中英文）
        intent_mapping = {
            # 中文动作词
            "查询": "query",
            "搜索": "search",
            "查找": "search",
            "获取": "fetch",
            "爬取": "scrape",
            "抓取": "scrape",
            "发送": "send",
            "创建": "create",
            "删除": "delete",
            "分析": "analyze",
            "翻译": "translate",
            "播放": "play",
            "打开": "open",
            "关闭": "close",
            # 英文动作词
            "search": "search",
            "find": "search",
            "get": "fetch",
            "crawl": "scrape",
            "scrape": "scrape",
            "send": "send",
            "create": "create",
            "delete": "delete",
            "analyze": "analyze",
            "translate": "translate",
            "play": "play",
            "open": "open",
            "close": "close"
        }
        
        # 找到第一个匹配的意图
        for action in action_words:
            if action in intent_mapping:
                return intent_mapping[action]
        
        # 基于目标词判断
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
        """生成文本摘要
        
        Args:
            text: 原文
            keywords: 关键词列表
            
        Returns:
            摘要
        """
        # 简单策略：提取包含最多关键词的句子
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
    
    def _calculate_confidence(self, keywords: List[KeywordInfo],
                             entities: ExtractedEntities,
                             intent: str) -> float:
        """计算提取置信度
        
        Args:
            keywords: 关键词列表
            entities: 实体信息
            intent: 意图
            
        Returns:
            置信度（0-1）
        """
        confidence = 0.5  # 基础置信度
        
        # 关键词数量加分
        if len(keywords) >= 5:
            confidence += 0.2
        elif len(keywords) >= 3:
            confidence += 0.1
        
        # 实体数量加分
        total_entities = (
            len(entities.persons) + 
            len(entities.locations) + 
            len(entities.times) +
            len(entities.numbers)
        )
        if total_entities >= 3:
            confidence += 0.15
        elif total_entities >= 1:
            confidence += 0.05
        
        # 意图明确性加分
        if intent != "chat" and intent != "general":
            confidence += 0.1
        
        # 关键词质量加分（高分关键词多则加分）
        high_quality_kw = sum(1 for kw in keywords if kw.score > 0.5)
        if high_quality_kw >= 3:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def to_params(self, result: ExtractionResult) -> Dict[str, Any]:
        """将提取结果转换为技能参数
        
        Args:
            result: 提取结果
            
        Returns:
            参数字典
        """
        params = {}
        
        # 添加实体信息
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
        
        # 添加关键词信息
        if result.action_words:
            params["action"] = result.action_words[0]
        if result.target_words:
            params["target"] = result.target_words[0]
        
        # 添加意图
        params["intent"] = result.main_intent
        
        return params
    
    def expand_keywords(self, keywords: List[KeywordInfo], text: str) -> List[KeywordInfo]:
        """关键词扩展功能 - 基于领域词典和相关性扩展关键词
        
        Args:
            keywords: 原始关键词列表
            text: 原文
            
        Returns:
            扩展后的关键词列表
        """
        if not keywords:
            return []
        
        expanded = list(keywords)  # 复制原有关键词
        expanded_words = {kw.word for kw in expanded}
        
        # 为每个关键词查找相关词
        for kw in keywords:
            # 在领域词典中查找相关词
            related_words = self._find_related_words(kw.word)
            
            for related_word in related_words:
                # 避免重复，且确保在原文中出现
                if related_word not in expanded_words and related_word in text:
                    # 计算位置权重
                    position = text.find(related_word)
                    position_weight = 1.0 / (1 + position / len(text)) if position >= 0 else 0.5
                    
                    # 给予扩展词较低的基础分数（原词的60%）
                    score = kw.score * 0.6 * position_weight
                    
                    expanded.append(KeywordInfo(
                        word=related_word,
                        score=score,
                        category=kw.category,
                        position=position
                    ))
                    expanded_words.add(related_word)
        
        # 重新排序并去重
        expanded.sort(key=lambda x: x.score, reverse=True)
        
        # 只返回前20个高质量关键词
        return expanded[:20]
    
    def _find_related_words(self, keyword: str) -> List[str]:
        """基于领域词典查找相关词
        
        Args:
            keyword: 关键词
            
        Returns:
            相关词列表
        """
        related = []
        
        # 在所有领域词典中查找
        for domain, words in self.domain_dictionary.items():
            if keyword in words:
                # 找到同一领域的其他词（排除自身）
                related.extend([w for w in words if w != keyword])
                break
        
        # 如果没有找到领域相关词，尝试语义相似词
        if not related:
            related = self._get_semantic_similar_words(keyword)
        
        return related[:5]  # 最多返回5个相关词
    
    def _get_semantic_similar_words(self, keyword: str) -> List[str]:
        """获取语义相似词（简化版）
        
        Args:
            keyword: 关键词
            
        Returns:
            相似词列表
        """
        # 简单的同义词映射（可扩展）
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
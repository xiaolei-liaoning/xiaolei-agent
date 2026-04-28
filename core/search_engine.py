"""自主搜索引擎

核心功能：
- 实时网络搜索
- 结果校验和去重
- 多源交叉验证
- 自动摘要和引用
- **智能关键词检索（新增）**
  - TF-IDF权重计算
  - 基于层级加权
  - 余弦相似度匹配
  - 返回带分数的排序结果

实现原理：
- 使用SerpAPI进行Google搜索
- 结果清洗和去重
- 相关性排序
- 多源信息融合
- 向量空间模型语义匹配
"""
import logging
import asyncio
import aiohttp
import json
import math
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)


class SelfSearchEngine:
    """自主搜索引擎"""
    
    def __init__(self):
        self.api_key = None
        self.search_url = "https://serpapi.com/search.json"
        self._initialize_config()
    
    def _initialize_config(self):
        """初始化配置"""
        try:
            from dotenv import load_dotenv
            import os
            load_dotenv()
            self.api_key = os.getenv("SERPAPI_KEY")
            if self.api_key:
                logger.info("SerpAPI 配置成功")
            else:
                logger.warning("未配置 SERPAPI_KEY，将使用备用搜索方法")
        except Exception as e:
            logger.warning("加载配置失败: %s", e)
    
    async def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """执行搜索
        
        Args:
            query: 搜索关键词
            num_results: 期望结果数量
            
        Returns:
            搜索结果列表
        """
        if self.api_key:
            return await self._search_with_serpapi(query, num_results)
        else:
            return await self._search_with_backup(query, num_results)
    
    async def _search_with_serpapi(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """使用SerpAPI进行搜索
        
        Args:
            query: 搜索关键词
            num_results: 期望结果数量
            
        Returns:
            搜索结果列表
        """
        try:
            params = {
                "q": query,
                "api_key": self.api_key,
                "num": num_results,
                "hl": "zh-cn",
                "gl": "cn"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._process_serpapi_results(data, query)
                    else:
                        logger.error("SerpAPI 请求失败: %d", response.status)
                        return await self._search_with_backup(query, num_results)
        except Exception as e:
            logger.error("SerpAPI 搜索失败: %s", e)
            return await self._search_with_backup(query, num_results)
    
    async def _search_with_backup(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """备用搜索方法
        
        Args:
            query: 搜索关键词
            num_results: 期望结果数量
            
        Returns:
            搜索结果列表
        """
        # 这里使用一个模拟的搜索结果，实际项目中可以集成其他搜索API
        logger.info("使用备用搜索方法")
        
        # 模拟搜索结果
        mock_results = [
            {
                "title": f"关于{query}的搜索结果1",
                "snippet": f"这是关于{query}的详细信息，包含了相关的内容和数据。",
                "url": f"https://example.com/search1?q={query}",
                "date": datetime.now().isoformat()
            },
            {
                "title": f"{query}的最新资讯",
                "snippet": f"最新的{query}资讯，提供了最新的发展动态和趋势。",
                "url": f"https://example.com/search2?q={query}",
                "date": datetime.now().isoformat()
            },
            {
                "title": f"{query}的详细介绍",
                "snippet": f"详细介绍了{query}的概念、原理和应用场景。",
                "url": f"https://example.com/search3?q={query}",
                "date": datetime.now().isoformat()
            }
        ]
        
        return mock_results[:num_results]
    
    def _process_serpapi_results(self, data: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
        """处理SerpAPI搜索结果
        
        Args:
            data: SerpAPI返回的数据
            query: 搜索关键词
            
        Returns:
            处理后的搜索结果列表
        """
        results = []
        
        # 处理 organic results
        if "organic_results" in data:
            for item in data["organic_results"]:
                result = {
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", ""),
                    "date": item.get("date", datetime.now().isoformat()),
                    "source": self._extract_source(item.get("link", "")),
                    "quality_score": self._calculate_quality_score(item),
                    "relevance_score": self._calculate_relevance_score(item, query),
                    "authority_score": self._calculate_authority_score(item.get("link", ""))
                }
                if result["title"] and result["url"] and result["quality_score"] > 0.3:
                    results.append(result)
        
        # 处理 featured snippet
        if "answer_box" in data:
            answer_box = data["answer_box"]
            result = {
                "title": answer_box.get("title", ""),
                "snippet": answer_box.get("answer", "") or answer_box.get("snippet", ""),
                "url": answer_box.get("link", ""),
                "date": datetime.now().isoformat(),
                "is_featured": True,
                "source": self._extract_source(answer_box.get("link", "")),
                "quality_score": 0.9,  # Featured snippet 质量分数较高
                "relevance_score": 0.9,  # Featured snippet 相关性较高
                "authority_score": 0.8  # Featured snippet 权威性较高
            }
            if result["snippet"]:
                results.insert(0, result)  #  Featured snippet 优先
        
        # 去重
        unique_results = []
        seen_urls = set()
        for result in results:
            url = result.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        # 排序（基于标题和摘要的相关性、质量分数、权威性和时效性）
        unique_results.sort(key=lambda x: self._calculate_combined_score(x, query), reverse=True)
        
        return unique_results
    
    def _extract_source(self, url: str) -> str:
        """从URL中提取来源
        
        Args:
            url: 网页URL
            
        Returns:
            来源名称
        """
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""
    
    def _calculate_quality_score(self, item: Dict[str, Any]) -> float:
        """计算搜索结果的质量分数
        
        Args:
            item: 搜索结果项
            
        Returns:
            质量分数（0-1）
        """
        score = 0.0
        
        # 检查标题长度
        title = item.get("title", "")
        if 10 <= len(title) <= 80:
            score += 0.2
        
        # 检查摘要长度
        snippet = item.get("snippet", "")
        if len(snippet) >= 50:
            score += 0.2
        
        # 检查是否有网站链接
        if item.get("link"):
            score += 0.2
        
        # 检查是否有日期
        if item.get("date"):
            score += 0.2
        
        # 检查是否有丰富的片段
        if item.get("rich_snippet"):
            score += 0.2
        
        return min(score, 1.0)
    
    def _calculate_relevance_score(self, item: Dict[str, Any], query: str) -> float:
        """计算搜索结果的相关性分数
        
        Args:
            item: 搜索结果项
            query: 搜索关键词
            
        Returns:
            相关性分数（0-1）
        """
        score = 0.0
        query_words = query.lower().split()
        
        # 标题相关性
        title = item.get("title", "").lower()
        title_match_count = sum(1 for word in query_words if word in title)
        if title_match_count > 0:
            score += (title_match_count / len(query_words)) * 0.5
        
        # 摘要相关性
        snippet = item.get("snippet", "").lower()
        snippet_match_count = sum(1 for word in query_words if word in snippet)
        if snippet_match_count > 0:
            score += (snippet_match_count / len(query_words)) * 0.3
        
        # 精确匹配
        if query.lower() in title or query.lower() in snippet:
            score += 0.2
        
        return min(score, 1.0)
    
    def _calculate_authority_score(self, url: str) -> float:
        """计算搜索结果的权威性分数
        
        Args:
            url: 搜索结果URL
            
        Returns:
            权威性分数（0-1）
        """
        score = 0.0
        
        # 域名权威性
        authority_domains = {
            ".gov": 1.0,
            ".edu": 0.9,
            ".org": 0.8,
            ".com": 0.6,
            ".net": 0.5
        }
        
        for domain, domain_score in authority_domains.items():
            if domain in url:
                score = domain_score
                break
        
        # 知名网站加分
        trusted_sites = [
            "wikipedia.org", "baidu.com", "google.com", "bing.com",
            "zhihu.com", "stackoverflow.com", "github.com",
            "medium.com", "blog.csdn.net", "juejin.cn"
        ]
        
        for site in trusted_sites:
            if site in url:
                score += 0.2
                break
        
        return min(score, 1.0)
    
    def _calculate_combined_score(self, result: Dict[str, Any], query: str) -> float:
        """计算综合分数
        
        Args:
            result: 搜索结果
            query: 搜索关键词
            
        Returns:
            综合分数（0-1）
        """
        # 计算相关性分数
        relevance_score = self._calculate_relevance(result, query)
        
        # 计算质量分数
        quality_score = result.get("quality_score", 0.5)
        
        # 计算权威性分数
        authority_score = self._calculate_authority_score(result.get("url", ""))
        
        # 计算时效性分数
        recency_score = self._calculate_recency_score(result.get("date", ""))
        
        # 权重
        weights = {
            "relevance": 0.5,  # 提高相关性权重
            "quality": 0.15,
            "authority": 0.15,
            "recency": 0.2
        }
        
        # 计算综合分数
        combined_score = (
            relevance_score * weights["relevance"] +
            quality_score * weights["quality"] +
            authority_score * weights["authority"] +
            recency_score * weights["recency"]
        )
        
        return min(combined_score, 1.0)
    
    def _calculate_recency_score(self, date_str: str) -> float:
        """计算时效性分数
        
        Args:
            date_str: 日期字符串
            
        Returns:
            时效性分数（0-1）
        """
        try:
            if not date_str:
                return 0.5
            
            # 解析日期
            date = datetime.fromisoformat(date_str)
            now = datetime.now()
            
            # 计算天数差
            days_diff = (now - date).days
            
            # 时效性分数：越新分数越高
            if days_diff == 0:
                return 1.0
            elif days_diff <= 7:
                return 0.9
            elif days_diff <= 30:
                return 0.7
            elif days_diff <= 90:
                return 0.5
            elif days_diff <= 180:
                return 0.3
            else:
                return 0.1
        except Exception:
            return 0.5
    
    def _calculate_relevance(self, result: Dict[str, Any], query: str) -> float:
        """计算搜索结果与查询的相关性
        
        Args:
            result: 搜索结果
            query: 搜索关键词
            
        Returns:
            相关性得分（0-1）
        """
        score = 0.0
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()
        query_lower = query.lower()
        
        # 完全匹配
        if query_lower in title:
            score += 0.5
        if query_lower in snippet:
            score += 0.3
        
        # 部分匹配
        for word in query_lower.split():
            if word in title:
                score += 0.1
            if word in snippet:
                score += 0.05
        
        # Featured snippet 加分
        if result.get("is_featured", False):
            score += 0.2
        
        return min(score, 1.0)
    
    async def get_webpage_content(self, url: str) -> Optional[str]:
        """获取网页内容
        
        Args:
            url: 网页URL
            
        Returns:
            网页内容，如果失败则返回None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.text()
                        # 简单的HTML清理
                        import re
                        # 移除HTML标签
                        text = re.sub(r'<[^>]+>', '', content)
                        # 移除多余的空白字符
                        text = re.sub(r'\s+', ' ', text).strip()
                        return text[:2000]  # 只返回前2000个字符
                    else:
                        logger.error("获取网页内容失败: %d", response.status)
                        return None
        except Exception as e:
            logger.error("获取网页内容异常: %s", e)
            return None
    
    async def validate_information(self, information: str, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """验证信息的准确性
        
        Args:
            information: 要验证的信息
            sources: 信息来源列表
            
        Returns:
            验证结果
        """
        # 简单的验证逻辑：检查多个来源是否包含相同的信息
        validation_result = {
            "validated": False,
            "confidence": 0.0,
            "sources": [],
            "issues": []
        }
        
        if not sources:
            validation_result["issues"].append("没有足够的信息来源")
            return validation_result
        
        # 检查信息在多少个来源中出现
        match_count = 0
        matched_sources = []
        
        for source in sources:
            snippet = source.get("snippet", "").lower()
            if any(keyword.lower() in snippet for keyword in information.split()[:5]):
                match_count += 1
                matched_sources.append(source)
        
        # 计算置信度
        confidence = match_count / len(sources)
        validation_result["confidence"] = confidence
        validation_result["sources"] = matched_sources
        
        # 判断是否验证通过
        if confidence >= 0.6:
            validation_result["validated"] = True
        else:
            validation_result["issues"].append("信息在多个来源中不一致")
        
        return validation_result
    
    async def generate_summary(self, results: List[Dict[str, Any]]) -> str:
        """生成搜索结果摘要
        
        Args:
            results: 搜索结果列表
            
        Returns:
            摘要文本
        """
        if not results:
            return "没有找到相关信息"
        
        # 提取关键信息
        key_points = []
        for i, result in enumerate(results[:3]):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            if title and snippet:
                key_points.append(f"[{i+1}] {title}: {snippet[:150]}...")
        
        # 生成摘要
        summary = "搜索结果摘要：\n"
        summary += "\n".join(key_points)
        
        return summary
    
    async def search_by_keywords(
        self, 
        keywords: List[str], 
        documents: List[Dict[str, Any]],
        use_tfidf: bool = True,
        use_hierarchy: bool = True,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """基于关键词的智能检索（v4.2.2增强版）
        
        核心改进：
        1. ✅ 新增精准关键词匹配（精确匹配得分）
        2. ✅ 新增BM25算法（更适合短文本）
        3. ✅ 动态权重调整（根据文本长度）
        4. ✅ 短语匹配支持（完整短语加分）
        
        Args:
            keywords: 关键词列表
            documents: 文档列表，每个文档包含：
                - content: 文档内容
                - title: 文档标题（可选）
                - metadata: 元数据（可选）
                - hierarchy_level: 层级级别（1-5，1为最高层）
            use_tfidf: 是否使用TF-IDF权重
            use_hierarchy: 是否使用层级加权
            top_k: 返回前k个结果
            
        Returns:
            带分数的排序结果列表，每个结果包含：
                - document: 原始文档
                - score: 综合得分
                - exact_match_score: 精准匹配分数
                - bm25_score: BM25分数
                - tfidf_score: TF-IDF分数
                - cosine_score: 余弦相似度分数
                - phrase_match_score: 短语匹配分数
                - hierarchy_score: 层级分数
                - matched_keywords: 匹配的关键词
        """
        logger.info("开始智能关键词检索(v4.2.2)，关键词数: %d, 文档数: %d", len(keywords), len(documents))
        
        if not keywords or not documents:
            return []
        
        # 1. 预处理关键词
        processed_keywords = self._preprocess_keywords(keywords)
        
        # 2. 计算平均文档长度（用于BM25）
        avg_doc_length = self._calculate_avg_doc_length(documents)
        
        # 3. 构建文档向量空间
        doc_vectors = []
        for doc in documents:
            vector = self._build_document_vector(doc, processed_keywords, use_tfidf)
            doc_vectors.append(vector)
        
        # 4. 构建查询向量
        query_vector = self._build_query_vector(processed_keywords, use_tfidf)
        
        # 5. 计算多维度分数
        results = []
        for i, (doc, doc_vector) in enumerate(zip(documents, doc_vectors)):
            # 【新增】精准关键词匹配分数
            exact_match_score = self._calculate_exact_match_score(doc, processed_keywords)
            
            # 【新增】BM25分数（更适合短文本）
            bm25_score = self._calculate_bm25_score(doc, processed_keywords, avg_doc_length)
            
            # 计算余弦相似度
            cosine_score = self._cosine_similarity(query_vector, doc_vector)
            
            # 计算TF-IDF分数
            tfidf_score = self._calculate_tfidf_score(query_vector, doc_vector) if use_tfidf else 0.0
            
            # 【新增】短语匹配分数
            phrase_match_score = self._calculate_phrase_match_score(doc, processed_keywords)
            
            # 计算层级分数
            hierarchy_score = self._calculate_hierarchy_score(doc) if use_hierarchy else 0.0
            
            # 查找匹配的关键词
            matched_keywords = self._find_matched_keywords(doc, processed_keywords)
            
            # 【优化】动态权重配置（根据文本长度调整）
            content_length = len(doc.get("content", ""))
            weights = self._get_dynamic_weights(content_length)
            
            # 综合分数（加权求和）
            combined_score = (
                exact_match_score * weights["exact_match"] +
                bm25_score * weights["bm25"] +
                cosine_score * weights["cosine"] +
                tfidf_score * weights["tfidf"] +
                phrase_match_score * weights["phrase_match"] +
                hierarchy_score * weights["hierarchy"]
            )
            
            results.append({
                "document": doc,
                "score": combined_score,
                "exact_match_score": exact_match_score,
                "bm25_score": bm25_score,
                "tfidf_score": tfidf_score,
                "cosine_score": cosine_score,
                "phrase_match_score": phrase_match_score,
                "hierarchy_score": hierarchy_score,
                "matched_keywords": matched_keywords,
                "match_count": len(matched_keywords)
            })
        
        # 6. 按综合分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        
        # 7. 返回top_k结果
        top_results = results[:top_k]
        
        logger.info("智能检索完成，返回 %d 个结果（最高分: %.3f）", 
                   len(top_results), top_results[0]["score"] if top_results else 0)
        
        return top_results
    
    def _preprocess_keywords(self, keywords: List[str]) -> List[str]:
        """预处理关键词
        
        Args:
            keywords: 原始关键词列表
            
        Returns:
            处理后的关键词列表
        """
        try:
            import jieba
        except ImportError:
            logger.warning("jieba未安装，使用简单分词")
            return [kw.lower().strip() for kw in keywords if kw.strip()]
        
        processed = []
        for keyword in keywords:
            # 使用jieba分词
            words = jieba.lcut(keyword)
            # 过滤停用词和短词
            filtered = [w for w in words if len(w) >= 2 and w not in self._get_stopwords()]
            processed.extend(filtered)
        
        # 去重
        return list(set(processed))
    
    def _get_stopwords(self) -> set:
        """获取停用词集合
        
        Returns:
            停用词集合
        """
        return {
            "的", "了", "在", "是", "我", "有", "和", "就",
            "不", "人", "都", "一", "一个", "上", "也", "很",
            "到", "说", "要", "去", "你", "会", "着", "没有",
            "看", "好", "自己", "这", "他", "她", "它", "们",
            "那", "些", "什么", "怎么", "如何", "为什么"
        }
    
    def _build_document_vector(
        self, 
        doc: Dict[str, Any], 
        keywords: List[str],
        use_tfidf: bool = True
    ) -> Dict[str, float]:
        """构建文档向量
        
        Args:
            doc: 文档
            keywords: 关键词列表
            use_tfidf: 是否使用TF-IDF
            
        Returns:
            文档向量（关键词 -> 权重）
        """
        content = doc.get("content", "")
        title = doc.get("title", "")
        
        # 合并标题和内容（标题权重更高）
        weighted_content = f"{title} {title} {content}"
        
        try:
            import jieba
            words = jieba.lcut(weighted_content)
        except ImportError:
            # 简单分词
            words = re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{3,}', weighted_content)
        
        # 计算词频
        word_freq = Counter(words)
        total_words = len(words) if words else 1
        
        vector = {}
        for keyword in keywords:
            freq = word_freq.get(keyword, 0)
            
            if use_tfidf:
                # TF-IDF: TF * IDF
                tf = freq / total_words
                # 简化IDF：假设所有关键词都在文档集中出现
                idf = math.log(len(keywords) / (1 + freq))
                vector[keyword] = tf * idf
            else:
                # 仅使用词频
                vector[keyword] = freq
        
        return vector
    
    def _build_query_vector(
        self, 
        keywords: List[str],
        use_tfidf: bool = True
    ) -> Dict[str, float]:
        """构建查询向量
        
        Args:
            keywords: 关键词列表
            use_tfidf: 是否使用TF-IDF
            
        Returns:
            查询向量
        """
        vector = {}
        for keyword in keywords:
            # 查询向量中所有关键词权重相等
            vector[keyword] = 1.0
        
        return vector
    
    def _cosine_similarity(
        self, 
        vec1: Dict[str, float], 
        vec2: Dict[str, float]
    ) -> float:
        """计算余弦相似度
        
        Args:
            vec1: 向量1
            vec2: 向量2
            
        Returns:
            余弦相似度（0-1）
        """
        # 获取所有维度
        all_keys = set(vec1.keys()) | set(vec2.keys())
        
        if not all_keys:
            return 0.0
        
        # 计算点积
        dot_product = sum(vec1.get(k, 0) * vec2.get(k, 0) for k in all_keys)
        
        # 计算模长
        magnitude1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        magnitude2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        # 余弦相似度
        similarity = dot_product / (magnitude1 * magnitude2)
        
        return max(0.0, min(1.0, similarity))
    
    def _calculate_tfidf_score(
        self, 
        query_vec: Dict[str, float], 
        doc_vec: Dict[str, float]
    ) -> float:
        """计算TF-IDF分数
        
        Args:
            query_vec: 查询向量
            doc_vec: 文档向量
            
        Returns:
            TF-IDF分数（0-1）
        """
        # 计算加权点积
        all_keys = set(query_vec.keys()) & set(doc_vec.keys())
        
        if not all_keys:
            return 0.0
        
        score = sum(query_vec[k] * doc_vec[k] for k in all_keys)
        
        # 归一化到0-1
        max_possible = sum(query_vec[k] * max(doc_vec.values()) for k in query_vec.keys())
        
        if max_possible == 0:
            return 0.0
        
        normalized_score = score / max_possible
        
        return max(0.0, min(1.0, normalized_score))
    
    def _calculate_hierarchy_score(self, doc: Dict[str, Any]) -> float:
        """计算层级分数
        
        Args:
            doc: 文档
            
        Returns:
            层级分数（0-1），层级越高分数越高
        """
        hierarchy_level = doc.get("hierarchy_level", 3)  # 默认中层
        
        # 层级映射：1->1.0, 2->0.8, 3->0.6, 4->0.4, 5->0.2
        level_scores = {
            1: 1.0,
            2: 0.8,
            3: 0.6,
            4: 0.4,
            5: 0.2
        }
        
        return level_scores.get(hierarchy_level, 0.5)
    
    def _calculate_avg_doc_length(self, documents: List[Dict[str, Any]]) -> float:
        """计算平均文档长度（词数）
        
        Args:
            documents: 文档列表
            
        Returns:
            平均文档长度
        """
        if not documents:
            return 0.0
        
        total_length = 0
        count = 0
        try:
            import jieba
        except ImportError:
            jieba = None
            
        for doc in documents:
            content = doc.get("content", "")
            if jieba:
                words = jieba.lcut(content)
                # 过滤停用词和单字
                filtered = [w for w in words if len(w) > 1 and w not in self._get_stopwords()]
                total_length += len(filtered)
            else:
                # 简单估算：非空白字符数 / 2
                total_length += len(re.sub(r'\s+', '', content)) / 2
            count += 1
            
        return total_length / count if count > 0 else 0.0

    def _calculate_exact_match_score(self, doc: Dict[str, Any], keywords: List[str]) -> float:
        """计算精准匹配分数
        
        Args:
            doc: 文档
            keywords: 关键词列表
            
        Returns:
            精准匹配分数（0-1）
        """
        content = doc.get("content", "").lower()
        title = doc.get("title", "").lower()
        
        if not keywords:
            return 0.0
            
        match_count = 0
        for kw in keywords:
            kw_lower = kw.lower()
            # 中文直接使用in操作符，英文使用单词边界匹配
            if re.match(r'^[a-zA-Z]+$', kw):
                # 英文：使用单词边界
                pattern = r'\b' + re.escape(kw_lower) + r'\b'
                if re.search(pattern, content) or re.search(pattern, title):
                    match_count += 1
            else:
                # 中文：直接查找
                if kw_lower in content or kw_lower in title:
                    match_count += 1
                
        return match_count / len(keywords)

    def _calculate_bm25_score(
        self, 
        doc: Dict[str, Any], 
        keywords: List[str], 
        avg_doc_length: float,
        k1: float = 1.5,
        b: float = 0.75
    ) -> float:
        """计算BM25分数
        
        Args:
            doc: 文档
            keywords: 关键词列表
            avg_doc_length: 平均文档长度
            k1: BM25参数，控制词频饱和点
            b: BM25参数，控制文档长度归一化
            
        Returns:
            BM25分数
        """
        try:
            import jieba
        except ImportError:
            jieba = None
            
        content = doc.get("content", "")
        title = doc.get("title", "")
        # 标题权重加倍
        full_text = f"{title} {title} {content}"
        
        if jieba:
            words = jieba.lcut(full_text)
            # 过滤停用词
            filtered_words = [w for w in words if len(w) > 1 and w not in self._get_stopwords()]
        else:
            filtered_words = re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{3,}', full_text)
            
        doc_len = len(filtered_words)
        word_freq = Counter(filtered_words)
        
        score = 0.0
        num_docs = len(keywords) # 这里简化处理，假设关键词集合代表文档集大小用于IDF估算
        
        for kw in keywords:
            freq = word_freq.get(kw, 0)
            if freq == 0:
                continue
                
            # 简化IDF计算: log((N - n + 0.5) / (n + 0.5) + 1)
            # 由于没有全局文档频率统计，这里假设每个关键词至少在少量文档中出现
            # 使用一个固定的较小值作为 IDF 的基础，或者仅依赖 TF 部分
            # 为了演示效果，这里给一个基于频率的简单加权
            idf = math.log(1.5) # 简化 IDF
            
            # BM25 TF 部分
            numerator = freq * (k1 + 1)
            denominator = freq + k1 * (1 - b + b * (doc_len / avg_doc_length if avg_doc_length > 0 else 1))
            
            score += idf * (numerator / denominator)
            
        return score

    def _calculate_phrase_match_score(self, doc: Dict[str, Any], keywords: List[str]) -> float:
        """计算短语匹配分数
        
        Args:
            doc: 文档
            keywords: 关键词列表
            
        Returns:
            短语匹配分数（0-1）
        """
        content = doc.get("content", "").lower()
        title = doc.get("title", "").lower()
        combined = f"{title} {content}"
        
        if len(keywords) < 2:
            return 0.0
            
        # 尝试将关键词组合成短语进行匹配
        # 这里简单地将所有关键词按顺序连接作为一个短语检查
        # 更复杂的实现可以检查滑动窗口
        phrase = " ".join(keywords)
        if phrase in combined:
            return 1.0
            
        # 检查两两相邻关键词是否在文中相邻出现
        matches = 0
        total_pairs = 0
        for i in range(len(keywords) - 1):
            pair = f"{keywords[i]} {keywords[i+1]}"
            total_pairs += 1
            if pair in combined:
                matches += 1
                
        return matches / total_pairs if total_pairs > 0 else 0.0

    def _get_dynamic_weights(self, content_length: int) -> Dict[str, float]:
        """根据内容长度获取动态权重
        
        Args:
            content_length: 内容长度
            
        Returns:
            权重字典
        """
        # 短文本更依赖精准匹配和BM25，长文本更依赖TF-IDF和余弦相似度
        if content_length < 100:
            return {
                "exact_match": 0.3,
                "bm25": 0.3,
                "cosine": 0.1,
                "tfidf": 0.1,
                "phrase_match": 0.1,
                "hierarchy": 0.1
            }
        elif content_length < 500:
            return {
                "exact_match": 0.2,
                "bm25": 0.2,
                "cosine": 0.2,
                "tfidf": 0.2,
                "phrase_match": 0.1,
                "hierarchy": 0.1
            }
        else:
            return {
                "exact_match": 0.1,
                "bm25": 0.1,
                "cosine": 0.3,
                "tfidf": 0.3,
                "phrase_match": 0.1,
                "hierarchy": 0.1
            }

    def _find_matched_keywords(
        self, 
        doc: Dict[str, Any], 
        keywords: List[str]
    ) -> List[str]:
        """查找文档中匹配的关键词
        
        Args:
            doc: 文档
            keywords: 关键词列表
            
        Returns:
            匹配的关键词列表
        """
        content = doc.get("content", "").lower()
        title = doc.get("title", "").lower()
        combined = f"{title} {content}"
        
        matched = []
        for keyword in keywords:
            if keyword.lower() in combined:
                matched.append(keyword)
        
        return matched
    
    async def analyze_and_respond(
        self,
        query: str,
        keywords_result: Any,
        search_results: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """分析搜索结果并生成人性化回复
        
        Args:
            query: 用户原始查询
            keywords_result: 关键词提取结果（ExtractionResult）
            search_results: 搜索结果列表
            context: 上下文信息
            
        Returns:
            人性化回复
        """
        logger.info("开始分析搜索结果并生成回复")
        
        try:
            # 延迟导入
            from .llm_backend import get_llm_router
            router = get_llm_router()
            
            # 构建搜索结果摘要
            results_summary = self._format_search_results(search_results)
            
            # 构建提示词
            prompt = f"""请根据以下信息，为用户查询生成一个专业、友好且有用的回复。

**用户查询**: {query}

**提取的关键词**:
- 主要意图: {keywords_result.main_intent if hasattr(keywords_result, 'main_intent') else '未知'}
- 动作词: {', '.join(keywords_result.action_words[:5]) if hasattr(keywords_result, 'action_words') else '无'}
- 目标词: {', '.join(keywords_result.target_words[:5]) if hasattr(keywords_result, 'target_words') else '无'}
- 实体信息: {self._format_entities(keywords_result.entities) if hasattr(keywords_result, 'entities') else '无'}

**搜索结果** (共{len(search_results)}条):
{results_summary}

**回复要求**:
1. 开头用简洁的语言概括核心发现（1-2句话）
2. 列出3-5个关键要点，使用emoji增强可读性
3. 提供实用的建议或下一步行动
4. 如果有数据来源，标注引用
5. 语气友好、专业，像真人对话
6. 使用Markdown格式，适当使用粗体、列表等
7. 如果信息不足，诚实说明并提供可能的方向

请生成回复："""
            
            # 调用LLM生成回复
            response = await router.simple_chat(
                user_message=prompt,
                system_prompt="你是一个专业的AI助手，擅长分析信息并生成人性化的回复。",
                temperature=0.7
            )
            
            if response:
                logger.info("成功生成人性化回复")
                return response
            else:
                logger.warning("LLM回复为空，使用降级方案")
                return self._generate_fallback_response(query, search_results)
                
        except Exception as e:
            logger.error("生成回复失败: %s", e)
            return self._generate_fallback_response(query, search_results)
    
    def _format_search_results(self, results: List[Dict[str, Any]]) -> str:
        """格式化搜索结果为文本
        
        Args:
            results: 搜索结果列表
            
        Returns:
            格式化文本
        """
        if not results:
            return "未找到相关结果"
        
        formatted = []
        for i, result in enumerate(results[:5], 1):
            doc = result.get("document", result)
            title = doc.get("title", "无标题")
            content = doc.get("content", doc.get("snippet", ""))[:200]
            score = result.get("score", 0)
            matched = result.get("matched_keywords", [])
            
            formatted.append(
                f"{i}. **{title}** (相关度: {score:.2f})\n"
                f"   内容: {content}...\n"
                f"   匹配关键词: {', '.join(matched[:3]) if matched else '无'}\n"
            )
        
        return "\n".join(formatted)
    
    def _format_entities(self, entities: Any) -> str:
        """格式化实体信息
        
        Args:
            entities: 实体对象
            
        Returns:
            格式化文本
        """
        parts = []
        
        if hasattr(entities, 'persons') and entities.persons:
            parts.append(f"人物: {', '.join(entities.persons[:3])}")
        if hasattr(entities, 'locations') and entities.locations:
            parts.append(f"地点: {', '.join(entities.locations[:3])}")
        if hasattr(entities, 'times') and entities.times:
            parts.append(f"时间: {', '.join(entities.times[:3])}")
        if hasattr(entities, 'organizations') and entities.organizations:
            parts.append(f"组织: {', '.join(entities.organizations[:3])}")
        
        return "; ".join(parts) if parts else "无"
    
    def _generate_fallback_response(
        self, 
        query: str, 
        results: List[Dict[str, Any]]
    ) -> str:
        """生成降级回复（当LLM不可用时）
        
        Args:
            query: 用户查询
            results: 搜索结果
            
        Returns:
            降级回复
        """
        if not results:
            return f"抱歉，我没有找到关于\"{query}\"的相关信息。您可以尝试换个关键词再问我。"
        
        response = f"🔍 关于\"{query}\"的搜索结果：\n\n"
        
        for i, result in enumerate(results[:3], 1):
            doc = result.get("document", result)
            title = doc.get("title", "无标题")
            content = doc.get("content", doc.get("snippet", ""))[:150]
            
            response += f"{i}. **{title}**\n"
            response += f"   {content}...\n\n"
        
        response += "💡 **建议**：\n"
        response += "- 如需更详细的信息，可以点击相关链接查看原文\n"
        response += "- 或者提供更具体的关键词，我可以帮您进一步筛选"
        
        return response


# 全局自主搜索引擎实例
self_search_engine = None

def get_self_search_engine() -> SelfSearchEngine:
    """获取自主搜索引擎实例
    
    Returns:
        SelfSearchEngine实例
    """
    global self_search_engine
    if self_search_engine is None:
        self_search_engine = SelfSearchEngine()
    return self_search_engine
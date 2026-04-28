"""深度思考引擎

核心功能：
- 理解问题并判断是否需要信息
- 制定思考计划和步骤
- 评估信息需求并触发搜索
- 执行验证和自我反思
- 修正和完善答案

实现原理：
- 多轮隐式推理
- 思维链（CoT）强化版
- 自我反思（Self-Reflect）
"""
import logging
import asyncio
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import OrderedDict

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """深度思考引擎"""
    
    def __init__(self):
        self.llm_router = None
        self.search_engine = None
        self._initialize_dependencies()
        # 缓存机制 - 使用OrderedDict实现LRU缓存
        self._cache = OrderedDict()  # 使用OrderedDict实现LRU缓存
        self._cache_expiry = timedelta(minutes=10)  # 缓存过期时间：10分钟
        self._max_cache_size = 500  # 增加最大缓存容量：500条
        # 批量缓存检查和清理
        self._last_cache_cleanup = datetime.now()
        self._cache_cleanup_interval = timedelta(minutes=5)  # 每5分钟清理一次过期缓存
    
    def _initialize_dependencies(self):
        """初始化依赖"""
        try:
            from core.llm_backend import get_llm_router
            self.llm_router = get_llm_router()
            logger.info("LLM 后端初始化成功")
        except Exception as e:
            logger.warning("LLM 后端初始化失败: %s", e)
        
        try:
            from core.search_engine import SelfSearchEngine
            self.search_engine = SelfSearchEngine()
            logger.info("自主搜索引擎初始化成功")
        except Exception as e:
            logger.warning("自主搜索引擎初始化失败: %s", e)
    
    def _get_message_hash(self, message: str) -> str:
        """计算消息的哈希值，用于缓存键
        
        Args:
            message: 用户消息
            
        Returns:
            消息的哈希值
        """
        return hashlib.md5(message.encode('utf-8')).hexdigest()
    
    def _get_cache(self, message: str) -> Optional[Dict[str, Any]]:
        """获取缓存
        
        Args:
            message: 用户消息
            
        Returns:
            缓存的结果，如果不存在或过期则返回None
        """
        cache_key = self._get_message_hash(message)
        if cache_key in self._cache:
            cached_result, timestamp = self._cache[cache_key]
            # 检查缓存是否过期
            if datetime.now() - timestamp < self._cache_expiry:
                # 将访问的项移到末尾，表示最近使用
                self._cache.move_to_end(cache_key)
                return cached_result
            else:
                # 缓存过期，删除
                del self._cache[cache_key]
        return None
    
    def _cleanup_cache(self):
        """清理过期缓存"""
        current_time = datetime.now()
        # 检查是否需要清理
        if current_time - self._last_cache_cleanup < self._cache_cleanup_interval:
            return
        
        # 清理过期缓存
        expired_keys = []
        for key, (_, timestamp) in self._cache.items():
            if current_time - timestamp >= self._cache_expiry:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        # 记录清理时间
        self._last_cache_cleanup = current_time
        logger.info(f"清理了 {len(expired_keys)} 个过期缓存，当前缓存大小: {len(self._cache)}")
    
    def _update_cache(self, message: str, result: Dict[str, Any]) -> None:
        """更新缓存
        
        Args:
            message: 用户消息
            result: 处理结果
        """
        # 定期清理过期缓存
        self._cleanup_cache()
        
        cache_key = self._get_message_hash(message)
        # 如果键已存在，先删除它
        if cache_key in self._cache:
            del self._cache[cache_key]
        # 添加到末尾，表示最近使用
        self._cache[cache_key] = (result, datetime.now())
        # 限制缓存大小，最多保存指定数量的记录
        if len(self._cache) > self._max_cache_size:
            # 删除最久未使用的缓存（OrderedDict的第一个项）
            self._cache.popitem(last=False)
    
    async def process(self, message: str, user_id: int = 1) -> Dict[str, Any]:
        """处理用户消息，执行深度思考
        
        Args:
            message: 用户消息
            user_id: 用户ID
            
        Returns:
            包含思考过程和最终答案的字典
        """
        start_time = datetime.now()
        
        # 检查缓存
        cached_result = self._get_cache(message)
        if cached_result:
            end_time = datetime.now()
            elapsed = (end_time - start_time).total_seconds()
            # 更新时间戳
            cached_result['elapsed_time'] = elapsed
            cached_result['timestamp'] = end_time.isoformat()
            return cached_result
        
        # 1. 快速预处理 - 检查是否为简单问题
        if self._is_simple_question(message):
            # 简单问题直接回答，跳过完整思考流程
            final_answer = await self._quick_answer(message)
            end_time = datetime.now()
            elapsed = (end_time - start_time).total_seconds()
            
            result = {
                "final_answer": final_answer,
                "thinking_process": {
                    "type": "quick",
                    "reason": "简单问题，直接回答"
                },
                "elapsed_time": elapsed,
                "timestamp": end_time.isoformat()
            }
            
            # 更新缓存
            self._update_cache(message, result)
            
            return result
        
        # 2. 理解问题并判断是否需要信息
        understanding = await self._understand_question(message)
        logger.info("理解结果: %s", understanding)
        
        # 3. 制定思考计划
        plan = await self._create_plan(understanding, message)
        logger.info("思考计划: %s", plan)
        
        # 4. 评估信息需求
        info_needed = await self._assess_info_needs(plan, message)
        logger.info("信息需求评估: %s", info_needed)
        
        # 5. 执行搜索（如果需要）
        search_results = []
        if info_needed.get("needs_search", False):
            search_results = await self._execute_search(info_needed, message)
            logger.info("搜索结果数量: %d", len(search_results))
        
        # 6. 执行验证和自我反思
        validation = await self._validate_and_reflect(plan, search_results, message)
        logger.info("验证和反思结果: %s", validation)
        
        # 7. 多源信息融合
        fused_info = self._fuse_information(search_results, message)
        
        # 8. 生成最终答案
        final_answer = await self._generate_final_answer(plan, search_results, validation, message, fused_info)
        
        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()
        
        result = {
            "final_answer": final_answer,
            "thinking_process": {
                "understanding": understanding,
                "plan": plan,
                "info_needed": info_needed,
                "search_results": search_results[:3],  # 只返回前3个结果
                "validation": validation,
                "fused_info": fused_info
            },
            "elapsed_time": elapsed,
            "timestamp": end_time.isoformat()
        }
        
        # 更新缓存
        self._update_cache(message, result)
        
        return result
    
    async def _understand_question(self, message: str) -> Dict[str, Any]:
        """理解问题
        
        Args:
            message: 用户消息
            
        Returns:
            包含问题类型、关键信息、是否需要实时信息的字典
        """
        if not self.llm_router or not self.llm_router.is_available():
            # 基于规则的理解
            realtime_keywords = ["最新", "最近", "今天", "现在", "2026", "2025", "2024", "新闻", "趋势", "最新消息", "天气", "当前", "此刻", "最近的", "最新的"]
            message_lower = message.lower()
            needs_realtime_info = any(keyword in message_lower for keyword in realtime_keywords)
            matched_keywords = [k for k in realtime_keywords if k in message_lower]
            logger.info(f"LLM不可用，使用备用逻辑。消息: {message}, 需要实时信息: {needs_realtime_info}, 匹配的关键词: {matched_keywords}")
            return {
                "question_type": "fact" if needs_realtime_info else "general",
                "key_information": message,
                "needs_realtime_info": needs_realtime_info,
                "confidence": 0.7 if needs_realtime_info else 0.5
            }
        
        prompt = f"""
请分析以下用户问题，并返回JSON格式的理解结果：

用户问题：{message}

分析内容包括：
1. question_type: 问题类型（如：事实查询、观点询问、建议请求、指令执行等）
2. key_information: 关键信息点
3. needs_realtime_info: 是否需要实时信息（是/否）
4. confidence: 理解置信度（0-1）

请只返回JSON，不要包含其他内容。
"""
        
        try:
            response = await self.llm_router.simple_chat(prompt)
            # 检查响应是否为错误信息
            if "GLM 调用失败" in response or "模型服务暂时不可用" in response or "请求过于频繁" in response:
                logger.warning("LLM API 返回错误信息，使用备用逻辑")
                # 基于规则的理解
                realtime_keywords = ["最新", "最近", "今天", "现在", "2026", "2025", "2024", "新闻", "趋势", "最新消息", "天气", "当前", "此刻", "最近的", "最新的"]
                needs_realtime_info = any(keyword in message.lower() for keyword in realtime_keywords)
                return {
                    "question_type": "fact" if needs_realtime_info else "general",
                    "key_information": message,
                    "needs_realtime_info": needs_realtime_info,
                    "confidence": 0.7 if needs_realtime_info else 0.5
                }
            import json
            # 尝试解析JSON
            result = json.loads(response)
            # 验证结果格式
            if isinstance(result, dict) and all(key in result for key in ["question_type", "key_information", "needs_realtime_info", "confidence"]):
                return result
            else:
                raise ValueError("Invalid JSON format")
        except Exception as e:
            logger.error("理解问题失败: %s", e)
            # 基于规则的理解
            realtime_keywords = ["最新", "最近", "今天", "现在", "2026", "2025", "2024", "新闻", "趋势", "最新消息", "天气", "当前", "此刻", "最近的", "最新的"]
            message_lower = message.lower()
            needs_realtime_info = any(keyword in message_lower for keyword in realtime_keywords)
            logger.info(f"消息: {message}, 实时关键词检查: {needs_realtime_info}, 关键词: {[k for k in realtime_keywords if k in message_lower]}")
            return {
                "question_type": "fact" if needs_realtime_info else "general",
                "key_information": message,
                "needs_realtime_info": needs_realtime_info,
                "confidence": 0.7 if needs_realtime_info else 0.5
            }
    
    async def _create_plan(self, understanding: Dict[str, Any], message: str) -> Dict[str, Any]:
        """制定思考计划
        
        Args:
            understanding: 问题理解结果
            message: 用户消息
            
        Returns:
            包含思考步骤的计划
        """
        if not self.llm_router or not self.llm_router.is_available():
            # 基于理解结果生成计划
            if understanding.get("needs_realtime_info", False):
                return {
                    "steps": ["分析问题", "搜索相关信息", "验证信息准确性", "生成答案"],
                    "strategy": "搜索后回答"
                }
            else:
                return {
                    "steps": ["分析问题", "提供答案"],
                    "strategy": "直接回答"
                }
        
        prompt = f"""
基于以下问题理解结果，制定一个思考计划：

理解结果：{understanding}
用户问题：{message}

计划应包括：
1. steps: 思考步骤列表
2. strategy: 总体策略

请只返回JSON，不要包含其他内容。
"""
        
        try:
            response = await self.llm_router.simple_chat(prompt)
            # 检查响应是否为错误信息
            if "GLM 调用失败" in response or "模型服务暂时不可用" in response or "请求过于频繁" in response:
                logger.warning("LLM API 返回错误信息，使用备用逻辑")
                # 基于理解结果生成计划
                if understanding.get("needs_realtime_info", False):
                    return {
                        "steps": ["分析问题", "搜索相关信息", "验证信息准确性", "生成答案"],
                        "strategy": "搜索后回答"
                    }
                else:
                    return {
                        "steps": ["分析问题", "提供答案"],
                        "strategy": "直接回答"
                    }
            import json
            # 尝试解析JSON
            result = json.loads(response)
            # 验证结果格式
            if isinstance(result, dict) and all(key in result for key in ["steps", "strategy"]):
                return result
            else:
                raise ValueError("Invalid JSON format")
        except Exception as e:
            logger.error("制定计划失败: %s", e)
            # 基于理解结果生成计划
            if understanding.get("needs_realtime_info", False):
                return {
                    "steps": ["分析问题", "搜索相关信息", "验证信息准确性", "生成答案"],
                    "strategy": "搜索后回答"
                }
            else:
                return {
                    "steps": ["分析问题", "提供答案"],
                    "strategy": "直接回答"
                }
    
    async def _assess_info_needs(self, plan: Dict[str, Any], message: str) -> Dict[str, Any]:
        """评估信息需求
        
        Args:
            plan: 思考计划
            message: 用户消息
            
        Returns:
            包含是否需要搜索、搜索关键词、搜索策略的字典
        """
        if not self.llm_router or not self.llm_router.is_available():
            # 简单规则判断
            realtime_keywords = ["最新", "最近", "今天", "现在", "2026", "2025", "2024", "新闻", "趋势", "最新消息", "天气", "当前", "此刻", "最近的", "最新的"]
            needs_search = any(keyword in message.lower() for keyword in realtime_keywords)
            
            # 提取搜索关键词
            import re
            keywords = []
            # 提取主要关键词
            main_keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', message)
            if main_keywords:
                keywords.append(' '.join(main_keywords[:5]))
            else:
                keywords.append(message[:50])
            
            return {
                "needs_search": needs_search,
                "search_keywords": keywords,
                "search_strategy": "general"
            }
        
        prompt = f"""
评估以下问题是否需要搜索额外信息：

思考计划：{plan}
用户问题：{message}

评估内容包括：
1. needs_search: 是否需要搜索（是/否）
2. search_keywords: 搜索关键词列表
3. search_strategy: 搜索策略（如：general、specific、comprehensive等）

请只返回JSON，不要包含其他内容。
"""
        
        try:
            response = await self.llm_router.simple_chat(prompt)
            # 检查响应是否为错误信息
            if "GLM 调用失败" in response or "模型服务暂时不可用" in response or "请求过于频繁" in response:
                logger.warning("LLM API 返回错误信息，使用备用逻辑")
                # 基于规则的评估
                realtime_keywords = ["最新", "最近", "今天", "现在", "2026", "2025", "2024", "新闻", "趋势", "最新消息", "天气", "当前", "此刻", "最近的", "最新的"]
                needs_search = any(keyword in message.lower() for keyword in realtime_keywords)
                
                # 提取搜索关键词
                import re
                keywords = []
                # 提取主要关键词
                main_keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', message)
                if main_keywords:
                    keywords.append(' '.join(main_keywords[:5]))
                else:
                    keywords.append(message[:50])
                
                return {
                    "needs_search": needs_search,
                    "search_keywords": keywords,
                    "search_strategy": "general"
                }
            import json
            # 尝试解析JSON
            result = json.loads(response)
            # 验证结果格式
            if isinstance(result, dict) and all(key in result for key in ["needs_search", "search_keywords", "search_strategy"]):
                return result
            else:
                raise ValueError("Invalid JSON format")
        except Exception as e:
            logger.error("评估信息需求失败: %s", e)
            # 基于规则的评估
            realtime_keywords = ["最新", "最近", "今天", "现在", "2026", "2025", "2024", "新闻", "趋势", "最新消息", "天气", "当前", "此刻", "最近的", "最新的"]
            needs_search = any(keyword in message.lower() for keyword in realtime_keywords)
            
            # 提取搜索关键词
            import re
            keywords = []
            # 提取主要关键词
            main_keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', message)
            if main_keywords:
                keywords.append(' '.join(main_keywords[:5]))
            else:
                keywords.append(message[:50])
            
            return {
                "needs_search": needs_search,
                "search_keywords": keywords,
                "search_strategy": "general"
            }
    
    async def _execute_search(self, info_needed: Dict[str, Any], message: str) -> List[Dict[str, Any]]:
        """执行搜索
        
        Args:
            info_needed: 信息需求评估结果
            message: 用户消息
            
        Returns:
            搜索结果列表
        """
        if not self.search_engine:
            return []
        
        search_results = []
        keywords = info_needed.get("search_keywords", [])
        
        # 并行执行搜索，提高效率
        search_tasks = []
        for keyword in keywords[:3]:  # 最多搜索3个关键词
            search_tasks.append(self.search_engine.search(keyword))
        
        # 等待所有搜索任务完成
        if search_tasks:
            results_list = await asyncio.gather(*search_tasks, return_exceptions=True)
            for results in results_list:
                if isinstance(results, list):
                    search_results.extend(results)
                else:
                    logger.error("搜索任务失败: %s", results)
        
        # 去重和排序
        unique_results = []
        seen_urls = set()
        for result in search_results:
            url = result.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        # 按综合分数排序（相关性、质量、权威性、时效性）
        unique_results.sort(key=lambda x: self._calculate_combined_score(x, message), reverse=True)
        
        return unique_results[:10]  # 返回前10个结果，提供更多信息
    
    def _is_simple_question(self, message: str) -> bool:
        """判断是否为简单问题
        
        Args:
            message: 用户消息
            
        Returns:
            是否为简单问题
        """
        # 检查是否包含实时关键词，如果包含则不视为简单问题
        realtime_keywords = ["最新", "最近", "今天", "现在", "2026", "2025", "2024", "新闻", "趋势", "最新消息", "天气", "当前", "此刻", "最近的", "最新的"]
        message_lower = message.lower()
        if any(keyword in message_lower for keyword in realtime_keywords):
            return False
        
        # 简单问题模式
        simple_patterns = [
            r'^你好$',
            r'^hi$',
            r'^hello$',
            r'^在吗$',
            r'^你是谁$',
            r'^你叫什么名字$',
            r'^现在几点了$',
            r'^帮我个忙$',
            r'^谢谢$',
            r'^再见$',
            r'^早上好$',
            r'^下午好$',
            r'^晚上好$',
            r'^晚安$',
            r'^是的$',
            r'^好的$',
            r'^可以$',
            r'^不行$',
            r'^没问题$'
        ]
        
        import re
        for pattern in simple_patterns:
            if re.match(pattern, message.strip()):
                return True
        
        # 长度判断
        if len(message) < 8:
            return True
        
        # 检查是否为命令式问题
        command_patterns = [
            r'^帮我.*$',
            r'^请.*$',
            r'^能否.*$',
            r'^是否.*$',
            r'^可不可以.*$'
        ]
        for pattern in command_patterns:
            if re.match(pattern, message.strip()):
                return False
        
        return False
    
    async def _quick_answer(self, message: str) -> str:
        """快速回答简单问题
        
        Args:
            message: 用户消息
            
        Returns:
            快速回答
        """
        message_lower = message.lower().strip()
        
        # 预设回答
        quick_answers = {
            '你好': '你好！我是小龙虾AI助手，有什么可以帮你的吗？',
            'hi': 'Hello! I\'m Xiaolongxia AI assistant. How can I help you?',
            'hello': 'Hello! I\'m Xiaolongxia AI assistant. How can I help you?',
            '在吗': '在呢！有什么可以帮你的吗？',
            '你是谁': '我是小龙虾AI助手，一个智能对话系统。',
            '你叫什么名字': '我叫小龙虾，是你的智能助手。',
            '今天天气怎么样': '抱歉，我需要实时天气信息才能回答这个问题。',
            '现在几点了': '抱歉，我无法获取当前时间信息。',
            '帮我个忙': '当然可以！请问你需要什么帮助？',
            '谢谢': '不客气！有什么其他问题随时问我。',
            '再见': '再见！祝你有个愉快的一天。'
        }
        
        for key, answer in quick_answers.items():
            if key in message_lower:
                return answer
        
        # 默认回答
        return '你好！有什么可以帮你的吗？'
    
    def _fuse_information(self, search_results: List[Dict[str, Any]], message: str) -> Dict[str, Any]:
        """多源信息融合
        
        Args:
            search_results: 搜索结果列表
            message: 用户消息
            
        Returns:
            融合后的信息
        """
        if not search_results:
            return {"fused_content": "", "sources": []}
        
        # 提取关键信息
        key_points = []
        sources = []
        
        for result in search_results[:10]:  # 处理前10个结果，获取更多信息
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            url = result.get("url", "")
            
            # 提取关键句
            import re
            sentences = re.split(r'[。！？.!?]', snippet)
            key_sentences = [s for s in sentences if s.strip() and len(s) > 10]
            
            if key_sentences:
                key_points.extend(key_sentences[:3])  # 每个结果取前3个关键句
            
            sources.append({
                "title": title,
                "url": url,
                "score": result.get("quality_score", 0.5),
                "relevance_score": result.get("relevance_score", 0.5),
                "authority_score": result.get("authority_score", 0.5),
                "date": result.get("date", "")
            })
        
        # 去重关键信息
        unique_key_points = []
        seen = set()
        for point in key_points:
            point_lower = point.lower()
            if point_lower not in seen:
                seen.add(point_lower)
                unique_key_points.append(point)
        
        # 按综合分数排序来源
        sources.sort(key=lambda x: (x.get("score", 0) + x.get("relevance_score", 0) + x.get("authority_score", 0)) / 3, reverse=True)
        
        # 融合内容
        fused_content = " ".join(unique_key_points[:15])  # 最多15个关键句
        
        # 生成摘要
        summary = self._generate_summary(unique_key_points, message)
        
        # 按主题分组关键信息
        topic_groups = self._group_key_points_by_topic(unique_key_points, message)
        
        return {
            "fused_content": fused_content,
            "summary": summary,
            "sources": sources[:5],  # 返回前5个来源
            "key_points": unique_key_points[:10],  # 返回前10个关键信息
            "topic_groups": topic_groups,  # 按主题分组的关键信息
            "source_count": len(search_results),  # 信息来源数量
            "unique_key_points_count": len(unique_key_points)  # 唯一关键信息数量
        }
    
    def _group_key_points_by_topic(self, key_points: List[str], message: str) -> Dict[str, List[str]]:
        """按主题分组关键信息
        
        Args:
            key_points: 关键信息列表
            message: 用户消息
            
        Returns:
            按主题分组的关键信息
        """
        if not key_points:
            return {}
        
        # 提取用户问题的主要关键词
        import re
        message_words = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', message.lower()))
        
        # 简单的主题分组
        topic_groups = {}
        
        for point in key_points:
            # 提取关键点的关键词
            point_words = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', point.lower()))
            
            # 计算与用户问题的相关性
            common_words = message_words & point_words
            
            if common_words:
                # 以第一个共同词作为主题
                topic = next(iter(common_words))
            else:
                # 以关键点的第一个词作为主题
                point_tokens = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', point)
                topic = point_tokens[0] if point_tokens else "其他"
            
            # 分组
            if topic not in topic_groups:
                topic_groups[topic] = []
            topic_groups[topic].append(point)
        
        # 限制每个主题的关键点数量
        for topic in topic_groups:
            topic_groups[topic] = topic_groups[topic][:5]
        
        return topic_groups
    
    def _generate_summary(self, key_points: List[str], message: str) -> str:
        """生成摘要
        
        Args:
            key_points: 关键信息列表
            message: 用户消息
            
        Returns:
            摘要
        """
        if not key_points:
            return ""
        
        # 简单的摘要生成逻辑
        # 提取与用户问题最相关的关键信息
        import re
        message_words = re.findall(r'\w+', message.lower())
        
        # 计算每个关键信息与用户问题的相关性
        relevant_points = []
        for point in key_points:
            point_words = re.findall(r'\w+', point.lower())
            common_words = set(message_words) & set(point_words)
            if common_words:
                relevant_points.append((len(common_words), point))
        
        # 按相关性排序
        relevant_points.sort(reverse=True)
        
        # 取前3个最相关的点作为摘要
        summary_points = [point for _, point in relevant_points[:3]]
        
        if summary_points:
            return " ".join(summary_points)
        else:
            # 如果没有相关点，取前3个关键信息
            return " ".join(key_points[:3])
    
    def _calculate_relevance(self, result: Dict[str, Any], message: str) -> float:
        """计算搜索结果与问题的相关性
        
        Args:
            result: 搜索结果
            message: 用户消息
            
        Returns:
            相关性得分（0-1）
        """
        score = 0.0
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()
        message_lower = message.lower()
        
        # 标题匹配
        for word in message_lower.split():
            if word in title:
                score += 0.2
        
        # 摘要匹配
        for word in message_lower.split():
            if word in snippet:
                score += 0.1
        
        # 关键词密度
        title_words = title.split()
        snippet_words = snippet.split()
        message_words = message_lower.split()
        
        # 标题关键词密度
        title_match_count = sum(1 for word in message_words if word in title_words)
        if title_words:
            score += (title_match_count / len(title_words)) * 0.3
        
        # 摘要关键词密度
        snippet_match_count = sum(1 for word in message_words if word in snippet_words)
        if snippet_words:
            score += (snippet_match_count / len(snippet_words)) * 0.2
        
        return min(score, 1.0)
    
    def _calculate_combined_score(self, result: Dict[str, Any], message: str) -> float:
        """计算搜索结果的综合分数
        
        Args:
            result: 搜索结果
            message: 用户消息
            
        Returns:
            综合得分（0-1）
        """
        # 计算相关性分数
        relevance_score = self._calculate_relevance(result, message)
        
        # 计算质量分数
        quality_score = result.get("quality_score", 0.5)
        
        # 计算权威性分数
        authority_score = result.get("authority_score", 0.5)
        
        # 计算时效性分数
        recency_score = self._calculate_recency_score(result.get("date", ""))
        
        # 权重
        weights = {
            "relevance": 0.4,  # 相关性权重
            "quality": 0.2,     # 质量权重
            "authority": 0.2,   # 权威性权重
            "recency": 0.2      # 时效性权重
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
        """计算搜索结果的时效性分数
        
        Args:
            date_str: 日期字符串
            
        Returns:
            时效性得分（0-1）
        """
        try:
            if not date_str:
                return 0.5
            
            # 解析日期
            from datetime import datetime
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
    
    async def _validate_and_reflect(self, plan: Dict[str, Any], search_results: List[Dict[str, Any]], message: str) -> Dict[str, Any]:
        """执行验证和自我反思
        
        Args:
            plan: 思考计划
            search_results: 搜索结果
            message: 用户消息
            
        Returns:
            验证和反思结果
        """
        if not self.llm_router or not self.llm_router.is_available():
            # 基于规则的验证
            return self._rule_based_validation(plan, search_results, message)
        
        search_summaries = []
        for i, result in enumerate(search_results[:5]):  # 使用前5个搜索结果
            search_summaries.append(f"[{i+1}] {result.get('title', '')}: {result.get('snippet', '')[:150]}...")
        search_context = "\n".join(search_summaries)
        
        prompt = f"""
        请验证以下信息是否足够回答用户问题，并进行自我反思：

        思考计划：{plan}
        搜索结果：
        {search_context}
        用户问题：{message}

        验证内容包括：
        1. validation_passed: 验证是否通过（是/否）
        2. issues: 存在的问题列表
        3. confidence: 回答置信度（0-1）
        4. reflection: 自我反思内容，包括可能的错误和改进方向
        5. additional_search: 是否需要额外搜索（是/否）
        6. missing_info: 缺少的信息
        7. improvement_suggestions: 改进建议
        8. key_evidence: 关键证据

        请只返回JSON，不要包含其他内容。
        """
        
        try:
            response = await self.llm_router.simple_chat(prompt)
            import json
            # 尝试解析JSON
            result = json.loads(response)
            # 验证结果格式
            if isinstance(result, dict) and all(key in result for key in ["validation_passed", "issues", "confidence"]):
                # 确保所有字段都存在
                result.setdefault("reflection", "")
                result.setdefault("additional_search", False)
                result.setdefault("missing_info", [])
                result.setdefault("improvement_suggestions", [])
                result.setdefault("key_evidence", [])
                return result
            else:
                raise ValueError("Invalid JSON format")
        except Exception as e:
            logger.error("验证和反思失败: %s", e)
            # 基于规则的验证
            return self._rule_based_validation(plan, search_results, message)
    
    def _rule_based_validation(self, plan: Dict[str, Any], search_results: List[Dict[str, Any]], message: str) -> Dict[str, Any]:
        """基于规则的验证
        
        Args:
            plan: 思考计划
            search_results: 搜索结果
            message: 用户消息
            
        Returns:
            验证结果
        """
        issues = []
        missing_info = []
        improvement_suggestions = []
        key_evidence = []
        confidence = 0.8
        
        # 检查搜索结果数量
        if not search_results:
            issues.append("没有找到相关信息")
            missing_info.append("缺少相关搜索结果")
            confidence = 0.3
            improvement_suggestions.append("尝试使用不同的搜索关键词")
        elif len(search_results) < 3:
            issues.append("搜索结果数量较少")
            missing_info.append("需要更多相关信息")
            confidence = 0.6
            improvement_suggestions.append("扩展搜索关键词或使用更具体的查询")
        
        # 检查搜索结果质量
        low_quality_results = [r for r in search_results if len(r.get('snippet', '')) < 50]
        if low_quality_results:
            issues.append("部分搜索结果质量较低")
            missing_info.append("需要更详细的信息")
            confidence -= 0.1
            improvement_suggestions.append("优先使用质量较高的搜索结果")
        
        # 检查搜索结果相关性
        import re
        message_words = re.findall(r'[\w\u4e00-\u9fa5]+', message.lower())
        low_relevance_results = []
        high_relevance_results = []
        
        for result in search_results:
            snippet = result.get('snippet', '').lower()
            title = result.get('title', '').lower()
            content = f"{title} {snippet}"
            matched_words = set(message_words) & set(re.findall(r'[\w\u4e00-\u9fa5]+', content))
            if len(matched_words) < len(message_words) * 0.3:
                low_relevance_results.append(result)
            else:
                high_relevance_results.append(result)
                # 提取关键证据
                if len(key_evidence) < 3:
                    key_evidence.append(f"[{result.get('title', '')}] {result.get('snippet', '')[:100]}...")
        
        if low_relevance_results:
            issues.append("部分搜索结果与问题相关性较低")
            missing_info.append("需要更相关的信息")
            confidence -= 0.1
            improvement_suggestions.append("优化搜索关键词以提高相关性")
        
        # 检查搜索结果时效性
        realtime_keywords = ["最新", "最近", "今天", "现在", "2026", "2025", "2024", "新闻", "趋势", "最新消息", "天气", "当前", "此刻", "最近的", "最新的"]
        message_lower = message.lower()
        needs_realtime_info = any(keyword in message_lower for keyword in realtime_keywords)
        
        if needs_realtime_info:
            # 检查结果是否包含日期
            dated_results = [r for r in search_results if r.get("date")]
            if not dated_results:
                issues.append("需要实时信息，但搜索结果中没有日期信息")
                missing_info.append("需要包含日期的最新信息")
                confidence -= 0.2
                improvement_suggestions.append("添加时间限定词到搜索查询")
            else:
                # 检查日期是否足够新
                from datetime import datetime, timedelta
                recent_results = []
                for result in dated_results:
                    try:
                        date = datetime.fromisoformat(result.get("date"))
                        if datetime.now() - date < timedelta(days=30):
                            recent_results.append(result)
                    except Exception:
                        pass
                if not recent_results:
                    issues.append("搜索结果日期过于久远")
                    missing_info.append("需要更近期的信息")
                    confidence -= 0.1
                    improvement_suggestions.append("指定更具体的时间范围")
        
        # 检查信息多样性
        if len(search_results) > 0:
            sources = set()
            for result in search_results:
                source = result.get("source", "") or result.get("url", "")
                if source:
                    sources.add(source)
            if len(sources) < 2:
                issues.append("信息来源过于单一")
                missing_info.append("需要更多不同来源的信息")
                confidence -= 0.1
                improvement_suggestions.append("尝试从不同来源获取信息")
        
        # 确保置信度在合理范围内
        confidence = max(0.3, min(confidence, 1.0))
        
        return {
            "validation_passed": len(issues) == 0,
            "issues": issues,
            "confidence": confidence,
            "reflection": "基于规则的验证完成，可能需要更多信息",
            "additional_search": len(issues) > 0,
            "missing_info": missing_info,
            "improvement_suggestions": improvement_suggestions,
            "key_evidence": key_evidence
        }
    
    async def _generate_final_answer(self, plan: Dict[str, Any], search_results: List[Dict[str, Any]], 
                                    validation: Dict[str, Any], message: str, fused_info: Dict[str, Any] = None) -> str:
        """生成最终答案
        
        Args:
            plan: 思考计划
            search_results: 搜索结果
            validation: 验证和反思结果
            message: 用户消息
            fused_info: 融合后的信息
            
        Returns:
            最终答案
        """
        if not self.llm_router or not self.llm_router.is_available():
            # 基于融合信息的备用回答
            if fused_info and fused_info.get('fused_content'):
                return f"根据搜索结果，{fused_info.get('fused_content')[:200]}..."
            elif search_results:
                # 基于搜索结果生成简单回答
                summary = ""
                for i, result in enumerate(search_results[:2]):
                    summary += f"{result.get('title', '')}: {result.get('snippet', '')[:100]}...\n"
                return f"根据搜索结果：\n{summary}"
            else:
                return "我需要更多信息来回答这个问题。"
        
        # 构建上下文
        search_summaries = []
        for i, result in enumerate(search_results[:3]):
            search_summaries.append(f"[{i+1}] {result.get('title', '')}: {result.get('snippet', '')}")
        search_context = "\n".join(search_summaries)
        
        # 融合信息
        fused_context = ""
        if fused_info:
            fused_context = f"\n融合信息：\n{fused_info.get('fused_content', '')}"
            if fused_info.get('key_points'):
                key_points_str = "\n".join([f"- {point}" for point in fused_info.get('key_points', [])])
                fused_context += f"\n\n关键信息：\n{key_points_str}"
        
        prompt = f"""
        基于以下信息，生成一个全面、准确的回答：

        思考计划：{plan}
        搜索结果：
        {search_context}
        {fused_context}
        验证结果：{validation}
        用户问题：{message}

        回答要求：
        1. 直接回答用户问题，不要有引言或开场白
        2. 结合搜索结果和融合信息，确保信息准确全面
        3. 结构清晰，逻辑连贯，使用列表格式呈现多个要点
        4. 如果信息不足，明确说明缺少的信息
        5. 对于有争议的信息，保持中立
        6. 回答要简洁明了，避免冗长

        请只返回回答内容，不要包含其他内容。
        """
        
        try:
            response = await self.llm_router.simple_chat(prompt)
            return response
        except Exception as e:
            logger.error("生成最终答案失败: %s", e)
            # 基于融合信息的备用回答
            if fused_info and fused_info.get('fused_content'):
                return f"根据搜索结果，{fused_info.get('fused_content')[:200]}..."
            elif search_results:
                # 基于搜索结果生成简单回答
                summary = ""
                for i, result in enumerate(search_results[:2]):
                    summary += f"{result.get('title', '')}: {result.get('snippet', '')[:100]}...\n"
                return f"根据搜索结果：\n{summary}"
            else:
                return "抱歉，我无法生成回答。"


# 全局深度思考引擎实例
reasoning_engine = None

def get_reasoning_engine() -> ReasoningEngine:
    """获取深度思考引擎实例
    
    Returns:
        ReasoningEngine实例
    """
    global reasoning_engine
    if reasoning_engine is None:
        reasoning_engine = ReasoningEngine()
    return reasoning_engine
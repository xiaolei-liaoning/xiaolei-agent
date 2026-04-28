"""对话历史压缩器 - 多层摘要与上下文检索

工业级对话压缩系统：
- 多层摘要生成（短期/中期/长期）
- 智能语义检索
- 上下文增强RAG查询
- 自动摘要更新和清理
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── 路径常量 ───────────────────────────────────────────────────────────────
SUMMARY_DIR = Path(os.path.expanduser("~/.小雷版小龙虾/conversation_summaries"))
SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

# ─── 压缩配置 ───────────────────────────────────────────────────────────────
SHORT_TERM_ROUNDS = 10      # 短期摘要：最近10轮
MEDIUM_TERM_ROUNDS = 50     # 中期摘要：最近50轮
LONG_TERM_DAYS = 30         # 长期摘要：最近30天

# ─── 摘要级别 ───────────────────────────────────────────────────────────────
SUMMARY_LEVELS = {
    'short': {
        'description': '短期摘要',
        'rounds': SHORT_TERM_ROUNDS,
        'detail_level': 'detailed'
    },
    'medium': {
        'description': '中期摘要',
        'rounds': MEDIUM_TERM_ROUNDS,
        'detail_level': 'key_points'
    },
    'long': {
        'description': '长期摘要',
        'days': LONG_TERM_DAYS,
        'detail_level': 'topics'
    }
}


class ConversationCompressor:
    """对话历史压缩器
    
    功能：
    - 多层摘要生成（短期/中期/长期）
    - 智能语义检索
    - 上下文增强RAG查询
    - 自动摘要更新和清理
    """
    
    def __init__(self) -> None:
        self._vector_store = None
        self._llm_client = None
        self._summary_cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        
        self._init_vector_store()
        self._init_llm_client()
    
    def _init_vector_store(self) -> None:
        """初始化向量存储"""
        try:
            from core.vector_memory import VectorMemoryStore
            self._vector_store = VectorMemoryStore()
            logger.info("向量存储初始化成功")
        except Exception as exc:
            logger.error("向量存储初始化失败: %s", exc)
            self._vector_store = None
    
    def _init_llm_client(self) -> None:
        """初始化LLM客户端"""
        try:
            import zhipuai
            api_key = os.getenv('ZHIPUAI_API_KEY')
            if api_key:
                self._llm_client = zhipuai.ZhipuAI(api_key=api_key)
                logger.info("LLM客户端初始化成功")
            else:
                logger.warning("ZHIPUAI_API_KEY未设置，摘要功能受限")
        except ImportError:
            logger.warning("zhipuai未安装，摘要功能受限")
        except Exception as exc:
            logger.error("LLM客户端初始化失败: %s", exc)
    
    def compress_history(
        self,
        conversation_history: List[Dict[str, Any]],
        user_id: int,
        compression_level: str = 'auto'
    ) -> Dict[str, Any]:
        """压缩对话历史
        
        Args:
            conversation_history: 对话历史列表
            user_id: 用户ID
            compression_level: 压缩级别 (short/medium/long/auto)
        
        Returns:
            压缩结果
        """
        if not conversation_history:
            return {
                'success': False,
                'error': '对话历史为空'
            }
        
        start_time = time.perf_counter()
        
        try:
            # 自动确定压缩级别
            if compression_level == 'auto':
                compression_level = self._determine_compression_level(conversation_history)
            
            # 生成摘要
            summary = self._generate_summary(
                conversation_history,
                user_id,
                compression_level
            )
            
            # 存储摘要
            self._store_summary(summary, user_id, compression_level)
            
            elapsed = time.perf_counter() - start_time
            logger.info("对话压缩完成 [%s], 耗时: %.3fs", compression_level, elapsed)
            
            return {
                'success': True,
                'action': 'compress_history',
                'compression_level': compression_level,
                'summary': summary,
                'original_rounds': len(conversation_history),
                'compressed_ratio': self._calculate_compression_ratio(conversation_history, summary),
                'elapsed': round(elapsed, 3),
                'reply': f"✅ 对话已压缩为{compression_level}摘要，压缩率: {self._calculate_compression_ratio(conversation_history, summary):.1%}"
            }
            
        except Exception as exc:
            logger.error("对话压缩失败: %s", exc)
            return {
                'success': False,
                'error': f'对话压缩失败: {exc}'
            }
    
    def get_context(
        self,
        query: str,
        user_id: int,
        max_results: int = 5,
        time_range: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取相关上下文
        
        Args:
            query: 查询文本
            user_id: 用户ID
            max_results: 最大返回结果数
            time_range: 时间范围 (short/medium/long)
        
        Returns:
            相关上下文
        """
        if not query or not query.strip():
            return {
                'success': False,
                'error': '查询文本为空'
            }
        
        start_time = time.perf_counter()
        
        try:
            # 检查缓存
            cache_key = f"context_{user_id}_{query}_{time_range}_{max_results}"
            if cache_key in self._summary_cache:
                cached = self._summary_cache[cache_key]
                if time.time() - cached.get('timestamp', 0) < 300:  # 5分钟缓存
                    return cached['result']
            
            # 检索相关摘要
            contexts = self._search_relevant_contexts(
                query,
                user_id,
                max_results,
                time_range
            )
            
            # 格式化结果
            result = {
                'success': True,
                'action': 'get_context',
                'query': query,
                'contexts': contexts,
                'count': len(contexts),
                'reply': self._format_context_reply(contexts)
            }
            
            # 缓存结果
            with self._cache_lock:
                self._summary_cache[cache_key] = {
                    'result': result,
                    'timestamp': time.time()
                }
            
            elapsed = time.perf_counter() - start_time
            logger.info("上下文检索完成, 耗时: %.3fs", elapsed)
            
            return result
            
        except Exception as exc:
            logger.error("上下文检索失败: %s", exc)
            return {
                'success': False,
                'error': f'上下文检索失败: {exc}'
            }
    
    def search_history(
        self,
        query: str,
        user_id: int,
        max_results: int = 10,
        date_range: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """搜索历史对话
        
        Args:
            query: 查询文本
            user_id: 用户ID
            max_results: 最大返回结果数
            date_range: 日期范围 (start_date, end_date)
        
        Returns:
            搜索结果
        """
        if not query or not query.strip():
            return {
                'success': False,
                'error': '查询文本为空'
            }
        
        start_time = time.perf_counter()
        
        try:
            # 从向量库检索
            memories = self._vector_store.search_memories(
                query,
                user_id,
                top_k=max_results
            )
            
            # 过滤对话类记忆
            conversation_memories = [
                m for m in memories
                if m.get('metadata', {}).get('category') == 'conversation'
            ]
            
            # 日期过滤
            if date_range:
                start_date, end_date = date_range
                conversation_memories = [
                    m for m in conversation_memories
                    if self._is_in_date_range(
                        m.get('metadata', {}).get('timestamp', ''),
                        start_date,
                        end_date
                    )
                ]
            
            elapsed = time.perf_counter() - start_time
            
            return {
                'success': True,
                'action': 'search_history',
                'query': query,
                'results': conversation_memories,
                'count': len(conversation_memories),
                'elapsed': round(elapsed, 3),
                'reply': self._format_search_reply(conversation_memories)
            }
            
        except Exception as exc:
            logger.error("历史对话搜索失败: %s", exc)
            return {
                'success': False,
                'error': f'历史对话搜索失败: {exc}'
            }
    
    def _determine_compression_level(
        self,
        conversation_history: List[Dict[str, Any]]
    ) -> str:
        """自动确定压缩级别
        
        Args:
            conversation_history: 对话历史
        
        Returns:
            压缩级别
        """
        rounds = len(conversation_history)
        
        if rounds <= SHORT_TERM_ROUNDS:
            return 'short'
        elif rounds <= MEDIUM_TERM_ROUNDS:
            return 'medium'
        else:
            return 'long'
    
    def _generate_summary(
        self,
        conversation_history: List[Dict[str, Any]],
        user_id: int,
        compression_level: str
    ) -> Dict[str, Any]:
        """生成摘要
        
        Args:
            conversation_history: 对话历史
            user_id: 用户ID
            compression_level: 压缩级别
        
        Returns:
            摘要内容
        """
        level_config = SUMMARY_LEVELS.get(compression_level, SUMMARY_LEVELS['short'])
        
        # 根据级别选择对话轮数
        if compression_level == 'long':
            # 长期摘要：按日期过滤
            cutoff_date = datetime.now() - timedelta(days=LONG_TERM_DAYS)
            filtered_history = [
                conv for conv in conversation_history
                if self._parse_timestamp(conv.get('timestamp', '')) >= cutoff_date
            ]
        else:
            # 短期/中期摘要：按轮数过滤
            rounds = level_config.get('rounds', SHORT_TERM_ROUNDS)
            filtered_history = conversation_history[-rounds:]
        
        # 格式化对话文本
        conversation_text = self._format_conversation(filtered_history)
        
        # 使用LLM生成摘要
        summary_text = self._llm_generate_summary(
            conversation_text,
            compression_level,
            level_config.get('detail_level', 'detailed')
        )
        
        # 提取关键信息
        key_points = self._extract_key_points(filtered_history)
        
        # 识别主题
        topics = self._identify_topics(filtered_history)
        
        return {
            'level': compression_level,
            'timestamp': datetime.now().isoformat(),
            'rounds': len(filtered_history),
            'summary_text': summary_text,
            'key_points': key_points,
            'topics': topics,
            'metadata': {
                'user_id': str(user_id),
                'compression_level': compression_level,
                'detail_level': level_config.get('detail_level'),
                'original_rounds': len(conversation_history)
            }
        }
    
    def _store_summary(
        self,
        summary: Dict[str, Any],
        user_id: int,
        compression_level: str
    ) -> None:
        """存储摘要
        
        Args:
            summary: 摘要内容
            user_id: 用户ID
            compression_level: 压缩级别
        """
        # 存储到向量库
        if self._vector_store:
            summary_text = summary.get('summary_text', '')
            if summary_text:
                self._vector_store.add_memory(
                    user_id=user_id,
                    content=summary_text,
                    category='conversation',
                    metadata={
                        'compression_level': compression_level,
                        'topics': summary.get('topics', []),
                        'key_points_count': len(summary.get('key_points', [])),
                        'rounds': summary.get('rounds', 0)
                    }
                )
        
        # 存储到文件
        summary_file = SUMMARY_DIR / f"summary_{user_id}_{compression_level}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.debug("摘要已保存: %s", summary_file)
        except Exception as exc:
            logger.warning("摘要文件保存失败: %s", exc)
    
    def _search_relevant_contexts(
        self,
        query: str,
        user_id: int,
        max_results: int,
        time_range: Optional[str]
    ) -> List[Dict[str, Any]]:
        """检索相关上下文
        
        Args:
            query: 查询文本
            user_id: 用户ID
            max_results: 最大结果数
            time_range: 时间范围
        
        Returns:
            相关上下文列表
        """
        if not self._vector_store:
            return []
        
        # 检索对话类记忆
        memories = self._vector_store.search_memories(
            query,
            user_id,
            top_k=max_results * 2  # 获取更多结果用于过滤
        )
        
        # 过滤对话类记忆
        conversation_memories = [
            m for m in memories
            if m.get('metadata', {}).get('category') == 'conversation'
        ]
        
        # 时间范围过滤
        if time_range:
            cutoff_date = self._get_cutoff_date(time_range)
            conversation_memories = [
                m for m in conversation_memories
                if self._parse_timestamp(
                    m.get('metadata', {}).get('timestamp', '')
                ) >= cutoff_date
            ]
        
        return conversation_memories[:max_results]
    
    def _llm_generate_summary(
        self,
        conversation_text: str,
        compression_level: str,
        detail_level: str
    ) -> str:
        """使用LLM生成摘要
        
        Args:
            conversation_text: 对话文本
            compression_level: 压缩级别
            detail_level: 详细程度
        
        Returns:
            摘要文本
        """
        if not self._llm_client:
            return self._fallback_summary(conversation_text, compression_level)
        
        try:
            prompt = self._build_summary_prompt(conversation_text, compression_level, detail_level)
            
            response = self._llm_client.chat.completions.create(
                model="glm-4",
                messages=[
                    {"role": "system", "content": "你是一个专业的对话摘要助手，能够准确提取对话的核心内容和关键信息。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as exc:
            logger.warning("LLM摘要生成失败，使用备用方案: %s", exc)
            return self._fallback_summary(conversation_text, compression_level)
    
    def _build_summary_prompt(
        self,
        conversation_text: str,
        compression_level: str,
        detail_level: str
    ) -> str:
        """构建摘要提示词
        
        Args:
            conversation_text: 对话文本
            compression_level: 压缩级别
            detail_level: 详细程度
        
        Returns:
            提示词
        """
        level_descriptions = {
            'short': '最近10轮对话',
            'medium': '最近50轮对话',
            'long': '最近30天的对话'
        }
        
        detail_instructions = {
            'detailed': '请提供详细的摘要，包括每个主要话题的详细讨论内容。',
            'key_points': '请提取关键要点，每个要点用简洁的语言概括。',
            'topics': '请识别并总结主要讨论的主题和趋势。'
        }
        
        prompt = f"""请对以下{level_descriptions.get(compression_level, '对话')}进行摘要：

{conversation_text}

要求：
1. {detail_instructions.get(detail_level, '提供简洁的摘要')}
2. 识别并提取关键信息
3. 保持逻辑清晰，层次分明
4. 用中文回答

摘要："""
        
        return prompt
    
    def _fallback_summary(
        self,
        conversation_text: str,
        compression_level: str
    ) -> str:
        """备用摘要方案（不使用LLM）
        
        Args:
            conversation_text: 对话文本
            compression_level: 压缩级别
        
        Returns:
            摘要文本
        """
        # 简单截取前500字符
        max_length = 500 if compression_level == 'short' else 1000
        if len(conversation_text) > max_length:
            last_period = conversation_text[:max_length].rfind('。')
            if last_period > max_length * 0.5:
                return conversation_text[:last_period + 1]
        return conversation_text[:max_length]
    
    def _format_conversation(
        self,
        conversation_history: List[Dict[str, Any]]
    ) -> str:
        """格式化对话文本
        
        Args:
            conversation_history: 对话历史
        
        Returns:
            格式化的对话文本
        """
        lines = []
        for i, conv in enumerate(conversation_history):
            role = conv.get('role', 'user')
            content = conv.get('content', '')
            lines.append(f"{i+1}. [{role}]: {content}")
        return '\n'.join(lines)
    
    def _extract_key_points(
        self,
        conversation_history: List[Dict[str, Any]]
    ) -> List[str]:
        """提取关键要点
        
        Args:
            conversation_history: 对话历史
        
        Returns:
            关键要点列表
        """
        key_points = []
        
        # 简单策略：提取用户消息中的问句和重要陈述
        for conv in conversation_history:
            if conv.get('role') == 'user':
                content = conv.get('content', '')
                if '?' in content or '！' in content or '。' in content:
                    key_points.append(content[:100])
        
        return key_points[:5]  # 最多5个要点
    
    def _identify_topics(
        self,
        conversation_history: List[Dict[str, Any]]
    ) -> List[str]:
        """识别主题
        
        Args:
            conversation_history: 对话历史
        
        Returns:
            主题列表
        """
        # 简单策略：基于关键词识别主题
        topics = set()
        
        topic_keywords = {
            '数据分析': ['数据', '分析', '统计', '图表'],
            '机器学习': ['机器学习', '预测', '模型', '训练'],
            '翻译': ['翻译', '英文', '中文', '语言'],
            '自动化': ['自动化', '脚本', '任务', '执行'],
            '系统': ['系统', '进程', '内存', 'CPU']
        }
        
        for conv in conversation_history:
            content = conv.get('content', '').lower()
            for topic, keywords in topic_keywords.items():
                if any(kw in content for kw in keywords):
                    topics.add(topic)
        
        return list(topics)
    
    def _calculate_compression_ratio(
        self,
        conversation_history: List[Dict[str, Any]],
        summary: Dict[str, Any]
    ) -> float:
        """计算压缩率
        
        Args:
            conversation_history: 对话历史
            summary: 摘要
        
        Returns:
            压缩率 (0-1)
        """
        original_length = sum(len(conv.get('content', '')) for conv in conversation_history)
        summary_length = len(summary.get('summary_text', ''))
        
        if original_length == 0:
            return 0.0
        
        return 1.0 - (summary_length / original_length)
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """解析时间戳
        
        Args:
            timestamp_str: 时间戳字符串
        
        Returns:
            datetime对象
        """
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            return datetime.min
    
    def _get_cutoff_date(self, time_range: str) -> datetime:
        """获取截止日期
        
        Args:
            time_range: 时间范围
        
        Returns:
            截止日期
        """
        now = datetime.now()
        
        if time_range == 'short':
            return now - timedelta(hours=24)
        elif time_range == 'medium':
            return now - timedelta(days=7)
        elif time_range == 'long':
            return now - timedelta(days=30)
        else:
            return datetime.min
    
    def _is_in_date_range(
        self,
        timestamp_str: str,
        start_date: datetime,
        end_date: datetime
    ) -> bool:
        """检查是否在日期范围内
        
        Args:
            timestamp_str: 时间戳字符串
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            是否在范围内
        """
        try:
            timestamp = self._parse_timestamp(timestamp_str)
            return start_date <= timestamp <= end_date
        except:
            return False
    
    def _format_context_reply(
        self,
        contexts: List[Dict[str, Any]]
    ) -> str:
        """格式化上下文回复
        
        Args:
            contexts: 上下文列表
        
        Returns:
            格式化的回复
        """
        if not contexts:
            return "未找到相关上下文"
        
        reply_lines = [
            f"📚 找到 {len(contexts)} 条相关上下文",
            ""
        ]
        
        for i, ctx in enumerate(contexts, 1):
            content = ctx.get('content', '')[:200]
            metadata = ctx.get('metadata', {})
            level = metadata.get('compression_level', 'unknown')
            distance = ctx.get('distance', 0)
            
            reply_lines.append(f"{i}. [{level}] (相似度: {1-distance:.2f})")
            reply_lines.append(f"   {content}...")
            reply_lines.append("")
        
        return '\n'.join(reply_lines)
    
    def _format_search_reply(
        self,
        results: List[Dict[str, Any]]
    ) -> str:
        """格式化搜索回复
        
        Args:
            results: 搜索结果列表
        
        Returns:
            格式化的回复
        """
        if not results:
            return "未找到相关历史对话"
        
        reply_lines = [
            f"🔍 找到 {len(results)} 条历史对话",
            ""
        ]
        
        for i, result in enumerate(results, 1):
            content = result.get('content', '')[:200]
            metadata = result.get('metadata', {})
            timestamp = metadata.get('timestamp', '')[:10]
            distance = result.get('distance', 0)
            
            reply_lines.append(f"{i}. [{timestamp}] (相似度: {1-distance:.2f})")
            reply_lines.append(f"   {content}...")
            reply_lines.append("")
        
        return '\n'.join(reply_lines)
    
    def cleanup_old_summaries(self, days: int = 30) -> Dict[str, Any]:
        """清理旧摘要
        
        Args:
            days: 保留天数
        
        Returns:
            清理结果
        """
        logger.info("清理旧摘要：保留最近 %d 天", days)
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cleaned = 0
            
            for summary_file in SUMMARY_DIR.glob("summary_*.json"):
                try:
                    file_date = datetime.fromtimestamp(summary_file.stat().st_mtime)
                    if file_date < cutoff_date:
                        summary_file.unlink()
                        cleaned += 1
                except Exception as exc:
                    logger.warning("删除摘要文件失败 %s: %s", summary_file, exc)
                    continue
            
            logger.info("清理完成：删除 %d 个旧摘要文件", cleaned)
            
            return {
                'cleaned': cleaned,
                'remaining': len(list(SUMMARY_DIR.glob("summary_*.json")))
            }
            
        except Exception as exc:
            logger.error("清理旧摘要失败: %s", exc)
            return {
                'cleaned': 0,
                'error': str(exc)
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            统计信息
        """
        summary_files = list(SUMMARY_DIR.glob("summary_*.json"))
        
        return {
            'total_summaries': len(summary_files),
            'vector_store_available': self._vector_store is not None,
            'llm_available': self._llm_client is not None,
            'cache_size': len(self._summary_cache),
            'summary_dir': str(SUMMARY_DIR)
        }


conversation_compressor = ConversationCompressor()
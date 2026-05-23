"""深度思考引擎

基于 Deep Thinking Protocol 框架的智能思考系统，包含以下核心功能：
1. 问题理解 - 理解用户意图和需求
2. 信息收集 - 收集必要的背景信息和知识
3. 方案设计 - 生成和评估多个解决路径
4. 执行验证 - 实施方案并验证结果
5. 反思优化 - 总结经验并持续改进

思考深度级别：
- Level 1: Quick (快速模式，< 5秒)
- Level 2: Standard (标准模式，5-30秒)
- Level 3: Deep (深度模式，> 30秒)
"""
import logging
import asyncio
import hashlib
import math
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import OrderedDict

from core.engine.reasoning_types import (
    ThinkingDepth,
    TaskComplexity,
    ImpactLevel,
    _get_rag_engine,
    _get_short_term_memory,
)

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """基于 Deep Thinking Protocol 的深度思考引擎
    
    核心5阶段框架：
    1. 问题理解 - 理解用户需求和边界
    2. 信息收集 - 收集必要知识和上下文
    3. 方案设计 - 生成多个解决方案并评估
    4. 执行验证 - 实施并验证结果
    5. 反思优化 - 总结经验并改进
    """
    
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
        # 决策复杂度矩阵
        self._complexity_matrix = self._build_complexity_matrix()
        # 质量标准检查器
        self._quality_standards = self._build_quality_standards()
    
    def _build_complexity_matrix(self) -> Dict[str, ThinkingDepth]:
        """构建决策复杂度矩阵
        
        Returns:
            (复杂度, 影响程度) -> 思考深度的映射
        """
        return {
            (TaskComplexity.SIMPLE, ImpactLevel.LOW): ThinkingDepth.QUICK,
            (TaskComplexity.SIMPLE, ImpactLevel.MEDIUM): ThinkingDepth.QUICK,
            (TaskComplexity.SIMPLE, ImpactLevel.HIGH): ThinkingDepth.STANDARD,
            (TaskComplexity.MODERATE, ImpactLevel.LOW): ThinkingDepth.QUICK,
            (TaskComplexity.MODERATE, ImpactLevel.MEDIUM): ThinkingDepth.STANDARD,
            (TaskComplexity.MODERATE, ImpactLevel.HIGH): ThinkingDepth.DEEP,
            (TaskComplexity.COMPLEX, ImpactLevel.LOW): ThinkingDepth.STANDARD,
            (TaskComplexity.COMPLEX, ImpactLevel.MEDIUM): ThinkingDepth.DEEP,
            (TaskComplexity.COMPLEX, ImpactLevel.HIGH): ThinkingDepth.DEEP,
        }
    
    def _build_quality_standards(self) -> Dict[str, Dict[str, Any]]:
        """构建质量标准检查器
        
        Returns:
            质量标准配置
        """
        return {
            "completeness": {
                "description": "完整性：所有子任务都被处理，没有隐含假设",
                "checker": self._check_completeness,
                "min_score": 0.7
            },
            "correctness": {
                "description": "正确性：逻辑一致，信息准确，工具使用正确",
                "checker": self._check_correctness,
                "min_score": 0.7
            },
            "feasibility": {
                "description": "可行性：技术上可实现，在资源约束内",
                "checker": self._check_feasibility,
                "min_score": 0.6
            },
            "efficiency": {
                "description": "效率：思考时间与任务价值成正比",
                "checker": self._check_efficiency,
                "min_score": 0.5
            },
            "explainability": {
                "description": "可解释性：能清楚说明决策理由",
                "checker": self._check_explainability,
                "min_score": 0.6
            }
        }
    
    # ========== 质量标准检查方法 ==========
    def _check_completeness(self, thinking_process: Dict[str, Any], message: str) -> float:
        """检查完整性得分
        
        Args:
            thinking_process: 思考过程
            message: 用户消息
            
        Returns:
            完整性得分 (0-1)
        """
        score = 0.5  # 基础分
        
        # 检查是否有问题理解
        if 'understanding' in thinking_process:
            score += 0.15
        
        # 检查是否有思考计划
        if 'plan' in thinking_process:
            score += 0.15
        
        # 检查是否有验证反思
        if 'validation' in thinking_process:
            score += 0.1
        
        # 检查关键信息提取
        understanding = thinking_process.get('understanding', {})
        if understanding.get('key_information'):
            score += 0.1
        
        return min(score, 1.0)
    
    def _check_correctness(self, thinking_process: Dict[str, Any], message: str) -> float:
        """检查正确性得分
        
        Args:
            thinking_process: 思考过程
            message: 用户消息
            
        Returns:
            正确性得分 (0-1)
        """
        score = 0.5
        
        # 检查验证是否通过
        validation = thinking_process.get('validation', {})
        if validation.get('validation_passed'):
            score += 0.2
        
        # 检查置信度
        confidence = validation.get('confidence', 0.5)
        score += confidence * 0.2
        
        # 检查是否有关键证据
        if validation.get('key_evidence'):
            score += 0.1
        
        return min(score, 1.0)
    
    def _check_feasibility(self, thinking_process: Dict[str, Any], message: str) -> float:
        """检查可行性得分
        
        Args:
            thinking_process: 思考过程
            message: 用户消息
            
        Returns:
            可行性得分 (0-1)
        """
        score = 0.6
        
        # 检查是否有明确的计划
        plan = thinking_process.get('plan', {})
        if plan.get('steps'):
            score += 0.2
        
        # 检查是否有备用方案
        if 'fallback_plans' in thinking_process:
            score += 0.2
        
        return min(score, 1.0)
    
    def _check_efficiency(self, thinking_process: Dict[str, Any], message: str) -> float:
        """检查效率得分
        
        Args:
            thinking_process: 思考过程
            message: 用户消息
            
        Returns:
            效率得分 (0-1)
        """
        score = 0.7
        
        # 检查是否合理使用搜索
        info_needed = thinking_process.get('info_needed', {})
        needs_search = info_needed.get('needs_search', False)
        
        # 简单问题不搜索更高效
        if len(message) < 20 and not needs_search:
            score += 0.3
        elif needs_search:
            # 有搜索需求时执行搜索是合理的
            score += 0.1
        
        return min(score, 1.0)
    
    def _check_explainability(self, thinking_process: Dict[str, Any], message: str) -> float:
        """检查可解释性得分
        
        Args:
            thinking_process: 思考过程
            message: 用户消息
            
        Returns:
            可解释性得分 (0-1)
        """
        score = 0.6
        
        # 检查是否有清晰的思考步骤
        if 'steps' in thinking_process:
            score += 0.2
        
        # 检查是否有反思内容
        validation = thinking_process.get('validation', {})
        if validation.get('reflection'):
            score += 0.2
        
        return min(score, 1.0)
    
    # ========== 思考深度选择方法 ==========
    def determine_thinking_depth(self, message: str) -> ThinkingDepth:
        """根据决策复杂度矩阵确定思考深度
        
        Args:
            message: 用户消息
            
        Returns:
            确定的思考深度级别
        """
        # 分析任务复杂度
        complexity = self._determine_task_complexity(message)
        
        # 分析影响程度
        impact = self._determine_impact_level(message)
        
        # 使用复杂度矩阵确定思考深度
        key = (complexity, impact)
        depth = self._complexity_matrix.get(key, ThinkingDepth.STANDARD)
        
        logger.info(f"思考深度决策：复杂度={complexity.value}, 影响={impact.value} -> 深度={depth.value}")
        return depth
    
    def _determine_task_complexity(self, message: str) -> TaskComplexity:
        """确定任务复杂度级别
        
        Args:
            message: 用户消息
            
        Returns:
            任务复杂度级别
        """
        score = self._calculate_complexity_score(message)
        
        if score < 6:
            return TaskComplexity.SIMPLE
        elif score < 11:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.COMPLEX
    
    def _calculate_complexity_score(self, message: str) -> int:
        """计算任务复杂度分数
        
        Args:
            message: 用户消息
            
        Returns:
            复杂度分数
        """
        score = 0
        message_lower = message.lower()
        
        # 1. 长度分析
        length = len(message)
        if length <= 10:
            score += 0
        elif length <= 20:
            score += 1
        elif length <= 40:
            score += 2
        elif length <= 60:
            score += 4
        elif length <= 100:
            score += 6
        else:
            score += 8
        
        # 2. 多问题检测
        question_count = message.count('？') + message.count('?')
        if question_count == 1:
            score += 2
        elif question_count >= 2:
            score += 5
        
        # 3. 条件句式
        conditional_keywords = ['如果', '假如', '要是', '若', '倘若', '一旦', 'if']
        if any(kw in message_lower for kw in conditional_keywords):
            score += 3
        
        # 4. 比较句式
        comparison_keywords = ['和', '与', '相比', '比较', '哪个', '哪一个', 'vs', 'or']
        if any(kw in message_lower for kw in comparison_keywords):
            score += 3
        
        # 5. 因果句式
        causal_keywords = ['因为', '所以', '因此', '由于', '导致', '造成', 'because', 'so']
        if any(kw in message_lower for kw in causal_keywords):
            score += 3
        
        # 6. 推理句式
        reasoning_keywords = ['为什么', '如何', '怎么', '怎样', '应该', '需要', 'why', 'how']
        reasoning_count = sum(1 for kw in reasoning_keywords if kw in message_lower)
        score += reasoning_count * 2
        
        # 7. 领域检测
        domain_keywords = {
            'technical': ['python', '编程', '代码', '算法', '数据', '软件', '开发', '系统', 'api'],
            'math': ['计算', '公式', '证明', '定理', '方程', '求解', '数学'],
            'science': ['实验', '研究', '发现', '理论', '分析', '原理', '科学'],
            'business': ['市场', '营销', '销售', '利润', '投资', '管理', '商业'],
            'legal': ['法律', '法规', '合同', '权利', '义务', '诉讼', '司法']
        }
        
        domains_found = 0
        for domain, keywords in domain_keywords.items():
            if any(kw.lower() in message_lower for kw in keywords):
                domains_found += 1
        
        score += domains_found * 3
        
        # 8. 实时信息需求
        realtime_keywords = ["最新", "最近", "今天", "现在", "新闻", "趋势", "天气", "当前"]
        if any(kw in message_lower for kw in realtime_keywords):
            score += 3
        
        # 9. 深度思考触发词
        deep_thinking_keywords = ["分析", "研究", "评估", "思考", "总结", "解释", "设计", "规划"]
        if any(kw in message_lower for kw in deep_thinking_keywords):
            score += 4
        
        # 10. 多步任务指示词
        multistep_keywords = ["先", "然后", "接着", "再", "最后", "之后", "并且", "同时"]
        if any(kw in message_lower for kw in multistep_keywords):
            score += 3
        
        return score
    
    def _determine_impact_level(self, message: str) -> ImpactLevel:
        """确定任务影响程度
        
        Args:
            message: 用户消息
            
        Returns:
            影响程度级别
        """
        message_lower = message.lower()
        
        # 高影响关键词
        high_impact_keywords = [
            "重要", "关键", "紧急", "严重", "核心", "必须", "生死攸关",
            "战略", "长期", "重大", "影响深远", "不可逆", "决策"
        ]
        
        # 中影响关键词
        medium_impact_keywords = [
            "建议", "规划", "设计", "分析", "研究", "评估",
            "优化", "改进", "提升", "重要性"
        ]
        
        # 检查高影响
        high_hit = sum(1 for kw in high_impact_keywords if kw in message_lower)
        if high_hit >= 1:
            return ImpactLevel.HIGH
        
        # 检查中影响
        medium_hit = sum(1 for kw in medium_impact_keywords if kw in message_lower)
        if medium_hit >= 2 or len(message) > 50:
            return ImpactLevel.MEDIUM
        
        # 默认低影响
        return ImpactLevel.LOW
    
    def evaluate_quality(self, thinking_process: Dict[str, Any], message: str) -> Dict[str, Any]:
        """评估思考质量
        
        Args:
            thinking_process: 思考过程
            message: 用户消息
            
        Returns:
            质量评估结果
        """
        quality_report = {
            "overall_score": 0.0,
            "standards": {},
            "passed": True,
            "improvement_suggestions": []
        }
        
        total_score = 0.0
        standards_count = 0
        
        for standard_name, standard_config in self._quality_standards.items():
            checker = standard_config["checker"]
            min_score = standard_config["min_score"]
            
            try:
                score = checker(thinking_process, message)
                passed = score >= min_score
                
                quality_report["standards"][standard_name] = {
                    "description": standard_config["description"],
                    "score": score,
                    "min_score": min_score,
                    "passed": passed
                }
                
                total_score += score
                standards_count += 1
                
                if not passed:
                    quality_report["passed"] = False
                    quality_report["improvement_suggestions"].append(
                        f"{standard_name}: 需要改进（当前 {score:.2f}，要求 {min_score:.2f}）"
                    )
            except Exception as e:
                logger.warning(f"质量标准检查失败 {standard_name}: {e}")
        
        if standards_count > 0:
            quality_report["overall_score"] = total_score / standards_count
        
        return quality_report
    
    def _initialize_dependencies(self):
        """初始化依赖"""
        try:
            from .llm_backend import get_llm_router
            self.llm_router = get_llm_router()
            logger.info("LLM 后端初始化成功")
        except Exception as e:
            logger.warning("LLM 后端初始化失败: %s", e)
    
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
        """处理用户消息，执行深度思考（使用新的 Deep Thinking Protocol）
        
        Args:
            message: 用户消息
            user_id: 用户ID
            
        Returns:
            包含思考过程和最终答案的字典
        """
        # 先使用legacy实现（完整版本）
        result = await self.process_legacy(message, user_id)
        
        # 在此基础上，添加新的protocol功能：思考深度和质量评估
        try:
            # 1. 添加思考深度信息
            depth = self.determine_thinking_depth(message)
            result["thinking_depth"] = depth.value
            result["quality_assessment"] = "added"
            
            # 2. 添加质量评估
            thinking_process = result.get("thinking_process", {})
            quality_report = self.evaluate_quality(thinking_process, message)
            result["quality_report"] = quality_report
            
        except Exception as e:
            logger.warning(f"添加protocol增强信息时出错: {e}")
        
        return result
    
    async def process_legacy(self, message: str, user_id: int = 1) -> Dict[str, Any]:
        """处理用户消息，执行深度思考（旧版本，保留用于兼容性）
        
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
        
        # 新增：获取BFS第2层匹配和RAG相似标签
        bfs_layer2 = await self._get_bfs_layer2_matching(message, info_needed.get("search_keywords", []))
        rag_similar = await self._get_rag_similar_tags(info_needed.get("search_keywords", []))
        
        # 6. 执行验证和自我反思
        validation = await self._validate_and_reflect(plan, search_results, message)
        logger.info("验证和反思结果: %s", validation)
        
        # 7. 多源信息融合
        fused_info = self._fuse_information(search_results, message)
        
        # 8. 生成最终答案
        final_answer = await self._generate_final_answer(plan, search_results, validation, message, fused_info)
        
        # 9. ✅ 新增：多轮反思迭代优化
        reflection_iterations = []
        max_reflection_iterations = 3
        
        for iteration in range(max_reflection_iterations):
            # 反思当前答案
            reflection = await self._reflect_on_answer(final_answer, search_results, message)
            reflection_iterations.append(reflection)
            
            confidence = reflection.get("confidence", 0)
            logger.info(f"反思迭代 {iteration+1}: 置信度 {confidence:.2f}")
            
            if confidence >= 0.85:
                logger.info(f"答案置信度达到阈值 {confidence:.2f}，停止迭代")
                break
                
            # 改进答案
            improved_answer = await self._improve_answer(final_answer, reflection, message)
            
            if improved_answer and improved_answer != final_answer:
                final_answer = improved_answer
                logger.info(f"迭代 {iteration+1}：答案已优化")
            else:
                logger.info(f"迭代 {iteration+1}：答案无法进一步优化")
                break
        
        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()
        
        # 构建思考步骤列表（用于前端显示）
        thinking_steps = []
        
        # 步骤1: 理解问题
        thinking_steps.append({
            "title": "理解问题",
            "content": f"问题类型: {understanding.get('question_type', '未知')}\n关键信息: {understanding.get('key_information', '')[:50]}...\n需要实时信息: {'是' if understanding.get('needs_realtime_info') else '否'}"
        })
        
        # 步骤2: 制定计划
        thinking_steps.append({
            "title": "制定计划",
            "content": f"策略: {plan.get('strategy', '未知')}\n步骤: {', '.join(plan.get('steps', []))}"
        })
        
        # 步骤3: 评估信息需求
        thinking_steps.append({
            "title": "评估信息需求",
            "content": f"需要搜索: {'是' if info_needed.get('needs_search') else '否'}\n搜索关键词: {', '.join(info_needed.get('search_keywords', []))[:50]}..."
        })
        
        # 步骤4: BFS上下文匹配（如果有结果）
        if bfs_layer2:
            items = "\n".join([f"  - {item.get('title', '')}" for item in bfs_layer2])
            thinking_steps.append({
                "title": "BFS上下文匹配",
                "content": f"找到 {len(bfs_layer2)} 条相关历史上下文\n{items}"
            })
        
        # 步骤5: RAG相似标签（如果有结果）
        if rag_similar:
            items = "\n".join([f"  - {item.get('title', '')}" for item in rag_similar])
            thinking_steps.append({
                "title": "RAG相似标签检索",
                "content": f"找到 {len(rag_similar)} 条相关知识\n{items}"
            })
        
        # 步骤6: 执行搜索（如果需要）
        if search_results:
            thinking_steps.append({
                "title": "执行搜索",
                "content": f"搜索结果: {len(search_results)} 条\n验证置信度: {validation.get('confidence', 0):.2f}"
            })
        
        # 步骤7: 生成答案
        thinking_steps.append({
            "title": "生成答案",
            "content": "根据分析结果生成最终回答"
        })
        
        result = {
            "final_answer": final_answer,
            "thinking_process": {
                "understanding": understanding,
                "plan": plan,
                "info_needed": info_needed,
                "bfs_layer2": bfs_layer2,
                "rag_similar": rag_similar,
                "search_results": search_results[:3],  # 只返回前3个结果
                "validation": validation,
                "fused_info": fused_info,
                "steps": thinking_steps,
                "summary": f"问题分析完成，共 {len(thinking_steps)} 个思考步骤"
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
你是一个专业的问题分析助手。请分析以下用户问题，并严格按照JSON格式返回结果，不要包含任何其他内容。

用户问题：{message}

分析结果的JSON格式如下：
{{
  "question_type": "问题类型（如：事实查询、观点询问、建议请求、指令执行）",
  "key_information": "关键信息点",
  "needs_realtime_info": false,
  "confidence": 0.8
}}

注意：
- question_type 是字符串
- key_information 是字符串，包含问题中的关键信息
- needs_realtime_info 是布尔值，true 或 false
- confidence 是数字，范围 0-1

请严格返回纯JSON，不要包含代码块标记或其他文字。
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
你是一个专业的计划制定助手。请基于问题理解结果，制定思考计划，并严格按照JSON格式返回。

理解结果：{understanding}
用户问题：{message}

计划的JSON格式如下：
{{
  "steps": ["步骤1", "步骤2", "步骤3"],
  "strategy": "策略名称"
}}

注意：
- steps 是字符串数组
- strategy 是字符串，如"直接回答"或"搜索后回答"

请严格返回纯JSON，不要包含代码块标记或其他文字。
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
你是一个专业的信息需求评估助手。请评估问题是否需要搜索额外信息，并严格按照JSON格式返回。

思考计划：{plan}
用户问题：{message}

评估结果的JSON格式如下：
{{
  "needs_search": false,
  "search_keywords": ["关键词1", "关键词2"],
  "search_strategy": "general"
}}

注意：
- needs_search 是布尔值，true 或 false
- search_keywords 是字符串数组
- search_strategy 是字符串，如"general"、"specific"、"comprehensive"

请严格返回纯JSON，不要包含代码块标记或其他文字。
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
        
        return unique_results[:15]  # 返回前15个结果，包含更多相关信息
    
    async def _get_bfs_layer2_matching(self, message: str, keywords: List[str]) -> List[Dict[str, Any]]:
        """获取BFS上下文树第2层节点并与关键词匹配（增强版：语义相似度）"""
        results = []
        try:
            stm = _get_short_term_memory()
            if stm:
                # 获取深度为3的上下文以获取实际消息内容
                layer_nodes = stm.get_context("1", depth=3)
                if layer_nodes:
                    matched = []
                    for node in layer_nodes:
                        node_content = node.get("content", "").lower()
                        # 检查是否包含实际消息内容（不是纯标签）
                        if len(node_content) > 20:
                            # ✅ 增强：结合关键词匹配和语义相似度
                            keyword_score = sum(1 for kw in keywords if kw.lower() in node_content)
                            
                            # 语义相似度得分（0-1）
                            semantic_score = self._calculate_text_similarity(message, node.get("content", ""))
                            
                            # 综合得分：关键词匹配(0.4) + 语义相似度(0.6)
                            combined_score = keyword_score * 0.4 + semantic_score * 0.6
                            
                            if combined_score >= 0.2:  # 降低阈值，因为语义相似度更敏感
                                matched.append({
                                    "title": f"【上下文】{node.get('role', 'user')}消息",
                                    "content": node.get("content", ""),
                                    "source": "bfs_layer2",
                                    "match_score": combined_score,
                                    "keyword_score": keyword_score,
                                    "semantic_score": semantic_score,
                                    "role": node.get("role", "user")
                                })
                    # 按综合得分排序
                    matched.sort(key=lambda x: x["match_score"], reverse=True)
                    results = matched[:8]  # 增加返回数量，语义匹配更精准
                logger.info(f"BFS第2层匹配完成，找到 {len(results)} 条结果")
        except Exception as e:
            logger.error("BFS第2层匹配失败: %s", e)
        return results
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的语义相似度
        
        使用词重叠和余弦相似度的组合方法
        
        Args:
            text1: 第一段文本
            text2: 第二段文本
            
        Returns:
            相似度得分（0-1）
        """
        if not text1 or not text2:
            return 0.0
            
        # 分词（支持中英文）
        words1 = self._tokenize(text1)
        words2 = self._tokenize(text2)
        
        if not words1 or not words2:
            return 0.0
            
        # 方法1: 词重叠率
        set1 = set(words1)
        set2 = set(words2)
        intersection = set1 & set2
        union = set1 | set2
        
        if not union:
            overlap_score = 0.0
        else:
            overlap_score = len(intersection) / len(union)
        
        # 方法2: 子字符串匹配（处理中文词语）
        substring_score = 0.0
        text1_lower = text1.lower()
        text2_lower = text2.lower()
        
        # 检查是否有2个以上字符的子串匹配
        for word in words1:
            if len(word) >= 2 and word in text2_lower:
                substring_score += 1
        
        substring_score = substring_score / max(len(words1), 1)
        
        # 方法3: 字符级相似度
        char_overlap = sum(1 for c in text1_lower if c in text2_lower)
        char_score = char_overlap / max(len(text1_lower), len(text2_lower), 1)
        
        # 综合得分
        similarity = (overlap_score * 0.4 + substring_score * 0.3 + char_score * 0.3)
        
        return min(similarity, 1.0)
    
    def _tokenize(self, text: str) -> List[str]:
        """文本分词（支持中英文）"""
        import re
        
        # 匹配中文和英文单词
        pattern = re.compile(r'[\u4e00-\u9fa5]+|[a-zA-Z]+')
        tokens = pattern.findall(text.lower())
        
        # 过滤太短的词（中文单字保留，英文至少2个字符）
        result = []
        for token in tokens:
            if len(token) >= 2:
                result.append(token)
            elif len(token) == 1 and '\u4e00' <= token <= '\u9fff':
                # 保留中文单字
                result.append(token)
        
        return result
    
    def _word_frequency(self, words: List[str]) -> Dict[str, int]:
        """计算词频"""
        freq = {}
        for word in words:
            freq[word] = freq.get(word, 0) + 1
        return freq
    
    def _cosine_similarity(self, vec1: Dict[str, int], vec2: Dict[str, int]) -> float:
        """计算余弦相似度"""
        # 获取所有唯一词
        all_words = set(vec1.keys()) | set(vec2.keys())
        
        # 计算点积
        dot_product = sum(vec1.get(word, 0) * vec2.get(word, 0) for word in all_words)
        
        # 计算向量长度
        len1 = math.sqrt(sum(v * v for v in vec1.values()))
        len2 = math.sqrt(sum(v * v for v in vec2.values()))
        
        if len1 == 0 or len2 == 0:
            return 0.0
            
        return dot_product / (len1 * len2)
    
    async def _get_rag_similar_tags(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """获取RAG相似标签内容"""
        results = []
        rag = _get_rag_engine()
        if not rag:
            return results
        
        try:
            for kw in keywords[:3]:
                topic_result = await rag.search_by_topic(topic=kw, user_id=1, max_results=3)
                if topic_result and topic_result.get("knowledge_points"):
                    for point in topic_result["knowledge_points"][:3]:
                        results.append({
                            "title": f"【知识】{point.get('topic', '')}",
                            "content": point.get("content", ""),
                            "source": "rag_similar_tags",
                            "tag": point.get("topic", ""),
                            "relevance": point.get("relevance", 0.8)
                        })
            
            seen = set()
            unique = []
            for r in results:
                title = r["title"]
                if title not in seen:
                    seen.add(title)
                    unique.append(r)
            results = unique[:8]
        except Exception as e:
            logger.error("RAG相似标签搜索失败: %s", e)
        return results
    
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
        
        # ✅ 增强：使用复杂度分析
        complexity = self._analyze_complexity(message)
        return complexity in ["trivial", "simple"]
    
    def _analyze_complexity(self, message: str) -> str:
        """分析问题复杂度
        
        Args:
            message: 用户消息
            
        Returns:
            复杂度级别: trivial/simple/moderate/complex/very_complex
        """
        score = 0
        
        # 1. 长度分析（权重更高）
        length = len(message)
        if length <= 10:
            score += 0
        elif length <= 20:
            score += 1
        elif length <= 40:
            score += 2
        elif length <= 60:
            score += 4
        elif length <= 100:
            score += 6
        else:
            score += 8
        
        # 2. 句式分析
        message_lower = message.lower()
        
        # 多问题检测（权重更高）
        question_count = message.count('？') + message.count('?')
        if question_count == 1:
            score += 2
        elif question_count >= 2:
            score += 5
        
        # 条件句式
        conditional_keywords = ['如果', '假如', '要是', '若', '倘若', '一旦']
        if any(kw in message_lower for kw in conditional_keywords):
            score += 3
        
        # 比较句式
        comparison_keywords = ['和', '与', '相比', '比较', '哪个', '哪一个']
        if any(kw in message_lower for kw in comparison_keywords):
            score += 3
        
        # 因果句式
        causal_keywords = ['因为', '所以', '因此', '由于', '导致', '造成']
        if any(kw in message_lower for kw in causal_keywords):
            score += 3
        
        # 推理句式（权重更高）
        reasoning_keywords = ['为什么', '如何', '怎么', '怎样', '应该', '需要']
        reasoning_count = sum(1 for kw in reasoning_keywords if kw in message_lower)
        score += reasoning_count * 2
        
        # 3. 领域检测（权重更高）
        domain_keywords = {
            '技术': ['Python', '编程', '代码', '算法', '数据', '软件', '开发', '系统'],
            '数学': ['计算', '公式', '证明', '定理', '方程', '求解'],
            '科学': ['实验', '研究', '发现', '理论', '分析', '原理'],
            '商业': ['市场', '营销', '销售', '利润', '投资', '管理'],
            '法律': ['法律', '法规', '合同', '权利', '义务', '诉讼']
        }
        
        domains_found = 0
        for domain, keywords in domain_keywords.items():
            if any(kw.lower() in message_lower for kw in keywords):
                domains_found += 1
        
        score += domains_found * 3
        
        # 4. 实时信息需求
        realtime_keywords = ["最新", "最近", "今天", "现在", "新闻", "趋势", "天气"]
        if any(kw in message_lower for kw in realtime_keywords):
            score += 3
        
        # 5. 深度思考触发词（权重更高）
        deep_thinking_keywords = ["分析", "研究", "评估", "思考", "总结", "解释"]
        if any(kw in message_lower for kw in deep_thinking_keywords):
            score += 4
        
        # 6. 否定和条件组合
        if '不' in message and ('如果' in message or '假如' in message):
            score += 3
        
        # 7. 命令句式检测
        command_keywords = ['帮我', '请', '能否', '是否', '可不可以']
        if any(kw in message_lower for kw in command_keywords):
            score += 2
        
        # 确定复杂度级别（调整阈值）
        if score < 3:
            return "trivial"
        elif score < 6:
            return "simple"
        elif score < 11:
            return "moderate"
        elif score < 18:
            return "complex"
        else:
            return "very_complex"
    
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
你是一个专业的验证和反思助手。请验证信息是否足够回答用户问题，并严格按照JSON格式返回结果。

思考计划：{plan}
搜索结果：
{search_context}
用户问题：{message}

验证结果的JSON格式如下：
{{
  "validation_passed": false,
  "issues": ["问题1", "问题2"],
  "confidence": 0.8,
  "reflection": "反思内容",
  "additional_search": false,
  "missing_info": ["缺少的信息1"],
  "improvement_suggestions": ["建议1"],
  "key_evidence": ["证据1"]
}}

注意：
- validation_passed 和 additional_search 是布尔值
- issues、missing_info、improvement_suggestions、key_evidence 是字符串数组
- confidence 是数字，范围 0-1
- reflection 是字符串

请严格返回纯JSON，不要包含代码块标记或其他文字。
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


    async def _reflect_on_answer(self, answer: str, search_results: List[Dict[str, Any]], message: str) -> Dict[str, Any]:
        """反思当前答案的质量
        
        Args:
            answer: 当前答案
            search_results: 搜索结果
            message: 用户消息
            
        Returns:
            反思结果，包含置信度和改进建议
        """
        if not self.llm_router or not self.llm_router.is_available():
            return self._rule_based_reflection(answer, search_results, message)
        
        search_summaries = []
        for i, result in enumerate(search_results[:3]):
            search_summaries.append(f"[{i+1}] {result.get('title', '')}: {result.get('snippet', '')[:100]}...")
        search_context = "\n".join(search_summaries)
        
        prompt = f"""
你是一个专业的答案反思助手。请分析当前答案是否准确、完整地回答了用户问题。

用户问题：{message}
当前答案：{answer}
参考信息：
{search_context}

请按照JSON格式返回反思结果：
{{
  "confidence": 0.85,
  "accuracy": "high",
  "completeness": "complete",
  "relevance": "high",
  "issues": ["问题1", "问题2"],
  "suggestions": ["改进建议1", "改进建议2"],
  "missing_info": ["缺少的信息"],
  "reflection": "反思内容"
}}

说明：
- confidence: 0-1的数字，表示对答案的置信度
- accuracy: high/medium/low，表示准确性
- completeness: complete/partial/incomplete，表示完整性
- relevance: high/medium/low，表示相关性
- issues: 问题列表
- suggestions: 改进建议列表
- missing_info: 缺少的信息列表
- reflection: 反思内容（字符串）

请严格返回纯JSON，不要包含其他内容。
"""
        
        try:
            response = await self.llm_router.simple_chat(prompt)
            import json
            result = json.loads(response)
            
            # 确保所有字段存在
            result.setdefault("confidence", 0.7)
            result.setdefault("accuracy", "medium")
            result.setdefault("completeness", "partial")
            result.setdefault("relevance", "medium")
            result.setdefault("issues", [])
            result.setdefault("suggestions", [])
            result.setdefault("missing_info", [])
            result.setdefault("reflection", "")
            
            return result
        except Exception as e:
            logger.error("反思失败: %s", e)
            return self._rule_based_reflection(answer, search_results, message)
    
    def _rule_based_reflection(self, answer: str, search_results: List[Dict[str, Any]], message: str) -> Dict[str, Any]:
        """基于规则的反思
        
        Args:
            answer: 当前答案
            search_results: 搜索结果
            message: 用户消息
            
        Returns:
            反思结果
        """
        issues = []
        suggestions = []
        missing_info = []
        confidence = 0.7
        
        # 检查答案长度
        if len(answer) < 20:
            issues.append("答案过于简短")
            suggestions.append("增加详细解释")
            confidence -= 0.1
        
        # 检查是否引用了搜索结果
        answer_lower = answer.lower()
        has_source = False
        for result in search_results[:3]:
            title = result.get("title", "").lower()
            snippet = result.get("snippet", "").lower()
            if title in answer_lower or snippet[:20] in answer_lower:
                has_source = True
                break
        
        if not has_source and search_results:
            issues.append("答案未引用搜索结果")
            suggestions.append("结合搜索结果提供更准确的回答")
            confidence -= 0.15
        
        # 检查问题关键词是否在答案中出现
        import re
        message_words = re.findall(r'[\w\u4e00-\u9fa5]+', message.lower())
        answer_words = re.findall(r'[\w\u4e00-\u9fa5]+', answer.lower())
        matched_words = set(message_words) & set(answer_words)
        
        if len(matched_words) < len(message_words) * 0.5:
            issues.append("答案与问题相关性不足")
            suggestions.append("确保回答直接针对用户问题")
            confidence -= 0.1
        
        # 检查是否有矛盾信息
        for result in search_results[:3]:
            snippet = result.get("snippet", "").lower()
            if snippet and snippet[:30] in answer_lower:
                pass  # 内容匹配，没问题
        
        confidence = max(0.3, min(confidence, 1.0))
        
        return {
            "confidence": confidence,
            "accuracy": "high" if confidence > 0.7 else "medium" if confidence > 0.5 else "low",
            "completeness": "complete" if not issues else "partial",
            "relevance": "high" if len(matched_words) >= len(message_words) * 0.7 else "medium",
            "issues": issues,
            "suggestions": suggestions,
            "missing_info": missing_info,
            "reflection": "基于规则的反思完成"
        }
    
    async def _improve_answer(self, answer: str, reflection: Dict[str, Any], message: str) -> str:
        """根据反思结果改进答案
        
        Args:
            answer: 当前答案
            reflection: 反思结果
            message: 用户消息
            
        Returns:
            改进后的答案
        """
        if not self.llm_router or not self.llm_router.is_available():
            return answer
        
        suggestions = reflection.get("suggestions", [])
        issues = reflection.get("issues", [])
        
        if not suggestions and not issues:
            return answer
        
        prompt = f"""
请根据以下反思结果改进答案：

用户问题：{message}
当前答案：{answer}

问题列表：
{chr(10).join([f"- {issue}" for issue in issues]) if issues else "- 无"}

改进建议：
{chr(10).join([f"- {suggestion}" for suggestion in suggestions]) if suggestions else "- 无"}

请基于问题和建议，生成一个改进后的答案。
要求：
1. 直接返回改进后的答案，不要有额外说明
2. 确保答案准确、完整、相关
3. 结构清晰，逻辑连贯
"""
        
        try:
            response = await self.llm_router.simple_chat(prompt)
            return response
        except Exception as e:
            logger.error("改进答案失败: %s", e)
            return answer


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


# ========== 向后兼容：从 reasoning_types 重新导出 ==========
# 外部代码通过 `from core.engine.reasoning_engine import Thing` 导入
# 的方式仍然有效
__all__ = [
    "ReasoningEngine",
    "get_reasoning_engine",
    "ThinkingDepth",
    "TaskComplexity",
    "ImpactLevel",
]
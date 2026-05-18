"""自动复盘模块 - Hermes自我进化第二步

使用MySQL数据库存储复盘结果，并用LLM生成有针对性的复盘分析。

复盘三个问题：
1. 哪里做得好？
2. 哪里踩坑？
3. 下次怎么更快？
"""

import json
import logging
import asyncio
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ReviewResultEntry:
    """复盘结果数据结构（内存中使用）"""
    review_id: str
    task_id: str
    timestamp: str
    task_description: str
    what_went_well: str
    pitfalls: str
    improvement: str
    skill_name: Optional[str] = None
    applicable_scenarios: Optional[List[str]] = None
    is_worth_saving: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewResultEntry":
        return cls(**data)


class AutoReviewer:
    """自动复盘器（MySQL版 + LLM增强 + 缓存优化）

    功能：
    - 任务结束自动触发复盘
    - 使用LLM生成有针对性的复盘报告
    - 判断是否值得沉淀为技能
    - 复盘结果存储到MySQL
    - LLM缓存机制减少调用次数和成本
    """

    def __init__(self, llm_client=None, cache_ttl: int = 3600):
        self.llm_client = llm_client
        self.review_history: Dict[str, ReviewResultEntry] = {}
        self._review_cache: Dict[str, tuple] = {}
        self._cache_ttl = cache_ttl

        if llm_client is None:
            self._try_init_llm()

        logger.info("AutoReviewer 初始化完成（LLM缓存TTL=%ds）", cache_ttl)

    def _generate_cache_key(self, execution_logs: str, task_description: str) -> str:
        """生成缓存键（基于执行日志的指纹）"""
        import hashlib
        content = f"{task_description}:{execution_logs[:500]}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached_review(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """获取缓存的复盘结果"""
        if cache_key not in self._review_cache:
            return None

        cached_time, cached_result = self._review_cache[cache_key]
        elapsed = (datetime.now() - cached_time).total_seconds()

        if elapsed > self._cache_ttl:
            del self._review_cache[cache_key]
            return None

        logger.debug("使用缓存的复盘结果 (缓存时间: %.0fs前)", elapsed)
        return cached_result

    def _cache_review(self, cache_key: str, result: Dict[str, Any]):
        """缓存复盘结果"""
        self._review_cache[cache_key] = (datetime.now(), result)
        logger.debug("复盘结果已缓存 (key=%s)", cache_key[:8])

    def _try_init_llm(self):
        """尝试初始化LLM客户端"""
        try:
            from core.engine.llm_backend import get_llm_router

            self.llm_facade = get_llm_router()
            self.llm_request_class = None

            if not self.llm_facade.is_available():
                logger.warning("没有可用的LLM模型，将使用智能Mock复盘")
                self.llm_facade = None

            logger.info("LLM客户端初始化成功")
        except Exception as e:
            logger.warning("LLM客户端初始化失败，将使用智能Mock复盘: %s", e)
            self.llm_facade = None
            self.llm_request_class = None

    def _get_db_session(self):
        """获取数据库会话"""
        try:
            from core.database import get_db_session as get_session
            return get_session()
        except Exception as e:
            logger.warning("数据库会话获取失败: %s", e)
            return None

    async def review(
        self,
        task_id: str,
        task_description: str,
        execution_logs: str,
        task_result: Optional[str] = None,
        user_feedback: Optional[str] = None,
    ) -> ReviewResultEntry:
        """执行复盘

        Args:
            task_id: 任务ID
            task_description: 任务描述
            execution_logs: 格式化后的执行日志
            task_result: 任务最终结果（可选）
            user_feedback: 用户反馈（可选）
        """
        logger.info("开始复盘任务: %s", task_id)

        cache_key = self._generate_cache_key(execution_logs, task_description)
        cached_result = self._get_cached_review(cache_key)

        if cached_result:
            logger.info("使用缓存的复盘结果: %s", task_id)
            review_result = ReviewResultEntry(
                review_id=cached_result['review_id'],
                task_id=task_id,
                timestamp=datetime.now().isoformat(),
                task_description=task_description,
                what_went_well=cached_result['what_went_well'],
                pitfalls=cached_result['pitfalls'],
                improvement=cached_result['improvement'],
                skill_name=cached_result.get('skill_name'),
                applicable_scenarios=cached_result.get('applicable_scenarios'),
                is_worth_saving=cached_result['is_worth_saving'],
            )
        elif self.llm_facade:
            review_result = await self._llm_review(task_id, task_description, execution_logs, task_result, user_feedback)
            self._cache_review(cache_key, review_result.to_dict())
        else:
            review_result = self._simple_review(task_id, task_description, execution_logs)

        self.review_history[task_id] = review_result
        self._save_review_to_db(review_result)

        logger.info(
            "复盘完成: %s, 值得保存: %s",
            task_id, review_result.is_worth_saving
        )

        return review_result

    async def _llm_review(
        self,
        task_id: str,
        task_description: str,
        execution_logs: str,
        task_result: Optional[str],
        user_feedback: Optional[str],
    ) -> ReviewResultEntry:
        """使用LLM进行深度复盘"""
        prompt = f"""你是一位经验丰富的AI助手复盘分析师。请基于以下执行日志，对这次任务执行进行深入分析。

任务描述: {task_description}

执行日志详情:
{execution_logs}

{f"任务最终结果: {task_result}" if task_result else ""}
{f"用户反馈: {user_feedback}" if user_feedback else ""}

请按照以下格式输出详细的复盘报告（用中文）：

【哪里做得好】
- 具体说明执行过程中哪些方面做得不错
- 包括成功的步骤、有效的工具调用、良好的决策等

【哪里踩坑】
- 具体说明遇到的问题、失败的步骤、错误的工具调用
- 如果没有明显问题，请分析潜在的风险点或可以改进的地方

【下次怎么更快】
- 具体的优化建议
- 包括可以复用的模式、简化的步骤、避免重复劳动的方法

【是否值得沉淀为技能】
- yes/no
- 如果yes，请给出技能名称和适用场景

请用自然、详细的语言描述，不要使用JSON格式。"""

        try:
            response = await self.llm_facade.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
            )
            response_text = response if isinstance(response, str) else str(response)

            return self._parse_llm_response(task_id, task_description, response_text)

        except Exception as e:
            logger.warning("LLM复盘失败，回退到简单复盘: %s", e)
            return self._simple_review(task_id, task_description, execution_logs)

    def _parse_llm_response(self, task_id: str, task_description: str, response_text: str) -> ReviewResultEntry:
        """解析LLM返回的复盘报告"""
        what_went_well = ""
        pitfalls = ""
        improvement = ""
        skill_name = None
        applicable_scenarios = []
        is_worth_saving = False

        sections = response_text.split("【")
        for section in sections:
            if "哪里做得好】" in section:
                what_went_well = section.split("】")[1].strip()
            elif "哪里踩坑】" in section:
                pitfalls = section.split("】")[1].strip()
            elif "下次怎么更快】" in section:
                improvement = section.split("】")[1].strip()
            elif "是否值得沉淀为技能】" in section:
                skill_section = section.split("】")[1].strip()
                if "yes" in skill_section.lower() or "是" in skill_section:
                    is_worth_saving = True
                    lines = skill_section.split("\n")
                    for line in lines:
                        if "技能名称" in line or "名称" in line:
                            skill_name = line.split(":")[-1].strip() if ":" in line else None
                        if "适用场景" in line:
                            scenarios = line.split(":")[-1].strip() if ":" in line else ""
                            applicable_scenarios = [s.strip() for s in scenarios.split("、") if s.strip()]

        if not what_went_well:
            what_went_well = "任务执行成功完成"
        if not pitfalls:
            pitfalls = "执行过程顺利，未发现明显问题。建议关注执行效率和结果质量的持续优化。"
        if not improvement:
            improvement = "可以考虑总结本次执行经验，形成可复用的工作流程；优化工具调用顺序，减少不必要的步骤。"

        return ReviewResultEntry(
            review_id=f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            task_id=task_id,
            timestamp=datetime.now().isoformat(),
            task_description=task_description,
            what_went_well=what_went_well,
            pitfalls=pitfalls,
            improvement=improvement,
            skill_name=skill_name,
            applicable_scenarios=applicable_scenarios if applicable_scenarios else None,
            is_worth_saving=is_worth_saving,
        )

    def _simple_review(
        self,
        task_id: str,
        task_description: str,
        execution_logs: str,
    ) -> ReviewResultEntry:
        """智能Mock复盘（无LLM时使用）"""
        lines = execution_logs.strip().split("\n")

        success_count = sum(1 for line in lines if "✅" in line)
        failed_count = sum(1 for line in lines if "❌" in line)
        total_count = len(lines)
        
        # 分析任务类型
        task_type = self._analyze_task_type(task_description)
        
        # 生成详细的复盘内容
        what_went_well = self._generate_what_went_well(task_type, success_count, total_count, lines)
        pitfalls = self._generate_pitfalls(task_type, failed_count, lines)
        improvement = self._generate_improvement(task_type, success_count, failed_count, total_count, lines)
        
        is_worth_saving = failed_count > 0 or success_count >= 5

        return ReviewResultEntry(
            review_id=f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            task_id=task_id,
            timestamp=datetime.now().isoformat(),
            task_description=task_description,
            what_went_well=what_went_well,
            pitfalls=pitfalls,
            improvement=improvement,
            is_worth_saving=is_worth_saving,
        )
    
    def _analyze_task_type(self, task_description: str) -> str:
        """分析任务类型"""
        task_description_lower = task_description.lower()
        
        if any(keyword in task_description_lower for keyword in ["分析", "研究", "评估", "对比"]):
            return "分析类"
        elif any(keyword in task_description_lower for keyword in ["爬取", "抓取", "获取", "搜索"]):
            return "数据获取类"
        elif any(keyword in task_description_lower for keyword in ["生成", "创作", "编写", "设计"]):
            return "创作类"
        elif any(keyword in task_description_lower for keyword in ["总结", "归纳", "摘要"]):
            return "总结类"
        else:
            return "通用类"
    
    def _analyze_failure_pattern(self, lines: List[str]) -> Dict[str, Any]:
        """分析失败模式

        Returns:
            Dict包含:
            - pattern: 失败模式类型 (timeout/network/param/unknown)
            - details: 具体描述
            - affected_tools: 受影响的工具列表
        """
        pattern_info = {
            "pattern": "unknown",
            "details": "",
            "affected_tools": []
        }

        error_keywords = {
            "timeout": ["超时", "timeout", "timed out", "连接超时"],
            "network": ["网络", "network", "连接失败", "connection", "无法访问", "DNS"],
            "param": ["参数", "param", "缺少参数", "invalid", "格式错误"],
            "auth": ["权限", "auth", "认证", "token", "未授权", "forbidden"],
            "rate": ["频率", "rate", "限流", "too many", "配额"],
        }

        combined_text = "\n".join(lines)

        for pattern_type, keywords in error_keywords.items():
            if any(kw.lower() in combined_text.lower() for kw in keywords):
                pattern_info["pattern"] = pattern_type
                break

        tool_pattern = r'\[([\w_]+)\]'
        failed_tools = set()
        for line in lines:
            if "❌" in line or "失败" in line or "错误" in line:
                match = re.search(tool_pattern, line)
                if match:
                    failed_tools.add(match.group(1))

        pattern_info["affected_tools"] = list(failed_tools)

        if pattern_info["pattern"] == "timeout":
            pattern_info["details"] = "存在网络超时问题，可能与目标网站响应慢有关"
        elif pattern_info["pattern"] == "network":
            pattern_info["details"] = "存在网络连接问题，建议检查网络状况"
        elif pattern_info["pattern"] == "param":
            pattern_info["details"] = "存在参数错误，建议检查输入参数格式"
        elif pattern_info["pattern"] == "auth":
            pattern_info["details"] = "存在权限认证问题，可能需要API密钥或登录"
        elif pattern_info["pattern"] == "rate":
            pattern_info["details"] = "存在频率限制，建议添加重试间隔"

        return pattern_info

    def _extract_execution_metrics(self, lines: List[str]) -> Dict[str, Any]:
        """提取执行指标"""
        metrics = {
            "total_steps": len(lines),
            "success_count": 0,
            "failed_count": 0,
            "total_duration_ms": 0,
            "avg_duration_ms": 0,
            "tools_used": set(),
            "slowest_step": None,
            "slowest_duration_ms": 0,
        }

        duration_pattern = r'耗时:\s*(\d+)ms'

        for line in lines:
            if "✅" in line:
                metrics["success_count"] += 1
            elif "❌" in line:
                metrics["failed_count"] += 1

            tool_match = re.search(r'\[([\w_]+)\]', line)
            if tool_match:
                metrics["tools_used"].add(tool_match.group(1))

            duration_match = re.search(duration_pattern, line)
            if duration_match:
                duration = int(duration_match.group(1))
                metrics["total_duration_ms"] += duration
                if duration > metrics["slowest_duration_ms"]:
                    metrics["slowest_duration_ms"] = duration
                    metrics["slowest_step"] = line.strip()[:50]

        if metrics["total_steps"] > 0:
            metrics["avg_duration_ms"] = metrics["total_duration_ms"] / metrics["total_steps"]

        return metrics

    def _generate_what_went_well(self, task_type: str, success_count: int, total_count: int, lines: list) -> str:
        """生成"哪里做得好"部分 - 增强版"""
        parts = []
        metrics = self._extract_execution_metrics(lines)

        if metrics["success_count"] == metrics["total_steps"] and metrics["total_steps"] > 0:
            parts.append(f"任务执行完全成功，所有 {metrics['total_steps']} 个步骤均顺利完成")

        if metrics["total_steps"] >= 3:
            parts.append(f"成功完成了 {metrics['success_count']}/{metrics['total_steps']} 个步骤，任务整体执行流程顺畅")

        if metrics["tools_used"]:
            tools_str = ", ".join(sorted(metrics["tools_used"]))
            parts.append(f"成功调用了工具: {tools_str}")

        if task_type == "分析类":
            parts.append("分析逻辑清晰，步骤安排合理")
        elif task_type == "数据获取类":
            parts.append("数据源获取成功，数据质量良好")
        elif task_type == "创作类":
            parts.append("创作流程顺利，内容生成成功")

        if metrics["avg_duration_ms"] < 1000:
            parts.append(f"平均执行速度较快 ({metrics['avg_duration_ms']:.0f}ms/步)")

        if not parts:
            parts.append("任务执行成功完成")

        return "\n".join(f"- {part}" for part in parts)

    def _generate_pitfalls(self, task_type: str, failed_count: int, lines: list) -> str:
        """生成"哪里踩坑"部分 - 增强版"""
        parts = []
        failure_pattern = self._analyze_failure_pattern(lines)

        if failed_count > 0:
            parts.append(f"有 {failed_count} 个步骤执行失败")

            if failure_pattern["details"]:
                parts.append(f"  - 失败模式: {failure_pattern['details']}")

            if failure_pattern["affected_tools"]:
                tools_str = ", ".join(failure_pattern["affected_tools"])
                parts.append(f"  - 受影响工具: {tools_str}")

            for line in lines:
                if "❌" in line:
                    parts.append(f"  - {line.replace('❌', '').strip()[:80]}")
        else:
            parts.append("执行过程顺利，未发现明显问题")

            if failure_pattern["pattern"] != "unknown":
                parts.append(f"  - 潜在风险: {failure_pattern['details']}")

            if task_type == "分析类":
                parts.append("  - 建议验证分析结果的准确性和数据来源的可靠性")
            elif task_type == "数据获取类":
                parts.append("  - 注意检查数据完整性，确保没有遗漏关键信息")
            elif task_type == "创作类":
                parts.append("  - 建议审查生成内容的质量和原创性")

            parts.append("  - 建议关注执行效率和结果质量的持续优化")

        return "\n".join(parts)

    def _generate_improvement(self, task_type: str, success_count: int, failed_count: int, total_count: int, lines: list) -> str:
        """生成"下次怎么更快"部分 - 增强版"""
        parts = []
        metrics = self._extract_execution_metrics(lines)
        failure_pattern = self._analyze_failure_pattern(lines)

        if total_count >= 5:
            parts.append("可以考虑总结本次执行经验，形成可复用的工作流程(SOP)")

        if failed_count > 0:
            if failure_pattern["pattern"] == "timeout":
                parts.append("建议增加超时时间或添加重试机制")
            elif failure_pattern["pattern"] == "network":
                parts.append("建议添加网络状态检查和自动重连")
            elif failure_pattern["pattern"] == "param":
                parts.append("建议添加参数预校验")
            else:
                parts.append("针对失败步骤进行优化，减少重试次数")

        if metrics["slowest_duration_ms"] > 3000:
            parts.append(f"注意最慢步骤耗时 {metrics['slowest_duration_ms']}ms，可考虑优化")

        if "web_scraper" in metrics["tools_used"]:
            parts.append("优化网页抓取策略，提高抓取效率和成功率")

        if "data_analysis" in metrics["tools_used"]:
            parts.append("优化数据分析算法，提升处理速度")

        parts.append("建立执行标准操作流程，便于后续复用")

        if task_type == "分析类":
            parts.append("可以考虑预加载常用分析模板，加快分析速度")
        elif task_type == "数据获取类":
            parts.append("可以考虑建立数据缓存机制，减少重复请求")
        elif task_type == "创作类":
            parts.append("可以考虑建立内容模板库，提高创作效率")

        return "\n".join(f"- {part}" for part in parts)

    def _save_review_to_db(self, review: ReviewResultEntry):
        """保存复盘结果到MySQL"""
        try:
            from core.database import get_db_session, ReviewResult

            try:
                with get_db_session() as session:
                    db_review = ReviewResult(
                        review_id=review.review_id,
                        task_id=review.task_id,
                        timestamp=datetime.fromisoformat(review.timestamp),
                        task_description=review.task_description,
                        what_went_well=review.what_went_well,
                        pitfalls=review.pitfalls,
                        improvement=review.improvement,
                        skill_name=review.skill_name,
                        applicable_scenarios=review.applicable_scenarios or [],
                        is_worth_saving=review.is_worth_saving,
                    )

                    session.add(db_review)
            except RuntimeError as db_error:
                if "数据库未初始化" in str(db_error):
                    logger.debug("数据库未初始化，跳过复盘持久化")
                else:
                    raise

        except Exception as e:
            logger.warning("保存复盘结果到数据库失败: %s", e)

    def get_review(self, task_id: str) -> Optional[ReviewResultEntry]:
        """获取指定任务的复盘结果"""
        return self.review_history.get(task_id)

    def get_recent_reviews(self, limit: int = 10) -> List[ReviewResultEntry]:
        """获取最近的复盘结果"""
        try:
            session = self._get_db_session()
            if session is None:
                return []

            from core.database import ReviewResult
            from sqlalchemy import desc

            reviews = session.query(ReviewResult)\
                .order_by(desc(ReviewResult.timestamp))\
                .limit(limit)\
                .all()

            return [
                ReviewResultEntry(
                    review_id=r.review_id,
                    task_id=r.task_id,
                    timestamp=r.timestamp.isoformat(),
                    task_description=r.task_description,
                    what_went_well=r.what_went_well,
                    pitfalls=r.pitfalls,
                    improvement=r.improvement,
                    skill_name=r.skill_name,
                    applicable_scenarios=r.applicable_scenarios or [],
                    is_worth_saving=r.is_worth_saving,
                )
                for r in reviews
            ]

        except Exception as e:
            logger.warning("获取复盘历史失败: %s", e)
            return sorted(
                self.review_history.values(),
                key=lambda x: x.timestamp,
                reverse=True
            )[:limit]

    def get_worth_saving_reviews(self) -> List[ReviewResultEntry]:
        """获取所有值得沉淀的复盘结果"""
        try:
            session = self._get_db_session()
            if session is None:
                return [r for r in self.review_history.values() if r.is_worth_saving]

            from core.database import ReviewResult

            reviews = session.query(ReviewResult)\
                .filter(ReviewResult.is_worth_saving == True)\
                .all()

            return [
                ReviewResultEntry(
                    review_id=r.review_id,
                    task_id=r.task_id,
                    timestamp=r.timestamp.isoformat(),
                    task_description=r.task_description,
                    what_went_well=r.what_went_well,
                    pitfalls=r.pitfalls,
                    improvement=r.improvement,
                    skill_name=r.skill_name,
                    applicable_scenarios=r.applicable_scenarios or [],
                    is_worth_saving=r.is_worth_saving,
                )
                for r in reviews
            ]

        except Exception as e:
            logger.warning("获取值得保存的复盘失败: %s", e)
            return [r for r in self.review_history.values() if r.is_worth_saving]

    def format_review_report(self, review: ReviewResultEntry) -> str:
        """格式化复盘报告供展示"""
        report = f"""
{'='*50}
📋 复盘报告: {review.task_id}
{'='*50}

📌 任务: {review.task_description}

✅ 哪里做得好？
{self._format_list(review.what_went_well)}

⚠️ 哪里踩坑？
{self._format_list(review.pitfalls)}

💡 下次怎么更快？
{self._format_list(review.improvement)}
"""
        if review.skill_name:
            report += f"""
📝 可沉淀技能: {review.skill_name}
   适用场景: {', '.join(review.applicable_scenarios or [])}
"""

        report += f"{'='*50}"
        return report

    def _format_list(self, text: str) -> str:
        """格式化列表文本"""
        lines = text.split("\n")
        formatted = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("-"):
                formatted.append(f"   - {line}")
            else:
                formatted.append(f"   {line}")
        return "\n".join(formatted)


_auto_reviewer_instance: Optional[AutoReviewer] = None


def get_auto_reviewer() -> AutoReviewer:
    """获取自动复盘器单例"""
    global _auto_reviewer_instance
    if _auto_reviewer_instance is None:
        _auto_reviewer_instance = AutoReviewer()
    return _auto_reviewer_instance

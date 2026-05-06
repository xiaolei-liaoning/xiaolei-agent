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
    """自动复盘器（MySQL版 + LLM增强）

    功能：
    - 任务结束自动触发复盘
    - 使用LLM生成有针对性的复盘报告
    - 判断是否值得沉淀为技能
    - 复盘结果存储到MySQL
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.review_history: Dict[str, ReviewResultEntry] = {}

        if llm_client is None:
            self._try_init_llm()

        logger.info("AutoReviewer 初始化完成（MySQL版 + LLM增强）")

    def _try_init_llm(self):
        """尝试初始化LLM客户端"""
        try:
            from core.multi_agent_v2.infrastructure.llm.llm_facade import LLMFacade
            from core.multi_agent_v2.infrastructure.llm.llm_facade import LLMRequest

            self.llm_facade = LLMFacade()
            self.llm_request_class = LLMRequest
            
            # 检查是否有可用模型
            if not self.llm_facade.models:
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

        if self.llm_facade:
            review_result = await self._llm_review(task_id, task_description, execution_logs, task_result, user_feedback)
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
            request = self.llm_request_class(
                prompt=prompt,
                model=None,  # 让系统自动选择可用模型
                max_tokens=1000,
                temperature=0.3
            )
            response = await self.llm_facade.generate(request)
            response_text = response.content if hasattr(response, 'content') else str(response)

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
    
    def _generate_what_went_well(self, task_type: str, success_count: int, total_count: int, lines: list) -> str:
        """生成"哪里做得好"部分"""
        parts = []
        
        if success_count == total_count and total_count > 0:
            parts.append(f"任务执行完全成功，所有 {total_count} 个步骤均顺利完成")
        
        if total_count >= 3:
            parts.append(f"成功完成了 {success_count}/{total_count} 个步骤，任务整体执行流程顺畅")
        
        if "web_scraper" in "\n".join(lines) or "爬取" in "\n".join(lines):
            parts.append("成功调用了网页抓取工具，获取了所需数据")
        
        if "data_analysis" in "\n".join(lines) or "分析" in "\n".join(lines):
            parts.append("数据分析模块运行正常，生成了分析结果")
        
        if task_type == "分析类":
            parts.append("分析逻辑清晰，步骤安排合理")
        elif task_type == "数据获取类":
            parts.append("数据源获取成功，数据质量良好")
        elif task_type == "创作类":
            parts.append("创作流程顺利，内容生成成功")
        
        if not parts:
            parts.append("任务执行成功完成")
        
        return "\n".join(f"- {part}" for part in parts)
    
    def _generate_pitfalls(self, task_type: str, failed_count: int, lines: list) -> str:
        """生成"哪里踩坑"部分"""
        parts = []
        
        if failed_count > 0:
            parts.append(f"有 {failed_count} 个步骤执行失败，建议检查失败原因")
            
            for line in lines:
                if "❌" in line:
                    parts.append(f"  - {line.replace('❌', '').strip()}")
        else:
            parts.append("执行过程顺利，未发现明显问题")
            
            # 潜在风险点分析
            if task_type == "分析类":
                parts.append("  - 建议验证分析结果的准确性和数据来源的可靠性")
            elif task_type == "数据获取类":
                parts.append("  - 注意检查数据完整性，确保没有遗漏关键信息")
            elif task_type == "创作类":
                parts.append("  - 建议审查生成内容的质量和原创性")
            
            parts.append("  - 建议关注执行效率和结果质量的持续优化")
        
        return "\n".join(parts)
    
    def _generate_improvement(self, task_type: str, success_count: int, failed_count: int, total_count: int, lines: list) -> str:
        """生成"下次怎么更快"部分"""
        parts = []
        
        if total_count >= 5:
            parts.append("可以考虑总结本次执行经验，形成可复用的工作流程(SOP)")
        
        if failed_count > 0:
            parts.append("针对失败步骤进行优化，减少重试次数")
        
        if "web_scraper" in "\n".join(lines):
            parts.append("优化网页抓取策略，提高抓取效率和成功率")
        
        if "data_analysis" in "\n".join(lines):
            parts.append("优化数据分析算法，提升处理速度")
        
        parts.append("建立执行标准操作流程，便于后续复用")
        parts.append("对常用任务类型建立技能库，下次直接调用")
        
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

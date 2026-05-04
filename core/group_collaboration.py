"""多Agent小组协作协调器

实现场景1：多Agent小组协作
实现场景2：无对应Agent处理
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


# ==========================================
# 枚举定义
# ==========================================

class CollaborationStrategy(Enum):
    """协作策略"""
    SEQUENTIAL = "sequential"      # 顺序协作
    PARALLEL = "parallel"          # 并行协作
    HIERARCHICAL = "hierarchical"  # 分层协作
    CIRCULAR = "circular"          # 循环协作

class TaskPhase(Enum):
    """任务阶段"""
    ANALYSIS = "analysis"
    PLANNING = "planning"
    EXECUTION = "execution"
    REVIEW = "review"
    INTEGRATION = "integration"

class AgentCapability(Enum):
    """Agent能力类别"""
    TEXT_GENERATION = "text_generation"
    DATA_ANALYSIS = "data_analysis"
    WEB_SEARCH = "web_search"
    CREATIVE_WRITING = "creative_writing"
    CODE_GENERATION = "code_generation"
    TRANSLATION = "translation"
    REASONING = "reasoning"


# ==========================================
# 数据结构
# ==========================================

@dataclass
class SubTask:
    """拆解后的子任务"""
    subtask_id: str
    description: str
    required_capability: AgentCapability
    assigned_group: Optional[str] = None
    status: str = "pending"
    result: Optional[Any] = None
    priority: float = 1.0
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class CollaborationSession:
    """协作会话"""
    session_id: str
    original_task: str
    subtasks: List[SubTask] = field(default_factory=list)
    phase: TaskPhase = TaskPhase.ANALYSIS
    coordinator_id: Optional[str] = None
    participant_groups: List[str] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = "active"
    error_message: Optional[str] = None


@dataclass
class AgentGroupProfile:
    """Agent小组能力画像"""
    group_id: str
    name: str
    capabilities: List[AgentCapability]
    description: str = ""
    success_rate: float = 1.0
    avg_response_time: float = 0.0
    total_tasks: int = 0
    available: bool = True


@dataclass
class AgentRecommendation:
    """Agent推荐结果"""
    recommended_groups: List[AgentGroupProfile]
    requires_new_agent: bool = False
    required_capabilities: List[AgentCapability] = field(default_factory=list)
    suggested_agent_name: Optional[str] = None
    suggested_agent_description: Optional[str] = None


# ==========================================
# 协作协调器实现
# ==========================================

class GroupCollaborationCoordinator:
    """多Agent小组协作协调器"""
    
    def __init__(self):
        self.sessions: Dict[str, CollaborationSession] = {}
        self.group_profiles: Dict[str, AgentGroupProfile] = {}
        self.capability_keywords: Dict[AgentCapability, List[str]] = {
            AgentCapability.TEXT_GENERATION: ["写", "生成", "创作", "文案", "报告"],
            AgentCapability.DATA_ANALYSIS: ["分析", "统计", "趋势", "数据", "计算"],
            AgentCapability.WEB_SEARCH: ["搜索", "查询", "找", "热搜", "信息"],
            AgentCapability.CREATIVE_WRITING: ["诗", "文学", "创意", "故事", "小说"],
            AgentCapability.CODE_GENERATION: ["代码", "编程", "程序", "开发"],
            AgentCapability.TRANSLATION: ["翻译", "英文", "中文", "外语"],
            AgentCapability.REASONING: ["推理", "思考", "深度思考", "逻辑"]
        }
        self._coordinator_callbacks: List[Callable] = []
        logger.info("✅ 多Agent小组协作协调器初始化完成")
    
    def register_group_profile(self, profile: AgentGroupProfile):
        """注册Agent小组能力画像"""
        self.group_profiles[profile.group_id] = profile
        logger.info(f"📋 注册小组能力画像: {profile.name}")
    
    def analyze_task_requirements(self, task: str) -> Dict[str, Any]:
        """分析任务需求，识别需要的能力"""
        required_capabilities = []
        
        for capability, keywords in self.capability_keywords.items():
            for keyword in keywords:
                if keyword in task:
                    required_capabilities.append(capability)
                    break
        
        if not required_capabilities:
            required_capabilities.append(AgentCapability.REASONING)
        
        return {
            "required_capabilities": required_capabilities,
            "task_type": "complex" if len(required_capabilities) > 1 else "simple",
            "estimated_subtasks": max(1, len(required_capabilities))
        }
    
    def recommend_agent_groups(self, task: str) -> AgentRecommendation:
        """为任务推荐合适的Agent小组"""
        analysis = self.analyze_task_requirements(task)
        required_capabilities = analysis["required_capabilities"]
        
        recommended_groups = []
        for group_id, profile in self.group_profiles.items():
            if not profile.available:
                continue
            
            matched_capabilities = [
                cap for cap in required_capabilities 
                if cap in profile.capabilities
            ]
            
            if matched_capabilities:
                profile_copy = AgentGroupProfile(
                    group_id=profile.group_id,
                    name=profile.name,
                    capabilities=profile.capabilities,
                    description=profile.description,
                    success_rate=profile.success_rate,
                    avg_response_time=profile.avg_response_time,
                    total_tasks=profile.total_tasks
                )
                recommended_groups.append(profile_copy)
        
        recommendation = AgentRecommendation(
            recommended_groups=recommended_groups,
            required_capabilities=required_capabilities
        )
        
        if not recommended_groups:
            recommendation.requires_new_agent = True
            recommendation.suggested_agent_name = self._suggest_agent_name(required_capabilities)
            recommendation.suggested_agent_description = self._suggest_agent_description(required_capabilities, task)
            logger.warning(f"⚠️ 任务需要新Agent: {task[:50]}...")
        
        logger.info(f"🎯 任务分析完成，推荐 {len(recommended_groups)} 个小组")
        return recommendation
    
    def _suggest_agent_name(self, capabilities: List[AgentCapability]) -> str:
        """建议新Agent名称"""
        if not capabilities:
            return "通用智能助手"
        
        primary_cap = capabilities[0]
        name_map = {
            AgentCapability.TEXT_GENERATION: "智能写作专家",
            AgentCapability.DATA_ANALYSIS: "数据分析专家",
            AgentCapability.WEB_SEARCH: "信息检索专家",
            AgentCapability.CREATIVE_WRITING: "文学创作专家",
            AgentCapability.CODE_GENERATION: "代码开发专家",
            AgentCapability.TRANSLATION: "多语言翻译专家",
            AgentCapability.REASONING: "深度思考专家"
        }
        
        return name_map.get(primary_cap, "智能专家团队")
    
    def _suggest_agent_description(self, capabilities: List[AgentCapability], task: str) -> str:
        """建议新Agent描述"""
        caps_str = ", ".join([cap.value for cap in capabilities])
        return f"专门处理 {caps_str} 相关任务的专业Agent小组。任务示例: {task[:30]}..."
    
    def split_task_into_subtasks(self, task: str, recommended_groups: List[AgentGroupProfile]) -> List[SubTask]:
        """将任务拆分为子任务"""
        subtasks = []
        analysis = self.analyze_task_requirements(task)
        
        if analysis["task_type"] == "simple":
            subtask = SubTask(
                subtask_id=str(uuid.uuid4()),
                description=task,
                required_capability=analysis["required_capabilities"][0],
                priority=1.0
            )
            if recommended_groups:
                subtask.assigned_group = recommended_groups[0].group_id
            subtasks.append(subtask)
        else:
            for capability in analysis["required_capabilities"]:
                matched_group = next(
                    (g for g in recommended_groups if capability in g.capabilities),
                    None
                )
                
                subtask = SubTask(
                    subtask_id=str(uuid.uuid4()),
                    description=self._generate_subtask_description(task, capability),
                    required_capability=capability,
                    assigned_group=matched_group.group_id if matched_group else None,
                    priority=0.8 if matched_group else 0.5
                )
                subtasks.append(subtask)
        
        logger.info(f"✂️ 任务拆解完成，共 {len(subtasks)} 个子任务")
        return subtasks
    
    def _generate_subtask_description(self, original_task: str, capability: AgentCapability) -> str:
        """生成子任务描述"""
        template_map = {
            AgentCapability.TEXT_GENERATION: "为任务生成相关文本内容",
            AgentCapability.DATA_ANALYSIS: "对相关数据进行分析和统计",
            AgentCapability.WEB_SEARCH: "搜索并收集相关信息",
            AgentCapability.CREATIVE_WRITING: "进行文学创作相关工作",
            AgentCapability.CODE_GENERATION: "完成代码开发任务",
            AgentCapability.TRANSLATION: "处理多语言翻译需求",
            AgentCapability.REASONING: "进行深度思考和逻辑推理"
        }
        
        base = template_map.get(capability, "处理相关任务")
        return f"{base}：{original_task[:50]}"
    
    async def start_collaboration_session(
        self,
        task: str,
        strategy: CollaborationStrategy = CollaborationStrategy.PARALLEL
    ) -> CollaborationSession:
        """启动协作会话"""
        session_id = str(uuid.uuid4())
        recommendation = self.recommend_agent_groups(task)
        
        subtasks = self.split_task_into_subtasks(task, recommendation.recommended_groups)
        
        session = CollaborationSession(
            session_id=session_id,
            original_task=task,
            subtasks=subtasks,
            participant_groups=[g.group_id for g in recommendation.recommended_groups],
            status="active"
        )
        
        self.sessions[session_id] = session
        
        logger.info(f"🚀 协作会话启动: {session_id}, 策略: {strategy.value}")
        return session
    
    async def execute_collaboration(
        self,
        session: CollaborationSession,
        group_executor: Any,
        strategy: CollaborationStrategy = CollaborationStrategy.PARALLEL
    ) -> Dict[str, Any]:
        """执行协作任务"""
        session.phase = TaskPhase.PLANNING
        session.updated_at = time.time()
        
        logger.info(f"📋 开始执行协作，策略: {strategy.value}")
        
        results = {}
        
        if strategy == CollaborationStrategy.PARALLEL:
            results = await self._execute_parallel(session, group_executor)
        elif strategy == CollaborationStrategy.SEQUENTIAL:
            results = await self._execute_sequential(session, group_executor)
        else:
            results = await self._execute_parallel(session, group_executor)
        
        session.phase = TaskPhase.INTEGRATION
        session.results = results
        session.status = "completed"
        session.updated_at = time.time()
        
        final_result = self._integrate_results(results, session.original_task)
        logger.info(f"✅ 协作完成，最终结果生成")
        
        return {
            "success": True,
            "session_id": session.session_id,
            "final_result": final_result,
            "subtask_results": results,
            "total_subtasks": len(session.subtasks)
        }
    
    async def _execute_parallel(
        self,
        session: CollaborationSession,
        group_executor: Any
    ) -> Dict[str, Any]:
        """并行执行所有子任务"""
        results = {}
        tasks = []
        
        for subtask in session.subtasks:
            if subtask.assigned_group and subtask.status == "pending":
                tasks.append(self._execute_subtask(subtask, group_executor, session))
        
        if tasks:
            completed_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in completed_results:
                if isinstance(result, Exception):
                    logger.error(f"⚠️ 子任务执行错误: {result}")
                elif result:
                    results[result["subtask_id"]] = result
        
        return results
    
    async def _execute_sequential(
        self,
        session: CollaborationSession,
        group_executor: Any
    ) -> Dict[str, Any]:
        """顺序执行子任务"""
        results = {}
        
        for subtask in session.subtasks:
            if subtask.assigned_group and subtask.status == "pending":
                try:
                    result = await self._execute_subtask(subtask, group_executor, session)
                    if result:
                        results[result["subtask_id"]] = result
                except Exception as e:
                    logger.error(f"⚠️ 子任务执行错误: {e}")
        
        return results
    
    async def _execute_subtask(
        self,
        subtask: SubTask,
        group_executor: Any,
        session: CollaborationSession
    ) -> Optional[Dict[str, Any]]:
        """执行单个子任务"""
        subtask.status = "in_progress"
        
        try:
            result = await group_executor.execute_with_group_id(
                subtask.assigned_group,
                subtask.description
            )
            
            subtask.status = "completed"
            subtask.result = result
            
            return {
                "subtask_id": subtask.subtask_id,
                "description": subtask.description,
                "assigned_group": subtask.assigned_group,
                "result": result,
                "success": result.get("success", False),
                "completed_at": time.time()
            }
        except Exception as e:
            subtask.status = "failed"
            logger.error(f"❌ 子任务执行失败: {e}")
            return None
    
    def _integrate_results(self, results: Dict[str, Any], original_task: str) -> str:
        """整合所有子任务结果"""
        if not results:
            return "未能获得有效结果。"
        
        integration = []
        integration.append("【任务执行总结】")
        integration.append(f"原始任务: {original_task}")
        integration.append("-" * 50)
        
        for subtask_id, result in results.items():
            if result.get("success"):
                integration.append(f"✓ {result.get('description', '')}")
                
                result_data = result.get("result", {})
                if result_data:
                    group_name = result_data.get("group_name", "")
                    if group_name:
                        integration.append(f"  由 {group_name} 完成")
                    
                    results_list = result_data.get("results", [])
                    for r in results_list[:2]:
                        msg = r.get("message", "")
                        if msg and len(msg) > 200:
                            msg = msg[:200] + "..."
                        if msg:
                            integration.append(f"  结果: {msg}")
        
        integration.append("-" * 50)
        integration.append(f"共完成 {len(results)} 个子任务")
        
        return "\n".join(integration)
    
    def get_session_status(self, session_id: str) -> Optional[CollaborationSession]:
        """获取会话状态"""
        return self.sessions.get(session_id)


# ==========================================
# 临时Agent创建器
# ==========================================

class TemporaryAgentCreator:
    """临时Agent创建器（用于场景2）"""
    
    def __init__(self):
        self.temporary_agents: Dict[str, Dict[str, Any]] = {}
        self.pending_requests: List[Dict[str, Any]] = []
        logger.info("✅ 临时Agent创建器初始化完成")
    
    def create_temporary_agent_config(
        self,
        required_capabilities: List[AgentCapability],
        suggested_name: str,
        suggested_description: str
    ) -> Dict[str, Any]:
        """创建临时Agent配置"""
        agent_id = f"temp_{uuid.uuid4().hex[:8]}"
        
        config = {
            "agent_id": agent_id,
            "name": suggested_name,
            "description": suggested_description,
            "capabilities": [cap.value for cap in required_capabilities],
            "is_temporary": True,
            "created_at": datetime.now().isoformat(),
            "requires_supervision": True,
            "human_review_threshold": 0.7
        }
        
        self.temporary_agents[agent_id] = config
        
        # 通知管理员
        self._notify_admin_for_new_agent(agent_id, config)
        
        logger.info(f"🛠️ 创建临时Agent配置: {agent_id}")
        return config
    
    def _notify_admin_for_new_agent(self, agent_id: str, config: Dict[str, Any]):
        """通知管理员添加标准Agent"""
        request = {
            "request_id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "agent_config": config,
            "request_time": datetime.now().isoformat(),
            "status": "pending"
        }
        self.pending_requests.append(request)
        logger.warning(f"⚠️ 管理员通知: 需要添加新Agent {config['name']}")
    
    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """获取待处理的Agent添加请求"""
        return [r for r in self.pending_requests if r["status"] == "pending"]
    
    def approve_agent_request(self, request_id: str, make_permanent: bool = False) -> bool:
        """审批Agent添加请求"""
        for request in self.pending_requests:
            if request["request_id"] == request_id:
                request["status"] = "approved"
                if make_permanent:
                    request["make_permanent"] = True
                logger.info(f"✅ Agent添加请求已批准: {request_id}")
                return True
        return False


# ==========================================
# 全局实例
# ==========================================

_group_coordinator = None
_temp_agent_creator = None

def get_group_coordinator() -> GroupCollaborationCoordinator:
    """获取协作协调器单例"""
    global _group_coordinator
    if _group_coordinator is None:
        _group_coordinator = GroupCollaborationCoordinator()
    return _group_coordinator

def get_temp_agent_creator() -> TemporaryAgentCreator:
    """获取临时Agent创建器单例"""
    global _temp_agent_creator
    if _temp_agent_creator is None:
        _temp_agent_creator = TemporaryAgentCreator()
    return _temp_agent_creator

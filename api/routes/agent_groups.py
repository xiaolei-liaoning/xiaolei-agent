"""Agent小组管理API

提供真正的Agent小组功能：
- 小组包含多个Agent
- 每个Agent有自己的角色和技能
- 支持混合Agent（人物Agent + 功能Agent）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import logging
import re
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-groups", tags=["Agent小组管理"])

# 全局内存存储（生产环境应该用数据库）
_agent_groups = {}


# ==========================================
# 数据模型
# ==========================================

class AgentSkill(BaseModel):
    """Agent使用的技能"""
    skill_id: str = Field(..., description="技能ID")
    skill_name: str = Field(..., description="技能名称")
    enabled: bool = Field(default=True, description="是否启用")


class AgentInGroup(BaseModel):
    """小组中的Agent"""
    agent_id: str = Field(..., description="Agent唯一标识")
    agent_type: str = Field(..., description="Agent类型（character/tool）")
    agent_name: str = Field(..., description="Agent名称")
    description: str = Field(default="", description="Agent描述")
    skills: List[AgentSkill] = Field(default_factory=list, description="Agent技能列表")
    priority: float = Field(default=1.0, description="优先级（0-1）")
    enabled: bool = Field(default=True, description="是否启用")


class AgentGroupCreate(BaseModel):
    """创建Agent小组请求"""
    name: str = Field(..., description="小组名称")
    description: str = Field(default="", description="小组描述")
    agents: List[AgentInGroup] = Field(..., description="Agent列表")
    strategy: str = Field(default="pipeline", description="协作模式：pipeline/parallel_review/master_slave/dynamic_auction")
    failure_strategy: Optional[str] = Field(None, description="失败处理策略")
    circuit_strategy: Optional[str] = Field(None, description="熔断策略")
    timeout: Optional[float] = Field(None, description="超时时间")
    circuit_breaker: bool = Field(default=False, description="熔断机制")
    elastic_scaling: bool = Field(default=False, description="弹性伸缩")
    
    @validator('name')
    def validate_name(cls, v):
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_\-()\u3002\uff0c\uff1a\uff1b\uff01\uff1f]{2,100}$', v):
            raise ValueError('小组名称只能包含中文、英文、数字、下划线、连字符，2-100字符')
        return v.strip()
    
    @validator('agents')
    def validate_agents(cls, v):
        if not v:
            raise ValueError('小组至少需要1个Agent')
        agent_ids = [a.agent_id for a in v]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError('Agent ID不能重复')
        return v


class AgentGroupUpdate(BaseModel):
    """更新Agent小组请求"""
    name: Optional[str] = Field(None, description="小组名称")
    description: Optional[str] = Field(None, description="小组描述")
    agents: Optional[List[AgentInGroup]] = Field(None, description="Agent列表")
    strategy: Optional[str] = Field(None, description="调度策略")
    circuit_breaker: Optional[bool] = Field(None, description="熔断机制")
    elastic_scaling: Optional[bool] = Field(None, description="弹性伸缩")


class AgentGroup(BaseModel):
    """Agent小组"""
    group_id: str = Field(..., description="小组ID")
    name: str = Field(..., description="小组名称")
    description: str = Field(..., description="小组描述")
    agents: List[AgentInGroup] = Field(..., description="Agent列表")
    strategy: str = Field(..., description="调度策略")
    failure_strategy: Optional[str] = Field(None, description="失败处理策略")
    circuit_strategy: Optional[str] = Field(None, description="熔断策略")
    timeout: Optional[float] = Field(None, description="超时时间")
    circuit_breaker: bool = Field(..., description="熔断机制")
    elastic_scaling: bool = Field(..., description="弹性伸缩")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    status: str = Field(default="active", description="状态")
    task_count: int = Field(default=0, description="任务计数")
    success_rate: float = Field(default=1.0, description="成功率")


# ==========================================
# 系统预定义Agent列表
# ==========================================

# 人物Agent（从skills/人物目录加载 + 自定义角色）
def get_character_agents() -> List[Dict[str, Any]]:
    """获取人物Agent列表"""
    character_agents = []
    
    # 1. 从skills/人物目录加载
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills", "人物")
    
    if os.path.exists(skills_dir):
        character_dirs = [d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d)) and not d.startswith(".")]
        
        # 人物Agent与名称的映射
        character_names = {
            "bestfriend": "知心闺蜜",
            "first_love": "初恋",
            "goddess": "女神",
            "john_carmack": "John Carmack",
            "libai": "李白",
            "linus_torvalds": "Linus Torvalds"
        }
        
        for character in character_dirs:
            agent_id = f"character_{character}"
            character_name = character_names.get(character, character)
            character_agents.append({
                "agent_id": agent_id,
                "agent_type": "character",
                "agent_name": character_name,
                "description": f"{character_name}角色Agent",
                "skills": [],
                "priority": 1.0,
                "enabled": True
            })
    
    # 2. 添加更多自定义角色Agent
    additional_characters = [
        {
            "agent_id": "character_scientist",
            "agent_type": "character",
            "agent_name": "爱因斯坦",
            "description": "天才科学家，擅长逻辑推理和创新思维",
            "skills": [],
            "priority": 1.0,
            "enabled": True
        },
        {
            "agent_id": "character_artist",
            "agent_type": "character",
            "agent_name": "达芬奇",
            "description": "艺术大师，擅长创意和审美",
            "skills": [],
            "priority": 1.0,
            "enabled": True
        },
        {
            "agent_id": "character_writer",
            "agent_type": "character",
            "agent_name": "莎士比亚",
            "description": "文学巨匠，擅长写作和表达",
            "skills": [],
            "priority": 1.0,
            "enabled": True
        },
        {
            "agent_id": "character_teacher",
            "agent_type": "character",
            "agent_name": "苏格拉底",
            "description": "伟大的老师，擅长提问和启发",
            "skills": [],
            "priority": 1.0,
            "enabled": True
        },
        {
            "agent_id": "character_warrior",
            "agent_type": "character",
            "agent_name": "诸葛亮",
            "description": "智慧军师，擅长策略和规划",
            "skills": [],
            "priority": 1.0,
            "enabled": True
        },
        {
            "agent_id": "character_explorer",
            "agent_type": "character",
            "agent_name": "哥伦布",
            "description": "探索家，擅长发现和探索新事物",
            "skills": [],
            "priority": 1.0,
            "enabled": True
        },
        {
            "agent_id": "character_doctor",
            "agent_type": "character",
            "agent_name": "华佗",
            "description": "神医，擅长诊断和解决问题",
            "skills": [],
            "priority": 1.0,
            "enabled": True
        },
        {
            "agent_id": "character_philosopher",
            "agent_type": "character",
            "agent_name": "老子",
            "description": "哲学家，擅长思考和洞察",
            "skills": [],
            "priority": 1.0,
            "enabled": True
        }
    ]
    
    character_agents.extend(additional_characters)
    
    return character_agents


# 工具Agent（从技能系统获取）
def get_tool_agents() -> List[Dict[str, Any]]:
    """获取工具Agent列表"""
    tool_agents = []
    
    # 工具Agent列表（使用真实存在的skill_id）
    tool_agent_defs = [
        {
            "agent_id": "tool_scraper",
            "agent_type": "tool",
            "agent_name": "爬虫专家",
            "description": "网页内容爬取和分析（微博、B站、知乎、抖音等）",
            "skills": ["web_scraper", "search_engine"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_analyzer",
            "agent_type": "tool",
            "agent_name": "数据分析员",
            "description": "数据统计、可视化、词云、趋势预测",
            "skills": ["data_analysis", "calculator"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_translator",
            "agent_type": "tool",
            "agent_name": "翻译官",
            "description": "11种语言互译，自动语言检测",
            "skills": ["translator"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_deep_thinker",
            "agent_type": "tool",
            "agent_name": "深度思考者",
            "description": "深度分析、自主搜索、验证闭环",
            "skills": ["deep_thinking", "search_engine"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_system_helper",
            "agent_type": "tool",
            "agent_name": "系统助手",
            "description": "系统信息查询、文件操作、进程管理",
            "skills": ["system_toolbox", "calculator"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_weatherman",
            "agent_type": "tool",
            "agent_name": "天气预报员",
            "description": "全球城市天气查询，未来3天预报",
            "skills": ["weather"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_automation_engineer",
            "agent_type": "tool",
            "agent_name": "自动化工程师",
            "description": "GUI自动化、工作流、全链路自动化",
            "skills": ["gui_automation", "advanced_automation"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_researcher",
            "agent_type": "tool",
            "agent_name": "研究员",
            "description": "RAG知识检索、资料整理",
            "skills": ["rag_search", "search_engine"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_calculator",
            "agent_type": "tool",
            "agent_name": "计算器",
            "description": "数学计算、统计计算",
            "skills": ["calculator"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_text_analyzer",
            "agent_type": "tool",
            "agent_name": "文本分析师",
            "description": "文本分析、拆解、摘要、标题生成",
            "skills": ["text_analyzer"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_orchestrator",
            "agent_type": "tool",
            "agent_name": "任务编排师",
            "description": "多步任务编排、协调、执行",
            "skills": ["multi_step", "advanced_automation"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_chatbot",
            "agent_type": "tool",
            "agent_name": "聊天助手",
            "description": "日常聊天、问答、陪伴",
            "skills": ["chat"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_ocr_expert",
            "agent_type": "tool",
            "agent_name": "OCR识别专家",
            "description": "文字识别、图像转文字",
            "skills": ["ocr_recognition"],
            "priority": 1.0
        },
        {
            "agent_id": "tool_openclaw",
            "agent_type": "tool",
            "agent_name": "OpenClaw工具",
            "description": "OpenClaw生态工具集",
            "skills": ["openclaw"],
            "priority": 1.0
        }
    ]
    
    for agent_def in tool_agent_defs:
        agent_skills = []
        for skill_id in agent_def.get("skills", []):
            agent_skills.append({
                "skill_id": skill_id,
                "skill_name": skill_id,
                "enabled": True
            })
        
        tool_agents.append({
            "agent_id": agent_def["agent_id"],
            "agent_type": agent_def["agent_type"],
            "agent_name": agent_def["agent_name"],
            "description": agent_def["description"],
            "skills": agent_skills,
            "priority": agent_def["priority"],
            "enabled": True
        })
    
    return tool_agents


# ==========================================
# API端点
# ==========================================

@router.get("/available-agents")
async def get_available_agents():
    """获取系统可用的所有Agent列表"""
    character_agents = get_character_agents()
    tool_agents = get_tool_agents()
    
    return {
        "success": True,
        "data": {
            "character_agents": character_agents,
            "tool_agents": tool_agents,
            "total_count": len(character_agents) + len(tool_agents)
        }
    }


@router.post("")
async def create_agent_group(group: AgentGroupCreate):
    """创建新的Agent小组"""
    group_id = str(uuid.uuid4())
    
    agent_group = AgentGroup(
        group_id=group_id,
        name=group.name,
        description=group.description,
        agents=group.agents,
        strategy=group.strategy,
        failure_strategy=group.failure_strategy,
        circuit_strategy=group.circuit_strategy,
        timeout=group.timeout,
        circuit_breaker=group.circuit_breaker,
        elastic_scaling=group.elastic_scaling,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        status="active",
        task_count=0,
        success_rate=1.0
    )
    
    _agent_groups[group_id] = agent_group
    logger.info(f"创建Agent小组成功: {group.name} ({group_id})")
    
    return {
        "success": True,
        "data": agent_group
    }


@router.get("")
async def get_all_agent_groups():
    """获取所有Agent小组"""
    return {
        "success": True,
        "data": list(_agent_groups.values())
    }


@router.get("/{group_id}")
async def get_agent_group(group_id: str):
    """获取指定的Agent小组"""
    if group_id not in _agent_groups:
        raise HTTPException(status_code=404, detail="Agent小组不存在")
    return {
        "success": True,
        "data": _agent_groups[group_id]
    }


@router.put("/{group_id}")
async def update_agent_group(group_id: str, group_update: AgentGroupUpdate):
    """更新Agent小组"""
    if group_id not in _agent_groups:
        raise HTTPException(status_code=404, detail="Agent小组不存在")
    
    group = _agent_groups[group_id]
    
    update_data = group_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)
    
    group.updated_at = datetime.now()
    logger.info(f"更新Agent小组成功: {group.name}")
    
    return {
        "success": True,
        "data": group
    }


@router.delete("/{group_id}")
async def delete_agent_group(group_id: str):
    """删除Agent小组"""
    if group_id not in _agent_groups:
        raise HTTPException(status_code=404, detail="Agent小组不存在")
    
    group_name = _agent_groups[group_id].name
    del _agent_groups[group_id]
    logger.info(f"删除Agent小组成功: {group_name}")
    
    return {
        "success": True,
        "message": f"Agent小组 {group_name} 已删除"
    }


@router.post("/{group_id}/activate")
async def activate_agent_group(group_id: str):
    """激活Agent小组"""
    if group_id not in _agent_groups:
        raise HTTPException(status_code=404, detail="Agent小组不存在")
    
    group = _agent_groups[group_id]
    group.status = "active"
    group.updated_at = datetime.now()
    
    logger.info(f"激活Agent小组: {group.name}")
    return {
        "success": True,
        "data": {
            "group_id": group_id,
            "status": "active"
        }
    }


@router.post("/{group_id}/deactivate")
async def deactivate_agent_group(group_id: str):
    """停用Agent小组"""
    if group_id not in _agent_groups:
        raise HTTPException(status_code=404, detail="Agent小组不存在")
    
    group = _agent_groups[group_id]
    group.status = "inactive"
    group.updated_at = datetime.now()
    
    logger.info(f"停用Agent小组: {group.name}")
    return {
        "success": True,
        "data": {
            "group_id": group_id,
            "status": "inactive"
        }
    }


@router.get("/{group_id}/stats")
async def get_agent_group_stats(group_id: str):
    """获取Agent小组统计信息"""
    if group_id not in _agent_groups:
        raise HTTPException(status_code=404, detail="Agent小组不存在")
    
    group = _agent_groups[group_id]
    
    return {
        "success": True,
        "data": {
            "group_id": group_id,
            "name": group.name,
            "agent_count": len(group.agents),
            "enabled_agent_count": len([a for a in group.agents if a.enabled]),
            "task_count": group.task_count,
            "success_rate": group.success_rate,
            "status": group.status,
            "created_at": group.created_at,
            "updated_at": group.updated_at
        }
    }


# ==========================================
# 小组执行API（与planning_agent集成）
# ==========================================

class GroupExecuteRequest(BaseModel):
    """小组执行请求"""
    message: str
    use_agents: Optional[List[str]] = None  # 指定使用某些agent，None表示全部
    strategy: Optional[str] = None  # 调度策略：priority, weighted_round_robin, collaborative, round_robin
    failure_strategy: Optional[str] = None  # 失败处理策略：fast_fail, retry, degrade, fallback
    circuit_strategy: Optional[str] = None  # 熔断策略：count_based, rate_based, time_based
    timeout: Optional[float] = None  # 超时时间（秒）


# 全局变量：当前选择的小组
_current_group_id: Optional[str] = None


@router.get("/current/selected")
async def get_current_group():
    """获取当前选择的小组"""
    if _current_group_id and _current_group_id in _agent_groups:
        return {
            "success": True,
            "data": {
                "group": _agent_groups[_current_group_id]
            }
        }
    return {
        "success": False,
        "data": {
            "group": None
        }
    }


@router.post("/current/select")
async def select_current_group(group_id: str):
    """选择当前小组"""
    global _current_group_id
    
    if group_id not in _agent_groups:
        raise HTTPException(status_code=404, detail="Agent小组不存在")
    
    _current_group_id = group_id
    logger.info(f"已选择小组: {_agent_groups[group_id].name}")
    
    return {
        "success": True,
        "data": {
            "group_id": group_id,
            "group": _agent_groups[group_id]
        }
    }


@router.post("/current/execute")
async def execute_with_current_group(request: GroupExecuteRequest):
    """使用当前选择的小组执行任务"""
    global _current_group_id
    
    if not _current_group_id or _current_group_id not in _agent_groups:
        raise HTTPException(status_code=400, detail="请先选择一个Agent小组")
    
    group = _agent_groups[_current_group_id]
    
    # 使用小组配置作为默认值
    final_strategy = request.strategy or group.strategy
    final_failure_strategy = request.failure_strategy or getattr(group, 'failure_strategy', None)
    final_circuit_strategy = request.circuit_strategy or getattr(group, 'circuit_strategy', None)
    final_timeout = request.timeout or getattr(group, 'timeout', None)
    
    logger.info(f"小组 {group.name} 开始执行任务，策略: {final_strategy}, "
                f"失败策略: {final_failure_strategy}, 熔断策略: {final_circuit_strategy}, 超时: {final_timeout}")
    
    # 已迁移至 JS Workflow 编排系统
    raise HTTPException(
        status_code=410,
        detail="AgentGroupExecutor 已移除，请使用 JS Workflow (core/multi_agent_v2/workflow/js_workflow.py)"
    )


@router.post("/{group_id}/execute")
async def execute_with_group(group_id: str, request: GroupExecuteRequest):
    """使用指定的小组执行任务"""
    if group_id not in _agent_groups:
        raise HTTPException(status_code=404, detail="Agent小组不存在")
    
    group = _agent_groups[group_id]
    
    # 使用小组配置作为默认值
    final_strategy = request.strategy or group.strategy
    final_failure_strategy = request.failure_strategy or getattr(group, 'failure_strategy', None)
    final_circuit_strategy = request.circuit_strategy or getattr(group, 'circuit_strategy', None)
    final_timeout = request.timeout or getattr(group, 'timeout', None)
    
    logger.info(f"小组 {group.name} 开始执行任务，策略: {final_strategy}, "
                f"失败策略: {final_failure_strategy}, 熔断策略: {final_circuit_strategy}, 超时: {final_timeout}")
    
    # 已迁移至 JS Workflow 编排系统
    raise HTTPException(
        status_code=410,
        detail="AgentGroupExecutor 已移除，请使用 JS Workflow (core/multi_agent_v2/workflow/js_workflow.py)"
    )


# ==========================================
# 初始化一些示例数据
# ==========================================

def _initialize_sample_groups():
    """初始化示例Agent小组"""
    # 获取可用Agent
    character_agents = get_character_agents()
    tool_agents = get_tool_agents()
    
    # 创建示例小组1：技术评审团队 - 并行评审模式
    review_team_agents = []
    
    # 添加Linus Torvalds（技术专家）
    linus_agent = next((a for a in character_agents if a["agent_id"] == "character_linus_torvalds"), None)
    if linus_agent:
        review_team_agents.append(AgentInGroup(**{
            **linus_agent,
            "skills": [
                AgentSkill(skill_id="review", skill_name="代码评审", enabled=True),
                AgentSkill(skill_id="system_toolbox", skill_name="系统工具箱", enabled=True)
            ]
        }))
    
    # 添加苏格拉底（提问和启发）
    socrates_agent = next((a for a in character_agents if a["agent_id"] == "character_teacher"), None)
    if socrates_agent:
        review_team_agents.append(AgentInGroup(**{
            **socrates_agent,
            "skills": [
                AgentSkill(skill_id="review", skill_name="评审", enabled=True),
                AgentSkill(skill_id="search_engine", skill_name="搜索引擎", enabled=True)
            ]
        }))
    
    # 添加深度思考者
    deep_thinker_agent = next((a for a in tool_agents if a["agent_id"] == "tool_deep_thinker"), None)
    if deep_thinker_agent:
        review_team_agents.append(AgentInGroup(**deep_thinker_agent))
    
    if review_team_agents:
        review_team = AgentGroup(
            group_id=str(uuid.uuid4()),
            name="技术评审团队",
            description="代码审查和技术方案评审团队，多专家并行评审",
            agents=review_team_agents,
            strategy="parallel_review",
            circuit_breaker=True,
            elastic_scaling=False
        )
        _agent_groups[review_team.group_id] = review_team
    
    # 创建示例小组2：创意流水线团队 - 流水线模式
    pipeline_team_agents = []
    
    # 添加达芬奇（创意设计）
    davinci_agent = next((a for a in character_agents if a["agent_id"] == "character_artist"), None)
    if davinci_agent:
        pipeline_team_agents.append(AgentInGroup(**{
            **davinci_agent,
            "skills": [
                AgentSkill(skill_id="creative_writing", skill_name="创意写作", enabled=True),
                AgentSkill(skill_id="search_engine", skill_name="搜索引擎", enabled=True)
            ]
        }))
    
    # 添加莎士比亚（文学创作）
    shakespeare_agent = next((a for a in character_agents if a["agent_id"] == "character_writer"), None)
    if shakespeare_agent:
        pipeline_team_agents.append(AgentInGroup(**{
            **shakespeare_agent,
            "skills": [
                AgentSkill(skill_id="writing", skill_name="写作", enabled=True),
                AgentSkill(skill_id="text_analyzer", skill_name="文本分析", enabled=True)
            ]
        }))
    
    # 添加李白（诗歌创作）
    libai_agent = next((a for a in character_agents if a["agent_id"] == "character_libai"), None)
    if libai_agent:
        pipeline_team_agents.append(AgentInGroup(**{
            **libai_agent,
            "skills": [
                AgentSkill(skill_id="translation", skill_name="翻译", enabled=True),
                AgentSkill(skill_id="writing", skill_name="写作", enabled=True)
            ]
        }))
    
    if pipeline_team_agents:
        pipeline_team = AgentGroup(
            group_id=str(uuid.uuid4()),
            name="创意流水线团队",
            description="创意设计、写作、翻译流水线协作",
            agents=pipeline_team_agents,
            strategy="pipeline",
            circuit_breaker=False,
            elastic_scaling=False
        )
        _agent_groups[pipeline_team.group_id] = pipeline_team
    
    # 创建示例小组3：科学研究团队 - 主从协作模式
    science_team_agents = []
    
    # 添加爱因斯坦（主Agent - 任务拆解）
    einstein_agent = next((a for a in character_agents if a["agent_id"] == "character_scientist"), None)
    if einstein_agent:
        science_team_agents.append(AgentInGroup(**{
            **einstein_agent,
            "skills": [
                AgentSkill(skill_id="deep_thinking", skill_name="深度思考", enabled=True),
                AgentSkill(skill_id="calculator", skill_name="计算器", enabled=True)
            ]
        }))
    
    # 添加研究员
    researcher_agent = next((a for a in tool_agents if a["agent_id"] == "tool_researcher"), None)
    if researcher_agent:
        science_team_agents.append(AgentInGroup(**researcher_agent))
    
    # 添加计算器
    calculator_agent = next((a for a in tool_agents if a["agent_id"] == "tool_calculator"), None)
    if calculator_agent:
        science_team_agents.append(AgentInGroup(**calculator_agent))
    
    # 添加数据分析员
    analyzer_agent = next((a for a in tool_agents if a["agent_id"] == "tool_analyzer"), None)
    if analyzer_agent:
        science_team_agents.append(AgentInGroup(**analyzer_agent))
    
    if science_team_agents:
        science_team = AgentGroup(
            group_id=str(uuid.uuid4()),
            name="科学研究团队",
            description="科学研究、深度思考和数据分析团队，主从协作模式",
            agents=science_team_agents,
            strategy="master_slave",
            circuit_breaker=True,
            elastic_scaling=False
        )
        _agent_groups[science_team.group_id] = science_team
    
    logger.info(f"初始化示例Agent小组完成，共 {len(_agent_groups)} 个小组")


# 初始化示例数据
_initialize_sample_groups()

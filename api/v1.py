"""统一API v1接口规范

前后端完全解耦，提供RESTful风格的统一接口：
- 所有接口以 /api/v1 为前缀
- 统一的响应格式
- 版本控制和向后兼容
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import time
import logging

logger = logging.getLogger(__name__)

# 创建v1路由器
router_v1 = APIRouter(prefix="/api/v1", tags=["API v1"])


# ============================================================================
# 通用响应模型
# ============================================================================

class APIResponse(BaseModel):
    """统一API响应模型"""
    success: bool = Field(..., description="是否成功")
    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="响应消息")
    data: Optional[Any] = Field(default=None, description="响应数据")
    timestamp: float = Field(default_factory=time.time, description="时间戳")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    success: bool = False
    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    error_details: Optional[str] = Field(default=None, description="详细错误信息")
    timestamp: float = Field(default_factory=time.time)


# ============================================================================
# 任务相关接口
# ============================================================================

class TaskDecomposeRequest(BaseModel):
    """任务拆解请求"""
    task_description: str = Field(..., description="任务描述")


@router_v1.post("/tasks/decompose", response_model=APIResponse, summary="任务拆解")
async def decompose_task(request: TaskDecomposeRequest):
    """使用双层策略拆解任务
    
    - 第一层：规则引擎快速匹配
    - 第二层：LLM智能泛化
    - 第三层：兜底方案
    """
    try:
        from core.task_decomposer import get_task_decomposer
        
        decomposer = get_task_decomposer()
        result = await decomposer.decompose(request.task_description)
        
        return APIResponse(
            success=True,
            data={
                "path": result.path.value,
                "subtasks_count": len(result.subtasks),
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "subtasks": [
                    {
                        "id": st.id,
                        "action": st.action,
                        "params": st.params,
                        "priority": st.priority
                    }
                    for st in result.subtasks
                ]
            }
        )
    except Exception as e:
        logger.error(f"任务拆解失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Planning Agent 任务执行接口
# ============================================================================

class TaskExecuteRequest(BaseModel):
    """任务执行请求"""
    task_description: str = Field(..., description="自然语言任务描述")


@router_v1.post("/tasks/execute", response_model=APIResponse, summary="执行任务")
async def execute_task(request: TaskExecuteRequest):
    """使用 Planning Agent 执行复杂任务
    
    - 自动分解任务为子任务
    - 智能规划执行顺序
    - 并行执行无依赖任务
    - 汇总执行结果
    
    示例任务：
    - "爬取微博热搜并分析趋势"
    - "打开浏览器搜索Python教程"
    - "发送邮件给test@example.com报告结果"
    """
    try:
        from planning_agent import planning_agent
        
        result = await planning_agent.execute(request.task_description)
        
        return APIResponse(
            success=result["success"],
            message=result["message"],
            data={
                "total_tasks": result["total_tasks"],
                "completed_tasks": result["completed_tasks"],
                "results": result["results"]
            }
        )
    except Exception as e:
        logger.error(f"任务执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Agent路由接口
# ============================================================================

@router_v1.get("/agents/status", response_model=APIResponse, summary="获取Agent状态")
async def get_agents_status():
    """获取所有Agent的状态和路由评分"""
    try:
        from core.agent_coordinator import get_agent_coordinator
        
        coordinator = get_agent_coordinator()
        status = await coordinator.get_agent_status()
        
        return APIResponse(
            success=True,
            data=status
        )
    except Exception as e:
        logger.error(f"获取Agent状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AgentRouteRequest(BaseModel):
    """Agent路由请求"""
    task_type: str = Field(..., description="任务类型")
    candidate_agents: Optional[List[str]] = Field(None, description="候选Agent列表")


@router_v1.post("/agents/route", response_model=APIResponse, summary="Agent路由选择")
async def route_to_agent(request: AgentRouteRequest):
    """使用多维加权模型选择最优Agent"""
    try:
        from core.agent_coordinator import get_agent_coordinator
        
        coordinator = get_agent_coordinator()
        best_agent = coordinator.router.select_best_agent(
            task_type=request.task_type,
            candidate_agents=request.candidate_agents
        )
        
        if not best_agent:
            return APIResponse(
                success=False,
                code=404,
                message="没有可用的Agent",
                data=None
            )
        
        score = coordinator.router.agent_metrics[best_agent].calculate_routing_score()
        
        return APIResponse(
            success=True,
            data={
                "selected_agent": best_agent,
                "routing_score": score,
                "all_scores": coordinator.router.get_all_scores()
            }
        )
    except Exception as e:
        logger.error(f"Agent路由失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 向量存储接口
# ============================================================================

@router_v1.post("/memory/backup", response_model=APIResponse, summary="备份向量存储")
async def backup_memory():
    """手动触发向量存储备份"""
    try:
        from core.vector_memory import VectorMemoryStore
        
        store = VectorMemoryStore()
        success = store.backup_memory()
        
        return APIResponse(
            success=success,
            message="备份成功" if success else "备份失败",
            data={"backup_enabled": True}
        )
    except Exception as e:
        logger.error(f"备份失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_v1.get("/memory/stats", response_model=APIResponse, summary="获取内存统计")
async def get_memory_stats():
    """获取向量存储的统计信息"""
    try:
        from core.vector_memory import VectorMemoryStore
        
        store = VectorMemoryStore()
        stats = store.get_memory_stats()
        
        return APIResponse(
            success=True,
            data=stats
        )
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_v1.post("/memory/optimize", response_model=APIResponse, summary="优化内存存储")
async def optimize_memory():
    """执行内存优化（清理旧记忆+备份）"""
    try:
        from core.vector_memory import VectorMemoryStore
        
        store = VectorMemoryStore()
        result = store.optimize_memory()
        
        return APIResponse(
            success=result["success"],
            message="优化成功" if result["success"] else "优化失败",
            data=result
        )
    except Exception as e:
        logger.error(f"内存优化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BFS文本处理接口
# ============================================================================

class BFSTextProcessRequest(BaseModel):
    """BFS文本处理请求"""
    text: str = Field(..., description="待处理的文本")
    max_depth: int = Field(default=5, description="最大深度")
    max_nodes: int = Field(default=100, description="最大节点数")


@router_v1.post("/bfs/process", response_model=APIResponse, summary="BFS文本处理")
async def process_text_bfs(request: BFSTextProcessRequest):
    """使用BFS处理器处理文本"""
    try:
        from core.bfs_processor import get_bfs_processor
        
        processor = get_bfs_processor(
            max_depth=request.max_depth, 
            max_nodes=request.max_nodes
        )
        result = processor.process_text(request.text)
        
        return APIResponse(
            success=result["success"],
            message="处理成功" if result["success"] else "处理失败",
            data=result
        )
    except Exception as e:
        logger.error(f"BFS处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RAG搜索接口
# ============================================================================

class RAGSearchRequest(BaseModel):
    """RAG搜索请求"""
    query: str = Field(..., description="搜索查询")
    user_id: int = Field(default=1, description="用户ID")
    learn: bool = Field(default=True, description="是否学习")
    max_results: int = Field(default=5, description="最大结果数")


@router_v1.post("/rag/search", response_model=APIResponse, summary="RAG搜索")
async def rag_search(request: RAGSearchRequest):
    """执行RAG智能搜索"""
    try:
        from core.rag_search_engine import RAGSearchEngine
        
        engine = RAGSearchEngine()
        result = await engine.search_and_learn(
            query=request.query,
            user_id=request.user_id,
            learn=request.learn,
            max_results=request.max_results
        )
        
        return APIResponse(
            success=True,
            data=result
        )
    except Exception as e:
        logger.error(f"RAG搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TopicSearchRequest(BaseModel):
    """主题搜索请求"""
    topic: str = Field(..., description="主题名称")
    user_id: int = Field(default=1, description="用户ID")
    max_results: int = Field(default=10, description="最大结果数")


@router_v1.get("/rag/topics", response_model=APIResponse, summary="按主题搜索")
async def search_by_topic(
    topic: str = Query(..., description="主题名称"),
    user_id: int = Query(default=1, description="用户ID"),
    max_results: int = Query(default=10, description="最大结果数")
):
    """按主题搜索知识"""
    try:
        from core.rag_search_engine import RAGSearchEngine
        
        engine = RAGSearchEngine()
        result = await engine.search_by_topic(
            topic=topic,
            user_id=user_id,
            max_results=max_results
        )
        
        return APIResponse(
            success=True,
            data=result
        )
    except Exception as e:
        logger.error(f"主题搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_v1.get("/rag/summary", response_model=APIResponse, summary="获取知识摘要")
async def get_knowledge_summary(topic: Optional[str] = None):
    """获取知识库摘要"""
    try:
        from core.rag_search_engine import RAGSearchEngine
        
        engine = RAGSearchEngine()
        summary = engine.get_knowledge_summary(topic=topic)
        
        return APIResponse(
            success=True,
            data=summary
        )
    except Exception as e:
        logger.error(f"获取摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_v1.get("/rag/stats", response_model=APIResponse, summary="RAG统计信息")
async def get_rag_stats():
    """获取RAG引擎统计信息"""
    try:
        from core.rag_search_engine import RAGSearchEngine
        
        engine = RAGSearchEngine()
        stats = engine.get_stats()
        
        return APIResponse(
            success=True,
            data=stats
        )
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 健康检查
# ============================================================================

@router_v1.get("/health", response_model=APIResponse, summary="健康检查")
async def health_check():
    """API v1健康检查"""
    return APIResponse(
        success=True,
        message="API v1 is healthy",
        data={
            "version": "v1.0.0",
            "status": "running"
        }
    )

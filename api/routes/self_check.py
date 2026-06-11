"""自我校验中间件 API 路由

提供RESTful API接口，方便前端和其他服务调用自我校验功能。

API端点:
- POST /api/v1/self-check/check - 执行自我校验
- GET /api/v1/self-check/stats - 获取统计信息
- POST /api/v1/self-check/batch - 批量处理
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import time
import logging

from core.results.self_check_middleware import SelfCheckMiddleware, get_self_check_middleware
from core.engine.llm_backend import get_llm_router

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(
    prefix="/api/v1/self-check",
    tags=["self-check"],
    responses={404: {"description": "Not found"}},
)

# 全局中间件实例
_middleware: Optional[SelfCheckMiddleware] = None
_llm_router = None


def get_middleware() -> SelfCheckMiddleware:
    """获取或创建中间件实例。"""
    global _middleware
    if _middleware is None:
        _middleware = get_self_check_middleware()
    return _middleware


def get_llm():
    """获取LLM路由器。"""
    global _llm_router
    if _llm_router is None:
        _llm_router = get_llm_router()
    return _llm_router


# ============================================================
# 数据模型
# ============================================================

class SelfCheckRequest(BaseModel):
    """自我校验请求模型。"""
    
    user_query: str = Field(..., description="用户问题", min_length=1, max_length=5000)
    pass_score: int = Field(80, description="合格分数线 (0-100)", ge=0, le=100)
    max_retry: int = Field(3, description="最大重试次数", ge=1, le=10)
    temperature: float = Field(0.7, description="生成温度", ge=0.0, le=2.0)
    system_prompt: Optional[str] = Field(None, description="系统提示词", max_length=2000)
    custom_check_prompt: Optional[str] = Field(None, description="自定义评审提示词", max_length=5000)
    enable_logging: bool = Field(True, description="是否启用日志")


class SelfCheckResponse(BaseModel):
    """自我校验响应模型。"""
    
    success: bool = Field(..., description="是否成功")
    answer: str = Field(..., description="最终答案")
    score: int = Field(..., description="最终得分")
    retry_count: int = Field(..., description="重试次数")
    is_passed: bool = Field(..., description="是否通过校验")
    history: List[Dict[str, Any]] = Field(default_factory=list, description="优化历史")
    total_time: float = Field(..., description="总耗时(秒)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    error: Optional[str] = Field(None, description="错误信息（如果有）")


class BatchCheckRequest(BaseModel):
    """批量校验请求模型。"""
    
    queries: List[str] = Field(..., description="问题列表", min_length=1, max_length=50)
    pass_score: int = Field(80, description="合格分数线", ge=0, le=100)
    max_retry: int = Field(3, description="最大重试次数", ge=1, le=10)


class BatchCheckResponse(BaseModel):
    """批量校验响应模型。"""
    
    success: bool = Field(..., description="是否成功")
    results: List[SelfCheckResponse] = Field(..., description="结果列表")
    summary: Dict[str, Any] = Field(..., description="汇总统计")


# ============================================================
# API 端点
# ============================================================

@router.post("/check", response_model=SelfCheckResponse)
async def perform_self_check(request: SelfCheckRequest):
    """执行自我校验与循环优化。
    
    对给定的用户问题进行LLM回答生成，并通过自我校验机制确保质量。
    
    **使用示例:**
    ```python
    import requests
    
    response = requests.post(
        "http://localhost:8000/api/v1/self-check/check",
        json={
            "user_query": "什么是量子计算？",
            "pass_score": 80,
            "max_retry": 3
        }
    )
    result = response.json()
    print(f"得分: {result['score']}, 答案: {result['answer']}")
    ```
    """
    try:
        middleware = get_middleware()
        llm_router = get_llm()
        
        # 定义生成函数
        async def generate_answer(query: str, context=None) -> str:
            """根据上下文生成回答。"""
            system_prompt = context.get("system_prompt") if context else None
            temperature = context.get("temperature", 0.7) if context else 0.7
            
            if system_prompt:
                return await llm_router.simple_chat(
                    query,
                    system_prompt=system_prompt,
                    temperature=temperature
                )
            else:
                return await llm_router.simple_chat(
                    query,
                    temperature=temperature
                )
        
        # 准备上下文
        context = {
            "system_prompt": request.system_prompt,
            "temperature": request.temperature,
        }
        
        # 执行自我校验
        result = await middleware.check_and_optimize(
            user_query=request.user_query,
            generate_func=generate_answer,
            context=context,
            custom_prompt_template=request.custom_check_prompt
        )
        
        # 构建响应
        response_data = result.to_dict()
        response_data["success"] = True
        
        return SelfCheckResponse(**response_data)
        
    except Exception as e:
        logger.error(f"自我校验失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"自我校验失败: {str(e)}")


@router.get("/stats")
async def get_self_check_stats():
    """获取自我校验统计信息。
    
    返回自检系统的运行统计数据，包括总检查数、通过率、平均重试次数等。
    
    **使用示例:**
    ```python
    import requests
    
    response = requests.get("http://localhost:8000/api/v1/self-check/stats")
    stats = response.json()
    print(f"总检查数: {stats['total_checks']}")
    print(f"通过率: {stats['pass_rate']}%")
    ```
    """
    try:
        middleware = get_middleware()
        stats = middleware.get_stats()
        
        return {
            "success": True,
            "data": stats,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.post("/batch", response_model=BatchCheckResponse)
async def batch_self_check(request: BatchCheckRequest, background_tasks: BackgroundTasks):
    """批量执行自我校验。
    
    对多个问题并行执行自我校验，适合批量处理场景。
    
    **注意:** 
    - 最多支持50个问题同时处理
    - 建议使用后台任务处理大量请求
    
    **使用示例:**
    ```python
    import requests
    
    response = requests.post(
        "http://localhost:8000/api/v1/self-check/batch",
        json={
            "queries": [
                "什么是Python?",
                "什么是JavaScript?",
                "什么是Java?"
            ],
            "pass_score": 80,
            "max_retry": 2
        }
    )
    results = response.json()
    for result in results['results']:
        print(f"问题得分: {result['score']}")
    ```
    """
    try:
        middleware = get_middleware()
        llm_router = get_llm()
        
        results = []
        total_start_time = time.time()
        
        # 依次处理每个问题（可以改为并行处理）
        for query in request.queries:
            async def generate_answer(q: str, context=None) -> str:
                return await llm_router.simple_chat(
                    q,
                    temperature=0.7
                )
            
            result = await middleware.check_and_optimize(
                user_query=query,
                generate_func=generate_answer
            )
            
            response_data = result.to_dict()
            response_data["success"] = True
            results.append(SelfCheckResponse(**response_data))
        
        total_time = time.time() - total_start_time
        
        # 计算汇总统计
        avg_score = sum(r.score for r in results) / len(results) if results else 0
        avg_retries = sum(r.retry_count for r in results) / len(results) if results else 0
        passed_count = sum(1 for r in results if r.is_passed)
        
        summary = {
            "total_queries": len(request.queries),
            "avg_score": round(avg_score, 2),
            "avg_retries": round(avg_retries, 2),
            "passed_count": passed_count,
            "failed_count": len(results) - passed_count,
            "pass_rate": round(passed_count / len(results) * 100, 2) if results else 0,
            "total_time": round(total_time, 2),
        }
        
        return BatchCheckResponse(
            success=True,
            results=results,
            summary=summary
        )
        
    except Exception as e:
        logger.error(f"批量自我校验失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量自我校验失败: {str(e)}")


@router.post("/reset-stats")
async def reset_self_check_stats():
    """重置自我校验统计信息。
    
    清空所有统计数据，重新开始计数。
    
    **使用示例:**
    ```python
    import requests
    
    response = requests.post("http://localhost:8000/api/v1/self-check/reset-stats")
    print(response.json())
    ```
    """
    try:
        middleware = get_middleware()
        middleware.reset_stats()
        
        return {
            "success": True,
            "message": "统计信息已重置"
        }
        
    except Exception as e:
        logger.error(f"重置统计信息失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重置统计信息失败: {str(e)}")


# ============================================================
# 健康检查
# ============================================================

@router.get("/health")
async def self_check_health():
    """自我校验服务健康检查。"""
    try:
        middleware = get_middleware()
        stats = middleware.get_stats()
        
        return {
            "status": "healthy",
            "service": "self-check-middleware",
            "version": "1.0.0",
            "stats": stats,
            "timestamp": time.time()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }

"""简化聊天 API — 仅 V1 ReAct 模式

提供最简洁的聊天接口：
- V1 队长 ReAct 模式处理
- 无登录/工作流/Skill选择
- 支持历史记录
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["simple_chat"])


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
class SimpleChatRequest(BaseModel):
    """简化聊天请求"""
    message: str = Field(..., min_length=1, description="用户消息")
    user_id: int = Field(default=1, ge=1, description="用户ID")
    agent_id: str = Field(default="v1_react", description="Agent ID")


class SimpleChatResponse(BaseModel):
    """简化聊天响应"""
    reply: str = Field(..., description="回复内容")
    thinking_process: Optional[Dict[str, Any]] = Field(default=None, description="思考过程")
    success: bool = Field(default=True, description="是否成功")


# ---------------------------------------------------------------------------
# 核心聊天 API
# ---------------------------------------------------------------------------
@router.post("/simple/chat", response_model=SimpleChatResponse, summary="简化聊天API")
async def simple_chat(request: SimpleChatRequest) -> SimpleChatResponse:
    """简化聊天 API — 仅使用 V1 ReAct 模式

    特性：
    - V1 队长使用 ReAct 模式（Thought → Action → Observation）
    - 集成 V2 所有工具（write_file, read_file, execute_python 等）
    - 无复杂功能（登录/工作流/Skill选择）
    """
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    start_time = time.time()
    logger.info("📨 简化聊天: %s...", message[:60])

    try:
        # 保存用户消息到 BFS 上下文
        try:
            from core.workflow.bfs_processor import get_bfs_processor
            bfs = get_bfs_processor()
            bfs.add_node(user_id=request.user_id, role="user", content=message)
        except Exception as e:
            logger.debug("保存用户消息到 BFS 失败: %s", e)

        # 使用 V1 队长 ReAct 模式处理
        from core.agent_system import V1LeaderPool

        pool = V1LeaderPool()
        leader, workers = await pool.create_team(worker_count=3, max_workers=5)

        try:
            result = await asyncio.wait_for(
                leader.supervise_task(message, workers, active_count=3, max_rounds=10),
                timeout=120,
            )
        except asyncio.TimeoutError:
            logger.warning("V1 ReAct 超时")
            result = {"success": False, "error": "执行超时", "results": [], "rounds": 0}

        # 清理队伍
        await pool.discard([leader] + workers)

        # 格式化回复
        success = result.get("success", False)
        all_results = result.get("results", [])
        total_rounds = result.get("rounds", 0)
        react_history = result.get("react_history", [])

        # 构建回复文本
        reply_parts = []
        if success:
            reply_parts.append(f"✅ 任务完成！共 {total_rounds} 轮 ReAct 循环。\n")
        else:
            error_msg = result.get("error", "任务未完全完成")
            reply_parts.append(f"⚠️ {error_msg}\n")

        # 添加执行结果
        for i, r in enumerate(all_results[:5]):  # 最多显示5个结果
            if r.get("success"):
                res = r.get("result", {})
                if isinstance(res, dict):
                    content = res.get("content", res.get("text", res.get("result", str(res))))
                else:
                    content = str(res)
                reply_parts.append(f"\n📌 结果{i+1}: {content[:500]}")

        reply_text = "\n".join(reply_parts) if reply_parts else "任务已处理，但无具体结果。"

        # 构建思考过程
        thinking_process = {
            "mode": "v1_react",
            "collaboration_mode": "leader_worker_react",
            "agents_used": [leader.name] + [w.name for w in workers],
            "rounds": total_rounds,
            "react_steps": [
                {
                    "round": h.get("round"),
                    "thought": h.get("thought", "")[:200],
                    "action_type": h.get("action_type"),
                    "success": h.get("result", {}).get("success", False),
                }
                for h in react_history
            ],
        }

        # 保存 AI 回复到 BFS 上下文
        try:
            from core.workflow.bfs_processor import get_bfs_processor
            bfs = get_bfs_processor()
            bfs.add_node(user_id=request.user_id, role="assistant", content=reply_text)
        except Exception as e:
            logger.debug("保存 AI 回复到 BFS 失败: %s", e)

        elapsed = time.time() - start_time
        logger.info("✅ 简化聊天完成: %.2fs, 成功: %s", elapsed, success)

        return SimpleChatResponse(
            reply=reply_text,
            thinking_process=thinking_process,
            success=success,
        )

    except Exception as e:
        logger.error("简化聊天异常: %s", e, exc_info=True)
        return SimpleChatResponse(
            reply=f"处理请求时出错: {str(e)}",
            thinking_process={"error": str(e)},
            success=False,
        )


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
@router.get("/simple/health", summary="简化聊天健康检查")
async def simple_health():
    """健康检查端点"""
    return {
        "status": "ok",
        "mode": "v1_react",
        "tools": "v2_all",
    }

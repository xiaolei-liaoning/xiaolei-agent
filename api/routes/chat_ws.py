"""WebSocket 聊天端点

包含：
- ConnectionManager - WebSocket 连接管理器（心跳检测）
- WebSocket /ws/chat - 实时聊天端点
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.handlers import (
    handle_automation_workflow,
    handle_multi_step_streaming,
    handle_single_step,
    _dispatcher,
)

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/api", tags=["chat-ws"])


# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self, heartbeat_interval: int = 30, heartbeat_timeout: int = 60):
        """
        初始化连接管理器

        Args:
            heartbeat_interval: 心跳间隔（秒）
            heartbeat_timeout: 心跳超时时间（秒）
        """
        self.active_connections: dict = {}  # {websocket: {"last_pong": datetime, "connected_at": datetime}}
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self._heartbeat_task = None
        self._running = False
        self._logger = logging.getLogger(__name__)

    async def start_heartbeat_check(self):
        """启动心跳检测任务"""
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._logger.warning("心跳检测任务已在运行")
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._logger.info("心跳检测任务已启动")

    async def stop_heartbeat_check(self):
        """停止心跳检测任务"""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._logger.info("心跳检测任务已停止")

    async def _heartbeat_loop(self):
        """心跳检测循环"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._check_heartbeats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"心跳检测循环异常: {e}")

    async def _check_heartbeats(self):
        """检查所有连接的心跳状态"""
        now = datetime.now()
        connections_to_remove = []

        for websocket, info in list(self.active_connections.items()):
            last_pong = info.get("last_pong")

            # 发送 ping
            try:
                await websocket.send_json({"type": "ping", "timestamp": now.isoformat()})
                self._logger.debug(f"发送 ping 到连接: {id(websocket)}")
            except Exception as e:
                self._logger.warning(f"发送 ping 失败: {e}")
                connections_to_remove.append(websocket)
                continue

            # 检查超时
            if last_pong:
                time_since_pong = (now - last_pong).total_seconds()
                if time_since_pong > self.heartbeat_timeout:
                    self._logger.warning(f"连接超时: {id(websocket)}, 最后 pong: {time_since_pong:.1f}秒前")
                    connections_to_remove.append(websocket)

        # 清理超时连接
        for websocket in connections_to_remove:
            try:
                await self.disconnect(websocket)
            except Exception as e:
                self._logger.error(f"清理超时连接失败: {e}")

    async def connect(self, websocket: WebSocket):
        """连接客户端，带简易鉴权（防止恶意客户端滥用 LLM 资源）

        Token 从环境变量 WS_AUTH_TOKEN 读取，未设置时默认拒绝所有连接
        （安全性优先——前端当前已禁用 WebSocket 走 HTTP API，见 static/js/coze.js）
        """
        import os as _os
        expected_token = _os.environ.get("WS_AUTH_TOKEN", "")

        # 尝试从查询参数或 header 获取 token
        token = websocket.query_params.get("token", "")
        if not token:
            # 兼容旧客户端：也尝试从 header 读取 Authorization: Bearer <token>
            auth = websocket.headers.get("authorization", "")
            if auth and auth.startswith("Bearer "):
                token = auth[7:]

        if not expected_token:
            self._logger.warning("WS_AUTH_TOKEN 未设置，WebSocket 连接被拒绝: %s", id(websocket))
            await websocket.close(code=1011, reason="server not configured")
            return

        if not token or token != expected_token:
            await websocket.close(code=1008, reason="invalid token")
            self._logger.warning(f"WebSocket 连接因无效 token 被拒绝: {id(websocket)}")
            return
        await websocket.accept()
        self.active_connections[websocket] = {
            "connected_at": datetime.now(),
            "last_pong": datetime.now(),
            "last_ping": None,
            "token": token
        }
        self._logger.info(f"WebSocket 连接授权通过: {id(websocket)}, 当前活跃连接数: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """断开连接"""
        if websocket in self.active_connections:
            del self.active_connections[websocket]
            # 尝试关闭连接
            try:
                await websocket.close()
            except Exception:
                self._logger.warning("关闭WebSocket连接时发生异常")
            self._logger.info(f"连接断开: {id(websocket)}, 当前活跃连接数: {len(self.active_connections)}")

    def update_pong(self, websocket: WebSocket):
        """更新 pong 时间"""
        if websocket in self.active_connections:
            self.active_connections[websocket]["last_pong"] = datetime.now()
            self._logger.debug(f"收到 pong 从连接: {id(websocket)}")


# 全局连接管理器实例
manager = ConnectionManager()


# ---------------------------------------------------------------------------
# WebSocket 端点：实时聊天
# ---------------------------------------------------------------------------
@ws_router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket 实时聊天端点。"""
    # 使用惰性导入避免与 chat.py 的循环引用（_needs_agent 定义在 chat.py 中）
    from api.routes.chat import _needs_agent

    await manager.connect(websocket)
    client_id: str = f"ws_{id(websocket)}"

    try:
        if _dispatcher is None:
            await websocket.send_json({
                "reply": "系统尚未初始化完成",
                "skill": "error",
                "success": False,
            })
            await websocket.close(code=1013)
            return
    except ImportError:
        await websocket.send_json({
            "reply": "系统尚未初始化完成",
            "skill": "error",
            "success": False,
        })
        await websocket.close(code=1013)
        return

    try:
        while True:
            try:
                # 修复 #079: receive_text 加超时——避免半开/僵尸连接无限阻塞,
                # 心跳检测依赖客户端周期性响应, 超时后走 except 正常断开
                data: str = await asyncio.wait_for(
                    websocket.receive_text(), timeout=manager.heartbeat_timeout
                )
            except asyncio.TimeoutError:
                logger.info("WebSocket 接收超时(%.0fs 无消息), 断开: %s",
                            manager.heartbeat_timeout, client_id)
                break
            except Exception:
                break

            try:
                request_data: Dict[str, Any] = json.loads(data)
                # 检查是否是 pong 消息
                message_type = request_data.get("type")
                if message_type == "pong":
                    manager.update_pong(websocket)
                    continue

                message: str = request_data.get("message", "")
                user_id: int = request_data.get("user_id", 1)
                agent_id: str = request_data.get("agent_id", "default")
            except (json.JSONDecodeError, TypeError):
                message = data
                user_id = 1
                agent_id = "default"

            if not message.strip():
                await websocket.send_json({
                    "reply": "消息不能为空",
                    "skill": "error",
                    "success": False,
                })
                continue

            # 判断是否需要Agent
            if _needs_agent(message):
                # 复杂任务 → 走Agent（这里简化处理）
                await websocket.send_json({
                    "reply": "该任务需要深度处理，请使用HTTP API",
                    "skill": "agent",
                    "success": False,
                })
                continue

            # 简单任务 → 直接处理
            skill_name: str = _dispatcher.match_skill(message)

            try:
                if skill_name == "advanced_automation":
                    result = await handle_automation_workflow(message, user_id)
                    reply_text = result.get("reply", "处理完成")
                    tool_call_info = {"name": "automation_workflow", "params": {"message": message}}
                    thinking_process = result.get("thinking_process")

                    await websocket.send_json({
                        "reply": reply_text,
                        "skill": skill_name,
                        "success": result.get("success", True),
                        "thinking_process": thinking_process,
                    })
                elif skill_name == "multi_step":
                    sub_results = await handle_multi_step_streaming(message, user_id, websocket)
                    reply_text = sub_results.get("reply", "多步任务完成")
                    await websocket.send_json({
                        "reply": reply_text,
                        "skill": "multi_step",
                        "success": sub_results.get("success", True),
                        "is_aggregated": True,
                    })
                else:
                    result = await handle_single_step(message, user_id, skill_name, agent_id, _dispatcher)
                    reply_text = result.get("reply", "处理完成")
                    tool_call_info = result.get("tool_call")

                    await websocket.send_json({
                        "reply": reply_text,
                        "skill": skill_name,
                        "success": result.get("success", True),
                    })
            except Exception as e:
                logger.error("WebSocket 消息处理失败: %s", e)
                await websocket.send_json({
                    "reply": f"处理失败: {e}",
                    "skill": "error",
                    "success": False,
                })

    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开: %s", client_id)
    except Exception as e:
        logger.info("WebSocket 连接异常关闭: %s (%s)", client_id, e)
    finally:
        await manager.disconnect(websocket)


__all__ = ["ws_router", "manager"]

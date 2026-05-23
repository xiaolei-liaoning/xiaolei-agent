"""
BaseAgent - 真正的智能体基类

每个Agent具备：
- 独立的心智 (Mind) - 思考、决策、反思
- 独立的记忆 (Memory) - 短期、长期、情景记忆
- 独立的能力 (Capabilities) - 技能、工具、知识
- 独立的生命周期 (Lifecycle) - 注册、发现、执行、注销
- 独立的通信能力 - 主动与其他Agent沟通
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# ── 从拆分后的子模块导入 ──────────────────────────────────────────────
from .models import (
    CommunicationTopic,
    AgentState,
    AgentType,
    Capability,
    Tool,
    Thought,
    Reflection,
    AgentMetrics,
    Task,
    ActionResult,
    Message,
)
from .mind import Mind
from .memory import MemorySystem

logger = logging.getLogger(__name__)

# MCP 工具缓存: {tool_name_lower: (server_name, tool_name)}
_MCP_TOOL_CACHE: Optional[Dict[str, tuple]] = None


async def _build_mcp_tool_cache() -> Dict[str, tuple]:
    """扫描 mcp/*.py 建立 tool→server 映射缓存"""
    import importlib.util as iutil

    cache = {}
    mcp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "mcp")
    if not os.path.isdir(mcp_dir):
        return cache
    for fname in sorted(os.listdir(mcp_dir)):
        if not fname.endswith("_mcp_server.py"):
            continue
        modname = fname[:-3]
        spec = iutil.spec_from_file_location(modname, os.path.join(mcp_dir, fname))
        if not spec or not spec.loader:
            continue
        try:
            mod = iutil.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            continue
        server_name = modname.replace("_mcp_server", "").replace("_", "-")
        script_path = fname
        for t in getattr(mod, "TOOLS", []):
            tn = t.get("name", "")
            desc = t.get("description", "")
            if tn:
                cache[tn.lower()] = (server_name, script_path, desc)
    logger.info(f"MCP 缓存构建完成: {len(cache)} 个工具")
    return cache


class BaseAgent(ABC):
    """Agent基类 - 真正的智能体"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_type: AgentType = AgentType.WORKER,
        name: Optional[str] = None,
        description: str = ""
    ):
        # 身份标识
        self.agent_id = agent_id or str(uuid.uuid4())
        self.agent_type = agent_type
        self.agent_name = name or f"{agent_type.value}_{self.agent_id[:8]}"
        self.description = description

        # 能力定义
        self.capabilities: List[Capability] = []
        self.tools: Dict[str, Tool] = {}

        # 自治系统
        self.mind = Mind(self)
        self.memory = MemorySystem(self)

        # 生命周期状态
        self.state = AgentState.CREATED
        self.health_score: float = 1.0
        self.current_load: float = 0.0
        self.max_load: float = 1.0

        # 性能指标
        self.metrics = AgentMetrics()

        # 上下文引用
        self.context_center: Optional[Any] = None
        self.task_history: List[Task] = []

        # SharedBus 引用（惰性初始化）
        self._bus: Optional[Any] = None

        # 通信中心（兼容旧接口，由子类或外部注入）
        self._communication_center: Optional[Any] = None

        # 查重跟踪器（防止兜圈子）
        from core.repetition_tracker import RepetitionTracker
        self._tracker = RepetitionTracker(threshold=3)

        # 锁
        self._state_lock = asyncio.Lock()

        # 实时思考轨迹显示器（可选，由 CLI 注入）
        self._trace: Optional[Any] = None

        logger.info(f"Agent创建: {self.agent_id} ({self.agent_type.value})")

    def set_trace(self, trace: Any) -> None:
        """注入实时思考轨迹显示器"""
        self._trace = trace
        self.mind._trace = trace  # Mind 也引用同一实例

    async def _ensure_bus(self) -> None:
        """惰性初始化 SharedBus 并订阅消息"""
        if self._bus is not None:
            return
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, Message, MessageType
            self._bus = get_shared_bus()
            # 订阅直接消息
            await self._bus.subscribe(f"agent:{self.agent_id}", self._on_bus_direct_message)
            logger.info(f"Agent {self.agent_id} SharedBus 初始化成功")
        except Exception as e:
            logger.warning(f"Agent {self.agent_id} SharedBus 初始化失败: {e}")

    async def _on_bus_direct_message(self, message: 'Message') -> None:
        """处理 SharedBus 直接消息"""
        logger.info(f"Agent {self.agent_id} 收到总线消息: {message.type.value}")
        await self.memory.store_episode({
            "type": "bus_message",
            "message_type": message.type.value,
            "sender": message.sender,
            "payload": message.payload,
        })

    async def register(self) -> None:
        """注册到SharedBus"""
        async with self._state_lock:
            if self.state != AgentState.CREATED:
                raise ValueError(f"Agent {self.agent_id} 已注册，不能重复注册")
            self.state = AgentState.REGISTERED
            await self._ensure_bus()
            logger.info(f"Agent注册: {self.agent_id} (SharedBus)")

    async def start(self) -> None:
        """启动Agent"""
        async with self._state_lock:
            if self.state != AgentState.REGISTERED:
                raise ValueError(f"Agent {self.agent_id} 未注册")

            self.state = AgentState.IDLE
            logger.info(f"Agent启动: {self.agent_id}")

    async def stop(self) -> None:
        """停止Agent"""
        async with self._state_lock:
            self.state = AgentState.STOPPED
            logger.info(f"Agent停止: {self.agent_id}")

    async def set_ready(self) -> None:
        """设置Agent为就绪状态"""
        async with self._state_lock:
            if self.state != AgentState.IDLE:
                raise ValueError(f"Agent {self.agent_id} 不在空闲状态")

            self.state = AgentState.READY

    async def receive_task(self, task: Task) -> None:
        """接收任务"""
        async with self._state_lock:
            if self.current_load >= self.max_load:
                raise RuntimeError(f"Agent {self.agent_id} 负载已满")

            self.current_load += task.complexity
            self.state = AgentState.READY
            self.task_history.append(task)

            logger.info(f"Agent {self.agent_id} 接收任务: {task.task_id}")

    async def think(self, task: Task) -> Thought:
        """思考：理解任务、制定计划"""
        return await self.mind.think(task)

    @abstractmethod
    async def execute(self, task: Task) -> ActionResult:
        """执行任务（子类必须实现）"""
        pass

    async def act(self, plan: List[str], tool_calls: Optional[List[Dict]] = None) -> ActionResult:
        """执行：调用工具（只读并行 + 写串行，参考Claude Code设计）"""
        logger.info(f"Agent {self.agent_id} 开始执行计划 ({len(plan)} 步)")

        start_time = time.time()
        results = []

        # 如果 LLM 选择了精确的 tool_calls，直接执行（绕过 plan 的关键词匹配）
        if tool_calls:
            logger.info(f"执行 LLM 自主选择的 {len(tool_calls)} 个工具调用")
            results = await self._execute_tool_calls(tool_calls)
            # 重试失败的调用一次
            failed_indices = [i for i, r in enumerate(results) if not r.get("success")]
            if failed_indices:
                retry_calls = [tool_calls[i] for i in failed_indices]
                logger.info(f"重试 {len(retry_calls)} 个失败的工具调用 ({len(failed_indices)}/{len(tool_calls)})")
                retry_results = await self._execute_tool_calls(retry_calls)
                for i, rr in zip(failed_indices, retry_results):
                    results[i] = rr
            outputs = [r for r in results if r.get("success")]
            execution_time = time.time() - start_time
            self.metrics.tasks_completed += 1
            self.metrics.total_execution_time += execution_time
            self.metrics.avg_execution_time = (
                self.metrics.total_execution_time / self.metrics.tasks_completed
            )
            ar = ActionResult(
                success=len(outputs) > 0,
                output=outputs,
                execution_time=execution_time,
            )
            await self._publish_to_bus(ar, results)
            return ar

        try:
            # 分拆：只读(并发安全)步骤并行，写步骤串行
            safe_steps = []
            serial_steps = []
            for step in plan:
                kw = ["读取", "查询", "搜索", "查看", "读", "get", "list", "search",
                       "read", "check", "分析", "统计"]
                if any(k in step for k in kw):
                    safe_steps.append(step)
                else:
                    serial_steps.append(step)

            trace = self._trace

            # 并行执行只读步骤
            if safe_steps:
                if trace:
                    for s in safe_steps:
                        trace.on_tool_call("并行步骤", s[:80])
                safe_results = await asyncio.gather(*[
                    self._execute_step(s) for s in safe_steps
                ], return_exceptions=True)
                for step, res in zip(safe_steps, safe_results):
                    ok = not isinstance(res, Exception)
                    results.append((step, {"success": ok,
                                           "result": res if ok else str(res)}))
                    if trace:
                        trace.on_tool_result(str(res)[:200] if ok else f"失败: {res}", max_lines=2)
                    if ok:
                        self._tracker.record(
                            self.task_history[-1].description if self.task_history else "unknown",
                            step, res,
                        )

            # 串行执行写步骤
            for step in serial_steps:
                if trace:
                    trace.on_tool_call("步骤", step[:80])
                result = await self._execute_step(step)
                results.append((step, result))
                if trace:
                    trace.on_tool_result(str(result.get("data_preview", ""))[:200] or str(result)[:200], max_lines=2)
                self._tracker.record(
                    self.task_history[-1].description if self.task_history else "unknown",
                    step, result,
                )

            # 重试失败的步骤一次
            retry_count = 0
            for i, (step, result) in enumerate(results):
                if not result.get("success"):
                    logger.info(f"重试失败步骤: {str(step)[:60]}...")
                    new_result = await self._execute_step(step)
                    results[i] = (step, new_result)
                    if new_result.get("success"):
                        retry_count += 1
            if retry_count:
                logger.info(f"重试成功 {retry_count} 个步骤")

            # 记录到情景记忆
            for step, result in results:
                await self.memory.store_episode({
                    "step": step,
                    "result": result,
                    "agent_id": self.agent_id
                })

            # 执行成功
            execution_time = time.time() - start_time
            self.metrics.tasks_completed += 1
            self.metrics.total_execution_time += execution_time
            self.metrics.avg_execution_time = (
                self.metrics.total_execution_time / self.metrics.tasks_completed
            )

            ar = ActionResult(
                success=True,
                output=results,
                execution_time=execution_time
            )

            # 发布执行结果到 SharedBus
            await self._publish_to_bus(ar, results)

            return ar

        except Exception as e:
            logger.error(f"Agent {self.agent_id} 执行失败: {e}")
            self.metrics.tasks_failed += 1

            ar = ActionResult(
                success=False,
                error=str(e),
                partial_results=results
            )

            # 发布失败到 SharedBus
            await self._publish_to_bus(ar, results)

            return ar

        finally:
            self.current_load = max(0, self.current_load - 0.3)

    async def _publish_to_bus(self, ar: ActionResult, step_results: list) -> None:
        """发布执行结果到 SharedBus（含工具调用详情）"""
        try:
            await self._ensure_bus()
            if not self._bus:
                return
            from core.multi_agent_v2.infrastructure.shared_bus import Message, MessageType
            task_id = self.task_history[-1].task_id if self.task_history else "unknown"

            # 提取工具调用结果摘要
            tool_summaries = []
            for item in step_results:
                if isinstance(item, dict):
                    tc = item.get("tool_call", {})
                    tool_summaries.append({
                        "tool_name": tc.get("name", "?"),
                        "success": item.get("success", False),
                    })

            payload = {
                "task_id": task_id,
                "agent_id": self.agent_id,
                "agent_type": self.agent_type.value,
                "success": ar.success,
                "steps": len(step_results),
                "execution_time": ar.execution_time,
                "error": ar.error,
                "tool_calls": tool_summaries,
                "output_preview": str(ar.output)[:500] if ar.output else "",
            }
            msg = Message(
                type=MessageType.TASK_PROGRESS if ar.success else MessageType.TASK_FAILED,
                sender=self.agent_id,
                topic=f"task:{task_id}",
                payload=payload,
            )
            await self._bus.publish(msg.topic, msg)
        except Exception as e:
            logger.debug(f"发布到 SharedBus 失败: {e}")

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """执行 LLM 选择的工具调用，参数由 LLM 构造（绕过关键词匹配）

        现在包含：
        - ToolRegistry schema 校验
        - tool_name 自动补齐（无前缀时尝试匹配）
        - 三种执行后端 fallback
        """
        results = []

        # 参数别名兼容：不同 LLM 可能用不同字段名
        def _normalize_args(args: Dict) -> Dict:
            aliases = [
                ("name", "path"),       # GLM 用 name 当 path
                ("input", "query"),     # 搜索工具别名
                ("text", "content"),    # 文本内容别名
                ("parameters", "args"), # 通用参数别名
            ]
            for alias_key, target in aliases:
                if alias_key in args and target not in args:
                    args[target] = args.pop(alias_key)
            return args

        # 获取 ToolRegistry（用于校验和名称解析）
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry
        registry = get_tool_registry()
        if not registry._initialized:
            await registry.discover_all()

        trace = self._trace

        for tc in tool_calls:
            raw_name = tc.get("name", "")
            args = _normalize_args(tc.get("arguments", {}).copy())

            # ── 工具名称规范化 ──────────────────────────────
            tool_name = tc.get("_tool_name", raw_name)
            server = tc.get("_server", "")
            lookup_name = raw_name

            # 如果 name 无 server 前缀，尝试从 registry 反查
            if "." not in lookup_name and registry.count > 0:
                for reg_name, reg_tool in registry._tools.items():
                    if reg_tool.tool_name == lookup_name or reg_name.endswith(f".{lookup_name}"):
                        lookup_name = reg_name
                        server = reg_tool.server
                        tool_name = reg_tool.tool_name
                        break

            if trace:
                trace.on_tool_call(tool_name, args)

            # ── Schema 校验 ──────────────────────────────────
            if registry.count > 0:
                valid, msg = registry.validate_arguments(lookup_name, args)
                if not valid:
                    logger.warning(f"工具参数校验失败: {lookup_name} -> {msg}")
                    results.append({
                        "tool_call": tc,
                        "success": False,
                        "result": {"error": f"参数校验失败: {msg}"},
                    })
                    if trace:
                        trace.on_tool_error(f"参数校验失败: {msg}")
                    continue

            result = None

            # Source 1: awesome_mcp_manager（用原始 name 匹配）
            try:
                from core.mcp.awesome_mcp_manager import awesome_mcp_manager
                defs = await awesome_mcp_manager.get_all_tool_definitions()
                for td in defs:
                    if td.get("function", {}).get("name") in (raw_name, lookup_name):
                        result = await awesome_mcp_manager.call_tool_by_definition(td, args)
                        break
            except Exception:
                pass

            # Source 2: mcp_client（指定 server）
            if result is None and server:
                try:
                    from core.mcp.mcp_client import mcp_client
                    if mcp_client._initialized:
                        result_text = await mcp_client.call_tool(server, tool_name, args)
                        result = {"result": {"content": [{"text": result_text}]}}
                except Exception:
                    pass

            # Source 3: 按工具名搜索所有服务器
            if result is None:
                try:
                    from core.mcp.mcp_client import mcp_client
                    if mcp_client._initialized:
                        servers = await mcp_client.list_servers()
                        for srv in servers:
                            srv_tools = await mcp_client.list_tools(srv)
                            for t in srv_tools:
                                if t.get("name") == tool_name:
                                    result_text = await mcp_client.call_tool(srv, tool_name, args)
                                    result = {"result": {"content": [{"text": result_text}]}}
                                    break
                            if result:
                                break
                except Exception:
                    pass

            if trace:
                if result is not None:
                    res_text = str(result.get("result", {}).get("content", ""))
                    trace.on_tool_result(res_text[:200] or str(result)[:200])
                else:
                    trace.on_tool_error("工具调用失败：所有后端均无响应")

            self._log_execution(
                f"tool_call_{tool_name}",
                {"server": server, "tool": tool_name, "args": args},
                result or {"error": "all backends failed"},
                0,
            )

            results.append({
                "tool_call": tc,
                "success": result is not None,
                "result": result,
            })

        return results

    async def _execute_step(self, step: str) -> Any:
        """执行单个步骤 — 调 MCP 工具 / RAG 搜索 / LLM

        路由逻辑：
        1. 搜索/查询类 → RAGSearchEngine
        2. 工具调用类 → MCPClientManager
        3. 其他 → LLM 直接生成
        4. 全部失败 → sleep(0.1) 兜底
        """
        task_id = self.task_history[-1].task_id if self.task_history else "unknown"
        start = time.time()

        try:
            # ─── 搜索 / 查询类 ─────────────────────────────
            kw_search = ["搜索", "查询", "查找", "搜", "找", "search", "lookup"]
            if any(k in step for k in kw_search):
                try:
                    from core.search.rag_search_engine import RAGSearchEngine
                    engine = RAGSearchEngine()
                    result = await engine.search_and_learn(
                        query=step, user_id=1, max_results=3, learn=True
                    )
                    elapsed = (time.time() - start) * 1000
                    self._log_execution("rag_search", {"query": step}, result, elapsed)
                    return {"step": step, "status": "completed", "result": result}
                except Exception as e:
                    logger.warning(f"RAG 搜索失败: {e}")

            # ★ A级优化：text-analyzer-mcp 内联（字符/词频/句子统计）
            kw_text_analysis = ["统计", "字数", "词数", "字符", "分析", "关键词",
                              "count", "char", "word", "sentence", "keyword"]
            if any(k in step for k in kw_text_analysis):
                try:
                    from collections import Counter

                    text = step
                    analysis_result = {}

                    # 提取引号中的文本
                    quote_match = re.search(r'[""""\'](.+?)[""""\']', step)
                    if quote_match:
                        text = quote_match.group(1)

                    # 字符统计（去空格）
                    analysis_result["字符数"] = len(text.replace(" ", ""))

                    # 词数统计（中英文）
                    chinese_chars = re.findall(r'[一-龥]', text)
                    english_words = re.findall(r'[a-zA-Z]+', text)
                    analysis_result["词数"] = len(chinese_chars) + len(english_words)

                    # 句子数统计
                    sentences = re.split(r'[。！？.!?]', text)
                    analysis_result["句子数"] = len([s for s in sentences if s.strip()])

                    # 关键词提取
                    chinese_words = re.findall(r'[一-龥]{2,4}', text)
                    english_words = re.findall(r'[a-zA-Z]{3,}', text)
                    all_words = chinese_words + english_words
                    stop_words = {'的', '了', '和', '是', '在', '我', '有', '个', '们', 'the', 'a', 'an', 'is', 'are'}
                    filtered = [w for w in all_words if w.lower() not in stop_words]
                    top_keywords = [w for w, _ in Counter(filtered).most_common(5)]
                    analysis_result["关键词"] = top_keywords

                    result_str = f"文本分析结果：字符数={analysis_result['字符数']}, 词数={analysis_result['词数']}, 句子数={analysis_result['句子数']}, 关键词={analysis_result['关键词']}"

                    elapsed = (time.time() - start) * 1000
                    self._log_execution("text_analyzer_inline", {"text": text[:50]}, analysis_result, elapsed)
                    return {"step": step, "status": "completed", "result": result_str, "tool": "text_analyzer_inline"}
                except Exception as e:
                    logger.debug(f"文本分析内联失败: {e}")

            # ─── 工具调用类（MCP） ─────────────────────────
            try:
                from core.mcp.mcp_client import mcp_client as mcp
                if not mcp._initialized:
                    await mcp.initialize()

                # 1. 先查已连接的服务器
                servers = await mcp.list_servers()
                found = None
                for server in servers:
                    tools = await mcp.list_tools(server)
                    for tool in tools:
                        tname = tool.get("name", "")
                        desc = tool.get("description", "")
                        if tname.lower() in step.lower() or any(
                            kw.lower() in desc.lower() for kw in step.split()
                        ):
                            found = (server, tname, {})
                            break
                    if found:
                        break

                # 2. 没找到 → 使用缓存快速查找本地MCP工具
                if not found:
                    global _MCP_TOOL_CACHE
                    if _MCP_TOOL_CACHE is None:
                        _MCP_TOOL_CACHE = await _build_mcp_tool_cache()

                    # 在缓存中查找匹配的工具
                    step_lower = step.lower()
                    step_words = step.split()
                    for tool_name, (server_name, script, desc) in _MCP_TOOL_CACHE.items():
                        if tool_name in step_lower or any(
                            kw.lower() in desc.lower() for kw in step_words
                        ):
                            # 自动连接服务器
                            mcp_dir = os.path.join(
                                os.path.dirname(__file__), "..", "..", "..", "..", "mcp"
                            )
                            await mcp.connect_server(
                                server_name, "python", [script],
                                cwd=os.path.join(mcp_dir, script[:-3] + "_mcp_server.py"),
                            )
                            found = (server_name, tool_name, {})
                            break

                # 3. 执行
                if found:
                    server, tname, args = found
                    result_text = await mcp.call_tool(server, tname, args)
                    elapsed = (time.time() - start) * 1000
                    self._log_execution(f"mcp_{tname}",
                        {"server": server, "tool": tname}, result_text, elapsed)
                    return {"step": step, "status": "completed",
                            "result": result_text, "tool": tname}

                # ★ S级优化：本地MCP没找到 → fallback到 awesome-mcp (114个额外工具)
                if not found:
                    try:
                        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

                        step_words = step.split()
                        search_results = []

                        for keyword in step_words[:3]:
                            if len(keyword) >= 2:
                                results = awesome_mcp_manager.search_servers(keyword)
                                search_results.extend(results)

                        seen = set()
                        unique_results = []
                        for r in search_results:
                            if r["name"] not in seen:
                                seen.add(r["name"])
                                unique_results.append(r)

                        if unique_results:
                            server_info = unique_results[0]
                            server_name = server_info["name"]

                            connect_result = await awesome_mcp_manager.quick_connect(server_name)

                            if connect_result.get("success"):
                                tools = await mcp.list_tools(server_name)
                                if tools:
                                    tool = tools[0]
                                    tname = tool.get("name", "")
                                    if tname:
                                        result_text = await mcp.call_tool(server_name, tname, {})
                                        elapsed = (time.time() - start) * 1000
                                        self._log_execution(f"awesome_mcp_{tname}",
                                            {"server": server_name, "tool": tname,
                                             "via": "awesome-mcp-fallback"},
                                            result_text, elapsed)
                                        return {"step": step, "status": "completed",
                                                "result": result_text, "tool": tname,
                                                "source": "awesome-mcp"}

                    except Exception as awesome_err:
                        logger.debug(f"awesome-mcp fallback 失败: {awesome_err}")

            except Exception as e:
                logger.debug(f"MCP 不可用: {e}")

        except Exception as e:
            logger.warning(f"执行步骤异常: {e}")

        # ─── 兜底 — 直接调用 LLM ─
        try:
            from core.engine.llm_backend import get_llm_router
            llm_router = get_llm_router()

            if llm_router.is_available():
                prompt = f"请完成以下任务步骤：{step}"
                response = await llm_router.chat([{"role": "user", "content": prompt}],
                                                temperature=0.7, max_tokens=500)

                elapsed = (time.time() - start) * 1000
                self._log_execution("llm_fallback", {"step": step}, response, elapsed)
                return {"step": step, "status": "completed", "result": response, "tool": "llm"}
        except Exception as llm_e:
            logger.warning(f"LLM兜底调用失败: {llm_e}")

        # 最后兜底：返回失败
        elapsed = (time.time() - start) * 1000
        self._log_execution("failed", {"step": step}, "无可用工具且LLM不可用", elapsed)
        return {"step": step, "status": "failed", "error": "无可用工具或搜索失败"}

    def _log_execution(self, tool_name: str, params: dict,
                       result: Any, duration_ms: float) -> None:
        """记录执行日志到 ExecutionLogger"""
        try:
            from core.execution_logger import get_execution_logger
            logger_inst = get_execution_logger()
            task_id = self.task_history[-1].task_id if self.task_history else "unknown"
            logger_inst.log(
                tool_name=tool_name,
                params=params,
                result=str(result)[:2000],
                status="success",
                duration_ms=duration_ms,
                agent_type=self.agent_type.value,
            )
        except Exception as e:
            logger.debug(f"ExecutionLogger 记录失败: {e}")

    async def reflect(self, result: ActionResult) -> Reflection:
        """反思：调 AutoReviewer 复盘 + SkillExtractor 沉淀 + SharedBus 广播"""
        logger.info(f"Agent {self.agent_id} 反思执行结果")

        task_id = self.task_history[-1].task_id if self.task_history else "unknown"
        task_desc = self.task_history[-1].description if self.task_history else ""
        execution_time = result.execution_time
        success = result.success

        # ─── 收集执行日志 ─────────────────────────────────
        logs_str = ""
        try:
            from core.execution_logger import get_execution_logger
            el = get_execution_logger()
            if hasattr(el, 'format_logs_for_review'):
                logs_str = el.format_logs_for_review(task_id)
        except Exception as e:
            logger.debug(f"ExecutionLogger 获取日志失败: {e}")

        # ─── AutoReviewer 复盘 ────────────────────────────
        review_result = None
        try:
            from core.auto_reviewer import get_auto_reviewer
            reviewer = get_auto_reviewer()
            review_result = await reviewer.review(
                task_id=task_id,
                task_description=task_desc,
                execution_logs=logs_str or f"步骤: {len(result.output if result.output else [])}, 耗时: {execution_time:.2f}s",
                task_result=str(result.output)[:1000] if result.output else None,
            )

            # ─── SkillExtractor 沉淀 ───────────────────────
            if review_result and review_result.is_worth_saving:
                try:
                    from core.skill_extractor import get_skill_extractor
                    extractor = get_skill_extractor()
                    extractor.extract_from_review(review_result, logs_str)
                except Exception as e:
                    logger.debug(f"SkillExtractor 提取失败: {e}")

        except Exception as e:
            logger.debug(f"AutoReviewer 复盘失败: {e}")

        # ─── 构建 Reflection ──────────────────────────────
        reflection = Reflection(
            success=success,
            lessons_learned=[review_result.what_went_well[:200]] if review_result and review_result.what_went_well else (
                ["任务成功完成"] if success else []
            ),
            improvements=[review_result.improvement[:200]] if review_result and review_result.improvement else (
                [] if success else ["考虑使用不同的策略"]
            ),
            performance_metrics={
                "execution_time": execution_time,
                "success_rate": self.metrics.success_rate,
            }
        )
        if review_result:
            reflection.performance_metrics["is_worth_saving"] = review_result.is_worth_saving
            reflection.performance_metrics["pitfalls"] = review_result.pitfalls[:100] if review_result.pitfalls else ""

        # 提取工具执行结果摘要，注入到 performance_metrics
        tool_summary = self._extract_tool_result_summary(result)
        if tool_summary:
            reflection.performance_metrics["tool_results"] = tool_summary

        # 存储到记忆
        await self.memory.store_episode({
            "type": "reflection",
            "result": reflection.__dict__,
            "agent_id": self.agent_id
        })

        # 实时显示反思结果
        if self._trace:
            summary = "任务成功" if success else "任务需要改进"
            if review_result and review_result.what_went_well:
                summary = review_result.what_went_well[:100]
            self._trace.on_reflection(summary, success)

        # 发布到 SharedBus（KEPA闭环：将反思结果传递给调度器）
        try:
            await self._ensure_bus()
            if self._bus:
                from core.multi_agent_v2.infrastructure.shared_bus import Message, MessageType

                # 获取任务类型（从历史任务中提取）
                task_type = self.task_history[-1].type if self.task_history else "general"

                # 获取协作模式（如果有上下文信息）
                collaboration_mode = ""
                if self.context_center:
                    try:
                        context = self.context_center.get_task_context(task_id)
                        if context and hasattr(context, 'collaboration_mode'):
                            collaboration_mode = context.collaboration_mode
                    except Exception:
                        pass

                await self._bus.publish(
                    f"agent:{self.agent_id}:reflect",
                    Message(
                        type=MessageType.REFLECTION_RESULT,
                        sender=self.agent_id,
                        topic=f"task:{task_id}:reflect",
                        payload={
                            "task_id": task_id,
                            "agent_id": self.agent_id,
                            "agent_type": self.agent_type.value,
                            "success": success,
                            "lessons_learned": reflection.lessons_learned,
                            "improvements": reflection.improvements,
                            "task_type": task_type,
                            "collaboration_mode": collaboration_mode,
                            "execution_time": execution_time,
                            "performance_metrics": reflection.performance_metrics,
                        }
                    )
                )
                logger.debug(f"✅ 反思结果已发布到KEPA闭环: agent={self.agent_id}, task={task_id}")
        except Exception as e:
            logger.debug(f"发布反思结果失败: {e}")

        return reflection

    def _extract_tool_result_summary(self, result: ActionResult) -> str:
        """从执行结果中提取工具调用摘要"""
        if not result or not result.output:
            return ""
        try:
            summaries = []
            for item in result.output:
                if isinstance(item, dict):
                    tc = item.get("tool_call", {})
                    name = tc.get("name", "?")
                    success = item.get("success", False)
                    res = item.get("result", {})
                    preview = str(res.get("result", {}).get("content", ""))[:100] if res else ""
                    if not preview:
                        preview = str(item.get("result", ""))[:100]
                    status = "✓" if success else "✗"
                    summaries.append(f"[{status}] {name}: {preview}")
            if summaries:
                return "工具执行:\n" + "\n".join(summaries[:5])
        except Exception:
            pass
        return ""

    async def _on_message_received(self, message: Dict[str, Any]):
        """处理收到的直接消息"""
        logger.info(f"Agent {self.agent_id} 收到消息: {message.get('sender')} -> {message.get('content', '')[:50]}...")

        # 存储到情景记忆
        await self.memory.store_episode({
            "type": "message_received",
            "sender": message.get("sender"),
            "content": message.get("content"),
            "message_type": message.get("message_type", "inform")
        })

        # 调用子类处理
        await self.handle_message(message)

    async def _on_topic_message(self, message: Dict[str, Any]):
        """处理订阅主题的消息"""
        logger.debug(f"Agent {self.agent_id} 收到主题消息: {message.get('topic', 'unknown')}")

        # 存储到情景记忆
        await self.memory.store_episode({
            "type": "topic_message",
            "topic": message.get("topic"),
            "content": message.get("content"),
            "sender": message.get("sender")
        })

        # 调用子类处理
        await self.handle_topic_message(message)

    async def send_message(self, target_agent_id: str, content: Any, message_type: str = "inform"):
        """发送消息给指定Agent"""
        if not self._communication_center:
            logger.warning(f"Agent {self.agent_id} 通信中心未初始化")
            return None

        message_id = await self._communication_center.send_direct(
            sender=self.agent_id,
            receiver=target_agent_id,
            content=content,
            message_type=message_type
        )

        logger.info(f"Agent {self.agent_id} 发送消息到 {target_agent_id}: {message_id}")
        return message_id

    async def publish_to_topic(self, topic: str, content: Any):
        """发布消息到指定主题"""
        if not self._communication_center:
            logger.warning(f"Agent {self.agent_id} 通信中心未初始化")
            return

        await self._communication_center.publish(
            topic=topic,
            message={
                "topic": topic,
                "content": content,
                "sender": self.agent_id,
                "timestamp": time.time()
            },
            sender=self.agent_id
        )

        logger.info(f"Agent {self.agent_id} 发布到主题 {topic}")

    async def broadcast(self, content: Any):
        """广播消息给所有Agent"""
        if not self._communication_center:
            logger.warning(f"Agent {self.agent_id} 通信中心未初始化")
            return

        await self._communication_center.broadcast(
            sender=self.agent_id,
            content=content
        )

        logger.info(f"Agent {self.agent_id} 广播消息")

    async def request_help(self, target_agent_id: str, content: Any, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """向其他Agent请求帮助（请求-响应模式）"""
        if not self._communication_center:
            logger.warning(f"Agent {self.agent_id} 通信中心未初始化")
            return None

        result = await self._communication_center.request(
            sender=self.agent_id,
            receiver=target_agent_id,
            content=content,
            timeout=timeout
        )

        logger.info(f"Agent {self.agent_id} 从 {target_agent_id} 获取响应")
        return result

    async def notify_task_completed(self, task_id: str, result: Any):
        """通知其他Agent任务已完成"""
        await self.publish_to_topic(
            topic=CommunicationTopic.TASK_COMPLETED.value,
            content={
                "task_id": task_id,
                "agent_id": self.agent_id,
                "result": result,
                "timestamp": time.time()
            }
        )

    async def notify_task_failed(self, task_id: str, error: str):
        """通知其他Agent任务失败"""
        await self.publish_to_topic(
            topic=CommunicationTopic.TASK_FAILED.value,
            content={
                "task_id": task_id,
                "agent_id": self.agent_id,
                "error": error,
                "timestamp": time.time()
            }
        )

    async def handle_message(self, message: Dict[str, Any]):
        """处理收到的消息（子类可重写）"""
        pass

    async def handle_topic_message(self, message: Dict[str, Any]):
        """处理主题消息（子类可重写）"""
        pass

    def get_online_agents(self) -> List[str]:
        """获取在线Agent列表"""
        if not self._communication_center:
            return []
        return self._communication_center.get_online_agents()

    async def ask_user(
        self,
        question: str,
        context: str = "",
        timeout: int = 60,
    ) -> Optional[str]:
        """反问用户：在降级前询问用户意见

        返回:
          "proceed" - 用户要求继续（降级处理）
          "retry"   - 用户要求重试
          "cancel"  - 用户要求取消
          None      - 超时无响应
        """
        from core.agents.agent_communication import get_question_registry
        future = get_question_registry().ask(
            agent_id=self.agent_id,
            agent_name=self.agent_name or self.agent_id,
            question=question,
            context=context,
            timeout=timeout,
        )
        try:
            result = await asyncio.wait_for(future, timeout=timeout + 5)
            return result
        except asyncio.TimeoutError:
            return None

    async def communicate(self, message: Message) -> None:
        """与其他Agent通信（兼容旧接口）"""
        if message.to_agent:
            await self.send_message(
                target_agent_id=message.to_agent,
                content=message.content,
                message_type=message.message_type
            )
        else:
            await self.broadcast(message.content)

    def can_handle(self, task: Task) -> bool:
        """判断是否能处理任务"""
        if self.current_load >= self.max_load:
            return False

        if self.state not in [AgentState.IDLE, AgentState.READY]:
            return False

        # 检查能力匹配
        for capability in self.capabilities:
            score = capability.match_score(task.keywords)
            if score > 0.3:
                return True

        return False

    def get_load(self) -> float:
        """获取当前负载"""
        return self.current_load

    def get_metrics(self) -> AgentMetrics:
        """获取性能指标"""
        return self.metrics

    async def run(self, task_description: str, max_iterations: int = 3) -> Dict[str, Any]:
        """迭代执行：think → act → reflect → 判断是否继续

        流程：
          1. think()     — LLM 理解任务、制定计划
          2. act()       — 执行计划中的步骤
          3. reflect()   — 评估结果置信度，收集改进建议
          4. 置信度 >= 0.85 → 完成
             置信度 < 0.85 & 还有次数 → 注入反思反馈 → 回 step 1

        Args:
            task_description: 自然语言任务描述
            max_iterations: 最大迭代次数（默认 3）

        Returns:
            {"success": bool, "result": ..., "iterations": int, "confidence": float}
        """
        # 创建 Task
        task = Task(
            task_id=f"run_{uuid.uuid4().hex[:8]}",
            type="general",
            description=task_description,
            keywords=task_description.split(),
            complexity=0.5,
            estimated_steps=3,
        )

        await self.register()
        await self.start()
        await self.receive_task(task)

        last_reflection = None
        iteration = 0
        best_result = None
        best_confidence = 0.0

        for iteration in range(1, max_iterations + 1):
            trace = self._trace

            # 迭代标记（Mind.think() 和 BaseAgent.act() 已有 trace 事件）
            if iteration > 1 and trace:
                reason = ""
                if last_reflection:
                    improvements = last_reflection.improvements
                    if improvements:
                        reason = improvements[0][:60]
                trace.on_iteration(iteration, reason)

            # 如果不是首次，将前一轮反思和工具结果注入到任务描述
            if last_reflection:
                lessons = last_reflection.lessons_learned
                improvements = last_reflection.improvements
                tool_results = last_reflection.performance_metrics.get("tool_results", "")
                feedback = ""
                if lessons:
                    feedback += "前一轮经验: " + "; ".join(lessons[:2]) + "\n"
                if improvements:
                    feedback += "需要改进: " + "; ".join(improvements[:2]) + "\n"
                if tool_results:
                    feedback += tool_results + "\n"
                if feedback:
                    task_updated = Task(
                        task_id=task.task_id, type=task.type,
                        description=task.description + "\n\n### 前一轮反馈\n" + feedback,
                        keywords=task.keywords, complexity=task.complexity,
                        estimated_steps=task.estimated_steps,
                    )
                else:
                    task_updated = task
            else:
                task_updated = task

            thought = await self.think(task_updated)

            result = await self.act(thought.plan, getattr(thought, 'tool_calls', None))

            # 保存最好结果
            if best_result is None or (result.success and not best_result.success):
                best_result = result

            # ── reflect ───────────────────────────────
            reflection = await self.reflect(result)

            # 计算置信度
            confidence = getattr(reflection, 'confidence', 0.5)
            if not hasattr(reflection, 'confidence'):
                confidence = reflection.performance_metrics.get('success_rate', 0.5) if hasattr(reflection, 'performance_metrics') else 0.5
            if result.success and confidence > best_confidence:
                best_confidence = confidence
                best_result = result

            if trace:
                detail = f"置信度 {confidence:.2f}"
                if confidence >= 0.85:
                    detail += " ✓"
                elif reflection.lessons_learned:
                    detail += " — " + reflection.lessons_learned[0][:60]
                trace.on_reflection(detail, confidence >= 0.85)

            # ── 决策 ──────────────────────────────────
            if confidence >= 0.85:
                if trace:
                    trace.status(f"置信度达标 {confidence:.2f}，结束迭代")
                break

            last_reflection = reflection

        # 完成
        if self._trace:
            self._trace.done(best_result.success if best_result else False,
                             detail=f"迭代 {iteration} 轮")

        return {
            "success": best_result.success if best_result else False,
            "result": best_result.output if best_result else None,
            "iterations": iteration,
            "confidence": best_confidence,
            "error": best_result.error if best_result and not best_result.success else None,
        }

    def __repr__(self) -> str:
        return f"BaseAgent(id={self.agent_id}, type={self.agent_type.value}, state={self.state.value})"


class AgentFactory:
    """Create disposable agents on demand — 统一创建 WorkAgent"""

    @staticmethod
    def create_agent(
        agent_type: AgentType,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "",
        **kwargs
    ) -> 'BaseAgent':
        """统一创建 WorkAgent — 不再区分多种 Agent 类型"""
        from .work_agent import WorkAgent
        return WorkAgent(
            agent_id=agent_id,
            name=name or f"agent_{agent_id[:8] if agent_id else 'unknown'}",
            description=description or f"WorkAgent ({agent_type.value})",
        )

    @staticmethod
    def create_agent_from_role(
        role_type: str,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "",
    ) -> 'BaseAgent':
        """根据角色类型创建 WorkAgent — 不再加载角色模板，直接创建通用 WorkAgent"""
        from .work_agent import WorkAgent

        agent = WorkAgent(
            agent_id=agent_id,
            name=name or role_type,
            description=description or f"WorkAgent for role: {role_type}",
        )

        return agent

    @staticmethod
    def create_agents_for_task(
        keywords: list,
        min_count: int = 2,
        max_count: int = 5,
    ) -> List['BaseAgent']:
        """创建多个 WorkAgent（旧接口，保留兼容）"""
        from .work_agent import WorkAgent
        count = max(min_count, min(max_count, len(keywords) + 1))
        return [
            WorkAgent(agent_id=f"agent-{i}", name=f"worker_{i}")
            for i in range(count)
        ]

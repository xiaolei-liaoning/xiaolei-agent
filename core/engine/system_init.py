"""系统初始化器 — 提取自 main.py 的 init_system()"""
import asyncio
import importlib
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SystemInitializer:
    """系统核心组件初始化器，每步独立方法。"""

    def __init__(self, app, ctx):
        self.app = app
        self.ctx = ctx
        self.env_status = {}

    async def initialize(self):
        """执行全部初始化步骤。"""
        self.ctx.startup_time = time.time()
        await self._step_register_tools()
        await self._step_init_dispatcher_and_plugins()
        await self._step_init_concurrent_processor()
        await self._step_init_task_planner()
        await self._step_init_other_components()
        await self._step_init_task_scheduler()
        await self._step_config_driven_services()
        await self._step_init_database()
        await self._step_init_feedback_hub()
        await self._step_inject_handler_refs()
        await self._step_inject_task_interface_refs()
        await self._step_check_env()
        self._log_summary()

    async def _step_register_tools(self):
        try:
            from core.multi_agent_v2.tools.tool_registry import get_tool_registry
            reg = get_tool_registry()
            await reg.discover_all()
            logger.info("V2 ToolRegistry 工具发现完成 (%d 个)", reg.count)
        except Exception as e:
            logger.warning("V2 ToolRegistry 发现失败: %s", e)
        try:
            from tools.tool_manager import register_all_skills
            register_all_skills()
            logger.info("ToolManager 内置工具注册完成（兼容路径）")
        except Exception as e:
            logger.debug("ToolManager 注册跳过: %s", e)
        
        # 注册 Agency Agents 角色匹配技能
        try:
            from core.skill_base import ToolRegistry
            from core.skills.agency_agents.skill import (
                AgencyAgentExecuteSkill,
                AgencyAgentListSkill,
                AgencyAgentMatcherSkill,
            )
            
            ToolRegistry.register(AgencyAgentMatcherSkill())
            ToolRegistry.register(AgencyAgentListSkill())
            ToolRegistry.register(AgencyAgentExecuteSkill())
            
            from core.skills.agency_agents.handler import get_agency_agent_matcher
            matcher = get_agency_agent_matcher()
            logger.info("✅ Agency Agents 角色匹配系统已注册 (%d 个专家角色)", len(matcher.agents))
        except Exception as e:
            logger.warning("Agency Agents 注册跳过: %s", e)

    async def _step_init_dispatcher_and_plugins(self):
        try:
            from core.engine.skill_dispatcher import SkillDispatcher
            self.ctx.dispatcher = SkillDispatcher()
            from core.plugin_loader import load_plugins
            await load_plugins()
            logger.info("Plugin 加载完成")

            # 连接插件注册的 MCP 服务器
            try:
                from core.mcp.plugin_bridge import connect_all_plugin_mcp_servers
                connected, failed = await connect_all_plugin_mcp_servers()
                logger.info(f"插件MCP连接: {len(connected)} 成功, {len(failed)} 失败")
            except Exception as e:
                logger.warning(f"插件MCP桥接失败（非致命）: {e}")
        except Exception as e:
            logger.error("Plugin加载失败: %s", e, exc_info=True)

    async def _step_init_concurrent_processor(self):
        try:
            from core.tasks.concurrent_processor import ConcurrentTaskProcessor
            self.ctx.processor = ConcurrentTaskProcessor()
            logger.info("ConcurrentTaskProcessor 初始化完成")
        except Exception as e:
            logger.error("ConcurrentTaskProcessor 初始化失败: %s", e, exc_info=True)

    async def _step_init_task_planner(self):
        try:
            from core.tasks.task_planner import TaskPlanner
            self.ctx.planner = TaskPlanner()
            logger.info("TaskPlanner 初始化完成")
        except Exception as e:
            logger.error("TaskPlanner 初始化失败: %s", e, exc_info=True)

    async def _step_init_other_components(self):
        components = [
            ("TaskProcessor", "core.tasks.task_processor", "task_processor"),
            ("自主搜索引擎", "core.search.rag_search_engine", "RAGSearchEngine"),
            # 已移除: ("监控管理器", "core.monitoring", "monitoring_manager"),  # DEPRECATED
        ]
        for name, module, obj in components:
            try:
                mod = importlib.import_module(module)
                instance = getattr(mod, obj)() if callable(getattr(mod, obj)) else getattr(mod, obj)
                if name == "监控管理器":
                    instance.start()
                elif name == "内存优化器":
                    instance.start()
                logger.info(f"{name}初始化完成")
            except Exception as e:
                logger.error(f"{name}初始化失败: {e}", exc_info=True)

    async def _step_init_task_scheduler(self):
        try:
            from core.tasks.task_scheduler import task_scheduler
            asyncio.create_task(task_scheduler.start())
            logger.info("任务调度器初始化完成")
        except Exception as e:
            logger.error("任务调度器初始化失败: %s", e, exc_info=True)

    async def _step_config_driven_services(self):
        try:
            from .config_loader import (
                auto_connect_mcp_servers,
                register_agents_from_config,
            )
            asyncio.create_task(auto_connect_mcp_servers())
            logger.info("配置驱动MCP服务器自启任务已提交")
            agents = register_agents_from_config()
            if agents:
                logger.info(f"配置驱动Agent注册完成: {len(agents)} 个")
        except Exception as e:
            logger.warning("配置驱动加载失败: %s", e)

    async def _step_init_database(self):
        try:
            from core.database import init_db
            init_db()
            self.ctx.db_initialized = True
            logger.info("MySQL 数据库初始化完成")
        except Exception as e:
            self.ctx.db_initialized = False
            logger.warning("MySQL 数据库初始化失败（系统仍可运行）: %s", e)

    async def _step_init_feedback_hub(self):
        """方案C: 注册 3 个 sink wrapper 到 FeedbackHub（不改原机制）"""
        try:
            from core.learning.feedback import get_hub
            from core.learning.reflection import ReviewerSink, EvolutionSink, MemorySink
            hub = get_hub()
            # 包装原机制 - 不改它们的实现
            import core.auto_reviewer as ar_mod
            import core.memory.self_evolution as se_mod
            import core.memory.memory_middleware as mw_mod
            hub.register(ReviewerSink(ar_mod))
            hub.register(EvolutionSink(se_mod))
            hub.register(MemorySink(mw_mod))
            self.ctx.feedback_hub = hub
            logger.info(f"FeedbackHub 初始化完成，已注册 {len(hub.sinks)} 个 sink")
        except Exception as e:
            logger.warning(f"FeedbackHub 初始化失败（系统仍可运行）: {e}", exc_info=True)

    async def _step_inject_handler_refs(self):
        try:
            from core.handlers import set_global_refs
            set_global_refs(self.ctx.dispatcher, self.ctx.processor, self.ctx.planner, self.ctx.db_initialized)
            logger.info("Handlers 全局引用设置完成")
        except Exception as e:
            logger.error("Handlers 全局引用设置失败: %s", e, exc_info=True)

    async def _step_inject_task_interface_refs(self):
        try:
            from core.handlers import handle_multi_step, handle_single_step
            from core.tasks.task_execution_interface import set_task_handlers

            class _TextAnalyzerAgent:
                """文本分析Agent — 基于 LLM 的文本理解"""
                async def execute(self, message: str, user_id: int) -> dict:
                    try:
                        from core.multi_agent_v2.tools.tool_registry import _handle_text_analyzer
                        result = await _handle_text_analyzer({"text": message})
                        if result.get("ok"):
                            return {"success": True, "reply": result.get("data", "")}
                        return {"success": False, "reply": result.get("error", "分析失败")}
                    except Exception as e:
                        return {"success": False, "reply": f"文本分析失败: {e}"}

            set_task_handlers(_TextAnalyzerAgent(), handle_multi_step, handle_single_step)
            logger.info("任务执行接口引用注入完成")
        except Exception as e:
            logger.error("任务执行接口引用注入失败: %s", e, exc_info=True)

    async def _step_check_env(self):
        try:
            from .check_env import check_env
            self.env_status = check_env()
            if not self.env_status.get("llm_ok"):
                logger.warning("LLM 未配置 — 聊天/代码生成/反思将不可用")
                logger.warning("请在 .env 中设置 ZHIPU_API_KEY 或 LLM_API_KEY")
        except Exception:
            pass

    def _log_summary(self):
        uptime = time.time() - self.ctx.startup_time
        logger.info("=" * 60)
        logger.info("  小雷版小龙虾 AI Agent v3.4.0 启动成功！")
        logger.info("  初始化耗时: %.2fs | DB: %s | LLM: %s", uptime,
                    "OK" if self.ctx.db_initialized else "OFF",
                    "OK" if self.env_status.get("llm_ok") else "未配置")
        logger.info("=" * 60)
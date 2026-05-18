"""工具管理器（精简版）

ToolManager 单例类：
- register_tool()  — 注册工具（handler + 元数据）
- execute()        — 执行工具，自动 Redis 缓存
- list_tools()     — 列出所有工具
- get_tool() / has_tool() — 查询工具
- _build_cache_key()  — MD5 哈希缓存键
- _get_cache() / _set_cache() — Redis 缓存读写
- execute_in_sandbox() — 沙盒安全执行代码

注意：技能注册已迁移到 core/skill_base.py (SkillRegistry) + core/guidance_skills.py。
ToolManager 仅保留 code_sandbox 一个内置工具，其余技能走 SkillRegistry 或 MCP。
"""
import json
import hashlib
import time
import logging
import threading
import asyncio
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)

# ─── TTL 策略（秒） ─────────────────────────────────────────────────────────
_TTL_MAP: Dict[str, int] = {
    "weather": 3600,
    "scraper": 600,
    "web_scraper": 600,
    "system_toolbox": 300,
    "system": 300,
    "translator": 3600,
    "data_analysis": 600,
    "gui_automation": 600,
    "rag_search": 600,
    "advanced_automation": 600,
    "search_engine": 600,  # 搜索引擎10分钟缓存
    "code_sandbox": 0,     # 代码执行不缓存（每次都是新的）
}

_DEFAULT_TTL = 600


class ToolManager:
    """工具管理器 — 单例模式（线程安全）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._tool_configs: Dict[str, Dict[str, Any]] = {}
        logger.info("ToolManager 初始化完成")

    @classmethod
    def get_instance(cls) -> "ToolManager":
        return cls()

    # ── 注册 ─────────────────────────────────────────────────────────────────
    def register_tool(self, name: str, handler: Any, description: str = "",
                      keywords: List[str] = None, priority: int = 3):
        """注册工具

        Args:
            name:        工具名称
            handler:     可调用对象（需有 execute 方法或直接 callable）
            description: 工具描述
            keywords:    关键词列表（用于技能分发）
            priority:    优先级（用于技能分发）

        注意：此方法同时将工具同步到 ToolRegistry，确保统一查询入口生效。
        """
        self._tools[name] = {
            "handler": handler,
            "description": description,
            "keywords": keywords or [],
            "priority": priority,
            "registered_at": time.time(),
        }
        self._tool_configs[name] = {
            "keywords": keywords or [],
            "priority": priority,
        }
        # 同步到 ToolRegistry（统一查询入口）
        try:
            from core.skill_base import ToolRegistry
            ToolRegistry.register_handler(
                name=name, handler=handler,
                description=description,
                keywords=keywords or [],
                priority=priority,
            )
        except Exception as exc:
            logger.debug("ToolRegistry 同步跳过: %s", exc)
        logger.info("工具注册成功: %s (priority=%d)", name, priority)

    # ── 执行 ─────────────────────────────────────────────────────────────────
    async def execute(self, tool_name: str, **kwargs) -> Any:
        """执行工具（自动 Redis 缓存）

        Returns:
            {"success": True, "result": ...} 或 {"success": False, "error": ...}
        """
        if tool_name not in self._tools:
            logger.warning("未找到工具: %s", tool_name)
            return {"success": False, "error": f"未找到工具: {tool_name}"}

        # 缓存检查
        cache_key = self._build_cache_key(tool_name, kwargs)
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.info("缓存命中: %s (key=%s)", tool_name, cache_key[:20])
            return cached

        handler = self._tools[tool_name]["handler"]
        start_time = time.time()

        try:
            # 优先调用 handler.execute()
            if hasattr(handler, "execute"):
                result = handler.execute(**kwargs)
                # 如果结果是协程，等待它完成
                if asyncio.iscoroutine(result):
                    result = await result
            elif callable(handler):
                result = handler(**kwargs)
                # 如果结果是协程，等待它完成
                if asyncio.iscoroutine(result):
                    result = await result
            else:
                return {"success": False, "error": f"工具 {tool_name} 无法执行"}

            elapsed = time.time() - start_time
            logger.info("工具 %s 执行完成, 耗时: %.3fs", tool_name, elapsed)

            # 统一结果格式
            if not isinstance(result, dict):
                result = {"success": True, "result": str(result)}

            # 写缓存
            if result.get("success", False):
                self._set_cache(cache_key, result, tool_name)

            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("工具 %s 执行失败 (%.3fs): %s", tool_name, elapsed, e)
            return {"success": False, "error": str(e)}

    async def execute_in_sandbox(self, 
                                code: str,
                                language: str = "python",
                                timeout: int = 30,
                                max_memory_mb: int = 512,
                                context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """在沙盒中安全执行代码
        
        Args:
            code: 要执行的代码字符串
            language: 编程语言（python/javascript/shell）
            timeout: 超时时间（秒）
            max_memory_mb: 最大内存限制（MB）
            context: 上下文变量字典
            
        Returns:
            {"success": bool, "result": ..., "stdout": ..., "stderr": ..., "execution_time": ...}
        """
        from core.tools.sandbox_executor import get_sandbox_executor, ResourceLimits, ExecutionStatus

        sandbox = get_sandbox_executor()
        
        # 配置资源限制
        limits = ResourceLimits(
            timeout=timeout,
            max_memory_mb=max_memory_mb,
            max_output_size_kb=1024
        )
        
        try:
            # 根据语言选择执行方法
            if language == "python":
                result = await sandbox.execute_python(
                    code=code,
                    limits=limits,
                    context=context
                )
            elif language == "javascript":
                result = await sandbox.execute_javascript(
                    code=code,
                    limits=limits
                )
            elif language == "shell":
                result = await sandbox.execute_shell(
                    command=code,
                    limits=limits
                )
            else:
                return {
                    "success": False,
                    "error": f"不支持的编程语言: {language}"
                }
            
            # 转换为统一格式
            success = result.status == ExecutionStatus.COMPLETED
            
            return {
                "success": success,
                "result": result.stdout if success else None,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "execution_time": result.execution_time,
                "status": result.status.value,
                "sandbox_id": result.sandbox_id,
                "error": result.error_message if not success else None
            }
            
        except Exception as e:
            logger.error(f"沙盒执行失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # ── 查询 ─────────────────────────────────────────────────────────────────
    def list_tools(self) -> List[Dict]:
        """列出所有已注册工具"""
        return [
            {
                "name": name,
                "description": info["description"],
                "keywords": info["keywords"],
                "priority": info["priority"],
            }
            for name, info in self._tools.items()
        ]

    def get_tool(self, name: str) -> Optional[Any]:
        """获取工具 handler"""
        return self._tools.get(name, {}).get("handler")

    def has_tool(self, name: str) -> bool:
        """检查工具是否已注册"""
        return name in self._tools

    # ── 缓存 ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _build_cache_key(tool_name: str, params: Dict) -> str:
        """MD5 哈希缓存键"""
        param_str = json.dumps(params, sort_keys=True, default=str)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        return f"tool:{tool_name}:{param_hash}"

    @staticmethod
    def _get_cache(key: str) -> Optional[Any]:
        """从 Redis 读取缓存"""
        try:
            from core.infrastructure.redis_pool import get_redis

            redis_client = get_redis(db=1)
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.debug("Redis 缓存读取失败: %s", exc)
        return None

    @staticmethod
    def _set_cache(key: str, value: Any, tool_name: str):
        """写入 Redis 缓存（按工具名选择 TTL）"""
        ttl = _TTL_MAP.get(tool_name, _DEFAULT_TTL)
        try:
            from core.infrastructure.redis_pool import get_redis

            redis_client = get_redis(db=1)
            redis_client.setex(key, ttl, json.dumps(value, default=str, ensure_ascii=False))
        except Exception as exc:
            logger.debug("Redis 缓存写入失败: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
#  注册所有内置技能（8 + 1）
# ═══════════════════════════════════════════════════════════════════════════════

def register_all_skills():
    """注册内置工具到 ToolManager（精简版）

    旧版 skills/X/handler.py 的动态导入已移除，所有技能通过以下通道调用：
    - 工具型技能 → MCP 服务器 (mcp/X_mcp_server.py, 独立进程)
    - 指导型技能 → GuidanceSkill (core/skill_base.py, 原生嵌入)
    - 沙盒代码执行 → 保留在 ToolManager

    ToolManager 仅保留 code_sandbox 用于安全代码执行。
    """
    tm = ToolManager.get_instance()

    # 只注册代码执行沙盒（其他工具走 SkillRegistry + MCP）
    # 直接创建沙盒处理器并注册
    try:
        handler = _create_sandbox_handler()
        tm.register_tool("code_sandbox", handler,
                         description="安全代码执行沙盒 - 支持Python/JavaScript/Shell",
                         keywords=["执行代码", "运行代码", "代码沙盒", "sandbox", "execute code", "run code"],
                         priority=9)
    except Exception as e:
        logger.error("沙盒工具注册失败: %s", e)

    logger.info("ToolManager 内置工具注册完成，共 %d 个", len(tm._tools))

def _create_sandbox_handler():
    """创建沙盒处理器"""
    class SandboxHandler:
        def __init__(self):
            self.tool_manager = ToolManager.get_instance()
        
        async def execute(self, 
                         code: str,
                         language: str = "python",
                         timeout: int = 30,
                         max_memory_mb: int = 512,
                         **kwargs):
            """执行沙盒代码"""
            return await self.tool_manager.execute_in_sandbox(
                code=code,
                language=language,
                timeout=timeout,
                max_memory_mb=max_memory_mb,
                context=kwargs.get("context")
            )
    
    return SandboxHandler()



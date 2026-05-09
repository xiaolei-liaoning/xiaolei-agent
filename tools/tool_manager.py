"""工具管理器（工业级）

ToolManager 单例类：
- register_tool()  — 注册工具（handler + 元数据）
- execute()        — 执行工具，自动 Redis 缓存
- list_tools()     — 列出所有工具
- get_tool() / has_tool() — 查询工具
- _build_cache_key()  — MD5 哈希缓存键
- _get_cache() / _set_cache() — Redis 缓存读写
- register_all_skills() — 注册所有 8+1 个内置技能
- execute_in_sandbox() — 沙盒安全执行代码
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
        from core.sandbox_executor import get_sandbox_executor, ResourceLimits, ExecutionStatus
        
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
            from core.redis_pool import get_redis

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
            from core.redis_pool import get_redis

            redis_client = get_redis(db=1)
            redis_client.setex(key, ttl, json.dumps(value, default=str, ensure_ascii=False))
        except Exception as exc:
            logger.debug("Redis 缓存写入失败: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
#  注册所有内置技能（8 + 1）
# ═══════════════════════════════════════════════════════════════════════════════

def register_all_skills():
    """注册所有内置技能到 ToolManager"""
    tm = ToolManager.get_instance()

    # 1. 天气
    _safe_register(tm, "weather", "skills.weather.handler", "weather_handler",
                   description="全国城市天气查询",
                   keywords=["天气", "气温", "温度", "weather"])

    # 2. 网页爬虫
    _safe_register(tm, "web_scraper", "skills.web_scraper.handler", "scraper_dispatcher",
                   description="网站爬虫 - 微博/百度/B站/抖音等",
                   keywords=["爬取", "抓取", "热搜", "热榜", "爬虫", "scrape"])

    # 3. 数据分析
    _safe_register(tm, "data_analysis", "skills.data_analysis.handler", "analysis_handler",
                   description="数据分析与可视化",
                   keywords=["分析", "统计", "可视化", "图表", "数据"])

    # 4. GUI 自动化
    _safe_register(tm, "gui_automation", "skills.gui_automation.handler", "gui_handler",
                   description="桌面应用自动化",
                   keywords=["打开", "点击", "发送", "自动化", "GUI"])

    # 5. 翻译
    _safe_register(tm, "translator", "skills.translator.handler", "translator",
                   description="多语言翻译助手",
                   keywords=["翻译", "translate", "中英互译"], priority=6)

    # 6. 高级自动化
    _safe_register(tm, "advanced_automation", "skills.advanced_automation.handler", "automation_hub",
                   description="全链路自动化工作流",
                   keywords=["工作流", "自动执行", "全链路"], priority=7)

    # 7. RAG 搜索
    _safe_register(tm, "rag_search", "skills.rag_search_handler", "rag_handler",
                   description="智能搜索与知识学习",
                   keywords=["搜索", "查询", "了解", "是什么", "search"])

    # 8. 系统工具箱
    _safe_register(tm, "system_toolbox", "skills.system_toolbox.handler", "system_handler",
                   description="系统信息查询与文件操作",
                   keywords=["系统", "时间", "日期", "计算", "内存"])

    # 9. 搜索引擎（与爬虫隔离）
    _safe_register(tm, "search_engine", "skills.search_engine.handler", "handler",
                   description="联网搜索引擎（search/scrape双模式）",
                   keywords=["搜索", "查询", "查找", "搜一下", "查一下", "了解一下", "search", "query"], priority=5)

    # 11-16. 人物Skill
    _safe_register(tm, "libai", "skills.人物.libai.handler", "handler",
                   description="诗仙李白 - 豪放不羁的唐代诗人",
                   keywords=["李白", "诗仙", "写诗", "作诗"], priority=4)
    
    _safe_register(tm, "goddess", "skills.人物.goddess.handler", "handler",
                   description="高冷女神 - 外冷内热",
                   keywords=["女神", "高冷", "冷淡"], priority=4)
    
    _safe_register(tm, "first_love", "skills.人物.first_love.handler", "handler",
                   description="温柔初恋 - 贴心伴侣",
                   keywords=["初恋", "温柔", "女朋友"], priority=4)
    
    _safe_register(tm, "bestfriend", "skills.人物.bestfriend.handler", "handler",
                   description="知心闺蜜 - 无话不谈",
                   keywords=["闺蜜", "姐妹", "吐槽"], priority=4)
    
    _safe_register(tm, "linus_torvalds", "skills.人物.linus_torvalds.handler", "handler",
                   description="Linus Torvalds - Linux之父",
                   keywords=["Linus", "Linux", "代码审查"], priority=4)
    
    _safe_register(tm, "john_carmack", "skills.人物.john_carmack.handler", "handler",
                   description="John Carmack - 传奇程序员",
                   keywords=["Carmack", "游戏优化", "性能"], priority=4)

    # 17. 深度思考
    _safe_register(tm, "deep_thinking", "skills.deep_thinking.handler", "get_deep_thinking_handler",
                   description="深度思考引擎 - 具备自主联网搜索能力",
                   keywords=["深度思考", "自主搜索", "联网查询", "最新信息", "分析一下", "研究一下", "了解一下", "详细分析", "深入探讨", "最新动态", "最新消息", "现在怎么样", "今天", "最近", "2026", "2025"], priority=8)

    # 18. 代码执行沙盒
    _safe_register(tm, "code_sandbox", "tools.tool_manager", "_create_sandbox_handler",
                   description="安全代码执行沙盒 - 支持Python/JavaScript/Shell",
                   keywords=["执行代码", "运行代码", "代码沙盒", "sandbox", "execute code", "run code"],
                   priority=9)

    # 19. OpenClaw工作流引擎增强技能
    _safe_register(tm, "openclaw_workflow", "skills.openclaw.handler", "get_openclaw_handler",
                   description="OpenClaw网格工作流引擎 - 提供模板库、版本管理、性能分析和导入导出功能",
                   keywords=["工作流", "workflow", "OpenClaw", "模板", "版本管理", "性能分析", "自动化流程"],
                   priority=2)

    # 20. 计算器技能
    _safe_register(tm, "calculator", "skills.calculator.handler", "get_calculator_handler",
                   description="基础数学计算器 - 支持加减乘除运算",
                   keywords=["计算", "计算器", "数学", "加减乘除", "calculate", "math"],
                   priority=3)

    # 21. MCP连接器技能
    _safe_register(tm, "mcp_connector", "skills.mcp_connector.handler", "MCPConnectorHandler",
                   description="MCP服务连接器 - 连接并调用外部MCP服务器",
                   keywords=["mcp", "connector", "协议", "插件", "连接服务", "the-agency"],
                   priority=3)

    # 22. 文本分析技能
    _safe_register(tm, "text_analyzer", "skills.text_analyzer.handler", "handler",
                   description="文本分析工具 - 统计字符数、词数、句子数，提取关键词",
                   keywords=["分析", "文本", "情感分析", "关键词提取", "词频统计", "text analysis"],
                   priority=3)

    # 23. 工作流引擎技能
    _safe_register(tm, "workflow_engine", "skills.workflow_engine", "get_workflow_manager",
                   description="工作流引擎管理器 - 可视化工作流搭建和执行",
                   keywords=["工作流", "流程", "自动化", "任务管理", "workflow", "flow"],
                   priority=2)

    # 24. XMI转换器技能
    _safe_register(tm, "xmi_converter", "skills.xmi_converter", "convert_xmi_to_workflow",
                   description="XMI格式转换器 - 将UML/XMI文件转换为可执行工作流",
                   keywords=["xmi", "转换", "格式", "uml", "工作流导入", "xml"],
                   priority=3)

    logger.info("内置技能注册完成，共 %d 个工具", len(tm._tools))


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


def _safe_register(tm: ToolManager, name: str, module_path: str, attr_name: str,
                   *, description: str, keywords: List[str], priority: int = 3):
    """安全注册工具（import 失败不影响其他工具）"""
    try:
        from importlib import import_module
        mod = import_module(module_path)
        handler = getattr(mod, attr_name)
        tm.register_tool(name, handler, description=description,
                         keywords=keywords, priority=priority)
    except Exception as e:
        logger.error("技能 %s 注册失败 (%s): %s", name, module_path, e)
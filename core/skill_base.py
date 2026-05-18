"""统一技能基类

类比 Claude Code 的 buildTool()——每个技能实现同一套接口，
上层调用方不需要关心具体技能的调用方式。

用法：
    class WeatherSkill(SkillHandler):
        name = "weather"
        description = "查询天气"
        input_schema = {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称"},
            },
        }

        async def execute(self, params, context=None):
            city = params.get("city", "北京")
            ...
            return {"success": True, "reply": "..."}

    注册到调度器：
        from .skill_base import SkillRegistry
        registry.register(WeatherSkill())
"""

from __future__ import annotations

import asyncio
import inspect
import os
import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  协议接口
# ═══════════════════════════════════════════════════════════════════════

@runtime_checkable
class ISkill(Protocol):
    """统一技能协议接口

    每个技能必须实现 execute() 方法，可选实现 validate() / describe()。
    """

    @property
    def name(self) -> str:
        """技能唯一标识"""
        ...

    @property
    def description(self) -> str:
        """技能描述（一句话）"""
        ...

    @property
    def keywords(self) -> List[str]:
        """匹配关键词列表"""
        ...

    @property
    def priority(self) -> int:
        """匹配优先级（越高越优先）"""
        ...

    async def execute(self, params: Dict[str, Any],
                      context: Any = None) -> Dict[str, Any]:
        """执行技能

        Args:
            params: 参数字典
            context: ExecutionContext 实例（可选）

        Returns:
            统一格式的结果字典，至少包含 success 字段：
            {"success": True, "reply": "..."}
        """
        ...


# ═══════════════════════════════════════════════════════════════════════
#  统一返回类型 & 注册表
# ═══════════════════════════════════════════════════════════════════════

class ToolCallResult:
    """统一工具调用返回

    所有通过 ToolRegistry.execute() 调用的工具都返回此类型。
    """
    def __init__(self, success: bool = False, data: Any = None,
                 error: str = "", permission: str = ""):
        self.success = success
        self.data = data
        self.error = error
        self.permission = permission  # 触发的是哪个权限检查点

    @classmethod
    def ok(cls, data: Any = None) -> "ToolCallResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str = "", permission: str = "") -> "ToolCallResult":
        return cls(success=False, error=error, permission=permission)

    def to_dict(self) -> dict:
        return {"success": self.success, "result": self.data,
                "error": self.error, "permission": self.permission}


class ToolRegistry:
    """统一注册表 — 合并 SkillRegistry + ToolManager + SkillDispatcher 的注册

    所有工具/技能统一走这里注册和查询，后续权限拦截和智能调度
    只需在此类上加逻辑，不用改每个调用点。
    """

    _tools: Dict[str, ISkill] = {}
    _keywords: Dict[str, List[str]] = {}
    _permissions: Dict[str, str] = {}  # skill_name → PermissionType 字符串
    _loaded: bool = False

    @classmethod
    def reset(cls):
        """重置注册表（用于测试或重新加载）"""
        cls._tools = {}
        cls._keywords = {}
        cls._permissions = {}
        cls._loaded = False
        logger.info("ToolRegistry 已重置")

    # ── 注册 ────────────────────────────────────────────────────────────

    @classmethod
    def register(cls, skill: ISkill, keywords: List[str] = None,
                 permission: str = ""):
        """注册一个技能到统一注册表

        此方法同时兼容 SkillRegistry.register() 和 ToolManager.register_tool()。
        keywords 用于 match() 的关键词查找，permission 用于权限拦截。
        """
        name = skill.name
        cls._tools[name] = skill
        if keywords:
            cls._keywords[name] = keywords
        elif hasattr(skill, "keywords") and skill.keywords:
            cls._keywords[name] = list(skill.keywords)
        if permission:
            cls._permissions[name] = permission

    @classmethod
    def register_handler(cls, name: str, handler: Any, description: str = "",
                         keywords: List[str] = None, priority: int = 3,
                         permission: str = ""):
        """注册一个 handler 函数/对象为技能（兼容 ToolManager 的非 ISkill 接口）

        自动用 LegacySkillAdapter 包装，简化迁移。
        """
        from types import ModuleType
        if isinstance(handler, type):
            inst = handler() if not isinstance(handler, ISkill) else handler
        else:
            inst = handler

        if isinstance(inst, ISkill):
            skill = inst
        else:
            skill = LegacySkillAdapter(
                handler_module=handler,
                skill_name=name,
                description=description,
                keywords=keywords or [],
                priority=priority,
            )
        cls.register(skill, keywords=keywords, permission=permission)

    # ── 匹配 ────────────────────────────────────────────────────────────

    @classmethod
    def _keyword_hits(cls, keywords: list, message_lower: str) -> int:
        """计算关键词命中数（支持中文模糊匹配）"""
        hits = 0
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in message_lower:
                hits += 1
            elif len(kw) <= 4:
                chars = sum(1 for c in kw_lower if c in message_lower)
                if chars >= len(kw_lower) * 0.7:
                    hits += 0.5
        return hits

    @classmethod
    def match(cls, message: str) -> Optional[str]:
        """基于关键词匹配，返回技能名称

        先查自身注册表，未命中时兜底查 SkillRegistry。
        """
        message_lower = message.lower()
        best_name: Optional[str] = None
        best_score = 0

        # 1. 查自身
        for name, keywords in cls._keywords.items():
            hits = cls._keyword_hits(keywords, message_lower)
            skill = cls._tools.get(name)
            priority = skill.priority if hasattr(skill, "priority") else 5
            score = hits * priority
            if score > best_score:
                best_score = score
                best_name = name

        # 2. 自身未命中，兜底查 SkillRegistry
        if not best_name:
            try:
                sr = get_skill_registry()
                matched = sr.match(message)
                if matched:
                    best_name = matched.name
                    # 同步注册到 ToolRegistry，下次直接命中
                    cls.register(matched)
            except Exception:
                pass

        return best_name

    @classmethod
    def match_skill(cls, message: str) -> Optional[ISkill]:
        """返回匹配的 ISkill 实例"""
        name = cls.match(message)
        if name:
            skill = cls._tools.get(name)
            if skill:
                return skill
            # 可能在 SkillRegistry 中
            try:
                return get_skill_registry().get(name)
            except Exception:
                pass
        return None

    # ── 执行 ────────────────────────────────────────────────────────────

    @classmethod
    async def execute(cls, name: str, params: dict = None,
                      context: Any = None) -> ToolCallResult:
        """统一执行入口

        先查权限（如有配置），再执行。
        权限检查失败时返回 ToolCallResult(success=False, permission=xxx)。
        """
        skill = cls._tools.get(name)
        # 自身未命中，兜底查 SkillRegistry
        if not skill:
            try:
                skill = get_skill_registry().get(name)
            except Exception:
                pass
        if not skill:
            return ToolCallResult.fail(error=f"tool '{name}' not found")

        # 权限检查
        perm_type = cls._permissions.get(name, "")
        if perm_type:
            allowed = await cls._check_permission(perm_type, context)
            if not allowed:
                return ToolCallResult.fail(
                    error=f"permission denied: {perm_type}",
                    permission=perm_type)

        try:
            result = await skill.execute(params or {}, context)
            if isinstance(result, dict) and result.get("success"):
                return ToolCallResult.ok(data=result.get("reply", result))
            elif isinstance(result, dict):
                return ToolCallResult.fail(error=result.get("error", "unknown"))
            return ToolCallResult.ok(data=result)
        except Exception as e:
            logger.warning(f"tool '{name}' execute error: {e}")
            return ToolCallResult.fail(error=str(e))

    @classmethod
    async def _check_permission(cls, perm_type: str, context: Any) -> bool:
        """权限检查 — 默认放行，由权限模块覆写行为"""
        try:
            from core.services.permission_service import get_permission_service, PermissionDecision
            ps = get_permission_service()
            decision = await ps.check_permission(perm_type, {"context": context})
            return decision in (PermissionDecision.ALLOW, PermissionDecision.ALWAYS_ALLOW)
        except Exception:
            return True  # 默认放行，保持兼容

    # ── 查询 ────────────────────────────────────────────────────────────

    @classmethod
    def get(cls, name: str) -> Optional[ISkill]:
        return cls._tools.get(name)

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._tools

    @classmethod
    def list(cls) -> List[dict]:
        return [
            {"name": name, "keywords": cls._keywords.get(name, []),
             "permission": cls._permissions.get(name, "")}
            for name in cls._tools
        ]

    @classmethod
    def unregister(cls, name: str) -> bool:
        """反注册一个技能，从所有索引中清理"""
        existed = name in cls._tools
        cls._tools.pop(name, None)
        cls._keywords.pop(name, None)
        cls._permissions.pop(name, None)
        if existed:
            logger.info("ToolRegistry 反注册技能: %s", name)
        return existed

    @classmethod
    def get_keywords(cls, name: str) -> List[str]:
        return cls._keywords.get(name, [])

    @classmethod
    def set_permission(cls, name: str, perm_type: str):
        cls._permissions[name] = perm_type


# ═══════════════════════════════════════════════════════════════════════
#  基类
# ═══════════════════════════════════════════════════════════════════════

class SkillHandler:
    """技能基类——提供默认实现，子类只需重写 execute()

    类似 Claude Code 的 buildTool() + TOOL_DEFAULTS，
    大部分方法已有安全默认值。
    """

    # ── 子类覆写 ───────────────────────────────────────────────────────

    name: str = ""
    description: str = ""
    keywords: List[str] = []
    priority: int = 5

    # 可选的 JSON Schema 定义（用于参数校验和文档）
    input_schema: Optional[Dict[str, Any]] = None

    # ── 接口实现 ───────────────────────────────────────────────────────

    async def execute(self, params: Dict[str, Any],
                      context: Any = None) -> Dict[str, Any]:
        """执行技能——子类必须重写此方法

        Args:
            params: 执行参数（字符串值，来源是 extract_params 或用户输入）
            context: ExecutionContext 实例

        Returns:
            {"success": True, "reply": "..."} 或 {"success": False, "error": "..."}
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} 未实现 execute() 方法"
        )

    def validate(self, params: Dict[str, Any]) -> Optional[str]:
        """参数校验——子类可选覆写

        Args:
            params: 执行参数

        Returns:
            错误字符串（参数无效时）或 None（参数有效时）
        """
        if self.input_schema and "required" in self.input_schema:
            for field in self.input_schema["required"]:
                if field not in params or not params[field]:
                    return f"缺少必要参数: {field}"
        return None

    # ── 基于反射的元信息（无需子类配置） ───────────────────────────────

    def get_name(self) -> str:
        return self.name or self.__class__.__name__.lower().replace("skill", "")

    def get_keywords(self) -> List[str]:
        return self.keywords

    def get_priority(self) -> int:
        return self.priority

    # ── 适配旧接口 ──────────────────────────────────────────────────────

    async def try_execute(self, action: str, params: Dict[str, Any],
                          context: Any = None) -> Dict[str, Any]:
        """兼容旧版 skill_loader 的调用方式

        旧代码调用 _handle_tool(skill_name, params)，
        新代码调用 skill.execute(params, context)。
        """
        return await self.execute(params, context)


# ═══════════════════════════════════════════════════════════════════════
#  适配器：将旧 handler 包装为新接口
# ═══════════════════════════════════════════════════════════════════════

class LegacySkillAdapter(SkillHandler):
    """旧版 skill handler 适配器

    将 module-level handle() 函数或类的 handle() 方法包装为 ISkill 接口。
    用于迁移过渡期——新技能直接用 SkillHandler，旧技能通过此适配器兼容。
    """

    def __init__(self, handler_module, skill_name: str = "",
                 description: str = "", keywords: List[str] = None,
                 priority: int = 5):
        self._handler = handler_module
        self._skill_name = skill_name or getattr(handler_module, "name", "unknown")
        self._description = description
        self.name = self._skill_name
        self.description = description
        self.keywords = keywords or []
        self.priority = priority

        # 探测 handler 的接口类型
        self._is_class = isinstance(handler_module, type)
        self._instance = None
        if not self._is_class:
            self._instance = handler_module

    async def execute(self, params: Dict[str, Any],
                      context: Any = None) -> Dict[str, Any]:
        handler = self._instance or self._handler
        result = None

        # 尝试多种调用方式
        if hasattr(handler, "execute"):
            # 同步 execute(city, **kwargs) 或 async execute()
            method = handler.execute
            if inspect.iscoroutinefunction(method):
                result = await method(**params)
            else:
                result = method(**params)
        elif hasattr(handler, "aexecute"):
            method = handler.aexecute
            if inspect.iscoroutinefunction(method):
                result = await method(**params)
            else:
                result = method(**params)
        elif hasattr(handler, "handle"):
            # module-level async def handle(action, params)
            method = handler.handle
            if inspect.iscoroutinefunction(method):
                result = await method(action=params.get("action", ""), params=params)
            else:
                result = method(action=params.get("action", ""), params=params)
        else:
            # 尝试直接调用模块级函数
            import types
            if isinstance(handler, types.ModuleType):
                if hasattr(handler, "handle"):
                    fn = handler.handle
                    sig = inspect.signature(fn)
                    if "action" in sig.parameters:
                        result = await fn(action=params.get("action", ""), **params)
                    else:
                        result = await fn(**params)
                else:
                    result = {"success": False, "error": f"skill {self._skill_name} 没有 handle()"}
            else:
                result = {"success": False, "error": f"无法识别 skill handler: {type(handler)}"}

        # 统一返回格式
        if not isinstance(result, dict):
            result = {"success": True, "reply": str(result)}
        return result


# ═══════════════════════════════════════════════════════════════════════
#  指导型技能 — 包装 SKILL.md 让 LLM 直接使用
# ═══════════════════════════════════════════════════════════════════════

class GuidanceSkill(SkillHandler):
    """指导型技能：将 SKILL.md 打包为 ISkill 接口

    这些技能没有可执行代码，而是提供指导内容让 LLM 自行遵循。
    execute() 返回 SKILL.md 全文 + 执行计划，供 LLM 作为上下文。

    用法：
        skill = GuidanceSkill("product-capability",
                              description="产品能力分析",
                              skill_md_path="/path/to/SKILL.md",
                              keywords=["产品", "能力", "prd"])
        registry.register(skill)
        result = await skill.execute({"task": "分析XX产品"})
        # result["reply"] → SKILL.md 全文 + 执行计划
    """

    def __init__(self, name: str, description: str = "",
                 skill_md_path: str = "", keywords: list = None,
                 priority: int = 3):
        self.name = name
        self.description = description
        self.skill_md_path = skill_md_path
        self.keywords = keywords or []
        self.priority = priority
        self._content: str = ""

    def load_content(self) -> str:
        """读取 SKILL.md 内容"""
        if self._content:
            return self._content
        if not self.skill_md_path or not os.path.exists(self.skill_md_path):
            self._content = f"（SKILL.md 未找到: {self.skill_md_path}）"
            return self._content
        try:
            with open(self.skill_md_path, 'r', encoding='utf-8') as f:
                self._content = f.read()
        except Exception as e:
            self._content = f"（读取失败: {e}）"
        return self._content

    async def execute(self, params: Dict[str, Any],
                      context: Any = None) -> Dict[str, Any]:
        """用 SKILL.md 指导内容驱动 LLM 执行

        加载 SKILL.md 作为 system prompt，调用 LLM 完成任务。
        无 task 参数时仅返回指导内容（供展示）。
        """
        content = self.load_content()
        task = params.get("task", params.get("query", ""))
        message = params.get("message", params.get("user_message", ""))

        # 无具体任务时，返回指导内容
        if not task and not message:
            return {
                "success": True,
                "reply": f"# {self.name}\n\n{self.description}\n\n{content[:2000]}",
                "content": content,
                "skill_name": self.name,
                "skill_type": "guidance",
            }

        # 有具体任务时，用 SKILL.md 驱动 LLM
        try:
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()

            user_text = message or task
            messages = [
                {"role": "system", "content": f"{content}\n\n请严格按照上述指导内容执行任务。"},
                {"role": "user", "content": user_text},
            ]

            reply = await router.chat(messages, temperature=0.7, max_tokens=2000)

            return {
                "success": True,
                "reply": reply,
                "content": content,
                "skill_name": self.name,
                "skill_type": "guidance",
                "task": task,
            }
        except Exception as e:
            logger.warning(f"GuidanceSkill LLM 执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": content,
                "skill_name": self.name,
                "skill_type": "guidance",
            }


# ═══════════════════════════════════════════════════════════════════════
#  注册表
# ═══════════════════════════════════════════════════════════════════════

class SkillRegistry:
    """技能注册表——管理所有 ISkill 实例

    用法：
        registry = SkillRegistry()
        registry.register(WeatherSkill())
        registry.register(LegacySkillAdapter(weather_handler))

        skill = registry.match("北京天气")
        result = await skill.execute({"city": "北京"})
    """

    def __init__(self):
        self._skills: Dict[str, ISkill] = {}

    def register(self, skill: ISkill) -> None:
        """注册一个技能"""
        name = skill.name
        self._skills[name] = skill
        logger.info(f"注册技能: {name}")

    def register_many(self, skills: List[ISkill]) -> None:
        for s in skills:
            self.register(s)

    def get(self, name: str) -> Optional[ISkill]:
        """按名称获取技能"""
        return self._skills.get(name)

    def all(self) -> List[ISkill]:
        """获取所有已注册技能"""
        return list(self._skills.values())

    def match(self, message: str) -> Optional[ISkill]:
        """基于关键词匹配技能（支持中文分词模糊匹配）"""
        message_lower = message.lower()
        best: Optional[ISkill] = None
        best_score = 0

        for skill in self._skills.values():
            keywords = skill.keywords if hasattr(skill, "keywords") else []
            hits = ToolRegistry._keyword_hits(keywords, message_lower)
            priority = skill.priority if hasattr(skill, "priority") else 5
            score = hits * priority
            if score > best_score:
                best_score = score
                best = skill

        return best

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)


# 全局单例
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry


def register_skill(skill: ISkill) -> None:
    """便捷函数：注册一个技能到全局注册表"""
    get_skill_registry().register(skill)


def discover_skills(base_dir: Optional[str] = None) -> int:
    """自动发现并加载所有 skills/ 目录下的 skill.py 文件

    每个 skill.py 在模块顶层调用 register_skill() 完成自注册。
    此函数只需确保文件被 import 即可。

    Args:
        base_dir: 项目根目录（默认从当前模块推导）

    Returns:
        发现的 skill.py 文件数量
    """
    import importlib.util
    import os
    import sys
    from pathlib import Path

    if base_dir is None:
        base_dir = str(Path(__file__).parent.parent)

    skills_dir = os.path.join(base_dir, "skills")
    if not os.path.isdir(skills_dir):
        logger.warning(f"skills 目录不存在: {skills_dir}")
        return 0

    count = 0
    for entry in os.listdir(skills_dir):
        skill_py = os.path.join(skills_dir, entry, "skill.py")
        if not os.path.isfile(skill_py):
            continue
        mod_name = f"skills.{entry}.skill"
        if mod_name in sys.modules:
            continue  # 已加载过
        try:
            spec = importlib.util.spec_from_file_location(mod_name, skill_py)
            if spec and spec.loader:
                spec.loader.exec_module(importlib.util.module_from_spec(spec))
                count += 1
                logger.debug(f"发现技能: {entry}")
        except Exception as e:
            logger.warning(f"加载技能 {entry} 失败: {e}")

    if count > 0:
        logger.info(f"技能自动发现完成: {count} 个")
    return count

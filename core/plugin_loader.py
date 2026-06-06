"""插件加载器 — 统一加载 plugin/ 容器中的功能级资源

职责：
1. 读取 plugin/plugin.json 清单
2. 自动注册 MCP 服务器（连接配置 + 进程管理）
3. 自动载入本地 Skills（keyword 注册 + workflow_engine 等）
4. 自动挂载功能级 API 路由
5. 统一初始化/关闭生命周期

替代方案：
  取代 main.py 中分散的 register_tool()、init_scheduled_tasks()、
  asyncio.create_task(auto_connect_mcp()) 等手工初始化代码。
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).parent.parent / "plugin"


# ═══════════════════════════════════════════════════════════════════════
#  核心接口
# ═══════════════════════════════════════════════════════════════════════

class PluginLoader:
    """插件加载器 — 单例

    支持两种插件模式：
    1. 传统模式：plugin/plugin.json 集中声明所有组件
    2. 动态模式：plugin/*/plugin.json 子目录独立插件，自动发现
    """

    _instance: Optional["PluginLoader"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.manifest: Dict[str, Any] = {}
        self.loaded_skills: List[str] = []
        self.loaded_mcp_servers: List[str] = []
        self.loaded_api_routes: List[str] = []
        self.discovered_plugins: List[str] = []
        self.sub_plugin_registrations: List[dict] = []

    # ── 加载清单 ────────────────────────────────────────────────────

    def load_manifest(self) -> Dict[str, Any]:
        """读取 plugin.json"""
        manifest_path = PLUGIN_DIR / "plugin.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    self.manifest = json.load(f)
                logger.info(f"📦 plugin.json loaded: {self.manifest.get('name', 'unknown')} v{self.manifest.get('version', '?')}")
            except Exception as e:
                logger.error(f"❌ plugin.json 加载失败: {e}")
        else:
            logger.warning(f"⚠️ plugin.json 不存在: {manifest_path}")
        return self.manifest

    # ── 动态子插件发现 ──────────────────────────────────────────────

    def discover_sub_plugins(self) -> List[dict]:
        """扫描 plugin/*/plugin.json 发现子插件

        每个子目录只要包含 plugin.json 就视为一个独立插件。
        返回所有发现并成功解析的子插件清单。
        """
        discovered = []
        for sub_dir in sorted(PLUGIN_DIR.iterdir()):
            if not sub_dir.is_dir():
                continue
            if sub_dir.name.startswith("_") or sub_dir.name.startswith("."):
                continue
            if sub_dir.name in ("mcp", "skills", "api", "config"):
                continue  # builtin 目录，不走动态发现

            plugin_json = sub_dir / "plugin.json"
            if not plugin_json.exists():
                continue

            try:
                with open(plugin_json, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                cfg["_plugin_dir"] = str(sub_dir)
                cfg["_plugin_name"] = cfg.get("name", sub_dir.name)
                discovered.append(cfg)
                self.discovered_plugins.append(sub_dir.name)
                logger.info(f"  🔌 发现插件 [{sub_dir.name}]: {cfg.get('description', '')}")
            except Exception as e:
                logger.warning(f"  ⚠️ 插件 {sub_dir.name} 解析失败: {e}")

        self.discovered_plugins = [p["_plugin_name"] for p in discovered]
        self.sub_plugin_registrations = discovered
        return discovered

    # ── 统一入口 ────────────────────────────────────────────────────

    async def load_all(self) -> Dict[str, Any]:
        """加载所有功能级资源：主清单 + 所有子插件

        Returns:
            {"skills": [...], "mcp_servers": [...], "api_routes": [...],
             "sub_plugins": [...], "guidance_skills": int}
        """
        self.load_manifest()

        # 发现并加载子插件
        sub_plugins = self.discover_sub_plugins()

        registry = self.manifest.get("registration", {})
        results = {}
        results["sub_plugins"] = [p["_plugin_name"] for p in sub_plugins]

        if registry.get("auto_register_skills", True):
            results["skills"] = await self.load_skills()

        if registry.get("auto_connect_mcp", True):
            results["mcp_servers"] = await self.load_mcp_servers()

        if registry.get("auto_mount_api_routes", True):
            results["api_routes"] = await self.load_api_routes()

        if registry.get("load_guidance_skills", True):
            results["guidance_skills"] = await self.load_guidance_skills()

        # 加载子插件的各组件
        for plugin_cfg in sub_plugins:
            sub_results = await self._load_sub_plugin(plugin_cfg)
            for k, v in sub_results.items():
                if isinstance(v, list):
                    results.setdefault(k, []).extend(v)
                elif isinstance(v, (int, float)):
                    results.setdefault(k, 0)
                    results[k] += v

        total = sum(len(v) for v in results.values() if isinstance(v, list))
        logger.info(f"✅ Plugin 系统加载完成: {len(sub_plugins)} 个子插件, {total} 组件")
        return results

    async def _load_sub_plugin(self, cfg: dict) -> Dict[str, Any]:
        """加载单个子插件的所有组件"""
        results = {"sub_plugin_skills": [], "sub_plugin_mcp": []}

        plugin_dir = Path(cfg["_plugin_dir"])
        plugin_name = cfg["_plugin_name"]

        # 加载子插件的 MCP 服务器
        for mcp_cfg in cfg.get("mcp_servers", []):
            try:
                server_name = mcp_cfg.get("name", f"{plugin_name}-mcp")
                command = mcp_cfg.get("command", "python3")
                args = mcp_cfg.get("args", [])

                from core.mcp.mcp_client import mcp_client
                await mcp_client.connect_server(
                    name=server_name,
                    command=command,
                    args=args,
                    cwd=str(PLUGIN_DIR),
                )
                self.loaded_mcp_servers.append(server_name)
                results["sub_plugin_mcp"].append(server_name)
                logger.info(f"  ✅ [{plugin_name}] MCP: {server_name}")
            except Exception as e:
                logger.warning(f"  ⚠️ [{plugin_name}] MCP 注册失败: {e}")

        # 加载子插件的 Skills
        for skill_cfg in cfg.get("skills", []):
            try:
                name = skill_cfg.get("name", plugin_name)
                keywords = skill_cfg.get("keywords", [])
                priority = skill_cfg.get("priority", 3)
                description = skill_cfg.get("description", "")

                from core.engine.skill_dispatcher import get_skill_dispatcher
                sd = get_skill_dispatcher()
                sd.register_tool(
                    name=name,
                    keywords=keywords,
                    priority=priority,
                    description=description,
                )

                # 如果有 SKILL.md，注册为指导型技能
                skill_md = skill_cfg.get("skill_md", "")
                if skill_md:
                    md_path = plugin_dir / skill_md
                    if md_path.exists():
                        self._register_skill_md(name, description, keywords, str(md_path))

                self.loaded_skills.append(name)
                results["sub_plugin_skills"].append(name)
                logger.info(f"  ✅ [{plugin_name}] Skill: {name}")
            except Exception as e:
                logger.warning(f"  ⚠️ [{plugin_name}] Skill 注册失败: {e}")

        return results

    def _extract_keywords_from_skill_md(self, md_path: str) -> List[str]:
        """从SKILL.md中提取触发关键词（委托模块级函数）"""
        return extract_keywords_from_skill_md(md_path)

    def _register_skill_md(self, name: str, description: str, keywords: list, md_path: str):
        """注册 SKILL.md 为指导型技能"""
        try:
            from core.skill_base import GuidanceSkill, get_skill_registry
            skill = GuidanceSkill(
                name=name,
                description=description or name,
                skill_md_path=md_path,
                keywords=keywords,
                priority=5,
            )
            skill.load_content()
            registry = get_skill_registry()
            registry.register(skill)
        except Exception as e:
            logger.warning(f"  ⚠️ SKILL.md 注册失败 {name}: {e}")

    # ── Skills 加载 ─────────────────────────────────────────────────

    async def load_skills(self) -> List[str]:
        """加载 plugin/skills/ 下的本地 Skills"""
        skills_cfg = self.manifest.get("skills", {})
        skill_names = skills_cfg.get("local_skills", [])
        results = []

        for name in skill_names:
            try:
                module_path = f"plugin.skills.{name}"
                if name == "workflow_engine":
                    from tools.tool_manager import ToolManager
                    mod = __import__(f"plugin.skills.{name}", fromlist=[name])
                    if hasattr(mod, "get_workflow_manager"):
                        handler = mod.get_workflow_manager()
                        ToolManager.get_instance().register_tool(
                            name="workflow_engine", handler=handler,
                            description="工作流引擎管理器",
                            keywords=["工作流", "流程", "workflow"],
                            priority=2)
                else:
                    from core.engine.skill_dispatcher import get_skill_dispatcher
                    sd = get_skill_dispatcher()
                    sd.register_tool(
                        name=name,
                        keywords=[name, name.replace("_", " ")],
                        priority=3,
                        description=f"插件技能: {name}")

                self.loaded_skills.append(name)
                results.append(name)
                logger.debug(f"  ✅ Skill: {name}")
            except Exception as e:
                logger.warning(f"  ⚠️ Skill {name} 加载失败: {e}")

        for persona in skills_cfg.get("persona_skills", []):
            try:
                from core.skill_base import GuidanceSkill, ToolRegistry, get_skill_registry

                # 构建 SKILL.md 路径: skills/人物/{name}/SKILL.md
                md_path = PLUGIN_DIR.parent / "skills" / "人物" / persona / "SKILL.md"

                if md_path.exists():
                    # ✅ 从SKILL.md中提取关键词（解析"## 🔑 触发关键词"部分）
                    keywords = self._extract_keywords_from_skill_md(str(md_path))
                    if not keywords:
                        # 兜底：使用角色名
                        keywords = [persona, persona.replace("_", " ")]
                    
                    # 注册为 GuidanceSkill（SKILL.md 驱动 LLM）
                    skill = GuidanceSkill(
                        name=persona,
                        description=f"人物: {persona}",
                        skill_md_path=str(md_path),
                        keywords=keywords,
                        priority=4,
                    )
                    skill.load_content()
                    
                    # ✅ 同时注册到两个注册表，确保所有路径都能找到
                    ToolRegistry.register(skill, keywords=keywords)
                    registry = get_skill_registry()
                    registry.register(skill)
                else:
                    # 无 SKILL.md 时回退到旧方式
                    from core.engine.skill_dispatcher import get_skill_dispatcher
                    sd = get_skill_dispatcher()
                    sd.register_tool(
                        name=persona,
                        keywords=[persona],
                        priority=4,
                        description=f"人物: {persona}")

                self.loaded_skills.append(persona)
                results.append(persona)
            except Exception as e:
                logger.warning(f"  ⚠️ 人物技能 {persona} 加载失败: {e}")

        logger.info(f"📦 Skills 加载: {len(results)} 个")
        return results

    # ── 指导型 Skills ───────────────────────────────────────────────

    async def load_guidance_skills(self) -> int:
        """加载 everything-claude-code 指导型技能"""
        skills_cfg = self.manifest.get("skills", {})
        guidance_cfg = skills_cfg.get("guidance_skills", {})
        source_path = guidance_cfg.get("source", "")
        
        # 验证路径
        if source_path:
            import os
            expanded_path = os.path.expanduser(source_path)
            if not os.path.isdir(expanded_path):
                logger.warning(f"⚠️ 指导型技能路径不存在: {source_path}")
                return 0
        
        try:
            from core.guidance_skills import load_guidance_skills
            count = load_guidance_skills()
            logger.info(f"📖 指导型技能: {count} 个")
            return count
        except Exception as e:
            logger.warning(f"⚠️ 指导型技能加载失败: {e}")
            return 0

    # ── MCP 服务器 ─────────────────────────────────────────────────

    async def load_mcp_servers(self) -> List[str]:
        """加载 MCP 服务器配置与自动连接"""
        mcp_cfg = self.manifest.get("mcp_servers", {})
        config_file = PLUGIN_DIR / mcp_cfg.get("config_file", "config/mcp_servers.yml")
        results = []

        if not config_file.exists():
            logger.warning(f"⚠️ MCP 配置文件不存在: {config_file}")
            return results

        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            servers = data.get("servers", {})
            for name, cfg in servers.items():
                if not cfg.get("auto_connect", True):
                    continue

                args = cfg.get("args", [])
                adjusted_args = []
                for arg in args:
                    if arg.startswith("mcp/") and not arg.startswith("plugin/mcp/"):
                        adjusted_args.append(arg.replace("mcp/", "plugin/mcp/", 1))
                    else:
                        adjusted_args.append(arg)

                try:
                    from core.mcp.awesome_mcp_manager import awesome_mcp_manager
                    result = await awesome_mcp_manager.quick_connect(name)
                    if result.get("success"):
                        self.loaded_mcp_servers.append(name)
                        results.append(name)
                        logger.debug(f"  ✅ MCP: {name}")
                    else:
                        logger.warning(f"  ⚠️ MCP {name} 连接失败: {result.get('message')}")
                except Exception as e:
                    logger.warning(f"  ⚠️ MCP {name} 异常: {e}")

        except Exception as e:
            logger.error(f"❌ MCP 加载失败: {e}")

        logger.info(f"🔗 MCP servers 加载: {len(results)} 个")
        return results

    # ── API 路由 ────────────────────────────────────────────────────

    async def load_api_routes(self) -> List[str]:
        """加载 plugin/api/ 下的功能级 API 路由"""
        api_cfg = self.manifest.get("api_routes", {})
        enabled = api_cfg.get("enabled", [])
        results = []

        for name in enabled:
            try:
                module_path = f"plugin.api.{name}"
                __import__(module_path)
                self.loaded_api_routes.append(name)
                results.append(name)
                logger.debug(f"  ✅ API: {name}")
            except Exception as e:
                logger.warning(f"  ⚠️ API {name} 加载失败: {e}")

        logger.info(f"🌐 API routes 加载: {len(results)} 个")
        return results

    # ── 列表查询 ────────────────────────────────────────────────────

    def list_plugins(self) -> List[dict]:
        """列出所有已发现的插件"""
        plugins = []
        for p in self.sub_plugin_registrations:
            plugins.append({
                "name": p.get("_plugin_name"),
                "version": p.get("version", "?"),
                "description": p.get("description", ""),
                "skills": [s.get("name") for s in p.get("skills", [])],
                "mcp_servers": [m.get("name") for m in p.get("mcp_servers", [])],
            })
        return plugins

    def list_skills(self) -> List[str]:
        """列出所有已加载的 Skills"""
        return self.loaded_skills

    def list_mcp_servers(self) -> List[str]:
        """列出所有已加载的 MCP 服务器"""
        return self.loaded_mcp_servers

    # ── 增量接口 ────────────────────────────────────────────────────

    async def add_skill(self, name: str, keywords: list = None,
                         priority: int = 3, description: str = "",
                         skill_md_path: str = "") -> bool:
        """增量添加一个技能"""
        try:
            from core.engine.skill_dispatcher import get_skill_dispatcher
            sd = get_skill_dispatcher()
            sd.register_tool(
                name=name, keywords=keywords or [name],
                priority=priority, description=description,
            )
            # 如果有 SKILL.md，注册为指导型技能
            if skill_md_path:
                md_path = Path(skill_md_path)
                if md_path.exists():
                    from core.skill_base import GuidanceSkill, ToolRegistry, get_skill_registry
                    skill = GuidanceSkill(
                        name=name, description=description or name,
                        skill_md_path=skill_md_path,
                        keywords=keywords or [],
                        priority=priority,
                    )
                    skill.load_content()
                    ToolRegistry.register(skill, keywords=keywords or [])
                    registry = get_skill_registry()
                    registry.register(skill)
            self.loaded_skills.append(name)
            logger.info("增量添加技能: %s", name)
            return True
        except Exception as e:
            logger.warning("增量添加技能失败 %s: %s", name, e)
            return False

    def remove_skill(self, name: str) -> bool:
        """增量移除一个技能"""
        try:
            from core.engine.skill_dispatcher import get_skill_dispatcher
            sd = get_skill_dispatcher()
            existed = sd.unregister_tool(name)
            from core.skill_base import ToolRegistry, get_skill_registry
            ToolRegistry.unregister(name)
            registry = get_skill_registry()
            registry.unregister(name)
            if name in self.loaded_skills:
                self.loaded_skills.remove(name)
            if existed:
                logger.info("增量移除技能: %s", name)
            return existed
        except Exception as e:
            logger.warning("增量移除技能失败 %s: %s", name, e)
            return False

    async def add_mcp_server(self, name: str, command: str, args: list,
                              env: dict = None, description: str = "") -> bool:
        """增量添加 MCP 服务器"""
        try:
            from core.mcp.awesome_mcp_manager import MCPProcess, awesome_mcp_manager
            process = MCPProcess(
                name=name, command=command,
                args=args, env=env or {},
            )
            success = await process.start()
            if success:
                awesome_mcp_manager._connected_servers[name] = process
                self.loaded_mcp_servers.append(name)
                logger.info("增量添加 MCP: %s", name)
                return True
            return False
        except Exception as e:
            logger.warning("增量添加 MCP 失败 %s: %s", name, e)
            return False

    async def remove_mcp_server(self, name: str) -> bool:
        """增量移除 MCP 服务器"""
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            result = await awesome_mcp_manager.disconnect_server(name)
            if name in self.loaded_mcp_servers:
                self.loaded_mcp_servers.remove(name)
            if result:
                logger.info("增量移除 MCP: %s", name)
            return result
        except Exception as e:
            logger.warning("增量移除 MCP 失败 %s: %s", name, e)
            return False

    async def add_api_route(self, module_path: str) -> bool:
        """增量加载一个 API 路由模块（由 main.py 的 mount_route 配合完成）"""
        try:
            __import__(module_path)
            self.loaded_api_routes.append(module_path)
            logger.info("增量加载 API 路由: %s", module_path)
            return True
        except Exception as e:
            logger.warning("增量加载 API 路由失败 %s: %s", module_path, e)
            return False

    def remove_api_route(self, module_path: str) -> bool:
        """增量卸载一个 API 路由模块"""
        if module_path in self.loaded_api_routes:
            self.loaded_api_routes.remove(module_path)
            logger.info("增量卸载 API 路由: %s", module_path)
            return True
        return False

    # ── 关闭 ────────────────────────────────────────────────────────

    async def shutdown_all(self):
        """关闭所有功能级资源"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        for name in list(awesome_mcp_manager.get_connected_servers()):
            await awesome_mcp_manager.disconnect_server(name)
        logger.info("🛑 Plugin 已关闭")


def extract_keywords_from_skill_md(md_path: str) -> List[str]:
    """从SKILL.md中提取触发关键词

    解析"## 🔑 触发关键词"部分，提取所有关键词。

    这是一个模块级工具函数，PluginLoader 和 main.py watcher 共用。
    """
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        import re
        pattern = r'##\s*🔑\s*触发关键词\s*\n(.*?)(?=\n##|\Z)'
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            return []

        keywords_section = match.group(1)
        keywords = []

        # 提取所有关键词（支持中文和英文）
        for line in keywords_section.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                if ':' in line or '：' in line:
                    kw_part = line.split(':')[-1] if ':' in line else line.split('：')[-1]
                    kws = [kw.strip() for kw in re.split(r'[、,，]', kw_part)]
                    keywords.extend([kw for kw in kws if kw])

        return keywords
    except Exception as e:
        logger.warning(f"提取SKILL.md关键词失败 {md_path}: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════
#  全局单例
# ═══════════════════════════════════════════════════════════════════════

_loader: Optional[PluginLoader] = None


def get_plugin_loader() -> PluginLoader:
    global _loader
    if _loader is None:
        _loader = PluginLoader()
    return _loader


async def load_plugins() -> Dict[str, Any]:
    """便捷方法：加载所有插件"""
    return await get_plugin_loader().load_all()

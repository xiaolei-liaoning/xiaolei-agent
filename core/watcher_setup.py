"""文件变更监听启动器 — 提取自 main.py 的 startup_event"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def setup_file_watcher(app) -> bool:
    """启动文件系统 watcher（动态自动加载）。

    监听：
    - MCP server 文件增删 → 连接/断开
    - config/mcp_servers.yml 变更 → 重载
    - config/agents.yml 变更 → 重载
    - skills/人物/SKILL.md 增删 → 注册/注销
    - api/routes/*.py 增删 → 挂载/卸载路由
    - plugin/*/plugin.json 增删 → 增量加载/卸载

    Returns:
        True if watcher started successfully
    """
    try:
        from core.watcher import FileWatcher
        from core.engine.skill_dispatcher import get_skill_dispatcher
        from core.skill_base import GuidanceSkill, ToolRegistry, get_skill_registry
        from core.plugin_loader import get_plugin_loader, extract_keywords_from_skill_md
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager
        from core.config_loader import load_mcp_servers_config, load_agents_config
        from api.route_manager import mount_route, unmount_route

        _watcher = FileWatcher(loop=asyncio.get_event_loop())

        def _match_mcp_server(file_stem: str, config_name: str) -> bool:
            if file_stem == config_name:
                return True
            if file_stem.endswith("_mcp_server"):
                base = file_stem.removesuffix("_mcp_server")
                if config_name == f"{base}-mcp" or config_name == base:
                    return True
            return False

        async def _on_mcp(name, action, filepath):
            if action == "add":
                servers = load_mcp_servers_config()
                for srv in servers:
                    if _match_mcp_server(name, srv["name"]):
                        await awesome_mcp_manager.quick_connect(srv["name"])
                        logger.info("MCP 文件添加: %s → 连接服务器: %s", filepath, srv["name"])
                        break
            elif action == "remove":
                await awesome_mcp_manager.disconnect_server(name)
                logger.info("MCP 文件删除: %s → 断开服务器: %s", filepath, name)

        async def _on_cfg_mcp():
            from core.config_loader import auto_connect_mcp_servers
            await auto_connect_mcp_servers()

        async def _on_cfg_agents():
            from core.config_loader import register_agents_from_config
            register_agents_from_config()

        async def _on_persona(persona, action, md_path):
            if action == "add":
                keywords = extract_keywords_from_skill_md(md_path) or [persona]
                skill = GuidanceSkill(
                    name=persona, description=f"人物: {persona}",
                    skill_md_path=md_path, keywords=keywords,
                )
                skill.load_content()
                get_skill_dispatcher().register_tool(name=persona, keywords=keywords)
                get_skill_registry().register(skill)
                _invalidate_skills_cache()
                logger.info("动态加载人物: %s", persona)
            elif action == "remove":
                get_skill_dispatcher().unregister_tool(persona)
                ToolRegistry.unregister(persona)
                get_skill_registry().unregister(persona)
                _invalidate_skills_cache()
                logger.info("动态卸载人物: %s", persona)

        async def _on_route(mod_name, action):
            if action == "add":
                mount_route(app, mod_name)
            elif action == "remove":
                unmount_route(app, mod_name)

        async def _on_plugin(plugin_name, action):
            pl = get_plugin_loader()
            if action == "add":
                pl.discover_sub_plugins()

        _watcher \
            .on_mcp_change(_on_mcp) \
            .on_config_mcp_change(_on_cfg_mcp) \
            .on_config_agents_change(_on_cfg_agents) \
            .on_persona_change(_on_persona) \
            .on_api_route_change(_on_route) \
            .on_plugin_change(_on_plugin)

        if _watcher.start():
            logger.info("文件变更监听已启动（动态加载 API/MCP/Skill）")
            app.state._file_watcher = _watcher
            return True
        return False
    except ImportError as e:
        logger.warning("watchdog 未安装，动态自动加载不可用: %s", e)
        return False
    except Exception as e:
        logger.warning("文件变更监听启动失败: %s", e)
        return False


def shutdown_file_watcher(app):
    """停止文件变更监听。"""
    try:
        watcher = getattr(app.state, "_file_watcher", None)
        if watcher:
            watcher.stop()
            logger.info("文件变更监听已停止")
    except Exception as e:
        logger.warning("文件变更监听停止失败: %s", e)


# Skills cache (moved from main.py)
_skills_cache = None
_skills_cache_loaded = False


def _invalidate_skills_cache():
    global _skills_cache, _skills_cache_loaded
    _skills_cache = None
    _skills_cache_loaded = False

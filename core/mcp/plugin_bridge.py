"""MCP 可插拔桥接 — PluginManager 的 mcp 注册归并到生产入口

дирekt定位 (用户定调):
  内置 = tool_registry.py 硬编, 不走 Plugin
  插件 = 用户在 ~/<root>/plugins/<name>/ 写 plugin.yaml + __init__.py register(ctx)
        ctx.register_mcp_server(...) → 归并到 config_loaded_mcp_servers()

本模块职责:
  1. merge_plugin_mcp_servers(): 把 PluginManager.get_mcp_servers() 并入
     PluginLoader sanity 检查后能读到的格式 — 与 config/mcp_servers.yml 对齐.
  2. connect_all_plugin_mcp(): 在 plugin_manager PM.activate_all() 之后、
     plugin_loader.load_plugins() 之前手动跑; 只做**插件 MCP** 连接.
"""

from __future__ import annotations

import logging
import shlex
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def merge_plugin_mcp_servers(plugin_servers: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """把 PluginManager.get_mcp_servers() 归并成 mcp_client.connect_server 的 kwargs。
    plugin_server.registration.transport stdio → command+args; http → http_url
    """
    out: Dict[str, Dict[str, Any]] = {}
    for name, reg in plugin_servers.items():
        if reg.transport == "stdio":
            # command 是单字符串, may be "npx -y @x/y" — split
            parts = shlex.split(reg.command) if isinstance(reg.command, str) else []
            if not parts:
                logger.debug(f"MCP server `{name}` transport=stdio 但 command 空, skip")
                continue
            out[name] = {
                "command": parts[0],
                "args": parts[1:],
                "env": reg.env,
                "type": "stdio",
                "health_check": reg.health_check,
            }
        else:   # http
            if not reg.url:
                logger.debug(f"MCP server `{name}` transport=http 但 url 空, skip")
                continue
            out[name] = {
                "command": "", "args": [],
                "env": reg.env,
                "http_url": reg.url,
                "type": "http",
                "health_check": reg.health_check,
            }
    return out


async def connect_all_plugin_mcp_servers(pm=None) -> Tuple[List[str], List[str]]:
    """把 PM 里 register出来的 MCP server 连上 mcp_client (真实可插拔链路)。

    Returns (connected, failed) 的服务名列表。
    """
    if pm is None:
        from core.plugin_registry import get_plugin_manager
        pm = get_plugin_manager()

    servers = merge_plugin_mcp_servers(pm.get_mcp_servers())
    if not servers:
        logger.info("Plugin MCP: 0 servers (PM 无注册), skip")
        return [], []

    connected, failed = [], []
    # 延迟 import — 绕开循环依赖 (mcp_client 在 system_init 时可能尚未 ready)
    from core.mcp.mcp_client import mcp_client

    for name, cfg in servers.items():
        try:
            ok = await mcp_client.connect_server(
                name=name,
                command=cfg["command"],
                args=cfg.get("args", []),
                env=cfg.get("env"),
                http_url=cfg.get("http_url") or None,
            )
            if ok:
                connected.append(name)
                logger.info(f"MCP 可插拔: {name} ({cfg['type']}) connected")
            else:
                failed.append(name)
        except Exception as e:
            logger.warning(f"MCP 可插拔 `{name}` 连接失败: {e}")
            failed.append(name)

    logger.info(f"MCP 可插拔合并: {len(connected)} 连接 / {len(failed)} 失败")
    return connected, failed

"""配置加载器 — 从 YAML 文件加载 MCP 服务器和 Agent 配置

将传统"代码定义"方式改为"配置驱动"：
- config/mcp_servers.yml → 定义 MCP 服务器，启动时自动连接
- config/agents.yml → 定义 Agent，启动时自动注册
"""

import asyncio
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"


def _load_yaml(filename: str) -> dict:
    """加载 YAML 配置文件"""
    path = CONFIG_DIR / filename
    if not path.exists():
        logger.warning(f"配置文件不存在: {path}")
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"加载 {filename} 失败: {e}")
        return {}


def load_mcp_servers_config() -> List[Dict[str, Any]]:
    """从 config/mcp_servers.yml 加载 MCP 服务器配置
    支持 from_awesome 引用精选库中的服务器配置
    """
    data = _load_yaml("mcp_servers.yml")
    servers = data.get("servers", {})
    result = []
    for name, cfg in servers.items():
        # 支持 from_awesome 引用精选数据库
        if "from_awesome" in cfg:
            awesome_name = cfg["from_awesome"]
            known_cfg = _lookup_known_server(awesome_name)
            if known_cfg:
                command = known_cfg.get("command", "python3")
                args = list(known_cfg.get("args", []))
                description = known_cfg.get("description", "")
                # 合并 env（用户配置覆盖精选数据库）
                base_env = dict(known_cfg.get("env", {}))
                user_env = cfg.get("env", {})
                base_env.update(user_env)
                env = base_env
            else:
                logger.warning(f"from_awesome 引用未找到: {awesome_name}，使用默认值")
                command = cfg.get("command", "python3")
                args = cfg.get("args", [])
                description = cfg.get("description", "")
                env = cfg.get("env", {})
        else:
            command = cfg.get("command", "python3")
            args = cfg.get("args", [])
            description = cfg.get("description", "")
            env = cfg.get("env", {})

        # 支持 .env 变量引用 ${VAR_NAME}
        resolved_env = {}
        for k, v in (env or {}).items():
            if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                resolved_env[k] = os.getenv(v[2:-1], "")
            else:
                resolved_env[k] = v

        result.append({
            "name": name,
            "command": command,
            "args": args,
            "description": description,
            "env": resolved_env,
            "auto_connect": cfg.get("auto_connect", True),
        })
    return result


def _lookup_known_server(name: str) -> Optional[Dict[str, Any]]:
    """从精选数据库查找已知服务器"""
    try:
        known_path = CONFIG_DIR.parent / "data" / "known_mcp_servers.json"
        if not known_path.exists():
            return None
        import json
        with open(known_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("servers", {}).get(name.lower().strip())
    except Exception:
        return None


def load_agents_config() -> List[Dict[str, Any]]:
    """从 config/agents.yml 加载 Agent 配置"""
    data = _load_yaml("agents.yml")
    agents = data.get("agents", {})
    result = []
    for name, cfg in agents.items():
        result.append({
            "name": name,
            "role_prompt": cfg.get("role_prompt", ""),
            "tools": cfg.get("tools", []),
            "priority": cfg.get("priority", 1),
        })
    # 按优先级排序
    result.sort(key=lambda a: a["priority"], reverse=True)
    return result


async def _start_single_mcp(srv: dict) -> tuple[bool, str, str]:
    """启动单个 MCP 服务器，返回 (成功?, 名称, 描述)"""
    try:
        from .mcp.awesome_mcp_manager import MCPProcess, awesome_mcp_manager

        cwd = str(CONFIG_DIR.parent)
        args = []
        for arg in srv["args"]:
            if arg.startswith("mcp/") or arg.startswith("./mcp/"):
                args.append(str(CONFIG_DIR.parent / arg))
            else:
                args.append(arg)

        process = MCPProcess(
            name=srv["name"],
            command=srv["command"],
            args=args,
            env=srv.get("env"),
        )
        success = await process.start()
        if success:
            awesome_mcp_manager._connected_servers[srv["name"]] = process
            return True, srv["name"], srv.get("description", "")
        return False, srv["name"], "启动失败"
    except Exception as e:
        return False, srv["name"], str(e)


async def auto_connect_mcp_servers(progress_callback=None):
    """从配置自动连接所有 MCP 服务器（并行启动，真正启动进程）

    Args:
        progress_callback: 可选的回调函数，接收 (name, success, desc) 用于 UI 显示进度
    """
    servers = load_mcp_servers_config()
    auto_servers = [s for s in servers if s.get("auto_connect", True)]
    if not auto_servers:
        return 0, 0

    tasks = [_start_single_mcp(srv) for srv in auto_servers]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    connected = 0
    failed = 0
    for success, name, desc in results:
        if success:
            logger.info(f"  ✅ MCP [{name}] {desc}")
            connected += 1
        else:
            logger.warning(f"  ⚠️ MCP [{name}] 启动失败: {desc}")
            failed += 1
        if progress_callback:
            progress_callback(name, success, desc)

    if connected or failed:
        logger.info(f"  MCP 服务器: {connected} 连接成功, {failed} 失败")
    return connected, failed


# Agent 配置注册表（全局）
_agent_registry: List[Dict[str, Any]] = []


def get_agent_registry() -> List[Dict[str, Any]]:
    """获取已注册的 Agent 配置列表"""
    global _agent_registry
    if not _agent_registry:
        _agent_registry = load_agents_config()
    return _agent_registry


def register_agents_from_config() -> List[Dict[str, Any]]:
    """从配置加载 Agent 到全局注册表，并注入到 multi_agent_v2 的 AgentPool"""
    global _agent_registry
    _agent_registry = load_agents_config()
    
    try:
        # 从配置创建 Agent 并注册到 AgentPool
        from core.multi_agent_v2.agents.base.base_agent import AgentFactory
        from core.multi_agent_v2.orchestration.lifecycle.agent_pool import get_agent_pool
        
        pool = get_agent_pool()
        created_agents = []
        
        for agent_config in _agent_registry:
            try:
                # 从配置创建 Agent
                agent = AgentFactory.from_config(agent_config)
                # 同步注册到 AgentPool
                pool.register_sync(agent)
                created_agents.append(agent)
                logger.info(f"  ✅ Agent [{agent_config['name']}] 已注册到 multi_agent_v2 AgentPool")
            except Exception as e:
                logger.error(f"  ❌ 创建并注册 Agent [{agent_config['name']}] 失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        return _agent_registry
        
    except Exception as e:
        logger.warning(f"multi_agent_v2 集成跳过: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    # 如果上面失败，只返回配置
    if not _agent_registry:
        logger.info("  Agent 配置为空，跳过注册")
        return []

    for agent in _agent_registry:
        logger.info(f"  ✅ Agent [{agent['name']}] 已注册 (优先级: {agent['priority']})")

    logger.info(f"  Agent 总计: {len(_agent_registry)} 个")
    return _agent_registry

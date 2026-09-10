"""PluginBridge 可插拔链路测试 — 工具 / MCP / SKILL 三通道验证

用户定调: 内置 == tool_registry 硬编 **不走 Plugin**;
         Plugin = **用户扩展** (mcp / skill_dir / new tool)
对标: hermes plugins/AGENTS.md 的 ctx 可插拔面
"""

import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import core.plugin_registry as _pr
from core.plugin_registry import PluginManager, reset_plugin_manager


def _mk(dirp, name, version, body):
    d = Path(dirp) / name; d.mkdir(parents=True, exist_ok=True)
    (d/"plugin.yaml").write_text(f"name: {name}\nversion: {version}\npip_dependencies: []", encoding="utf-8")
    (d/"__init__.py").write_text(body, encoding="utf-8")
    return d


# ════════════════════════════════════════════════════════════════
# A. MCP 可插拔链路 (插件 → PM → bridge → mcp_client.connect_server)
# ════════════════════════════════════════════════════════════════


def _mk_mcp_plugin(base, server_name="demo-mcp", command="echo demo"):
    body = f"""
def register(ctx):
    ctx.register_mcp_server(
        name="{server_name}",
        command="{command}",
        transport="stdio",
        env={{"X": "Y"}},
    )
"""
    return _mk_plugin(base, "mcp_demo_plugin", body=body.strip())


def test_plugin_mcp_merge_chain(tmp_path):
    """register_mcp_server → merge → shlex 拆 command"""
    base = tmp_path / "bundled"; base.mkdir()
    _mk_mcp_plugin(base)

    pm = PluginManager()
    _pr._BUNDLED_PLUGINS_DIR = base
    assert pm.activate("mcp_demo_plugin")   # 名字和 yaml 里一致
    assert "demo-mcp" in pm.get_mcp_servers()

    from core.mcp.plugin_bridge import merge_plugin_mcp_servers
    merged = merge_plugin_mcp_servers(pm.get_mcp_servers())
    assert merged["demo-mcp"]["command"] == "echo"
    assert merged["demo-mcp"]["args"] == ["demo"]


async def test_plugin_mcp_connect(tmp_path):
    """bridge → mcp_client.connect_server (真实调用 mcp_client 内部管道)"""
    base = tmp_path / "bundled"; base.mkdir()
    _mk_mcp_plugin(base, server_name="smoke-mcp", command="echo smoke")
    pm = PluginManager()
    _pr._BUNDLED_PLUGINS_DIR = base
    pm.activate("mcp_demo_plugin")

    from core.mcp.plugin_bridge import connect_all_plugin_mcp_servers
    from core.mcp.mcp_client import mcp_client
    mcp_client._server_configs = {}  # reset
    connected, failed = await connect_all_plugin_mcp_servers(pm)
    assert "smoke-mcp" in connected
    # mcp_client 配置真的收到
    assert "smoke-mcp" in mcp_client._server_configs
    await mcp_client.disconnect_server("smoke-mcp")


# ════════════════════════════════════════════════════════════════
# B. SKILL 可插拔 — plugin 提供 skill 目录, skill_loader 合并扫描
# ════════════════════════════════════════════════════════════════


def _mk_skill_plugin(base, skill_root: Path, name="skill_demo_plugin"):
    body = f"""
def register(ctx):
    ctx.register_skill_provider(dir_path="{skill_root}", trust="user")
"""
    return _mk_plugin(base, name, body=body)


def _mk_plugin(base, name, body=""):
    d = Path(base) / name; d.mkdir(parents=True, exist_ok=True)
    (d/"plugin.yaml").write_text(f"name: {name}\nversion: 1.0\n", encoding="utf-8")
    (d/"__init__.py").write_text(body, encoding="utf-8")
    return d


def test_skill_provider_chain(tmp_path):
    """插件 register_skill_provider(dir) → skill_loader 发现该目录 SKILL.md"""
    fake_skills = tmp_path / "user_skills"; fake_skills.mkdir()
    (fake_skills / "custom_hello").mkdir()
    (fake_skills / "custom_hello" / "SKILL.md").write_text(
        "---\nname: custom_hello\ndescription: 用户插件自带技能\n---\n# X", encoding="utf-8"
    )

    base = tmp_path / "bundled"; base.mkdir()
    _mk_plugin(base, "skill_demo", body=f"""
def register(ctx):
    ctx.register_skill_provider(dir_path="{fake_skills}", trust="user")
""")
    pm = PluginManager()
    _pr._BUNDLED_PLUGINS_DIR = base
    assert pm.activate("skill_demo")

    from core.multi_agent_v2.skills.skill_loader import discover_skills
    skills = discover_skills(force_reload=True, pm_provided=pm)
    assert "custom_hello" in skills, f"plugin skill dir 未被扫描, got {list(skills)[:5]}"


def test_default_skill_dirs_unchanged(tmp_path):
    """没有 plugin 时, 默认 SKILL_DIRS 仍然走 (向后兼容)"""
    from core.multi_agent_v2.skills.skill_loader import SKILL_DIRS
    assert "~/.opencode/skills" in SKILL_DIRS[0] or "opencode" in SKILL_DIRS[0]

"""PluginManager 可插拔架构测试 — 对标 hermes test_plugin_*.py

验证:
  A. enumerate (不 import) — plugin.yaml 清单扫描
  B. bundled-first 列表顺序 (bundled 不被 user shadow;user 覆盖同名)
  C. activate → register(ctx)ihanna 6 种
  D. 注册出的 tool 可真调用
  E. 失败降级 (有错的插件不 crash 核心)
  F. get_state observability
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.plugin_registry import (
    PluginManager,
    PluginContext,
    get_plugin_manager,
    reset_plugin_manager,
)


pytestmark = pytest.mark.asyncio


@pytest.fixture
def isolated_plugin_env(tmp_path, monkeypatch):
    """把 bundled / user plugin目录指向临时目录, 不影响生产插件."""
    import core.plugin_registry as _pr
    monkeypatch.setattr(_pr, "_BUNDLED_PLUGINS_DIR", tmp_path / "bundled")
    monkeypatch.setattr(_pr, "_USER_PLUGINS_DIR", tmp_path / "user")
    before = os.environ.get("XIAOLEI_PLUGINS_DISABLE", "")
    reset_plugin_manager()
    yield tmp_path
    reset_plugin_manager()


def _mk_plugin(base: Path, name: str, version: str = "1.0.0", body: str = None):
    """快速造一个插件目录 (yaml + __init__.py with register(ctx))"""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.yaml").write_text(
        f"""
name: {name}
version: {version}
description: "test plugin {name}"
pip_dependencies: []
hooks: [on_session_end]
""".strip(),
        encoding="utf-8",
    )
    (d / "__init__.py").write_text(body or "", encoding="utf-8")
    return d


# ════════════════════════════════════════════════════════════════
# A. 枚举 (不 import)
# ════════════════════════════════════════════════════════════════


def test_enumerate_bundled_only(isolated_plugin_env, tmp_path):
    """bundled 目录有 2 plugin.yaml → 枚举 2 个, 不需要 import code"""
    d = Path(isolated_plugin_env) / "bundled"
    _mk_plugin(d, "bbb_one", version="1.0.0")
    _mk_plugin(d, "aaa_two", version="2.0.0")

    pm = PluginManager()
    manifests = pm.discover()
    assert set(manifests.keys()) == {"bbb_one", "aaa_two"}
    # 不 import, activate 状态依然 False
    assert pm.get_state()["activated"] == []


# ════════════════════════════════════════════════════════════════
# B. user 覆盖 bundled
# ════════════════════════════════════════════════════════════════


def test_user_later_wins(isolated_plugin_env):
    """同名 user 覆盖 bundled (later-wins over bundled)"""
    d_bundled = Path(isolated_plugin_env) / "bundled"
    d_user = Path(isolated_plugin_env) / "user"
    _mk_plugin(d_bundled, "my_plugin", version="1.0.0")
    _mk_plugin(d_user, "my_plugin", version="2.0.0")

    pm = PluginManager()
    manifests = pm.discover()
    assert manifests["my_plugin"].version == "2.0.0"
    assert manifests["my_plugin"].source == "user"


# ════════════════════════════════════════════════════════════════
# C. 6 种 register
# ════════════════════════════════════════════════════════════════


def _mk_full_plugin(base: Path, name: str = "full_plugin"):
    d = _mk_plugin(base, name)
    (d / "__init__.py").write_text(
        """
def register(ctx):
    def greet(name): return {"hi": name}
    ctx.register_tool(
        name="greet", handler=greet,
        schema={"name": "greet", "description": "x", "parameters": {"type":"object","properties":{"name":{"type":"string"}}}},
        toolset="social", emoji="👋",
    )

    ctx.register_mcp_server(
        name="fake_mcp", command="echo", transport="stdio", env={"K": "V"},
    )

    ctx.register_skill_provider(dir_path="/tmp/fake_skills", trust="user")

    ctx.register_llm_provider(name="fake_llm", base_url="http://fake", env_vars=("FAKE_KEY",))

    class _Mem:
        pass
    ctx.register_memory_provider(_Mem())

    ctx.register_cli_command("testcmd", lambda a: a)
""".strip(),
        encoding="utf-8",
    )
    return d


def test_register_all_six_kinds(isolated_plugin_env):
    base = Path(isolated_plugin_env) / "bundled"
    _mk_full_plugin(base)
    pm = PluginManager()
    assert pm.activate("full_plugin")

    assert "greet" in pm.get_tools()
    assert "fake_mcp" in pm.get_mcp_servers()
    assert len(pm.get_skill_providers()) == 1
    assert "fake_llm" in pm.get_llm_profiles()
    assert len(pm.get_memory_providers()) == 1
    assert "testcmd" in pm.get_cli_commands()

    # 真调 handler
    tool = pm.get_tools()["greet"]
    assert tool.handler(name="x") == {"hi": "x"}


# ════════════════════════════════════════════════════════════════
# C2. register_mcp_server 输入验证 (stdio 需 command, http 需 url)
# ════════════════════════════════════════════════════════════════


def test_mcp_registration_validation(isolated_plugin_env):
    base = Path(isolated_plugin_env) / "bundled"
    d = _mk_plugin(base, "bad_mcp_plugin")
    (d / "__init__.py").write_text(
        """
def register(ctx):
    # 缺 command 的 stdio → 应 raise → PluginManager 记错误
    ctx.register_mcp_server(name="bad_stdio", command="", transport="stdio")
""".strip(),
        encoding="utf-8",
    )
    pm = PluginManager()
    ok = pm.activate("bad_mcp_plugin")
    assert not ok, "register_mcp_server 空 command 应报错"
    state = pm.get_state()
    assert "bad_mcp_plugin" in state["errors"], "错误应记录在 load_errors"
    # 系统不挂, 继续运行
    assert pm.get_state()["total"] > 0


# ════════════════════════════════════════════════════════════════
# D. 失败降级 — 一个插件崩不影响其他
# ════════════════════════════════════════════════════════════════


def test_bad_plugin_does_not_break_others(isolated_plugin_env):
    base = Path(isolated_plugin_env) / "bundled"
    _mk_plugin(base, "crash_plugin", body="def register(ctx): raise RuntimeError('boom')\n")
    _mk_plugin(base, "good_plugin", body="""
def register(ctx):
    ctx.register_tool(
        name="ping", handler=lambda: {"pong": 1},
        schema={"name": "ping", "description": "x", "parameters": {}},
    )
""".strip(),
    )

    pm = PluginManager()
    results = pm.activate_all()
    assert results["crash_plugin"] is False
    assert results["good_plugin"] is True
    assert "ping" in pm.get_tools()
    assert "crash_plugin" in pm.get_state()["errors"]


# ════════════════════════════════════════════════════════════════
# F. get_state / merge
# ════════════════════════════════════════════════════════════════


def test_get_state_summary(isolated_plugin_env):
    base = Path(isolated_plugin_env) / "bundled"
    _mk_plugin(base, "plugin_A")
    _mk_plugin(base, "plugin_B")
    pm = PluginManager()
    pm.activate_all()
    s = pm.get_state()
    assert s["total"] == 2
    assert s["bundled"] == 2
    assert set(s["activated"]) == {"plugin_A", "plugin_B"}


# ════════════════════════════════════════════════════════════════
# G. 全局 singleton 生命周期
# ════════════════════════════════════════════════════════════════


def test_singleton_reset_cycle():
    reset_plugin_manager()
    m1 = get_plugin_manager()
    m2 = get_plugin_manager()
    assert m1 is m2
    reset_plugin_manager()
    m3 = get_plugin_manager()
    assert m3 is not m1

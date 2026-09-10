"""PluginManager + PluginContext — 小雷版可插拔架构核心 (对标 hermes PluginManager)

设计原则 (照搬 hermes plugins/AGENTS.md):
- 插件在自己的目录内工作, 不碰 core 文件
- 一个插件一个 `register(ctx)` 函数, 通过 ctx.register_* 声明所有扩展
- 三通道 discovery: bundled (内置) → user dir (later-wins) → pip entrypoint
- 枚举不 import (读 plugin.yaml) — 激活才 import (速度)
- 同名时 user 覆盖 bundled (later-wins), 但 discovery 时 bundled 优先 appear

P0 聚焦 6 个可插拔面 (用户要求的 3 项 + 3 个基础):
  register_tool / register_mcp_server / register_skill_provider /
  register_llm_provider / register_memory_provider / register_cli_command
其余 (platform/dashboard/approval/context_engine) 留接口不实现。
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 约定路径 (三通道) ──
_BUNDLED_PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"   # 仓库内 plugins/
_USER_PLUGINS_DIR = Path.home() / ".小雷版小龙虾" / "plugins"
_ENTRYPOINT_GROUP = "xiaolei_agent.plugins"                           # pip entry point 组名


# ════════════════════════════════════════════════════════════════
# Registration dataclasses (注册对象)
# ════════════════════════════════════════════════════════════════


@dataclass
class PluginManifest:
    """从 plugin.yaml 读出的清单 (静态, 不 import code)"""
    name: str
    version: str = "0.0.0"
    description: str = ""
    source: str = "bundled"          # bundled / user / entrypoint
    location: str = ""               # 插件目录
    pip_dependencies: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    entry: str = "__init__"          # import 模块名


@dataclass
class ToolRegistration:
    """工具注册 (对标 registry.register 四件套)"""
    name: str
    handler: Callable
    schema: Dict[str, Any]
    toolset: str = "misc"
    check_fn: Optional[Callable] = None     # reachability 门控
    requires_env: Tuple[str, ...] = ()
    emoji: str = ""
    source_plugin: str = ""


@dataclass
class McpServerRegistration:
    """MCP server 定义 — 可插拔 (对标 hermes mcpServers)"""
    name: str
    command: str = ""                # stdio: 启动命令
    url: str = ""                    # http: URL
    transport: str = "stdio"         # stdio / http
    env: Dict[str, str] = field(default_factory=dict)
    health_check: bool = True
    source_plugin: str = ""


@dataclass
class SkillProviderRegistration:
    """SKILL 目录注册 — loader 自动发现"""
    dir_path: str
    trust: str = "user"              # user / builtin
    name: str = ""


@dataclass
class LLMProviderProfile:
    """LLM 配置可插拔 profile (精简 hermes ProviderProfile)"""
    name: str
    display_name: str = ""
    base_url: str = ""
    env_vars: Tuple[str, ...] = ()
    api_mode: str = "chat_completions"
    aliases: Tuple[str, ...] = ()
    description: str = ""
    supports_health_check: bool = True
    source_plugin: str = ""


# ════════════════════════════════════════════════════════════════
# PluginContext — 插件的窄面 (可调的 register_*)
# ════════════════════════════════════════════════════════════════


class PluginContext:
    """插件作者拿到的窄面 — 一个插件全部通过 ctx.register_* 声明扩展
    (对标 hermes hermes_cli/plugins.py PluginManager)"""

    def __init__(self, manager: "PluginManager", plugin_name: str):
        self._manager = manager
        self._plugin_name = plugin_name

    def _stamp(self, kwargs: dict) -> dict:
        kwargs["source_plugin"] = self._plugin_name
        return kwargs

    # ── 1. 工具 (最常用) ──
    def register_tool(
        self, name: str, handler: Callable, schema: Dict[str, Any],
        toolset: str = "misc",
        check_fn: Optional[Callable] = None,
        requires_env: Tuple[str, ...] = (),
        emoji: str = "",
    ) -> ToolRegistration:
        reg = ToolRegistration(
            name=name, handler=handler, schema=schema or {},
            toolset=toolset, check_fn=check_fn,
            requires_env=tuple(requires_env), emoji=emoji,
            **{"source_plugin": self._plugin_name},
        )
        self._manager._register_tool(reg)
        return reg

    # ── 2. MCP server ──
    def register_mcp_server(
        self, name: str, command: str = "", url: str = "",
        transport: str = "stdio",
        env: Optional[Dict[str, str]] = None,
        health_check: bool = True,
    ) -> McpServerRegistration:
        if transport not in ("stdio", "http"):
            raise ValueError(f"transport 只支持 stdio|http, 得到 {transport!r}")
        if transport == "stdio" and not command:
            raise ValueError(f"MCP stdio server `{name}` 需要 command")
        if transport == "http" and not url:
            raise ValueError(f"MCP http server `{name}` 需要 url")

        reg = McpServerRegistration(
            name=name, command=command, url=url, transport=transport,
            env=dict(env or {}), health_check=health_check,
            source_plugin=self._plugin_name,
        )
        self._manager._register_mcp_server(reg)
        return reg

    # ── 3. SKILL 目录 ──
    def register_skill_provider(self, dir_path: str, trust: str = "user") -> SkillProviderRegistration:
        if trust not in ("user", "builtin"):
            raise ValueError(f"trust 必须 user/builtin, 得到 {trust!r}")
        reg = SkillProviderRegistration(
            dir_path=os.path.expanduser(str(dir_path)),
            trust=trust,
            name=self._plugin_name,
        )
        self._manager._register_skill_provider(reg)
        return reg

    # ── 4. LLM provider profile ──
    def register_llm_provider(
        self, name: str, base_url: str = "",
        display_name: str = "", env_vars: Tuple[str, ...] = (),
        api_mode: str = "chat_completions",
        aliases: Tuple[str, ...] = (),
        description: str = "",
        supports_health_check: bool = True,
    ) -> LLMProviderProfile:
        prof = LLMProviderProfile(
            name=name, display_name=display_name, base_url=base_url,
            env_vars=tuple(env_vars), api_mode=api_mode, aliases=tuple(aliases),
            description=description,
            supports_health_check=supports_health_check,
            source_plugin=self._plugin_name,
        )
        self._manager._register_llm_provider(prof)
        return prof

    # ── 5. Memory provider (接口, 接 goal_store 后期) ──
    def register_memory_provider(self, provider: Any) -> None:
        self._manager._register_memory_provider(provider)

    # ── 6. CLI 子命令 (只有激活 provider 才接线, 对标 hermes --help 干净) ──
    def register_cli_command(self, name: str, handler: Callable) -> None:
        self._manager._register_cli_command(name, handler)

    # (留接口不实现 — 后期接平台/仪表盘审批等)
    def register_platform(self, *a, **kw) -> None:
        logger.debug(f"register_platform 未实现 (P0), 插件 {self._plugin_name} 想注册: {a[:2]}")

    def register_context_engine(self, engine: Any) -> None:
        logger.debug(f"register_context_engine 未实现, plugin={self._plugin_name}")


# ════════════════════════════════════════════════════════════════
# PluginManager — 三通道 discover / enumerate / activate
# ════════════════════════════════════════════════════════════════


class PluginManager:
    """核心可插拔管理器
    - enumerate_plugins(): 枚举 manifests, 不 import (快)
    - activate(name): import 并调 register(ctx) (慢一次)
    - get_*: 拿注册出的 tool/mcp/skill_provider/llm 供各子系统消费
    """

    def __init__(self):
        self._manifests: Dict[str, PluginManifest] = {}
        self._activated: Dict[str, bool] = {}
        self._load_errors: Dict[str, str] = {}

        # 四个消费面
        self._tools: Dict[str, ToolRegistration] = {}
        self._mcp_servers: Dict[str, McpServerRegistration] = {}
        self._skill_providers: List[SkillProviderRegistration] = []
        self._llm_profiles: Dict[str, LLMProviderProfile] = {}
        self._memory_providers: List[Any] = []
        self._cli_commands: Dict[str, Callable] = {}

    # ════════════════════════════════════════════════════════════
    # Enumerate (不 import)
    # ════════════════════════════════════════════════════════════

    def discover(self, force: bool = False) -> Dict[str, PluginManifest]:
        """三通道 enumerate — 只读 plugin.yaml 清单, 不 import 代码。
        规则: bundled-first 列表顺序, user 后来覆盖同名的 source (later-wins)"""
        if self._manifests and not force:
            return self._manifests

        self._manifests = {}

        for source_name, base_dir, source_tag in [
            ("bundled", _BUNDLED_PLUGINS_DIR, "bundled"),
            ("user", _USER_PLUGINS_DIR, "user"),
        ]:
            base_dir = Path(base_dir)  # 测试 monkeypatch 全局常量之后 (PathOr str 兼容)
            if not base_dir or not base_dir.is_dir():
                logger.debug(f"plugin dir 不存在 ({source_name}): {base_dir}")
                continue
            for child in sorted(base_dir.iterdir()):
                manifest_path = child / "plugin.yaml"
                if not manifest_path.is_file():
                    logger.debug(f"plugin `{child.name}` 缺 plugin.yaml, 跳过")
                    continue
                manifest = self._read_manifest(manifest_path, source_tag)
                if manifest:
                    # later-wins: user 同名覆盖 bundled
                    self._manifests[manifest.name] = manifest

        # pip entrypoints (P2, 先留)
        self._entrypoints()

        logger.info(
            f"PluginManager.discover: {len(self._manifests)} manifests "
            f"(bundled {sum(1 for m in self._manifests.values() if m.source == 'bundled')}, "
            f"user {sum(1 for m in self._manifests.values() if m.source == 'user')})"
        )
        return self._manifests

    def _read_manifest(self, manifest_path: Path, source: str) -> Optional[PluginManifest]:
        """解析 plugin.yaml (带 fallback: yaml 缺包走 key:value 手扫)"""
        try:
            content = manifest_path.read_text(encoding="utf-8").removeprefix("\ufeff")
        except Exception:
            return None
        try:
            import yaml
            parsed = yaml.safe_load(content)
        except ImportError:
            parsed = {}
            in_deps = False
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped == "pip_dependencies:":
                    in_deps = True
                    parsed.setdefault("pip_dependencies", [])
                    continue
                if in_deps and stripped.startswith("- "):
                    parsed["pip_dependencies"].append(stripped[2:].strip())
                    continue
                in_deps = False
                if ":" in stripped:
                    k, v = stripped.split(":", 1)
                    parsed[k.strip()] = v.strip().strip('"').strip("'")

        if not isinstance(parsed, dict) or not parsed.get("name"):
            return None
        try:
            return PluginManifest(
                name=str(parsed.get("name")),
                version=str(parsed.get("version", "0.0.0")),
                description=str(parsed.get("description", "")),
                source=source,
                location=str(manifest_path.parent),
                pip_dependencies=list(parsed.get("pip_dependencies") or []),
                hooks=list(parsed.get("hooks") or []),
                entry=str(parsed.get("entry", "__init__")),
            )
        except (TypeError, ValueError):
            return None

    def _entrypoints(self) -> List[PluginManifest]:
        """pip installed plugins — 兼容 pkg_resources / importlib.metadata"""
        out = []
        try:
            import importlib.metadata as _md
            eps = _md.entry_points(group=_ENTRYPOINT_GROUP)
            for ep in eps:
                out.append(PluginManifest(
                    name=ep.name, source="entrypoint",
                    location=f"entrypoint:{ep.value}",
                ))
        except Exception:
            pass
        return out

    # ════════════════════════════════════════════════════════════
    # Activate — 真正 import + 调 register(ctx)
    # ════════════════════════════════════════════════════════════

    def activate(self, name: str) -> bool:
        """import + 调 register(ctx)。失败记录错误但**不 raise** (降级运行)。
        ponytail: 失败时 sys.path 回滚 — 不让坏插件路径污染后续插件"""
        manifests = self.discover()
        manifest = manifests.get(name)
        if not manifest:
            logger.warning(f"PluginManager.activate: 插件 {name} 未发现")
            return False
        if self._activated.get(name):
            return True
        _sys_inserted = False
        try:
            # ponytail: 跨插件 import 冲突防御 — 插件都叫 `__init__.py`, sys.modules 同 key.
            # 解决: unique key (`xiaolei_plugin_<name>`) 直接按文件路径 load, 不走 sys.modules["__init__"].
            import importlib.util as _ilu
            mod_path = Path(manifest.location) / f"{manifest.entry}.py"
            if not mod_path.is_file():
                mod_path = Path(manifest.location) / manifest.entry / "__init__.py"
            spec = _ilu.spec_from_file_location(f"xiaolei_plugin_{name}", str(mod_path))
            mod = _ilu.module_from_spec(spec)
            sys.modules[f"xiaolei_plugin_{name}"] = mod   # 防多次 activate 重入
            if spec and spec.loader:
                spec.loader.exec_module(mod)
            register_fn = getattr(mod, "register", None)
            if not callable(register_fn):
                logger.warning(f"Plugin {name} 无 register(ctx) 函数, 视为空插件")
                self._activated[name] = True
                return True
            ctx = PluginContext(self, name)
            register_fn(ctx)
            self._activated[name] = True
            logger.info(
                f"PluginManager.activate: {name} v{manifest.version} "
                f"(source={manifest.source}, tools={len(self._tools)}, "
                f"mcp={len(self._mcp_servers)}, skills={len(self._skill_providers)})"
            )
            return True
        except Exception as e:
            logger.error(f"Plugin {name} 加载失败: {type(e).__name__}: {e}", exc_info=True)
            self._load_errors[name] = f"{type(e).__name__}: {e}"
            # sys.path 保留插入成功的也无妨（失败插件不改其他路径）
            # 但清 module cache 使同名模块重复 activate 时可重试
            sys.modules.pop(manifest.entry, None)
            return False

    def activate_all(self) -> Dict[str, bool]:
        """按顺序激活所有枚举到的插件（bundled → user）"""
        return {name: self.activate(name) for name in list(self.discover())}

    # ════════════════════════════════════════════════════════════
    # 子系统消费面 (供 tool_registry / MCP / skill_loader 读)
    # ════════════════════════════════════════════════════════════

    def _register_tool(self, reg: ToolRegistration) -> None:
        self._tools[reg.name] = reg
    def _register_mcp_server(self, reg: McpServerRegistration) -> None:
        self._mcp_servers[reg.name] = reg
    def _register_skill_provider(self, reg: SkillProviderRegistration) -> None:
        self._skill_providers.append(reg)
    def _register_llm_provider(self, prof: LLMProviderProfile) -> None:
        self._llm_profiles[prof.name] = prof
    def _register_memory_provider(self, provider: Any) -> None:
        self._memory_providers.append(provider)
    def _register_cli_command(self, name: str, handler: Callable) -> None:
        self._cli_commands[name] = handler

    # 读接口
    def get_tools(self) -> Dict[str, ToolRegistration]:
        return dict(self._tools)
    def get_mcp_servers(self) -> Dict[str, McpServerRegistration]:
        return dict(self._mcp_servers)
    def get_skill_providers(self) -> List[SkillProviderRegistration]:
        return list(self._skill_providers)
    def get_llm_profiles(self) -> Dict[str, LLMProviderProfile]:
        return dict(self._llm_profiles)
    def get_memory_providers(self) -> List[Any]:
        return list(self._memory_providers)
    def get_cli_commands(self) -> Dict[str, Callable]:
        return dict(self._cli_commands)

    def get_state(self) -> Dict[str, Any]:
        """observability — 启动 log / AGENTS.md 都读这个"""
        self.discover()
        return {
            "total": len(self._manifests),
            "bundled": sum(1 for m in self._manifests.values() if m.source == "bundled"),
            "user": sum(1 for m in self._manifests.values() if m.source == "user"),
            "activated": list(self._activated.keys()),
            "errors": dict(self._load_errors),
            "tools": len(self._tools),
            "mcp_servers": len(self._mcp_servers),
            "skill_providers": len(self._skill_providers),
            "llm_profiles": list(self._llm_profiles.keys()),
        }


# ── 全局单例 (对标 hermes get_llm_router 风格) ──
_manager: Optional[PluginManager] = None


def get_plugin_manager(force_new: bool = False) -> PluginManager:
    global _manager
    if _manager is None or force_new:
        _manager = PluginManager()
    return _manager


def reset_plugin_manager() -> None:
    """测试用 — 清 singleton"""
    global _manager
    _manager = None

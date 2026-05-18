"""文件系统变更监听器 — API/MCP/Skill 动态自动加载

设计：
1. watchdog 监听多个目录的文件变更事件
2. 事件在 watchdog 线程中触发，通过 asyncio.run_coroutine_threadsafe 调度到主循环
3. 1秒防抖避免重复事件
4. 每个事件按目录前缀分发到对应的注册/注销处理器
5. 单个处理器失败不影响其他处理器
"""

import asyncio
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable, Any

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# ── 防抖 ──────────────────────────────────────────────────────────────────
_DEBOUNCE_SECONDS = 1.0
_debounce_map: Dict[str, float] = {}
_debounce_lock = threading.Lock()


def _should_debounce(path: str) -> bool:
    """检查事件是否需要防抖（线程安全）"""
    now = time.time()
    with _debounce_lock:
        last = _debounce_map.get(path, 0.0)
        if now - last < _DEBOUNCE_SECONDS:
            return True
        _debounce_map[path] = now
        # 定期清理过期条目
        if len(_debounce_map) > 1000:
            cutoff = now - 10
            for k in list(_debounce_map.keys()):
                if _debounce_map[k] < cutoff:
                    del _debounce_map[k]
    return False


# ── 监视目录配置 ──────────────────────────────────────────────────────────

def _project_root() -> Path:
    """从当前文件推断项目根目录"""
    return Path(__file__).parent.parent


class WatchTargets:
    """需要监听的所有目录及文件模式"""

    def __init__(self, project_root: Optional[Path] = None):
        root = project_root or _project_root()

        self.root = root
        self.mcp_dir = root / "mcp"
        self.skills_persona_dir = root / "skills" / "人物"
        self.config_dir = root / "config"
        self.api_routes_dir = root / "api" / "routes"
        self.plugin_dir = root / "plugin"

        # 需要监视的所有目录
        self.directories: List[Path] = [
            d for d in [
                self.mcp_dir,
                self.skills_persona_dir,
                self.config_dir,
                self.api_routes_dir,
                self.plugin_dir,
            ] if d.exists()
        ]

    @property
    def mcp_yaml_path(self) -> Path:
        return self.config_dir / "mcp_servers.yml"

    @property
    def agents_yaml_path(self) -> Path:
        return self.config_dir / "agents.yml"


# ── 事件处理器 ────────────────────────────────────────────────────────────

class DynamicLoadHandler(FileSystemEventHandler):
    """文件系统事件 → 增量加载/卸载调度器

    Args:
        targets: WatchTargets 实例
        on_mcp_server_change: async (name, action: 'add'|'remove', filepath) → None
        on_skill_persona_change: async (persona_name, action, md_path) → None
        on_config_mcp_change: async () → None  (mcp_servers.yml 变更)
        on_config_agents_change: async () → None  (agents.yml 变更)
        on_api_route_change: async (mod_name, action) → None
        on_plugin_change: async (plugin_name, action) → None
        loop: asyncio.AbstractEventLoop 主循环（调度异步回调用）
    """

    def __init__(
        self,
        targets: WatchTargets,
        *,
        on_mcp_server_change: Optional[Callable] = None,
        on_skill_persona_change: Optional[Callable] = None,
        on_config_mcp_change: Optional[Callable] = None,
        on_config_agents_change: Optional[Callable] = None,
        on_api_route_change: Optional[Callable] = None,
        on_plugin_change: Optional[Callable] = None,
        loop: asyncio.AbstractEventLoop,
    ):
        super().__init__()
        self.targets = targets
        self._loop = loop

        # 回调注册
        self._on_mcp = on_mcp_server_change
        self._on_persona = on_skill_persona_change
        self._on_cfg_mcp = on_config_mcp_change
        self._on_cfg_agents = on_config_agents_change
        self._on_route = on_api_route_change
        self._on_plugin = on_plugin_change

        # 已知状态快照（用于 YAML diff）
        self._known_mcp_yaml = self._read_file(targets.mcp_yaml_path)
        self._known_agents_yaml = self._read_file(targets.agents_yaml_path)

        # 已知文件列表快照（用于检测删除）
        self._known_mcp_files: Set[str] = set()
        self._known_persona_files: Set[str] = set()
        self._known_route_files: Set[str] = set()
        self._known_plugin_dirs: Set[str] = set()
        self._scan_known_files()

    # ── 快照管理 ──────────────────────────────────────────────────────

    @staticmethod
    def _read_file(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8") if path.exists() else ""
        except Exception:
            return ""

    def _scan_known_files(self):
        """扫描当前文件系统状态作为基准"""
        if self.targets.mcp_dir.exists():
            self._known_mcp_files = {
                p.stem
                for p in self.targets.mcp_dir.iterdir() if p.is_file()
            }
        if self.targets.skills_persona_dir.exists():
            self._known_persona_files = {
                d.name for d in self.targets.skills_persona_dir.iterdir() if d.is_dir()
            }
        if self.targets.api_routes_dir.exists():
            self._known_route_files = {
                p.stem for p in self.targets.api_routes_dir.iterdir()
                if p.is_file() and p.suffix == ".py" and not p.name.startswith("_")
            }
        if self.targets.plugin_dir.exists():
            self._known_plugin_dirs = {
                d.name for d in self.targets.plugin_dir.iterdir()
                if d.is_dir() and not d.name.startswith("_")
            }

    # ── 事件分发 ──────────────────────────────────────────────────────

    def _async_call(self, coro):
        """安全地在主循环中调度协程"""
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except RuntimeError as e:
            logger.warning("调度异步任务失败（loop 可能已关闭）: %s", e)

    def on_created(self, event: FileSystemEvent):
        self._handle(event, "created")

    def on_deleted(self, event: FileSystemEvent):
        self._handle(event, "deleted")

    def on_modified(self, event: FileSystemEvent):
        self._handle(event, "modified")

    def _handle(self, event: FileSystemEvent, action: str):
        """事件分发入口"""
        if event.is_directory:
            return
        path = Path(event.src_path)
        # 删除事件不防抖（避免 modified 事件先到导致 deleted 被误杀）
        if action != "deleted" and _should_debounce(str(path)):
            return

        try:
            self._dispatch(path, action)
        except Exception as e:
            logger.warning("Watcher 事件处理异常 %s: %s", path, e)

    def _dispatch(self, path: Path, action: str):
        """按路径前缀分发到具体处理器"""
        root = self.targets.root

        try:
            rel = path.relative_to(root)
        except ValueError:
            return

        rel_str = str(rel.as_posix())

        # ── config/*.yml ──
        if rel_str == "config/mcp_servers.yml" and action in ("modified", "created"):
            new_content = self._read_file(path)
            if new_content != self._known_mcp_yaml:
                self._known_mcp_yaml = new_content
                if self._on_cfg_mcp:
                    self._async_call(self._on_cfg_mcp())

        elif rel_str == "config/agents.yml" and action in ("modified", "created"):
            new_content = self._read_file(path)
            if new_content != self._known_agents_yaml:
                self._known_agents_yaml = new_content
                if self._on_cfg_agents:
                    self._async_call(self._on_cfg_agents())

        # ── mcp/*_mcp_server.py ──
        elif rel_str.startswith("mcp/") and path.suffix == ".py":
            name = path.stem
            if action == "created":
                if self._on_mcp:
                    self._async_call(self._on_mcp(name, "add", str(path)))
            elif action == "deleted":
                if name in self._known_mcp_files and self._on_mcp:
                    self._async_call(self._on_mcp(name, "remove", str(path)))
            # 更新快照
            if action == "created":
                self._known_mcp_files.add(name)
            elif action == "deleted":
                self._known_mcp_files.discard(name)

        # ── skills/人物/<name>/ ──
        elif rel_str.startswith("skills/人物/"):
            parts = rel.parts
            if len(parts) >= 3:
                persona = parts[2]
                if path.name == "SKILL.md":
                    if action == "created":
                        if self._on_persona:
                            self._async_call(
                                self._on_persona(persona, "add", str(path))
                            )
                    elif action == "deleted":
                        if persona in self._known_persona_files and self._on_persona:
                            self._async_call(
                                self._on_persona(persona, "remove", str(path))
                            )
                    # 更新快照
                    if action == "created":
                        self._known_persona_files.add(persona)
                    elif action == "deleted":
                        self._known_persona_files.discard(persona)

        # ── api/routes/*.py ──
        elif rel_str.startswith("api/routes/"):
            if path.suffix == ".py" and not path.name.startswith("_"):
                mod_name = path.stem
                if action == "created":
                    if self._on_route:
                        self._async_call(self._on_route(mod_name, "add"))
                elif action == "deleted":
                    if mod_name in self._known_route_files and self._on_route:
                        self._async_call(self._on_route(mod_name, "remove"))
                # 更新快照
                if action == "created":
                    self._known_route_files.add(mod_name)
                elif action == "deleted":
                    self._known_route_files.discard(mod_name)

        # ── plugin/<name>/plugin.json ──
        elif rel_str.startswith("plugin/") and path.name == "plugin.json":
            plugin_name = rel.parts[1] if len(rel.parts) > 1 else ""
            if plugin_name:
                if action == "created":
                    if self._on_plugin:
                        self._async_call(self._on_plugin(plugin_name, "add"))
                elif action == "deleted":
                    if plugin_name in self._known_plugin_dirs and self._on_plugin:
                        self._async_call(self._on_plugin(plugin_name, "remove"))
                if action == "created":
                    self._known_plugin_dirs.add(plugin_name)
                elif action == "deleted":
                    self._known_plugin_dirs.discard(plugin_name)


# ── 管理器 ─────────────────────────────────────────────────────────────────

class FileWatcher:
    """文件变更监听管理器 — 提供 start/stop 接口供 main.py 调用

    用法:
        watcher = FileWatcher(loop=asyncio.get_event_loop())
        watcher.on_mcp_change(my_handler)
        watcher.start()
        ...
        watcher.stop()
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        self._loop = loop or asyncio.get_event_loop()
        self._observer: Optional[Observer] = None
        self._handler: Optional[DynamicLoadHandler] = None
        self._targets = WatchTargets()

        # 回调（供外部注册）
        self._on_mcp: Optional[Callable] = None
        self._on_persona: Optional[Callable] = None
        self._on_cfg_mcp: Optional[Callable] = None
        self._on_cfg_agents: Optional[Callable] = None
        self._on_route: Optional[Callable] = None
        self._on_plugin: Optional[Callable] = None

    # ── 回调注册（链式调用友好） ──────────────────────────────────────

    def on_mcp_change(self, cb: Callable):
        """async (name, action, filepath) → None"""
        self._on_mcp = cb
        return self

    def on_persona_change(self, cb: Callable):
        """async (persona_name, action, md_path) → None"""
        self._on_persona = cb
        return self

    def on_config_mcp_change(self, cb: Callable):
        """async () → None  mcp_servers.yml 变更"""
        self._on_cfg_mcp = cb
        return self

    def on_config_agents_change(self, cb: Callable):
        """async () → None  agents.yml 变更"""
        self._on_cfg_agents = cb
        return self

    def on_api_route_change(self, cb: Callable):
        """async (mod_name, action) → None"""
        self._on_route = cb
        return self

    def on_plugin_change(self, cb: Callable):
        """async (plugin_name, action) → None"""
        self._on_plugin = cb
        return self

    # ── 启动/停止 ─────────────────────────────────────────────────────

    def start(self) -> bool:
        """启动文件监听（向所有目标目录注册 watchdog observer）"""
        if self._observer:
            logger.info("Watcher 已在运行，跳过重复启动")
            return True

        if not self._targets.directories:
            logger.warning("没有可监视的目录，跳过 watcher 启动")
            return False

        # 创建事件处理器
        self._handler = DynamicLoadHandler(
            self._targets,
            on_mcp_server_change=self._on_mcp,
            on_skill_persona_change=self._on_persona,
            on_config_mcp_change=self._on_cfg_mcp,
            on_config_agents_change=self._on_cfg_agents,
            on_api_route_change=self._on_route,
            on_plugin_change=self._on_plugin,
            loop=self._loop,
        )

        # 启动 observer
        self._observer = Observer()
        for directory in self._targets.directories:
            self._observer.schedule(self._handler, str(directory), recursive=True)
            logger.info("Watcher 已注册: %s", directory)

        self._observer.start()
        logger.info(
            "文件变更监听已启动: %d 个目录", len(self._targets.directories)
        )
        return True

    def stop(self):
        """停止文件监听"""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
            logger.info("文件变更监听已停止")

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    @property
    def watched_directories(self) -> List[str]:
        return [str(d) for d in self._targets.directories]
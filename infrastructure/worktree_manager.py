"""
WorktreeManager — git worktree 隔离管理器

为多 Agent 提供工作目录隔离能力：
  - 每个 Agent 获得独立的 git worktree（detached HEAD）
  - Agent 可自由读写文件，互不干扰
  - 自动清理，即使 Agent 抛异常
  - 线程安全（asyncio.Lock）
  - 上下文管理器支持

用法:
    async with WorktreeManager() as wm:
        path = await wm.allocate("agent_001")
        # 在 path 中执行 agent 任务...
        await wm.release("agent_001")
    # 退出上下文时自动清理所有未释放的 worktree
"""

import asyncio
import logging
import os
import shutil
import subprocess
import uuid
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── 默认 Worktree 存放路径 ──────────────────────────────────────────

_DEFAULT_BASE_DIR = ".claude/worktrees/agent"
_CMD_TIMEOUT = 60  # git 命令超时（秒）


class WorktreeManager:
    """git worktree 隔离管理器

    每个 Agent 获得独立的工作目录（detached git worktree），
    任务完成后或异常时自动清理。

    Thread-safe: 所有写操作通过 asyncio.Lock 序列化。
    """

    def __init__(self, base_dir: Optional[str] = None, repo_path: Optional[str] = None):
        """
        Args:
            base_dir: worktree 存放的根目录（相对或绝对）。
                      默认为项目根目录下的 .claude/worktrees/agent。
            repo_path: git 仓库路径。默认为当前工作目录所属 git 仓库的根。
        """
        self._base_dir: str = base_dir or ""
        self._repo_path: str = repo_path or ""  # 懒初始化
        self._lock = asyncio.Lock()
        self._worktrees: Dict[str, str] = {}     # agent_id -> worktree_path
        self._initialized: bool = False

    # ── 公共 API ─────────────────────────────────────────────────────

    async def allocate(self, agent_id: str) -> str:
        """为指定 agent 分配一个隔离工作目录。

        如果该 agent 已有 worktree，直接返回已有路径（幂等）。

        Returns:
            worktree 的绝对路径
        """
        await self._ensure_repo_path()
        async with self._lock:
            if agent_id in self._worktrees:
                return self._worktrees[agent_id]
            return await self._allocate_inner(agent_id)

    async def release(self, agent_id: str) -> None:
        """释放指定 agent 的 worktree（删除目录和 git worktree 记录）。"""
        async with self._lock:
            await self._release_inner(agent_id)

    async def cleanup_all(self) -> None:
        """释放所有由本管理器创建的 worktree。"""
        async with self._lock:
            for agent_id in list(self._worktrees.keys()):
                await self._release_inner(agent_id)

    @property
    def active_count(self) -> int:
        return len(self._worktrees)

    @property
    def active_agents(self) -> Dict[str, str]:
        """返回 {agent_id: worktree_path} 的快照"""
        return dict(self._worktrees)

    # ── 内部实现 ─────────────────────────────────────────────────────

    async def _ensure_repo_path(self) -> None:
        if self._initialized:
            return
        if not self._repo_path:
            self._repo_path = self._get_repo_root()
        if not self._base_dir:
            self._base_dir = os.path.join(self._repo_path, _DEFAULT_BASE_DIR)
        self._initialized = True

    async def _allocate_inner(self, agent_id: str) -> str:
        """内部分配逻辑（已持有锁）"""
        branch_name = f"agent-{uuid.uuid4().hex[:16]}"
        tag = uuid.uuid4().hex[:12]
        worktree_path = os.path.join(self._base_dir, f"agent-{tag}")

        os.makedirs(self._base_dir, exist_ok=True)

        # 检查是否有未提交变更，如有则 stash
        stashed = self._maybe_stash()

        try:
            self._run_git([
                "worktree", "add", "--detach", worktree_path, "HEAD",
            ])
            self._worktrees[agent_id] = worktree_path
            logger.info(
                "Worktree allocated for %s: %s (branch: %s)",
                agent_id, worktree_path, branch_name,
            )
            return worktree_path
        except Exception:
            # worktree 创建失败，清理残留
            if os.path.exists(worktree_path):
                shutil.rmtree(worktree_path, ignore_errors=True)
            raise
        finally:
            if stashed:
                self._pop_stash()

    async def _release_inner(self, agent_id: str) -> None:
        """内部释放逻辑（已持有锁）"""
        path = self._worktrees.pop(agent_id, None)
        if path is None:
            return
        if not os.path.isdir(path):
            logger.warning("Worktree path gone for %s: %s", agent_id, path)
            return

        # 优先用 git worktree remove（清理 git 记录）
        try:
            self._run_git(["worktree", "remove", "--force", path])
            logger.info("Worktree released for %s: %s", agent_id, path)
        except Exception as exc:
            logger.warning(
                "git worktree remove failed for %s: %s — falling back to rm -rf",
                agent_id, exc,
            )
            shutil.rmtree(path, ignore_errors=True)

    # ── git 辅助 ─────────────────────────────────────────────────────

    def _get_repo_root(self) -> str:
        """获取 git 仓库根目录。"""
        return self._run_git(["rev-parse", "--show-toplevel"]).strip()

    def _has_uncommitted_changes(self) -> bool:
        """返回 True 如果工作区有未提交变更。"""
        out = self._run_git(["status", "--porcelain"])
        return bool(out.strip())

    def _maybe_stash(self) -> bool:
        """如果有未提交变更则 stash，返回是否 stash 了。"""
        if not self._has_uncommitted_changes():
            return False
        self._run_git(["stash", "push", "--include-untracked",
                        "--message", "worktree-isolation-auto-stash"])
        return True

    def _pop_stash(self) -> None:
        """pop 最近一次 stash（忽略冲突 — 用户变更优先）。"""
        try:
            self._run_git(["stash", "pop"])
        except Exception as exc:
            # stash pop 冲突不致命：用户的工作区变更优先
            logger.warning(
                "stash pop 冲突（这是合理的 — 用户变更优先）: %s", exc,
            )
            # 尝试 drop 以避免污染 stash 列表
            try:
                self._run_git(["stash", "drop"])
            except Exception:
                pass

    def _run_git(self, args: list) -> str:
        """执行 git 子命令，返回 stdout。异常时抛 RuntimeError。"""
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self._repo_path or None,
                capture_output=True,
                text=True,
                timeout=_CMD_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"git command timed out after {_CMD_TIMEOUT}s: {' '.join(cmd)}"
            )
        except FileNotFoundError:
            raise RuntimeError("git not found on PATH — cannot create worktrees")
        except Exception as exc:
            raise RuntimeError(f"git subprocess error: {exc}") from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout

    # ── 上下文管理器 ─────────────────────────────────────────────────

    async def __aenter__(self) -> "WorktreeManager":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup_all()

    # ── __del__ 兜底 ─────────────────────────────────────────────────

    def __del__(self) -> None:
        """兜底清理：如果 context manager 未正确退出，尝试删除遗留 worktree。"""
        if not self._worktrees:
            return
        # 同步清理（__del__ 中不能跑 async）
        for agent_id in list(self._worktrees.keys()):
            path = self._worktrees.pop(agent_id, None)
            if path and os.path.isdir(path):
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", path],
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    shutil.rmtree(path, ignore_errors=True)


# ── 便利函数 ────────────────────────────────────────────────────────

async def with_worktree(agent_id: str, fn, *args, **kwargs):
    """在 worktree 中执行异步函数 fn 的便利包装。

    用法:
        result = await with_worktree("agent_001", some_async_func, arg1, arg2)
    """
    async with WorktreeManager() as wm:
        path = await wm.allocate(agent_id)
        old_cwd = os.getcwd()
        try:
            os.chdir(path)
            return await fn(*args, **kwargs)
        finally:
            os.chdir(old_cwd)
            await wm.release(agent_id)

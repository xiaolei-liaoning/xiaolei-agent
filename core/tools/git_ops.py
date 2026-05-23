"""Git 工作流工具 — diff/status/commit/PR

基于 ShellExecutor 执行 git 命令，提供人类可读的输出格式化。
支持标准 git 操作和 GitHub PR 创建（通过 gh CLI）。
"""

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GitResult:
    """Git 操作结果"""
    success: bool = True
    output: str = ""
    error: str = ""
    command: str = ""


class GitTool:
    """Git 工作流工具

    使用方式：
        git = GitTool("/path/to/repo")
        status = await git.status()
        diff = await git.diff()
        result = await git.commit("feat: add new feature")
    """

    def __init__(self, repo_path: str = "."):
        self.repo_path = os.path.abspath(os.path.expanduser(repo_path))
        self._git_root: Optional[str] = None

    async def _git(self, args: List[str]) -> GitResult:
        """执行 git 命令（使用 subprocess 直连，避免 shlex 分割）

        Args:
            args: git 参数列表，如 ['status', '--porcelain']

        Returns:
            GitResult 执行结果
        """
        cmd = ["git"] + args
        command_str = " ".join(str(a) for a in cmd)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            out_text = stdout.decode("utf-8", errors="replace")
            err_text = stderr.decode("utf-8", errors="replace")
            if proc.returncode != 0:
                return GitResult(
                    success=False,
                    output=out_text,
                    error=err_text or f"退出码 {proc.returncode}",
                    command=command_str,
                )
            return GitResult(
                success=True,
                output=out_text,
                error=err_text,
                command=command_str,
            )
        except asyncio.TimeoutError:
            return GitResult(success=False, error="git 命令超时", command=command_str)
        except Exception as e:
            return GitResult(success=False, error=str(e), command=command_str)

    def _check_repo(self) -> Optional[str]:
        """检查是否在 git 仓库中，返回仓库根目录"""
        if self._git_root:
            return self._git_root
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                self._git_root = result.stdout.strip()
                return self._git_root
        except Exception:
            pass
        return None

    @property
    def current_branch(self) -> str:
        """获取当前分支名"""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"

    async def status(self) -> str:
        """显示 git status

        Returns:
            格式化后的状态信息
        """
        repo = self._check_repo()
        if not repo:
            return "❌ 当前目录不是 Git 仓库"

        branch = self.current_branch

        # 获取详细状态
        status_result = await self._git(["status"])
        if not status_result.success:
            return f"❌ git status 失败: {status_result.error}"

        # 获取简短状态用于统计
        short_result = await self._git(["status", "--porcelain"])
        lines = [l for l in short_result.output.splitlines() if l.strip()] if short_result.success else []

        staged = [l for l in lines if l[0] != " " and l[0] != "?"]
        unstaged = [l for l in lines if l[1] != " "]
        untracked = [l for l in lines if l.startswith("??")]

        output = [
            f"📂 仓库: {repo}",
            f"🌿 分支: {branch}",
            f"───" if status_result.output else "",
            status_result.output.strip(),
        ]

        if not lines:
            output.append("\n工作区干净，没有未提交的更改。")

        return "\n".join(output)

    async def diff(self, files: Optional[List[str]] = None, cached: bool = False) -> str:
        """显示 git diff

        Args:
            files: 指定文件列表
            cached: 是否显示暂存区差异

        Returns:
            格式化的 diff 输出
        """
        repo = self._check_repo()
        if not repo:
            return "❌ 当前目录不是 Git 仓库"

        args = ["diff", "--no-color"]
        if cached:
            args.append("--cached")
        if files:
            args.extend(["--"] + files)

        result = await self._git(args)
        if not result.success:
            return f"❌ git diff 失败: {result.error}"

        output = result.output
        if not output.strip():
            diff_type = "暂存区" if cached else "工作区"
            return f"📄 {diff_type}没有差异"

        # 统计变更行数
        added = len([l for l in output.splitlines() if l.startswith("+") and not l.startswith("+++")])
        removed = len([l for l in output.splitlines() if l.startswith("-") and not l.startswith("---")])

        return f"📄 差异 ({added} 行添加, {removed} 行删除):\n\n{output[:5000]}"

    async def log(self, count: int = 10, branch: Optional[str] = None) -> str:
        """显示 git log

        Args:
            count: 显示条数
            branch: 分支名

        Returns:
            格式化的提交历史
        """
        repo = self._check_repo()
        if not repo:
            return "❌ 当前目录不是 Git 仓库"

        args = [
            "log",
            f"--max-count={count}",
            "--format=%h %s%nAuthor: %an <%ae>%nDate: %ad%n",
            "--date=short",
        ]
        if branch:
            args.append(branch)

        result = await self._git(args)
        if not result.success:
            return f"❌ git log 失败: {result.error}"

        if not result.output.strip():
            return "没有提交历史"

        return f"📜 最近 {count} 条提交:\n\n" + result.output[:3000]

    async def branch(self, remote: bool = False) -> str:
        """列出分支

        Args:
            remote: 是否显示远程分支

        Returns:
            分支列表
        """
        repo = self._check_repo()
        if not repo:
            return "❌ 当前目录不是 Git 仓库"

        args = ["branch"]
        if remote:
            args.append("-a")

        result = await self._git(args)
        if not result.success:
            return f"❌ git branch 失败: {result.error}"

        return f"🌿 分支:\n{result.output.strip()[:2000]}"

    async def add(self, files: List[str]) -> str:
        """暂存文件

        Args:
            files: 要暂存的文件列表

        Returns:
            操作结果
        """
        repo = self._check_repo()
        if not repo:
            return "❌ 当前目录不是 Git 仓库"

        if not files:
            return "⚠️ 请指定要暂存的文件的列表"

        args = ["add", "--"] + files
        result = await self._git(args)
        if not result.success:
            return f"❌ git add 失败: {result.error}"

        return f"✅ 已暂存 {len(files)} 个文件: {', '.join(files[:10])}" + \
               (f" ...还有 {len(files) - 10} 个" if len(files) > 10 else "")

    async def commit(self, message: str, add_all: bool = False) -> str:
        """提交更改

        Args:
            message: 提交信息
            add_all: 是否自动暂存所有更改

        Returns:
            操作结果
        """
        repo = self._check_repo()
        if not repo:
            return "❌ 当前目录不是 Git 仓库"

        if not message:
            return "⚠️ 请提供提交信息"

        if add_all:
            add_result = await self._git(["add", "-A"])
            if not add_result.success:
                return f"❌ git add -A 失败: {add_result.error}"

        args = ["commit", "-m", message]
        result = await self._git(args)
        if not result.success:
            return f"❌ git commit 失败: {result.error}"

        return f"✅ 提交成功:\n{result.output.strip()}"

    async def push(self, remote: str = "origin", branch: Optional[str] = None) -> str:
        """推送更改到远程仓库

        Args:
            remote: 远程仓库名
            branch: 分支名

        Returns:
            操作结果
        """
        repo = self._check_repo()
        if not repo:
            return "❌ 当前目录不是 Git 仓库"

        branch = branch or self.current_branch
        if branch == "unknown":
            return "❌ 无法确定当前分支"

        args = ["push", remote, branch]
        result = await self._git(args)
        if not result.success:
            return f"❌ git push 失败: {result.error}"

        return f"✅ 已推送到 {remote}/{branch}:\n{result.output.strip()[:1000]}"

    async def create_pr(self, title: str, body: str = "", base: str = "main") -> str:
        """使用 gh CLI 创建 Pull Request

        Args:
            title: PR 标题
            body: PR 描述
            base: 目标分支

        Returns:
            PR 链接或错误信息
        """
        if not shutil.which("gh"):
            return "❌ gh CLI 未安装。请执行: brew install gh"

        repo = self._check_repo()
        if not repo:
            return "❌ 当前目录不是 Git 仓库"

        branch = self.current_branch
        if branch == "main" or branch == "master":
            return "⚠️ 当前在主分支上，请先切换到功能分支"

        try:
            cmd = [
                "gh", "pr", "create",
                "--title", title,
                "--base", base,
                "--head", branch,
            ]
            if body:
                cmd.extend(["--body", body])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                return f"❌ PR 创建失败: {stderr.decode('utf-8', errors='replace')[:500]}"

            return f"✅ PR 已创建:\n{stdout.decode('utf-8', errors='replace').strip()}"
        except asyncio.TimeoutError:
            return "❌ PR 创建超时（30秒）"
        except Exception as e:
            return f"❌ PR 创建异常: {e}"


# 便捷函数
async def git_status(repo_path: str = ".") -> str:
    """便捷 git status"""
    git = GitTool(repo_path)
    return await git.status()


async def git_diff(repo_path: str = ".", files: Optional[List[str]] = None, cached: bool = False) -> str:
    """便捷 git diff"""
    git = GitTool(repo_path)
    return await git.diff(files=files, cached=cached)


async def git_commit(repo_path: str = ".", message: str = "", add_all: bool = True) -> str:
    """便捷 git commit"""
    git = GitTool(repo_path)
    return await git.commit(message=message, add_all=add_all)


async def create_github_pr(title: str, body: str = "", base: str = "main", repo_path: str = ".") -> str:
    """便捷创建 GitHub PR"""
    git = GitTool(repo_path)
    return await git.create_pr(title=title, body=body, base=base)

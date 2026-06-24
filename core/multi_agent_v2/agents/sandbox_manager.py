"""
SandboxManager — 沙盒写入流程管理器

在 ReAct 循环中，将 write_file 自动重定向到沙盒目录，
通过验证后再同步到桌面，避免用户看到不完整的半成品。

数据流：
  write_file(path="~/Desktop/game.py")
    → SandboxManager.redirect_path() → /tmp/agent_sandbox/react_{task}/game.py
    → 写入沙盒文件
    → FileQualityMiddleware 检查 + 沙盒验证
    → 循环结束后 sync_to_desktop() 复制到桌面
"""

import ast
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SandboxManager:
    """沙盒写入流程管理器

    自动将 write_file 的目标路径从桌面重定向到沙盒目录。
    文件通过验证后再同步到桌面。
    """

    def __init__(self, task_id: str):
        safe_id = "".join(c for c in task_id if c.isalnum() or c in ('_', '-'))[:40]
        self.sandbox_dir = Path(tempfile.gettempdir()) / f"agent_sandbox/react_{safe_id}"
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.mapping: Dict[str, str] = {}  # sandbox_path → real_path
        logger.info(f"沙盒目录: {self.sandbox_dir}")

    def redirect_path(self, original_path: str) -> str:
        """将桌面路径映射到沙盒目录"""
        expanded = os.path.expanduser(original_path)
        desktop = os.path.expanduser("~/Desktop")
        if not expanded.startswith(desktop):
            return original_path  # 非桌面路径不重定向
        rel = os.path.relpath(expanded, desktop)
        sandbox_path = str(self.sandbox_dir / rel)
        os.makedirs(os.path.dirname(sandbox_path), exist_ok=True)
        self.mapping[sandbox_path] = expanded
        logger.info(f"路径重定向: {expanded} → {sandbox_path}")
        return sandbox_path

    def sync_to_desktop(self) -> List[str]:
        """将沙盒内所有文件同步到桌面"""
        synced = []
        for sandbox_path, real_path in self.mapping.items():
            if not os.path.exists(sandbox_path):
                logger.warning(f"沙盒文件不存在，跳过: {sandbox_path}")
                continue
            try:
                os.makedirs(os.path.dirname(real_path), exist_ok=True)
                shutil.copy2(sandbox_path, real_path)
                synced.append(real_path)
            except Exception as e:
                logger.error(f"同步失败: {sandbox_path} → {real_path}: {e}")

        if synced:
            _total = len(synced)
            _chars = sum(os.path.getsize(f) for f in synced)
            print(f"  \033[1;32m✅ 沙盒同步完成: {_total}个文件, {_chars}字符已复制到桌面\033[0m")

        return synced

    async def validate_python(self, file_path: str, content: str = "") -> Optional[str]:
        """对 Python 文件做 ast.parse + 沙盒运行时验证 + 代码质量关卡

        1. ast.parse 语法检查
        2. 游戏类文件检查 __main__ 入口
        3. 代码质量关卡（行数、类/函数数量、关键元素）
        4. 通过 SandboxExecutor 执行代码检测运行时错误
        """
        if not file_path.endswith('.py'):
            return None
        if not content and os.path.exists(file_path):
            try:
                content = open(file_path, encoding='utf-8').read()
            except Exception as e:
                return f"无法读取文件: {e}"
        if not content:
            return None

        _lines = [l for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
        _line_count = len(_lines)
        _basename = os.path.basename(file_path).lower()
        _app_keywords = ['game', 'snake', 'puzzle', '八数码', '贪吃蛇', '2048', 'app', 'main']
        _is_app = any(kw in _basename for kw in _app_keywords)
        if not _is_app:
            try:
                from core.engine.llm_backend import get_llm_router
                _router = get_llm_router()
                if _router and _router.is_available():
                    _resp = await _router.simple_chat(
                        f"以下文件名是否看起来像游戏或应用主文件？只回答'是'或'否'\n\n{_basename}",
                        temperature=0, max_tokens=10
                    )
                    _is_app = _resp and '是' in str(_resp)
            except Exception:
                pass

        # 1. ast.parse 语法检查
        try:
            ast.parse(content)
        except SyntaxError as e:
            return f"语法错误: {e.msg} (行{e.lineno})"

        # 1.5 代码质量关卡（对游戏/应用类文件）
        if _is_app:
            _class_count = content.count("class ")
            _func_count = content.count("def ")
            _has_main = "if __name__" in content
            _loop_keywords = ['while ', 'for ', 'pygame.display', 'screen.blit', 'update(', 'draw(', 'clock.tick']
            _has_loop = any(kw in content for kw in _loop_keywords)
            if not _has_loop:
                try:
                    from core.engine.llm_backend import get_llm_router
                    _router = get_llm_router()
                    if _router and _router.is_available():
                        _resp = await _router.simple_chat(
                            f"以下代码是否包含游戏主循环？只回答'是'或'否'\n\n{content[:1500]}",
                            temperature=0, max_tokens=10
                        )
                        _has_loop = _resp and '是' in str(_resp)
                except Exception:
                    pass

            _quality_errors = []

            # 行数检查：< 50 行的游戏/应用几乎不完整
            if _line_count < 50:
                _quality_errors.append(
                    f"行数过少（{_line_count} 行），游戏/应用代码不应少于 50 行"
                )

            # 类定义检查
            if _class_count == 0 and _func_count < 3:
                _quality_errors.append(
                    f"缺少类定义且函数过少（class={_class_count}, def={_func_count}），"
                    "游戏代码应至少包含类定义或 3+ 个函数"
                )

            # 主循环检查
            if not _has_loop:
                _quality_errors.append(
                    "缺少游戏主循环（while/for/update/draw），代码可能为空壳"
                )

            if _quality_errors:
                _err_msg = "代码质量检查不通过:\n" + "\n".join(
                    f"  - {e}" for e in _quality_errors
                )
                logger.warning(f"质量关卡: {file_path} → {_err_msg}")
                return _err_msg

        # 2. 检查 main 入口（游戏/应用类）
        if _is_app:
            _func_count = content.count("def ")
            _has_main = "if __name__" in content
            if _func_count >= 2 and not _has_main:
                return "缺少 `if __name__ == '__main__':` 主入口"

        # 3. 沙盒运行时验证（对游戏/应用类文件执行代码检测错误）
        if _is_app:
            try:
                from core.tools.sandbox_executor import SandboxExecutor, ResourceLimits

                _ex = SandboxExecutor()
                _limits = ResourceLimits(timeout=5, max_output_size_kb=500)
                _result = await _ex.execute_python(content, limits=_limits)
                if _result and _result.exit_code != 0:
                    _err = _result.stderr or ""
                    return f"运行时错误: {_err[:200]}"
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"沙盒运行时验证异常: {e}")

        return None

    def cleanup(self) -> None:
        """清理沙盒目录"""
        try:
            if self.sandbox_dir.exists():
                shutil.rmtree(str(self.sandbox_dir))
        except Exception as e:
            logger.warning(f"沙盒清理失败: {e}")

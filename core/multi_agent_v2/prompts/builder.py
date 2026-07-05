"""PromptBuilder — 组合式 .txt prompt 加载和依赖解析"""
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CircularDependencyError(Exception):
    pass


class PromptNotFoundError(FileNotFoundError):
    pass


class PromptBuilder:
    def __init__(self, root_dir: str = "prompts"):
        self._root = Path(root_dir)
        self._cache: Dict[str, str] = {}

    def _resolve_path(self, path: str) -> Path:
        return (self._root / path).with_suffix(".txt")

    def load(self, path: str, _stack: Optional[list] = None) -> str:
        if path in self._cache:
            return self._cache[path]

        if _stack is None:
            _stack = []
        if path in _stack:
            raise CircularDependencyError(
                f"循环依赖: {' → '.join(_stack)} → {path}"
            )

        file_path = self._resolve_path(path)
        if not file_path.exists():
            raise PromptNotFoundError(
                f"Prompt 文件不存在: {file_path}"
            )

        raw = file_path.read_text(encoding="utf-8")

        lines = raw.split("\n")
        requires = []
        body_start = 0

        for i, line in enumerate(lines[:3]):
            stripped = line.strip()
            if stripped.startswith("@requires:"):
                deps = stripped[len("@requires:"):].strip()
                requires.extend(d.strip() for d in deps.split(",") if d.strip())
                body_start = i + 1
            elif stripped:
                break
        body = "\n".join(lines[body_start:])

        _stack.append(path)
        resolved_deps = {}
        for dep in requires:
            resolved_deps[dep] = self.load(dep, _stack)
        _stack.pop()

        for dep_path, dep_content in resolved_deps.items():
            marker = f"{{{{{dep_path}}}}}"
            if marker in body:
                body = body.replace(marker, dep_content)
            else:
                body += f"\n\n{dep_content}"

        self._cache[path] = body
        return body

    def assemble_system(self, modules: list[str]) -> str:
        return "\n\n".join(self.load(f"system/{m}") for m in modules)

    def get_tool_desc(self, name: str) -> str:
        return self.load(f"tools/{name}")

    def get_agent_prompt(self, agent_type: str) -> str:
        role = self.load(f"agents/{agent_type}")
        rules = self.load("agents/work_rules")
        return f"{role}\n\n{rules}"

    def get_block(self, block_name: str, **vars) -> str:
        return self.load(f"blocks/{block_name}").format(**vars)

    def clear_cache(self):
        self._cache.clear()


_builder: Optional[PromptBuilder] = None


def get_builder(root_dir: str = None) -> PromptBuilder:
    global _builder
    if _builder is None:
        if root_dir is None:
            root_dir = str(Path(__file__).parent.parent.parent.parent / "prompts")
        _builder = PromptBuilder(root_dir)
    return _builder

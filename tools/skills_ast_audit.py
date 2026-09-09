#!/usr/bin/env python3
"""AST 深度审计 — 借鉴 hermes-agent tools/skills_ast_audit.py。

扫描技能 Python 文件中的动态 import / 动态属性访问，输出格式化报告。
这是诊断提示（供人工审查），不是安全门禁（任何模式都可能有合法用途）。

用法：
    python tools/skills_ast_audit.py <path> [path2 ...]
    # 或扫描整个 core/ 目录：
    python tools/skills_ast_audit.py core/
"""

from __future__ import annotations

import ast
import sys
from contextlib import suppress
from pathlib import Path
from typing import List, Tuple

# (file, line, pattern_id, description)
Finding = Tuple[str, int, str, str]

_IGNORED_DIRS = {"__pycache__", ".venv", "venv", "node_modules", ".git"}
# builtin name -> (参数下标, pattern_id, description)
_DYNAMIC_CALLS = {
    "__import__": (0, "dynamic_import_computed", "__import__ with non-literal module name"),
    "getattr": (1, "dynamic_getattr", "getattr with non-literal attribute name"),
}


def _is_importlib(name: str) -> bool:
    return name == "importlib" or name.startswith("importlib.")


def _scan_source(content: str, rel_path: str) -> List[Finding]:
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, RecursionError):
        return []
    findings: List[Finding] = []

    def hit(node, pid, desc):
        findings.append((rel_path, node.lineno, pid, desc))

    class V(ast.NodeVisitor):
        def visit_Call(self, node):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "import_module":
                # importlib.import_module() — 运行时加载任意模块
                hit(node, "dynamic_import", "importlib.import_module() — loads arbitrary modules at runtime")
            elif isinstance(f, ast.Name) and f.id in _DYNAMIC_CALLS:
                arg_index, pid, desc = _DYNAMIC_CALLS[f.id]
                if len(node.args) > arg_index and not isinstance(node.args[arg_index], ast.Constant):
                    hit(node, pid, desc)
            self.generic_visit(node)

        def visit_Subscript(self, node):
            if (isinstance(node.value, ast.Attribute) and node.value.attr == "__dict__"
                    and not isinstance(node.slice, ast.Constant)):
                hit(node, "dict_access", "__dict__[<computed>] — dynamic attribute access")
            self.generic_visit(node)

        def visit_Import(self, node):
            for a in node.names:
                if _is_importlib(a.name):
                    hit(node, "importlib_import", f"import {a.name} — enables dynamic module loading")
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            if _is_importlib(node.module or ""):
                hit(node, "importlib_import", f"from {node.module} import ... — enables dynamic module loading")
            self.generic_visit(node)

    with suppress(RecursionError, ValueError, RuntimeError):  # hostile input: keep what we have
        V().visit(tree)
    return findings


def _scan_file(py: Path, rel: str) -> List[Finding]:
    try:
        return _scan_source(py.read_text(encoding="utf-8", errors="replace"), rel)
    except OSError:
        return []


def ast_scan_path(path: Path) -> List[Finding]:
    """Scan one .py file or every .py under a directory; [] for non-Python/missing."""
    if path.is_file():
        return _scan_file(path, path.name) if path.suffix.lower() == ".py" else []
    if not path.is_dir():
        return []
    return [
        f for py in sorted(path.rglob("*.py"))
        if not set(py.parent.parts) & _IGNORED_DIRS
        for f in _scan_file(py, py.relative_to(path).as_posix())
    ]


def format_ast_report(findings: List[Finding], module_name: str = "") -> str:
    """纯文本报告（按文件分组）。"""
    header = f"AST deep scan: {module_name}" if module_name else "AST deep scan"
    if not findings:
        return f"{header}\n  No dynamic import/access patterns detected."
    lines, current = [header, f"  {len(findings)} finding(s):"], None
    for f, line, pid, desc in sorted(findings):
        if f != current:
            current = f
            lines.append(f"  {f}")
        lines.append(f"    L{line}  {pid}  — {desc}")
    return "\n".join(lines + ["", "  Note: diagnostic hints for human review, not security verdicts."])


def main(argv: List[str]) -> int:
    targets = argv[1:] or ["core/"]
    all_findings: List[Finding] = []
    for t in targets:
        p = Path(t)
        if not p.exists():
            print(f"SKIP: {t} does not exist", file=sys.stderr)
            continue
        all_findings.extend(ast_scan_path(p))
    print(format_ast_report(all_findings, "xiaolei-agent 副本"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

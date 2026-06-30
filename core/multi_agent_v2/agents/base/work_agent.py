"""
WorkAgent - 统一智能体（精简版）

单一 Agent 类型，统一走 _execute_fast 快路径（ReAct 直通）。

核心保留：
  - personality/role → system_prompt_for_role() → 注入 LLM
  - temp_memory 临时记忆
  - _execute_fast() → run_react() → 4层 MiddlewareChain
  - 任务完成即消失（finally 清理）

已删除：
  - adapt_to_task() / capabilities 系统（不参与实际执行决策）
  - _execute_full 路径（已删除）
  - light_mode 参数
  - SharedBus 总线监听（JS Workflow 独立模式，agent 间不通信）
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .models import ActionResult, AgentType, Task

logger = logging.getLogger(__name__)


class WorkAgent(BaseAgent):
    """统一工作 Agent — 根据任务动态调整行为和能力"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "通用工作 Agent，根据任务动态调整",
        personality: str = "",
        role: str = "",
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.WORKER,
            name=name,
            description=description,
            personality=personality,
            role=role,
        )

        # 模型覆盖（orchestrator 动态设置）
        self._model_override: str = ""

        # 工作记录
        self.work_history: List[Dict[str, Any]] = []

        # Agent标签，用于输出前缀
        self._agent_label: str = name or "Agent"

        # 已注入文件路径缓存（项目分析用，拦截重复 read_file）
        self._cached_file_paths: set = set()

        logger.info(f"WorkAgent 初始化完成: {self.agent_id}")

    def reset(self) -> None:
        """重置 Agent 状态，为下次复用做准备"""
        self.work_history = []
        self._model_override = ""
        self._cached_file_paths = set()
        try:
            from core.multi_agent_v2.tools.cache import clear_project_file_cache
            clear_project_file_cache()
        except Exception:
            pass
        self.reset_temp_memory()
        self.personality = ""
        self.role = ""
        logger.debug(f"WorkAgent {self.agent_id} 状态已重置")

    # ── 执行入口 ───────────────────────────────────────────────────────

    async def execute(self, task: Task) -> ActionResult:
        """执行任务 - 统一执行入口"""
        return await self._execute_fast(task)

    async def _execute_fast(self, task: Task) -> ActionResult:
        """轻量执行 — 直通 ReAct 快路径"""
        logger.info(f"WorkAgent [轻量] 执行任务: {task.task_id} ({task.type})")
        start = time.time()
        desc = task.description

        print(f"\n    \033[1;36m⚡ 开始任务: {desc[:80]}\033[0m")

        try:
            # ── 项目分析任务：Phase 1 扫描 → Phase 2 批量读 → 透传 ReAct ──
            if await self._is_project_analysis(desc):
                phase_data = await self._phase1_and_2(desc, start)
                if phase_data:
                    desc = f"{desc.rstrip()}\n\n===== 项目结构概览（Phase 1 扫描）=====\n{phase_data}"
                    task.description = desc
                    print(f"    \033[1;32m📦 Phase 1 结构数据已注入 ({len(phase_data)} 字符)\033[0m")

            # ── SharedBus 工作记忆：搜索其他 Agent 已有成果 ──
            try:
                from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
                _bus = get_shared_bus()
                _found = False
                for _w in re.findall(r'[一-鿟\w]{2,}', desc)[:5]:
                    _results = await _bus.search_knowledge(_w)
                    if _results:
                        _summaries = []
                        for _k, _v in _results.items():
                            _s = _v.get("meta", {}).get("summary", "")
                            if _s and len(_s) > 10:
                                _summaries.append(f"  └─ {_s[:200]}")
                        if _summaries:
                            desc = f"{desc}\n\n📋 其他 Agent 已有成果:\n" + "\n".join(_summaries)
                            task.description = desc
                            _found = True
                            print(f"    \033[1;35m📋 工作记忆: {len(_summaries)} 条已有成果已注入\033[0m")
                            break
                if not _found:
                    print(f"    \033[2;35m📋 工作记忆: 无已有成果\033[0m")
            except Exception:
                pass

            # ── 统一走 ReActCore 中间件链 ──
            _mr = task.context.get("max_rounds", 0)
            max_rounds = max(_mr, 10) if _mr else 10
            logger.info(f"WorkAgent → ReActCore (max_rounds={max_rounds})")
            from core.multi_agent_v2.agents.react_core import run_react

            # ── 三层 Skill 匹配 ──
            try:
                from core.skills.base_skills import get_skill_system
                skill_result = await get_skill_system().match(desc)
                if skill_result.personality:
                    overlay = f"【Skill角色】\n{skill_result.personality[:500]}"
                    self.personality = f"{self.personality}\n\n---\n{overlay}" if self.personality else skill_result.personality[:2000]
                    self._skill_tools = list(skill_result.tool_preference)
                    print(f"    \033[1;36m🧠 Skill: {skill_result.skill_name}\033[0m")
                    role_chars = len(skill_result.personality)
                    print(f"    \033[2m📄 角色定义: {role_chars} 字符\033[0m")
                # ponytail: project_analysis 跳过 Expert 角色（238 个 persona 与代码分析不相关）
                if skill_result.expert_personality and skill_result.skill_id not in ("project_analyzer", "project_analysis"):
                    ep = skill_result.expert_personality
                    # 跳过 YAML frontmatter（---...---），从内容正文开始
                    if ep.startswith('---'):
                        idx = ep.find('---', 3)
                        if idx > 0:
                            ep = ep[idx + 3:].strip()
                    self.personality += f"\n\n---\n【Expert】\n{ep[:12000]}"
                    print(f"    \033[1;36m👤 Expert: {skill_result.expert_name}\033[0m")
                    if len(ep) > 100:
                        print(f"    \033[2m📄 角色定义已加载 ({len(ep[:12000])} 字)\033[0m")
                if skill_result.guidance:
                    self._skill_guidance = skill_result.guidance
                    print(f"    \033[2m📖 Skill 指导: {len(skill_result.guidance)} 字符\033[0m")

                # ── skill_agent_map.yaml Expert 覆盖 ──
                try:
                    import yaml, os
                    _map_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "config", "skill_agent_map.yaml")
                    if os.path.isfile(_map_path):
                        with open(_map_path) as _f:
                            _map_data = yaml.safe_load(_f)
                        _agent_map = _map_data.get("skill_agent_map", {})
                        if skill_result.skill_id in _agent_map:
                            _override_id = _agent_map[skill_result.skill_id]
                            _base = get_skill_system().base_skills.get(_override_id)
                            if _base and _base.role_prompt:
                                self.personality = _base.role_prompt
                                print(f"    \033[1;36m🧠 Skill: {_override_id} (skill_agent_map 覆盖)\033[0m")
                                print(f"    \033[2m📄 角色定义: {len(_base.role_prompt)} 字符, tools: {len(_base.tools)}\033[0m")
                except Exception as _e:
                    logger.debug(f"skill_agent_map 覆盖失败: {_e}")
            except Exception as e:
                logger.warning(f"Skill 匹配异常: {e}")

            # 如果有 Guidance，注入到 personality_prompt
            guidance_text = getattr(self, "_skill_guidance", "")
            pp = self.system_prompt_for_role()
            if guidance_text:
                pp += "\n\n<guidance>\n" + guidance_text[:2000] + "\n</guidance>"

            result = await run_react(
                desc,
                max_rounds=max_rounds,
                model=task.context.get("model", ""),
                personality_prompt=pp,
                agent=self,
                allowed_tools=task.context.get("allowed_tools"),
                disallowed_tools=task.context.get("disallowed_tools"),
                tool_preference=set(getattr(self, "_skill_tools", [])),
            )

            elapsed = time.time() - start
            success = result.get("success", False)
            output = result.get("answer", "")
            error = result.get("error", "")

            ar = ActionResult(
                success=success,
                output=str(output) if output else None,
                error=error,
                execution_time=elapsed,
                metadata={
                    "light_mode": True,
                    "iterations": result.get("iterations", 0),
                },
            )

            self.work_history.append(
                {
                    "task_id": task.task_id,
                    "task_type": task.type,
                    "success": success,
                    "execution_time": elapsed,
                    "timestamp": time.time(),
                }
            )
            if len(self.work_history) > 100:
                self.work_history = self.work_history[-100:]

            logger.info(f"WorkAgent [轻量] 完成: success={success} {elapsed:.1f}s")

            # ── SharedBus 工作记忆：写入分析成果 ──
            _answer = str(output)[:300] if output else ""
            if _answer and len(_answer) > 20 and success:
                try:
                    from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus
                    _bus = get_shared_bus()
                    _tags = set(re.findall(r'[一-鿟\w]{2,}', desc)[:5])
                    await _bus.store_knowledge(
                        key=f"analysis:{self.agent_id}",
                        data={"result": output, "task": desc[:200]},
                        tags=_tags,
                        source=self.agent_id,
                        summary=_answer[:200],
                    )
                except Exception:
                    pass

            return ar

        except Exception as e:
            logger.error(f"WorkAgent [轻量] 异常: {e}")
            return ActionResult(
                success=False, error=str(e), execution_time=time.time() - start
            )

    async def _is_project_analysis(self, desc: str) -> bool:
        """判断是否为项目分析任务"""
        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        if not router or not router.is_available():
            return False
        prompt = (
            "判断以下用户请求是否属于「分析某个项目的代码/结构/架构」。"
            "只回答'是'或'否'。\n请求：" + desc[:200]
        )
        resp = await router.simple_chat(prompt, temperature=0, max_tokens=10)
        return resp and '是' in str(resp).strip()

    async def _phase1_and_2(self, desc: str, start: float) -> str:
        """全新项目分析：程序化扫描 + CodeGraph 调用链 + 读头部，LLM 仅做 HTML 包装"""
        import os, re, json, subprocess
        from pathlib import Path

        print(f"    \033[1;36m📂 项目分析：CodeGraph 扫描 + 文件头部读取\033[0m")

        # 1. 提取路径（支持中文/全角字符，V2-C8 fix）
        path = None
        for pat in [r'(~[^\s，,]+/[\w\u4e00-\u9fff./-]+)', r'(/[\w\u4e00-\u9fff./-]+)', r'(\.\.[\w\u4e00-\u9fff./-]+)']:
            m = re.search(pat, desc)
            if m:
                c = os.path.expanduser(m.group(1))
                if os.path.isdir(c):
                    path = c
                    break
        if not path:
            return ""

        # 2. 初始化 CodeGraph 索引
        cg_ok = False
        try:
            _r = subprocess.run(["codegraph", "init", "."], cwd=path,
                              capture_output=True, text=True, timeout=120)
            cg_ok = _r.returncode == 0 or "already initialized" in (_r.stdout + _r.stderr).lower()
        except Exception:
            pass

        # 3. 用 os.walk 遍历所有文件（排除无关目录）
        EXCLUDE = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next",
                   "dist", "build", ".cache", ".codegraph", ".history", ".mypy_cache",
                   ".pytest_cache", ".deer-flow", "target", "bazel-*"}
        BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
                      ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz", ".rar", ".dmg",
                      ".exe", ".dll", ".so", ".dylib", ".pyc", ".mp4", ".mp3", ".wav",
                      ".DS_Store"}
        BLACKLIST_FILES = {".DS_Store", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                           ".gitignore", ".prettierrc", ".editorconfig", "tsconfig.tsbuildinfo"}

        # 收集所有文件，按顶层目录分组
        top_dirs = {}  # dirname → [relpath, ...]
        root_files = []  # 根目录文件
        for root, dirs, files in os.walk(path):
            # 排除目录
            dirs[:] = [d for d in dirs if d not in EXCLUDE and not d.startswith(".")]
            for f in files:
                if f.startswith(".") or f in BLACKLIST_FILES:
                    continue
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, path)
                ext = os.path.splitext(f)[1].lower()
                if ext in BINARY_EXT:
                    continue
                if "/" in rel:
                    top = rel.split("/")[0]
                    top_dirs.setdefault(top, []).append(rel)
                else:
                    root_files.append(rel)

        print(f"    \033[2m📂 发现 {len(top_dirs)} 个顶层目录, {len(root_files)} 个根文件\033[0m")

        # 4. 读每个文件的头部 30 行（用于分析功能）
        def read_file_head(rel_path: str, lines: int = 30) -> str:
            fp = os.path.join(path, rel_path)
            if not os.path.isfile(fp):
                return ""
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    return "".join(f.readline() for _ in range(lines)).strip()
            except (OSError, PermissionError):
                return ""

        def count_lines(rel_path: str) -> int:
            fp = os.path.join(path, rel_path)
            if not os.path.isfile(fp):
                return 0
            try:
                with open(fp, "rb") as f:
                    return sum(1 for _ in f)
            except (OSError, PermissionError):
                return 0

        # 5. 逐个目录分析
        analysis_sections = []
        # 先读根目录的 README 和关键配置
        doc_candidates = ["README.md", "README", "Readme.md", "CLAUDE.md", "AGENTS.md"]
        config_candidates = ["pyproject.toml", "package.json", "Cargo.toml", "go.mod",
                             "Makefile", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                             ".env.example", "config.yaml", "config.json", "app_config.json"]

        # 先处理根目录的 key 文件
        root_readmes = [r for r in root_files if r.lower() in [d.lower() for d in doc_candidates]]
        root_configs = [r for r in root_files if r.lower() in [c.lower() for c in config_candidates]]
        root_targets = root_readmes + root_configs + [r for r in root_files
                                                       if r not in root_readmes + root_configs][:5]

        if root_targets:
            analysis_sections.append("===== 项目根目录 =====")
            for rf in root_targets:
                head = read_file_head(rf)
                lc = count_lines(rf)
                if head:
                    # 提取第一行作为简短描述
                    first_line = head.split("\n")[0][:100] if head else ""
                    analysis_sections.append(f"📄 {rf}  ({lc}行)")
                    analysis_sections.append(f"   首行: {first_line}")
                    analysis_sections.append(f"   内容概要: {head[:300]}")
                    analysis_sections.append("")

        # 按目录分组
        # 先生成目录顺序：先关键目录（doc/config），再其他
        ordered_dirs = sorted(top_dirs.keys())
        # 把 backend, api, core, src, app 等核心目录放前面
        core_rank = {"backend": 0, "api": 0, "core": 0, "src": 0, "app": 0,
                     "server": 0, "cli": 0, "engine": 0, "agent": 0}
        ordered_dirs.sort(key=lambda d: (core_rank.get(d, 5), d))

        # CodeGraph 调用链缓存
        cg_callers_cache = {}

        for dname in ordered_dirs:
            files_in_dir = sorted(top_dirs[dname])
            # 优先选入口/核心文件（main, app, index, 最大的py/ts文件）
            priority_files = []
            other_files = []
            for f_rel in files_in_dir:
                fbase = os.path.basename(f_rel).lower()
                if fbase in ("main.py", "app.py", "__init__.py", "__main__.py",
                             "index.ts", "index.tsx", "index.js", "index.jsx",
                             "server.py", "cli.py", "entrypoint.py"):
                    priority_files.insert(0, f_rel)
                elif fbase.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                    other_files.append(f_rel)

            # 每个目录读最多 5 个文件（2 个优先级 + 3 个其他源码）
            to_read = priority_files[:3] + other_files[:4]
            to_read = to_read[:6]  # 最多读 6 个

            analysis_sections.append(f"\n===== 📁 {dname}/ =====")
            # 找目录下可能的 README
            dir_readme = [f for f in files_in_dir
                          if os.path.basename(f).lower() in ("readme.md", "readme")]
            if dir_readme:
                rh = read_file_head(dir_readme[0], 20)
                if rh:
                    analysis_sections.append(f"  📖 README: {rh[:200]}")

            for f_rel in to_read:
                head = read_file_head(f_rel)
                lc = count_lines(f_rel)
                if not head:
                    continue

                # 提取 imports
                import_lines = []
                class_lines = []
                func_lines = []
                for line in head.split("\n"):
                    s = line.strip()
                    if s.startswith("import ") or s.startswith("from "):
                        import_lines.append(s)
                    if s.startswith("class ") and ":" in s:
                        class_lines.append(s[:120])
                    if s.startswith("def ") and ":" in s:
                        func_lines.append(s[:120])
                    if s.startswith("async def ") and ":" in s:
                        func_lines.append(s[:120])
                    # TS/JS
                    if s.startswith("export ") and ("function" in s or "class" in s or "const" in s or "interface" in s or "type " in s):
                        class_lines.append(s[:120])

                # 生成文件分析
                analysis_sections.append(f"📄 {f_rel}  ({lc}行)")
                if import_lines[:5]:
                    analysis_sections.append(f"   导入: {', '.join(import_lines[:5])}")
                if class_lines[:3]:
                    analysis_sections.append(f"   定义: {', '.join(class_lines[:3])}")
                if func_lines[:3]:
                    analysis_sections.append(f"   函数: {', '.join(func_lines[:3])}")

                # CodeGraph 调用链查询（对核心文件）
                if cg_ok and (f_rel.endswith(".py") or f_rel.endswith(".ts") or f_rel.endswith(".tsx")):
                    # 取类名或函数名作为查询目标
                    symbol_to_query = ""
                    for cl in class_lines:
                        m = re.match(r'class\s+(\w+)', cl)
                        if m:
                            symbol_to_query = m.group(1)
                            break
                    if not symbol_to_query:
                        for fl in func_lines:
                            m = re.match(r'(?:async\s+)?def\s+(\w+)', fl)
                            if m:
                                symbol_to_query = m.group(1)
                                break
                    if symbol_to_query and symbol_to_query not in cg_callers_cache:
                        try:
                            _cr = subprocess.run(
                                ["codegraph", "callees", symbol_to_query],
                                cwd=path, capture_output=True, text=True, timeout=10
                            )
                            if _cr.returncode == 0 and _cr.stdout.strip():
                                cg_out = _cr.stdout.strip()
                                cg_callers_cache[symbol_to_query] = cg_out
                                # 取前 5 行
                                cg_lines = cg_out.split("\n")[:5]
                                analysis_sections.append(f"   调用链: {', '.join(l.strip() for l in cg_lines if l.strip())}")
                        except Exception:
                            pass

            # 统计该目录下未读的文件
            remaining = len(files_in_dir) - len(to_read)
            if remaining > 0:
                analysis_sections.append(f"   ... 另有 {remaining} 个文件未读取")

        analysis_text = "\n".join(analysis_sections)

        # 6. 组装最终数据
        elapsed = time.time() - start
        print(f"    \033[1;32m📂 分析完成 ({elapsed:.1f}s): {len(analysis_text)} 字符分析数据\033[0m")
        print(f"    \033[2m📋 覆盖 {len(top_dirs)} 个目录, {len(analysis_sections)} 条分析记录\033[0m")

        return (
            f"【项目分析数据已就绪 — LLM 仅做 HTML 包装】\n\n"
            f"下方是一个项目经过程序化扫描后的完整分析数据。\n"
            f"⚠️ IMPORTANT: 你只有 3 轮输出机会。不要调用 read_file 或任何其他工具——"
            f"所有数据已在此。你的唯一任务：将这些数据格式化输出为美观的 HTML，"
            f"用 write_file 写入桌面文件。\n\n"
            f"规则：\n"
            f"- 第 1 轮：直接生成 HTML 代码（<!DOCTYPE html> 完整文档）\n"
            f"- 第 2 轮：用 write_file 写入 ~/Desktop/xxx-analysis.html\n"
            f"- 第 3 轮：输出完成消息\n"
            f"- 不需要读任何文件，分析数据已经在上面\n\n"
            f"格式要求：\n"
            f"- 完整 <!DOCTYPE html>，内嵌 CSS 样式\n"
            f"- 每层目录用 📁 标题，每个文件用 📄 子项\n"
            f"- 包含：项目路径、文件数、目录数、技术栈\n"
            f"- 包含：每个目录的职责概括 + 每个文件的功能说明\n"
            f"- 包含：调用链关系（如果有）\n"
            f"- 样式美观，背景白色/浅灰，字体优雅，适合阅读\n\n"
            f"路径：{path}\n"
            f"分析耗时：{elapsed:.1f}s\n\n"
            f"{analysis_text}"
        )

    def get_work_stats(self) -> Dict[str, Any]:
        """获取工作统计"""
        if not self.work_history:
            return {"total_tasks": 0}
        total = len(self.work_history)
        successful = sum(1 for r in self.work_history if r.get("success"))
        by_type: Dict[str, int] = {}
        for r in self.work_history:
            t = r.get("task_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total_tasks": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_type": by_type,
        }

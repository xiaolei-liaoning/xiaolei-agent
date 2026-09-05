"""Chat / Run / Analyze / Scrape / Automate / WeChat / Orchestrate / Smart / Workflows handlers."""

import asyncio
import json
import logging
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.colors import (
    CliColors,
    print_chat_bubble,
    print_color,
    print_error,
    print_success,
    print_warning,
)
from cli.command_parser import CommandType, ParsedCommand
from cli.logging_system import log_error, log_info, log_success, log_warning
from cli.thinking_engine import (
    think_analyze,
    think_complete,
    think_log,
    think_plan,
    think_start,
    think_step,
    think_summarize,
)


class ChatHandler:
    """Handles chat, run, analyze, scrape, automate, wechat, orchestrate, smart, workflow commands."""

    def __init__(self, cli):
        self.cli = cli
        self._prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """从 workflows/.workflow_prompt_template.md 读取 workflow prompt 模板"""
        template_path = (
            Path(__file__).parent.parent.parent
            / "workflows" / ".workflow_prompt_template.md"
        )
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return self._builtin_template()

    def _builtin_template(self) -> str:
        """内置后备模板（文件被删时保证可用）"""
        return (
            "生成 JS Workflow 脚本，必须包含 export const meta + export default async function。\n\n"
            "【可用 API】\n"
            "  - agent(prompt, {label, isFinal}) — 启动一个子 Agent 执行子任务\n"
            "  - parallel([thunks]) — 并行启动多个 agent，等待全部完成\n"
            "  - $dag({key: spec}) — 声明式 DAG 编排\n"
            "  - phase(title) — 标记阶段性进度分组\n"
            "  - log(msg) — 输出进度消息\n\n"
            "任务：{{task}}\n\n"
            "开始写 workflow："
        )

    # ──────────────────────────────────────────────
    # /run
    # ──────────────────────────────────────────────

    async def handle_run(self, parsed_cmd: ParsedCommand):
        """处理执行工作流命令"""
        request = parsed_cmd.action if parsed_cmd.action else parsed_cmd.remaining
        if not request:
            print_error("请提供任务描述")
            return

        from cli.base import WorkflowEngineWrapper

        wrapper = WorkflowEngineWrapper()
        start = time.time()
        result = await wrapper.create_and_execute(request)
        elapsed = time.time() - start

        success = result.get("success", False)
        self.cli._display_workflow_result(result)
        log_info(f"执行完成: success={success}, 耗时={elapsed:.1f}s")

    # ──────────────────────────────────────────────
    # /orchestrate
    # ──────────────────────────────────────────────

    # ──────────────────────────────────────────────
    # /task /explore /analyze /build — 子代理快捷命令
    # ──────────────────────────────────────────────

    async def handle_task_subagent(self, parsed_cmd: ParsedCommand):
        """用 task 子代理执行（通用）"""
        request = parsed_cmd.action or parsed_cmd.remaining or ""
        if not request:
            print_error("请提供任务描述")
            return
        await self._run_with_subagent(request, "general")

    async def handle_explore_subagent(self, parsed_cmd: ParsedCommand):
        """用 explore 子代理探索"""
        request = parsed_cmd.action or parsed_cmd.remaining or ""
        if not request:
            print_error("请提供任务描述")
            return
        await self._run_with_subagent(request, "explore")

    async def handle_analyze_subagent(self, parsed_cmd: ParsedCommand):
        """用 analyze 子代理深度分析"""
        request = parsed_cmd.action or parsed_cmd.remaining or ""
        if not request:
            print_error("请提供任务描述")
            return
        await self._run_with_subagent(request, "analyze")

    async def handle_build_subagent(self, parsed_cmd: ParsedCommand):
        """用 build 子代理开发构建"""
        request = parsed_cmd.action or parsed_cmd.remaining or ""
        if not request:
            print_error("请提供任务描述")
            return
        await self._run_with_subagent(request, "build")

    async def _run_with_subagent(self, request: str, agent_type: str):
        """强制使用子代理执行任务"""
        from cli.base import WorkflowEngineWrapper

        # 直接调子代理
        try:
            from core.multi_agent_v2.agents.subagent.spawn import task
            result = await task(description=request, agent=agent_type)
        except Exception as e:
            # fallback: 通过 WorkAgent
            log_warning(f"子代理执行失败，降级到 WorkAgent: {e}")
            wrapper = WorkflowEngineWrapper()
            result = await wrapper.create_and_execute(
                f"[使用子代理 {agent_type} 模式] {request}"
            )

        success = result.get("success", False)
        output = result.get("output", result.get("answer", ""))
        if success and output:
            print_success(f"✅ {output[:500]}")
        else:
            error = result.get("error", "无输出")
            print_error(f"❌ {error}")
        log_info(f"子代理执行完成: agent={agent_type}, success={success}")

    async def handle_orchestrate(self, parsed_cmd: ParsedCommand):
        """多Agent编排 — 真正的多Agent并发协作"""
        action = parsed_cmd.action or ""
        remaining = parsed_cmd.remaining or ""
        task = remaining or action or ""
        if not task:
            print_error("请提供任务描述")
            return
        await self._run_ad_hoc(task)

    async def _llm_decompose_task(self, task: str) -> list:
        """用 LLM 动态将任务分解为子任务"""
        try:
            from core.engine.llm_backend import get_llm_router

            router = get_llm_router()
            if not router or not router.is_available():
                return []

            prompt = (
                "将以下任务拆解为3个独立的子任务，每个子任务聚焦一个不同的维度。\n"
                "输出格式：每行一个子任务标题，不要序号，不要引号。\n\n"
                f"任务：{task[:200]}\n\n"
                "如果是分析类任务，示例：网站架构分析 | 用户体验评估 | 性能优化建议\n"
                "如果是创建/构建类任务（写代码、做游戏、生成文件），示例：界面和样式创建 | 游戏逻辑实现 | 交互和输出文件\n"
                "开始："
            )
            resp = await asyncio.wait_for(
                router.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=300,
                ),
                timeout=15.0,
            )
            text = str(resp).strip() if resp else ""
            if not text or "[LLM_MOCK]" in text:
                return []

            lines = [line.strip() for line in text.split("\n") if line.strip()]
            lines = [line for line in lines if line and not line.startswith("示例")]
            lines = [re.sub(r"^\d+[\.\)、]\s*", "", line) for line in lines]
            return lines[:3]
        except Exception:
            return []

    async def _run_ad_hoc(self, task: str):
        """ad-hoc 模式：JS Workflow 编排"""
        from cli.animated_spinner import print_section
        from cli.colors import CLAUDE, log_status, print_error as pe

        print_section("Multi-Agent Orchestration")

        script = ""

        if task.strip().startswith("export const meta") or task.strip().startswith(
            "export default"
        ):
            log_status("检测到 JS 脚本，直接执行", color=CLAUDE)
            script = task
        elif task.endswith(".js") and os.path.exists(task):
            log_status(f"加载 JS 文件: {task}", color=CLAUDE)
            with open(task, "r", encoding="utf-8") as f:
                script = f.read()
        else:
            log_status("LLM 正在编写 JS Workflow 脚本...", color=CLAUDE)
            script = await self._llm_write_workflow(task)
            if script:
                # ponytail: 保存生成的脚本到桌面，用描述性文件名
                try:
                    import re as _re
                    _name = "workflow"
                    _m = _re.search(r"name:\s*['\"]([^'\"]+)", script)
                    if _m:
                        _name = _m.group(1).strip().replace(" ", "_")[:40]
                    else:
                        _safe = _re.sub(r"[^\w]", "_", task[:30]).strip("_")[:30]
                        if _safe:
                            _name = _safe
                    _path = os.path.expanduser(f"~/Desktop/{_name}.js")
                    # 如果文件已存在，加序号
                    if os.path.exists(_path):
                        _base = _path.rsplit(".", 1)[0]
                        _n = 1
                        while os.path.exists(f"{_base}_{_n}.js"):
                            _n += 1
                        _path = f"{_base}_{_n}.js"
                    # 同时更新 _last_workflow.js 方便快速查看最新
                    _last = os.path.expanduser("~/Desktop/_last_workflow.js")
                    with open(_last, "w", encoding="utf-8") as _f:
                        _f.write(script)
                    with open(_path, "w", encoding="utf-8") as _f:
                        _f.write(script)
                    log_status(f"已保存脚本到 {_path}", color="white")
                except Exception:
                    pass
            if script and not self._validate_workflow_script(script, task):
                log_status("LLM 脚本语义校验未通过，使用固定模板", color="yellow")
                script = ""
            if not script:
                log_status("LLM 写脚本失败，使用固定模板", color="yellow")
                task_safe = task[:300].replace("`", "\\`").replace("$", "\\$")
                script = f"""
export const meta = {{
    name: "单Agent执行",
    description: "LLM不可用，直接用agent执行任务",
    phases: [
        {{"title": "执行", "detail": "直接执行任务"}},
    ],
}}

export default async function() {{
    globalThis._globalTask = `{task_safe}`
    phase("执行")
    return await agent(`{task_safe}`, {{ label: "执行", timeout: 300, isFinal: true }})
}}
"""

        try:
            from core.multi_agent_v2.workflow import run_claude_workflow

            # ponytail: 如果 task 是本地目录路径，作为 args.path 传入 workflow
            workflow_args = None
            _stripped = task.strip()
            if os.path.isdir(_stripped):
                workflow_args = {"path": os.path.abspath(_stripped)}

            wr = await run_claude_workflow(script, args=workflow_args)

            if wr.success and wr.output:
                text = str(wr.output)
                print(f"\n  \033[1;37m◇ \033[0m\033[1mResult\033[0m")
                print(f"  {text[:1000] if len(text) > 1000 else text}")
                if wr.phases:
                    print(f"\n  \033[2mPhases: {' → '.join(p.title for p in wr.phases)}  ·  {wr.elapsed:.1f}s\033[0m")
                if wr.agent_graph and (wr.agent_graph.get('nodes') or wr.agent_graph.get('edges')):
                    g = wr.agent_graph
                    phases_data = [{"title": p.title, "detail": p.detail} for p in wr.phases] if wr.phases else []
                    g['_phases'] = phases_data
                    _render_agent_graph(g)
            else:
                log_status(f"编排完成但无结果: {wr.error or '无输出'}", color="yellow")
        except Exception as e:
            # ponytail: 语法错误时打印前500字符方便调试
            if script:
                _snippet = script[:500].replace("\\", "\\\\").replace("`", "\\`")
                print(f"    \033[2;37m[debug] 生成脚本前500字符:\033[0m\n{_snippet}\n    \033[2;37m[debug] 脚本总长度: {len(script)} 字符\033[0m")
            pe(f"编排执行失败: {e}")

    async def _llm_write_workflow(self, task: str) -> str:
        """用 LLM 根据任务描述生成 JS Workflow 脚本"""
        try:
            from core.engine.llm_backend import get_llm_router

            router = get_llm_router()
            if not router or not router.is_available():
                return ""

            # ── 第一步：匹配 Pattern（先用 LLM 分类）──
            pattern_match_prompt = (
                "从以下10个pattern中选出最匹配以下任务的编号，只输出编号(如 ⑩)，不要其他文字。\n\n"
                "① 纯并行→汇总（多源搜索/多平台对比）\n"
                "② 串行流水线（分析→报告）\n"
                "③ 复杂DAG（代码生成/多模块）\n"
                "④ 动态批量（遍历文件批量处理）\n"
                "⑤ CodeGraph预扫描→多Agent分析（项目分析首选）\n"
                "⑥ 迭代循环（代码优化/迭代改进）\n"
                "⑦ 产出→验证（方案审查/安全审核）\n"
                "⑧ 多方案Tournament（方案选优）\n"
                "⑨ 容错并行（多源搜索/个别允许失败）\n"
                "⑩ 游戏开发专用（植物大战僵尸等）\n\n"
                "任务：" + task[:300] + "\n\n编号："
            )
            pattern_resp = await asyncio.wait_for(
                router.simple_chat(pattern_match_prompt, temperature=0, max_tokens=10),
                timeout=15.0,
            )
            matched_pattern = str(pattern_resp or "").strip()[:3]

            # ── 第二步：靶向注入 Pattern 提示 ──
            extracted = self._extract_pattern_sections(matched_pattern)
            if extracted:
                rules = (
                    "严格按照以下模板的结构生成 workflow。\n"
                    "独立模块必须用 parallel() 并行，禁止串行。\n"
                    "可以组合/嵌套多个模板来满足任务需求。\n"
                )
                # ponytail: prevent LLM from dropping HTML output in game workflows
                if "⑩" in matched_pattern or "10" in matched_pattern:
                    rules += (
                        "⚠️ 游戏开发铁律（违者输出不可运行）：\n"
                        "• 最后一个 agent 必须用 write_file 生成完整的 game.html\n"
                        "• game.html 必须内联/引用所有 JS 模块，可直接在浏览器打开\n"
                        "• 绝对禁止省略 HTML 输出或用 read_file 替代 write_file\n"
                    )

                prompt = (
                    f"【匹配 Pattern: {matched_pattern}】\n"
                    + rules
                    + "\n参考模板：\n" + extracted + "\n\n"
                    + "任务：" + task[:600]
                )
            else:
                base_prompt = self._prompt_template.replace("{{task}}", task[:600])
                prompt = (
                    f"【匹配 Pattern: {matched_pattern}】\n"
                    "严格按照该 pattern 的示例代码结构生成 workflow。\n"
                    "独立模块必须用 parallel() 并行，禁止串行。\n\n"
                    + base_prompt
                )
            resp = await asyncio.wait_for(
                router.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=8192,
                ),
                timeout=120.0,
            )
            text = str(resp).strip() if resp else ""
            if not text or "[LLM_MOCK]" in text:
                return ""

            # 去掉 markdown 代码块标记
            text = text.removeprefix("```javascript").removeprefix("```js").removeprefix("```")
            text = text.removesuffix("```").strip()
            # 去掉 LLM 在代码前加的中文说明
            export_idx = text.find("export const meta")
            if export_idx >= 0:
                text = text[export_idx:].strip()
            # 截掉代码后面的中文说明
            # ponytail: 跳过 template literal `...` 内的 ${...} 避免 brace 计数被干扰
            fn_idx = text.find("export default async function")
            if fn_idx >= 0:
                brace_count = 0
                started = False
                in_backtick = False
                for i in range(fn_idx, len(text)):
                    ch = text[i]
                    if ch == '`':
                        in_backtick = not in_backtick
                        continue
                    if in_backtick:
                        continue
                    if ch == '{':
                        brace_count += 1
                        started = True
                    elif ch == '}':
                        brace_count -= 1
                        if started and brace_count == 0:
                            text = text[:i+1].strip()
                            break
            if "export const meta" not in text:
                return ""
            return text
        except Exception:
            return ""

    def _extract_pattern_sections(self, pattern_str: str) -> str:
        """从 workflow 模板中提取匹配编号的代码段"""
        nums = re.findall(r'[①-⑩]', pattern_str)
        if not nums:
            return ""
        path = Path(__file__).parent.parent.parent / "workflows" / ".workflow_prompt_template.md"
        if not path.exists():
            return ""
        sections = re.split(r"\n(?=### [①-⑩])", path.read_text(encoding="utf-8"))
        matched = []
        for s in sections:
            m = re.match(r"### ([①-⑩])", s.strip())
            if m and m.group(1) in nums:
                matched.append(s.strip())
        return "\n\n---\n\n".join(matched)

    def _validate_workflow_script(self, script: str, task: str) -> bool:
        if "export const meta" not in script:
            return False
        if "export default" not in script or "async function" not in script:
            return False
        return True

    # ──────────────────────────────────────────────
    # /analyze
    # ──────────────────────────────────────────────

    async def handle_analyze(self, parsed_cmd: ParsedCommand):
        """/analyze 命令"""
        action = parsed_cmd.action or "visualize"
        params = parsed_cmd.params

        think_start(f"数据分析: {action}")
        think_analyze("数据分析")
        think_plan([
            {"title": "数据分析", "description": f"执行{action}分析"},
            {"title": "生成结果", "description": "生成分析报告或图表"},
        ])

        think_step(1)
        think_log(f"正在执行{action}分析...")

        try:
            from cli.base import WorkflowEngineWrapper

            wrapper = WorkflowEngineWrapper()
            workflow = {
                "name": f"分析_{action}",
                "description": f"{action}分析",
                "steps": [{
                    "type": "analyze", "action": action, "params": params,
                    "description": f"执行{action}分析",
                }],
                "generate_report": True,
            }
            result = await wrapper.create_and_execute(str(workflow), mode="workflow")
            think_complete(1, success=True)
            think_step(2)
            think_log("生成分析结果...")
            think_complete(2, success=True)
            think_summarize(True, result)
            self.cli._display_workflow_result(result)
        except Exception as e:
            think_complete(1, success=False, error=str(e))
            think_summarize(False)
            log_error(f"分析失败: {e}")

    # ──────────────────────────────────────────────
    # /scrape
    # ──────────────────────────────────────────────

    async def handle_scrape(self, parsed_cmd: ParsedCommand):
        """/scrape 命令"""
        site = parsed_cmd.action or "微博"
        action = parsed_cmd.params.get("action", "热搜top10")

        think_start(f"爬取{site}: {action}")
        think_analyze("数据爬取")
        think_plan([
            {"title": "连接网站", "description": f"访问{site}网站"},
            {"title": "获取数据", "description": f"获取{action}数据"},
            {"title": "保存结果", "description": "保存数据到文件"},
        ])

        think_step(1)
        think_log(f"正在连接{site}...")

        try:
            from cli.base import WorkflowEngineWrapper

            wrapper = WorkflowEngineWrapper()
            workflow = {
                "name": f"爬虫_{site}",
                "description": f"爬取{site}数据",
                "steps": [{
                    "type": "scrape", "site": site, "action": action,
                    "description": f"爬取{site}{action}",
                }],
                "generate_report": True,
            }
            result = await wrapper.create_and_execute(str(workflow), mode="workflow")
            think_complete(1, success=True)
            think_step(2)
            think_log(f"获取{action}数据...")
            think_complete(2, success=True)
            think_step(3)
            think_log("保存数据...")
            think_complete(3, success=True)
            think_summarize(True, result)
            self.cli._display_workflow_result(result)
        except Exception as e:
            think_complete(1, success=False, error=str(e))
            think_summarize(False)
            log_error(f"爬取失败: {e}")

    # ──────────────────────────────────────────────
    # /automate
    # ──────────────────────────────────────────────

    async def handle_automate(self, parsed_cmd: ParsedCommand):
        """/automate 命令"""
        action = parsed_cmd.action
        params = parsed_cmd.params
        if not action:
            print_error("请提供自动化操作，如: /automate open_app --app Safari")
            return

        think_start(f"自动化操作: {action}")
        think_analyze("GUI自动化")
        think_plan([{"title": f"执行{action}", "description": f"执行{action}操作"}])

        think_step(1)
        think_log(f"正在执行{action}...")

        try:
            from cli.base import WorkflowEngineWrapper

            wrapper = WorkflowEngineWrapper()
            workflow = {
                "name": f"CLI自动化_{action}",
                "description": f"CLI触发的{action}操作",
                "steps": [{
                    "type": "automate", "action": action, "params": params,
                    "description": f"执行{action}",
                }],
                "generate_report": False,
            }
            result = await wrapper.create_and_execute(str(workflow), mode="workflow")
            think_complete(1, success=True)
            think_summarize(True, result)
            self.cli._display_workflow_result(result)
        except Exception as e:
            think_complete(1, success=False, error=str(e))
            think_summarize(False)
            log_error(f"自动化失败: {e}")

    # ──────────────────────────────────────────────
    # /wechat
    # ──────────────────────────────────────────────

    async def handle_wechat(self, parsed_cmd: ParsedCommand):
        """/wechat 命令"""
        action = parsed_cmd.action
        params = parsed_cmd.params

        if action == "send":
            friend = params.get("friend")
            message = params.get("message")
            if not friend or not message:
                print_error("请提供好友名称和消息内容")
                print_error("示例: /wechat send --friend 张三 --message 你好")
                return

            think_start(f"发送微信消息给{friend}")
            think_analyze("微信消息发送")
            think_plan([
                {"title": "打开微信", "description": "启动微信应用"},
                {"title": "搜索好友", "description": f"查找好友{friend}"},
                {"title": "发送消息", "description": f"发送消息: {message}"},
            ])

            think_step(1)
            think_log("正在打开微信...")

            try:
                subprocess.run(["open", "-a", "WeChat"])
                await asyncio.sleep(2)
                think_complete(1, success=True)

                think_step(2)
                think_log(f"搜索好友{friend}...")
                script = 'tell application "System Events" to tell application process "WeChat" to keystroke "f" using command down'
                subprocess.run(["osascript", "-e", script])
                await asyncio.sleep(0.5)
                script2 = f'tell application "System Events" to tell application process "WeChat" to keystroke "{friend}"'
                subprocess.run(["osascript", "-e", script2])
                await asyncio.sleep(0.8)
                script3 = 'tell application "System Events" to tell application process "WeChat" to keystroke return'
                subprocess.run(["osascript", "-e", script3])
                await asyncio.sleep(1.5)
                think_complete(2, success=True)

                think_step(3)
                think_log("发送消息...")
                subprocess.run(["pbcopy"], input=message.encode("utf-8"))
                await asyncio.sleep(0.2)
                script4 = 'tell application "System Events" to tell application process "WeChat" to keystroke "v" using command down'
                subprocess.run(["osascript", "-e", script4])
                await asyncio.sleep(0.3)
                script5 = 'tell application "System Events" to tell application process "WeChat" to keystroke return'
                subprocess.run(["osascript", "-e", script5])
                await asyncio.sleep(1.0)
                think_complete(3, success=True)
                think_summarize(True, {"success": True})
                log_success(f"消息已发送给 {friend}")
            except Exception as e:
                think_complete(1, success=False, error=str(e))
                think_summarize(False)
                log_error(f"发送失败: {e}")
        else:
            print_error(f"未知微信操作: {action}")

    # ──────────────────────────────────────────────
    # /chat
    # ──────────────────────────────────────────────

    async def handle_chat(self, parsed_cmd: ParsedCommand):
        """/chat 命令"""
        valid_modes = {"simple", "deep", "expert", "quick"}
        action = parsed_cmd.action or ""
        remaining = parsed_cmd.remaining.strip()

        if action in valid_modes:
            mode = action
            initial_message = remaining
        else:
            mode = "simple"
            initial_message = (action + " " + remaining).strip()

        if initial_message:
            self.cli.chat_mode = True
            print_color(f"\n进入聊天模式 ({mode})...", CliColors.BLUE)
            print_chat_bubble(initial_message, is_user=True)
            self.cli.chat_history.append({"role": "user", "content": initial_message})
            await self.handle_smart_request_with_history(initial_message)
            await self._chat_mode_loop()
        else:
            await self._start_chat_mode(mode)

    async def _start_chat_mode(self, mode: str = "simple"):
        """进入聊天模式"""
        self.cli.chat_mode = True
        print_color(f"\n进入聊天模式 ({mode})...", CliColors.BLUE)
        print_color("输入 quit/exit/bye 退出聊天模式，/clear 清空历史", CliColors.GRAY)
        print_color(f"当前会话: {self.cli.session_id}", CliColors.GRAY)
        await self._chat_mode_loop()

    async def _chat_mode_loop(self):
        """聊天模式核心循环"""
        from cli.prompt import get_chat_input

        while self.cli.chat_mode:
            try:
                user_input = get_chat_input(self.cli)

                if user_input.lower() in ["quit", "exit", "bye", "结束"]:
                    print_color("👋 退出聊天模式", CliColors.BLUE)
                    self.cli.chat_mode = False
                    break

                if not user_input.strip():
                    continue

                self.cli.chat_history.append({"role": "user", "content": user_input})
                print_chat_bubble(user_input, is_user=True)

                parsed_cmd = self.cli.command_parser.parse(user_input)

                if parsed_cmd.is_command:
                    if parsed_cmd.command_type == CommandType.CLEAR:
                        self.cli.chat_history = []
                        print_color("聊天历史已清空", CliColors.BLUE)
                    else:
                        await self.cli.handle_command(parsed_cmd)
                else:
                    await self.handle_smart_request_with_history(user_input)

            except KeyboardInterrupt:
                print_color("\n👋 退出聊天模式", CliColors.BLUE)
                self.cli.chat_mode = False
                break
            except Exception as e:
                log_error(f"聊天处理失败: {e}")

    async def handle_smart_request_with_history(self, request: str):
        """带历史记录的智能请求处理"""
        if not request.strip():
            return

        from core.multi_agent_v2.agents.base.models import Task
        from core.multi_agent_v2.agents.base.work_agent import WorkAgent

        initial_message = request
        agent = WorkAgent()
        # ponytail: cli_user 默认 id，接 user_id 模块后可替换
        agent.user_id = str(getattr(self.cli, 'user_id', 'cli_user'))
        task = Task(task_id=uuid.uuid4().hex[:8], type="general", description=request)

        try:
            result = await agent.execute(task)
        except Exception as e:
            print_error(f"❌ 执行异常: {e}")
            return

        if result.success:
            answer = str(result.output)
            if answer:
                # ponytail: 智能截断——找到最后一个自然断点（段落/句子/列表项）
                _display = answer
                if len(answer) > 2000:
                    _truncated = answer[:2000]
                    _break = max(_truncated.rfind('\n\n'), _truncated.rfind('\n-'), _truncated.rfind('。\n'), _truncated.rfind('。'))
                    if _break > 500:
                        _display = answer[:_break + 1]
                    else:
                        _display = _truncated
                    _display += "\n\n...(完整结果已保存到桌面 v2_result.txt)"
                print_chat_bubble(_display, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": answer})

            # ponytail: 对话结束后提取事实，失败静默
            try:
                from core.memory.memory_middleware import get_memory_middleware
                mw = get_memory_middleware()
                uid = str(getattr(self.cli, 'user_id', 'cli_user'))
                asyncio.ensure_future(mw.process_turn(uid, initial_message, str(answer)[:2000]))
            except Exception:
                pass

    async def handle_smart_request(self, request: str):
        """处理智能请求"""
        if not request.strip():
            return

        from cli.colors import print_error as pe, print_success as ps
        from cli.thinking_trace import get_trace
        from core.multi_agent_v2.agents.base.models import Task
        from core.multi_agent_v2.agents.base.work_agent import WorkAgent

        trace = get_trace()
        trace.enabled = True
        trace.start(request[:80])

        agent = WorkAgent()
        agent.user_id = str(getattr(self.cli, 'user_id', 'cli_user'))
        task = Task(task_id=uuid.uuid4().hex[:8], type="general", description=request)

        try:
            result = await agent.execute(task)
        except Exception as e:
            pe(f"❌ 执行异常: {e}")
            return

        if result.success:
            text = str(result.output)[:300]
            if text.strip():
                ps(f"   {text.strip()}")
        else:
            pe(f"❌ {result.error or '执行失败'}")

    # ──────────────────────────────────────────────
    # MCP recommendation / Clarification helpers
    # ──────────────────────────────────────────────

    async def _handle_mcp_recommendation(
        self, mcp_result: Dict[str, Any], original_request: str
    ):
        """处理MCP服务器推荐结果"""
        if not mcp_result.get("success"):
            log_warning(f"MCP推荐失败: {mcp_result.get('error')}")
            return

        from cli.colors import _console

        recommendation_text = mcp_result.get("recommendation_text", "")
        if recommendation_text:
            print_color(recommendation_text, CliColors.CYAN)

        try:
            user_choice = _console.input("\n[yellow bold]请选择: [/]").strip().lower()
        except (EOFError, KeyboardInterrupt):
            user_choice = "no"

        recommended_servers = mcp_result.get("recommended_servers", [])

        selected_server = None
        if user_choice in ["是", "yes", "y", "1"]:
            if recommended_servers:
                selected_server = recommended_servers[0]["server_name"]
        elif user_choice.isdigit():
            index = int(user_choice) - 1
            if 0 <= index < len(recommended_servers):
                selected_server = recommended_servers[index]["server_name"]
        elif user_choice in ["否", "no", "n"]:
            print_color("\n好的，我将使用普通聊天模式回复您。", CliColors.GREEN)
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": llm_response})
            return
        else:
            print_warning("无效选择，将使用普通聊天模式")
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": llm_response})
            return

        if not selected_server:
            print_warning("未找到匹配的服务器，将使用普通聊天模式")
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": llm_response})
            return

        print_color(f"\n🔗 正在连接MCP服务器: {selected_server}...", CliColors.CYAN)
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        connect_result = await awesome_mcp_manager.quick_connect(selected_server)

        if not connect_result or not connect_result.get("success"):
            print_error(f"连接MCP服务器失败: {connect_result.get('error', '未知错误')}")
            print_color("将使用普通聊天模式", CliColors.YELLOW)
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": llm_response})
            return

        print_success(f"✅ 成功连接到 {selected_server}")
        await self._smart_call_mcp_tool(selected_server, original_request)

    async def _handle_clarification(
        self, clarification_result: Dict[str, Any], original_request: str
    ):
        """处理反问结果"""
        if not clarification_result.get("success"):
            log_warning(f"反问步骤失败: {clarification_result.get('error')}")
            return

        from cli.colors import _console

        clarification_text = clarification_result.get("clarification_text", "")
        if clarification_text:
            print_color(clarification_text, CliColors.CYAN)

        try:
            user_answer = _console.input("\n[yellow bold]请输入您的回答: [/]").strip()
        except (EOFError, KeyboardInterrupt):
            user_answer = ""

        if user_answer:
            enhanced_request = f"{original_request}。补充信息：{user_answer}"
            print_color(f"\n好的，我将根据您的补充信息重新处理：{enhanced_request}", CliColors.GREEN)

            from cli.base import WorkflowEngineWrapper

            wrapper = WorkflowEngineWrapper()
            result = await wrapper.create_and_execute(
                enhanced_request, chat_history=self.cli.chat_history
            )

            if result.get("success") and result.get("results"):
                first_result = result["results"][0] if result["results"] else {}
                if first_result.get("type") == "mcp_interaction":
                    await self._handle_mcp_recommendation(first_result, enhanced_request)
                else:
                    response = result.get("summary", result.get("result", "任务完成"))
                    print_chat_bubble(response, is_user=False)
                    self.cli.chat_history.append({"role": "assistant", "content": response})
            else:
                llm_response = await self._chat_with_llm(enhanced_request)
                if llm_response:
                    print_chat_bubble(llm_response, is_user=False)
                    self.cli.chat_history.append({"role": "assistant", "content": llm_response})
        else:
            print_color("\n未收到您的回答，将使用普通聊天模式", CliColors.YELLOW)
            llm_response = await self._chat_with_llm(original_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": llm_response})

    async def _chat_with_llm(self, message: str) -> str:
        """直接使用LLM响应聊天消息"""
        try:
            from core.engine.llm_backend import get_llm_router

            llm_router = get_llm_router()
            if not llm_router.is_available():
                return ""

            messages = []
            system_prompt = """
你是小雷版小龙虾AI助手，一个友好、聪明的聊天伙伴。
请用自然、友好的语言回应用户的请求。
如果是故事请求，请讲一个有趣的小故事。
如果是问题，请给出清晰的回答。
            """.strip()
            messages.append({"role": "system", "content": system_prompt})
            if self.cli.chat_history:
                for msg in self.cli.chat_history[-5:]:
                    messages.append(msg)
            messages.append({"role": "user", "content": message})

            response = await llm_router.chat(messages, temperature=0.7, max_tokens=1000)
            return response.strip() if response else ""
        except Exception as e:
            log_error(f"LLM聊天失败: {e}")
            return ""

    async def _smart_call_mcp_tool(self, server_name: str, user_request: str):
        """智能调用MCP工具"""
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        print_color("\n🔍 正在分析您的需求并选择合适工具...", CliColors.CYAN)

        tools = await awesome_mcp_manager.get_server_tools(server_name)
        if not tools:
            print_warning("未找到可用工具，将使用普通聊天模式")
            llm_response = await self._chat_with_llm(user_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": llm_response})
            return

        best_tool = self._match_best_tool(tools, user_request)
        if not best_tool:
            print_warning("未找到合适的工具，将使用普通聊天模式")
            llm_response = await self._chat_with_llm(user_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": llm_response})
            return

        tool_name = best_tool["name"]
        print_success(f"✅ 选择工具: {tool_name}")
        print_color(f"   描述: {best_tool.get('description', 'N/A')}", CliColors.GRAY)

        required_params = best_tool.get("inputSchema", {}).get("required", [])
        extracted_params = self._extract_tool_params(user_request, best_tool)
        missing_params = [p for p in required_params if p not in extracted_params]

        if missing_params:
            print_color("\n❓ 需要提供以下信息:", CliColors.YELLOW)
            for param in missing_params:
                try:
                    value = input(f"   {param}: ").strip()
                    if value:
                        extracted_params[param] = value
                except (EOFError, KeyboardInterrupt):
                    print_warning("用户取消输入")
                    return

        print_color(f"\n🚀 正在调用 {server_name}.{tool_name}...", CliColors.CYAN)
        result = await awesome_mcp_manager.call_server_tool(
            server_name, tool_name, extracted_params
        )

        if result and isinstance(result, dict) and result.get("success"):
            print_success("✅ 工具调用成功")
            response_text = result.get("result", "操作完成")
            print_chat_bubble(str(response_text), is_user=False)
            self.cli.chat_history.append({"role": "assistant", "content": str(response_text)})
        else:
            error_msg = (
                result.get("error", "未知错误") if isinstance(result, dict) else "未知错误"
            )
            print_error(f"❌ 工具调用失败: {error_msg}")
            llm_response = await self._chat_with_llm(user_request)
            if llm_response:
                print_chat_bubble(llm_response, is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": llm_response})

    def _match_best_tool(self, tools: List[Dict[str, Any]], user_request: str) -> Optional[Dict[str, Any]]:
        """根据用户请求匹配最合适的工具"""
        message_lower = user_request.lower()
        best_score = 0
        best_tool = None

        for tool in tools:
            tool_name = tool.get("name", "").lower()
            tool_desc = tool.get("description", "").lower()
            score = 0
            if tool_name in message_lower:
                score += 3
            keywords = tool_desc.split()
            matched_keywords = [kw for kw in keywords if len(kw) > 2 and kw in message_lower]
            score += len(matched_keywords) * 0.5
            if score > best_score:
                best_score = score
                best_tool = tool

        return best_tool if best_score >= 1.0 else None

    def _extract_tool_params(self, user_request: str, tool: Dict[str, Any]) -> Dict[str, Any]:
        """从用户请求中提取工具参数"""
        params = {}
        properties = tool.get("inputSchema", {}).get("properties", {})

        for param_name, param_schema in properties.items():
            param_type = param_schema.get("type", "string")

            if param_name.lower() in ["city", "location", "place"]:
                city_match = re.search(r"([一-龥]+市|[一-龥]+省)", user_request)
                if city_match:
                    params[param_name] = city_match.group(1)
            elif param_type == "string" and (
                "url" in param_name.lower() or "link" in param_name.lower()
            ):
                url_match = re.search(r"https?://\S+", user_request)
                if url_match:
                    params[param_name] = url_match.group(0)
            elif param_type in ["number", "integer"]:
                number_match = re.search(r"(\d+\.?\d*)", user_request)
                if number_match:
                    num_value = float(number_match.group(1))
                    if param_type == "integer":
                        num_value = int(num_value)
                    params[param_name] = num_value

        return params

    # ──────────────────────────────────────────────
    # /smart
    # ──────────────────────────────────────────────

    async def handle_smart(self, parsed_cmd: ParsedCommand):
        """/smart 命令"""
        action = parsed_cmd.action.lower() if parsed_cmd.action else ""
        remaining = parsed_cmd.remaining.strip()

        if action in ("demo", "status"):
            print_color(
                'ℹ️  /smart demo/status 已不再支持，直接使用 /smart "任务" 执行',
                CliColors.YELLOW,
            )
            return

        user_query = (action + " " + remaining).strip() if action else remaining
        if user_query:
            await self.handle_smart_request(user_query)
        else:
            print_error('请提供任务描述，如: /smart "爬取微博热搜并分析"')
            print_color("\n💡 智能多Agent命令用法:", CliColors.CYAN)
            print_color("────────────────────────", CliColors.GRAY)
            print_color('/smart "任务描述" - 使用智能Agent执行任务', CliColors.WHITE)
            print_color("直接输入自然语言 - 自动识别处理（无需前缀）", CliColors.WHITE)

    # ──────────────────────────────────────────────
    # /workflows
    # ──────────────────────────────────────────────

    async def handle_workflows(self, parsed_cmd: ParsedCommand):
        """处理工作流进度查看命令"""
        print_color("\n📋 多Agent编排", CliColors.BOLD)
        print_color("─" * 50, CliColors.GRAY)
        print_color('使用 /orchestrate "任务" 启动多Agent自动编排', CliColors.GRAY)
        print_color('使用 /smart "任务" 启动智能Agent执行', CliColors.GRAY)


# ═══════════════════════════════════════════════════════════════
# 协作图渲染
# ═══════════════════════════════════════════════════════════════

def _badge_style(status: str, truncated: bool):
    if status == "failed":
        return "❌", "fill:#fee2e2,stroke:#ef4444", "#ef4444"
    if truncated:
        return "⚠️", "fill:#fef3c7,stroke:#f59e0b", "#f59e0b"
    if status == "done":
        return "✅", "fill:#dcfce7,stroke:#22c55e", "#22c55e"
    return "⏳", "fill:#e0f2fe,stroke:#3b82f6", "#3b82f6"


def _render_agent_graph(graph: dict):
    """将 agent_graph 渲染为执行报告 HTML（含阶段/依赖/重试标记）"""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    retry_events = graph.get("retryEvents", [])
    comp_warnings = graph.get("compressionWarnings", [])
    phases_meta = graph.get("_phases", [])
    if not nodes and not edges:
        return

    from cli.colors import print_success, log_status, CLAUDE
    log_status("正在生成执行报告...", color=CLAUDE)

    retry_map = {}
    for e in retry_events:
        retry_map.setdefault(e.get("label"), []).append(e)

    # ── 按 phase 分组 ──
    phase_names = [p["title"] for p in phases_meta] if phases_meta else []
    phase_groups: dict[str, list] = {}
    for n in nodes:
        p = n.get("phase") or ""
        phase_groups.setdefault(p, []).append(n)
    # 无 phase 的归入"未分组"
    if "" in phase_groups and len(phase_groups[""]) == len(nodes):
        phase_groups.clear()

    # ── 构建 Mermaid ──
    mermaid_lines = ["graph TD"]
    global_nid = 0
    node_ids = {}
    all_details = []

    def _emit_node(n):
        nonlocal global_nid
        nid = f"N{global_nid}"
        global_nid += 1
        label = n.get("label", nid)
        status = n.get("status", "unknown")
        duration = n.get("duration", 0)
        dur_str = f"{duration/1000:.1f}s" if duration else ""
        truncated = bool((n.get("metadata") or {}).get("truncated"))
        has_retry = label in retry_map
        badge, style, _ = _badge_style(status, truncated)

        display = f"{badge} {label}"
        if dur_str:
            display += f" ({dur_str})"
        mermaid_lines.append(f'    {nid}["{display}"]')
        mermaid_lines.append(f'    style {nid} {style}')
        node_ids[label] = nid

        rows = [f"<tr><td>状态</td><td>{badge} {status}</td></tr>"]
        if dur_str:
            rows.append(f"<tr><td>耗时</td><td>{dur_str}</td></tr>")
        model = n.get("model", "")
        if model:
            rows.append(f"<tr><td>模型</td><td>{model}</td></tr>")
        if truncated:
            rows.append(f'<tr><td style="color:#f59e0b">截断</td><td style="color:#f59e0b">⚠️ 输出不完整</td></tr>')
        prompt = n.get("prompt", "")
        if prompt:
            rows.append(f"<tr><td>任务</td><td style='font-size:12px;color:#666'>{prompt[:120]}</td></tr>")
        all_details.append({"label": label, "rows": "".join(rows), "has_retry": has_retry, "phase": n.get("phase", "")})

        return nid

    # 按 phase 分组 + 时间排序
    phase_order = []
    _auto_edge_count = 0
    PHASE_FILLS = ["#f0f7ff", "#fefce8", "#f0fdf4", "#fef2f2", "#f5f3ff"]
    if phase_groups:
        for phase_title, phase_nodes in phase_groups.items():
            phase_nodes.sort(key=lambda x: x.get("startTime", 0) or 0)
            phase_order.append((phase_title, phase_nodes))
        # 按最早 startTime 排序
        phase_order.sort(key=lambda x: min((n.get("startTime", 0) or 0) for n in x[1]))
        for idx, (phase_title, phase_nodes) in enumerate(phase_order):
            display_phase = phase_title if phase_title else "未分组"
            phase_color = PHASE_FILLS[idx % len(PHASE_FILLS)]
            mermaid_lines.append(f"    subgraph SG{idx}[{display_phase}]")
            mermaid_lines.append(f"    style SG{idx} fill:{phase_color},stroke:#cbd5e1,stroke-width:1")
            for n in phase_nodes:
                _emit_node(n)
            mermaid_lines.append("    end")
        # ── 自动在 phase 之间加边（fan-out / fan-in / 顺序连） ──
        for idx in range(len(phase_order) - 1):
            _, cur_nodes = phase_order[idx]
            _, next_nodes = phase_order[idx + 1]
            if not cur_nodes or not next_nodes:
                continue
            cn_ids = [node_ids.get(n.get("label", "")) for n in cur_nodes if node_ids.get(n.get("label", ""))]
            nn_ids = [node_ids.get(n.get("label", "")) for n in next_nodes if node_ids.get(n.get("label", ""))]
            if not cn_ids or not nn_ids:
                continue
            if len(cn_ids) == 1 and len(nn_ids) >= 1:
                for nid in nn_ids:
                    mermaid_lines.append(f"    {cn_ids[0]} --> {nid}")
                    _auto_edge_count += 1
            elif len(nn_ids) == 1:
                for cid in cn_ids:
                    mermaid_lines.append(f"    {cid} --> {nn_ids[0]}")
                    _auto_edge_count += 1
            else:
                mermaid_lines.append(f"    {cn_ids[-1]} -->|阶段| {nn_ids[0]}")
                _auto_edge_count += 1
    else:
        # 无 phase 信息：纯时间线
        sorted_nodes = sorted(nodes, key=lambda x: x.get("startTime", 0) or 0)
        for i, n in enumerate(sorted_nodes):
            _emit_node(n)
            # 自动加顺序边
            if i > 0:
                prev_id = node_ids.get(sorted_nodes[i-1].get("label", ""))
                cur_id = node_ids.get(n.get("label", ""))
                if prev_id and cur_id:
                    mermaid_lines.append(f"    {prev_id} --> {cur_id}")

    # 显式依赖边
    for e in edges:
        frm = e.get("from", "")
        to = e.get("to", "")
        if frm in node_ids and to in node_ids:
            mermaid_lines.append(f"    {node_ids[frm]} -->|依赖| {node_ids[to]}")

    # 重试虚线
    seen_retry = set()
    for e in retry_events:
        label = e.get("label", "")
        if label in seen_retry:
            continue
        seen_retry.add(label)
        if label in node_ids:
            mermaid_lines.append(f"    {node_ids[label]} -.->|重试| {node_ids[label]}")

    mermaid_code = "\n".join(mermaid_lines)

    # ── 按 phase 分组的详情卡片 ──
    phase_detail_blocks = []
    if phase_groups:
        for phase_title, phase_nodes in phase_groups.items():
            display_phase = phase_title if phase_title else "未分组"
            total = len(phase_nodes)
            ok = sum(1 for n in phase_nodes if n.get("status") == "done")
            cards = ""
            for n in phase_nodes:
                label = n.get("label", "?")
                has_retry = label in retry_map
                badge, _, color = _badge_style(n.get("status", "unknown"), (n.get("metadata") or {}).get("truncated", False))
                dur_str = f"{(n.get('duration', 0) / 1000):.1f}s" if n.get("duration") else ""
                cards += f'''
      <div class="node-card" style="border-left:4px solid {color}">
        <h3>{badge} {label} <span class="node-time">{dur_str}</span></h3>
        {"<span class=\"retry-badge\">🔄 重试</span>" if has_retry else ""}
      </div>'''
            phase_detail_blocks.append(f'''
    <div class="phase-detail">
      <div class="phase-detail-header">
        <h2>📁 {display_phase}</h2>
        <span class="phase-stats">{ok}/{total} 成功</span>
      </div>
      {cards}
    </div>''')
    else:
        # 无 phase：平铺卡片
        for d in all_details:
            phase_detail_blocks.append(f'''
    <div class="node-card">
      <h3>{d["label"]}</h3>
      {"<span class=\"retry-badge\">🔄 重试</span>" if d["has_retry"] else ""}
    </div>''')

    detail_html = "".join(phase_detail_blocks)

    warning_html = ""
    if comp_warnings:
        warning_html = '<div class="warnings"><h3>⚠️ 压缩警告</h3><ul>' + "".join(
            f'<li><strong>{w.get("label","?")}</strong>: {w.get("detail","")}</li>' for w in comp_warnings
        ) + "</ul></div>"

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<title>Workflow 执行报告</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#f0f2f5; font-family:-apple-system,"Microsoft YaHei",sans-serif; padding:40px; }}
  .container {{ max-width:1200px; margin:0 auto; }}
  h1 {{ font-size:22px; margin-bottom:4px; color:#1a1a2e; }}
  .subtitle {{ font-size:13px; color:#666; margin-bottom:24px; }}
  .layout {{ display:flex; gap:24px; align-items:flex-start; }}
  @media (max-width:900px) {{ .layout {{ flex-direction:column; }} }}
  .diagram {{ flex:1; min-width:0; background:#fff; border-radius:12px; padding:24px; box-shadow:0 2px 12px rgba(0,0,0,0.08); overflow-x:auto; }}
  .diagram svg {{ max-width:100%; height:auto; }}
  .details {{ width:340px; display:flex; flex-direction:column; gap:16px; }}
  @media (max-width:900px) {{ .details {{ width:auto; }} }}
  .phase-detail {{ background:#fff; border-radius:10px; overflow:hidden; box-shadow:0 1px 6px rgba(0,0,0,0.06); }}
  .phase-detail-header {{ display:flex; justify-content:space-between; align-items:center; padding:10px 14px; background:#f8fafc; border-bottom:1px solid #e2e8f0; }}
  .phase-detail-header h2 {{ font-size:14px; margin:0; color:#1e293b; }}
  .phase-stats {{ font-size:11px; color:#64748b; background:#e2e8f0; padding:1px 8px; border-radius:8px; }}
  .node-card {{ padding:10px 14px; border-bottom:1px solid #f0f0f0; }}
  .node-card:last-child {{ border-bottom:none; }}
  .node-card h3 {{ font-size:13px; margin:0; color:#1a1a2e; display:flex; align-items:center; gap:4px; }}
  .node-time {{ font-size:11px; color:#94a3b8; font-weight:normal; margin-left:auto; }}
  .retry-badge {{ font-size:10px; background:#fef3c7; color:#d97706; padding:1px 6px; border-radius:3px; }}
  .warnings {{ background:#fef3c7; border:1px solid #f59e0b; border-radius:10px; padding:16px; margin-top:20px; }}
  .warnings h3 {{ font-size:15px; color:#d97706; margin-bottom:8px; }}
  .warnings li {{ font-size:13px; margin:4px 0; color:#92400e; }}
  .legend {{ display:flex; gap:20px; margin-top:16px; font-size:12px; color:#666; }}
</style>
</head>
<body><div class="container">
<h1>🔄 Workflow 执行报告</h1>
<p class="subtitle">{len(nodes)} 个 Agent · {len(edges) + _auto_edge_count} 条依赖 · {len(retry_events)} 次重试 · {len(comp_warnings)} 个压缩警告 · {len(phase_names)} 阶段</p>
<div class="layout">
<div class="diagram">
<div class="mermaid">
{mermaid_code}
</div>
<div class="legend">
<span>✅ 成功</span> <span>⚠️ 输出截断</span> <span>❌ 失败</span> <span>⏳ 运行中</span>
<span style="margin-left:16px;border-bottom:2px dashed #999">─ 重试</span>
</div>
</div>
<div class="details">
{detail_html}
{warning_html}
</div>
</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad:true,theme:'neutral',flowchart:{{useMaxWidth:true,htmlLabels:true}}}})</script>
</body></html>'''

    import tempfile, subprocess
    path = os.path.join(tempfile.gettempdir(), "workflow-exec-report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    subprocess.Popen(["open", path])
    print_success(f"  ☝️  执行报告已打开: {path}")

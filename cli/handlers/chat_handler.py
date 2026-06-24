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

        print_section("🤖 多Agent 自动编排 (JS Workflow)")

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

            wr = await run_claude_workflow(script)

            if wr.success and wr.output:
                print_section("📋 最终结果")
                text = str(wr.output)
                print(text[:1000] if len(text) > 1000 else text)
                if wr.phases:
                    print(
                        f"    \033[2;37m阶段: {' → '.join(p.title for p in wr.phases)}"
                        f" | {wr.elapsed:.1f}s\033[0m"
                    )
                if wr.agent_graph and (wr.agent_graph.get('nodes') or wr.agent_graph.get('edges')):
                    _render_agent_graph(wr.agent_graph)
            else:
                log_status(f"编排完成但无结果: {wr.error or '无输出'}", color="yellow")
        except Exception as e:
            pe(f"编排执行失败: {e}")

    async def _llm_write_workflow(self, task: str) -> str:
        """用 LLM 根据任务描述生成 JS Workflow 脚本"""
        try:
            from core.engine.llm_backend import get_llm_router

            router = get_llm_router()
            if not router or not router.is_available():
                return ""

            # ── 先识别任务类型 ──
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()
            is_code_task = False
            if router and router.is_available():
                resp = await router.simple_chat(
                    "判断以下请求是否需要生成代码/脚本。只回答'是'或'否'。注意：写文章/博客/文档不算。\n请求：" + task[:200],
                    temperature=0, max_tokens=10
                )
                is_code_task = '是' in str(resp or '')

            # ── 检测到 JS 脚本片段直接执行 ──
            if "export const meta" not in task and "$dag" not in task and is_code_task:
                # 代码生成/重构类：保留 $dag 强制模板（已验证可靠）
                prompt = (
                    "生成 JS Workflow 脚本，必须包含 export const meta + export default async function。\n\n"
                    "API: agent(prompt,{label,isFinal}) $dag(nodes) parallel(thunks)\n\n"
                    "这是代码类任务，必须用 $dag 模式（声明式 DAG 依赖编排）：\n"
                    "- 先分析接口/设计\n"
                    "- 再并行写各个模块\n"
                    "- 最后合并/集成\n\n"
                    "$dag 示例：\n"
                    "const ctx = await $dag({\n"
                    "  分析: () => agent('分析',{label:'分析'}),\n"
                    "  引擎: {depends:'分析',task: ctx => agent('引擎\\n'+ctx['分析'],{label:'引擎'})},\n"
                    "  UI: {depends:'分析',task: ctx => agent('UI\\n'+ctx['分析'],{label:'UI'})},\n"
                    "  合并: {depends:['引擎','UI'],task: ctx => agent('合并\\n'+ctx['引擎']+ctx['UI'],{label:'合并',isFinal:true})},\n"
                    "})\n"
                    "return ctx['合并'];\n\n"
                    f"任务：{task[:600]}\n\n"
                    "开始："
                )
            else:
                # 其他任务：用编排思维规则，不套模板
                prompt = (
                    "生成 JS Workflow 脚本，必须包含 export const meta + export default async function。\n\n"
                    "【可用 API】\n"
                    "  - agent(prompt, {label, isFinal}) — 启动一个子 Agent 执行子任务\n"
                    "  - parallel([thunks]) — 并行启动多个 agent，等待全部完成，返回数组\n"
                    "  - $dag({key: spec}) — 声明式 DAG 编排（key 间可声明 depends 依赖）\n"
                    "  - phase(title) — 标记阶段性进度分组\n"
                    "  - log(msg) — 输出进度消息\n\n"
                    "【编排规则：根据步骤之间的数据依赖关系选结构，不按任务类型名称选】\n\n"
                    "规则① 某步的输出是下一步的输入（串行数据流）：\n"
                    "   用 await agent() 逐个执行，前一结果传后一 prompt\n"
                    "   例：搜数据 → 分析 → 写报告（每一步依赖上一步结果）\n\n"
                    "规则② 多步彼此完全独立：\n"
                    "   用 parallel([() => agent(...), () => agent(...)]) 同时跑\n"
                    "   例：同时搜百度+微博+知乎，三个结果谁也不用等谁\n\n"
                    "规则③ 部分步骤有依赖关系、部分可并行（复杂拓扑）：\n"
                    "   用 $dag() 声明谁依赖谁，引擎自动决定执行顺序\n"
                    "   例：A 和 B 可并行 → C 依赖 A+B 都完成\n\n"
                    "规则④ 步骤数量在执行前不确定（动态列表）：\n"
                    "   用 for 循环把结果集转成 parallel agent\n"
                    "   例：遍历一组文件，对每个文件开一个 agent 处理\n\n"
                    "规则⑤ 某步的结果决定是否继续或走哪条路（条件分支）：\n"
                    "   用 if/else + await agent() 或 await agent() + guard\n"
                    "   例：搜索结果为空→换搜索词重试；不为空→分析\n\n"
                    "【三要三不要】\n"
                    "  ✅ 必须：用 phase() 给步骤逻辑分组\n"
                    "  ✅ 必须：一个 workflow 里可以混用 parallel + agent + $dag\n"
                    "  ✅ 必须：子 task 的 prompt 语义完整，能独立理解执行\n"
                    "  ❌ 不要：强行用 $dag——除非真的有并行+依赖的拓扑关系\n"
                    "  ❌ 不要：复制示例的变量名和结构——根据实际任务编\n"
                    "  ❌ 不要：写多余注释——代码清晰即可\n\n"
                    f"任务：{task[:600]}\n\n"
                    "开始写 workflow："
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
            fn_idx = text.find("export default async function")
            if fn_idx >= 0:
                brace_count = 0
                started = False
                for i in range(fn_idx, len(text)):
                    if text[i] == '{':
                        brace_count += 1
                        started = True
                    elif text[i] == '}':
                        brace_count -= 1
                        if started and brace_count == 0:
                            text = text[:i+1].strip()
                            break
            if "export const meta" not in text:
                return ""
            return text
        except Exception:
            return ""

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
                print_chat_bubble(answer[:500], is_user=False)
                self.cli.chat_history.append({"role": "assistant", "content": answer[:500]})

            # ponytail: 对话结束后提取事实，失败静默
            try:
                from core.memory.memory_middleware import get_memory_middleware
                mw = get_memory_middleware()
                uid = str(getattr(self.cli, 'user_id', 'cli_user'))
                asyncio.ensure_future(mw.process_turn(uid, initial_message, str(answer)[:500]))
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

def _render_agent_graph(graph: dict):
    """将 agent_graph 渲染为 Mermaid HTML 并用浏览器打开"""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes and not edges:
        return

    from cli.colors import print_success, log_status, CLAUDE
    log_status("正在生成 Agent 协作图...", color=CLAUDE)

    # 构建 Mermaid 流程图
    mermaid_lines = ["graph TD"]
    # 每个 node
    node_ids = {}
    for i, n in enumerate(nodes):
        nid = f"N{i}"
        label = n.get("label", nid)
        task = n.get("prompt", "")
        status = n.get("status", "")
        badge = "✅" if status == "done" else "⏳"
        mermaid_lines.append(f'    {nid}["{badge} {label}"]')
        node_ids[label] = nid
    # 每个 edge
    for e in edges:
        frm = e.get("from", "")
        to = e.get("to", "")
        frm_id = node_ids.get(frm, frm)
        to_id = node_ids.get(to, to)
        mermaid_lines.append(f"    {frm_id} --> {to_id}")

    mermaid_code = "\n".join(mermaid_lines)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<title>Agent 协作图</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #f0f2f5; font-family: -apple-system, "Microsoft YaHei", sans-serif; padding: 40px; }}
  .container {{ max-width: 1000px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin-bottom: 8px; color: #1a1a2e; }}
  .subtitle {{ font-size: 13px; color: #666; margin-bottom: 24px; }}
  .mermaid-wrap {{ background: #fff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); overflow-x: auto; }}
  .mermaid-wrap svg {{ max-width: 100%; height: auto; }}
  .legend {{ display: flex; gap: 20px; margin-top: 16px; font-size: 13px; color: #666; }}
</style>
</head>
<body><div class="container">
<h1>🤖 Agent 协作图</h1>
<p class="subtitle">{len(nodes)} 个 Agent · {len(edges)} 条依赖边</p>
<div class="mermaid-wrap">
<div class="mermaid">
{mermaid_code}
</div>
</div>
<div class="legend">
<span>✅ 已完成</span> <span>⏳ 执行中</span>
</div>
</div></body></html>'''

    import tempfile, subprocess
    path = os.path.join(tempfile.gettempdir(), "agent-collab-graph.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    subprocess.Popen(["open", path])
    print_success(f"  ☝️  Agent 协作图已打开: {path}")

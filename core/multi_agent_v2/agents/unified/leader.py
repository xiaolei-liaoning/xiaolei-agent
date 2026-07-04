"""V1 LeaderAgent + V1LeaderPool — 队长 ReAct 循环 + Worker 池

LeaderAgent: Think → Delegate/Batch → Observe → 循环/完成
V1LeaderPool: Worker 池化管理（按 skill_id 池化 + 创建/归还/清理）
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .worker import LLMAgent, AgentRole, AgentMessage
from .prompts import OUTPUT_FORMATS, llm_json, get_llm_router_safe

logger = logging.getLogger(__name__)


class LeaderAgent(LLMAgent):
    """队长 Agent — 监管 Worker、分析结果、动态规划"""

    def __init__(self, name: str, max_workers: int = 5, tool_registry=None):
        super().__init__(name=name, role=AgentRole.LEADER, tool_registry=tool_registry)
        self.workers: Dict[str, LLMAgent] = {}
        self.max_workers = max_workers
        self.active_worker_count = 3
        self._current_skill_id = "general"
        self.worker_states: Dict[str, str] = {}
        self._pool = None  # V1LeaderPool 引用，由外部设置

    async def supervise_task(self, task_description: str, workers: List[LLMAgent],
                             active_count: int = 3, max_rounds: Optional[int] = None,
                             skill_id: str = "general") -> Dict:
        """队长 ReAct 主循环: Thought → Action → Observation → 循环/完成

        Args:
            task_description: 任务描述
            workers: Worker Agent 列表（全部槽位）
            active_count: 本轮活跃 Worker 数
            max_rounds: 最大循环轮次
            skill_id: 技能 ID
        """
        if max_rounds is None:
            max_rounds = int(os.getenv("AGENT_MAX_ROUNDS", "10"))
        self.active_worker_count = min(active_count, len(workers))
        self._current_skill_id = skill_id
        self.workers = {w.name: w for w in workers}

        logger.info(f"队长 {self.name} 开始 ReAct 执行任务: {task_description}")

        all_results = []
        context_history = []
        round_num = 0

        for w in workers:
            w.leader_name = self.name

        while round_num < max_rounds:
            round_num += 1
            logger.info(f"ReAct 第 {round_num} 轮")

            thought = await self._react_think(
                task_description, context_history, all_results, round_num
            )

            successful = [r for r in all_results if r.get("success")]
            if successful and round_num >= 3 and not thought.get("done"):
                logger.info(f"已有 {len(successful)} 个成功结果，强制 done（跳过 LLM 决策）")
                final = thought.get("thinking", "")
                if not final or len(final) < 20:
                    for r in reversed(successful):
                        data = r.get("result", {})
                        if isinstance(data, dict):
                            c = data.get("tool_result_summary", data.get("content", ""))
                            if c:
                                final = c[:5000]
                                break
                thought = {"done": True, "thinking": final or "任务已完成",
                            "final_result": final or "任务已完成"}

            if thought.get("done"):
                logger.info(f"ReAct 第 {round_num} 轮: 队长判定任务完成")
                final = thought.get("final_result") or thought.get("thinking", "任务完成")
                all_results.append({
                    "success": True,
                    "result": {"tool_result_summary": final, "content": final},
                    "worker": self.name, "task": "最终结果"
                })
                break

            action = thought.get("action", {})
            action_type = action.get("type", "unknown")

            action_result = await self._react_act(
                action_type, action, workers, task_description, context_history
            )

            observation = {
                "round": round_num,
                "thought": thought.get("thinking", ""),
                "action_type": action_type,
                "action": action,
                "result": action_result,
            }
            context_history.append(observation)

            if action_result.get("success"):
                all_results.append(action_result)

            logger.info(f"ReAct 第 {round_num} 轮观察: {action_type} - "
                         f"{'成功' if action_result.get('success') else '失败'}")

            if action_type == "tool" and not action_result.get("success"):
                tool_fail_streak = sum(
                    1 for h in context_history
                    if h["action_type"] == "tool" and not h["result"].get("success")
                )
                if tool_fail_streak >= 1:
                    context_history.append({
                        "round": round_num,
                        "thought": "系统提示：tool 执行失败，下一轮必须使用 delegate 分配给 Worker",
                        "action_type": "system_override",
                        "action": {"type": "delegate"},
                        "result": {"success": False, "error": "tool fallback"},
                    })

            if action_type == "batch_delegate" and not action_result.get("success"):
                analysis = action_result.get("result", {}).get("analysis", {})
                if analysis.get("decision") == "reassign":
                    self.active_worker_count = min(
                        self.active_worker_count + 1, self.max_workers)
                    logger.info(f"reassign: 增加活跃 Worker 到 {self.active_worker_count}")

            if action_type == "batch_delegate" and action_result.get("success") and all_results:
                result_data = action_result.get("result", {})
                success_count = result_data.get("success_count", 0)
                total_count = result_data.get("total_count", 0)
                if total_count > 0 and success_count > 0:
                    logger.info(f"{success_count}/{total_count} 子任务完成，强制切换为 process_results")
                    context_history.append({
                        "round": round_num,
                        "thought": (f"系统强制：{success_count}/{total_count} 子任务已完成，"
                                    "下一轮必须使用 process_results 综合分析（失败子任务也需报告）"),
                        "action_type": "system_override",
                        "action": {"type": "process_results",
                                   "task": f"综合分析以下结果并生成最终答案：{task_description}"},
                        "result": {"success": False, "error": "force process_results"},
                    })

        total_subtask_count = 0
        successful_subtask_count = 0
        for r in all_results:
            result_data = r.get("result", {})
            if isinstance(result_data, dict) and "batch_results" in result_data:
                for br in result_data["batch_results"]:
                    total_subtask_count += 1
                    if br.get("success"):
                        successful_subtask_count += 1
            else:
                total_subtask_count += 1
                if r.get("success"):
                    successful_subtask_count += 1
        success = successful_subtask_count > 0 and successful_subtask_count == total_subtask_count

        if successful_subtask_count == 0 and total_subtask_count > 0:
            _fail_msgs = []
            for h in context_history:
                _r = h.get("result", {})
                if isinstance(_r, dict) and not _r.get("success") and _r.get("error"):
                    _fail_msgs.append(str(_r["error"])[:200])
            if _fail_msgs:
                all_results.append({
                    "success": False,
                    "result": {"tool_result_summary": "失败原因: " + "; ".join(_fail_msgs[:3]),
                               "content": "失败原因: " + "; ".join(_fail_msgs[:3])},
                    "worker": self.name,
                })

        total_subtasks = total_subtask_count

        logger.info(f"{'✅' if success else '❌'} ReAct 任务完成: 共 {round_num} 轮, "
                     f"{total_subtasks} 个子任务")

        result_payload = {
            "success": success, "rounds": round_num,
            "total_subtasks": total_subtasks, "react_history": context_history,
        }
        asyncio.ensure_future(self._store_experience(task_description, result_payload))

        if self.user_id:
            try:
                from core.memory.self_evolution import get_evolution_engine
                asyncio.ensure_future(get_evolution_engine().check_and_evolve(self.user_id))
            except Exception:
                pass

        return {
            "success": success,
            "results": all_results,
            "rounds": round_num,
            "total_subtasks": total_subtasks,
            "react_history": context_history,
        }

    async def _store_experience(self, task: str, result: dict) -> None:
        if not self.vm or not self.user_id:
            return
        success = result.get("success", False)
        rounds = result.get("rounds", 0)
        total_sub = result.get("total_subtasks", 0)
        strategies = set()
        for h in result.get("react_history", []):
            strategies.add(h.get("action_type", ""))
        used = ", ".join(s for s in strategies if s) or "direct"
        task_type = "分析"
        if any(kw in task for kw in ["搜索", "查找", "调研", "热搜"]):
            task_type = "搜索调研"
        elif any(kw in task for kw in ["写", "创建", "保存", "生成"]):
            task_type = "生成创作"
        elif any(kw in task for kw in ["代码", "执行", "运行", "python"]):
            task_type = "代码执行"
        elif any(kw in task for kw in ["分析", "对比", "总结", "翻译"]):
            task_type = "分析处理"
        content = (
            f"[{task_type}] 使用 {used} 策略，{rounds} 轮完成，"
            f"{total_sub}个子任务，{'成功' if success else '失败'}。"
            f"任务: {task[:100]}"
        )
        try:
            self.vm.add_memory(
                user_id=self.user_id, content=content, category="experience",
                metadata={
                    "task_type": task_type, "strategy": used,
                    "rounds": rounds, "success": str(success),
                    "agent": self.name,
                },
            )
        except Exception as e:
            logger.debug(f"写入经验失败: {e}")

    async def _react_think(self, task_description: str, history: List[Dict],
                           results: List[Dict], round_num: int) -> Dict:
        history_text = ""
        if history:
            history_lines = []
            for h in history[-3:]:
                history_lines.append(
                    f"轮次{h['round']}: 思考={h['thought'][:100]}, "
                    f"行动={h['action_type']}, 结果={'成功' if h['result'].get('success') else '失败'}"
                )
            history_text = "\n".join(history_lines)

        if history:
            last_batch = [h for h in history[-2:]
                          if h["action_type"] in ("batch_delegate", "delegate")]
            if last_batch and results:
                history_text += "\n→ 上一轮是 delegate，本轮必须 process_results"

        results_text = ""
        if results:
            result_summaries = []
            for r in results[-3:]:
                data = r.get("result", {})
                if isinstance(data, dict):
                    if "batch_results" in data:
                        for br in data["batch_results"][:3]:
                            br_data = br.get("result", {})
                            if isinstance(br_data, dict):
                                if br.get("success"):
                                    c = br_data.get("tool_result_summary", br_data.get("content", ""))
                                    if c:
                                        result_summaries.append(str(c)[:1500])
                                else:
                                    _err = br_data.get("error", br_data.get("tool_result_summary", ""))
                                    _task = br.get("task", "未知子任务")[:80]
                                    result_summaries.append(f"❌ 子任务失败[{_task}]: {str(_err)[:150]}")
                    else:
                        c = data.get("content", data.get("result", data.get("tool_result_summary", "")))
                        if c:
                            result_summaries.append(str(c)[:1500])
            if result_summaries:
                results_text = "\n【已有结果】\n" + "\n".join(result_summaries)
            else:
                results_text = f"\n已完成 {len(results)} 个子任务"

        tool_hints = ""
        try:
            tools = await self._get_tools_for_task(task_description)
            if tools:
                tool_names = []
                for t in tools:
                    fn = t.get("function", {})
                    name = fn.get("name", "?")
                    desc = fn.get("description", "")[:60]
                    tool_names.append(f"  - {name}: {desc}")
                tool_hints = "\n【Worker 可用工具】\n" + "\n".join(tool_names[:20])
        except Exception:
            pass

        user_context_str = ""
        if self.user_id:
            try:
                from core.memory.memory_middleware import get_memory_middleware
                mw = get_memory_middleware()
                user_context_str = await mw.get_user_context(self.user_id, task_description)
            except Exception:
                pass

        experience_hints = ""
        if self.vm:
            try:
                shared = self.vm.search_memories(
                    query=task_description, user_id=None, top_k=3
                )
                personal = []
                if self.user_id:
                    personal = self.vm.search_memories(
                        query=task_description, user_id=self.user_id, top_k=3
                    )
                combined = (shared or []) + (personal or [])
                seen = set()
                unique = []
                for m in combined:
                    cid = m.get("id", "")
                    if cid not in seen:
                        seen.add(cid)
                        unique.append(m)
                if unique:
                    lines = []
                    for m in unique[:5]:
                        cat = m.get("metadata", {}).get("category", "")
                        prefix = "💡" if cat == "insight" else "📋"
                        lines.append(f"{prefix} {m['content'][:200]}")
                    if lines:
                        experience_hints = "\n【知识库 + 历史经验参考】\n" + "\n".join(lines)
            except Exception as e:
                logger.debug(f"检索知识/经验失败: {e}")

        full_task = task_description
        if user_context_str:
            full_task = f"{task_description}\n\n{user_context_str}\n\n请根据以上用户信息回答。"

        skill_hints = ""
        try:
            pool_info = getattr(self, '_pool', None)
            if pool_info is not None:
                skills = list(pool_info._agent_configs.keys()) if hasattr(pool_info, '_agent_configs') else []
            else:
                from core.engine.config_loader import register_agents_from_config
                skills = [c["id"] for c in register_agents_from_config()]
            if skills:
                skill_hints = f"\n可用 skill: {', '.join(skills)}\n当前匹配 skill: {self._current_skill_id or 'general'}\n\n"
        except Exception:
            skill_hints = "\n可用 skill: project_analyzer, web_scraper, data_analyst, general\n\n"

        system = (
            "你是队长Agent。严格按以下三轮流程执行，不得跳过任何一步：\n\n"
            "第1轮 → delegate（或 batch_delegate）给 Worker 执行\n"
            "第2轮 → process_results 综合分析 Worker 返回的结果\n"
            "第3轮 → done 结束\n\n"
            "格式：\n"
            'delegate: {"done":false,"action":{"type":"delegate","task":"子任务","skill":"skill名"}}\n'
            'batch_delegate: {"done":false,"action":{"type":"batch_delegate","tasks":[{"task":"子任务1","skill":"skill名"},...]}}\n'
            'process_results: {"done":false,"action":{"type":"process_results","task":"综合分析"}}\n'
            'done: {"done":true,"thinking":"已完成..."}\n\n'
            "规则：\n"
            "- 除非用户要求保存文件，否则不要自己决定写文件\n"
            "- 用户要求保存到桌面 → delegate 的 task 里写明用 write_file\n"
            "- 不得跳过 process_results 直接 done\n"
            "输出纯JSON，不要其他内容。"
        ) + skill_hints

        user = (f"任务: {full_task}\n\n历史:\n{history_text or '无'}\n\n"
                f"{results_text}\n\n第{round_num}轮，请思考下一步：")

        result = await llm_json(system, user, max_tokens=500)

        if not result or not isinstance(result, dict):
            return {"done": True, "thinking": "LLM 响应异常，结束任务"}

        return result

    async def _react_act(self, action_type: str, action: Dict,
                         workers: List[LLMAgent], original_task: str,
                         context_history: List[Dict] = None) -> Dict:
        if action_type == "tool":
            tool_name = action.get("tool_name", "")
            args = action.get("args", {})

            if not tool_name:
                return {"success": False, "error": "未指定工具名称"}

            result = await self._execute_tool(tool_name, args)
            return result

        elif action_type == "delegate":
            task = action.get("task", original_task)
            skill_id = action.get("skill", self._current_skill_id or "general")
            if not task:
                return {"success": False, "error": "未指定子任务"}

            worker = workers[0] if workers else None
            if not worker:
                return {"success": False, "error": "无可用 Worker"}

            msg = AgentMessage(from_agent=self.name, content=task, message_type="task")
            result_str = await worker.process_message(msg)

            try:
                data = json.loads(result_str)
                is_ok = data.get("success", True) is True and data.get("status") != "failed"
            except Exception:
                data = {"raw": result_str[:500]}
                is_ok = False

            return {
                "success": is_ok, "result": data,
                "worker": worker.name, "skill_id": skill_id,
            }

        elif action_type == "batch_delegate":
            tasks = action.get("tasks", [])
            if not tasks:
                tasks = await self._decompose_task(original_task)

            if not tasks:
                return {"success": False, "error": "无可用子任务"}

            task_skills = []
            normalized_tasks = []
            for task_item in tasks:
                if isinstance(task_item, dict):
                    t = task_item["task"]
                    s = task_item.get("skill", self._current_skill_id or "general")
                else:
                    t = task_item
                    s = self._current_skill_id or "general"
                normalized_tasks.append(t)
                task_skills.append(s)

            active_workers = []
            _pool_pulled = []
            for i, skill in enumerate(task_skills):
                try:
                    if self._pool:
                        w = await self._pool.get_worker(skill, self.name)
                    else:
                        w = None
                    if w:
                        active_workers.append(w)
                        _pool_pulled.append(w)
                    else:
                        if self._pool:
                            w = await self._pool.get_worker("general", self.name)
                        if w:
                            active_workers.append(w)
                            _pool_pulled.append(w)
                        else:
                            active_workers.append(workers[i % len(workers)])
                except Exception:
                    active_workers.append(workers[i % len(workers)])

            assignments = self._assign(normalized_tasks, active_workers)

            try:
                batch_results = await self._execute_batch(assignments, workers)
            finally:
                for pw in _pool_pulled:
                    try:
                        if self._pool:
                            await self._pool.return_worker(pw)
                    except Exception:
                        pass

            success_count = sum(1 for r in batch_results if r.get("success"))

            if success_count > 0:
                return {
                    "success": True,
                    "result": {
                        "batch_results": batch_results,
                        "success_count": success_count,
                        "total_count": len(batch_results),
                    },
                    "workers": [r.get("worker") for r in batch_results],
                    "skill_ids": task_skills,
                }

            analysis = await self._analyze_results(batch_results, original_task, 1)

            return {
                "success": False,
                "result": {
                    "batch_results": batch_results,
                    "analysis": analysis,
                    "success_count": 0,
                    "total_count": len(batch_results),
                },
                "workers": [r.get("worker") for r in batch_results],
                "skill_ids": task_skills,
            }

        elif action_type == "process_results":
            prev_results = []
            for h in reversed(context_history):
                atype = h.get("action_type")
                if atype in ("batch_delegate", "delegate") and h.get("result", {}).get("success"):
                    if atype == "batch_delegate":
                        prev_results = h["result"].get("result", {}).get("batch_results", [])
                    else:
                        prev_results = [h["result"]]
                    break

            if not prev_results:
                return {"success": False, "error": "没有找到可处理的前一轮结果"}

            summaries = []
            for r in prev_results[:5]:
                data = r.get("result", {})
                if isinstance(data, dict):
                    if "batch_results" in data:
                        for br in data["batch_results"][:3]:
                            br_data = br.get("result", {})
                            if isinstance(br_data, dict):
                                c = br_data.get("tool_result_summary", br_data.get("content", ""))
                                if c:
                                    summaries.append(str(c)[:1500])
                    else:
                        cc = data.get("content", "") or ""
                        tc = data.get("tool_result_summary", "") or ""
                        c = cc or tc
                        if c:
                            summaries.append(str(c)[:1500])

            combined = "\n\n---\n\n".join(summaries) if summaries else "无有效结果"

            if len(summaries) > 1 and combined != "无有效结果":
                try:
                    _synth_prompt = (
                        "你是队长Agent。以下是多个Worker的执行结果，请综合分析生成一份连贯、完整的最终报告。\n"
                        "保留所有关键数据和结论，不要遗漏。直接输出报告正文，不要加前言。\n\n"
                        f"任务：{original_task[:200]}\n\n各Worker结果：\n{combined[:8000]}"
                    )
                    _router = get_llm_router_safe()
                    if _router and _router.is_available():
                        _synth_text = await asyncio.wait_for(
                            _router.chat(
                                [{"role": "user", "content": _synth_prompt}],
                                temperature=0.5, max_tokens=4000,
                            ),
                            timeout=60.0,
                        )
                        if _synth_text and len(str(_synth_text)) > 50:
                            combined = str(_synth_text)
                except Exception as _e:
                    logger.debug(f"LLM 合成失败，用拼接结果: {_e}")

            _should_write = (
                "保存到桌面" in original_task or "保存到 ~/Desktop" in original_task
                or "保存到 ~/桌面" in original_task
            )
            if self.tool_registry and _should_write:
                import re as _re
                _path = None
                _name_match = _re.search(
                    r'(?:文件名为?|file_name|filename)\s*[:：]?\s*([\w.\-]+)', original_task)
                if _name_match:
                    _path = f"~/Desktop/{_name_match.group(1)}"
                if not _path:
                    _abs_match = _re.search(r'保存到\s*([~/][\w/.\-]+)', original_task)
                    if _abs_match:
                        _path = _abs_match.group(1)
                if _path:
                    try:
                        _handler = self.tool_registry.get_handler("write_file")
                        if _handler:
                            await _handler({"path": _path, "content": combined})
                            logger.info(f"process_results 自动写入文件: {_path}")
                            combined = f"✅ 报告已保存到 {_path}\n\n{combined[:200]}...\n\n（完整内容见文件）"
                    except Exception as _e:
                        logger.warning(f"自动写文件失败: {_e}")

            return {
                "success": True,
                "result": {"tool_result_summary": combined, "content": combined},
                "worker": self.name,
                "processed_count": len(prev_results),
            }

        else:
            return {"success": False, "error": f"未知的行动类型: {action_type}"}

    async def _decompose_task(self, task_description: str) -> List[str]:
        system = (
            "你是队长Agent。负责将复杂任务分解为多个独立的子任务，每个子任务可以并行执行。\n\n"
            "输出JSON格式:\n"
            f"{OUTPUT_FORMATS['decompose']}"
        )
        user = (f"请将以下任务分解为{self.active_worker_count}个左右的子任务：\n"
                f"{task_description}\n\n注意：不要输出JSON外的其他内容。")

        rag_context = await self._do_rag_query(task_description)
        if rag_context:
            user = (f"请参考知识库信息后，将以下任务分解为{self.active_worker_count}个左右的子任务：\n\n"
                    f"【知识库参考】\n{rag_context}\n\n【原始任务】\n{task_description}\n\n"
                    f"注意：不要输出JSON外的其他内容。")

        result = await llm_json(system, user, max_tokens=800)
        raw_subtasks = result.get("subtasks", [])
        subtasks = [s for s in raw_subtasks if isinstance(s, str)]
        if len(raw_subtasks) != len(subtasks):
            logger.debug(f"_decompose_task: 过滤了 {len(raw_subtasks) - len(subtasks)} 个非字符串子任务")
        if not subtasks:
            return [task_description]

        return subtasks[:self.max_workers]

    def _assign(self, tasks: List[str], active_workers: List[LLMAgent]) -> List[Dict]:
        assignments = []
        for i, task in enumerate(tasks):
            worker = active_workers[i % len(active_workers)]
            assignments.append({"worker": worker, "task": task, "index": i})
        return assignments

    async def _execute_batch(self, assignments: List[Dict],
                              all_workers: List[LLMAgent]) -> List[Dict]:
        async def _run_one(assignment: Dict) -> Dict:
            worker = assignment["worker"]
            task_content = assignment["task"]

            msg = AgentMessage(from_agent=self.name, content=task_content, message_type="task")
            result_str = await worker.process_message(msg)
            try:
                data = json.loads(result_str)
                is_ok = data.get("success", True) is True and data.get("status") != "failed"
            except Exception as e:
                data = {"raw": result_str[:200], "error": str(e)}
                is_ok = False

            return {
                "worker": worker.name, "task": task_content,
                "success": is_ok, "result": data,
            }

        batch = await asyncio.gather(*[_run_one(a) for a in assignments], return_exceptions=True)
        results = []
        for item in batch:
            if isinstance(item, Exception):
                results.append({
                    "success": False, "error": str(item),
                    "worker": "unknown", "task": "",
                    "result": {"error": str(item)}
                })
            else:
                results.append(item)

        return results

    async def _analyze_results(self, batch_results: List[Dict], original_task: str,
                                round_num: int) -> Dict:
        summary_lines = []
        for r in batch_results:
            status = "✅" if r.get("success", False) else "❌"
            summary_lines.append(
                f"{status} Worker {r.get('worker', '?')}: "
                f"{json.dumps(r.get('result', {}), ensure_ascii=False)[:500]}"
            )

        system = (
            "你是队长Agent。你的职责是分析队员(Worker)的执行结果。\n\n"
            "输出JSON:\n"
            f"{OUTPUT_FORMATS['leader_analyze']}\n\n"
            "decision 含义：\n"
            "- complete: 所有结果满意，任务完成\n"
            "- retry: 部分结果不满意，需要重试（在 retry_tasks 中列出需要重试的任务）\n"
            "- reassign: 需要更多 Worker 并重试部分任务"
        )
        user = (
            f"原始任务: {original_task}\n"
            f"第 {round_num} 轮执行结果:\n"
            + "\n".join(summary_lines)
        )

        result = await llm_json(system, user, max_tokens=500)

        if not result:
            return {"decision": "retry", "confidence": 0.0, "reason": "LLM 分析失败，保守重试"}

        return result


# ════════════════════════════════════════════════════════════════
# V1LeaderPool — 队长模式 Agent 池
# ════════════════════════════════════════════════════════════════

class V1LeaderPool:
    """队长模式 Agent 池 — 1 个队长 + 最多 max_workers 个 Worker（支持池化复用）"""

    def __init__(self):
        self._all_agents: Dict[str, LLMAgent] = {}
        self._tool_registry = None
        self._worker_pool: Dict[str, List[LLMAgent]] = {}
        self._busy_workers: Dict[str, LLMAgent] = {}
        self._pool_lock = asyncio.Lock()
        self._agent_configs: Dict[str, dict] = {}

    def _load_agent_configs(self):
        if self._agent_configs:
            return
        try:
            from core.engine.config_loader import register_agents_from_config
            for cfg in register_agents_from_config():
                self._agent_configs[cfg["id"]] = cfg
        except Exception as e:
            logger.error("加载 agents.yml 配置失败，Worker 将使用默认配置: %s", e)

    async def _ensure_tool_registry(self):
        if self._tool_registry is None:
            try:
                from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
                self._tool_registry = V1ToolRegistry()
                await self._tool_registry.discover_all()
                for agent in self._all_agents.values():
                    if agent.tool_registry is None:
                        agent.tool_registry = self._tool_registry
            except Exception as e:
                logger.warning(f"初始化工具注册表失败: {e}")
                self._tool_registry = None

    async def create_team(self, worker_count: int = 3, max_workers: int = 5) -> tuple:
        await self._ensure_tool_registry()
        self._load_agent_configs()
        team_id = uuid4().hex[:8]
        leader = LeaderAgent(
            name=f"队长_{team_id}",
            max_workers=max_workers,
            tool_registry=self._tool_registry,
        )
        self._all_agents[leader.name] = leader

        workers = []
        for i in range(max_workers):
            w = LLMAgent(
                name=f"队员{i+1}_{team_id}",
                role=AgentRole.WORKER,
                tool_registry=self._tool_registry,
            )
            self._all_agents[w.name] = w
            workers.append(w)

        leader.workers = {w.name: w for w in workers}
        leader.active_worker_count = min(worker_count, max_workers)

        logger.info(f"创建队伍: 1 队长 + {worker_count}/{max_workers} Worker (队长={leader.name})")
        return leader, workers

    async def get_worker(self, skill_id: str = "general",
                          leader_name: str = None) -> Optional[LLMAgent]:
        await self._ensure_tool_registry()
        self._load_agent_configs()
        async with self._pool_lock:
            if skill_id not in self._worker_pool:
                self._worker_pool[skill_id] = []

            if self._worker_pool[skill_id]:
                worker = self._worker_pool[skill_id].pop()
                worker._update_state("idle", "从池中取出")
                if leader_name:
                    worker.leader_name = leader_name
                self._busy_workers[worker.name] = worker
                logger.debug(f"从池中取出 Worker: {worker.name}")
                return worker

            total_workers = (sum(len(v) for v in self._worker_pool.values())
                             + len(self._busy_workers))
            if total_workers < 10:
                config = self._agent_configs.get(skill_id, {})
                worker = LLMAgent(
                    name=f"队员_{skill_id}_{uuid4().hex[:6]}",
                    role=AgentRole.WORKER,
                    role_prompt=config.get("role_prompt", ""),
                    tool_restrictions=None,
                    tool_registry=self._tool_registry,
                )
                worker.skill_id = skill_id
                if leader_name:
                    worker.leader_name = leader_name

                self._all_agents[worker.name] = worker
                self._busy_workers[worker.name] = worker
                logger.debug(f"创建新 Worker: {worker.name} (skill={skill_id})")
                return worker

            logger.warning("Worker池已满(%d)，无法获取更多Worker", total_workers)
            return None

    async def return_worker(self, worker: LLMAgent) -> None:
        async with self._pool_lock:
            self._busy_workers.pop(worker.name, None)
            worker._update_state("idle", "任务完成归还池")
            worker.current_task = None
            worker.last_result = None

            skill_id = getattr(worker, 'skill_id', "general")
            if skill_id not in self._worker_pool:
                self._worker_pool[skill_id] = []

            if worker not in self._worker_pool[skill_id]:
                self._worker_pool[skill_id].append(worker)
                logger.debug(f"Worker 归还池: {worker.name} (skill={skill_id})")

    async def discard(self, agents: List[LLMAgent]) -> None:
        for agent in agents:
            if agent.role == AgentRole.LEADER:
                self._all_agents.pop(agent.name, None)
                logger.debug(f"V1LeaderPool: 清理 Leader {agent.name}")
            else:
                await self.return_worker(agent)

    def get_agent(self, name: str) -> Optional[LLMAgent]:
        return self._all_agents.get(name)

    def get_all_agents(self) -> List[LLMAgent]:
        return list(self._all_agents.values())

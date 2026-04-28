"""任务规划器（工业级）

双路径策略：
1. 规则快速路径 process_task() — 正则拆分 + SkillDispatcher 匹配
2. GLM 慢速路径 process_task_with_glm() — 调用 LLM 分解复杂任务
"""
import json
import re
import logging
import threading
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── 多步分隔词 ──────────────────────────────────────────────────────────────
_STEP_SEPARATORS = ["先", "然后", "接着", "再", "最后", "之后", "，然后", "，再"]

# ─── 任务持久化目录 ──────────────────────────────────────────────────────────
TASK_DIR = Path(__file__).parent.parent / "tasks"
TASK_DIR.mkdir(exist_ok=True)


class TaskPlanner:
    """任务分解器 — 规则优先 + GLM 兜底"""

    def __init__(self):
        self._task_counter = 0
        self._counter_lock = threading.Lock()
        self._output_dir = TASK_DIR

        # GLM 系统提示
        self._system_prompt = (
            "你是AI Agent任务分解引擎，将用户自然语言转化为工具调用JSON数组。\n\n"
            "# 可用工具清单\n"
            "- weather: 天气查询 (参数: city)\n"
            "- web_scraper: 网站爬取 (参数: site_name, action)\n"
            "- data_analysis: 数据分析与可视化 (参数: action)\n"
            "- gui_automation: GUI自动化操作 (参数: action, app/text/url)\n"
            "- translator: 翻译 (参数: text, target_lang)\n"
            "- rag_search: 智能搜索 (参数: query)\n"
            "- system_toolbox: 系统工具 (参数: action)\n"
            "- chat: 闲聊对话 (参数: message)\n\n"
            "# 输出格式\n"
            "返回JSON数组，每项包含:\n"
            '{"user_id":1,"user_message":"原文","ai_response":"操作描述",'
            '"tool_call":{"name":"工具名","params":{}}}\n\n'
            "# 规则\n"
            "1. 优先匹配具体工具\n"
            "2. 多步任务拆分为多个独立项\n"
            "3. 闲聊用chat工具\n"
            "4. 仅返回JSON数组，无其他文字"
        )

    # ── 公开 API ─────────────────────────────────────────────────────────────

    def process_task(self, task: Dict[str, Any], user_id: int = 1,
                     skill_name: str = None) -> List[Dict[str, Any]]:
        """处理任务（规则快速路径）

        策略：
        1. 已匹配到非 chat/multi_step 的技能 → 单步直通
        2. 消息含多步分隔词 → 规则拆分
        3. 否则原样返回
        """
        with self._counter_lock:
            self._task_counter += 1

        task["task_id"] = self._task_counter
        task["user_id"] = user_id
        task["timestamp"] = datetime.now().isoformat()

        # 已识别具体技能 → 单步直通
        if skill_name and skill_name not in ("chat", "multi_step"):
            logger.info("单步直通: skill=%s", skill_name)
            return self._execute_simple_task(task)

        # 尝试规则拆分
        if self._can_rule_decompose(task.get("user_message", "")):
            logger.info("规则拆分多步任务: %s", task.get("user_message", "")[:50])
            return self._rule_decompose(task)

        return [task]

    async def process_task_with_glm(self, task: Dict[str, Any],
                                     user_id: int = 1) -> List[Dict[str, Any]]:
        """使用 GLM 分解任务（慢速路径）

        当规则拆分无法覆盖时，调用 LLM 进行智能分解。
        """
        try:
            from core.llm_backend import get_llm_router

            router = get_llm_router()

            if not router.is_available():
                logger.warning("GLM 不可用，回退到规则分解")
                return self.process_task(task, user_id)

            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": f"用户消息: {task['user_message']}"},
            ]

            content = await router.chat(messages)
            decomposed = self._parse_glm_response(content, task, user_id)

            if decomposed:
                self._save_tasks(decomposed)
                return decomposed

            # GLM 解析失败，回退
            return [task]

        except Exception as e:
            logger.error("GLM 分解失败: %s", e)
            return [task]

    # ── 内部方法 ─────────────────────────────────────────────────────────────

    def _can_rule_decompose(self, message: str) -> bool:
        """判断消息是否包含多步分隔词"""
        return any(sep in message for sep in _STEP_SEPARATORS)

    def _rule_decompose(self, task: Dict) -> List[Dict]:
        """基于规则的正则拆分多步任务

        分隔词：先/然后/接着/再/最后/之后/，然后/，再
        每个子任务独立匹配 skill + 提取 params
        """
        message = task["user_message"]
        sub_tasks: List[Dict] = []

        # 按分隔词拆分
        parts = re.split(r"(先|然后|接着|再|最后|之后|，然后|，再)", message)

        for part in parts:
            part = part.strip()
            if not part or part in _STEP_SEPARATORS:
                continue

            # 每个子任务独立匹配技能
            from core.skill_dispatcher import SkillDispatcher

            dispatcher = SkillDispatcher()
            skill = dispatcher.match_skill(part)
            params = dispatcher.extract_params(part, skill)

            sub_task = {
                "task_id": task["task_id"] * 100 + len(sub_tasks) + 1,
                "user_id": task["user_id"],
                "user_message": part,
                "ai_response": f"执行: {part}",
                "tool_call": {"name": skill, "params": params},
                "status": "pending",
                "timestamp": datetime.now().isoformat(),
            }
            sub_tasks.append(sub_task)

        if not sub_tasks:
            return [task]

        self._save_tasks(sub_tasks)
        return sub_tasks

    def _execute_simple_task(self, task: Dict) -> List[Dict]:
        """单步任务直通"""
        return [task]

    def _parse_glm_response(self, content: str, original_task: Dict,
                            user_id: int) -> Optional[List[Dict]]:
        """解析 GLM 返回的 JSON 数组"""
        try:
            content = content.strip()

            # 去掉 markdown 代码块标记
            if content.startswith("```"):
                content = re.sub(r"```\w*\n?", "", content).strip()
                content = content.rstrip("`").strip()

            parsed = json.loads(content)

            if not isinstance(parsed, list):
                parsed = [parsed]

            tasks: List[Dict] = []
            base_id = original_task.get("task_id", 1)

            for i, item in enumerate(parsed):
                task = {
                    "task_id": base_id * 100 + i + 1,
                    "user_id": user_id,
                    "user_message": item.get("user_message", original_task["user_message"]),
                    "ai_response": item.get("ai_response", ""),
                    "tool_call": item.get("tool_call", {"name": "chat", "params": {}}),
                    "status": "pending",
                    "timestamp": datetime.now().isoformat(),
                }
                tasks.append(task)

            logger.info("GLM 分解为 %d 个子任务", len(tasks))
            return tasks

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error("GLM 返回 JSON 解析失败: %s", e)
            return None

    def _save_tasks(self, tasks: List[Dict]):
        """持久化分解后的任务到 JSON 文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self._output_dir / f"tasks_{timestamp}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=2)
            logger.debug("任务已持久化: %s", filepath)
        except Exception as e:
            logger.error("任务保存失败: %s", e)

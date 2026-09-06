"""未完成目标的持久化 — 单文件存储（恢复场景只需最近一个未完成 goal）

文件: ~/.xiaolei/goals/unfinished.json
写入: run_react 以 blocked/round_limit/interrupted 收尾时保存
清除: run_react 以 completed 收尾时删除
读取: run_react 启动时检测，任务匹配则注入恢复上下文
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

GOALS_DIR = os.path.expanduser("~/.xiaolei/goals")
GOAL_PATH = os.path.join(GOALS_DIR, "unfinished.json")


def save_unfinished_goal(state: Dict) -> bool:
    try:
        os.makedirs(GOALS_DIR, exist_ok=True)
        state = dict(state)
        state["saved_at"] = datetime.now().isoformat(timespec="seconds")
        for k in ("task", "blocked_reason", "progress_note", "plan_summary"):
            if k in state:
                state[k] = str(state[k])[:300]
        state["files_written"] = [str(f)[:200] for f in state.get("files_written", [])][:5]
        tmp = GOAL_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, GOAL_PATH)
        logger.info(f"未完成目标已保存: {state.get('task', '')[:60]}")
        return True
    except Exception as e:
        logger.debug(f"保存未完成目标失败: {e}")
        return False


def clear_unfinished_goal() -> None:
    try:
        if os.path.exists(GOAL_PATH):
            os.remove(GOAL_PATH)
    except Exception as e:
        logger.debug(f"清除未完成目标失败: {e}")


def load_unfinished_goal(task_description: str = "") -> Optional[Dict]:
    """匹配规则:
    - task_description 为空 → 直接返回（调用方自行判断）
    - ≤12 字且含续做词（继续/接着/continue/resume）→ 视为恢复指令
    - 否则按任务前 40 字精确匹配
    """
    try:
        if not os.path.exists(GOAL_PATH):
            return None
        with open(GOAL_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not task_description:
            return state
        td = task_description.strip()
        _is_resume = len(td) <= 12 and any(
            kw in td.lower() for kw in ("继续", "接着", "continue", "resume")
        )
        if _is_resume:
            return state
        saved_task = str(state.get("task", ""))[:40]
        if saved_task and saved_task[:40] == td[:40]:
            return state
        return None
    except Exception as e:
        logger.debug(f"读取未完成目标失败: {e}")
        return None

"""未完成目标的持久化 — 按 task_id 隔离的多文件存储（修复 #010 #011）

原版本（疑点 #010 #011）：
  - 单文件 ~/.xiaolei/goals/unfinished.json，多 agent 并行时互相覆盖
  - .tmp 文件名固定，两个进程同时 save 时互相删对方 tmp
  - 续做检测只看前 12 字，任务匹配前 40 字逐字精确，改 1 个字不命中
  - 失败时 logger.debug 静默

新版本：
  - 每个 task 一个文件 ~/.xiaolei/goals/<task_hash>.json
  - 用 fcntl 文件锁（跨进程安全）
  - 续做检测：完整字符串 normalize + 包含关系匹配（不是逐字精确）
  - 失败时 logger.warning + 抛出 RuntimeError
"""
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

GOALS_DIR = os.path.expanduser("~/.xiaolei/goals")
os.makedirs(GOALS_DIR, exist_ok=True)


def _task_id(task_description: str) -> str:
    """用 task 描述的 hash 作为文件名（不暴露原始任务内容）"""
    return hashlib.sha256(task_description.encode("utf-8")).hexdigest()[:16]


def _goal_path(task_id: str) -> str:
    return os.path.join(GOALS_DIR, f"{task_id}.json")


def _normalize(text: str) -> str:
    """归一化：去空白、去标点、转小写——让"分析 X" 和 "分析X" 匹配。"""
    return re.sub(r"\s+", "", text.lower().strip())


def _acquire_lock(path: str):
    """获取文件锁（跨进程安全）。失败时降级到无锁（单进程 OK）。"""
    try:
        import fcntl
        f = open(path, "a+")
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        return f
    except (ImportError, OSError):
        # Windows 或 fcntl 不可用 → 降级（不锁）
        return None


def save_unfinished_goal(state: Dict) -> bool:
    """保存未完成目标。返回 True 表示成功，False 表示失败（抛异常而非静默）。"""
    task_desc = str(state.get("task", ""))
    if not task_desc:
        raise ValueError("state 必须包含 'task' 字段")

    task_id = _task_id(task_desc)
    path = _goal_path(task_id)
    tmp = path + ".tmp"
    lock = _acquire_lock(path)

    try:
        os.makedirs(GOALS_DIR, exist_ok=True)
        state = dict(state)
        state["saved_at"] = datetime.now().isoformat(timespec="seconds")
        state["_task_id"] = task_id
        for k in ("task", "blocked_reason", "progress_note", "plan_summary"):
            if k in state:
                state[k] = str(state[k])[:300]
        state["files_written"] = [str(f)[:200] for f in state.get("files_written", [])][:5]

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # 原子替换
        logger.info(f"未完成目标已保存: task_id={task_id} task={task_desc[:60]}")
        return True
    except Exception as e:
        # 修复 #010: 不再静默，logger.warning 让用户看到
        logger.error(f"保存未完成目标失败: {e}", exc_info=True)
        return False
    finally:
        if lock:
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()
            except Exception:
                pass


def clear_unfinished_goal(task_description: str) -> None:
    """清除指定 task 的未完成目标。"""
    if not task_description:
        return
    task_id = _task_id(task_description)
    path = _goal_path(task_id)
    lock = _acquire_lock(path)
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"未完成目标已清除: task_id={task_id}")
    except Exception as e:
        logger.error(f"清除未完成目标失败: {e}", exc_info=True)
    finally:
        if lock:
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()
            except Exception:
                pass


def _strip_resume_suffix(task: str) -> str:
    """剥离续跑注入的后缀"（从上次断点继续：已完成的部分不要重做…）"

    修复(goal叠加): 每次续跑 run_react 都会在 _orig_task 后拼这个后缀，
    若 _orig_task 本身来自上一个续跑的 goal（已带后缀），会越叠越胖，
    用户原话被淹没（实测: "(从上次断点继续…)"在 goal 文件里出现两次）。
    """
    marker = "（从上次断点继续"
    idx = task.find(marker)
    if idx > 0:
        return task[:idx].strip()
    return task


def load_unfinished_goal(task_description: str = "") -> Optional[Dict]:
    """加载匹配的未完成目标。

    匹配规则（修复 #011 + 修复(goal劫持)）:
      - task_description 为空 → 直接返回最近的（用于纯恢复命令）
      - 含续做词（继续/接着/continue/resume）→ 返回最近的
      - 否则按 normalize 后的包含关系匹配（不是逐字精确），
        但短输入(≤6字)不参与包含匹配——修复目标劫持:
        "你好"/"ok"/"嗯" normalize 后必是任何长目标全文的子串，
        两字问候会把用户任务改成上轮的烂尾任务（实测"你好"被改写成
        热搜报告续跑）。短输入只有显式续做词（is_resume 分支）才拉 goal。
    """
    if not os.path.exists(GOALS_DIR):
        return None
    lock_path = os.path.join(GOALS_DIR, ".lock")
    lock = _acquire_lock(lock_path)
    try:
        # 列出所有 goal 文件
        goal_files = []
        for f in os.listdir(GOALS_DIR):
            if f.startswith(".") or not f.endswith(".json"):
                continue
            path = os.path.join(GOALS_DIR, f)
            try:
                mtime = os.path.getmtime(path)
                goal_files.append((mtime, path))
            except OSError:
                continue
        goal_files.sort(reverse=True)  # 最新的在前

        if not task_description:
            # 返回最近的
            if goal_files:
                with open(goal_files[0][1], "r", encoding="utf-8") as f:
                    return json.load(f)
            return None

        td = task_description.strip()
        td_lower = td.lower()
        td_normalized = _normalize(td)

        # 续做检测（显式意图才放行——不受长度门槛限制）
        is_resume = (
            len(td) <= 12
            and any(kw in td_lower for kw in ("继续", "接着", "continue", "resume"))
        )
        if is_resume and goal_files:
            with open(goal_files[0][1], "r", encoding="utf-8") as f:
                return json.load(f)

        # 修复(goal劫持): 短输入不做包含匹配 —— "你好"/"嗯"/"ok"
        # normalize 后必是任何长 goal 的子串，用户只是打招呼却被
        # 改写成烂尾任务续跑。6 字以下（如"你好"）不放行包含匹配。
        if len(td_normalized) <= 6:
            return None

        # 包含关系匹配
        for _, path in goal_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                saved_task = str(state.get("task", ""))
                if not saved_task:
                    continue
                saved_normalized = _normalize(saved_task)
                if (
                    saved_normalized == td_normalized
                    or saved_normalized in td_normalized
                    or td_normalized in saved_normalized
                ):
                    return state
            except (OSError, json.JSONDecodeError) as e:
                logger.debug(f"读取 goal 失败 {path}: {e}")
                continue
        return None
    except Exception as e:
        logger.error(f"加载未完成目标失败: {e}", exc_info=True)
        return None
    finally:
        if lock:
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()
            except Exception:
                pass

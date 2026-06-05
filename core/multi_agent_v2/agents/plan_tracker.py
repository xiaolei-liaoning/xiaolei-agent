"""
PlanTracker — 执行计划追踪器

让 Agent 能：
1. 执行前先列计划（Plan）
2. 执行中知道自己到了哪一步（Track）
3. 执行后根据结果动态调整（Adapt）

集成到 MiddlewareChain 中，通过 ctx.plan_state 访问。
每轮 ReAct 自动注入进度到 prompt，让 LLM 始终知道做了什么/还剩什么。
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

# ── LLM 计划创建提示词 ──────────────────────────────────────────
PLAN_CREATION_PROMPT = """你是一个任务规划师。请将用户的任务拆解为 2-5 个具体可执行的步骤。

可用工具（选择最匹配的）：
- search: 联网搜索（百度/谷歌/Bing）
- fetch_url: 获取网页内容
- file: 读写文件（action=read|write, path=文件路径, content=写入内容）
- execute_python: 执行 Python 代码
- execute_shell: 执行 Shell 命令
- call_api: HTTP 请求（GET/POST/PUT/DELETE）

JSON 输出格式：
{"steps": [
  {"id":"step_1","name":"步骤名","description":"具体做什么"},
  {"id":"step_2","name":"步骤名","description":"具体做什么"}
]}

原则：
1. 步骤必须具体且有可验证的产出（如"搜索百度热搜"而非"准备搜索"）
2. 每步要对应一个可用的工具操作（搜索→search, 写文件→file, 爬网页→fetch_url, 分析→execute_python）
3. 不要"打开浏览器/初始化环境/分析需求"等空洞步骤
4. 如果任务要"保存到桌面"或"生成报告"，最后一步必须是 **用 file 工具将结果写入桌面文件**，如 {"id":"step_N","name":"保存报告到桌面","description":"调用 file 工具写入 /Users/leiyuxuan/Desktop/xxx.txt"}

只输出 JSON，不要其他文字。"""


# ═══════════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════════

@dataclass
class StepRecord:
    """单个步骤记录"""
    id: str
    name: str
    description: str
    status: str = "pending"        # pending | in_progress | completed | failed
    result: Optional[str] = None   # 执行结果摘要
    error: Optional[str] = None    # 错误信息


@dataclass
class PlanState:
    """完整计划状态 — 在 MiddlewareChain 的 ctx 中传递"""
    steps: List[StepRecord] = field(default_factory=list)
    current_idx: int = 0
    round_count: int = 0
    created: bool = False          # 计划是否已创建
    last_status: str = ""          # 上次注入的状态文本（用于去重替换）

    # ── 当前步骤 ──

    def current(self) -> Optional[StepRecord]:
        """返回当前正在执行的步骤（或 None）"""
        if 0 <= self.current_idx < len(self.steps):
            return self.steps[self.current_idx]
        return None

    def begin_current(self):
        """将当前步骤标记为 in_progress"""
        cur = self.current()
        if cur and cur.status == "pending":
            cur.status = "in_progress"

    def finish_current(self, result: str = "") -> bool:
        """完成当前步骤，移动到下一步。
        Returns: 是否确实完成了一个步骤
        """
        cur = self.current()
        if cur:
            cur.status = "completed"
            cur.result = result[:200] if result else "完成"
            self.current_idx += 1
            return True
        return False

    def fail_current(self, error: str = ""):
        """当前步骤失败，跳过到下一步"""
        cur = self.current()
        if cur:
            cur.status = "failed"
            cur.error = error[:200] if error else "执行失败"
            self.current_idx += 1

    def skip_current(self, reason: str = ""):
        """跳过当前步骤（标记为 skipped）"""
        cur = self.current()
        if cur:
            cur.status = "skipped"
            cur.error = reason[:200] if reason else "跳过"
            self.current_idx += 1

    # ── 状态查询 ──

    def done(self) -> bool:
        """所有步骤已处理完毕（不论成功/失败/跳过）"""
        return self.current_idx >= len(self.steps)

    def all_ok(self) -> bool:
        """所有步骤全部完成（无失败/跳过）"""
        return len(self.steps) > 0 and all(s.status == "completed" for s in self.steps)

    def progress(self) -> str:
        """返回 '3/5' 格式的进度字符串"""
        done = sum(1 for s in self.steps if s.status == "completed")
        return f"{done}/{len(self.steps)}"

    # ── Prompt 生成 ──

    def status_prompt(self) -> str:
        """生成执行状态文本 — 注入到下一轮 LLM prompt

        Agent 通过这段文本知道自己做了什么 / 还剩什么。
        """
        if not self.steps:
            return ""

        lines = [
            "",
            "─" * 48,
            "📋 执行状态（知道做了什么，也知道还剩什么）",
            "─" * 48,
        ]
        for s in self.steps:
            icon = {
                "completed": "✅", "in_progress": "🔄",
                "failed": "❌", "skipped": "⏭️",
                "pending": "  ○",
            }.get(s.status, "  ○")
            label = f"{icon} [{s.id}] {s.name}"
            if s.status == "completed" and s.result:
                label += f" → {s.result[:60]}"
            if s.status == "failed" and s.error:
                label += f" ({s.error[:60]})"
            lines.append(label)

        # 🧭 下一步指引
        cur = self.current()
        if cur and cur.status == "in_progress":
            lines.append(f"  🧭 下一步：继续执行 [{cur.id}] {cur.name}")
            lines.append(f"     目标：{cur.description}")
        elif cur:
            lines.append(f"  🧭 下一步：开始 [{cur.id}] {cur.name}")
            lines.append(f"     目标：{cur.description}")
        else:
            pass  # 没有剩余步骤

        lines.append(f"  📊 进度：{self.progress()}（共 {len(self.steps)} 步）")
        lines.append("─" * 48)

        return "\n".join(lines)

    def plan_prompt_block(self) -> str:
        """生成初始计划摘要文本 — 注入到 task_description 开头"""
        if not self.steps:
            return ""
        lines = ["╔══════════════════════════════════════════",
                 "║  📋 执行计划（共 %d 步）" % len(self.steps),
                 "╠" + "═" * 38]
        for i, s in enumerate(self.steps, 1):
            lines.append(f"║  {i}. {s.name}")
            lines.append(f"║     {s.description[:50]}")
        lines.append("╚══════════════════════════════════════════")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "steps": [{"id": s.id, "name": s.name, "status": s.status} for s in self.steps],
            "current_idx": self.current_idx,
            "progress": self.progress(),
            "done": self.done(),
        }


# ═══════════════════════════════════════════════════════════════════
# 计划解析工具
# ═══════════════════════════════════════════════════════════════════

def parse_plan_from_llm(text: str, ps: PlanState) -> bool:
    """从 LLM 返回文本中解析计划，填充到 PlanState

    Returns: 是否成功解析
    """
    # 1. 尝试 JSON 格式
    m = re.search(r'\{[^{}]*"steps"[^{}]*\}', text, re.DOTALL)
    if not m:
        m = re.search(r'(\{.*\})', text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            steps_data = data if isinstance(data, list) else data.get("steps", [])
            for sd in steps_data:
                ps.steps.append(StepRecord(
                    id=sd.get("id", f"step_{len(ps.steps) + 1}"),
                    name=sd.get("name", sd.get("title", "")),
                    description=sd.get("description", sd.get("desc", "")),
                ))
            if ps.steps:
                ps.created = True
                return True
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass

    # 2. 尝试文本行解析（编号列表）
    lines = text.split("\n")
    plan_lines = []
    in_plan = False
    for line in lines:
        stripped = line.strip()
        # 检测计划引出行
        if any(kw in stripped for kw in ["计划", "步骤", "plan", "step", "方案"]):
            in_plan = True
            continue
        if not in_plan:
            # 如果发现编号行，也认为进入了计划区域
            if re.match(r'^\s*[\d]+[.、\)]\s', stripped):
                in_plan = True
            else:
                continue
        if not stripped:
            continue
        # 清理行
        cleaned = re.sub(r'^[\d]+[.、\)]\s*', '', stripped)
        cleaned = re.sub(r'^[-*]\s*', '', cleaned)
        cleaned = re.sub(r'^【.*?】', '', cleaned)
        if cleaned and len(cleaned) > 3:
            plan_lines.append(cleaned)

    if len(plan_lines) >= 2:
        for i, pl in enumerate(plan_lines):
            ps.steps.append(StepRecord(
                id=f"step_{i + 1}",
                name=pl[:40],
                description=pl,
            ))
        ps.created = True
        return True

    return False

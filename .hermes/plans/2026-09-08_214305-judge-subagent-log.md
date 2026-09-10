# 日志判读：准确区分 task 与 orchestrate 子代理

## Goal

写一个可运行脚本，能从任意 CLI 日志文本里**准确数出** `◆ task` 与 `◆ orchestrate` 各出现几次、`[子代理]` 块各多少，从而让任何人一眼判定"这次子代理是单发（task）还是并行（orchestrate）"，并把判读规则固化成一键复用的工具，回答"`[子代理]` 到底是不是 task"。

## Current context / assumptions

- 项目路径：`/Users/leiyuxuan/Desktop/小雷版agent_副本`（git 分支 `v1-architecture-fix`）。
- 已用只读追踪确认的代码事实：
  - `◆ task` 工具 handler = `_handle_task`（`core/multi_agent_v2/tools/tool_registry.py:1615`）→ 调 `spawn_subagent`（**单发**一个子代理）。日志行形态：`◆ task  ·  description=改写为计算器, prompt=...`。
  - `◆ orchestrate` 工具 handler = `_handle_orchestrate`（`tool_registry.py:1642`）→ 调 `orchestrate_subagents`（`spawn.py:390`）→ 内部对每个 DAG 任务再调 `spawn_subagent`（`spawn.py:453`），**并行**发多个子代理。日志行形态：`◆ orchestrate  ·  tasks=[{'id': 'arch', ...}]`（tasks 是数组）。
  - `[子代理]` 前缀来自 `spawn.py:65` 的 `_tag="子代理"`（`_drain_print_queue`），对**任何**经 `spawn_subagent` 产生的输出统一加前缀 → **与 task/orchestrate 无关**。
  - react_core 的 `_get_prefix`（`react_core.py:87-95`）在子代理路径因 `run_react` 未传 `agent=`（`spawn.py:213`）而返回空串，**不会**打 `[子代理]` 前缀。
- 因此正确判读依据是**日志行开头的工具名**（`◆ task` vs `◆ orchestrate`），**不是** `[子代理]` 块。

## Architecture / proposed approach

不修改任何引擎逻辑。交付两个产物：
1. `scripts/judge_subagent.py` — 读取 CLI 日志文本/文件，用正则统计 `◆ task`、`◆ orchestrate`、`[子代理]` 出现次数，并输出判读结论。
2. `docs/subagent-log-reading.md` — 把判读规则与代码证据（文件:行号）写清楚，附你贴的两个日志实例的判定结果。

核心判读规则：
- 有 `◆ task` → 单发子代理（每次一个）。
- 有 `◆ orchestrate` → 并行多子代理（一次 tasks 数组多个）。
- `[子代理]` 只说明"有子代理执行"，不说明工具名。

## Step-by-step tasks

全部为新增脚本/文档，不触碰现有逻辑代码。

### Task 1 — 写判读脚本

新建 `scripts/judge_subagent.py`：

```python
#!/usr/bin/env python3
"""从 CLI 日志判定 task / orchestrate / 子代理使用情况。

用法：
  python3 scripts/judge_subagent.py <logfile|logtext>
  echo "◆ task · description=xxx" | python3 scripts/judge_subagent.py -
"""
import re, sys

def judge(text: str) -> dict:
    # ◆ task：单发子代理。形态 "◆ task  ·  description=... , ...  ·  ✓/✗"
    task = re.findall(r"◆\s*task\s*·", text)
    # ◆ orchestrate：并行多子代理。形态 "◆ orchestrate  ·  tasks=[{'id': ..."
    orch = re.findall(r"◆\s*orchestrate\s*·", text)
    # [子代理] 块前缀：说明有子代理执行（不区分工具）
    sub = re.findall(r"\[子代理\]", text)
    return {"task": len(task), "orchestrate": len(orch), "subagent_blocks": len(sub)}

def report(text: str) -> str:
    r = judge(text)
    lines = [
        f"◆ task 调用次数        : {r['task']}   (每次 = 单发一个子代理)",
        f"◆ orchestrate 调用次数 : {r['orchestrate']}  (每次 = tasks 数组并行多个子代理)",
        f"[子代理] 前缀块个数     : {r['subagent_blocks']}  (只说明有子代理，不区分工具)",
    ]
    verdict = []
    if r["task"]:
        verdict.append("检测到单发子代理(task)")
    if r["orchestrate"]:
        verdict.append("检测到并行编排(orchestrate)")
    if not verdict:
        verdict.append("本次未调用子代理工具")
    lines.append("结论: " + " + ".join(verdict))
    return "\n".join(lines)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
            print(report(f.read()))
    else:
        print(report(sys.stdin.read()))
```

### Task 2 — 用你贴的两段日志验证脚本

把两段真实日志分别存临时文件，跑脚本，核对输出：

```bash
cd ~/Desktop/小雷版agent_副本 && mkdir -p scripts
# 片段A：计算器任务（应判出 task=1, orchestrate=0）
cat > /tmp/calc.log <<'EOF'
◆ read_file  ·  path=...  ·  ✓
◆ task  ·  description=改写为计算器, prompt=请把文件 ...  ·  ✓
◆ execute_shell  ·  command=cd ...  ·  ✓
EOF
# 片段B：EverOS 分析（应判出 orchestrate=3, task=0）
cat > /tmp/everos.log <<'EOF'
◆ read_file  ·  path=...  ·  ✓
◆ orchestrate  ·  tasks=[{'id': 'arch', 'description': ...  ·  ✓
◆ orchestrate  ·  tasks=[{'agent': 'analyze', 'descrip ...  ·  ✓
◆ orchestrate  ·  tasks=[{'agent': 'analyze', 'descrip ...  ·  ✓
EOF
echo "== 计算器片段 ==" && ./.venv/bin/python scripts/judge_subagent.py /tmp/calc.log
echo "== EverOS 片段 ==" && ./.venv/bin/python scripts/judge_subagent.py /tmp/everos.log
```

期望输出：
```
== 计算器片段 ==
◆ task 调用次数        : 1   (每次 = 单发一个子代理)
◆ orchestrate 调用次数 : 0  (每次 = tasks 数组并行多个子代理)
[子代理] 前缀块个数     : 0  (只说明有子代理，不区分工具)
结论: 检测到单发子代理(task)

== EverOS 片段 ==
◆ task 调用次数        : 0   ...
◆ orchestrate 调用次数 : 3  ...
[子代理] 前缀块个数     : 0  ...
结论: 检测到并行编排(orchestrate)
```
（片段里没贴 `[子代理]` 行，故该数可为 0；若把 `[子代理]` 行也算进去，则 `subagent_blocks > 0`。以实际片段为准。）

### Task 3 — 写判读文档

新建 `docs/subagent-log-reading.md`，内容：
- 判读规则三点（task=单发 / orchestrate=并行 / [子代理]=仅标识）。
- 代码证据表：`tool_registry.py:1615`（task→spawn_subagent）、`tool_registry.py:1642`（orchestrate→orchestrate_subagents）、`spawn.py:453`（编排内每任务调 spawn_subagent）、`spawn.py:65`（`_tag="子代理"`）。
- 实例：计算器=task(1)、EverOS=orchestrate(3，tasks 数组)。
- 用户常见误读：`[子代理]` 块 ≠ task，必须看 `◆` 行工具名。

### Task 4 — 提交

```bash
cd ~/Desktop/小雷版agent_副本 && git add scripts/judge_subagent.py docs/subagent-log-reading.md && git commit -m "docs/tool: 日志判读 — 区分 task(单发) vs orchestrate(并行) 子代理"
```

## Tests / validation

- Task 2 的运行输出与"期望输出"一致（task=1/orch=0 与 task=0/orch=3）。
- 用真实日志再跑一次确认 `[子代理]` 块也能被统计：把用户给的完整日志存文件后跑脚本，`subagent_blocks` 应为正数。
- 若某个片段匹配不到，说明日志里工具名写法有变（例如缩进/空格），需在 `judge` 正则里容错（`◆\s*task\s*·` 已含 `\s*`）。

## Risks, tradeoffs, and open questions

- **正则依赖日志格式**：若日志渲染改版（如 `◆` 换成别的符号或空格变化），需同步调整 `judge()`。当前正则用 `◆\s*task\s*·` 已容错空格。
- **不改变行为**：本计划只做"判读工具"，不改 task/orchestrate 的运行逻辑。若后续想"让 agent 自动决定单发还是并行"，那是另一任务，不在本范围。
- **待定**：是否要把脚本做成 CLI 内可调用的命令（如 `/judge`），还是仅作独立脚本？本计划先做独立脚本，后续若要集成再扩展。

## Key reference lines (verified this session)

- `core/multi_agent_v2/tools/tool_registry.py:1615` `_handle_task` → `spawn_subagent`（单发）
- `core/multi_agent_v2/tools/tool_registry.py:1642` `_handle_orchestrate` → `orchestrate_subagents`（并行）
- `core/multi_agent_v2/tools/tool_registry.py:1638` task 成功返回 `[子代理 {session_id}] ...`
- `core/multi_agent_v2/agents/subagent/spawn.py:390` `orchestrate_subagents`
- `core/multi_agent_v2/agents/subagent/spawn.py:453` 编排内每 DAG 任务调 `spawn_subagent`
- `core/multi_agent_v2/agents/subagent/spawn.py:65` `_tag = "子代理"`（`[子代理]` 前缀，不区分工具）
- `core/multi_agent_v2/agents/react_core.py:87-95` `_get_prefix`（子代理路径返回空串）

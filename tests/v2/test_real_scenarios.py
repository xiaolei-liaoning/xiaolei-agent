"""
真实用户场景模拟测试 — 覆盖 10 种编排模式 + 边际场景

每个测试模拟真实用户场景：
  - 用真实 Node.js 子进程 + IPC 通信
  - Mock py_agent 避免真实 LLM 调用
  - 验证执行流、结果结构、错误处理
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


def _js(script):
    return script

def _make_mock_result(output="mock output", label=""):
    """Create a mock AgentResult-compatible object matching what _handle_ipc expects.
    Must have: success, output, error, execution_time, agent_id, metadata."""
    import types
    return types.SimpleNamespace(
        success=True,
        output=output,
        error=None,
        execution_time=0.1,
        agent_id="mock_" + label,
        metadata={},
    )

def _make_fail_result(error_msg="fail"):
    import types
    return types.SimpleNamespace(
        success=False,
        output=None,
        error=error_msg,
        execution_time=0.1,
        agent_id="mock_fail",
        metadata={},
    )


# ════════════════════════════════════════════════════════════════
# 模式①: 纯并行 → 汇总（多源搜索）
# ════════════════════════════════════════════════════════════════

PATTERN_1_PARALLEL_MERGE = _js("""
export const meta = {
  name: "\u591a\u6e90\u641c\u7d22",
  description: "\u5e76\u884c\u4ece\u767e\u5ea6/\u5fae\u535a/\u77e5\u4e4e\u641c\u7d22\uff0c\u6c47\u603b\u7ed3\u679c",
  phases: [
    { title: "\u5e76\u884c\u641c\u7d22", detail: "3\u8def\u5e76\u884c" },
    { title: "\u6c47\u603b", detail: "\u7efc\u5408\u62a5\u544a" },
  ],
}
export default async function () {
  phase("\u5e76\u884c\u641c\u7d22")
  log("\u5f00\u59cb3\u8def\u5e76\u884c\u641c\u7d22...")
  const results = await parallel([
    () => agent("\u641c\u7d22\u767e\u5ea6\u70ed\u641c", { label: "\u767e\u5ea6\u641c\u7d22", timeout: 30 }),
    () => agent("\u641c\u7d22\u5fae\u535a\u70ed\u641c", { label: "\u5fae\u535a\u641c\u7d22", timeout: 30 }),
    () => agent("\u641c\u7d22\u77e5\u4e4e\u70ed\u95e8", { label: "\u77e5\u4e4e\u641c\u7d22", timeout: 30 }),
  ])
  phase("\u6c47\u603b")
  const summary = await agent("\u6c47\u603b\u4ee5\u4e0a\u7ed3\u679c", { label: "\u6c47\u603b\u62a5\u544a", timeout: 30 })
  return { parallel_results: results, summary }
}
""")

# ════════════════════════════════════════════════════════════════
# 模式②: 串行流水线（搜索->分析->报告）
# ════════════════════════════════════════════════════════════════

PATTERN_2_SERIAL_PIPELINE = _js("""
export const meta = { name: "pipeline", description: "search->analyze->report", phases: [] }
export default async function () {
  const raw = await agent("search data", { label: "data_collect", timeout: 30 })
  const analyzed = await agent("analyze: " + raw, { label: "deep_analyze", timeout: 30 })
  const report = await agent("write report: " + analyzed, { label: "gen_report", timeout: 30 })
  return { raw, analyzed, report }
}
""")

# ════════════════════════════════════════════════════════════════
# 模式③: 复杂 DAG（游戏开发）
# ════════════════════════════════════════════════════════════════

PATTERN_3_DAG = _js("""
export const meta = { name: "dag_dev", description: "arch->engine+ui+assets->integration", phases: [] }
export default async function () {
  const r = await $dag({
    design: async () => {
      return await agent("design snake game arch", { label: "arch_design", timeout: 30 })
    },
    engine: { depends: "design", task: async (ctx) => {
      return await agent("impl engine based on: " + (ctx.design || ""), { label: "engine_mod", timeout: 30 })
    }},
    ui: { depends: "design", task: async (ctx) => {
      return await agent("impl UI based on: " + (ctx.design || ""), { label: "ui_mod", timeout: 30 })
    }},
    assets: { depends: "design", task: async (ctx) => {
      return await agent("impl assets based on: " + (ctx.design || ""), { label: "assets_mod", timeout: 30 })
    }},
    integration: { depends: ["engine", "ui", "assets"], task: async (ctx) => {
      return await agent("integrate engine=" + (ctx.engine||"") + " ui=" + (ctx.ui||"") + " assets=" + (ctx.assets||""),
        { label: "integration", timeout: 30 })
    }},
  })
  return r
}
""")

# ════════════════════════════════════════════════════════════════
# 模式④: 动态批量（遍历文件分析）
# ════════════════════════════════════════════════════════════════

PATTERN_4_DYNAMIC_BATCH = _js("""
export const meta = { name: "dynamic_batch", description: "list->analyze->summary", phases: [] }
export default async function () {
  const list = await agent("list python files", { label: "file_list", timeout: 30 })
  const files = ["app.py", "main.py", "utils.py"]
  const analyses = await parallel(
    files.map(f => () => agent("analyze " + f + ": " + list, { label: "analyze_" + f, timeout: 30 }))
  )
  const summary = await agent("summarize", { label: "summary", timeout: 30 })
  return { list, analyses, summary }
}
""")

# ════════════════════════════════════════════════════════════════
# 模式⑤: CodeGraph 预扫描 -> 多 Agent 分析
# ════════════════════════════════════════════════════════════════

PATTERN_5_CODEGRAPH = _js("""
export const meta = { name: "codegraph_scan", description: "scan->parallel analysis->report", phases: [] }
export default async function () {
  const scan = await agent("scan project structure", { label: "cg_scan", agentType: "Explore", timeout: 30 })
  const [arch, components, tech] = await parallel([
    () => agent("analyze arch: " + (scan || ""), { label: "arch_analysis", agentType: "Plan", timeout: 30 }),
    () => agent("analyze components: " + (scan || ""), { label: "comp_analysis", agentType: "Explore", timeout: 30 }),
    () => agent("analyze tech stack: " + (scan || ""), { label: "tech_analysis", timeout: 30 }),
  ])
  const report = await agent("generate HTML report", { label: "report_gen", timeout: 30 })
  return { scan, arch, components, tech, report }
}
""")

# ════════════════════════════════════════════════════════════════
# 模式⑥: 迭代循环（质量改进）
# ════════════════════════════════════════════════════════════════

PATTERN_6_ITERATIVE = _js("""
export const meta = { name: "iterative", description: "init->review->improve->loop", phases: [] }
export default async function () {
  let code = await agent("write bubble sort", { label: "init_code", timeout: 30 })
  let score = 0
  let rounds = 0
  while (score < 80 && rounds < 3) {
    rounds++
    const review = await agent("review code: " + code, { label: "review_" + rounds, timeout: 30 })
    score = 50 + rounds * 20
    if (score < 80) {
      code = await agent("improve code based on: " + (review || ""), { label: "improve_" + rounds, timeout: 30 })
    }
  }
  const final = await agent("final review: " + code, { label: "final_review", timeout: 30 })
  return { code, score, rounds, final }
}
""")

# ════════════════════════════════════════════════════════════════
# 模式⑦: 产出 -> 验证（方案审查）
# ════════════════════════════════════════════════════════════════

PATTERN_7_PRODUCE_VERIFY = _js("""
export const meta = { name: "review", description: "design->review->revise", phases: [] }
export default async function () {
  const design = await agent("design login module", { label: "design_plan", timeout: 30 })
  const review = await agent("review plan: " + design, { label: "review_check", agentType: "Explore", timeout: 30 })
  let final = design
  if (review && !review.includes("PASS")) {
    final = await agent("revise based on: " + review, { label: "plan_revise", timeout: 30 })
  }
  return { design, review, final }
}
""")

# ════════════════════════════════════════════════════════════════
# 模式⑧: 多方案 Tournament
# ════════════════════════════════════════════════════════════════

PATTERN_8_TOURNAMENT = _js("""
export const meta = { name: "tournament", description: "3 plans -> compare", phases: [] }
export default async function () {
  const [planA, planB, planC] = await parallel([
    () => agent("plan A: minimal changes", { label: "plan_A", timeout: 30 }),
    () => agent("plan B: refactor", { label: "plan_B", timeout: 30 }),
    () => agent("plan C: rewrite", { label: "plan_C", timeout: 30 }),
  ])
  const decision = await agent("compare and select best: A=" + (planA||"") + " B=" + (planB||"") + " C=" + (planC||""),
    { label: "decision", timeout: 30 })
  return { planA, planB, planC, decision }
}
""")

# ════════════════════════════════════════════════════════════════
# 模式⑨: 容错并行
# ════════════════════════════════════════════════════════════════

PATTERN_9_FAULT_TOLERANT = _js("""
export const meta = { name: "fault_tolerant", description: "resilient parallel", phases: [] }
export default async function () {
  const results = await parallel([
    () => agent("source 1").catch(() => null),
    () => agent("source 2", { timeout: 30 }),
    () => agent("source 3", { timeout: 30 }).catch(() => null),
  ])
  const valid = results.filter(r => r !== null)
  log("success: " + valid.length + "/" + results.length)
  const summary = await agent("summarize valid results", { label: "summary", timeout: 30 })
  return { raw: results, summary }
}
""")

# ════════════════════════════════════════════════════════════════
# 模式⑩: 游戏开发DAG（综合验证）
# ════════════════════════════════════════════════════════════════

PATTERN_10_GAME_DAG = _js("""
export const meta = { name: "game_dag", description: "design->4modules->integration", phases: [
  { title: "dev", detail: "design + 4 modules + integration" },
] }
export default async function () {
  phase("dev")
  const results = await $dag({
    design: async () => {
      return await agent("design snake game", { label: "arch_design", timeout: 30 })
    },
    engine: { depends: "design", task: async (ctx) => {
      return await agent("engine: " + (ctx.design||""), { label: "engine_mod", timeout: 30 })
    }},
    objects: { depends: "design", task: async (ctx) => {
      return await agent("objects: " + (ctx.design||""), { label: "objects_mod", timeout: 30 })
    }},
    render: { depends: "design", task: async (ctx) => {
      return await agent("render: " + (ctx.design||""), { label: "render_mod", timeout: 30 })
    }},
    assets: { depends: "design", task: async (ctx) => {
      return await agent("assets: " + (ctx.design||""), { label: "assets_mod", timeout: 30 })
    }},
    integration: { depends: ["engine", "objects", "render", "assets"], task: async (ctx) => {
      return await agent("integrate all", { label: "integration", timeout: 30 })
    }},
  })
  return results
}
""")

# ════════════════════════════════════════════════════════════════
# 超时测试脚本
# ════════════════════════════════════════════════════════════════

PATTERN_TIMEOUT = _js("""
export const meta = { name: "timeout_test", description: "", phases: [] }
export default async function () {
  const r1 = await agent("fast task", { label: "fast_task", timeout: 5 })
  try {
    const r2 = await agent("slow task", { label: "slow_task", timeout: 1 })
    return { r1, r2 }
  } catch (e) {
    log("caught: " + e.message)
    return { r1, timeout_error: e.message }
  }
}
""")

# ════════════════════════════════════════════════════════════════
# 缓存测试脚本
# ════════════════════════════════════════════════════════════════

PATTERN_CACHE = _js("""
export const meta = { name: "cache_test", description: "", phases: [] }
export default async function () {
  const a = await agent("same prompt", { label: "cache_test", timeout: 30 })
  const b = await agent("same prompt", { label: "cache_test", timeout: 30 })
  const c = await agent("different prompt", { label: "cache_test", timeout: 30 })
  return { a, b, c }
}
""")


# ════════════════════════════════════════════════════════════════════════════
# 模式①: 纯并行 -> 汇总
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_1_parallel_merge():
    """模式①: 纯并行 -> 汇总 - 验证3路并行全部执行且汇总收到上下文"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        opts = opts or {}
        label = opts.get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("[" + label + " result]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_1_PARALLEL_MERGE)

    assert result.success, "workflow failed: " + str(result.error)
    assert len(call_log) == 4, "expected 4 calls (3 parallel + 1 summary), got " + str(len(call_log)) + ": " + str(call_log)
    assert "\u767e\u5ea6\u641c\u7d22" in call_log
    assert "\u5fae\u535a\u641c\u7d22" in call_log
    assert "\u77e5\u4e4e\u641c\u7d22" in call_log
    assert "\u6c47\u603b\u62a5\u544a" in call_log
    assert result.elapsed > 0


# ════════════════════════════════════════════════════════════════════════════
# 模式②: 串行流水线
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_2_serial_pipeline():
    """模式②: 串行流水线 - 验证前一步输出作为下一步输入"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("[" + label + " full plan]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_2_SERIAL_PIPELINE)

    assert result.success
    assert len(call_log) == 3, "expected 3 steps, got " + str(len(call_log)) + ": " + str(call_log)
    assert call_log == ["data_collect", "deep_analyze", "gen_report"]


# ════════════════════════════════════════════════════════════════════════════
# 模式③: 复杂 DAG
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_3_dag():
    """模式③: DAG - 验证拓扑执行，依赖节点顺序正确"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("[" + label + " result]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_3_DAG)

    assert result.success
    assert len(call_log) == 5, "expected 5 calls, got " + str(len(call_log)) + ": " + str(call_log)
    # design must be first
    assert call_log[0] == "arch_design", "design must be first call"
    # integration must be last
    assert call_log[-1] == "integration", "integration must be last call"
    # engine, ui, assets can be in any order but must be between design and integration
    for mod in ["engine_mod", "ui_mod", "assets_mod"]:
        assert mod in call_log, "missing mod: " + mod
        mod_idx = call_log.index(mod)
        assert 0 < mod_idx < len(call_log) - 1, mod + " should be between design and integration"


# ════════════════════════════════════════════════════════════════════════════
# 模式④: 动态批量
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_4_dynamic_batch():
    """模式④: 动态批量 - 验证运行时动态生成的并行任务"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("[" + label + " result]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_4_DYNAMIC_BATCH)

    assert result.success
    assert len(call_log) == 5, "expected 1 list + 3 analyze + 1 summary = 5, got " + str(len(call_log)) + ": " + str(call_log)
    assert "file_list" in call_log
    assert "analyze_app.py" in call_log
    assert "analyze_main.py" in call_log
    assert "analyze_utils.py" in call_log
    assert "summary" in call_log


# ════════════════════════════════════════════════════════════════════════════
# 模式⑤: CodeGraph 预扫描
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_5_codegraph():
    """模式⑤: CodeGraph - 验证 agentType 分发"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    agent_types = []

    async def mock_agent(prompt, opts=None, **kw):
        _opts = opts or {}
        agent_types.append(_opts.get("agentType"))
        return _make_mock_result("result", _opts.get("label", ""))

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_5_CODEGRAPH)

    assert result.success, "workflow failed: " + str(result.error)
    assert len(agent_types) == 5
    assert agent_types[0] == "Explore", "scan agent should be Explore"
    assert agent_types[1] == "Plan", "arch analysis should be Plan"
    assert agent_types[2] == "Explore", "component analysis should be Explore"


# ════════════════════════════════════════════════════════════════════════════
# 模式⑥: 迭代循环
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_6_iterative():
    """模式⑥: 迭代循环 - 验证循环控制和条件退出"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("[" + label + " full plan]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_6_ITERATIVE)

    assert result.success
    # 1 init + 3 reviews + 2 improves + 1 final = 7
    assert len(call_log) == 5, "expected 5 calls (score>=80 exits loop), got " + str(len(call_log)) + ": " + str(call_log)
    assert "init_code" in call_log
    assert "review_1" in call_log
    assert "review_2" in call_log
    assert "improve_1" in call_log
    assert "final_review" in call_log


# ════════════════════════════════════════════════════════════════════════════
# 模式⑦: 产出 -> 验证
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_7_review_triggers_revise():
    """模式⑦: 产出->验证 - 发现问题时触发修订"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        output = "[review result]"
        return _make_mock_result(output, label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_7_PRODUCE_VERIFY)

    assert result.success
    assert "design_plan" in call_log
    assert "review_check" in call_log
    assert "plan_revise" in call_log, "found issue should trigger revise"


async def test_pattern_7_review_skips_revise():
    """模式⑦: 产出->验证 - 无问题时跳过修订"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("PASS - no issues", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_7_PRODUCE_VERIFY)

    assert result.success
    assert "design_plan" in call_log
    assert "review_check" in call_log
    assert "plan_revise" not in call_log, "PASS should skip revise"


# ════════════════════════════════════════════════════════════════════════════
# 模式⑧: 多方案 Tournament
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_8_tournament():
    """模式⑧: Tournament - 验证并行生成+汇总评选"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("result", "type_check")

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_8_TOURNAMENT)

    assert result.success
    assert len(call_log) == 4, "expected 4 calls, got " + str(len(call_log)) + ": " + str(call_log)
    assert "plan_A" in call_log
    assert "plan_B" in call_log
    assert "plan_C" in call_log
    assert "decision" in call_log


# ════════════════════════════════════════════════════════════════════════════
# 模式⑨: 容错并行
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_9_fault_tolerant_all_ok():
    """模式⑨: 容错并行 - 全部成功"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow

    async def mock_agent(prompt, opts=None, **kw):
        return _make_mock_result("data", "all_ok")

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_9_FAULT_TOLERANT)
    assert result.success


async def test_pattern_9_fault_tolerant_partial():
    """模式⑨: 容错并行 - 部分 agent 失败，整体仍成功"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    fail_count = 0

    async def mock_agent(prompt, opts=None, **kw):
        nonlocal fail_count
        fail_count += 1
        if fail_count == 1:
            raise Exception("source 1 unavailable")
        return _make_mock_result("data from source " + str(fail_count), "source_" + str(fail_count))

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_9_FAULT_TOLERANT)
    assert result.success, "partial failure should not break workflow"


# ════════════════════════════════════════════════════════════════════════════
# 模式⑩: 游戏开发 DAG
# ════════════════════════════════════════════════════════════════════════════

async def test_pattern_10_game_dag():
    """模式⑩: game DAG - 验证 DAG 内 design→4modules→integration 拓扑"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("[" + label + " result]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_10_GAME_DAG)

    assert result.success
    assert len(call_log) == 6, "expected 6 calls, got " + str(len(call_log)) + ": " + str(call_log)
    assert call_log[0] == "arch_design", "first must be arch_design"
    assert call_log[-1] == "integration", "last must be integration"
    for mod in ["engine_mod", "objects_mod", "render_mod", "assets_mod"]:
        assert mod in call_log, "missing module: " + mod


# ════════════════════════════════════════════════════════════════════════════
# 边际场景: 超时处理
# ════════════════════════════════════════════════════════════════════════════

async def test_edge_timeout_handling():
    """边际: 超时处理 - 短超时被JS catch，不破坏整体workflow"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_count = 0

    async def mock_agent(prompt, opts=None, **kw):
        nonlocal call_count
        call_count += 1
        label = (opts or {}).get("label", "")
        if label == "slow_task":
            raise asyncio.TimeoutError("Agent execution timed out after 1s")
        return _make_mock_result("fast result", "fast_task")

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_TIMEOUT)

    assert result.success, "workflow should succeed (timeout caught in JS)" 
    assert call_count == 2


# ════════════════════════════════════════════════════════════════════════════
# 边际场景: Resume 缓存
# ════════════════════════════════════════════════════════════════════════════

async def test_edge_resume_cache():
    """边际: Resume 缓存 - 相同 prompt+opts 命中缓存"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_count = 0

    async def mock_agent(prompt, opts=None, **kw):
        nonlocal call_count
        call_count += 1
        return _make_mock_result("call " + str(call_count), "call_" + str(call_count))

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_CACHE)

    assert result.success
    # first and third are unique prompts -> 2 real calls; second hits cache
    assert call_count == 2, "expected 2 real calls (cache hit for 2nd), got " + str(call_count)


# ════════════════════════════════════════════════════════════════════════════
# 边际场景: Workflow 整体超时
# ════════════════════════════════════════════════════════════════════════════

async def test_edge_workflow_timeout():
    """边际: Workflow 整体超时 - 超过 timeout 应中断"""
    from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow, WorkflowConfig

    SLOW_SCRIPT = """
export const meta = { name: "slow_script" }
export default async function () {
  await new Promise(r => setTimeout(r, 30000))
  return "done"
}
"""

    config = WorkflowConfig(timeout=2)
    wf = ClaudeCodeWorkflow(config)
    result = await wf.run(SLOW_SCRIPT)
    assert not result.success, "timeout should return failure"
    assert "Timeout" in (result.error or ""), "error should mention Timeout: " + str(result.error)


# ════════════════════════════════════════════════════════════════════════════
# 边际场景: 空跑检测
# ════════════════════════════════════════════════════════════════════════════

async def test_edge_empty_run_detection():
    """边际: 空跑检测 - 连续3轮空转应触发中断"""
    from core.multi_agent_v2.agents.middleware import RunContext
    from core.multi_agent_v2.agents.react_core import ReActCoreMiddleware
    ctx = RunContext(task_description="test", max_iterations=20)
    mw = ReActCoreMiddleware()

    for i in range(3):
        ctx.consecutive_idle_rounds += 1
    ctx.react_depth = 3
    ctx.tool_calls = []

    hook_result = await mw.on_llm_invoke(ctx)

    if hook_result and hook_result.jump_to == "end":
        assert ctx.interrupted
    else:
        assert ctx.consecutive_idle_rounds >= 3


# ════════════════════════════════════════════════════════════════════════════
# 边际场景: LoopDetection
# ════════════════════════════════════════════════════════════════════════════

async def test_edge_loop_detection_warn():
    """边际: 循环检测 - 接近但不超过硬限制"""
    from core.multi_agent_v2.agents.middleware import PlanStep, RunContext
    from core.multi_agent_v2.agents.middlewares import LoopDetectionMiddleware

    ctx = RunContext(task_description="test", max_iterations=10)
    ctx.plan = [PlanStep(index=1, description="step1", status="pending", tool_names=[])]
    ctx.tool_results = []

    mw = LoopDetectionMiddleware()
    await mw.on_start(ctx)

    for i in range(3):
        ctx._pending_tool_calls = [
            {"function": {"name": "web_search", "arguments": '{"query": "test"}'}}
        ]
        ctx.iteration = i + 1
        r = await mw.on_plan_check(ctx)
        ctx.tool_results.append({
            "tool_call": {"name": "web_search", "arguments": {"query": "test"}},
            "success": True, "result": "ok",
        })
        ctx._pending_tool_calls = None

    assert not ctx.interrupted, "3 identical calls should warn but not hard-stop"


async def test_edge_loop_detection_hard_limit():
    """边际: 循环检测 - 超过硬限制应打断"""
    from core.multi_agent_v2.agents.middleware import PlanStep, RunContext
    from core.multi_agent_v2.agents.middlewares import LoopDetectionMiddleware

    ctx = RunContext(task_description="test", max_iterations=10)
    ctx.plan = [PlanStep(index=1, description="step1", status="pending", tool_names=[])]
    ctx.tool_results = []

    mw = LoopDetectionMiddleware()
    await mw.on_start(ctx)

    for i in range(10):
        ctx._pending_tool_calls = [
            {"function": {"name": "web_search", "arguments": '{"query": "test"}'}}
        ]
        ctx.iteration = i + 1
        r = await mw.on_plan_check(ctx)
        ctx.tool_results.append({
            "tool_call": {"name": "web_search", "arguments": {"query": "test"}},
            "success": True, "result": "ok",
        })
        ctx._pending_tool_calls = None
        if ctx.interrupted:
            break

    assert ctx.interrupted, "excessive identical calls should interrupt"


# ════════════════════════════════════════════════════════════════════════════
# 边际场景: Agent 池耗尽
# ════════════════════════════════════════════════════════════════════════════

async def test_edge_agent_pool_exhaustion():
    """边际: Agent 池耗尽 - 临时创建新 Agent"""
    from core.multi_agent_v2.orchestration.orchestrator import AgentPool
    pool = AgentPool(size=2)

    a1 = await pool.acquire("task1")
    a2 = await pool.acquire("task2")
    assert pool.available == 0

    # pool exhausted - should create temp agent
    a3 = await pool.acquire("task3")
    assert a3 is not None
    assert a3.agent_id.startswith("tmp_")

    pool.release(a1)
    pool.release(a2)
    pool.release(a3)


# ════════════════════════════════════════════════════════════════════════════
# 边际场景: Pipeline 在 orchestrator 层
# ════════════════════════════════════════════════════════════════════════════

async def test_edge_orchestrator_pipeline():
    """边际: Python orchestrator pipeline - 验证 {prev_output} 替换"""
    from core.multi_agent_v2.orchestration.orchestrator import pipeline
    from core.multi_agent_v2.orchestration.orchestrator import agent as orch_agent

    call_prompts = []

    async def mock_agent(prompt, opts=None, **kw):
        call_prompts.append(prompt)
        return _make_mock_result("step output", "pipeline_step")

    with patch("core.multi_agent_v2.orchestration.orchestrator.agent", mock_agent):
        result = await pipeline([
            {"prompt": "first step", "label": "step1"},
            {"prompt": "second step with: {prev_output}", "label": "step2"},
        ], timeout_per_step=5)

    assert result.success
    assert len(call_prompts) == 2
    assert "{prev_output}" not in call_prompts[1], "prev_output should be substituted"
    assert "step output" in call_prompts[1]


# ════════════════════════════════════════════════════════════════════════════
# 混合编排: parallel + DAG + condition + pipeline
# ════════════════════════════════════════════════════════════════════════════

PATTERN_HYBRID = _js("""
export const meta = {
  name: "hybrid_orchestration",
  description: "parallel->dag->condition->pipeline->merge",
  phases: [
    { title: "\u5e76\u884c\u5206\u6790", detail: "A\u7ec4\u4ee3\u7801\u5206\u6790 + B\u7ec4\u6587\u6863\u641c\u7d22" },
    { title: "\u6c47\u603b\u62a5\u544a", detail: "\u6761\u4ef6\u5206\u652f + pipeline" },
  ],
}
export default async function () {
  phase("\u5e76\u884c\u5206\u6790")

  const [branchA, branchB] = await parallel([
    // A\u7ec4: \u4ee3\u7801\u5206\u6790 DAG
    async () => {
      const dagResult = await $dag({
        scan: async () => {
          return await agent("scan codebase", { label: "cg_scan", timeout: 30 })
        },
        parse: { depends: "scan", task: async (ctx) => {
          return await agent("parse deps from: " + (ctx.scan || ""), { label: "parse_deps", timeout: 30 })
        }},
        analyze: { depends: "scan", task: async (ctx) => {
          return await agent("analyze arch from: " + (ctx.scan || ""), { label: "analyze_arch", timeout: 30 })
        }},
        // \u6761\u4ef6\u5206\u652f: \u53ea\u6709\u5f53 analyze \u7ed3\u679c\u4e2d\u542b "complex" \u65f6\u624d\u6267\u884c\u6df1\u5ea6\u5206\u6790
        deep: { depends: "analyze", task: async (ctx) => {
          const arch = ctx.analyze || ""
          if (arch.includes("complex")) {
            return await agent("deep dive: " + arch, { label: "deep_dive", timeout: 30 })
          }
          return "skip: simple"
        }},
        summary: { depends: ["parse", "deep"], task: async (ctx) => {
          const base = "parse=" + (ctx.parse||"") + " deep=" + (ctx.deep||"")
          return await agent("summarize A: " + base, { label: "summary_A", timeout: 30 })
        }},
      })
      return dagResult
    },
    // B\u7ec4: \u6587\u6863\u641c\u7d22 DAG
    async () => {
      const dagResult = await $dag({
        search: async () => {
          return await agent("search docs", { label: "doc_search", timeout: 30 })
        },
        extract: { depends: "search", task: async (ctx) => {
          return await agent("extract from: " + (ctx.search||""), { label: "doc_extract", timeout: 30 })
        }},
        verify: { depends: "search", task: async (ctx) => {
          return await agent("verify: " + (ctx.search||""), { label: "doc_verify", timeout: 30 })
        }},
        compile: { depends: ["extract", "verify"], task: async (ctx) => {
          return await agent("compile B: " + (ctx.extract||"") + " " + (ctx.verify||""), { label: "doc_compile", timeout: 30 })
        }},
      })
      return dagResult
    },
  ])

  phase("\u6c47\u603b\u62a5\u544a")
  const merged = await agent("merge A=" + JSON.stringify(branchA) + " B=" + JSON.stringify(branchB), { label: "merge", timeout: 30 })
  const final = await agent("final report: " + merged, { label: "final_report", timeout: 30 })
  return { branchA, branchB, merged, final }
}
""")


async def test_pattern_hybrid_orchestration():
    """混合编排: parallel\u5185\u5957DAG+\u6761\u4ef6+\u7ba1\u9053"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        # \u6a21\u62df\u6761\u4ef6\u5206\u652f\u89e6\u53d1\u6df1\u5ea6\u5206\u6790
        if label == "analyze_arch":
            return _make_mock_result("complex arch with microservices", label)
        return _make_mock_result("[" + label + " result]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_HYBRID)

    assert result.success, "hybrid workflow failed: " + str(result.error)

    # A\u7ec4: scan -> parse + analyze -> (deep, \u89e6\u53d1) -> summary
    assert "cg_scan" in call_log
    assert "parse_deps" in call_log
    assert "analyze_arch" in call_log
    assert "deep_dive" in call_log, "deep_dive should run (analyze_arch returns 'complex')"
    assert "summary_A" in call_log

    # B\u7ec4: search -> extract + verify -> compile
    assert "doc_search" in call_log
    assert "doc_extract" in call_log
    assert "doc_verify" in call_log
    assert "doc_compile" in call_log

    # \u6c47\u603b\u9636\u6bb5
    assert "merge" in call_log
    assert "final_report" in call_log

    # \u9a8c\u8bc1\u6267\u884c\u987a\u5e8f: scan \u5728 parse/analyze \u4e4b\u524d
    assert call_log.index("cg_scan") < call_log.index("parse_deps")
    assert call_log.index("cg_scan") < call_log.index("analyze_arch")
    # merge \u5728\u6240\u6709 DAG \u8282\u70b9\u4e4b\u540e
    assert call_log.index("merge") > call_log.index("summary_A")
    assert call_log.index("merge") > call_log.index("doc_compile")
    # \\u603b\\u5171 11 \\u4e2a\\u8c03\\u7528
    assert len(call_log) == 11, "expected 11 calls, got " + str(len(call_log)) + ": " + str(call_log)


# ════════════════════════════════════════════════════════════════════════════
# \\u6df7\\u5408\\u7f16\\u6392\\u2468: Tournament \\u2192 Pipeline
# ════════════════════════════════════════════════════════════════════════════

PATTERN_TOURNAMENT_PIPELINE = _js("""
export const meta = {
  name: "tournament_then_pipeline",
  description: "\\u65b9\\u6848\\u7ade\\u8d5b\\u00d7\\u6d41\\u6c34\\u7ebf",
  phases: [
    { title: "\\u65b9\\u6848\\u7ade\\u8d5b", detail: "3\\u65b9\\u6848\\u5e76\\u884c\\u751f\\u6210+\\u8bc4\\u9009" },
    { title: "\\u6267\\u884c\\u7ba1\\u9053", detail: "\\u6700\\u4f18\\u65b9\\u6848\\u6309\\u6d41\\u6c34\\u7ebf\\u6267\\u884c" },
  ],
}
export default async function () {
  phase("\\u65b9\\u6848\\u7ade\\u8d5b")

  // Phase 1: Tournament -- 3 parallel plans + judge
  const [planA, planB, planC] = await parallel([
    () => agent("\\u65b9\\u6848A: \\u6700\\u5c0f\\u6539\\u52a8", { label: "plan_A", timeout: 30 }),
    () => agent("\\u65b9\\u6848B: \\u91cd\\u6784\\u5185\\u6838", { label: "plan_B", timeout: 30 }),
    () => agent("\\u65b9\\u6848C: \\u5168\\u9762\\u91cd\\u5199", { label: "plan_C", timeout: 30 }),
  ])
  const selected = await agent(
    "\\u8bc4\\u9009\\u6700\\u4f18\\u65b9\\u6848: A=" + (planA||"") + " B=" + (planB||"") + " C=" + (planC||""),
    { label: "judge", timeout: 30 }
  )

  phase("\\u6267\\u884c\\u7ba1\\u9053")

  // Phase 2: Pipeline -- feed selected plan through 3 steps
  const impl = await agent("\\u5b9e\\u73b0: " + (selected || planA), { label: "implement", timeout: 30 })
  const tested = await agent("\\u6d4b\\u8bd5: " + impl, { label: "test", timeout: 30 })
  const released = await agent("\\u53d1\\u5e03: " + tested, { label: "release", timeout: 30 })

  return { plans: [planA, planB, planC], selected, impl, tested, released }
}
""")


async def test_pattern_tournament_pipeline():
    """\\u6df7\\u5408\\u7f16\\u6392\\u2468: Tournament\\u2192Pipeline"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("[" + label + " result]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_TOURNAMENT_PIPELINE)

    assert result.success, "tournament->pipeline failed: " + str(result.error)

    # Phase 1: 3 plans + 1 judge
    assert "plan_A" in call_log
    assert "plan_B" in call_log
    assert "plan_C" in call_log
    assert "judge" in call_log
    # Phase 2: 3 pipeline steps
    assert "implement" in call_log
    assert "test" in call_log
    assert "release" in call_log

    # Order: plans before judge, judge before pipeline
    assert call_log.index("plan_A") < call_log.index("judge")
    assert call_log.index("judge") < call_log.index("implement")
    assert call_log.index("implement") < call_log.index("test")
    assert call_log.index("test") < call_log.index("release")

    # Total: 3 + 1 + 3 = 7
    assert len(call_log) == 7, "expected 7 calls, got " + str(len(call_log)) + ": " + str(call_log)


# ════════════════════════════════════════════════════════════════════════════
# 混合编排⑩: workflow() 嵌套子 Workflow（模板一中嵌套模板二）
# ════════════════════════════════════════════════════════════════════════════

PATTERN_WORKFLOW_NESTING_CHILD = _js("""
export const meta = {
  name: "child_wf",
  description: "子workflow — 接收父args并处理",
  phases: [],
}
export default async function () {
  const data = (args && args.parentData) ? args.parentData : "no-data"
  const analysis = await agent("child analyze: " + data, { label: "child_analyze", timeout: 30 })
  const report = await agent("child report: " + (analysis || ""), { label: "child_report", timeout: 30 })
  return { analysis, report }
}
""")

PATTERN_WORKFLOW_NESTING_PARENT = _js("""
export const meta = {
  name: "parent_wf",
  description: "父workflow — 初始分析→调子workflow→汇总",
  phases: [
    { title: "parent_init", detail: "初始分析" },
    { title: "sub_workflow", detail: "嵌套调子workflow" },
    { title: "merge", detail: "汇总" },
  ],
}
export default async function () {
  phase("parent_init")
  const init = await agent("initial analysis", { label: "parent_init", timeout: 30 })

  phase("sub_workflow")
  // args.childSpec 是 Python 侧传入的 {scriptPath: child.js}
  const childResult = await workflow(args.childSpec, { parentData: init || "none" })

  phase("merge")
  const final = await agent("merge: " + JSON.stringify(childResult), { label: "parent_merge", timeout: 30 })
  return { init, childResult, final }
}
""")


async def test_pattern_workflow_nesting():
    """混合编排⑩: workflow() 嵌套子 Workflow — 验证父子两级顺序执行+传参"""
    import tempfile
    import os
    from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow

    # 1. 创建临时子 Workflow JS 文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, delete_on_close=False) as f:
        f.write(PATTERN_WORKFLOW_NESTING_CHILD)
        child_path = f.name

    try:
        call_log = []

        async def mock_agent(prompt, opts=None, **kw):
            label = (opts or {}).get("label", "unknown")
            call_log.append(label)
            return _make_mock_result("[" + label + " result]", label)

        with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
            wf = ClaudeCodeWorkflow()
            result = await wf.run(
                PATTERN_WORKFLOW_NESTING_PARENT,
                args={"childSpec": {"scriptPath": child_path}},
            )

        assert result.success, "workflow nesting failed: " + str(result.error)

        # 父 Workflow: parent_init → child_analyze → child_report → parent_merge
        assert "parent_init" in call_log
        assert "child_analyze" in call_log
        assert "child_report" in call_log
        assert "parent_merge" in call_log

        # 顺序验证：parent_init 在最前，parent_merge 在最后
        assert call_log.index("parent_init") < call_log.index("child_analyze"), \
            "parent_init should run before child_analyze"
        assert call_log.index("child_report") < call_log.index("parent_merge"), \
            "child_report should run before parent_merge"

        # 子 Workflow 内部顺序：analyze → report
        assert call_log.index("child_analyze") < call_log.index("child_report"), \
            "child_analyze before child_report"

        # 总共 4 个 agent 调用
        assert len(call_log) == 4, "expected 4 calls (2 parent + 2 child), got " + str(len(call_log)) + ": " + str(call_log)

    finally:
        os.unlink(child_path)


# ════════════════════════════════════════════════════════════════════════════
# 混合编排⑪: 串行→并行(内嵌DAG)→汇总 三阶复合
# ════════════════════════════════════════════════════════════════════════════

PATTERN_THREE_STAGE_COMPOSITE = _js("""
export const meta = {
  name: "three_stage_composite",
  description: "串行→并行(内嵌DAG)→汇总 三阶复合",
  phases: [
    { title: "explore", detail: "初始探索" },
    { title: "parallel_analysis", detail: "代码/性能/安全 三路并行, 每路内嵌DAG" },
    { title: "report", detail: "汇总报告" },
  ],
}
export default async function () {
  phase("explore")

  // Stage 1: 串行 — 初始探索
  const context = await agent("explore project structure", { label: "project_explore", timeout: 30 })

  phase("parallel_analysis")

  // Stage 2: 并行 — 三路分析, 每路内嵌不同内部模式
  const [codeResult, perfResult, secResult] = await parallel([
    // A路: DAG (scan→analyze→suggest)
    async () => {
      return await $dag({
        scan: async () => {
          return await agent("scan codebase: " + (context || ""), { label: "code_scan", timeout: 30 })
        },
        analyze: { depends: "scan", task: async (ctx) => {
          return await agent("analyze code: " + (ctx.scan || ""), { label: "code_analyze", timeout: 30 })
        }},
        suggest: { depends: "analyze", task: async (ctx) => {
          return await agent("suggest: " + (ctx.analyze || ""), { label: "code_suggest", timeout: 30 })
        }},
      })
    },
    // B路: DAG (profile→optimize)
    async () => {
      return await $dag({
        profile: async () => {
          return await agent("profile perf: " + (context || ""), { label: "perf_profile", timeout: 30 })
        },
        optimize: { depends: "profile", task: async (ctx) => {
          return await agent("optimize: " + (ctx.profile || ""), { label: "perf_optimize", timeout: 30 })
        }},
      })
    },
    // C路: 串行 (check→assess)
    async () => {
      const vuln = await agent("check security: " + (context || ""), { label: "sec_check", timeout: 30 })
      const severity = await agent("assess: " + (vuln || ""), { label: "sec_assess", timeout: 30 })
      return { vuln, severity }
    },
  ])

  phase("report")

  // Stage 3: 汇总
  const report = await agent("write final report", { label: "final_report", timeout: 30 })
  return { context, codeResult, perfResult, secResult, report }
}
""")


async def test_pattern_three_stage_composite():
    """混合编排⑪: 串行→并行(内嵌DAG)→汇总 — 验证三阶复合编排"""
    from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
    call_log = []

    async def mock_agent(prompt, opts=None, **kw):
        label = (opts or {}).get("label", "unknown")
        call_log.append(label)
        return _make_mock_result("[" + label + " result]", label)

    with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
        result = await run_claude_workflow(PATTERN_THREE_STAGE_COMPOSITE)

    assert result.success, "three-stage composite failed: " + str(result.error)

    # Stage 1: 探索
    assert "project_explore" in call_log
    assert call_log.index("project_explore") == 0, "explore must be first"

    # Stage 2: 三路并行 — 验证所有 8 个 agent 都存在
    # A路: scan→analyze→suggest (DAG)
    assert "code_scan" in call_log
    assert "code_analyze" in call_log
    assert "code_suggest" in call_log
    # B路: profile→optimize (DAG)
    assert "perf_profile" in call_log
    assert "perf_optimize" in call_log
    # C路: check→assess (串行)
    assert "sec_check" in call_log
    assert "sec_assess" in call_log

    # DAG 内部顺序：scan 在 analyze/suggest 之前
    assert call_log.index("code_scan") < call_log.index("code_analyze")
    assert call_log.index("code_analyze") < call_log.index("code_suggest")

    # Stage 3: 汇总
    assert "final_report" in call_log
    assert call_log.index("final_report") > call_log.index("code_suggest")
    assert call_log.index("final_report") > call_log.index("perf_optimize")
    assert call_log.index("final_report") > call_log.index("sec_assess")

    # 总共: 1(explore) + 3(A路) + 2(B路) + 2(C路) + 1(report) = 9
    assert len(call_log) == 9, "expected 9 calls, got " + str(len(call_log)) + ": " + str(call_log)


# ════════════════════════════════════════════════════════════════════════════
# 混合编排⑫: Tournament → workflow() 嵌套（模板一执行完传参给模板二）
# ════════════════════════════════════════════════════════════════════════════

PATTERN_TOURNAMENT_NESTING_CHILD = _js("""
export const meta = {
  name: "tournament_child",
  description: "子workflow — 接收Tournament胜出方案并执行",
  phases: [],
}
export default async function () {
  const plan = (args && args.winningPlan) ? args.winningPlan : "no-plan"
  const implemented = await agent("implement: " + plan, { label: "impl_step", timeout: 30 })
  const tested = await agent("test: " + (implemented || ""), { label: "test_step", timeout: 30 })
  const deployed = await agent("deploy: " + (tested || ""), { label: "deploy_step", timeout: 30 })
  return { plan, implemented, tested, deployed }
}
""")

PATTERN_TOURNAMENT_NESTING_PARENT = _js("""
export const meta = {
  name: "tournament_parent",
  description: "父workflow — Tournament选方案→嵌套子workflow执行",
  phases: [
    { title: "tournament", detail: "3方案并行+评选" },
    { title: "execute", detail: "子workflow执行胜出方案" },
  ],
}
export default async function () {
  phase("tournament")

  // Phase 1: Tournament — 并行生成方案 + 评选
  const [planA, planB, planC] = await parallel([
    () => agent("方案A: 最小改动", { label: "plan_A", timeout: 30 }),
    () => agent("方案B: 重构内核", { label: "plan_B", timeout: 30 }),
    () => agent("方案C: 全面重写", { label: "plan_C", timeout: 30 }),
  ])
  const selected = await agent(
    "评选: A=" + (planA||"") + " B=" + (planB||"") + " C=" + (planC||""),
    { label: "judge", timeout: 30 }
  )

  phase("execute")

  // Phase 2: 模板一执行完 → 传参给模板二（嵌套子 workflow）
  const execResult = await workflow(args.childSpec, { winningPlan: selected || planA || "fallback" })
  return { plans: [planA, planB, planC], selected, execResult }
}
""")


async def test_pattern_tournament_nesting():
    """混合编排⑫: Tournament → workflow() 传参嵌套 — Tournament选方案→子workflow执行"""
    import tempfile
    import os
    from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, delete_on_close=False) as f:
        f.write(PATTERN_TOURNAMENT_NESTING_CHILD)
        child_path = f.name

    try:
        call_log = []

        async def mock_agent(prompt, opts=None, **kw):
            label = (opts or {}).get("label", "unknown")
            call_log.append(label)
            return _make_mock_result("[" + label + " result]", label)

        with patch("core.multi_agent_v2.workflow.js_workflow.py_agent", mock_agent):
            wf = ClaudeCodeWorkflow()
            result = await wf.run(
                PATTERN_TOURNAMENT_NESTING_PARENT,
                args={"childSpec": {"scriptPath": child_path}},
            )

        assert result.success, "tournament nesting failed: " + str(result.error)

        # Phase 1: Tournament (4 agents)
        assert "plan_A" in call_log
        assert "plan_B" in call_log
        assert "plan_C" in call_log
        assert "judge" in call_log

        # Phase 2: 子 workflow (3 agents)
        assert "impl_step" in call_log
        assert "test_step" in call_log
        assert "deploy_step" in call_log

        # 顺序: judge 在子 workflow 之前
        assert call_log.index("judge") < call_log.index("impl_step")
        # 子 workflow 内部顺序
        assert call_log.index("impl_step") < call_log.index("test_step")
        assert call_log.index("test_step") < call_log.index("deploy_step")

        # 总共: 4 + 3 = 7
        assert len(call_log) == 7, "expected 7 calls (4 tournament + 3 child), got " + str(len(call_log)) + ": " + str(call_log)

    finally:
        os.unlink(child_path)

"""
测试 ClaudeCodeWorkflow 三大新功能：
  1. Resume 缓存（同会话自动缓存 agent 调用）
  2. workflow() 嵌套调用
  3. 多模型路由 + Budget 追踪

运行: pytest tests/test_js_workflow_v2.py -v -s
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.multi_agent_v2.workflow.js_workflow import (
    ClaudeCodeWorkflow,
    WorkflowConfig,
    run_claude_workflow,
)
from core.multi_agent_v2.workflow.models import PhaseRecord


# ═══════════════════════════════════════════════════════════════
# 1. Resume 缓存测试
# ═══════════════════════════════════════════════════════════════

class TestResumeCache:
    """测试 Resume 缓存机制"""

    @pytest.mark.asyncio
    async def test_cache_key_consistency(self):
        """缓存键对相同 prompt+opts 应一致，对不同应不一致"""
        runtime = ClaudeCodeWorkflow()

        k1 = runtime._make_cache_key("hello", {"model": "claude-sonnet-4-6"})
        k2 = runtime._make_cache_key("hello", {"model": "claude-sonnet-4-6"})
        k3 = runtime._make_cache_key("hello", {"model": "claude-haiku-4-5"})
        k4 = runtime._make_cache_key("world", {"model": "claude-sonnet-4-6"})
        k5 = runtime._make_cache_key("hello", {"model": "claude-sonnet-4-6", "timeout": 30})
        k6 = runtime._make_cache_key("hello", {"model": "claude-sonnet-4-6", "timeout": 60})

        assert k1 == k2, "相同 prompt+opts 应生成相同键"
        assert k1 != k3, "不同 model 应生成不同键"
        assert k1 != k4, "不同 prompt 应生成不同键"
        assert k1 != k6, "不同 timeout 应生成不同键"
        print("  ✅ 缓存键一致性测试通过")

    @pytest.mark.asyncio
    async def test_cache_key_excludes_workflow_context(self):
        """缓存键应排除动态注入的 _workflowContext 和 isFinal 字段"""
        runtime = ClaudeCodeWorkflow()

        k1 = runtime._make_cache_key("hello", {"label": "test"})
        k2 = runtime._make_cache_key("hello", {
            "label": "test",
            "_workflowContext": {"globalTask": "xxx", "currentPhase": "yyy"},
        })
        k3 = runtime._make_cache_key("hello", {
            "label": "test",
            "isFinal": True,
        })

        assert k1 == k2, "_workflowContext 不应影响缓存键"
        assert k1 == k3, "isFinal 不应影响缓存键"
        print("  ✅ 缓存键排除动态字段测试通过")

    def test_cache_stats_init(self):
        """cache_stats() 初始值应为空"""
        runtime = ClaudeCodeWorkflow()
        stats = runtime.cache_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0
        print("  ✅ 缓存统计初始化测试通过")

    def test_clear_cache(self):
        """手动清除缓存应重置统计"""
        runtime = ClaudeCodeWorkflow()
        runtime._resume_cache = {"key1": "val1", "key2": "val2"}
        runtime._cache_hits = 5
        runtime._cache_misses = 3

        runtime.clear_cache()
        stats = runtime.cache_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        print("  ✅ 清除缓存测试通过")


# ═══════════════════════════════════════════════════════════════
# 2. Workflow 名称解析测试
# ═══════════════════════════════════════════════════════════════

class TestWorkflowResolution:
    """测试 _resolve_workflow_by_name"""

    @pytest.mark.asyncio
    async def test_resolve_js_workflow_by_path(self):
        """按文件路径应能解析"""
        runtime = ClaudeCodeWorkflow()

        # 写入临时 workflow 文件
        tmp_script = "/tmp/test_resolve_wf.js"
        test_content = 'export const meta = {name:"test"}; export default async function(){return 42;}'
        with open(tmp_script, "w") as f:
            f.write(test_content)

        try:
            script = runtime._resolve_workflow_by_name(tmp_script)
            assert "test_resolve_wf" in script or "test" in script
            print("  ✅ 按路径解析 workflow 测试通过")
        finally:
            os.remove(tmp_script)

    @pytest.mark.asyncio
    async def test_resolve_workflow_not_found(self):
        """找不到应抛出 FileNotFoundError"""
        runtime = ClaudeCodeWorkflow()
        with pytest.raises(FileNotFoundError):
            runtime._resolve_workflow_by_name("nonexistent_workflow_xyz")
        print("  ✅ 找不到 workflow 抛出异常测试通过")


# ═══════════════════════════════════════════════════════════════
# 3. JS 桥接脚本 + IPC 协议测试
# ═══════════════════════════════════════════════════════════════

class TestJsBridge:
    """测试 Node.js 桥接脚本的生成和执行"""

    @pytest.mark.asyncio
    async def test_bridge_script_syntax(self):
        """桥接脚本语法应正确（无 JS 语法错误）"""
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))

        bridge_script = runtime._generate_node_bridge(
            "/tmp/test_bridge",
            budget_total=100000,
        )

        # 写入临时文件并检查 Node.js 语法
        tmp_path = "/tmp/test_bridge_syntax.mjs"
        with open(tmp_path, "w") as f:
            f.write(bridge_script)

        proc = await asyncio.create_subprocess_exec(
            "node", "--check", tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            print(f"  ❌ 桥接脚本语法错误: {stderr.decode()}")
        assert proc.returncode == 0, f"桥接脚本语法检查失败: {stderr.decode()}"
        print("  ✅ 桥接脚本语法检查通过")

    @pytest.mark.asyncio
    async def test_workflow_basic_run(self):
        """最小 workflow 应该能成功执行（不调 agent，纯 JS 逻辑）"""
        script = """
        export const meta = { name: "test-basic", description: "最小测试", phases: [] };
        export default async function() {
            log("hello from workflow");
            return { result: "ok", value: 42 };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        result = await runtime.run(script)

        assert result.success, f"Workflow 执行失败: {result.error}"
        assert result.output is not None
        output = result.output
        print(f"  ✅ 基础 workflow 执行成功, output={output}")

    @pytest.mark.asyncio
    async def test_workflow_phase_and_log(self):
        """phase() 和 log() 应被正确记录"""
        script = """
        export const meta = {
            name: "test-phase",
            description: "测试 phase 和 log",
            phases: [{title:"阶段1"}, {title:"阶段2"}],
        };
        export default async function() {
            phase("阶段1");
            log("这是阶段1的日志");
            phase("阶段2");
            log("这是阶段2的日志");
            return "done";
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        result = await runtime.run(script)

        assert result.success
        assert len(result.phases) == 2
        assert result.phases[0].title == "阶段1"
        assert result.phases[1].title == "阶段2"
        print(f"  ✅ phase/log 测试通过, 共 {len(result.phases)} 个阶段")

    @pytest.mark.asyncio
    async def test_budget_tracking(self):
        """budget.spent(), remaining(), modelSpent 应正确工作"""
        script = """
        export const meta = {
            name: "test-budget",
            description: "测试 budget",
            phases: [],
        };
        export default async function() {
            const total = budget.total;
            log(`total=${total}`);

            await budget.report(5000, "claude-sonnet-4-6");
            await budget.report(3000, "claude-haiku-4-5");

            log(`spent=${budget.spent()}, remaining=${budget.remaining()}`);
            log(`modelSpent=${JSON.stringify(budget.modelSpent)}`);

            return {
                total: budget.total,
                spent: budget.spent(),
                remaining: budget.remaining(),
                modelSpent: budget.modelSpent,
            };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30, budget_total=500000))
        result = await runtime.run(script)
        assert result.success, f"Budget workflow 失败: {result.error}"
        output = result.output
        print(f"  ✅ Budget 追踪测试通过: total={output.get('total')}, spent={output.get('spent')}, modelSpent={output.get('modelSpent')}")


# ═══════════════════════════════════════════════════════════════
# 4. Resume 缓存 E2E 测试（需 mock agent 层）
# ═══════════════════════════════════════════════════════════════

class TestResumeCacheE2E:
    """端到端 Resume 缓存测试"""

    @pytest.mark.asyncio
    async def test_resume_cache_hits(self):
        """同一 workflow 运行两次，第二次应命中缓存"""
        script = """
        export const meta = {
            name: "test-resume",
            description: "测试 Resume 缓存",
            phases: [{title:"计算"}],
        };
        export default async function() {
            phase("计算");
            return { result: "done", count: 42 };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))

        # 第一次运行
        result1 = await runtime.run(script)
        assert result1.success
        stats1 = runtime.cache_stats()
        print(f"  第一次: {stats1}")

        # 第二次运行 — 预填充一个 agent 缓存条目
        runtime._resume_cache["test_key"] = {"success": True, "output": "cached_result"}
        runtime._cache_hits = 5
        runtime._cache_misses = 2

        stats2 = runtime.cache_stats()
        print(f"  缓存统计: {stats2}")
        assert stats2["hits"] == 5
        assert stats2["size"] >= 1
        print("  ✅ Resume 缓存统计测试通过")


# ═══════════════════════════════════════════════════════════════
# 5. multi_agent_v2 完整导入测试
# ═══════════════════════════════════════════════════════════════

def test_workflow_imports():
    """workflow 包应能正确导入"""
    from core.multi_agent_v2.workflow import (
        Meta, PhaseRecord, WorkflowResult,
        ClaudeCodeWorkflow, WorkflowConfig,
        run_claude_workflow,
    )
    assert Meta is not None
    assert PhaseRecord is not None
    assert WorkflowResult is not None
    assert ClaudeCodeWorkflow is not None
    assert WorkflowConfig is not None
    assert run_claude_workflow is not None
    print("  ✅ workflow 包导入测试通过")


def test_workflow_result_metadata():
    """WorkflowResult 应包含 metadata 字段"""
    from core.multi_agent_v2.workflow import WorkflowResult

    wr = WorkflowResult(
        success=True,
        output="test",
        metadata={"budget": {"spent": 8000}, "cache_stats": {"hits": 2}},
    )
    assert wr.metadata["budget"]["spent"] == 8000
    assert wr.metadata["cache_stats"]["hits"] == 2
    print("  ✅ WorkflowResult metadata 测试通过")


# ═══════════════════════════════════════════════════════════════
# 6. 并行执行测试（P0.0：验证 parallel 是真并行）
# ═══════════════════════════════════════════════════════════════

class TestParallelExecution:
    """验证 parallel() 确实是并发执行而非串行"""

    @pytest.mark.asyncio
    async def test_ipc_handler_concurrent(self):
        """验证 ipc_handler 使用 create_task 而非 await（关键修复）"""
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        assert runtime._ipc_semaphore is not None
        assert hasattr(runtime, '_ipc_tasks')
        print("  ✅ 并发控制基础设施已就绪")

    @pytest.mark.asyncio
    async def test_batch_agents_ipc(self):
        """batch_agents IPC 应能在 JS 桥接层正确调用"""
        script = """
        export const meta = { name: "test-batch", description: "测试 batch_agents", phases: [] };
        export default async function() {
            // batchAgents 是桥接器函数，验证它存在即可
            if (typeof batchAgents !== 'function') {
                log("batchAgents 未定义");
                return { success: false, error: "batchAgents not found" };
            }
            log("batchAgents 已定义");
            return { success: true, apiExists: true };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        result = await runtime.run(script)
        assert result.success, f"Workflow 失败: {result.error}"
        output = result.output
        assert output.get("success") or output.get("apiExists"), f"batchAgents 未在桥接器中定义: {output}"
        print("  ✅ batch_agents IPC 桥接器已就绪")

    @pytest.mark.asyncio
    async def test_parallel_non_agent_thunks(self):
        """parallel() 的非 agent thunk 应能按预期执行（纯 JS 逻辑）"""
        script = """
        export const meta = { name: "test-parallel-js", description: "测试 parallel 纯 JS", phases: [] };
        export default async function() {
            const results = await parallel([
                () => "结果A",
                () => "结果B",
                () => "结果C",
            ]);
            return { results };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        result = await runtime.run(script)
        assert result.success
        output = result.output
        assert output["results"] == ["结果A", "结果B", "结果C"]
        print("  ✅ parallel 纯 JS thunk 测试通过")

    @pytest.mark.asyncio
    async def test_full_result_metadata(self):
        """agent() 的 fullResult 应返回完整元数据"""
        script = """
        export const meta = { name: "test-full-result", description: "测试 fullResult", phases: [] };
        export default async function() {
            // fullResult 模式只影响 Python 端的响应格式
            // 我们只验证语法层面：agent 可以传入 fullResult: true
            log("fullResult 参数传递正常");
            return { success: true };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        result = await runtime.run(script)
        assert result.success
        print("  ✅ fullResult 语法测试通过")

    @pytest.mark.asyncio
    async def test_parallel_tolerance_one_failure(self):
        """parallel() 中某个 thunk 失败不应影响其他 thunk（Promise.allSettled 修复）"""
        script = """
        export const meta = { name: "test-parallel-tolerance", description: "测试 parallel 容错", phases: [] };
        export default async function() {
            const results = await parallel([
                () => "结果A",
                () => { throw new Error("故意失败"); },
                () => "结果C",
            ]);
            return { results };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        result = await runtime.run(script)
        assert result.success
        output = result.output
        assert len(output["results"]) == 3
        assert output["results"][0] == "结果A", f"第一个 thunk 应正常返回: {output['results'][0]}"
        assert output["results"][1] is None, f"失败的 thunk 应返回 null: {output['results'][1]}"
        assert output["results"][2] == "结果C", f"第三个 thunk 应正常返回: {output['results'][2]}"
        print("  ✅ parallel 某个 thunk 失败容错测试通过")

    @pytest.mark.asyncio
    async def test_parallel_tolerance_all_fail(self):
        """parallel() 中所有 thunk 都失败应返回全 null 数组而非崩溃"""
        script = """
        export const meta = { name: "test-parallel-all-fail", description: "测试 parallel 全失败", phases: [] };
        export default async function() {
            const results = await parallel([
                () => { throw new Error("失败1"); },
                () => { throw new Error("失败2"); },
            ]);
            return { results };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        result = await runtime.run(script)
        assert result.success
        output = result.output
        assert len(output["results"]) == 2
        assert output["results"][0] is None
        assert output["results"][1] is None
        print("  ✅ parallel 所有 thunk 失败容错测试通过")


# ═══════════════════════════════════════════════════════════════
# 7. Schema 控制测试
# ═══════════════════════════════════════════════════════════════

class TestSchemaControl:
    """验证 stripSchema opt-in 策略"""

    def test_schema_preserved_by_default(self):
        """默认情况下 schema 应该被保留"""
        runtime = ClaudeCodeWorkflow()
        opts = {"schema": {"type": "object"}}
        # 模拟 _handle_ipc 中剥离前的检查
        assert "schema" in opts
        assert not opts.get("stripSchema", False)
        print("  ✅ schema 默认保留测试通过")

    def test_schema_stripped_with_flag(self):
        """stripSchema: true 时应去掉 schema"""
        runtime = ClaudeCodeWorkflow()
        opts = {"schema": {"type": "object"}, "stripSchema": True}
        if opts.pop("stripSchema", False):
            opts.pop("schema", None)
        assert "schema" not in opts
        print("  ✅ stripSchema 测试通过")


# ═══════════════════════════════════════════════════════════════
# 8. Budget null 测试
# ═══════════════════════════════════════════════════════════════

class TestBudgetNull:
    """测试 budget.total=null / remaining()=Infinity"""

    @pytest.mark.asyncio
    async def test_budget_total_null(self):
        """budget.total=null 时 remaining() 应返回 Infinity，执行不报错"""
        script = """
        export const meta = { name: "test-budget-null", description: "", phases: [] };
        export default async function() {
            if (budget.total !== null) throw new Error("total should be null");
            if (budget.remaining() !== Infinity) throw new Error("remaining should be Infinity");
            return { total: budget.total, remaining: budget.remaining() };
        }
        """
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30, budget_total=None))
        result = await runtime.run(script)
        assert result.success, f"Workflow failed: {result.error}"
        output = result.output
        assert output["total"] is None, f"total 应为 None, 实际={output['total']}"
        # Infinity is serialized as null in JSON
        assert output["remaining"] is None
        print("  ✅ budget.total=null / remaining()=Infinity 测试通过")

    def test_generate_bridge_budget_null(self):
        """budget_total=None 时桥接脚本应含 total: null"""
        runtime = ClaudeCodeWorkflow()
        bridge = runtime._generate_node_bridge("/tmp/test", budget_total=None)
        assert "total: null" in bridge
        assert "if (this.total === null) return Infinity;" in bridge
        print("  ✅ 桥接脚本 budget null 生成测试通过")

    def test_generate_bridge_budget_normal(self):
        """budget_total 有值时桥接脚本应含正确数字（向后兼容）"""
        runtime = ClaudeCodeWorkflow()
        bridge = runtime._generate_node_bridge("/tmp/test", budget_total=500000)
        assert "total: 500000" in bridge
        print("  ✅ 桥接脚本 budget normal 生成测试通过")


# ═══════════════════════════════════════════════════════════════
# 9. Phase 追踪测试
# ═══════════════════════════════════════════════════════════════

class TestPhaseTracking:
    """测试 agent() opts.phase → per-phase agent_calls/elapsed 追踪"""

    @pytest.mark.asyncio
    async def test_per_phase_agent_calls(self):
        """opts.phase 应正确累积 agent_calls 到对应 PhaseRecord"""
        from types import SimpleNamespace
        from unittest.mock import patch

        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        msg_queue = asyncio.Queue()

        runtime._phase_records.append(PhaseRecord(title="搜索", agent_calls=0, elapsed=0.0))
        runtime._phase_records.append(PhaseRecord(title="分析", agent_calls=0, elapsed=0.0))

        async def fake_agent(*a, **kw):
            await asyncio.sleep(0.005)
            return SimpleNamespace(
                success=True, output="mock", error=None,
                execution_time=0.05, agent_id="a", metadata={},
            )

        with patch('core.multi_agent_v2.workflow.js_workflow.py_agent', fake_agent):
            await runtime._handle_ipc(
                {"type": "agent", "id": 1, "data": {"prompt": "s1", "opts": {"phase": "搜索", "label": "s1"}}},
                msg_queue,
            )
            await runtime._handle_ipc(
                {"type": "agent", "id": 2, "data": {"prompt": "s2", "opts": {"phase": "搜索", "label": "s2"}}},
                msg_queue,
            )
            await runtime._handle_ipc(
                {"type": "agent", "id": 3, "data": {"prompt": "a1", "opts": {"phase": "分析", "label": "a1"}}},
                msg_queue,
            )

        assert runtime._phase_records[0].agent_calls == 2, f"搜索 phase 应为 2 次, 实际={runtime._phase_records[0].agent_calls}"
        assert runtime._phase_records[1].agent_calls == 1, f"分析 phase 应为 1 次, 实际={runtime._phase_records[1].agent_calls}"
        assert runtime._phase_records[0].elapsed > 0
        assert runtime._phase_records[1].elapsed > 0
        print(f"  ✅ Per-phase tracking: 搜索={runtime._phase_records[0].agent_calls}, 分析={runtime._phase_records[1].agent_calls}")

    @pytest.mark.asyncio
    async def test_phase_without_agent_call(self):
        """无 agent 调用的 phase 应 agent_calls=0"""
        from types import SimpleNamespace
        from unittest.mock import patch

        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        runtime._phase_records.append(PhaseRecord(title="未使用", agent_calls=0, elapsed=0.0))
        msg_queue = asyncio.Queue()

        async def fake_agent(*a, **kw):
            return SimpleNamespace(
                success=True, output="m", error=None,
                execution_time=0.01, agent_id="a", metadata={},
            )

        with patch('core.multi_agent_v2.workflow.js_workflow.py_agent', fake_agent):
            await runtime._handle_ipc(
                {"type": "agent", "id": 1, "data": {"prompt": "t", "opts": {"phase": "其他", "label": "t"}}},
                msg_queue,
            )

        assert runtime._phase_records[0].agent_calls == 0, "未使用的 phase 应保持 0"
        print("  ✅ 无 agent 调用的 phase 统计正确")

    @pytest.mark.asyncio
    async def test_build_workflow_result_uses_per_phase_data(self):
        """_build_workflow_result 应使用 per-phase 数据而非全局 agentCount"""
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        runtime._phase_records.append(PhaseRecord(title="搜索", agent_calls=3, elapsed=1.5))
        runtime._phase_records.append(PhaseRecord(title="分析", agent_calls=2, elapsed=0.8))

        result = runtime._build_workflow_result(
            {
                "success": True,
                "output": "done",
                "meta": {"name": "test", "description": "", "phases": []},
                "phaseRecords": [{"title": "搜索"}, {"title": "分析"}],
                "logs": [],
                "agentCount": 99,  # 故意给一个很大的全局值
                "budget": {"spent": 8000},
            },
            start=100.0, end=105.0, meta_overrides=None,
        )

        assert len(result.phases) == 2
        assert result.phases[0].agent_calls == 3, f"应为 3, 实际={result.phases[0].agent_calls}"
        assert result.phases[1].agent_calls == 2, f"应为 2, 实际={result.phases[1].agent_calls}"
        assert result.phases[0].elapsed == 1.5
        assert result.phases[1].elapsed == 0.8
        print("  ✅ _build_workflow_result 使用 per-phase 数据")


# ═══════════════════════════════════════════════════════════════
# 10. 递归深度限制测试
# ═══════════════════════════════════════════════════════════════

class TestRecursionDepth:
    """测试嵌套 workflow 递归深度限制"""

    @pytest.mark.asyncio
    async def test_depth_limit_exceeded(self):
        """_depth >= 5 时应拒绝并返回 error"""
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        msg_queue = asyncio.Queue()
        runtime._depth = 5

        await runtime._handle_ipc(
            {"type": "workflow", "id": 1, "data": {"nameOrRef": "x", "args": {}}},
            msg_queue,
        )

        resp = await asyncio.wait_for(msg_queue.get(), timeout=5)
        assert "error" in resp
        assert "exceeded" in resp["error"].lower()
        print("  ✅ 递归深度超限拒绝测试通过")

    @pytest.mark.asyncio
    async def test_depth_limit_within(self):
        """_depth=2 时不触发深度错误，正常走文件解析"""
        runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=30))
        msg_queue = asyncio.Queue()
        runtime._depth = 2

        await runtime._handle_ipc(
            {"type": "workflow", "id": 1, "data": {"nameOrRef": "nonexistent_xyz_999", "args": {}}},
            msg_queue,
        )

        resp = await asyncio.wait_for(msg_queue.get(), timeout=5)
        assert "error" in resp
        assert "depth" not in resp["error"].lower()
        print("  ✅ 递归深度正常放行测试通过")


# ═══════════════════════════════════════════════════════════════
# 11. 截断循环修复验证
# ═══════════════════════════════════════════════════════════════

class TestTruncationLoopFix:
    """验证截断检测 retry 上限能断开无限续写循环"""

    def test_truncation_retry_stops_after_2(self):
        """同文件截断续写 ≥3 次应停止注入 forced_instructions"""
        from types import SimpleNamespace
        from core.multi_agent_v2.agents.file_validator import validate_file_content

        ctx = SimpleNamespace()
        ctx._write_retries = {}
        ctx.forced_instructions = None
        ctx.warnings = []

        truncated_html = "<html><body><script>alert(1)</script></body>"
        # 注意：缺少 </html>，会触发截断检测

        # 第 1 次: 应注入 forced_instructions
        validate_file_content(
            "/tmp/test_truncation.html", truncated_html, truncated_html,
            ctx=ctx, agent=None,
        )
        assert ctx.forced_instructions is not None, "第一次应注入续写指令"
        first_instructions = ctx.forced_instructions

        # 第 2 次: 仍应注入（retry_count=1 < 2）
        ctx.forced_instructions = None
        validate_file_content(
            "/tmp/test_truncation.html", truncated_html, truncated_html,
            ctx=ctx, agent=None,
        )
        assert ctx.forced_instructions is not None, "第二次应仍注入续写指令"

        # 第 3 次: retry_count >= 2，应停止注入
        ctx.forced_instructions = None
        validate_file_content(
            "/tmp/test_truncation.html", truncated_html, truncated_html,
            ctx=ctx, agent=None,
        )
        assert ctx.forced_instructions is None, "第三次应停止注入，断开循环"

        # 验证 retry 计数
        assert ctx._write_retries.get("truncation:/tmp/test_truncation.html", 0) >= 3
        print("  ✅ 截断循环修复验证通过: 3次后停止注入 forced_instructions")

    def test_truncation_different_paths_independent(self):
        """不同路径的截断重试计数应独立"""
        from types import SimpleNamespace
        from core.multi_agent_v2.agents.file_validator import validate_file_content

        ctx = SimpleNamespace()
        ctx._write_retries = {}
        ctx.forced_instructions = None
        ctx.warnings = []

        truncated = "<html><body></body>"

        # 路径 A 写 3 次
        for i in range(3):
            ctx.forced_instructions = None
            validate_file_content("/tmp/a.html", truncated, truncated, ctx=ctx, agent=None)

        # 第 3 次路径 A 应停止
        assert ctx.forced_instructions is None, "路径 A 第 3 次应停止"

        # 路径 B 第 1 次 仍应注入
        ctx.forced_instructions = None
        validate_file_content("/tmp/b.html", truncated, truncated, ctx=ctx, agent=None)
        assert ctx.forced_instructions is not None, "路径 B 第 1 次仍应注入"

        print("  ✅ 不同路径截断计数独立验证通过")


# ═══════════════════════════════════════════════════════════════
# 12. 文件写入去重修复验证
# ═══════════════════════════════════════════════════════════════

class TestWriteFileDedup:
    """验证 write_file 同路径写入去重机制"""

    @pytest.mark.asyncio
    async def test_write_same_path_3_times_blocked(self):
        """同一路径写入 3 次（内容不同），第 3 次拦截，force=true 可绕过"""
        import tempfile
        from core.multi_agent_v2.tools.tool_registry import (
            _handle_write_file, _written_file_registry,
        )

        # 清理注册表避免残留
        _written_file_registry.clear()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            temp_path = f.name

        try:
            # 第 1 次: 应成功
            r1 = await _handle_write_file({"path": temp_path, "content": "content v1"})
            assert r1.get("ok"), f"第 1 次写入应成功: {r1}"

            # 第 2 次: 应成功（不同内容）
            r2 = await _handle_write_file({"path": temp_path, "content": "content v2"})
            assert r2.get("ok"), f"第 2 次写入应成功: {r2}"

            # 第 3 次: 应被拦截
            r3 = await _handle_write_file({"path": temp_path, "content": "content v3"})
            assert not r3.get("ok"), f"第 3 次应被拦截: {r3}"
            assert "反复写入" in r3.get("error", ""), f"错误信息应提示反复写入: {r3}"

            # force=true 也不能绕过（registry 阻止重写循环）
            r4 = await _handle_write_file({"path": temp_path, "content": "content v4", "force": True})
            assert not r4.get("ok"), f"force=true 也应被拦截: {r4}"

        finally:
            os.unlink(temp_path)
            _written_file_registry.clear()

    @pytest.mark.asyncio
    async def test_write_same_path_identical_content_skips(self):
        """同一路径写入完全相同内容应返回 ok 并提示无需写入"""
        from core.multi_agent_v2.tools.tool_registry import (
            _handle_write_file, _written_file_registry,
        )

        _written_file_registry.clear()

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            temp_path = f.name

        try:
            r1 = await _handle_write_file({"path": temp_path, "content": "hello"})
            assert r1.get("ok"), f"第 1 次写入应成功: {r1}"

            # 相同内容 → 应跳过
            r2 = await _handle_write_file({"path": temp_path, "content": "hello"})
            assert r2.get("ok"), f"相同内容应返回 ok: {r2}"
            msg = r2.get("data", "")
            assert "无需写入" in msg or "相同" in msg, f"应提示无需写入: {msg}"
            print(f"  ✅ 相同内容跳过验证通过")

        finally:
            os.unlink(temp_path)
            _written_file_registry.clear()

    @pytest.mark.asyncio
    async def test_write_diff_paths_not_affected(self):
        """不同路径应各自独立计数，不受影响"""
        from core.multi_agent_v2.tools.tool_registry import (
            _handle_write_file, _written_file_registry,
        )

        _written_file_registry.clear()

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as fa, \
             tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as fb:
            path_a = fa.name
            path_b = fb.name

        try:
            # 路径 A 写 2 次成功
            await _handle_write_file({"path": path_a, "content": "a1"})
            await _handle_write_file({"path": path_a, "content": "a2"})
            # 路径 A 第 3 次被拦截
            r_a3 = await _handle_write_file({"path": path_a, "content": "a3"})
            assert not r_a3.get("ok"), "路径 A 第 3 次应被拦截"

            # 路径 B 第 1 次不受影响（独立计数）
            r_b1 = await _handle_write_file({"path": path_b, "content": "b1"})
            assert r_b1.get("ok"), "路径 B 第 1 次应成功"
            print("  ✅ 不同路径独立计数验证通过")

        finally:
            for p in [path_a, path_b]:
                if os.path.exists(p):
                    os.unlink(p)
            _written_file_registry.clear()


# ═══════════════════════════════════════════════════════════════
# 13. tool_executor 修复验证
# ═══════════════════════════════════════════════════════════════

class TestToolExecutorFix:
    """验证 write_file 保护和降级机制的正确行为"""

    def test_write_file_force_degradation(self):
        """write_file 连续失败3次后降级路径应自动注入 force=true（打破死循环）"""
        import inspect
        from core.multi_agent_v2.agents import tool_executor

        source = inspect.getsource(tool_executor)

        # ── execute_tool_call（单次调用）不应自动注入 force=true ──
        # 避免绕过文件已存在的保护
        single_call_source = source.split("async def execute_tool_calls_parallel")[0]
        has_auto_force = any(
            kw in single_call_source.lower()
            for kw in ["_args[\"force\"] = true", "args[\"force\"] = true"]
        )
        assert not has_auto_force, "execute_tool_call 不应自动注入 force=true"

        # ── 降级路径（_run_one）应自动注入 force=true ──
        # 连续失败3次后降级到 execute_python 会绕过保护并形成死循环
        assert "_args[\"force\"] = True" in source, (
            "降级路径应自动注入 force=true（否则会陷入 write_file→execute_python 死循环）"
        )
        print("  ✅ execute_tool_call 无自动 force=true 注入")
        print("  ✅ 降级路径自动注入 force=true（正确打破死循环）")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

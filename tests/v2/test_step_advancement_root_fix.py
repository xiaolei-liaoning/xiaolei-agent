"""
端到端测试：步骤推进根因修复 — swap 对称互换

覆盖三个失败案例：
1. dbx 数据库客户端 — search_files 但步骤期望 write_file
2. Angry Birds — execute_shell ls/mkdir 但步骤期望 write_file
3. 探索工具也可被写文件推进（反方向 swap）
"""
import pytest
from core.multi_agent_v2.agents.middleware import PlanStep, RunContext
from core.multi_agent_v2.agents.plan_manager import update_step_status


def _make_ctx(steps, tool_results):
    ctx = RunContext(task_description="test")
    ctx.plan = steps
    ctx.tool_results = list(tool_results)
    ctx.consecutive_failures = {}
    ctx._step_retries = {}
    return ctx


class TestStepAdvancementRootFix:

    def test_explore_tool_advances_write_step(self):
        """Angry Birds 案例：execute_shell ls/mkdir → write_file 步骤推进"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="写代码", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "execute_shell", "arguments": {"command": "ls"}},
                 "success": True, "result": "dir listing"},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "execute_shell 应推进 write_file 步骤"

    def test_search_files_advances_write_step(self):
        """dbx 案例：search_files → write_file 步骤推进"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="写文件", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "search_files", "arguments": {"pattern": "*.py"}},
                 "success": True, "result": "file list"},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "search_files 应推进 write_file 步骤"

    def test_read_file_advances_write_step(self):
        """read_file 探索 → write_file 步骤推进"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="生成报告", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "read_file", "arguments": {"path": "t.txt"}},
                 "success": True, "result": "file content"},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "read_file 应推进 write_file 步骤"

    def test_write_also_advances_explore_step(self):
        """反方向 swap：write_file → 探索步骤也推进"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="探索代码", tool_names=["codegraph_explore"])],
            tool_results=[
                {"tool_call": {"name": "write_file", "arguments": {"path": "out.txt", "content": "data"}},
                 "success": True, "result": {}},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "write_file 应推进 explore 步骤"

    def test_exact_match_still_works(self):
        """原始精确匹配不受影响"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="写文件", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "write_file", "arguments": {"path": "x.txt", "content": "hello"}},
                 "success": True, "result": {}},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "done"

    def test_multiple_steps_only_first_advances(self):
        """多步骤：execute_shell 只推进当前步骤，后续步骤不受影响"""
        ctx = _make_ctx(
            steps=[
                PlanStep(index=1, description="写文件", tool_names=["write_file"]),
                PlanStep(index=2, description="搜索", tool_names=["web_search"]),
            ],
            tool_results=[
                {"tool_call": {"name": "execute_shell", "arguments": {"command": "ls"}},
                 "success": True, "result": "dir listing"},
            ],
        )
        ctx.plan[0].status = "pending"
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "execute_shell 推进步骤 1"
        assert ctx.plan[1].status != "done", "步骤 2 不应被推进"

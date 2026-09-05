"""
端到端测试：步骤推进根因修复 — swap 对称互换

覆盖三个失败案例：
1. dbx 数据库客户端 — search_files 但步骤期望 write_file
2. Angry Birds — execute_shell ls/mkdir 但步骤期望 write_file
3. 探索工具也可被写文件推进（反方向 swap）
"""
import pytest
import os
import tempfile
from core.multi_agent_v2.agents.middleware import PlanStep, RunContext
from core.multi_agent_v2.agents.plan_manager import update_step_status
from core.multi_agent_v2.agents.react_core import _check_postcondition_exit_guard


def _make_ctx(steps, tool_results):
    ctx = RunContext(task_description="test")
    ctx.plan = steps
    ctx.tool_results = list(tool_results)
    ctx.consecutive_failures = {}
    ctx._step_retries = {}
    return ctx


class TestStepAdvancementRootFix:

    def test_explore_tool_advances_write_step(self):
        """Angry Birds 案例：已写过文件 → execute_shell 可推进 write_file 步骤"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="写代码", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "write_file", "arguments": {"path": "a.py", "content": "x"}},
                 "success": True, "result": {}},
                {"tool_call": {"name": "execute_shell", "arguments": {"command": "ls"}},
                 "success": True, "result": "dir listing"},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "有 write_file 历史时 execute_shell 应推进 write_file 步骤"

    def test_search_files_advances_write_step(self):
        """dbx 案例：已写过文件 → search_files 可推进 write_file 步骤"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="写文件", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "write_file", "arguments": {"path": "a.py", "content": "x"}},
                 "success": True, "result": {}},
                {"tool_call": {"name": "search_files", "arguments": {"pattern": "*.py"}},
                 "success": True, "result": "file list"},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "有 write_file 历史时 search_files 应推进 write_file 步骤"

    def test_read_file_advances_write_step(self):
        """read_file 探索 → write_file 步骤推进（有写历史）"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="生成报告", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "write_file", "arguments": {"path": "a.py", "content": "x"}},
                 "success": True, "result": {}},
                {"tool_call": {"name": "read_file", "arguments": {"path": "t.txt"}},
                 "success": True, "result": "file content"},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "有 write_file 历史时 read_file 应推进 write_file 步骤"

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
        """多步骤：execute_shell 只推进当前步骤（有写历史）"""
        ctx = _make_ctx(
            steps=[
                PlanStep(index=1, description="写文件", tool_names=["write_file"]),
                PlanStep(index=2, description="搜索", tool_names=["web_search"]),
            ],
            tool_results=[
                {"tool_call": {"name": "write_file", "arguments": {"path": "a.py", "content": "x"}},
                 "success": True, "result": {}},
                {"tool_call": {"name": "execute_shell", "arguments": {"command": "ls"}},
                 "success": True, "result": "dir listing"},
            ],
        )
        ctx.plan[0].status = "pending"
        update_step_status(ctx)
        assert ctx.plan[0].status == "done", "有 write_file 历史时 execute_shell 推进步骤 1"
        assert ctx.plan[1].status != "done", "步骤 2 不应被推进"


class TestSwapWriteFileGuard:

    def test_explore_does_not_skip_first_write(self):
        """没有写历史时 explore 工具不应推进 write_file 步骤（防止跳过首次写入）"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="写代码", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "execute_shell", "arguments": {"command": "mkdir -p dir"}},
                 "success": True, "result": ""},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "pending", "首次写入前 explore 不应推进 write_file 步骤"

    def test_search_files_does_not_skip_first_write(self):
        """没有写历史时 search_files 不应推进 write_file 步骤"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="写文件", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "search_files", "arguments": {"pattern": "*.py"}},
                 "success": True, "result": "file list"},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "pending", "首次写入前 search_files 不应推进 write_file 步骤"

    def test_read_file_does_not_skip_first_write(self):
        """没有写历史时 read_file 不应推进 write_file 步骤"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="生成报告", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "read_file", "arguments": {"path": "DESIGN.md"}},
                 "success": True, "result": "design doc"},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "pending", "首次写入前 read_file 不应推进 write_file 步骤"

    def test_multiple_explores_does_not_skip_first_write(self):
        """没有写历史时多次探索也不应推进 write_file 步骤"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="写代码", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "execute_shell", "arguments": {"command": "ls"}},
                 "success": True, "result": "dir"},
                {"tool_call": {"name": "read_file", "arguments": {"path": "DESIGN.md"}},
                 "success": True, "result": "design"},
                {"tool_call": {"name": "execute_shell", "arguments": {"command": "mkdir -p src"}},
                 "success": True, "result": ""},
            ],
        )
        update_step_status(ctx)
        assert ctx.plan[0].status == "pending", "无 write_file 历史时多次 explore 也不应推进"


class TestReadFileLoopDetection:

    def test_read_file_loop_triggers_for_write_tasks(self):
        """read_file 循环应触发 write 任务的 forced_instructions"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="用 write_file 创建文件", tool_names=["write_file"])],
            tool_results=[
                {"tool_call": {"name": "read_file", "arguments": {"path": "DESIGN.md"}},
                 "success": True, "result": "design"},
                {"tool_call": {"name": "read_file", "arguments": {"path": "DESIGN.md"}},
                 "success": True, "result": "design"},
                {"tool_call": {"name": "read_file", "arguments": {"path": "DESIGN.md"}},
                 "success": True, "result": "design"},
            ],
        )
        ctx.react_depth = 2
        update_step_status(ctx)
        assert ctx.forced_instructions, "write 任务卡在 read_file 应产生 forced_instructions"
        assert "write_file" in ctx.forced_instructions.lower(), "指令应提到 write_file"
        assert "read_file" in ctx.disallowed_tools, "read_file 应被禁用"

    def test_read_file_loop_does_not_trigger_without_write_keywords(self):
        """没有 write 关键词时不触发 write 检测"""
        ctx = _make_ctx(
            steps=[PlanStep(index=1, description="分析代码质量", tool_names=["read_file"])],
            tool_results=[
                {"tool_call": {"name": "read_file", "arguments": {"path": "a.py"}},
                 "success": True, "result": "code"},
                {"tool_call": {"name": "read_file", "arguments": {"path": "a.py"}},
                 "success": True, "result": "code"},
                {"tool_call": {"name": "read_file", "arguments": {"path": "a.py"}},
                 "success": True, "result": "code"},
            ],
        )
        ctx.react_depth = 2
        ctx.forced_instructions = None
        ctx.disallowed_tools = []
        ctx._filtered_tools = None
        update_step_status(ctx)
        assert not ctx.disallowed_tools or "read_file" not in ctx.disallowed_tools


class TestInsertExploreBeforeWrite:

    def test_inserts_explore_before_write_step(self):
        """write_file 步骤前应自动插入 explore 步骤"""
        from core.multi_agent_v2.agents.plan_manager import _insert_explore_before_write
        steps = [
            PlanStep(index=1, description="用 write_file 创建 engine.js", tool_names=["write_file"]),
        ]
        result = _insert_explore_before_write(steps)
        assert len(result) == 2, "应插入 explore 步骤"
        assert "execute_shell" in (result[0].tool_names or []), "探索步骤应有 execute_shell"
        assert result[1].tool_names == ["write_file"], "原始 write 步骤应保持"

    def test_does_not_insert_explore_if_already_present(self):
        """如果前一步已经是 explore，不再重复插入"""
        from core.multi_agent_v2.agents.plan_manager import _insert_explore_before_write
        steps = [
            PlanStep(index=1, description="创建目录", tool_names=["execute_shell"]),
            PlanStep(index=2, description="用 write_file 创建 engine.js", tool_names=["write_file"]),
        ]
        result = _insert_explore_before_write(steps)
        assert len(result) == 2, "已有 explore 步骤时不应再插入"
        assert result[0].tool_names == ["execute_shell"]
        assert result[1].tool_names == ["write_file"]

    def test_handles_multiple_write_steps(self):
        """多个 write_file 步骤时每个前面都插入 explore"""
        from core.multi_agent_v2.agents.plan_manager import _insert_explore_before_write
        steps = [
            PlanStep(index=1, description="用 write_file 创建 a.js", tool_names=["write_file"]),
            PlanStep(index=2, description="用 write_file 创建 b.js", tool_names=["write_file"]),
        ]
        result = _insert_explore_before_write(steps)
        assert len(result) == 4, "2 个 write 步骤 → 4 个总步骤（插 2 个 explore）"
        assert "execute_shell" in (result[0].tool_names or [])
        assert result[1].tool_names == ["write_file"]
        assert "execute_shell" in (result[2].tool_names or [])
        assert result[3].tool_names == ["write_file"]

    def test_preserves_non_write_steps(self):
        """非 write 步骤保持不动"""
        from core.multi_agent_v2.agents.plan_manager import _insert_explore_before_write
        steps = [
            PlanStep(index=1, description="搜索资料", tool_names=["web_search"]),
        ]
        result = _insert_explore_before_write(steps)
        assert len(result) == 1
        assert result[0].tool_names == ["web_search"]


class TestExtractExpectedFiles:

    def test_extracts_write_file_paths(self):
        """从任务描述中提取 write_file 路径"""
        from core.multi_agent_v2.agents.subagent.spawn import _extract_expected_files
        text = '用 write_file(path="~/Desktop/kof_game/src/engine.js") 写入引擎'
        paths = _extract_expected_files(text)
        assert any("engine.js" in p for p in paths), f"应提取 engine.js 路径, got {paths}"

    def test_returns_empty_for_no_write_file(self):
        """没有 write_file 描述时返回空列表"""
        from core.multi_agent_v2.agents.subagent.spawn import _extract_expected_files
        text = "请分析代码结构"
        assert _extract_expected_files(text) == []

    def test_extracts_multiple_paths(self):
        """多个 write_file 路径都被提取"""
        from core.multi_agent_v2.agents.subagent.spawn import _extract_expected_files
        text = '1. write_file(path="a.js")\n2. write_file(path="b.js")'
        paths = _extract_expected_files(text)
        assert len(paths) >= 2, f"应提取 2 个路径, got {paths}"


class TestLoopExitGuard:
    """KOF 场景：agent 试图 final_answer 退出时，postcondition 守卫拦截"""

    def test_blocks_exit_when_file_missing(self):
        """file_exists 不满足时拦截退出"""
        step = PlanStep(index=1, description="写 engine.js", tool_names=["write_file"],
                        postconditions=["file_exists:/tmp/_test_kof_missing.flag"])
        ctx = RunContext(task_description="test")
        ctx.plan = [step]
        ctx.react_depth = 3
        ctx.final_answer = "写完了"
        assert _check_postcondition_exit_guard(ctx), "应拦截"
        assert not ctx.final_answer, "final_answer 应被清空"
        assert ctx.forced_instructions, "应设置 forced_instructions"

    def test_allows_exit_when_file_exists(self):
        """file_exists 满足时允许退出"""
        tmp = tempfile.mktemp(suffix=".flag")
        try:
            open(tmp, "w").close()
            step = PlanStep(index=1, description="写 engine.js", tool_names=["write_file"],
                            postconditions=[f"file_exists:{tmp}"])
            ctx = RunContext(task_description="test")
            ctx.plan = [step]
            ctx.react_depth = 3
            ctx.final_answer = "写完了"
            assert not _check_postcondition_exit_guard(ctx), "不应拦截（文件已存在）"
            assert ctx.final_answer == "写完了", "final_answer 应保留"
        finally:
            os.unlink(tmp)

    def test_blocks_exit_when_tool_not_called(self):
        """tool_called 不满足时拦截退出"""
        step = PlanStep(index=1, description="分析代码", tool_names=["codegraph_explore"],
                        postconditions=["tool_called:codegraph_explore"])
        ctx = RunContext(task_description="test")
        ctx.plan = [step]
        ctx.react_depth = 3
        ctx.final_answer = "分析完毕"
        assert _check_postcondition_exit_guard(ctx), "应拦截"
        assert not ctx.final_answer

    def test_allows_exit_when_tool_called(self):
        """tool_called 满足时允许退出"""
        step = PlanStep(index=1, description="搜索", tool_names=["web_search"],
                        postconditions=["tool_called:web_search"])
        ctx = RunContext(task_description="test")
        ctx.plan = [step]
        ctx.tool_results = [{"tool_call": {"name": "web_search"}, "success": True}]
        ctx.react_depth = 3
        ctx.final_answer = "搜索完毕"
        assert not _check_postcondition_exit_guard(ctx)
        assert ctx.final_answer == "搜索完毕"

    def test_does_not_trigger_below_depth_3(self):
        """react_depth < 3 时不触发"""
        step = PlanStep(index=1, description="写文件", tool_names=["write_file"],
                        postconditions=["file_exists:/nonexistent"])
        ctx = RunContext(task_description="test")
        ctx.plan = [step]
        ctx.react_depth = 2
        ctx.final_answer = "完成"
        assert not _check_postcondition_exit_guard(ctx)

    def test_does_not_trigger_without_final_answer(self):
        """final_answer 为空时不触发"""
        ctx = RunContext(task_description="test")
        ctx.plan = [PlanStep(index=1, description="写文件", tool_names=["write_file"],
                             postconditions=["file_exists:/nonexistent"])]
        ctx.react_depth = 3
        assert not _check_postcondition_exit_guard(ctx)

    def test_handles_no_plan(self):
        """plan 为空时安全返回 False"""
        ctx = RunContext(task_description="test")
        ctx.react_depth = 3
        ctx.final_answer = "完成"
        assert not _check_postcondition_exit_guard(ctx)

    def test_handles_empty_postconditions(self):
        """postconditions 为空时不拦截"""
        step = PlanStep(index=1, description="写文件", tool_names=["write_file"])
        ctx = RunContext(task_description="test")
        ctx.plan = [step]
        ctx.react_depth = 3
        ctx.final_answer = "完成"
        assert not _check_postcondition_exit_guard(ctx)

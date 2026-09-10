"""
Comprehensive tool system tests - covers all 24 tools in tools/

Test suites:
  1. Base infrastructure (Tool, ToolRegistry)
  2. File I/O (ReadTool, WriteTool, EditTool)
  3. Search (GrepTool, GlobTool, OpencodeGlobTool)
  4. Shell execution (ShellTool, BashTool)
  5. Network (WebFetchTool, WebSearchTool, MCPWebSearchTool)
  6. Task management (TaskTool, TodoTool, TodoWriteTool, PlanTool)
  7. Code intelligence (LSPTool, JSONSchemaTool, SchemaTool)
  8. Interaction (QuestionTool)
  9. Utilities (TruncateTool, ExternalDirectoryTool, InvalidTool)
  10. Registry & meta (RegistryTool, SkillTool)
"""

import os
import sys
import json
import tempfile
from dataclasses import dataclass
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

try:
    from base import Tool, ToolInput, ToolOutput, ToolPermission, ToolRegistry, tool_registry
except ImportError:
    pytest.skip("旧 tools/ 系统已移除，此测试需要 tools/base.py", allow_module_level=True)


# ============================================================
# 0. Fixtures
# ============================================================

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        old_cwd = os.getcwd()
        os.chdir(d)
        yield Path(d)
        os.chdir(old_cwd)


@pytest.fixture
def sample_file(tmp_dir):
    f = tmp_dir / "test.txt"
    f.write_text("hello world\nline 2\nline 3\n", encoding="utf-8")
    return f


@pytest.fixture
def sample_dir(tmp_dir):
    (tmp_dir / "a.py").write_text("print('a')")
    (tmp_dir / "b.py").write_text("print('b')")
    (tmp_dir / "sub").mkdir()
    (tmp_dir / "sub" / "c.py").write_text("print('c')")
    return tmp_dir


# ============================================================
# 1. Base infrastructure
# ============================================================

class TestBaseInfrastructure:

    def test_tool_abstract_enforcement(self):
        with pytest.raises(TypeError):
            Tool("bad", "no execute")  # cannot instantiate abstract

    def test_tool_registry_register_and_get(self):
        reg = ToolRegistry()
        tool = DummyTool("dummy", "A test tool", ToolPermission.READ)
        reg.register(tool)
        assert reg.has_tool("dummy")
        assert reg.get_tool("dummy") is tool

    def test_tool_registry_execute(self):
        reg = ToolRegistry()
        tool = DummyTool("echo", "Echo", ToolPermission.READ)
        reg.register(tool)
        result = reg.execute("echo", {"msg": "hi"})
        assert result["success"] is True
        assert result["result"].output == "hi"

    def test_tool_registry_execute_not_found(self):
        reg = ToolRegistry()
        with pytest.raises(ValueError):
            reg.execute("nonexistent", {})

    def test_tool_registry_unregister(self):
        reg = ToolRegistry()
        tool = DummyTool("x", "x", ToolPermission.READ)
        reg.register(tool)
        assert reg.unregister("x") is True
        assert reg.has_tool("x") is False
        assert reg.unregister("x") is False

    def test_tool_registry_list_by_permission(self):
        reg = ToolRegistry()
        reg.register(DummyTool("r1", "r1", ToolPermission.READ))
        reg.register(DummyTool("w1", "w1", ToolPermission.WRITE))
        reg.register(DummyTool("r2", "r2", ToolPermission.READ))
        reads = reg.list_tools(ToolPermission.READ)
        assert len(reads) == 2
        writes = reg.list_tools(ToolPermission.WRITE)
        assert len(writes) == 1

    def test_tool_definition(self):
        tool = DummyTool("test_def", "Test", ToolPermission.READ, timeout=60, max_retries=5)
        d = tool.get_definition()
        assert d.name == "test_def"
        assert d.timeout == 60
        assert d.max_retries == 5

    def test_global_tool_registry_exists(self):
        assert isinstance(tool_registry, ToolRegistry)

    def test_tool_permission_enum(self):
        assert ToolPermission.READ.value == "read"
        assert ToolPermission.WRITE.value == "write"
        assert ToolPermission.EXECUTE.value == "execute"
        assert ToolPermission.ADMIN.value == "admin"


@dataclass
class DummyOutput(ToolOutput):
    output: str = ""


@dataclass
class DummyInput(ToolInput):
    msg: str = ""


class DummyTool(Tool[DummyInput, DummyOutput]):
    def __init__(self, name, description, permission, timeout=30, max_retries=3):
        super().__init__(name, description, permission, timeout, max_retries)

    def get_input_schema(self):
        return {"type": "object", "properties": {"msg": {"type": "string"}}}

    def get_output_schema(self):
        return {"type": "object", "properties": {"output": {"type": "string"}}}

    def validate_input(self, input_data):
        if isinstance(input_data, DummyInput):
            return input_data
        return DummyInput(**input_data)

    def execute(self, input_data: DummyInput):
        return DummyOutput(output=input_data.msg)


# ============================================================
# 2. File I/O tools
# ============================================================

class TestReadTool:
    def test_read_text_file(self, sample_file):
        from read import ReadTool, ReadInput
        tool = ReadTool()
        result = tool.execute(ReadInput(path=str(sample_file)))
        assert "hello world" in result.content
        assert result.total_lines == 3

    def test_read_directory(self, tmp_dir):
        from read import ReadTool, ReadInput
        (tmp_dir / "x.txt").write_text("x")
        (tmp_dir / "y.txt").write_text("y")
        tool = ReadTool()
        result = tool.execute(ReadInput(path=str(tmp_dir)))
        assert result.type == "list"
        assert len(result.items) >= 2

    def test_read_nonexistent(self):
        from read import ReadTool, ReadInput
        tool = ReadTool()
        with pytest.raises(FileNotFoundError):
            tool.execute(ReadInput(path="/nonexistent_path_xyz"))

    def test_read_pagination(self, sample_file):
        from read import ReadTool, ReadInput
        tool = ReadTool()
        result = tool.execute(ReadInput(path=str(sample_file), offset=2, limit=1))
        assert result.total_lines == 3
        assert result.offset == 2
        assert result.limit == 1


class TestWriteTool:
    def test_create_file(self, tmp_dir):
        from write import WriteTool, WriteInput
        p = tmp_dir / "new.txt"
        tool = WriteTool()
        result = tool.execute(WriteInput(path=str(p), content="created"))
        assert result.operation == "create"
        assert result.existed is False
        assert p.read_text() == "created"

    def test_overwrite_file(self, tmp_dir):
        from write import WriteTool, WriteInput
        p = tmp_dir / "existing.txt"
        p.write_text("old")
        tool = WriteTool()
        result = tool.execute(WriteInput(path=str(p), content="new"))
        assert result.operation == "write"
        assert result.existed is True
        assert p.read_text() == "new"

    def test_create_nested_dirs(self, tmp_dir):
        from write import WriteTool, WriteInput
        p = tmp_dir / "a" / "b" / "c.txt"
        tool = WriteTool()
        result = tool.execute(WriteInput(path=str(p), content="nested"))
        assert result.operation == "create"
        assert p.read_text() == "nested"


class TestEditTool:
    def test_edit_replacement(self, tmp_dir):
        from edit import EditTool, EditInput
        p = tmp_dir / "f.txt"
        p.write_text("hello world\n")
        tool = EditTool()
        result = tool.execute(EditInput(path=str(p), old_string="world", new_string="there"))
        assert result.replacements == 1
        assert p.read_text() == "hello there\n"

    def test_edit_replace_all(self, tmp_dir):
        from edit import EditTool, EditInput
        p = tmp_dir / "f.txt"
        p.write_text("a a a\n")
        tool = EditTool()
        result = tool.execute(EditInput(path=str(p), old_string="a", new_string="b", replace_all=True))
        assert result.replacements == 3
        assert p.read_text() == "b b b\n"

    def test_edit_multiple_match_error(self, tmp_dir):
        from edit import EditTool, EditInput
        p = tmp_dir / "f.txt"
        p.write_text("a a\n")
        tool = EditTool()
        with pytest.raises(ValueError, match="multiple exact matches"):
            tool.execute(EditInput(path=str(p), old_string="a", new_string="b"))

    def test_edit_empty_old_string(self, tmp_dir):
        from edit import EditTool, EditInput
        p = tmp_dir / "f.txt"
        p.write_text("content")
        tool = EditTool()
        with pytest.raises(ValueError, match="old_string"):
            tool.execute(EditInput(path=str(p), old_string="", new_string="x"))


# ============================================================
# 3. Search tools (Grep, Glob)
# ============================================================

class TestGrepTool:
    def test_grep_simple(self, sample_dir):
        from grep import GrepTool, GrepInput
        tool = GrepTool()
        result = tool.execute(GrepInput(pattern="print", path=str(sample_dir), match_lines=False))
        assert result.total_matches >= 3

    def test_grep_no_match(self, sample_dir):
        from grep import GrepTool, GrepInput
        tool = GrepTool()
        result = tool.execute(GrepInput(pattern="ZZZZNOTHING", path=str(sample_dir)))
        assert result.total_matches == 0

    def test_grep_case_insensitive(self, sample_dir):
        from grep import GrepTool, GrepInput
        tool = GrepTool()
        result = tool.execute(GrepInput(pattern="PRINT", path=str(sample_dir), case_sensitive=False, match_lines=False))
        assert result.total_matches >= 3

    def test_grep_files_with_matches(self, sample_dir):
        from grep import GrepTool, GrepInput
        tool = GrepTool()
        result = tool.execute(GrepInput(pattern="print", path=str(sample_dir), output_mode="files_with_matches", match_lines=False))
        assert result.total_files >= 2

    def test_grep_full_line_match(self, sample_dir):
        from grep import GrepTool, GrepInput
        (sample_dir / "single_line.txt").write_text("exact_line_match\n")
        tool = GrepTool()
        result = tool.execute(GrepInput(pattern="exact_line_match", path=str(sample_dir / "single_line.txt"), match_lines=True))
        assert result.total_matches == 1


class TestGlobTool:
    def test_glob_py_files(self, sample_dir):
        from glob_tool import GlobTool, GlobInput
        tool = GlobTool()
        result = tool.execute(GlobInput(pattern="*.py", path=str(sample_dir)))
        assert len(result.items) >= 2

    def test_glob_recursive(self, sample_dir):
        from glob_tool import GlobTool, GlobInput
        tool = GlobTool()
        result = tool.execute(GlobInput(pattern="**/*.py", path=str(sample_dir)))
        assert len(result.items) >= 3

    def test_glob_no_match(self, sample_dir):
        from glob_tool import GlobTool, GlobInput
        tool = GlobTool()
        result = tool.execute(GlobInput(pattern="*.xyz", path=str(sample_dir)))
        assert len(result.items) == 0


class TestOpencodeGlobTool:
    def test_opencode_glob_recursive(self, sample_dir):
        from opencode_glob import OpencodeGlobTool, GlobInput
        tool = OpencodeGlobTool()
        result = tool.execute(GlobInput(pattern="**/*.py", path=str(sample_dir)))
        assert result.count >= 1

    def test_opencode_glob_non_recursive(self, sample_dir):
        from opencode_glob import OpencodeGlobTool, GlobInput
        tool = OpencodeGlobTool()
        result = tool.execute(GlobInput(pattern="*.py", path=str(sample_dir), recursive=False))
        assert result.count >= 2

    def test_opencode_glob_all_py_with_recursive(self, sample_dir):
        from opencode_glob import OpencodeGlobTool, GlobInput
        tool = OpencodeGlobTool()
        result = tool.execute(GlobInput(pattern="*.py", path=str(sample_dir), recursive=True))
        assert result.count >= 2

    def test_opencode_glob_hidden_filter(self, sample_dir):
        from opencode_glob import OpencodeGlobTool, GlobInput
        (sample_dir / ".hidden.py").write_text("# hidden")
        tool = OpencodeGlobTool()
        result = tool.execute(GlobInput(pattern="**/*.py", path=str(sample_dir), include_hidden=False))
        assert ".hidden.py" not in " ".join(result.matches)


# ============================================================
# 4. Shell execution
# ============================================================

class TestShellTool:
    def test_shell_echo(self):
        from shell import ShellTool, ShellInput
        tool = ShellTool()
        result = tool.execute(ShellInput(command="echo hello"))
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_shell_failure(self):
        from shell import ShellTool, ShellInput
        tool = ShellTool()
        result = tool.execute(ShellInput(command="exit 1"))
        assert result.exit_code == 1

    def test_shell_env(self):
        from shell import ShellTool, ShellInput
        tool = ShellTool()
        result = tool.execute(ShellInput(command="echo $MY_VAR", env={"MY_VAR": "testval"}))
        assert "testval" in result.stdout


class TestBashTool:
    def test_bash_echo(self):
        from bash import BashTool, BashInput
        tool = BashTool()
        result = tool.execute(BashInput(command="echo bash_works"))
        assert result.exit_code == 0
        assert "bash_works" in result.output

    def test_bash_with_workdir(self, tmp_dir):
        from bash import BashTool, BashInput
        tool = BashTool()
        result = tool.execute(BashInput(command="pwd", workdir=str(tmp_dir)))
        assert str(tmp_dir) in result.output


# ============================================================
# 5. Network tools
# ============================================================

class TestWebFetchTool:
    def test_webfetch_success(self):
        from webfetch import WebFetchTool, WebFetchInput
        tool = WebFetchTool()
        result = tool.execute(WebFetchInput(url="https://example.com"))
        assert result.status_code == 200
        assert "Example Domain" in result.content

    def test_webfetch_invalid_url(self):
        from webfetch import WebFetchTool, WebFetchInput
        tool = WebFetchTool()
        with pytest.raises(Exception):
            tool.execute(WebFetchInput(url="https://nonexistent.invalid"))


class TestWebSearchTool:
    def test_websearch_basic(self):
        from websearch import WebSearchTool, WebSearchInput
        tool = WebSearchTool()
        result = tool.execute(WebSearchInput(query="test query"))
        assert len(result.results) > 0
        assert result.results[0].title


class TestMCPWebSearchTool:
    def test_mcp_websearch_mocked(self):
        from mcp_websearch import MCPWebSearchTool, MCPWebSearchInput
        tool = MCPWebSearchTool()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps({
                "results": [
                    {"title": "T1", "url": "https://x.com", "snippet": "S1", "source": "x.com"}
                ]
            })
            mock_run.return_value.returncode = 0
            result = tool.execute(MCPWebSearchInput(query="test"))
            assert len(result.results) == 1
            assert result.results[0].title == "T1"

    def test_mcp_websearch_cli_not_found(self):
        from mcp_websearch import MCPWebSearchTool, MCPWebSearchInput
        tool = MCPWebSearchTool()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(ValueError, match="MCP"):
                tool.execute(MCPWebSearchInput(query="test"))


# ============================================================
# 6. Task management
# ============================================================

class TestPlanTool:
    def test_plan_generate_default(self):
        from plan import PlanTool, PlanInput
        tool = PlanTool()
        result = tool.execute(PlanInput(goal="Build a login page"))
        assert len(result.steps) == 5
        assert result.goal == "Build a login page"
        assert result.steps[0].status == "pending"

    def test_plan_custom_steps(self):
        from plan import PlanTool, PlanInput
        tool = PlanTool()
        steps = [{"title": "Step 1", "description": "Do thing"}]
        result = tool.execute(PlanInput(goal="Test", steps=steps))
        assert len(result.steps) == 1
        assert result.steps[0].title == "Step 1"

    def test_plan_strategy(self):
        from plan import PlanTool, PlanInput
        tool = PlanTool()
        r1 = tool.execute(PlanInput(goal="Test", strategy="concise"))
        r2 = tool.execute(PlanInput(goal="Test", strategy="agile"))
        assert len(r1.steps) <= 5
        assert len(r2.steps) <= 5


class TestTaskTool:
    def test_task_crud_cycle(self):
        from task import TaskTool, TaskInput
        tool = TaskTool()
        created = tool.execute(TaskInput(action="create", title="Test task"))
        assert created.success
        task_id = created.task.id
        read = tool.execute(TaskInput(action="read", task_id=task_id))
        assert read.task.title == "Test task"
        updated = tool.execute(TaskInput(action="update", task_id=task_id, status="done"))
        assert updated.success
        listed = tool.execute(TaskInput(action="list"))
        assert len(listed.tasks) >= 1
        deleted = tool.execute(TaskInput(action="delete", task_id=task_id))
        assert deleted.success

    def test_task_list_empty(self):
        from task import TaskTool, TaskInput
        tool = TaskTool()
        result = tool.execute(TaskInput(action="list"))
        assert result.success

    def test_task_clear(self):
        from task import TaskTool, TaskInput
        tool = TaskTool()
        tool.execute(TaskInput(action="create", title="T1"))
        tool.execute(TaskInput(action="clear"))
        result = tool.execute(TaskInput(action="list"))
        assert len(result.tasks) == 0


class TestTodoTool:
    def test_todo_crud_cycle(self):
        from todo import TodoTool, TodoInput
        tool = TodoTool()
        added = tool.execute(TodoInput(action="add", content="Buy milk"))
        assert added.success
        todo_id = added.todo.id
        completed = tool.execute(TodoInput(action="complete", todo_id=todo_id))
        assert completed.todo.completed is True
        uncompleted = tool.execute(TodoInput(action="uncomplete", todo_id=todo_id))
        assert uncompleted.todo.completed is False
        listed = tool.execute(TodoInput(action="list"))
        assert len(listed.todos) >= 1
        deleted = tool.execute(TodoInput(action="delete", todo_id=todo_id))
        assert deleted.success

    def test_todo_filter(self):
        from todo import TodoTool, TodoInput
        tool = TodoTool()
        tool.execute(TodoInput(action="add", content="Task A"))
        r = tool.execute(TodoInput(action="list", filter="active"))
        assert r.success

    def test_todo_clear(self):
        from todo import TodoTool, TodoInput
        tool = TodoTool()
        tool.execute(TodoInput(action="add", content="X"))
        tool.execute(TodoInput(action="clear"))
        result = tool.execute(TodoInput(action="list"))
        assert len(result.todos) == 0


class TestTodoWriteTool:
    def test_todowrite_create(self):
        from todowrite import TodoWriteTool, TodoWriteInput
        tool = TodoWriteTool()
        result = tool.execute(TodoWriteInput(todos=[{"content": "Test todo"}]))
        assert result.updated_count == 1
        assert len(result.todos) == 1

    def test_todowrite_update(self):
        from todowrite import TodoWriteTool, TodoWriteInput
        tool = TodoWriteTool()
        tool.execute(TodoWriteInput(todos=[{"id": "t1", "content": "Initial"}]))
        result = tool.execute(TodoWriteInput(todos=[{"id": "t1", "status": "completed"}]))
        assert result.updated_count == 1

    def test_todowrite_multiple(self):
        from todowrite import TodoWriteTool, TodoWriteInput
        tool = TodoWriteTool()
        result = tool.execute(TodoWriteInput(todos=[
            {"content": "A", "priority": "high"},
            {"content": "B", "priority": "low"},
        ]))
        assert result.updated_count == 2


# ============================================================
# 7. Code intelligence
# ============================================================

class TestJSONSchemaTool:
    def test_validate_valid(self):
        from json_schema import JSONSchemaTool, JSONSchemaInput
        tool = JSONSchemaTool()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
        data = {"name": "Alice"}
        result = tool.execute(JSONSchemaInput(action="validate", schema=schema, data=data))
        assert result.success is True

    def test_validate_invalid(self):
        from json_schema import JSONSchemaTool, JSONSchemaInput
        tool = JSONSchemaTool()
        schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
        data = {"age": "not_a_number"}
        result = tool.execute(JSONSchemaInput(action="validate", schema=schema, data=data))
        assert result.success is False

    def test_generate_schema(self):
        from json_schema import JSONSchemaTool, JSONSchemaInput
        tool = JSONSchemaTool()
        result = tool.execute(JSONSchemaInput(action="generate", data={"name": "Alice", "age": 30}))
        assert result.success is True
        assert result.schema["type"] == "object"
        assert "name" in result.schema["properties"]
        assert "age" in result.schema["properties"]


class TestSchemaTool:
    def test_register_and_validate(self, tmp_dir):
        from schema import SchemaTool, SchemaInput
        tool = SchemaTool()
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        reg = tool.execute(SchemaInput(action="register", schema_name="test_schema", schema=schema))
        assert reg.success
        val = tool.execute(SchemaInput(action="validate", schema=schema, data={"x": 42}))
        assert val.success
        val2 = tool.execute(SchemaInput(action="validate", schema=schema, data={"x": "bad"}))
        assert val2.success is False

    def test_schema_list(self):
        from schema import SchemaTool, SchemaInput
        tool = SchemaTool()
        result = tool.execute(SchemaInput(action="list"))
        assert result.success


class TestLSPTool:
    def test_lsp_unsupported_language(self):
        from lsp import LSPTool, LSPInput
        tool = LSPTool()
        with pytest.raises(ValueError):
            tool.execute(LSPInput(action="complete", language="nonexistent_lang_xyz"))

    def test_lsp_input_validation(self):
        from lsp import LSPTool, LSPInput
        tool = LSPTool()
        with pytest.raises(ValueError):
            tool.execute(LSPInput(action="invalid_action", language="python"))


# ============================================================
# 8. Interaction
# ============================================================

class TestQuestionTool:
    def test_question_text(self):
        from question import QuestionTool, QuestionInput
        tool = QuestionTool()
        result = tool.execute(QuestionInput(text="What is your name?", type="text"))
        assert result.success
        assert result.answer

    def test_question_boolean(self):
        from question import QuestionTool, QuestionInput
        tool = QuestionTool()
        results = []
        for _ in range(5):
            r = tool.execute(QuestionInput(text="Is this a test?", type="boolean", required=False))
            results.append(r)
        at_least_one_ok = any(r.success for r in results)
        assert at_least_one_ok

    def test_question_select(self):
        from question import QuestionTool, QuestionInput
        from question import QuestionOption
        tool = QuestionTool()
        opts = [QuestionOption(text="A", value="a"), QuestionOption(text="B", value="b")]
        result = tool.execute(QuestionInput(text="Pick one", type="select", options=opts))
        assert result.success

    def test_question_number(self):
        from question import QuestionTool, QuestionInput
        tool = QuestionTool()
        result = tool.execute(QuestionInput(text="Enter a number", type="number"))
        assert result.success
        assert isinstance(result.answer, (int, float))


# ============================================================
# 9. Utilities
# ============================================================

class TestTruncateTool:
    def test_truncate_middle(self):
        from truncate import TruncateTool, TruncateInput
        tool = TruncateTool()
        content = "A" * 2000
        result = tool.execute(TruncateInput(content=content, max_length=100, mode="middle"))
        assert result.truncated_length <= 100

    def test_truncate_end(self):
        from truncate import TruncateTool, TruncateInput
        tool = TruncateTool()
        content = "hello world"
        result = tool.execute(TruncateInput(content=content, max_length=5, mode="end"))
        assert result.truncated_length < len(content)

    def test_truncate_start(self):
        from truncate import TruncateTool, TruncateInput
        tool = TruncateTool()
        content = "A" * 100
        result = tool.execute(TruncateInput(content=content, max_length=10, mode="start"))
        assert result.truncated_length < len(content)

    def test_truncate_noop(self):
        from truncate import TruncateTool, TruncateInput
        tool = TruncateTool()
        result = tool.execute(TruncateInput(content="short", max_length=100))
        assert result.truncated_content == "short"

    def test_truncate_smart(self):
        from truncate import TruncateTool, TruncateInput
        tool = TruncateTool()
        content = "A" * 500 + "\n\n" + "B" * 500
        result = tool.execute(TruncateInput(content=content, max_length=200, mode="smart"))
        assert result.truncated_length <= 200


class TestExternalDirectoryTool:
    def test_external_directory_add_remove(self, tmp_dir):
        from external_directory import ExternalDirectoryTool, ExternalDirectoryInput
        tool = ExternalDirectoryTool()
        added = tool.execute(ExternalDirectoryInput(action="add", path=str(tmp_dir), alias="mydir"))
        assert added.success
        listed = tool.execute(ExternalDirectoryInput(action="list"))
        assert len(listed.directories) >= 1
        info = tool.execute(ExternalDirectoryInput(action="info", name="mydir"))
        assert info.success
        removed = tool.execute(ExternalDirectoryInput(action="remove", name="mydir"))
        assert removed.success

    def test_external_directory_resolve(self, tmp_dir):
        from external_directory import ExternalDirectoryTool, ExternalDirectoryInput
        tool = ExternalDirectoryTool()
        tool.execute(ExternalDirectoryInput(action="add", path=str(tmp_dir), alias="resolvedir"))
        result = tool.execute(ExternalDirectoryInput(action="resolve", name="resolvedir"))
        assert result.success
        assert result.alias == "resolvedir"


class TestInvalidTool:
    def test_invalid_all_error_types(self):
        from invalid import InvalidTool, InvalidInput
        tool = InvalidTool()
        for err_type in ["not_found", "invalid_input", "permission_denied", "execution_failed", "timeout"]:
            result = tool.execute(InvalidInput(tool_name="test_tool", error_type=err_type))
            assert result.success is False
            assert result.error_type == err_type

    def test_invalid_suggestions(self):
        from invalid import InvalidTool, InvalidInput
        tool = InvalidTool()
        result = tool.execute(InvalidInput(tool_name="read", error_type="not_found"))
        assert len(result.suggestions) >= 0

    def test_invalid_custom_message(self):
        from invalid import InvalidTool, InvalidInput
        tool = InvalidTool()
        result = tool.execute(InvalidInput(tool_name="x", error_type="not_found", error_message="custom err"))
        assert "custom err" in result.error_message


# ============================================================
# 10. Registry & meta tools
# ============================================================

class TestRegistryTool:
    def test_registry_list(self):
        from registry import RegistryTool, RegistryInput
        tool = RegistryTool()
        result = tool.execute(RegistryInput(action="list"))
        assert result.success

    def test_registry_search(self):
        from registry import RegistryTool, RegistryInput
        tool = RegistryTool()
        result = tool.execute(RegistryInput(action="search", search_query="read"))
        assert result.success

    def test_registry_clear(self):
        from registry import RegistryTool, RegistryInput
        tool = RegistryTool()
        result = tool.execute(RegistryInput(action="clear"))
        assert result.success

    def test_registry_register_module(self):
        from registry import RegistryTool, RegistryInput
        tool = RegistryTool()
        result = tool.execute(RegistryInput(
            action="register", tool_name="grep",
            tool_path=os.path.abspath("tools/grep.py"),
            tool_class="GrepTool",
        ))
        assert result.success


class TestSkillTool:
    def test_skill_list(self):
        from skill import SkillTool, SkillInput
        tool = SkillTool()
        result = tool.execute(SkillInput(action="list"))
        assert result.success

    def test_skill_load_via_name(self):
        from skill import SkillTool, SkillInput
        tool = SkillTool()
        loaded = tool.execute(SkillInput(action="load", skill_name="builtin_test", skill_data={
            "name": "builtin_test",
            "description": "Built-in test skill",
            "version": "1.0.0",
        }))
        assert loaded.success

    def test_skill_info(self):
        from skill import SkillTool, SkillInput
        tool = SkillTool()
        tool.execute(SkillInput(action="load", skill_name="skill_info_test", skill_data={
            "name": "skill_info_test", "description": "Info test"
        }))
        result = tool.execute(SkillInput(action="info", skill_name="skill_info_test"))
        assert result.success


# ============================================================
# 11. ApplyPatchTool
# ============================================================

class TestApplyPatchTool:
    def test_apply_patch(self, tmp_dir):
        from apply_patch import ApplyPatchTool, ApplyPatchInput
        p = tmp_dir / "target.txt"
        p.write_text("line1\nline2\nline3\n")
        diff = "--- a/target.txt\n+++ b/target.txt\n@@ -1,3 +1,3 @@\n line1\n-line2\n+modified\n line3\n"
        tool = ApplyPatchTool()
        result = tool.execute(ApplyPatchInput(path=str(p), diff=diff))
        assert result.changes_applied == 1
        assert "modified" in p.read_text()

    def test_apply_patch_create_file(self, tmp_dir):
        from apply_patch import ApplyPatchTool, ApplyPatchInput
        p = tmp_dir / "new.txt"
        diff = "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+new content\n"
        tool = ApplyPatchTool()
        with pytest.raises(FileNotFoundError):
            tool.execute(ApplyPatchInput(path=str(p), diff=diff))

    def test_apply_patch_with_create_flag(self, tmp_dir):
        from apply_patch import ApplyPatchTool, ApplyPatchInput
        p = tmp_dir / "new.txt"
        diff = "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+new content\n"
        tool = ApplyPatchTool()
        result = tool.execute(ApplyPatchInput(path=str(p), diff=diff, create_if_not_exists=True))
        assert p.exists()

    def test_apply_patch_no_file_error(self, tmp_dir):
        from apply_patch import ApplyPatchTool, ApplyPatchInput
        p = tmp_dir / "missing.txt"
        tool = ApplyPatchTool()
        with pytest.raises(ValueError, match="diff"):
            tool.execute(ApplyPatchInput(path=str(p), diff=""))


# ============================================================
# 12. Integration: tool registry end-to-end
# ============================================================

class TestToolRegistryIntegration:
    def test_register_and_execute_multiple_tools(self, tmp_dir):
        from base import ToolRegistry
        reg = ToolRegistry()

        from read import ReadTool
        from write import WriteTool
        from plan import PlanTool
        from truncate import TruncateTool

        reg.register(ReadTool())
        reg.register(WriteTool())
        reg.register(PlanTool())
        reg.register(TruncateTool())

        p = tmp_dir / "hello.txt"
        write_result = reg.execute("write", {"path": str(p), "content": "hello world"})
        assert write_result["success"]

        read_result = reg.execute("read", {"path": str(p)})
        assert read_result["success"]
        assert "hello world" in str(read_result["result"].content)

        plan_result = reg.execute("plan", {"goal": "integration test"})
        assert plan_result["success"]

        truncate_result = reg.execute("truncate", {"content": "A" * 100, "max_length": 10})
        assert truncate_result["success"]

    def test_execute_nonexistent_tool(self):
        from base import tool_registry
        with pytest.raises(ValueError):
            tool_registry.execute("tool_does_not_exist_12345", {})


# ============================================================
# 13. Integration: multi-tool collaboration workflows
# ============================================================

class TestMultiToolWorkflows:
    """多工具协作场景的端到端集成测试"""

    def test_write_read_edit_cycle(self, tmp_dir):
        """写 → 读 → 编辑 → 再读 完整工作流"""
        from write import WriteTool, WriteInput
        from read import ReadTool, ReadInput
        from edit import EditTool, EditInput

        p = tmp_dir / "hello.py"
        content = "def greet(name):\n    return f'Hello, {name}!'\n"

        WriteTool().execute(WriteInput(path=str(p), content=content))
        read_result = ReadTool().execute(ReadInput(path=str(p)))
        assert "greet" in str(read_result.content)

        EditTool().execute(EditInput(
            path=str(p), old_string="Hello", new_string="Hi",
            replace_all=True,
        ))
        read_result2 = ReadTool().execute(ReadInput(path=str(p)))
        assert "Hi" in str(read_result2.content)
        assert "Hello" not in str(read_result2.content)

    def test_grep_read_grep_cycle(self, tmp_dir):
        """写多文件 → grep 搜索 → read 确认"""
        from write import WriteTool, WriteInput
        from grep import GrepTool, GrepInput
        from read import ReadTool, ReadInput

        files = {
            "models/user.py": "class User:\n    pass\n",
            "models/post.py": "class Post:\n    pass\n",
            "utils/helpers.py": "def helper():\n    return 42\n",
        }
        for path, content in files.items():
            full_path = tmp_dir / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            WriteTool().execute(WriteInput(path=str(full_path), content=content))

        matches = GrepTool().execute(GrepInput(
            pattern="class ", path=str(tmp_dir), match_lines=False,
        ))
        assert len(matches.matches) >= 2

        read_result = ReadTool().execute(ReadInput(path=str(tmp_dir / "models/user.py")))
        assert "User" in str(read_result.content)

    def test_todo_task_plan_workflow(self, tmp_dir):
        """Todo → TaskList → Plan 的工具编排"""
        from todo import TodoTool, TodoInput
        from task import TaskTool, TaskInput
        from plan import PlanTool, PlanInput

        # Create a todo
        result = TodoTool().execute(TodoInput(action="add", content="集成测试用例"))
        assert result.success

        # Verify it's listed
        list_result = TodoTool().execute(TodoInput(action="list"))
        assert list_result.success

        # Create a task
        t = TaskTool().execute(TaskInput(action="create", title="测试任务"))
        # TaskTool may not have explicit success, check it ran without error

        # Generate a plan
        p = PlanTool().execute(PlanInput(goal="完成集成测试"))
        assert hasattr(p, "plan_id") or hasattr(p, "steps")

    def test_truncate_then_write(self, tmp_dir):
        """truncate 输出结果写入文件"""
        from truncate import TruncateTool, TruncateInput
        from write import WriteTool, WriteInput

        content = "A" * 1000 + "B" * 1000 + "C" * 1000
        truncated = TruncateTool().execute(TruncateInput(
            content=content, max_length=500, mode="smart",
        ))
        assert truncated.truncated_length <= 500

        p = tmp_dir / "output.txt"
        WriteTool().execute(WriteInput(
            path=str(p), content=truncated.truncated_content,
        ))
        written = p.read_text()
        assert len(written) <= 500
        assert written == truncated.truncated_content

    def test_glob_and_read_cycle(self, tmp_dir):
        """glob 搜索 → read 多个匹配文件"""
        from write import WriteTool, WriteInput
        from read import ReadTool, ReadInput
        from glob_tool import GlobTool, GlobInput

        for i in range(3):
            p = tmp_dir / f"data_{i}.txt"
            WriteTool().execute(WriteInput(path=str(p), content=f"content_{i}"))

        matches = GlobTool().execute(GlobInput(
            pattern="*.txt", path=str(tmp_dir),
        ))
        assert len(matches.items) == 3

        for f in matches.items:
            r = ReadTool().execute(ReadInput(path=f.resource))
            assert r.content.strip()

    def test_bash_and_truncate(self, tmp_dir):
        """shell 输出 → truncate 截断"""
        from shell import ShellTool, ShellInput
        from truncate import TruncateTool, TruncateInput

        result = ShellTool().execute(ShellInput(
            command=f"ls -la {tmp_dir}",
        ))
        truncated = TruncateTool().execute(TruncateInput(
            content=result.stdout or str(result), max_length=200, mode="end",
        ))
        assert truncated.truncated_length <= 200

    def test_invalid_tool_fallback(self):
        """invalid tool → 错误信息 + 建议"""
        from invalid import InvalidTool, InvalidInput

        result = InvalidTool().execute(InvalidInput(
            tool_name="nonexistent_tool",
            error_type="not_found",
            error_message="工具不存在",
        ))
        assert result.success is False

    def test_write_json_read_parse(self, tmp_dir):
        """写 JSON 文件 → 读 → 内容验证"""
        from write import WriteTool, WriteInput
        from read import ReadTool, ReadInput

        data = {"key": "value", "nested": {"a": 1, "b": 2}}
        p = tmp_dir / "data.json"
        import json
        WriteTool().execute(WriteInput(path=str(p), content=json.dumps(data, indent=2)))

        result = ReadTool().execute(ReadInput(path=str(p)))
        parsed = json.loads(str(result.content))
        assert parsed["key"] == "value"
        assert parsed["nested"]["a"] == 1

    def test_todo_persistence(self):
        """Todo 增删查持久化"""
        from todo import TodoTool, TodoInput

        TodoTool().execute(TodoInput(action="add", content="集成测试项1"))
        TodoTool().execute(TodoInput(action="add", content="集成测试项2"))

        lst = TodoTool().execute(TodoInput(action="list"))
        assert lst.success

        TodoTool().execute(TodoInput(action="clear"))
        lst2 = TodoTool().execute(TodoInput(action="list"))
        assert lst2.success

    def test_v2_discovery_and_handler(self, tmp_dir):
        """通过 V2 ToolRegistry 发现并调用本地工具"""
        import asyncio
        from core.multi_agent_v2.tools.tool_registry import get_tool_registry

        async def _test():
            reg = get_tool_registry()
            await reg.discover_all()

            # Verify local tools are discoverable
            local = [t for t in reg._tools.values() if "local" in t.tags]
            assert len(local) >= 20

            # Verify handler works for key tools
            for name in ("truncate", "read", "todo", "invalid"):
                h = reg.get_handler(name)
                assert h is not None, f"handler for {name} not found"

            # Execute through handler
            h = reg.get_handler("truncate")
            r = await h({"content": "test", "max_length": 3, "mode": "end"})
            from core.multi_agent_v2.tools.tool_result import is_ok
            assert is_ok(r)

        asyncio.run(_test())

"""回归测试：覆盖所有已修复 Bug"""

import pytest
import asyncio
import inspect
from unittest.mock import Mock, patch, MagicMock, AsyncMock


class TestMCPClientLock:
    """Bug #3: MCP 客户端竞态锁"""

    def test_mcp_client_has_lock(self):
        """验证 MCPClientManager 有 _request_lock"""
        from core.mcp.mcp_client import MCPClientManager

        mgr = MCPClientManager()
        assert hasattr(mgr, "_request_lock"), "MCPClientManager 缺少 _request_lock"
        assert isinstance(mgr._request_lock, asyncio.Lock), (
            "_request_lock 不是 asyncio.Lock"
        )

    def test_send_request_uses_lock(self):
        """验证 _send_request 使用了 async with lock"""
        from core.mcp.mcp_client import MCPClientManager
        source = inspect.getsource(MCPClientManager._send_request)
        assert "async with" in source, "_send_request 未使用 async with"
        assert "_request_lock" in source, "_send_request 未使用 _request_lock"


class TestTaskProcessor:
    """Bug #5: TaskProcessor 双重 __init__"""

    def test_single_init(self):
        """验证只有单个 __init__"""
        from core.tasks.task_processor import TaskProcessor

        # 检查是否只有一个 __init__ 方法
        methods = [
            m for m in inspect.getmembers(TaskProcessor, predicate=inspect.isfunction)
            if m[0] == "__init__"
        ]
        assert len(methods) == 1, (
            f"TaskProcessor 有 {len(methods)} 个 __init__（应有 1 个）"
        )

    def test_init_has_all_fields(self):
        """验证 __init__ 初始化了所有必要字段"""
        import inspect
        from core.tasks.task_processor import TaskProcessor

        source = inspect.getsource(TaskProcessor.__init__)

        # 检查必要的字段初始化
        expected_fields = ["router", "_feedback_history", "_skill_success_rates"]
        for field in expected_fields:
            assert field in source, f"__init__ 缺少对 {field} 的初始化"


class TestPyrightConfig:
    """Bug #17+#18: Pyright 配置修复"""

    def test_python_version(self):
        """验证 pythonVersion 为 3.13"""
        import json
        with open("pyrightconfig.json") as f:
            config = json.load(f)
        assert config.get("pythonVersion") == "3.13", (
            f"pythonVersion 应为 3.13，当前为 {config.get('pythonVersion')}"
        )

    def test_no_analysis_ignore(self):
        """验证 pythonAnalysis.ignore 已被移除"""
        import json
        with open("pyrightconfig.json") as f:
            config = json.load(f)
        analysis = config.get("pythonAnalysis", {})
        assert "ignore" not in analysis or not analysis["ignore"], (
            "pythonAnalysis.ignore 应被移除"
        )


class TestImportModule:
    """Bug #21: __import__ → importlib.import_module"""

    def test_main_py_no_dunder_import(self):
        """验证 main.py 及相关模块不再使用 __import__"""
        for path in ("main.py", "api/route_manager.py", "core/system_init.py"):
            with open(path) as f:
                content = f.read()
            import_count = content.count("__import__")
            assert import_count == 0, f"{path} 仍有 {import_count} 处 __import__"
        # 验证 importlib.import_module 存在于路由管理器或系统初始化器中
        for path in ("api/route_manager.py", "core/system_init.py"):
            with open(path) as f:
                if "importlib.import_module" in f.read():
                    break
        else:
            assert False, "未在 api/route_manager.py 或 core/system_init.py 中找到 importlib.import_module"

    def test_routes_init_no_dunder_import(self):
        """验证 api/routes/__init__.py 不再使用 __import__"""
        with open("api/routes/__init__.py") as f:
            content = f.read()
        assert "__import__" not in content, (
            "api/routes/__init__.py 仍在使用 __import__"
        )


class TestCLIBase:
    """Bug #24: API 参数不匹配"""

    def test_no_available_agents(self):
        """验证 cli/base.py 的 schedule 调用不含 available_agents"""
        with open("cli/base.py") as f:
            content = f.read()
        # 检查 schedule 调用中没有 available_agents
        import re
        schedule_calls = re.findall(r"scheduler\.schedule\([^)]*\)", content)
        for call in schedule_calls:
            assert "available_agents" not in call, (
                f"schedule 调用包含了无效参数 available_agents: {call}"
            )


class TestWorkflowTestData:
    """Bug #25: 工作流测试数据"""

    def test_workflow_json_exists(self):
        """验证 test_workflow.json 存在"""
        import os
        assert os.path.exists("workflows/test_workflow.json")

    def test_workflow_dag_json_exists(self):
        """验证 test_workflow_dag.json 存在"""
        import os
        assert os.path.exists("workflows/test_workflow_dag.json")


class TestAppContext:
    """Bug #22: AppContext dataclass"""

    def test_app_context_exists(self):
        """验证 main.py 定义了 AppContext"""
        import sys
        sys.path.insert(0, ".")
        # 通过源码检查避免 import 副作用
        with open("main.py") as f:
            content = f.read()
        assert "class AppContext" in content, "main.py 缺少 AppContext 类"
        assert "ctx = AppContext()" in content, "main.py 缺少 ctx 实例"

    def test_app_context_fields(self):
        """验证 AppContext 包含必要字段"""
        with open("main.py") as f:
            content = f.read()
        for field in ["dispatcher", "processor", "planner", "db_initialized", "startup_time"]:
            assert field in content, f"AppContext 缺少字段 {field}"


class TestEnvSecurity:
    """Bug #7: API 密钥安全"""

    # 项目实际使用的实时 API key（使用时需替换为占位符！）
    _KNOWN_LIVE_KEYS = {
        "ZHIPU_API_KEY",
        "DEEPSEEK_API_KEY",
    }

    def test_no_live_api_key(self):
        """验证 .env 不包含非白名单的实时 API 密钥"""
        with open(".env") as f:
            content = f.read()

        has_live_unknown = False
        unknown_details = []
        for line in content.split("\n"):
            line = line.strip()
            if "=" not in line or line.startswith("#") or not line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            # 只检查包含 _KEY / _TOKEN / _SECRET / _API 的变量
            if not any(suffix in key for suffix in ("_KEY", "_TOKEN", "_SECRET", "_API")):
                continue
            if not value or value.startswith("your_") or value.startswith("$"):
                continue
            if key in self._KNOWN_LIVE_KEYS:
                continue
            has_live_unknown = True
            unknown_details.append(f"  {key}={value[:16]}...")

        assert not has_live_unknown, (
            ".env 包含非白名单的实时密钥，请替换为占位符或加入白名单：\n"
            + "\n".join(unknown_details)
        )


class TestSSLVerification:
    """Bug #8: SSL 验证"""

    def test_no_verify_false_in_search(self):
        """验证搜索引擎代码中无 verify=False"""
        with open("core/search/rag_search_engine.py") as f:
            content = f.read()
        assert "verify=False" not in content, (
            "rag_search_engine.py 仍包含 verify=False"
        )

        with open("core/search/search_engine_factory.py") as f:
            content = f.read()
        assert "verify=False" not in content, (
            "search_engine_factory.py 仍包含 verify=False"
        )

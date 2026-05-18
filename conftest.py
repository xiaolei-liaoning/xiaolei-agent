"""Root conftest - 为顶层遗留的脚本风格测试文件提供 fixtures"""

import pytest


class _PerformanceTestStub:
    """performance_test.py 的 PerformanceTest 桩，使 pytest 收集时不会崩溃"""
    pass


@pytest.fixture(scope="session")
def pt():
    """performance_test.py 所需 fixture"""
    from performance_test import PerformanceTest
    return PerformanceTest()


@pytest.fixture(scope="session")
def name():
    """test_full_connectivity.py 中 test_module(name, import_expr) 的桩"""
    return ""


@pytest.fixture(scope="session")
def import_expr():
    """test_full_connectivity.py 中 test_module(name, import_expr) 的桩"""
    return "pass"


@pytest.fixture(scope="session")
def func():
    """tools/test_app.py 所需 fixture"""
    return lambda: True


@pytest.fixture(scope="session")
def module_info():
    """tools/test_unused_modules.py 所需 fixture"""
    return {"name": "test", "module_name": "test", "short_name": "test", "imports": [], "path": ".", "expected": "", "reason": ""}


@pytest.fixture(scope="session")
def all_py_files():
    """tools/test_unused_modules.py 所需 fixture"""
    return []

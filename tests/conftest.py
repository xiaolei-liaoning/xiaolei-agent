"""小雷版 agent 测试全局 conftest — 参考 hermes-agent/tests/conftest.py 封闭宇宙设计

四大不变量（autouse fixture 自动生效，测试自己不用写）：

1. 凭据环境变量清空 — 本地 API key 不能泄进测试；
   真实 LLM 测试必须显式打 real_llm 标记才恢复
2. 隔离状态目录 — XIAOLEI_TEST_HOME 指到临时目录；
   核心代码读 ~/.xiaolei 的路径在测试中被重定向
3. 确定性 — TZ=UTC、PYTHONHASHSEED=0
4. 分层标记 — real_llm / slow 测试默认跳过（配合 pyproject addopts）
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# 项目根加入 sys.path（tests/ 在仓库根下）
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── 收集期之前固化生产路径（学 hermes: ORDER MATTERS）──
# 在任何 test 模块 import 之前捕获真实 ~/.xiaolei，
# 写保护 guard 用它判断"这次写是否打到生产目录"
_PRE_SANDBOX_XIAOLEI = os.path.expanduser("~/.xiaolei")


def _points_at_production_xiaolei(value: str) -> bool:
    """给定路径是否解析到真实生产 ~/.xiaolei。生产目录的写入必须拒绝。"""
    if not value:
        return False
    try:
        return Path(value).expanduser().resolve() == Path(_PRE_SANDBOX_XIAOLEI).resolve()
    except (OSError, ValueError):
        return False


# 凭据形态环境变量：以这些后缀结尾 = 凭据（hermes 同款规则）
_CREDENTIAL_SUFFIXES = (
    "_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_CREDENTIALS", "_AUTH",
)

# 需要保留的非凭据（按需追加）
_CREDENTIAL_EXEMPT = set()

# 真实目录中测试真正需要的最小凭据（real_llm 标记的测试才的环境）
_REAL_LLM_KEEP = ("DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "LLM_API_KEY")


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch, request):
    """每个测试自动生效的环境隔离（hermes _hermetic_environment 平替）。

    - 凭据环境变量清空（real_llm 标记的测试豁免）
    - TZ / PYTHONHASHSEED 固定
    - XIAOLEI_HOME / 状态目录指向临时目录
    """
    # 1) 清凭据（real_llm 测试豁免，让它们能用真 key 调真模型）
    is_real_llm = request.node.get_closest_marker("real_llm") is not None
    for var in list(os.environ.keys()):
        if var in _CREDENTIAL_EXEMPT:
            continue
        if any(var.endswith(sfx) for sfx in _CREDENTIAL_SUFFIXES):
            if is_real_llm and var in _REAL_LLM_KEEP:
                continue
            monkeypatch.delenv(var, raising=False)

    # 2) 确定性
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("PYTHONHASHSEED", "0")

    # 3) 状态目录沙盒 — 核心代码用 ~/.xiaolei 的地方在测试中重定向
    #    通过环境变量 XIAOLEI_STATE_DIR 让代码走 tempdir（项目侧只读此变量时生效）
    tmp_state = tempfile.mkdtemp(prefix="xiaolei_test_state_")
    monkeypatch.setenv("XIAOLEI_STATE_DIR", tmp_state)
    monkeypatch.setenv("XIAOLEI_TEST_MODE", "1")

    yield tmp_state


@pytest.fixture(autouse=True)
def _production_dir_write_guard(request):
    """写保护 — 测试若试图写真实 ~/.xiaolei 直接失败（hermes kanban guard 平替）。

    用 deny-list 判断：任何 open(w)/mkdir 到 resolve 后等于
    _PRE_SANDBOX_XIAOLEI 的路径 → 报错并指出该测试在污染生产目录。
    """
    real_root = Path(_PRE_SANDBOX_XIAOLEI)
    if not real_root.is_dir():
        yield
        return
    real_root_resolved = real_root.resolve()

    # 检测点：tests 显式调用 helper 或直接 open。这里 guard 最常见的写路径——
    # 通过 os.walk 拦截过于侵入，改为对 builtins.open 以写模式开生产路径时报错
    import builtins
    _orig_open = builtins.open
    in_test = True

    def _guarded_open(file, mode="r", *args, **kwargs):
        if not (in_test and isinstance(file, (str, Path))):
            return _orig_open(file, mode, *args, **kwargs)
        try:
            f = Path(file)
            if any(m in mode for m in ("w", "a", "x")) and f.is_absolute():
                resolved = f.expanduser().resolve()
                if resolved == real_root_resolved or real_root_resolved in resolved.parents:
                    raise AssertionError(
                        f"测试试图写入生产目录: {resolved}\n"
                        f"测试必须通过 tmp_path / _hermetic_environment 的临时目录写。"
                    )
        except (OSError, ValueError):
            pass
        return _orig_open(file, mode, *args, **kwargs)

    builtins.open = _guarded_open
    yield
    builtins.open = _orig_open


@pytest.fixture(autouse=True)
def _neutralize_webbrowser(monkeypatch):
    """中和 webbrowser — 测试想开浏览器只记录不真开（hermes 同款）"""
    import webbrowser as _wb
    opened = []

    def _record(url=None, *_a, **_kw):
        opened.append(url)
        return True

    for name in ("open", "open_new", "open_new_tab"):
        monkeypatch.setattr(_wb, name, _record, raising=False)
    monkeypatch.setattr(_wb, "get", lambda *_a, **_kw: _record, raising=False)
    return opened


@pytest.fixture(autouse=True)
def _no_network_outside_marker(monkeypatch, request):
    """非 real_network 标记的测试禁止真实外网请求。

    socket.socket.connect 到非 localhost 地址 → 直接 raise，防静默外呼
    （挂起测试的第二大根源）。real_network 标记的测试豁免。
    """
    if request.node.get_closest_marker("real_network") is not None:
        yield
        return
    import socket as _socket

    _orig_connect = _socket.socket.connect
    _blocked = []

    def _guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        # localhost / 内网回环豁免
        if isinstance(host, str) and host in ("127.0.0.1", "localhost", "::1"):
            return _orig_connect(self, address)
        _blocked.append(host)
        raise AssertionError(
            f"测试试图访问外网: {host}。\n"
            f"如需真实网络，加 @pytest.mark.real_network 标记；"
            f"否则请 mock（AsyncMock/MagicMock patch requests/httpx）。\n"
            f"被拦截的连接: {_blocked[:3]}"
        )

    monkeypatch.setattr(_socket.socket, "connect", _guarded_connect)
    yield


def pytest_configure(config):
    """注册项目自定义 marker（必须在配置期，与 pyproject 联动）"""
    for marker, desc in [
        ("real_llm", "会调真实 LLM API — 默认 skip，XIAOLEI_REAL_LLM=1 才跑"),
        ("real_network", "会访问真实外网 — 默认 skip，XIAOLEI_REAL_NETWORK=1 才跑"),
        ("slow", "超过 30s 的测试 — 默认跳过"),
        ("unit", "纯单元测试（默认都跑）"),
    ]:
        config.addinivalue_line("markers", f"{marker}: {desc}")


def pytest_collection_modifyitems(config, items):
    """收集期分层 — 未显式标记的 real_llm/real_network 测试自动 skip。
    环境变量 XIAOLEI_REAL_LLM=1 / XIAOLEI_REAL_NETWORK=1 显式解锁。"""
    want_real_llm = os.environ.get("XIAOLEI_REAL_LLM", "") == "1"
    want_real_network = os.environ.get("XIAOLEI_REAL_NETWORK", "") == "1"
    for item in items:
        if item.get_closest_marker("real_llm") and not want_real_llm:
            item.add_marker(pytest.mark.skip(reason="real_llm 测试需要 XIAOLEI_REAL_LLM=1"))
        if item.get_closest_marker("real_network") and not want_real_network:
            item.add_marker(pytest.mark.skip(reason="real_network 测试需要 XIAOLEI_REAL_NETWORK=1"))

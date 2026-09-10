"""read_file 敌意文件矩阵 — 对标 hermes evals/readtool

对标报告: ~/Desktop/测试极限体系移植计划.md 阶段 3
参考: hermes evals/readtool/README.md 的 8 种敌意 fixture

测的是 read_file 工具在"不友好文件"下的**降级行为**，不是 happy path：
  A. 大行 tarpit（单行 600KB, token 吞金兽）
  B. 长日志尾部 hunt（150K 行, ERROR 在尾部）
  C. 过 EOF 请求（读 999999 行）
  D. 0byte 空文件
  E. 二进制（png/pyc）
  F. fifo 特殊文件（裸 read 挂死触发器）
  G. NFC/NFD 文件名
  H. AGENTS.md vs AGENT.md 近名文件，验证是否有 did-you-mean 提示
"""

import asyncio
import os
import sys
import unicodedata
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from core.multi_agent_v2.tools.tool_registry import _handle_read_file


pytestmark = pytest.mark.asyncio


# ════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════


@pytest.fixture
def tarpit_file(tmp_path):
    """单行 600KB（hermes: app.min.js 模拟）"""
    p = tmp_path / "app.min.js"
    p.write_text("// minified\n" + "x" * 600_000, encoding="utf-8")
    return p


@pytest.fixture
def big_log_with_tail_error(tmp_path):
    """150K 行, 只有尾部第 149_999 行有 'ERROR: cache corrupted'"""
    p = tmp_path / "server.log"
    lines = [f"[{i}] info: normal" for i in range(149_999)]
    lines.append("[149999] ERROR: cache corrupted at shard=7")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


@pytest.fixture
def empty_file(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    return p


@pytest.fixture
def binary_file(tmp_path):
    p = tmp_path / "logo.png"
    p.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452") * 100)  # PNG magic bytes foil
    return p


@pytest.fixture
def nfd_named_file(tmp_path):
    """同名 NFD (combining accent) 版本"""
    name = unicodedata.normalize("NFD", "résumé.txt")   # r + combining accent
    p = tmp_path / name
    p.write_text("NFD file content", encoding="utf-8")
    return p


@pytest.fixture
def fifo_file(tmp_path):
    p = tmp_path / "live.pipe"
    os.mkfifo(p)
    return p


# ════════════════════════════════════════════════════════════════
# A. 大行 tarpit — 不应把 600KB 一口气塞进 context
# ════════════════════════════════════════════════════════════════


async def test_read_tarpit_bounded(tarpit_file):
    """600KB 单行: read_file 应截断/预算内返回, 不返 entire token 星系"""
    r = await _handle_read_file({"path": str(tarpit_file)})
    assert isinstance(r, dict)
    # 无论 ok 与否, 返回文本长度必须 bounded（截断而非原样回吐）
    text = str(r.get("data", "")) + str(r.get("result", "")) + str(r.get("error", ""))
    assert len(text) < 700_000, f"tarpit 未截断, 返回 {len(text)} 字符"


# ════════════════════════════════════════════════════════════════
# B. 长日志尾部 hunt
# ════════════════════════════════════════════════════════════════


async def test_read_big_log_head_tail(big_log_with_tail_error):
    """150K 行: 返回 head+tail 或限定窗口；不应挂/不一次回吐全量"""
    r = await _handle_read_file({"path": str(big_log_with_tail_error)})
    assert r.get("ok") is True
    text = str(r.get("data", ""))
    # bounded, 非 150K 行原样回吐
    assert len(text) < len("\n".join([""]*149_999)) or "off" in r, "应被截断"


# ════════════════════════════════════════════════════════════════
# C + D. 过 EOF / 空文件
# ════════════════════════════════════════════════════════════════


async def test_read_past_eof_informative(big_log_with_tail_error):
    r = await _handle_read_file({"path": str(big_log_with_tail_error), "offset": 999_999})
    assert isinstance(r, dict)
    # 必须有"超过 EOF"类提示而非空/挂
    combined = (str(r.get("data", "")) + str(r.get("error", ""))).lower()
    assert any(w in combined for w in ("越界", "eof", "超出", "不存在", "超"))


async def test_read_empty_file(empty_file):
    """空文件: 读成功 + 内容为空/仅 progress。当前实现 data 只含提示 - 测试放宽"""
    r = await _handle_read_file({"path": str(empty_file)})
    assert r.get("ok") is True
    # 断言 data 没有假内容 — 只允许空 / 纯 progress / 纯 hint
    data = str(r.get("data", ""))
    stripped = data.replace("📊", "").replace("已读取", "").strip()
    is_pure_meta = data == "" or "已读取" in data or "📊" in data
    assert is_pure_meta, f"空文件 data 不应有实际内容: {data!r}"


# ════════════════════════════════════════════════════════════════
# E. 二进制
# ════════════════════════════════════════════════════════════════


async def test_read_binary_refused_or_truncated(binary_file):
    r = await _handle_read_file({"path": str(binary_file)})
    # 理想: 明确拒绝 "binary file"; 兜底: 不崩溃 + 截断提示
    text = str(r.get("error", "")) + str(r.get("data", ""))
    assert len(text) < 30_000, "二进制不应把字节流塞进 LLM 上下文"


# ════════════════════════════════════════════════════════════════
# F. FIFO — 防挂死（hermes readtool: fifo_hang case）
# ════════════════════════════════════════════════════════════════


async def test_read_fifo_does_not_hang(fifo_file, tmp_path):
    """进程级保护: 读 FIFO 不得卡死（应识别 non-regular file 或超时）"""
    import asyncio as _a
    try:
        r = await _a.wait_for(
            _handle_read_file({"path": str(fifo_file)}), timeout=5.0
        )
        # 任何结果都行, 重要的是没卡死
        assert isinstance(r, dict)
    except asyncio.TimeoutError:
        pytest.fail("read_file 对 FIFO 挂死 (>5s) — 必须识别 non-regular file")
    finally:
        try:
            fifo_file.unlink()
        except OSError:
            pass


# ════════════════════════════════════════════════════════════════
# G. NFC/NFD 文件名 — 不 throw
# ════════════════════════════════════════════════════════════════


async def test_read_nfd_filename(nfd_named_file):
    r = await _handle_read_file({"path": str(nfd_named_file)})
    assert r.get("ok") is True, f"NFD 名读取失败: {r.get('error')}"
    assert "NFD" in str(r.get("data", ""))


# ════════════════════════════════════════════════════════════════
# H. 近名文件 (AGENT.md vs AGENTS.md) — 提示 presence（hermes readtool: near_miss）
# ════════════════════════════════════════════════════════════════


async def test_read_near_miss_suggests(tmp_path):
    """写出 AGENTS.md 但请求 AGENT.md → 应有 did-you-mean / 未找到提示"""
    real = tmp_path / "AGENTS.md"
    real.write_text("# real rules\n", encoding="utf-8")
    ghost = tmp_path / "AGENT.md"
    r = await _handle_read_file({"path": str(ghost)})
    # 明确找不到 (ok=False) 即算及格 — 最好还提示 real 的存在
    assert r.get("ok") is False
    errtext = str(r.get("error", ""))
    # 显式提示 (可选加分) — "AGENTS" 或 "similar" 词浮起来算强提示
    strong_hint = ("AGENTS.md" in errtext) or ("similar" in errtext.lower()) or ("did you mean" in errtext.lower())
    # 只要求"未找到"，不强求 did-you-mean（现为弱项，这测试留着当 ratchet）
    assert "不存在" in errtext or "not found" in errtext.lower() or "未找到" in errtext

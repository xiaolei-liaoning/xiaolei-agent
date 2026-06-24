import json
import tempfile
from pathlib import Path
from core.memory.user_profile import UserProfile, get_user_profile


def test_profile_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_001", base_dir=tmpdir)
        assert p.name is None
        assert p.facts == []
        assert p.preferences == []


def test_set_name():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_002", base_dir=tmpdir)
        p.name = "小雷"
        assert p.name == "小雷"
        p2 = UserProfile("test_002", base_dir=tmpdir)
        assert p2.name == "小雷"


def test_add_fact_dedup():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_003", base_dir=tmpdir)
        assert p.add_fact("用户喜欢Python") is True
        assert p.add_fact("用户喜欢Python") is False
        assert len(p.facts) == 1


def test_add_preference():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_004", base_dir=tmpdir)
        p.add_preference("喜欢深色主题")
        assert len(p.preferences) == 1
        assert p.preferences[0]["content"] == "喜欢深色主题"


def test_remove_fact():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_005", base_dir=tmpdir)
        p.add_fact("用户住在北京")
        p.add_fact("用户喜欢Python")
        assert p.remove_fact("北京") is True
        assert len(p.facts) == 1
        assert "Python" in p.facts[0]["content"]


def test_to_system_prompt_block():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_006", base_dir=tmpdir)
        p.name = "小帅"
        p.add_fact("用户是程序员")
        block = p.to_system_prompt_block()
        assert "小帅" in block
        assert "程序员" in block
        assert "用户画像" in block


def test_empty_profile_prompt():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_007", base_dir=tmpdir)
        assert p.to_system_prompt_block() == ""


def test_singleton():
    p1 = get_user_profile("test_008")
    p2 = get_user_profile("test_008")
    assert p1 is p2

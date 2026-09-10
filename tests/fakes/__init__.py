"""测试用 fake LLM 基础设施"""
from tests.fakes.fake_llm_server import FakeRouter, patch_router, make_router
__all__ = ["FakeRouter", "patch_router", "make_router"]

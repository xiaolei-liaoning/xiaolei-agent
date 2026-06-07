"""v2 中间件空上下文安全行为测试（精简版 — 4层链）"""
import asyncio
import sys
sys.path.insert(0, '.')

from core.multi_agent_v2.agents.middleware import RunContext, BaseMiddleware
from core.multi_agent_v2.agents.middlewares import (
    ReActDepthMiddleware, ReflectionMiddleware, KEPAMiddleware,
)
from core.multi_agent_v2.agents.react_core import build_default_chain


async def test_kepa_empty_context():
    """KEPAMiddleware 在空上下文中不抛异常"""
    kepa = KEPAMiddleware()
    ctx = RunContext('test')
    try:
        await kepa.on_think_start(ctx)
        await kepa.on_tool_end(ctx)
        await kepa.on_finish(ctx)
    except Exception as e:
        assert False, f'KEPA raised exception in empty context: {e}'
    print('✅ test_kepa_empty_context')


async def test_all_middlewares_empty_context():
    """所有中间件在所有钩子上空上下文不抛异常"""
    chain = build_default_chain()
    ctx = RunContext('test_empty')
    hooks = ['on_start', 'on_think_start', 'on_think_end', 'on_tool_end', 'on_finish']
    for hook in hooks:
        method = getattr(chain, hook, None)
        if method:
            try:
                await method(ctx)
            except Exception as e:
                assert False, f'{type(chain).__name__}.{hook} threw: {e}'
    print('✅ test_all_middlewares_empty_context')


async def test_reflection_middleware_empty():
    """ReflectionMiddleware 在空上下文中不抛异常"""
    rm = ReflectionMiddleware()
    ctx = RunContext('test')
    try:
        await rm.on_tool_end(ctx)
    except Exception as e:
        assert False, f'ReflectionMiddleware raised: {e}'
    print('✅ test_reflection_middleware_empty')


async def main():
    await test_kepa_empty_context()
    await test_all_middlewares_empty_context()
    await test_reflection_middleware_empty()
    print('\n🎉 All middleware behavior tests passed!')


if __name__ == '__main__':
    asyncio.run(main())

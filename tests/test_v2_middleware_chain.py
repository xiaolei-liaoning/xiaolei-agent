"""v2 MiddlewareChain 基础行为测试"""
import asyncio
import sys
sys.path.insert(0, '.')

from core.multi_agent_v2.agents.middleware import (
    RunContext, BaseMiddleware, MiddlewareChain, HookResult
)
from core.multi_agent_v2.agents.react_core import build_default_chain


class CaptureAgent(BaseMiddleware):
    HOOKS = ('on_start',)
    def __init__(self):
        super().__init__()
        self.agent_ref = None
    async def on_start(self, ctx):
        self.agent_ref = self._agent
        return HookResult()


class FilteredMW(BaseMiddleware):
    HOOKS = ('on_start',)
    def __init__(self):
        super().__init__()
        self.calls = []
    async def on_start(self, ctx):
        self.calls.append('on_start')
    async def on_think_start(self, ctx):
        self.calls.append('on_think_start')


class UnfilteredMW(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.calls = []
    async def on_start(self, ctx):
        self.calls.append('on_start')
    async def on_think_start(self, ctx):
        self.calls.append('on_think_start')


class ShortCircuit(BaseMiddleware):
    HOOKS = ('on_think_start',)
    async def on_think_start(self, ctx):
        return HookResult(jump_to='end', reason='test')


class NormalMW(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.called = False
    async def on_think_start(self, ctx):
        self.called = True


async def test_bind_agent():
    chain = MiddlewareChain()
    mw = CaptureAgent()
    chain.add(mw)
    chain.bind_agent('my-agent')
    # Call on_start to trigger agent_ref capture
    ctx = RunContext('test')
    await chain.on_start(ctx)
    assert mw.agent_ref == 'my-agent', f'Expected my-agent, got {mw.agent_ref}'
    print('✅ test_bind_agent')


async def test_hooks_filtering():
    chain = MiddlewareChain()
    fw = FilteredMW()
    uw = UnfilteredMW()
    chain.add(fw)
    chain.add(uw)
    ctx = RunContext('test')
    await chain.on_think_start(ctx)
    assert 'on_think_start' not in fw.calls, f'Filtered should not see on_think_start, got {fw.calls}'
    assert 'on_think_start' in uw.calls, 'Unfiltered should see on_think_start'
    print('✅ test_hooks_filtering')


async def test_hookresult_shortcircuit():
    chain = MiddlewareChain()
    sc = ShortCircuit()
    nw = NormalMW()
    chain.add(sc)
    chain.add(nw)
    ctx = RunContext('test')
    hr = await chain.on_think_start(ctx)
    assert hr.jump_to == 'end', f'Expected end, got {hr.jump_to}'
    assert not nw.called, 'NormalMW should not be called after ShortCircuit'
    print('✅ test_hookresult_shortcircuit')


async def test_build_default_chain():
    chain = build_default_chain()
    assert len(chain._middlewares) == 12, f'Expected 12 middlewares, got {len(chain._middlewares)}'
    names = [type(m).__name__ for m in chain._middlewares]
    expected = [
        'ProfileMiddleware', 'DynamicStageRoutingMiddleware', 'PlanAwareMiddleware',
        'ReActDepthMiddleware', 'ReActCoreMiddleware', 'ReflectionCheckMiddleware',
        'DataPipelineMiddleware', 'ConfidenceMiddleware', 'ReflectionMiddleware',
        'KEPAMiddleware', 'BranchMiddleware', 'AskUserMiddleware'
    ]
    assert names == expected, f'Mismatch: {names}'
    print('✅ test_build_default_chain')


async def test_add_len():
    chain = MiddlewareChain()
    assert len(chain) == 0
    chain.add(BaseMiddleware())
    assert len(chain) == 1
    chain.add(BaseMiddleware())
    assert len(chain) == 2
    print('✅ test_add_len')


async def main():
    await test_add_len()
    await test_bind_agent()
    await test_hooks_filtering()
    await test_hookresult_shortcircuit()
    await test_build_default_chain()
    print('\n🎉 All middleware chain tests passed!')


if __name__ == '__main__':
    asyncio.run(main())

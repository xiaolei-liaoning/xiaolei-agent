"""v2 SharedBus 消息 + 知识存储测试"""
import asyncio
import sys
sys.path.insert(0, '.')

from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, Message, MessageType


async def test_store_get():
    bus = get_shared_bus()
    await bus.clear_knowledge()
    await bus.store_knowledge('test:hello', {'data': 'world'}, tags={'test'}, source='pytest')
    result = await bus.get_knowledge('test:hello')
    assert result == {'data': 'world'}, f'Expected {{"data": "world"}}, got {result}'
    assert await bus.get_knowledge('nonexistent') is None
    print('✅ test_store_get')


async def test_search_knowledge():
    bus = get_shared_bus()
    await bus.clear_knowledge()
    await bus.store_knowledge('kepa:search:1', {'result': 'data1'}, tags={'kepa', 'search'}, source='a')
    await bus.store_knowledge('kepa:code:1', {'result': 'data2'}, tags={'kepa', 'code'}, source='b')
    results = await bus.search_knowledge('search')
    assert 'kepa:search:1' in results, f'search tag search failed: {results}'
    code_results = await bus.search_knowledge('code')
    assert 'kepa:code:1' in code_results, f'code tag search failed'
    assert len(await bus.search_knowledge('nonexistent')) == 0
    print('✅ test_search_knowledge')


async def test_list_clear():
    bus = get_shared_bus()
    await bus.clear_knowledge()
    assert len(await bus.list_knowledge()) == 0
    await bus.store_knowledge('test:x', {'v': 1}, tags={'x'}, source='t')
    assert 'test:x' in await bus.list_knowledge()
    await bus.clear_knowledge()
    assert await bus.get_knowledge('test:x') is None
    print('✅ test_list_clear')


async def test_publish_subscribe():
    bus = get_shared_bus()
    received = []
    async def cb(msg):
        received.append(msg)
    await bus.subscribe('test_topic', cb)
    msg = Message(type=MessageType.AGENT_MESSAGE, sender='a', topic='test_topic', payload={'x': 1})
    await bus.publish('test_topic', msg)
    await asyncio.sleep(0.05)
    assert len(received) == 1, f'Expected 1 message, got {len(received)}'
    assert received[0].payload == {'x': 1}
    # unsubscribe
    await bus.unsubscribe('test_topic', cb)
    await bus.publish('test_topic', msg)
    await asyncio.sleep(0.05)
    assert len(received) == 1, 'Should not receive after unsubscribe'
    print('✅ test_publish_subscribe')


async def test_direct_messaging():
    bus = get_shared_bus()
    msg = Message(type=MessageType.AGENT_MESSAGE, sender='a', receiver='b', payload={'hello': 'b'})
    await bus.send_direct('b', msg)
    received = await bus.receive_direct('b', timeout=0.5)
    assert received is not None, 'Should receive direct message'
    assert received.payload == {'hello': 'b'}, f'Wrong payload: {received.payload}'
    # No messages for unknown agent
    timeout_result = await bus.receive_direct('nonexistent', timeout=0.1)
    assert timeout_result is None, 'Should return None for nonexistent'
    print('✅ test_direct_messaging')


async def test_singleton():
    bus1 = get_shared_bus()
    bus2 = get_shared_bus()
    assert bus1 is bus2, 'get_shared_bus should return the same instance'
    print('✅ test_singleton')


async def main():
    await test_store_get()
    await test_search_knowledge()
    await test_list_clear()
    await test_publish_subscribe()
    await test_direct_messaging()
    await test_singleton()
    await get_shared_bus().clear_knowledge()
    print('\n🎉 All SharedBus tests passed!')


if __name__ == '__main__':
    asyncio.run(main())

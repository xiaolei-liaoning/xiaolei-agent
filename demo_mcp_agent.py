#!/usr/bin/env python3
"""
MCPAgent 完整使用演示
"""

import asyncio
import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demo_all_usage():
    """演示所有使用方式"""
    print("\n" + "="*80)
    print(" MCPAgent 完整使用演示 ")
    print("="*80)
    
# DEAD-IMPORT: from core.multi_agent_v2.agents.expert.mcp_agent import (
        MCPAgent, Task, get_mcp_agent
    )
    
    print("\n📌 方式 0: 使用单例")
    print("-" * 80)
    agent1 = get_mcp_agent()
    agent2 = get_mcp_agent()
    print(f"   单例工作: {agent1 is agent2}")
    
    print("\n📌 方式 1: 直接创建 Agent")
    print("-" * 80)
    agent = MCPAgent(name="演示 Agent")
    print(f"   Agent 创建成功: {agent.agent_name}")
    
    print("\n📌 方式 2: 使用 call() 方法（推荐用于简单调用）")
    print("-" * 80)
    print("   await agent.call('calculator', 'add', a=10, b=20)")
    
    print("\n📌 方式 3: 动态属性访问（最优雅的方式）")
    print("-" * 80)
    print("   await agent.calculator.add(a=10, b=20)")
    print("   await agent.weather.get_weather(city='北京')")
    print("   await agent.file_ops.list_files(path='.')")
    
    print("\n📌 方式 4: 快捷方法")
    print("-" * 80)
    print("   await agent.quick_calc('1 + 2 * 3')")
    print("   await agent.quick_weather('上海')")
    
    print("\n📌 方式 5: 使用 Task 方式（完整流程）")
    print("-" * 80)
    print("   task = Task(...)")
    print("   await agent.execute(task)")
    
    print("\n" + "="*80)
    print(" 可用的服务器和工具 ")
    print("="*80)
    
    servers = await agent.get_available_servers()
    if servers:
        for server in servers:
            print(f"   - {server}")
    else:
        print("   - calculator (计算器)")
        print("   - weather (天气)")
        print("   - file_ops (文件操作)")
        print("   - text_processing (文本处理)")
        print("   - fun (趣味工具)")
    
    print("\n" + "="*80)
    print(" 核心特性 ")
    print("="*80)
    print("   ✅ 连接池管理 - 复用连接，避免重复连接")
    print("   ✅ 自动连接 - 调用工具时自动连接服务器")
    print("   ✅ 动态工具发现 - 自动发现可用工具")
    print("   ✅ 多 Agent 协作 - 与其他 Agent 配合工作")
    print("   ✅ 优雅降级 - 服务不可用时安全处理")
    
    print("\n" + "="*80)
    print(" 演示完成！")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(demo_all_usage())

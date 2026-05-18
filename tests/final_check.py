#!/usr/bin/env python3
"""最终验证脚本 - 检查所有修复是否正确"""

import sys
import os

def check_module(name, import_path):
    """检查单个模块"""
    try:
        __import__(import_path)
        print(f"✅ {name}")
        return True
    except Exception as e:
        print(f"❌ {name}: {e}")
        return False

def check_file_contains(filepath, pattern):
    """检查文件是否包含特定内容"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if pattern in content:
                print(f"✅ {filepath}: 包含 '{pattern}'")
                return True
            else:
                print(f"❌ {filepath}: 不包含 '{pattern}'")
                return False
    except Exception as e:
        print(f"❌ {filepath}: {e}")
        return False

def main():
    print("🚀 最终验证 - 检查所有修复\n")
    print("=" * 60)

    all_ok = True

    # 添加项目路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)
    os.chdir(project_root)

    # 1. 检查关键模块
    print("\n📦 关键模块导入检查:")
    modules = [
        ("IntelligentScheduler", "core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler"),
        ("AwesomeMCPManger", "core.mcp.awesome_mcp_manager"),
        ("ToolRegistry", "core.skill_base"),
        ("PluginLoader", "core.plugin_loader"),
        ("LLMBackend", "core.engine.llm_backend"),
        ("SmartAgentCLIv2", "cli.smart_agent_v2"),
        ("CollaborationMode", "core.shared.enums"),
    ]

    for name, path in modules:
        if not check_module(name, path):
            all_ok = False

    # 2. 检查代码修复
    print("\n🔧 代码修复检查:")

    if not check_file_contains("core/mcp/awesome_mcp_manager.py", "await self._connected_servers[server_key].stop()"):
        all_ok = False

    if not check_file_contains("core/skill_base.py", "def reset(cls):"):
        all_ok = False

    if not check_file_contains("core/plugin_loader.py", "os.path.expanduser"):
        all_ok = False

    if not check_file_contains("core/multi_agent_v2/orchestration/scheduler/intelligent_scheduler.py", "优先从agent_pool获取已有Agent"):
        all_ok = False

    # 3. 检查CLI增强
    print("\n🖥️ CLI增强检查:")

    if not check_file_contains("cli.py", "async def handle_smart"):
        all_ok = False

    if not check_file_contains("cli.py", "def _demo_collaboration_modes"):
        all_ok = False

    if not check_file_contains("cli.py", "def _execute_with_mode"):
        all_ok = False

    if not check_file_contains("cli/smart_agent_v2.py", "class SmartAgentCLIv2"):
        all_ok = False

    if not check_file_contains("cli/command_parser.py", "pipeline/master/review/auction/hybrid"):
        all_ok = False

    # 4. 总结
    print("\n" + "=" * 60)
    if all_ok:
        print("✅ 所有检查通过！项目状态良好。")
    else:
        print("⚠️ 部分检查失败，请查看上述输出。")

    print()
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())


"""模块化重构验证脚本

用于验证 main.py 拆分后的模块是否能正常导入和运行。
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_imports():
    """测试所有模块的导入是否正常"""
    print("=" * 60)
    print("测试模块导入...")
    print("=" * 60)
    
    tests = [
        ("core.handlers", "内部处理器模块"),
        ("api.routes.chat", "聊天API路由"),
        ("api.routes.history", "历史记录API路由"),
        ("api.routes.system", "系统API路由"),
        ("api.routes", "路由模块包"),
    ]
    
    failed = []
    for module_name, description in tests:
        try:
            __import__(module_name)
            print(f"✅ {description:20s} ({module_name})")
        except Exception as e:
            print(f"❌ {description:20s} ({module_name}): {e}")
            failed.append((module_name, e))
    
    print()
    if failed:
        print(f"⚠️  {len(failed)} 个模块导入失败:")
        for module_name, error in failed:
            print(f"   - {module_name}: {error}")
        return False
    else:
        print("✅ 所有模块导入成功！")
        return True


def test_handlers_functions():
    """测试 handlers 模块中的关键函数是否存在"""
    print("\n" + "=" * 60)
    print("测试 handlers 函数...")
    print("=" * 60)
    
    from core import handlers
    
    required_functions = [
        "handle_automation_workflow",
        "handle_multi_step",
        "handle_multi_step_streaming",
        "handle_single_step",
        "handle_chat",
        "get_system_prompt",
        "save_chat_history",
        "save_task_log",
        "set_global_refs",
    ]
    
    missing = []
    for func_name in required_functions:
        if hasattr(handlers, func_name):
            print(f"✅ {func_name}")
        else:
            print(f"❌ {func_name} 不存在")
            missing.append(func_name)
    
    print()
    if missing:
        print(f"⚠️  {len(missing)} 个函数缺失:")
        for func_name in missing:
            print(f"   - {func_name}")
        return False
    else:
        print("✅ 所有关键函数都存在！")
        return True


def test_router_endpoints():
    """测试路由模块中的端点是否注册"""
    print("\n" + "=" * 60)
    print("测试路由端点...")
    print("=" * 60)
    
    from api.routes import chat_router, history_router, system_router
    
    routers = [
        (chat_router, "聊天路由", ["/api/chat", "/ws/chat"]),
        (history_router, "历史路由", ["/api/history", "/api/history/stats", "/api/task-logs"]),
        (system_router, "系统路由", ["/api/health", "/api/metrics", "/api/characters"]),
    ]
    
    all_ok = True
    for router, name, endpoints in routers:
        print(f"\n{name}:")
        registered_paths = [route.path for route in router.routes]
        
        for endpoint in endpoints:
            # WebSocket 端点特殊处理
            if endpoint.startswith("/ws/"):
                exists = any(endpoint in path for path in registered_paths)
            else:
                exists = endpoint in registered_paths
            
            if exists:
                print(f"  ✅ {endpoint}")
            else:
                print(f"  ❌ {endpoint} 未注册")
                all_ok = False
    
    print()
    if all_ok:
        print("✅ 所有路由端点注册成功！")
    else:
        print("⚠️  部分路由端点未注册")
    
    return all_ok


def test_fastapi_app():
    """测试 FastAPI 应用是否能正常创建"""
    print("\n" + "=" * 60)
    print("测试 FastAPI 应用...")
    print("=" * 60)
    
    try:
        from main import app
        
        print(f"✅ 应用标题: {app.title}")
        print(f"✅ 应用版本: {app.version}")
        print(f"✅ 路由数量: {len(app.routes)}")
        
        # 检查关键路由是否存在
        routes_info = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                methods = ', '.join(route.methods) if route.methods else 'N/A'
                routes_info.append(f"  {methods:10s} {route.path}")
        
        print(f"\n📋 部分路由列表（前10个）:")
        for info in routes_info[:10]:
            print(info)
        
        if len(routes_info) > 10:
            print(f"  ... 还有 {len(routes_info) - 10} 个路由")
        
        print("\n✅ FastAPI 应用创建成功！")
        return True
        
    except Exception as e:
        print(f"❌ FastAPI 应用创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试流程"""
    print("\n" + "🧪 " * 30)
    print("开始模块化重构验证测试")
    print("🧪 " * 30 + "\n")
    
    start_time = time.time()
    
    results = []
    
    # 测试1: 模块导入
    results.append(("模块导入", test_imports()))
    
    # 测试2: Handlers函数
    results.append(("Handlers函数", test_handlers_functions()))
    
    # 测试3: 路由端点
    results.append(("路由端点", test_router_endpoints()))
    
    # 测试4: FastAPI应用
    results.append(("FastAPI应用", test_fastapi_app()))
    
    elapsed = time.time() - start_time
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:20s} {status}")
    
    print()
    print(f"总计: {passed}/{total} 项测试通过")
    print(f"耗时: {elapsed:.2f}s")
    
    if passed == total:
        print("\n🎉 所有测试通过！模块化重构成功！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 项测试失败，请检查上述错误信息")
        return 1


if __name__ == "__main__":
    sys.exit(main())

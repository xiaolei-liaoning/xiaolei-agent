#!/usr/bin/env python3
"""桌面自动化功能演示"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.app_interface import get_app_manager, AppType


async def main():
    print("=" * 60)
    print("🖥️  桌面自动化功能演示")
    print("=" * 60)
    
    manager = get_app_manager()
    
    # 检查桌面自动化接口
    apps = manager.get_available_apps()
    
    if "desktop_automation" not in apps:
        print("❌ 桌面自动化接口未注册")
        return
    
    print("\n✅ 桌面自动化接口已注册")
    print(f"📋 可用操作: {len(apps['desktop_automation'])} 个")
    
    for i, action in enumerate(apps['desktop_automation'], 1):
        print(f"   {i}. {action}")
    
    # 演示1: 获取屏幕尺寸
    print("\n" + "=" * 60)
    print("📐 演示1: 获取屏幕尺寸")
    print("=" * 60)
    
    result = await manager.execute(
        AppType.DESKTOP_AUTOMATION,
        "get_screen_size",
        {}
    )
    
    if result.success:
        print(f"✅ 屏幕尺寸: {result.result['width']} x {result.result['height']}")
    else:
        print(f"❌ 获取失败: {result.error}")
    
    # 演示2: 截屏
    print("\n" + "=" * 60)
    print("📸 演示2: 屏幕截图")
    print("=" * 60)
    
    result = await manager.execute(
        AppType.DESKTOP_AUTOMATION,
        "screenshot",
        {}
    )
    
    if result.success:
        print(f"✅ 截图已保存: {result.result['path']}")
        print(f"⏰ 时间: {result.result['timestamp']}")
    else:
        print(f"❌ 截图失败: {result.error}")
    
    # 演示3: 截取指定区域
    print("\n" + "=" * 60)
    print("📸 演示3: 截取指定区域")
    print("=" * 60)
    
    result = await manager.execute(
        AppType.DESKTOP_AUTOMATION,
        "capture_region",
        {"x": 100, "y": 100, "width": 400, "height": 300}
    )
    
    if result.success:
        print(f"✅ 区域截图已保存: {result.result['path']}")
        print(f"📐 区域: {result.result['region']}")
    else:
        print(f"❌ 区域截图失败: {result.error}")
    
    # 演示4: 点击指定位置
    print("\n" + "=" * 60)
    print("🖱️  演示4: 点击指定位置")
    print("=" * 60)
    
    result = await manager.execute(
        AppType.DESKTOP_AUTOMATION,
        "click_at",
        {"x": 500, "y": 300, "clicks": 1}
    )
    
    if result.success:
        print(f"✅ 点击成功: ({result.result['x']}, {result.result['y']})")
        print(f"🖱️  点击次数: {result.result['clicks']}")
    else:
        print(f"❌ 点击失败: {result.error}")
    
    # 演示5: 查找文字位置
    print("\n" + "=" * 60)
    print("🔍 演示5: 查找文字位置")
    print("=" * 60)
    
    result = await manager.execute(
        AppType.DESKTOP_AUTOMATION,
        "locate_text",
        {"text": "测试"}
    )
    
    if result.success:
        print(f"✅ 找到文字位置: ({result.result['x']}, {result.result['y']})")
        print(f"📝 文字: {result.result['text']}")
        print(f"🎯 置信度: {result.result['confidence']}")
    else:
        print(f"❌ 查找失败: {result.error}")
    
    # 演示6: 查找所有匹配
    print("\n" + "=" * 60)
    print("🔍 演示6: 查找所有匹配")
    print("=" * 60)
    
    result = await manager.execute(
        AppType.DESKTOP_AUTOMATION,
        "find_all_matches",
        {"target": "按钮"}
    )
    
    if result.success:
        print(f"✅ 找到 {result.result['count']} 个匹配")
        for i, match in enumerate(result.result['matches'][:3], 1):
            print(f"   {i}. 位置: ({match['x']}, {match['y']}), 置信度: {match['confidence']}")
    else:
        print(f"❌ 查找失败: {result.error}")
    
    # 演示7: 查找并点击
    print("\n" + "=" * 60)
    print("🖱️  演示7: 查找并点击")
    print("=" * 60)
    
    result = await manager.execute(
        AppType.DESKTOP_AUTOMATION,
        "locate_and_click",
        {"target": "确定", "method": "ocr", "clicks": 1}
    )
    
    if result.success:
        print(f"✅ 查找并点击成功")
        print(f"📍 位置: ({result.result['x']}, {result.result['y']})")
    else:
        print(f"❌ 查找并点击失败: {result.error}")
    
    print("\n" + "=" * 60)
    print("🎉 演示完成!")
    print("=" * 60)
    
    # 显示功能总结
    print("\n📊 功能总结:")
    print("   1. 📐 获取屏幕尺寸")
    print("   2. 📸 屏幕截图")
    print("   3. 📸 截取指定区域")
    print("   4. 🖱️  点击指定位置")
    print("   5. 🔍 查找文字位置")
    print("   6. 🔍 查找所有匹配")
    print("   7. 🖱️  查找并点击")
    print("   8. 🖼️  查找图像位置")
    print("   9. 🖱️  查找图像并点击")


if __name__ == "__main__":
    asyncio.run(main())
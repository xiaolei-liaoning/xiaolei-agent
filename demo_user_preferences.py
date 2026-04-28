#!/usr/bin/env python3
"""
用户偏好设置功能演示脚本

展示如何使用新添加的用户偏好设置功能
"""

import webbrowser
import time
from pathlib import Path

def main():
    print("=" * 70)
    print("🎨 Coze平台 - 用户偏好设置功能演示")
    print("=" * 70)
    print()
    
    # 检查服务是否运行
    import requests
    try:
        response = requests.get("http://localhost:8001/api/health", timeout=3)
        if response.status_code == 200:
            print("✅ 服务正在运行")
        else:
            print("⚠️  服务异常，请先启动服务")
            return
    except:
        print("❌ 服务未启动，正在启动...")
        import subprocess
        import os
        os.chdir("/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent")
        subprocess.Popen(["python3", "main.py"], 
                        stdout=open("/tmp/coze_demo.log", "w"),
                        stderr=subprocess.STDOUT)
        print("⏳ 等待服务启动...")
        time.sleep(5)
    
    print()
    print("📖 功能说明:")
    print("-" * 70)
    print()
    print("1️⃣  打开Coze平台页面")
    print("   访问: http://localhost:8001/coze")
    print()
    print("2️⃣  点击右上角的设置图标 ⚙️")
    print("   位置: 页面右上角齿轮图标")
    print()
    print("3️⃣  体验以下功能:")
    print()
    print("   🎨 主题设置")
    print("      • ☀️ 亮色主题 - 适合白天使用")
    print("      • 🌙 暗色主题 - 适合夜间使用，护眼")
    print("      • 🔄 自动跟随系统 - 根据系统设置自动切换")
    print()
    print("   🔤 字体大小")
    print("      • 小 (Small) - 适合大屏显示器")
    print("      • 中 (Medium) - 默认大小，适合大多数场景")
    print("      • 大 (Large) - 适合小屏或视力不佳用户")
    print()
    print("   🌍 语言选择")
    print("      • 简体中文 - 默认语言")
    print("      • English - 英文界面（翻译功能待实现）")
    print()
    print("   ⚙️  其他设置")
    print("      • 🔊 提示音 - 消息提示音效开关")
    print("      • 💾 自动保存 - 自动保存聊天记录")
    print("      • 🔢 代码行号 - 显示代码编辑器行号")
    print()
    print("4️⃣  设置会自动保存")
    print("   • 所有设置保存在浏览器localStorage中")
    print("   • 下次访问时自动恢复您的偏好")
    print("   • 点击'恢复默认'可重置所有设置")
    print()
    print("-" * 70)
    print()
    
    # 询问是否打开浏览器
    choice = input("是否现在打开Coze平台体验？(y/n): ").strip().lower()
    if choice == 'y':
        print("\n🚀 正在打开浏览器...")
        webbrowser.open("http://localhost:8001/coze")
        print("✅ 浏览器已打开，请体验用户偏好设置功能！")
        print()
        print("💡 提示:")
        print("   - 尝试切换不同主题，观察界面变化")
        print("   - 调整字体大小，找到最适合您的尺寸")
        print("   - 刷新页面，验证设置是否持久化保存")
    else:
        print("\n📝 您可以稍后手动访问: http://localhost:8001/coze")
    
    print()
    print("=" * 70)
    print("✨ 演示结束")
    print("=" * 70)

if __name__ == "__main__":
    main()

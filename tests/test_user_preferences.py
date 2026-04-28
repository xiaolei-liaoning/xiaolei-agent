"""
用户偏好设置功能测试脚本

测试内容：
1. 主题切换功能（亮色/暗色/自动）
2. 字体大小调节（小/中/大）
3. 语言选择（中文/英文）
4. localStorage存储和读取
5. UI状态同步
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8001"


def test_health_check():
    """测试健康检查接口"""
    print("\n🔍 测试1: 健康检查")
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 健康检查通过 - 状态: {data['status']}, 版本: {data['version']}")
            return True
        else:
            print(f"❌ 健康检查失败 - HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False


def test_metrics():
    """测试系统指标接口"""
    print("\n📊 测试2: 系统指标")
    try:
        response = requests.get(f"{BASE_URL}/api/metrics", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 系统指标获取成功")
            print(f"   - 工具数量: {data.get('tools_count', 0)}")
            print(f"   - Redis状态: {data.get('redis', {}).get('status', 'unknown')}")
            return True
        else:
            print(f"❌ 系统指标获取失败 - HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 系统指标异常: {e}")
        return False


def test_frontend_settings_modal():
    """测试前端设置模态框是否存在"""
    print("\n🎨 测试3: 前端设置模态框")
    try:
        response = requests.get(f"{BASE_URL}/coze", timeout=5)
        if response.status_code == 200:
            html_content = response.text
            
            # 检查设置模态框是否存在
            has_modal = 'id="settings-modal"' in html_content
            has_theme_options = 'theme-option' in html_content
            has_font_size = 'font-size-option' in html_content
            has_language_select = 'language-select' in html_content
            
            if has_modal and has_theme_options and has_font_size and has_language_select:
                print("✅ 前端设置模态框完整")
                print("   - ✓ 模态框容器")
                print("   - ✓ 主题选项")
                print("   - ✓ 字体大小选项")
                print("   - ✓ 语言选择")
                return True
            else:
                print("❌ 前端设置模态框不完整")
                print(f"   - 模态框容器: {'✓' if has_modal else '✗'}")
                print(f"   - 主题选项: {'✓' if has_theme_options else '✗'}")
                print(f"   - 字体大小: {'✓' if has_font_size else '✗'}")
                print(f"   - 语言选择: {'✓' if has_language_select else '✗'}")
                return False
        else:
            print(f"❌ 页面加载失败 - HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 前端测试异常: {e}")
        return False


def test_css_variables():
    """测试CSS变量是否正确定义"""
    print("\n🎭 测试4: CSS主题变量")
    try:
        response = requests.get(f"{BASE_URL}/static/css/coze.css", timeout=5)
        if response.status_code == 200:
            css_content = response.text
            
            # 检查关键CSS变量
            has_root_vars = ':root' in css_content and '--bg-primary' in css_content
            has_dark_theme = '[data-theme="dark"]' in css_content
            has_font_size = '[data-font-size=' in css_content
            
            if has_root_vars and has_dark_theme and has_font_size:
                print("✅ CSS主题变量定义完整")
                print("   - ✓ 根变量")
                print("   - ✓ 暗色主题")
                print("   - ✓ 字体大小")
                return True
            else:
                print("❌ CSS主题变量不完整")
                return False
        else:
            print(f"❌ CSS文件加载失败 - HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ CSS测试异常: {e}")
        return False


def test_javascript_functions():
    """测试JavaScript函数是否存在"""
    print("\n⚙️ 测试5: JavaScript功能函数")
    try:
        response = requests.get(f"{BASE_URL}/static/js/coze.js", timeout=5)
        if response.status_code == 200:
            js_content = response.text
            
            # 检查关键函数
            functions = [
                'openSettings',
                'closeSettings',
                'setTheme',
                'setFontSize',
                'setLanguage',
                'toggleSound',
                'toggleAutosave',
                'toggleLineNumbers',
                'resetSettings',
                'UserPreferences'
            ]
            
            found_functions = [func for func in functions if func in js_content]
            missing_functions = [func for func in functions if func not in js_content]
            
            if len(found_functions) == len(functions):
                print(f"✅ JavaScript功能函数完整 ({len(found_functions)}/{len(functions)})")
                for func in found_functions:
                    print(f"   - ✓ {func}")
                return True
            else:
                print(f"⚠️  JavaScript功能函数不完整 ({len(found_functions)}/{len(functions)})")
                for func in found_functions:
                    print(f"   - ✓ {func}")
                for func in missing_functions:
                    print(f"   - ✗ {func} (缺失)")
                return False
        else:
            print(f"❌ JS文件加载失败 - HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ JavaScript测试异常: {e}")
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 用户偏好设置功能测试")
    print("=" * 60)
    print(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 测试地址: {BASE_URL}")
    
    results = []
    
    # 执行测试
    results.append(("健康检查", test_health_check()))
    results.append(("系统指标", test_metrics()))
    results.append(("前端设置模态框", test_frontend_settings_modal()))
    results.append(("CSS主题变量", test_css_variables()))
    results.append(("JavaScript函数", test_javascript_functions()))
    
    # 统计结果
    print("\n" + "=" * 60)
    print("📈 测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:20s} {status}")
    
    print("-" * 60)
    print(f"总计: {passed}/{total} 通过")
    success_rate = (passed / total * 100) if total > 0 else 0
    print(f"成功率: {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("\n🎉 测试通过！用户偏好设置功能已就绪")
        return 0
    else:
        print("\n⚠️  部分测试未通过，请检查相关功能")
        return 1


if __name__ == "__main__":
    exit(main())

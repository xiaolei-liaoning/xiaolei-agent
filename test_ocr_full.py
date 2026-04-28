#!/usr/bin/env python3
"""
OCR 功能测试脚本

测试流程：
1. 创建测试图片
2. 测试文件上传 API
3. 测试 OCR 识别功能
4. 清理测试文件
"""

import asyncio
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def create_test_image():
    """创建包含文字的测试图片"""
    print("📝 创建测试图片...")
    
    width, height = 600, 300
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # 添加文字
    text_cn = "你好，世界！\n这是中文测试文本。"
    text_en = "Hello World!\nThis is English test text."
    
    try:
        # 尝试使用中文字体
        font_cn = ImageFont.truetype('/System/Library/Fonts/PingFang.ttc', 36)
        font_en = ImageFont.truetype('/System/Library/Fonts/Arial.ttf', 32)
    except:
        font_cn = ImageFont.load_default()
        font_en = ImageFont.load_default()
    
    # 绘制文字
    draw.text((50, 80), text_cn, fill='black', font=font_cn)
    draw.text((50, 180), text_en, fill='blue', font=font_en)
    
    # 保存测试图片
    test_image_path = '/tmp/test_ocr_image.png'
    image.save(test_image_path)
    print(f"✅ 测试图片已创建: {test_image_path}")
    
    return test_image_path


async def test_upload_api(image_path):
    """测试文件上传 API"""
    print("\n🚀 测试文件上传 API...")
    
    import aiohttp
    
    url = "http://localhost:8000/api/upload"
    
    try:
        with open(image_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename='test_image.png', content_type='image/png')
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"✅ 文件上传成功!")
                        print(f"   文件名: {result['filename']}")
                        print(f"   文件路径: {result['file_path']}")
                        print(f"   文件大小: {result['file_size']} bytes")
                        return result['file_path']
                    else:
                        error_text = await response.text()
                        print(f"❌ 文件上传失败: {response.status}")
                        print(f"   错误信息: {error_text}")
                        return None
                        
    except Exception as e:
        print(f"❌ 文件上传异常: {e}")
        return None


async def test_chat_with_ocr(file_path):
    """测试聊天 API 的 OCR 功能"""
    print("\n🚀 测试 OCR 识别功能...")
    
    import aiohttp
    
    url = "http://localhost:8000/api/chat"
    
    payload = {
        "message": "识别这张图片中的文字",
        "user_id": 1,
        "agent_id": "default",
        "file_paths": [file_path]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ OCR 识别成功!")
                    print(f"\n📋 识别结果:\n{result['reply']}")
                    print(f"\n🔧 工具调用: {result.get('tool_call')}")
                    print(f"🎯 技能匹配: {result.get('skill')}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ OCR 识别失败: {response.status}")
                    print(f"   错误信息: {error_text}")
                    return False
                        
    except Exception as e:
        print(f"❌ OCR 识别异常: {e}")
        return False


async def main():
    """主测试流程"""
    print("="*70)
    print("# OCR 功能完整测试")
    print("="*70)
    
    # 步骤1: 创建测试图片
    test_image_path = create_test_image()
    
    if not Path(test_image_path).exists():
        print("❌ 测试图片创建失败")
        return
    
    # 步骤2: 测试文件上传
    file_path = await test_upload_api(test_image_path)
    
    if not file_path:
        print("❌ 文件上传失败，跳过 OCR 测试")
        # 清理测试文件
        if Path(test_image_path).exists():
            os.remove(test_image_path)
        return
    
    # 步骤3: 测试 OCR 识别
    ocr_success = await test_chat_with_ocr(file_path)
    
    # 步骤4: 清理测试文件
    print("\n🗑️  清理测试文件...")
    if Path(test_image_path).exists():
        os.remove(test_image_path)
        print(f"✅ 测试图片已删除: {test_image_path}")
    
    uploaded_file = Path(file_path)
    if uploaded_file.exists():
        os.remove(uploaded_file)
        print(f"✅ 上传文件已删除: {uploaded_file}")
    
    # 测试结果汇总
    print("\n" + "="*70)
    print("# 测试结果汇总")
    print("="*70)
    print(f"✅ 测试图片创建: 通过")
    print(f"{'✅' if file_path else '❌'} 文件上传 API: {'通过' if file_path else '失败'}")
    print(f"{'✅' if ocr_success else '❌'} OCR 识别功能: {'通过' if ocr_success else '失败'}")
    
    if file_path and ocr_success:
        print("\n🎉 所有测试通过！OCR 功能正常工作。")
    else:
        print("\n⚠️  部分测试失败，请检查:")
        print("   1. 后端服务是否运行 (python main.py)")
        print("   2. PaddleOCR 是否安装 (pip install paddleocr paddlepaddle)")
        print("   3. uploads 目录是否有写入权限")


if __name__ == "__main__":
    try:
        import aiohttp
    except ImportError:
        print("❌ 缺少依赖: aiohttp")
        print("安装命令: pip install aiohttp")
        exit(1)
    
    asyncio.run(main())



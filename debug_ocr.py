#!/usr/bin/env python
"""调试PaddleOCR返回格式"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_test_image():
    """创建包含文字的测试图片"""
    width, height = 400, 200
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    text = "Hello World!"
    
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Arial.ttf', 40)
    except:
        font = ImageFont.load_default()
    
    draw.text((50, 70), text, fill='black', font=font)
    
    test_image_path = '/tmp/test_ocr_debug.png'
    image.save(test_image_path)
    print(f"✅ 测试图片已创建: {test_image_path}")
    
    return test_image_path

def debug_ocr_format(image_path):
    """调试OCR返回格式"""
    from paddleocr import PaddleOCR
    
    print(f"\n🔍 调试PaddleOCR返回格式...")
    
    ocr = PaddleOCR(use_angle_cls=True, lang='ch')
    result = ocr.ocr(image_path)
    
    print(f"\n📊 原始返回结果类型: {type(result)}")
    print(f"📊 原始返回结果长度: {len(result) if result else 0}")
    
    if result:
        ocr_result = result[0]
        print(f"\n📊 result[0] 类型: {type(ocr_result)}")
        print(f"📊 result[0] 属性和方法:")
        
        # 获取所有属性和方法
        attrs = [attr for attr in dir(ocr_result) if not attr.startswith('_')]
        for attr in attrs:
            try:
                value = getattr(ocr_result, attr)
                if not callable(value):
                    print(f"  - {attr}: {value} (类型: {type(value)})")
                else:
                    print(f"  - {attr}: [方法]")
            except:
                print(f"  - {attr}: [无法访问]")
        
        # 尝试获取识别结果
        print(f"\n📊 尝试获取识别结果:")
        
        # 尝试常见属性
        common_attrs = ['rec_texts', 'texts', 'text', 'boxes', 'rec_scores', 'scores']
        for attr in common_attrs:
            if hasattr(ocr_result, attr):
                value = getattr(ocr_result, attr)
                print(f"  - {attr}: {value}")
        
        # 尝试迭代
        print(f"\n📊 尝试迭代:")
        try:
            for i, item in enumerate(ocr_result):
                print(f"  - [{i}]: {item} (类型: {type(item)})")
                if i >= 2:  # 只显示前3个
                    print(f"  - ... (共{len(ocr_result)}项)")
                    break
        except Exception as e:
            print(f"  - 迭代失败: {e}")

if __name__ == "__main__":
    print("🚀 开始调试PaddleOCR...")
    
    # 创建测试图片
    image_path = create_test_image()
    
    # 调试OCR返回格式
    debug_ocr_format(image_path)
    
    # 清理测试图片
    if os.path.exists(image_path):
        os.remove(image_path)
        print(f"\n🗑️  测试图片已清理")
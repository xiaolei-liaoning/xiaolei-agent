"""OCR文字识别功能测试

测试data_analysis技能中的OCR功能，包括：
1. 中文图片识别
2. 英文图片识别
3. 批量处理
4. 错误处理
5. 智能回复生成
"""

import sys
from pathlib import Path
# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from skills.data_analysis.handler import DataAnalysisHandler


def print_separator(title: str):
    """打印分隔线"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def test_ocr_basic():
    """测试1: 基础OCR功能（需要实际图片文件）"""
    print_separator("测试1: 基础OCR功能")
    
    handler = DataAnalysisHandler()
    
    # 注意：这个测试需要实际的图片文件
    # 你可以替换为你自己的图片路径
    test_image = "/Users/test/Desktop/test_ocr.png"
    
    if not Path(test_image).exists():
        print(f"\n⚠️  跳过测试：测试图片不存在 ({test_image})")
        print("提示：请准备一张包含文字的图片进行测试")
        return
    
    print(f"\n测试图片: {test_image}")
    
    result = handler.execute(
        action="ocr",
        file_path=test_image
    )
    
    print(f"\n执行结果:")
    print(f"成功: {result['success']}")
    
    if result['success']:
        print(f"动作: {result.get('action', 'N/A')}")
        stats = result.get('statistics', {})
        print(f"文本块数: {stats.get('total_text_blocks', 0)}")
        print(f"总字符数: {stats.get('total_chars', 0)}")
        print(f"平均置信度: {stats.get('avg_confidence', 0):.3f}")
        print(f"耗时: {result.get('_elapsed', 0):.3f}秒")
        print(f"\n智能回复:\n{result.get('reply', 'N/A')[:500]}")
    else:
        print(f"错误: {result.get('error', '未知错误')}")


def test_ocr_with_language():
    """测试2: 指定语言识别"""
    print_separator("测试2: 指定语言识别")
    
    handler = DataAnalysisHandler()
    
    test_image = "/Users/test/Desktop/test_en.png"
    
    if not Path(test_image).exists():
        print(f"\n⚠️  跳过测试：测试图片不存在")
        return
    
    print(f"\n测试英文图片: {test_image}")
    
    result = handler.execute(
        action="ocr",
        file_path=test_image,
        language="en"  # 指定英文
    )
    
    print(f"\n执行结果:")
    print(f"成功: {result['success']}")
    
    if result['success']:
        stats = result.get('statistics', {})
        print(f"识别字符数: {stats.get('total_chars', 0)}")
        print(f"平均置信度: {stats.get('avg_confidence', 0):.3f}")


def test_ocr_error_handling():
    """测试3: 错误处理"""
    print_separator("测试3: 错误处理")
    
    handler = DataAnalysisHandler()
    
    # 测试不存在的文件
    print("\n测试1: 不存在的文件")
    result = handler.execute(
        action="ocr",
        file_path="/nonexistent/image.png"
    )
    print(f"成功: {result['success']}")
    print(f"错误: {result.get('error', 'N/A')[:100]}")
    
    # 测试不支持的格式
    print("\n测试2: 不支持的文件格式")
    result = handler.execute(
        action="ocr",
        file_path="/tmp/test.pdf"
    )
    print(f"成功: {result['success']}")
    print(f"错误: {result.get('error', 'N/A')[:100]}")


def test_ocr_paddleocr_not_installed():
    """测试4: PaddleOCR未安装的情况"""
    print_separator("测试4: PaddleOCR依赖检查")
    
    try:
        from paddleocr import PaddleOCR
        print("\n✅ PaddleOCR已安装")
        print("可以正常进行OCR识别测试")
    except ImportError:
        print("\n❌ PaddleOCR未安装")
        print("\n安装命令:")
        print("pip install paddleocr paddlepaddle")
        print("\n注意：首次运行会自动下载模型文件（约400MB）")


def test_ocr_integration():
    """测试5: 与ToolResultFormatter集成"""
    print_separator("测试5: ToolResultFormatter集成测试")
    
    handler = DataAnalysisHandler()
    
    test_image = "/Users/test/Desktop/test_ocr.png"
    
    if not Path(test_image).exists():
        print(f"\n⚠️  跳过测试：测试图片不存在")
        return
    
    print(f"\n测试图片: {test_image}")
    
    result = handler.execute(
        action="ocr",
        file_path=test_image
    )
    
    if result['success']:
        reply = result.get('reply', '')
        
        # 检查回复是否包含关键信息
        checks = [
            ("状态标识", "✅" in reply or "❌" in reply),
            ("概述章节", "📋" in reply or "概述" in reply),
            ("耗时显示", "⏱️" in reply or "耗时" in reply),
            ("文件位置", "📁" in reply or "文件位置" in reply),
            ("完成时间", "🕐" in reply or "完成时间" in reply),
            ("下一步建议", "💡" in reply or "建议" in reply),
        ]
        
        print("\n智能回复格式检查:")
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}: {'通过' if passed else '未通过'}")
        
        all_passed = all(passed for _, passed in checks)
        print(f"\n总体评估: {'✅ 全部通过' if all_passed else '⚠️ 部分未通过'}")


def main():
    """运行所有测试"""
    print("\n" + "#"*70)
    print("# OCR文字识别功能 - 完整测试")
    print("#"*70)
    
    try:
        # 先检查依赖
        test_ocr_paddleocr_not_installed()
        
        # 运行功能测试
        test_ocr_basic()
        test_ocr_with_language()
        test_ocr_error_handling()
        test_ocr_integration()
        
        print("\n" + "#"*70)
        print("# 所有测试完成！")
        print("#"*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ 测试出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

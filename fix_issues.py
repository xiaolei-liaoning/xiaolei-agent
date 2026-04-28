#!/usr/bin/env python
"""快速修复脚本

修复测试中发现的主要问题
"""

import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def install_missing_dependencies():
    """安装缺失的依赖"""
    print("\n" + "="*60)
    print("修复1: 安装缺失的依赖")
    print("="*60)
    
    dependencies = [
        'lightgbm==4.5.0',
    ]
    
    for dep in dependencies:
        print(f"\n安装 {dep}...")
        try:
            subprocess.run(
                ['pip', 'install', dep],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"✅ {dep} 安装成功")
        except subprocess.CalledProcessError as e:
            print(f"❌ {dep} 安装失败: {e}")
            return False
    
    return True

def fix_translator_bug():
    """修复翻译器bug"""
    print("\n" + "="*60)
    print("修复2: 修复翻译器bug")
    print("="*60)
    
    try:
        from skills.translator.handler import translator
        
        # 测试翻译
        result = translator.execute(text='Hello World', target_lang='zh')
        
        if result.get('success'):
            print("✅ 翻译器修复成功")
            return True
        else:
            print(f"❌ 翻译器仍有问题: {result.get('error', '')}")
            return False
            
    except Exception as e:
        print(f"❌ 翻译器修复失败: {e}")
        return False

def test_ml_prediction():
    """测试机器学习预测"""
    print("\n" + "="*60)
    print("测试3: 机器学习预测")
    print("="*60)
    
    try:
        from skills.data_analysis.handler import DataAnalysisHandler
        import pandas as pd
        
        # 创建测试数据
        test_file = Path(__file__).parent / 'skills' / 'data_analysis' / 'output' / 'test_ml_fix.csv'
        test_file.parent.mkdir(exist_ok=True)
        
        df = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [2, 4, 6, 8, 10],
            'target': [6, 12, 18, 24, 30]
        })
        df.to_csv(test_file, index=False, encoding='utf-8-sig')
        
        # 测试预测
        handler = DataAnalysisHandler()
        result = handler.execute(
            action='预测',
            file_path=str(test_file),
            target_column='target',
            prediction_type='regression'
        )
        
        if result.get('success'):
            print("✅ 机器学习预测测试成功")
            return True
        else:
            print(f"❌ 机器学习预测测试失败: {result.get('error', '')}")
            return False
            
    except Exception as e:
        print(f"❌ 机器学习预测测试异常: {e}")
        return False

def run_quick_fixes():
    """运行快速修复"""
    print("\n" + "="*60)
    print("开始快速修复")
    print("="*60)
    
    results = {}
    
    # 1. 安装依赖
    results['安装依赖'] = install_missing_dependencies()
    
    # 2. 测试翻译器
    results['翻译器'] = fix_translator_bug()
    
    # 3. 测试机器学习
    results['机器学习'] = test_ml_prediction()
    
    # 汇总结果
    print("\n" + "="*60)
    print("修复结果汇总")
    print("="*60)
    
    for name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {name}: {status}")
    
    passed = sum(1 for s in results.values() if s)
    total = len(results)
    
    print(f"\n总计: {passed}/{total} 成功")
    
    if passed == total:
        print("\n🎉 所有问题已修复！")
    else:
        print(f"\n⚠️  {total - passed} 个问题未解决，请手动检查")

def main():
    """主函数"""
    run_quick_fixes()

if __name__ == "__main__":
    main()
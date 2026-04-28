#!/usr/bin/env python
"""调试翻译器"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from skills.translator.handler import translator
    
    print("测试翻译器...")
    
    # 测试中译英
    print("\n1. 测试中译英...")
    result = translator.execute(text='你好世界', target_lang='en')
    print(f"结果: {result}")
    
    # 测试英译中
    print("\n2. 测试英译中...")
    result = translator.execute(text='Hello World', target_lang='zh')
    print(f"结果: {result}")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
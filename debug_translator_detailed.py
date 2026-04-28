#!/usr/bin/env python
"""调试翻译器 - 详细版本"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from skills.translator.handler import translator
    
    print("测试翻译器...")
    
    # 测试英译中
    print("\n2. 测试英译中...")
    try:
        result = translator.execute(text='Hello World', target_lang='zh')
        print(f"结果: {result}")
    except Exception as e:
        print(f"错误: {e}")
        traceback.print_exc()
    
except Exception as e:
    print(f"错误: {e}")
    traceback.print_exc()
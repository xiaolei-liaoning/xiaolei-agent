#!/usr/bin/env python3
"""修复demos目录下文件的导入路径"""

import os
import sys
from pathlib import Path

def fix_demo_imports():
    """修复demos目录下的文件导入"""
    
    demos_dir = Path("demos")
    if not demos_dir.exists():
        print("demos目录不存在")
        return
    
    demo_files = list(demos_dir.glob("*.py"))
    
    print(f"找到 {len(demo_files)} 个demo文件\n")
    
    for demo_file in demo_files:
        print(f"处理: {demo_file.name}")
        
        with open(demo_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查是否已经有路径处理
        if "sys.path.insert" in content:
            print("  ✓ 已有路径处理，跳过")
            continue
        
        # 添加路径处理
        import_block = """import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
        
        # 找到第一个import语句后插入
        lines = content.split("\n")
        shebang = ""
        docstring = ""
        rest = []
        in_docstring = False
        
        for line in lines:
            if line.startswith("#!"):
                shebang = line + "\n"
            elif not in_docstring and (line.startswith('"""') or line.startswith("'''")):
                docstring += line + "\n"
                if line.count('"""') == 1 and line.count("'''") == 0:
                    in_docstring = True
            elif in_docstring:
                docstring += line + "\n"
                if '"""' in line or "'''" in line:
                    in_docstring = False
            else:
                rest.append(line)
        
        # 重新组合
        new_content = shebang + docstring + import_block + "\n".join(rest)
        
        # 写回文件
        with open(demo_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        print("  ✓ 已修复")
    
    print("\n✅ 所有demo文件导入路径已修复")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fix_demo_imports()

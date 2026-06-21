#!/usr/bin/env python3
"""生成所有Skill的用法文档

自动扫描skills目录，提取每个skill的文档字符串和用法说明
"""

import os
import sys
from pathlib import Path
import re

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def extract_docstring(file_path):
    """从Python文件中提取文档字符串"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找模块文档字符串
        match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    except Exception as e:
        return f"读取失败: {e}"

def extract_class_info(file_path):
    """提取类名和主要方法"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找类定义
        class_match = re.search(r'class\s+(\w+)\s*:', content)
        class_name = class_match.group(1) if class_match else "Unknown"
        
        # 查找主要方法
        methods = re.findall(r'def\s+(execute|aexecute)\s*\(([^)]*)\)', content)
        
        return class_name, methods
    except Exception as e:
        return "Unknown", []

def get_skill_description(skill_dir):
    """获取skill的描述信息"""
    handler_files = [
        skill_dir / 'handler.py',
        skill_dir / 'main.py',
        skill_dir / '__init__.py'
    ]
    
    for handler_file in handler_files:
        if handler_file.exists():
            docstring = extract_docstring(handler_file)
            class_name, methods = extract_class_info(handler_file)
            
            # 提取第一行作为简短描述
            short_desc = docstring.split('\n')[0] if docstring else "无描述"
            
            return {
                'docstring': docstring,
                'class_name': class_name,
                'methods': methods,
                'short_desc': short_desc
            }
    
    return None

def format_skill_info(skill_name, info, index):
    """格式化单个skill的信息"""
    output = []
    output.append(f"### {index}. `{skill_name}`")
    output.append("")
    output.append(f"**描述**: {info['short_desc']}")
    output.append("")
    
    if info['docstring']:
        # 清理文档字符串
        lines = info['docstring'].split('\n')
        filtered_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('依赖：'):
                filtered_lines.append(line)
        
        if filtered_lines:
            output.append("**详细说明**:")
            output.append("```")
            output.append('\n'.join(filtered_lines[:15]))  # 限制行数
            output.append("```")
            output.append("")
    
    if info['methods']:
        output.append("**主要方法**:")
        for method_name, params in info['methods']:
            output.append(f"- `{method_name}({params})`")
        output.append("")
    
    output.append("---")
    output.append("")
    
    return '\n'.join(output)

def main():
    """主函数"""
    skills_dir = project_root / 'skills'
    
    if not skills_dir.exists():
        print(f"错误: skills目录不存在: {skills_dir}")
        sys.exit(1)
    
    # 收集所有skill目录
    skill_dirs = []
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir() and not item.name.startswith('__') and item.name != 'output':
            # 检查是否有handler.py或main.py
            if (item / 'handler.py').exists() or (item / 'main.py').exists():
                skill_dirs.append(item)
    
    print("=" * 80)
    print("📚 Skill用法文档")
    print("=" * 80)
    print()
    
    # 按类别分组
    categories = {
        '基础工具': ['translator', 'calculator', 'weather', 'search_engine', 'web_scraper'],
        '数据处理': ['data_analysis', 'ocr_recognition'],
        '自动化': ['advanced_automation', 'gui_automation', 'system_toolbox'],
        'AI增强': ['deep_thinking', 'doubao_chat', 'rag_search_handler'],
        '第三方集成': ['third_party', 'openclaw', 'marketplace'],
        '角色模拟': [],  # 人物类
        '其他': []
    }
    
    categorized_skills = {cat: [] for cat in categories.keys()}
    
    for skill_dir in skill_dirs:
        skill_name = skill_dir.name
        
        # 分类
        categorized = False
        for category, skill_list in categories.items():
            if skill_name in skill_list:
                categorized_skills[category].append(skill_dir)
                categorized = True
                break
        
        # 特殊处理人物类
        if skill_dir.parent.name == '人物':
            categorized_skills['角色模拟'].append(skill_dir)
            categorized = True
        
        if not categorized:
            categorized_skills['其他'].append(skill_dir)
    
    # 输出文档
    total_count = 0
    
    for category, skills in categorized_skills.items():
        if not skills:
            continue
        
        print(f"\n## 📂 {category}\n")
        
        for skill_dir in skills:
            skill_name = skill_dir.name
            info = get_skill_description(skill_dir)
            
            if info:
                total_count += 1
                print(format_skill_info(skill_name, info, total_count))
    
    print("\n" + "=" * 80)
    print(f"✅ 共找到 {total_count} 个Skill")
    print("=" * 80)
    
    # 保存到文件
    output_file = project_root / 'docs' / 'SKILLS_USAGE_GUIDE.md'
    output_file.parent.mkdir(exist_ok=True)
    
    from datetime import datetime
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 📚 Skill用法完整指南\n\n")
        f.write(f"> 自动生成于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"本文档包含系统中所有 {total_count} 个Skill的详细用法说明。\n\n")
        f.write("---\n\n")
        
        # 重新生成Markdown内容
        for category, skills in categorized_skills.items():
            if not skills:
                continue
            
            f.write(f"\n## 📂 {category}\n\n")
            
            for skill_dir in skills:
                skill_name = skill_dir.name
                info = get_skill_description(skill_dir)
                
                if info:
                    f.write(format_skill_info(skill_name, info, total_count))
    
    print(f"\n📄 详细文档已保存到: {output_file}")

if __name__ == '__main__':
    main()

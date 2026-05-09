#!/usr/bin/env python
"""向量知识库管理脚本

功能：
1. 清空向量知识库
2. 读取所有技能的SKILL.md文件
3. 为每个技能添加skill标签
4. 重新写入知识库用于分类
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from core.vector_memory import VectorMemoryStore

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_all_skill_dirs() -> List[Path]:
    """获取所有技能目录"""
    skills_dir = Path(__file__).parent / "skills"
    
    if not skills_dir.exists():
        logger.error("skills目录不存在: %s", skills_dir)
        return []
    
    skill_dirs = []
    for item in skills_dir.iterdir():
        # 跳过特殊目录和文件
        if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
            # 检查是否有SKILL.md文件
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skill_dirs.append(item)
    
    logger.info("找到 %d 个技能目录", len(skill_dirs))
    return skill_dirs


def parse_skill_md(skill_dir: Path) -> Dict[str, Any]:
    """解析SKILL.md文件"""
    skill_md = skill_dir / "SKILL.md"
    
    if not skill_md.exists():
        logger.warning("SKILL.md不存在: %s", skill_md)
        return None
    
    try:
        content = skill_md.read_text(encoding='utf-8')
        
        # 提取技能名称（目录名）
        skill_name = skill_dir.name
        
        # 提取功能描述
        description = ""
        lines = content.split('\n')
        in_description = False
        for line in lines:
            if '功能描述' in line:
                in_description = True
                continue
            if in_description:
                if line.startswith('##') or line.strip() == '':
                    break
                description += line.strip() + ' '
        
        # 提取触发关键词
        keywords = []
        in_keywords = False
        for line in lines:
            if '触发关键词' in line:
                in_keywords = True
                continue
            if in_keywords:
                if line.startswith('##') or line.strip() == '':
                    break
                if line.strip():
                    keywords.append(line.strip())
        
        # 提取参数说明
        parameters = []
        in_params = False
        for line in lines:
            if '参数说明' in line:
                in_params = True
                continue
            if in_params:
                if line.startswith('##') or line.startswith('| 参数'):
                    continue
                if line.startswith('|') and '---' not in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 5 and parts[1]:
                        parameters.append({
                            'name': parts[1],
                            'type': parts[2],
                            'required': parts[3],
                            'default': parts[4],
                            'description': parts[5] if len(parts) > 5 else ''
                        })
                elif line.startswith('##'):
                    break
        
        # 提取使用示例
        examples = []
        in_examples = False
        example_block = []
        for line in lines:
            if '使用示例' in line:
                in_examples = True
                continue
            if in_examples:
                if line.startswith('##'):
                    break
                if line.strip():
                    example_block.append(line.strip())
        
        if example_block:
            examples = '\n'.join(example_block)
        
        return {
            'skill_name': skill_name,
            'description': description.strip(),
            'keywords': keywords,
            'parameters': parameters,
            'examples': examples,
            'full_content': content
        }
        
    except Exception as e:
        logger.error("解析SKILL.md失败: %s, 错误: %s", skill_md, e)
        return None


def build_skill_documents(skill_info: Dict[str, Any]) -> List[Dict[str, str]]:
    """构建技能文档列表
    
    为每个技能创建多个文档片段，用于向量检索
    """
    skill_name = skill_info['skill_name']
    documents = []
    
    # 1. 技能概述文档
    doc1 = f"""
技能名称：{skill_name}
功能描述：{skill_info['description']}
触发关键词：{' '.join(skill_info['keywords'])}
""".strip()
    documents.append({
        'content': doc1,
        'metadata': {
            'skill_name': skill_name,
            'document_type': 'overview',
            'category': 'skill'
        }
    })
    
    # 2. 关键词文档
    if skill_info['keywords']:
        doc2 = f"""
技能名称：{skill_name}
触发关键词：
{chr(10).join(skill_info['keywords'])}
""".strip()
        documents.append({
            'content': doc2,
            'metadata': {
                'skill_name': skill_name,
                'document_type': 'keywords',
                'category': 'skill'
            }
        })
    
    # 3. 参数文档
    if skill_info['parameters']:
        param_lines = []
        for param in skill_info['parameters']:
            param_lines.append(f"- {param['name']}: {param['description']} (类型: {param['type']}, 必填: {param['required']})")
        
        doc3 = f"""
技能名称：{skill_name}
参数说明：
{chr(10).join(param_lines)}
""".strip()
        documents.append({
            'content': doc3,
            'metadata': {
                'skill_name': skill_name,
                'document_type': 'parameters',
                'category': 'skill'
            }
        })
    
    # 4. 使用示例文档
    if skill_info['examples']:
        doc4 = f"""
技能名称：{skill_name}
使用示例：
{skill_info['examples']}
""".strip()
        documents.append({
            'content': doc4,
            'metadata': {
                'skill_name': skill_name,
                'document_type': 'examples',
                'category': 'skill'
            }
        })
    
    # 5. 完整文档
    documents.append({
        'content': skill_info['full_content'],
        'metadata': {
            'skill_name': skill_name,
            'document_type': 'full',
            'category': 'skill'
        }
    })
    
    return documents


def clear_and_rebuild_vector_store():
    """清空并重建向量知识库"""
    logger.info("="*60)
    logger.info("开始清空并重建向量知识库")
    logger.info("="*60)
    
    # 1. 初始化向量存储
    vector_store = VectorMemoryStore()
    
    # 2. 清空现有数据
    logger.info("清空现有向量知识库...")
    current_count = vector_store.count()
    logger.info("当前记忆数: %d", current_count)
    
    vector_store.clear_all()
    logger.info("向量知识库已清空")
    
    # 3. 获取所有技能
    skill_dirs = get_all_skill_dirs()
    
    if not skill_dirs:
        logger.error("没有找到任何技能目录")
        return False
    
    # 4. 解析并添加技能文档
    total_documents = 0
    
    for skill_dir in skill_dirs:
        logger.info("\n处理技能: %s", skill_dir.name)
        
        # 解析SKILL.md
        skill_info = parse_skill_md(skill_dir)
        
        if not skill_info:
            logger.warning("跳过技能: %s (解析失败)", skill_dir.name)
            continue
        
        # 构建文档
        documents = build_skill_documents(skill_info)
        
        # 添加到向量库
        for doc in documents:
            memory_id = vector_store.add_memory(
                user_id=0,  # 系统用户
                content=doc['content'],
                category='fact',
                metadata=doc['metadata']
            )
            
            if memory_id:
                total_documents += 1
                logger.debug("  添加文档: %s (%s)", memory_id, doc['metadata']['document_type'])
        
        logger.info("  添加 %d 个文档", len(documents))
    
    # 5. 强制刷新缓冲区
    vector_store._flush_buffer()
    
    # 6. 验证结果
    final_count = vector_store.count()
    logger.info("\n" + "="*60)
    logger.info("向量知识库重建完成")
    logger.info("="*60)
    logger.info("处理技能数: %d", len(skill_dirs))
    logger.info("添加文档数: %d", total_documents)
    logger.info("向量库总数: %d", final_count)
    
    return True


def test_vector_search():
    """测试向量搜索功能"""
    logger.info("\n" + "="*60)
    logger.info("测试向量搜索功能")
    logger.info("="*60)
    
    vector_store = VectorMemoryStore()
    
    test_queries = [
        "天气",
        "爬取微博热搜",
        "分析数据",
        "翻译文字",
        "打开记事本",
        "GitHub trending",
    ]
    
    for query in test_queries:
        logger.info("\n查询: %s", query)
        results = vector_store.search_memories(query, top_k=3)
        
        if results:
            for i, result in enumerate(results, 1):
                skill_name = result['metadata'].get('skill_name', 'unknown')
                doc_type = result['metadata'].get('document_type', 'unknown')
                distance = result['distance']
                logger.info("  %d. [%s] %s (相似度: %.3f)", i, skill_name, doc_type, 1-distance)
        else:
            logger.info("  无结果")


def main():
    """主函数"""
    try:
        # 清空并重建向量知识库
        success = clear_and_rebuild_vector_store()
        
        if success:
            # 测试搜索功能
            test_vector_search()
            
            logger.info("\n✅ 向量知识库管理完成")
            return 0
        else:
            logger.error("\n❌ 向量知识库管理失败")
            return 1
            
    except Exception as e:
        logger.error("执行失败: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
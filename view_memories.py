#!/usr/bin/env python3
"""查看向量记忆库内容"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.vector_memory import VectorMemoryStore

def main():
    db = VectorMemoryStore()
    
    print("=" * 60)
    print("📚 向量记忆库查看器")
    print("=" * 60)
    print(f"\n记忆总数: {db.count()}")
    
    # 查询关键词
    query = input("\n请输入查询关键词（直接回车查看所有）: ").strip()
    
    if not query:
        # 获取所有记忆
        print("\n📋 显示所有记忆:")
        print("-" * 60)
        
        # ChromaDB不支持空查询，使用通用词检索
        results = db.search_memories('的', top_k=db.count())
        
        if not results:
            print("❌ 记忆库为空")
            return
    else:
        print(f"\n🔍 检索关键词: '{query}'")
        print("-" * 60)
        results = db.search_memories(query, top_k=10)
        
        if not results:
            print("❌ 未找到相关记忆")
            return
    
    for i, r in enumerate(results, 1):
        print(f"\n{i}. ID: {r['id']}")
        print(f"   内容: {r['content']}")
        print(f"   分类: {r['metadata'].get('category', 'N/A')}")
        print(f"   时间: {r['metadata'].get('timestamp', 'N/A')}")
        if 'distance' in r:
            similarity = 1 - r['distance']
            print(f"   相似度: {similarity:.4f}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()

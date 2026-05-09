#!/usr/bin/env python3
"""Agent小组数据迁移脚本

将内存中的小组数据迁移到MySQL数据库
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '小雷版小龙虾agent'))

def migrate_agent_groups_to_db():
    """将内存中的Agent小组数据迁移到数据库"""
    print("=" * 70)
    print("  Agent小组数据迁移工具")
    print("=" * 70)
    
    # 1. 初始化数据库
    print("\n[1/4] 初始化数据库...")
    try:
        from core.database import init_db, get_session, AgentGroup
        init_db()
        print("✅ 数据库初始化成功")
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
        return False
    
    # 2. 导入内存数据
    print("\n[2/4] 加载内存中的数据...")
    try:
        from api.routes.agent_groups import _agent_groups
        
        if not _agent_groups:
            print("⚠️  内存中没有小组数据,跳过迁移")
            return True
        
        print(f"📦 发现 {len(_agent_groups)} 个小组待迁移")
        for group_id, group_data in _agent_groups.items():
            print(f"   - {group_data['name']} (ID: {group_id})")
    except Exception as e:
        print(f"❌ 加载内存数据失败: {e}")
        return False
    
    # 3. 执行迁移
    print("\n[3/4] 开始迁移数据...")
    db = get_session()
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        for group_id, group_data in _agent_groups.items():
            try:
                # 检查是否已存在
                existing = db.query(AgentGroup).filter(AgentGroup.id == group_id).first()
                
                if existing:
                    print(f"   ⏭️  跳过已存在的小组: {group_data['name']}")
                    skipped_count += 1
                    continue
                
                # 创建新记录
                new_group = AgentGroup(
                    id=group_id,
                    name=group_data['name'],
                    members=group_data['members'],
                    strategy=group_data['strategy'],
                    circuit_breaker=group_data['circuit_breaker'],
                    elastic_scaling=group_data['elastic_scaling'],
                    status=group_data['status'],
                    created_at=datetime.fromisoformat(group_data['created_at']),
                    updated_at=datetime.fromisoformat(group_data['updated_at']),
                    last_active=datetime.fromisoformat(group_data['last_active']) if group_data.get('last_active') else None
                )
                db.add(new_group)
                migrated_count += 1
                print(f"   ✅ 迁移成功: {group_data['name']}")
                
            except Exception as e:
                error_count += 1
                print(f"   ❌ 迁移失败: {group_data['name']} - {e}")
        
        # 提交事务
        db.commit()
        print(f"\n✅ 事务提交成功")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 迁移失败,已回滚: {e}")
        return False
    finally:
        db.close()
    
    # 4. 验证结果
    print("\n[4/4] 验证迁移结果...")
    try:
        db = get_session()
        total_in_db = db.query(AgentGroup).count()
        db.close()
        
        print(f"✅ 数据库中共有 {total_in_db} 个小组")
        print(f"\n{'='*70}")
        print(f"  迁移统计:")
        print(f"  {'='*70}")
        print(f"  成功迁移: {migrated_count} 个")
        print(f"  跳过重复: {skipped_count} 个")
        print(f"  迁移失败: {error_count} 个")
        print(f"  数据库总数: {total_in_db} 个")
        print(f"{'='*70}")
        
        if error_count > 0:
            print(f"\n⚠️  警告: 有 {error_count} 个小组迁移失败,请检查日志")
            return False
        
        print(f"\n🎉 数据迁移完成!")
        return True
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False


if __name__ == '__main__':
    success = migrate_agent_groups_to_db()
    sys.exit(0 if success else 1)

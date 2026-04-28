#!/usr/bin/env python3
"""
向量存储备份功能测试

测试内容：
1. 备份管理器初始化
2. 创建备份
3. 列出备份
4. 删除备份
5. 备份统计信息
6. 自动备份调度
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path("/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent")
sys.path.insert(0, str(project_root))

from core.vector_store_backup import VectorStoreBackupManager, get_vector_store_backup_manager


class TestVectorStoreBackup:
    """向量存储备份测试类"""
    
    def __init__(self):
        self.results = []
        self.backup_manager = None
    
    def add_result(self, test_name: str, passed: bool, details: str = ""):
        """添加测试结果"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        print(f"{status} - {test_name}")
        if details:
            print(f"   📝 {details}")
    
    async def test_backup_manager_initialization(self):
        """测试1: 备份管理器初始化"""
        print("\n" + "="*80)
        print("🧪 测试1: 备份管理器初始化")
        print("="*80)
        
        try:
            # 测试单例模式
            manager1 = get_vector_store_backup_manager()
            manager2 = get_vector_store_backup_manager()
            
            if manager1 is manager2:
                self.add_result("测试1.1: 单例模式正确", True)
            else:
                self.add_result("测试1.1: 单例模式正确", False, "返回了不同实例")
            
            # 检查备份目录
            if manager1.backup_dir.exists():
                self.add_result("测试1.2: 备份目录存在", True, f"路径: {manager1.backup_dir}")
            else:
                self.add_result("测试1.2: 备份目录存在", False)
            
            # 检查最大备份数配置
            if manager1.max_backups == 5:
                self.add_result("测试1.3: 最大备份数配置正确", True)
            else:
                self.add_result("测试1.3: 最大备份数配置正确", False, f"实际值: {manager1.max_backups}")
            
            self.backup_manager = manager1
            
        except Exception as e:
            self.add_result("测试1: 备份管理器初始化", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_create_backup(self):
        """测试2: 创建备份"""
        print("\n" + "="*80)
        print("🧪 测试2: 创建备份")
        print("="*80)
        
        try:
            manager = self.backup_manager or get_vector_store_backup_manager()
            
            # 创建一个临时测试目录作为源
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                # 创建一些测试文件
                test_file = Path(temp_dir) / "test.txt"
                test_file.write_text("这是测试数据")
                
                # 创建备份
                backup_info = await manager.create_backup(
                    source_path=temp_dir,
                    description="测试备份"
                )
                
                if backup_info.get("status") == "completed":
                    self.add_result("测试2.1: 备份创建成功", True)
                    
                    # 验证备份信息
                    if "id" in backup_info and "timestamp" in backup_info:
                        self.add_result("测试2.2: 备份信息完整", True, f"ID: {backup_info['id']}")
                        
                        # 验证备份文件存在
                        backup_path = Path(backup_info["backup_path"])
                        if backup_path.exists():
                            self.add_result("测试2.3: 备份文件存在", True, f"大小: {backup_info['size_mb']:.2f} MB")
                        else:
                            self.add_result("测试2.3: 备份文件存在", False)
                    else:
                        self.add_result("测试2.2: 备份信息完整", False, "缺少必要字段")
                else:
                    self.add_result("测试2.1: 备份创建成功", False, f"状态: {backup_info.get('status')}")
            
        except Exception as e:
            self.add_result("测试2: 创建备份", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_list_backups(self):
        """测试3: 列出备份"""
        print("\n" + "="*80)
        print("🧪 测试3: 列出备份")
        print("="*80)
        
        try:
            manager = self.backup_manager or get_vector_store_backup_manager()
            
            backups = manager.list_backups()
            
            if isinstance(backups, list):
                self.add_result("测试3.1: 备份列表获取成功", True, f"共{len(backups)}个备份")
                
                if len(backups) > 0:
                    print("\n   📋 备份列表:")
                    for i, backup in enumerate(backups[:3], 1):
                        print(f"      {i}. {backup['id']} - {backup['datetime']}")
                else:
                    print("   ℹ️  暂无备份")
            else:
                self.add_result("测试3.1: 备份列表获取成功", False, "返回类型不正确")
            
        except Exception as e:
            self.add_result("测试3: 列出备份", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_delete_backup(self):
        """测试4: 删除备份"""
        print("\n" + "="*80)
        print("🧪 测试4: 删除备份")
        print("="*80)
        
        try:
            manager = self.backup_manager or get_vector_store_backup_manager()
            
            # 先创建一个备份
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                test_file = Path(temp_dir) / "test.txt"
                test_file.write_text("测试数据")
                
                backup_info = await manager.create_backup(temp_dir, "待删除备份")
                
                if backup_info.get("status") == "completed":
                    backup_id = backup_info["id"]
                    
                    # 删除备份
                    result = await manager.delete_backup(backup_id)
                    
                    if result.get("status") == "success":
                        self.add_result("测试4.1: 备份删除成功", True, f"ID: {backup_id}")
                        
                        # 验证备份已删除
                        remaining_backups = manager.list_backups()
                        deleted_exists = any(b["id"] == backup_id for b in remaining_backups)
                        
                        if not deleted_exists:
                            self.add_result("测试4.2: 备份已从列表中移除", True)
                        else:
                            self.add_result("测试4.2: 备份已从列表中移除", False)
                    else:
                        self.add_result("测试4.1: 备份删除成功", False, f"状态: {result.get('status')}")
                else:
                    self.add_result("测试4: 删除备份", False, "无法创建测试备份")
            
        except Exception as e:
            self.add_result("测试4: 删除备份", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_backup_stats(self):
        """测试5: 备份统计信息"""
        print("\n" + "="*80)
        print("🧪 测试5: 备份统计信息")
        print("="*80)
        
        try:
            manager = self.backup_manager or get_vector_store_backup_manager()
            
            stats = manager.get_backup_stats()
            
            if isinstance(stats, dict):
                self.add_result("测试5.1: 统计信息获取成功", True)
                
                print(f"\n   📊 备份统计:")
                print(f"      总备份数: {stats.get('total_backups', 0)}")
                print(f"      总大小: {stats.get('total_size_mb', 0):.2f} MB")
                print(f"      最早备份: {stats.get('oldest_backup', '无')}")
                print(f"      最新备份: {stats.get('newest_backup', '无')}")
                print(f"      最大保留: {stats.get('max_backups', 5)}")
                
                # 验证关键字段
                required_fields = ["total_backups", "total_size_mb", "max_backups"]
                if all(field in stats for field in required_fields):
                    self.add_result("测试5.2: 统计信息字段完整", True)
                else:
                    self.add_result("测试5.2: 统计信息字段完整", False, "缺少必要字段")
            else:
                self.add_result("测试5.1: 统计信息获取成功", False, "返回类型不正确")
            
        except Exception as e:
            self.add_result("测试5: 备份统计信息", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_cleanup_old_backups(self):
        """测试6: 清理旧备份"""
        print("\n" + "="*80)
        print("🧪 测试6: 清理旧备份")
        print("="*80)
        
        try:
            # 创建一个新的备份管理器，设置较小的max_backups
            manager = VectorStoreBackupManager(max_backups=2)
            
            # 创建3个备份（超过限制）
            import tempfile
            for i in range(3):
                with tempfile.TemporaryDirectory() as temp_dir:
                    test_file = Path(temp_dir) / f"test_{i}.txt"
                    test_file.write_text(f"测试数据{i}")
                    
                    await manager.create_backup(temp_dir, f"测试备份{i}")
            
            # 检查是否只保留了2个备份
            backups = manager.list_backups()
            
            if len(backups) <= 2:
                self.add_result("测试6.1: 旧备份清理成功", True, f"保留{len(backups)}个备份")
            else:
                self.add_result("测试6.1: 旧备份清理成功", False, f"仍有{len(backups)}个备份")
            
        except Exception as e:
            self.add_result("测试6: 清理旧备份", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_restore_backup(self):
        """测试7: 备份恢复功能"""
        print("\n" + "="*80)
        print("🧪 测试7: 备份恢复功能")
        print("="*80)
        
        try:
            import tempfile
            import shutil
            
            manager = self.backup_manager or get_vector_store_backup_manager()
            
            # 创建源目录并添加测试文件
            with tempfile.TemporaryDirectory() as temp_dir:
                source_path = Path(temp_dir) / "source_data"
                source_path.mkdir()
                
                # 创建测试文件
                test_file = source_path / "test.txt"
                test_file.write_text("这是原始测试数据")
                
                # 创建备份
                backup_info = await manager.create_backup(
                    source_path=str(source_path),
                    description="用于恢复测试的备份"
                )
                
                if backup_info.get("status") != "completed":
                    self.add_result("测试7.1: 备份创建成功", False, "无法创建测试备份")
                    return
                
                self.add_result("测试7.1: 备份创建成功", True, f"ID: {backup_info['id']}")
                
                # 创建恢复目标目录
                restore_path = Path(temp_dir) / "restored_data"
                
                # 执行恢复
                result = await manager.restore_backup(
                    backup_id=backup_info["id"],
                    target_path=str(restore_path)
                )
                
                if result.get("status") == "success":
                    self.add_result("测试7.2: 备份恢复成功", True)
                    
                    # 验证恢复的文件
                    restored_file = restore_path / "test.txt"
                    if restored_file.exists():
                        content = restored_file.read_text()
                        if content == "这是原始测试数据":
                            self.add_result("测试7.3: 恢复数据完整性验证", True, "数据完全一致")
                        else:
                            self.add_result("测试7.3: 恢复数据完整性验证", False, f"内容不匹配: {content}")
                    else:
                        self.add_result("测试7.3: 恢复数据完整性验证", False, "恢复文件不存在")
                else:
                    self.add_result("测试7.2: 备份恢复成功", False, f"状态: {result.get('status')}")
            
        except Exception as e:
            self.add_result("测试7: 备份恢复功能", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_backup_metadata_persistence(self):
        """测试8: 备份元数据持久化"""
        print("\n" + "="*80)
        print("🧪 测试8: 备份元数据持久化")
        print("="*80)
        
        try:
            import tempfile
            
            manager = VectorStoreBackupManager(max_backups=3)
            
            # 创建多个备份
            backup_ids = []
            for i in range(3):
                with tempfile.TemporaryDirectory() as temp_dir:
                    test_file = Path(temp_dir) / f"test_{i}.txt"
                    test_file.write_text(f"测试数据{i}")
                    
                    backup = await manager.create_backup(temp_dir, f"持久化测试备份{i}")
                    if backup.get("status") == "completed":
                        backup_ids.append(backup["id"])
            
            # 验证元数据已保存
            if manager.backup_metadata_file.exists():
                self.add_result("测试8.1: 元数据文件存在", True)
                
                # 重新加载管理器（模拟重启）
                new_manager = VectorStoreBackupManager(max_backups=3)
                backups = new_manager.list_backups()
                
                if len(backups) > 0:
                    self.add_result("测试8.2: 元数据持久化成功", True, f"恢复{len(backups)}个备份记录")
                    
                    # 验证备份ID是否保留
                    restored_ids = [b["id"] for b in backups]
                    if any(bid in restored_ids for bid in backup_ids):
                        self.add_result("测试8.3: 备份记录完整性", True)
                    else:
                        self.add_result("测试8.3: 备份记录完整性", False, "备份ID不匹配")
                else:
                    self.add_result("测试8.2: 元数据持久化成功", False, "没有恢复任何备份")
            else:
                self.add_result("测试8.1: 元数据文件存在", False)
            
        except Exception as e:
            self.add_result("测试8: 备份元数据持久化", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def test_concurrent_backup_operations(self):
        """测试9: 并发备份操作"""
        print("\n" + "="*80)
        print("🧪 测试9: 并发备份操作")
        print("="*80)
        
        try:
            import tempfile
            import asyncio
            
            manager = VectorStoreBackupManager(max_backups=5)
            
            # 同时创建多个备份
            async def create_test_backup(index):
                with tempfile.TemporaryDirectory() as temp_dir:
                    test_file = Path(temp_dir) / f"concurrent_{index}.txt"
                    test_file.write_text(f"并发测试数据{index}")
                    return await manager.create_backup(temp_dir, f"并发备份{index}")
            
            # 并发创建3个备份
            tasks = [create_test_backup(i) for i in range(3)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful_backups = [r for r in results if isinstance(r, dict) and r.get("status") == "completed"]
            
            if len(successful_backups) >= 2:  # 至少2个成功
                self.add_result("测试9.1: 并发备份支持", True, f"{len(successful_backups)}/3成功")
                
                # 验证所有备份都有唯一ID
                backup_ids = [b["id"] for b in successful_backups]
                if len(backup_ids) == len(set(backup_ids)):
                    self.add_result("测试9.2: 备份ID唯一性", True, "所有ID都不重复")
                else:
                    self.add_result("测试9.2: 备份ID唯一性", False, "存在重复ID")
            else:
                self.add_result("测试9.1: 并发备份支持", False, f"仅{len(successful_backups)}/3成功")
            
        except Exception as e:
            self.add_result("测试9: 并发备份操作", False, f"异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "🎯"*40)
        print("向量存储备份功能测试")
        print("🎯"*40)
        
        await self.test_backup_manager_initialization()
        await self.test_create_backup()
        await self.test_list_backups()
        await self.test_delete_backup()
        await self.test_backup_stats()
        await self.test_cleanup_old_backups()
        await self.test_restore_backup()
        await self.test_backup_metadata_persistence()
        await self.test_concurrent_backup_operations()
        
        # 打印总结
        print("\n" + "="*80)
        print("📊 测试结果总结")
        print("="*80)
        
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        
        for result in self.results:
            status = "✅" if result["passed"] else "❌"
            print(f"{status} {result['test']}")
            if result["details"]:
                print(f"   └─ {result['details']}")
        
        print(f"\n总计: {passed}/{total} 测试通过")
        
        if passed == total:
            print("\n🎉 所有测试通过！向量存储备份功能完整！")
        elif passed >= total * 0.8:
            print(f"\n⚠️  大部分测试通过（{passed}/{total}），建议修复失败项")
        else:
            print(f"\n❌ 多项测试失败（{passed}/{total}），需要立即修复")
        
        return passed == total


async def main():
    """主函数"""
    tester = TestVectorStoreBackup()
    success = await tester.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
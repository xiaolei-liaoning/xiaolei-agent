"""
向量存储备份管理器

功能：
1. 定期自动备份向量数据库
2. 支持手动触发备份
3. 备份文件版本管理（保留最近N个版本）
4. 备份恢复功能
5. 备份状态监控
"""

import asyncio
import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VectorStoreBackupManager:
    """向量存储备份管理器"""
    
    def __init__(self, backup_dir: str = None, max_backups: int = 5):
        """
        初始化备份管理器
        
        Args:
            backup_dir: 备份目录路径
            max_backups: 最大保留备份数量
        """
        # 默认备份目录
        if backup_dir is None:
            backup_dir = os.path.expanduser("~/.小雷版小龙虾/vector_store_backups")
        
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_backups = max_backups
        self.backup_metadata_file = self.backup_dir / "backup_metadata.json"
        
        # 加载元数据
        self.metadata = self._load_metadata()
        
        logger.info(f"向量存储备份管理器初始化完成: {self.backup_dir}")
    
    def _load_metadata(self) -> Dict[str, Any]:
        """加载备份元数据"""
        if self.backup_metadata_file.exists():
            try:
                with open(self.backup_metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载备份元数据失败: {e}")
                return {"backups": []}
        else:
            return {"backups": []}
    
    def _save_metadata(self):
        """保存备份元数据"""
        try:
            with open(self.backup_metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存备份元数据失败: {e}")
    
    async def create_backup(self, source_path: str, description: str = "") -> Dict[str, Any]:
        """
        创建向量存储备份
        
        Args:
            source_path: 源数据路径（ChromaDB目录或其他向量存储路径）
            description: 备份描述
            
        Returns:
            备份信息字典
        """
        try:
            source = Path(source_path)
            if not source.exists():
                raise FileNotFoundError(f"源路径不存在: {source_path}")
            
            # 生成备份文件名（带时间戳和随机数）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            import random
            random_suffix = random.randint(1000, 9999)
            backup_name = f"vector_store_{timestamp}_{random_suffix}"
            backup_path = self.backup_dir / backup_name
            
            logger.info(f"开始创建备份: {backup_name}")
            
            # 异步执行复制操作
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: shutil.copytree(str(source), str(backup_path))
            )
            
            # 记录备份信息
            backup_info = {
                "id": backup_name,
                "timestamp": timestamp,
                "datetime": datetime.now().isoformat(),
                "source_path": str(source),
                "backup_path": str(backup_path),
                "description": description,
                "size_mb": self._get_directory_size_mb(backup_path),
                "status": "completed"
            }
            
            # 更新元数据
            self.metadata["backups"].append(backup_info)
            self._cleanup_old_backups()
            self._save_metadata()
            
            logger.info(f"备份创建成功: {backup_name} ({backup_info['size_mb']:.2f} MB)")
            return backup_info
            
        except Exception as e:
            logger.error(f"创建备份失败: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def restore_backup(self, backup_id: str, target_path: str) -> Dict[str, Any]:
        """
        恢复向量存储备份
        
        Args:
            backup_id: 备份ID
            target_path: 恢复目标路径
            
        Returns:
            恢复结果
        """
        try:
            # 查找备份
            backup_info = self._find_backup(backup_id)
            if not backup_info:
                raise ValueError(f"备份不存在: {backup_id}")
            
            backup_path = Path(backup_info["backup_path"])
            target = Path(target_path)
            
            if not backup_path.exists():
                raise FileNotFoundError(f"备份文件不存在: {backup_path}")
            
            logger.info(f"开始恢复备份: {backup_id} -> {target_path}")
            
            # 如果目标已存在，先删除
            if target.exists():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: shutil.rmtree(str(target)))
            
            # 恢复备份
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: shutil.copytree(str(backup_path), str(target))
            )
            
            logger.info(f"备份恢复成功: {backup_id}")
            return {
                "status": "success",
                "backup_id": backup_id,
                "target_path": str(target)
            }
            
        except Exception as e:
            logger.error(f"恢复备份失败: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """列出所有备份"""
        return sorted(
            self.metadata["backups"],
            key=lambda x: x["timestamp"],
            reverse=True
        )
    
    async def delete_backup(self, backup_id: str) -> Dict[str, Any]:
        """
        删除指定备份
        
        Args:
            backup_id: 备份ID
            
        Returns:
            删除结果
        """
        try:
            backup_info = self._find_backup(backup_id)
            if not backup_info:
                raise ValueError(f"备份不存在: {backup_id}")
            
            backup_path = Path(backup_info["backup_path"])
            
            # 删除备份文件
            if backup_path.exists():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: shutil.rmtree(str(backup_path)))
            
            # 从元数据中移除
            self.metadata["backups"] = [
                b for b in self.metadata["backups"] if b["id"] != backup_id
            ]
            self._save_metadata()
            
            logger.info(f"备份删除成功: {backup_id}")
            return {"status": "success", "backup_id": backup_id}
            
        except Exception as e:
            logger.error(f"删除备份失败: {e}")
            return {"status": "failed", "error": str(e)}
    
    def get_backup_info(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """获取备份详细信息"""
        return self._find_backup(backup_id)
    
    def _find_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """查找备份"""
        for backup in self.metadata["backups"]:
            if backup["id"] == backup_id:
                return backup
        return None
    
    def _cleanup_old_backups(self):
        """清理旧备份，保留最近的max_backups个"""
        backups = self.metadata["backups"]
        
        if len(backups) > self.max_backups:
            # 按时间排序，删除最旧的
            sorted_backups = sorted(backups, key=lambda x: x["timestamp"])
            to_delete = sorted_backups[:len(backups) - self.max_backups]
            
            for backup in to_delete:
                backup_path = Path(backup["backup_path"])
                if backup_path.exists():
                    try:
                        shutil.rmtree(str(backup_path))
                        logger.info(f"清理旧备份: {backup['id']}")
                    except Exception as e:
                        logger.error(f"清理备份失败 {backup['id']}: {e}")
            
            # 更新元数据
            self.metadata["backups"] = sorted_backups[-self.max_backups:]
    
    def _get_directory_size_mb(self, path: Path) -> float:
        """计算目录大小（MB）"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(str(path)):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size / (1024 * 1024)
    
    async def schedule_auto_backup(
        self,
        source_path: str,
        interval_hours: int = 24,
        description: str = "自动备份"
    ):
        """
        设置定时自动备份
        
        Args:
            source_path: 源数据路径
            interval_hours: 备份间隔（小时）
            description: 备份描述
        """
        logger.info(f"启动自动备份任务: 每{interval_hours}小时")
        
        while True:
            try:
                await self.create_backup(source_path, description)
                logger.info(f"自动备份完成，等待{interval_hours}小时")
            except Exception as e:
                logger.error(f"自动备份失败: {e}")
            
            # 等待指定时间
            await asyncio.sleep(interval_hours * 3600)
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """获取备份统计信息"""
        backups = self.metadata["backups"]
        
        if not backups:
            return {
                "total_backups": 0,
                "total_size_mb": 0,
                "oldest_backup": None,
                "newest_backup": None
            }
        
        total_size = sum(b.get("size_mb", 0) for b in backups)
        sorted_backups = sorted(backups, key=lambda x: x["timestamp"])
        
        return {
            "total_backups": len(backups),
            "total_size_mb": round(total_size, 2),
            "oldest_backup": sorted_backups[0]["datetime"] if sorted_backups else None,
            "newest_backup": sorted_backups[-1]["datetime"] if sorted_backups else None,
            "max_backups": self.max_backups
        }


# ═══════════════════════════════════════════════════════════════════════════
#  全局单例
# ═══════════════════════════════════════════════════════════════════════════
_backup_manager_instance: Optional[VectorStoreBackupManager] = None


def get_vector_store_backup_manager() -> VectorStoreBackupManager:
    """获取向量存储备份管理器全局单例"""
    global _backup_manager_instance
    if _backup_manager_instance is None:
        _backup_manager_instance = VectorStoreBackupManager()
    return _backup_manager_instance

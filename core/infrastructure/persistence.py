"""持久化模块

实现任务和对话的持久化存储
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import sqlite3

logger = logging.getLogger(__name__)


class PersistenceManager:
    """持久化管理器"""
    
    def __init__(self, db_path: str = "./data/persistence.db"):
        self.db_path = db_path
        self._init_db()
        logger.info("持久化管理器初始化完成")
    
    def _init_db(self):
        """初始化数据库"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建任务表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            params TEXT NOT NULL,
            status TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            result TEXT,
            error TEXT
        )
        ''')
        
        # 创建对话表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            agent_id TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            tool_call TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_user_agent ON conversations(user_id, agent_id)')
        
        conn.commit()
        conn.close()
    
    def save_task(self, task_id: str, task_type: str, params: Dict[str, Any], status: str, 
                 priority: int = 0, result: Optional[Dict[str, Any]] = None, 
                 error: Optional[str] = None):
        """保存任务
        
        Args:
            task_id: 任务ID
            task_type: 任务类型
            params: 任务参数
            status: 任务状态
            priority: 优先级
            result: 任务结果
            error: 错误信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            INSERT OR REPLACE INTO tasks 
            (id, type, params, status, priority, updated_at, result, error)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            ''', (
                task_id,
                task_type,
                json.dumps(params),
                status,
                priority,
                json.dumps(result) if result else None,
                error
            ))
            conn.commit()
            logger.info(f"任务已保存: {task_id}")
        except Exception as e:
            logger.error(f"保存任务失败: {e}")
        finally:
            conn.close()
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "id": row[0],
                    "type": row[1],
                    "params": json.loads(row[2]),
                    "status": row[3],
                    "priority": row[4],
                    "created_at": row[5],
                    "updated_at": row[6],
                    "result": json.loads(row[7]) if row[7] else None,
                    "error": row[8]
                }
            return None
        except Exception as e:
            logger.error(f"获取任务失败: {e}")
            return None
        finally:
            conn.close()
    
    def get_tasks_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """根据状态获取任务
        
        Args:
            status: 任务状态
            limit: 限制数量
            
        Returns:
            任务列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?', 
                         (status, limit))
            rows = cursor.fetchall()
            
            tasks = []
            for row in rows:
                tasks.append({
                    "id": row[0],
                    "type": row[1],
                    "params": json.loads(row[2]),
                    "status": row[3],
                    "priority": row[4],
                    "created_at": row[5],
                    "updated_at": row[6],
                    "result": json.loads(row[7]) if row[7] else None,
                    "error": row[8]
                })
            return tasks
        except Exception as e:
            logger.error(f"获取任务失败: {e}")
            return []
        finally:
            conn.close()
    
    def save_conversation(self, conversation_id: str, user_id: int, agent_id: str, 
                         role: str, message: str, tool_call: Optional[Dict[str, Any]] = None):
        """保存对话
        
        Args:
            conversation_id: 对话ID
            user_id: 用户ID
            agent_id: Agent ID
            role: 角色
            message: 消息内容
            tool_call: 工具调用信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            INSERT INTO conversations 
            (id, user_id, agent_id, role, message, tool_call)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                conversation_id,
                user_id,
                agent_id,
                role,
                message,
                json.dumps(tool_call) if tool_call else None
            ))
            conn.commit()
            logger.info(f"对话已保存: {conversation_id}")
        except Exception as e:
            logger.error(f"保存对话失败: {e}")
        finally:
            conn.close()
    
    def get_conversations(self, user_id: int, agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取对话历史
        
        Args:
            user_id: 用户ID
            agent_id: Agent ID
            limit: 限制数量
            
        Returns:
            对话列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            SELECT * FROM conversations 
            WHERE user_id = ? AND agent_id = ? 
            ORDER BY timestamp DESC LIMIT ?
            ''', (user_id, agent_id, limit))
            rows = cursor.fetchall()
            
            conversations = []
            for row in rows:
                conversations.append({
                    "id": row[0],
                    "user_id": row[1],
                    "agent_id": row[2],
                    "role": row[3],
                    "message": row[4],
                    "tool_call": json.loads(row[5]) if row[5] else None,
                    "timestamp": row[6]
                })
            return list(reversed(conversations))  # 按时间正序返回
        except Exception as e:
            logger.error(f"获取对话失败: {e}")
            return []
        finally:
            conn.close()
    
    def delete_old_tasks(self, days: int = 7):
        """删除旧任务
        
        Args:
            days: 保留天数
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            DELETE FROM tasks 
            WHERE created_at < datetime('now', '-' || ? || ' days')
            ''', (days,))
            deleted = cursor.rowcount
            conn.commit()
            logger.info(f"删除了 {deleted} 个旧任务")
        except Exception as e:
            logger.error(f"删除旧任务失败: {e}")
        finally:
            conn.close()
    
    def delete_old_conversations(self, days: int = 30):
        """删除旧对话
        
        Args:
            days: 保留天数
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            DELETE FROM conversations 
            WHERE timestamp < datetime('now', '-' || ? || ' days')
            ''', (days,))
            deleted = cursor.rowcount
            conn.commit()
            logger.info(f"删除了 {deleted} 个旧对话")
        except Exception as e:
            logger.error(f"删除旧对话失败: {e}")
        finally:
            conn.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            统计信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 任务统计
            cursor.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status')
            task_stats = dict(cursor.fetchall())
            
            # 对话统计
            cursor.execute('SELECT agent_id, COUNT(*) FROM conversations GROUP BY agent_id')
            conversation_stats = dict(cursor.fetchall())
            
            return {
                "task_stats": task_stats,
                "conversation_stats": conversation_stats
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
        finally:
            conn.close()


# 全局持久化管理器实例
persistence_manager = PersistenceManager()
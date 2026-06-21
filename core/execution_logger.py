"""执行日志模块 - Hermes自我进化第一步

使用MySQL数据库记录每次工具调用的原始数据，为后续复盘提供素材。

执行日志内容：
- 调用了什么工具
- 参数是什么
- 成功还是失败
- 用户有没有纠正
- 耗时多少
"""

import json
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    USER_CORRECTED = "user_corrected"


@dataclass
class ExecutionLogEntry:
    """执行日志数据结构（内存中使用）"""
    log_id: str
    task_id: str
    timestamp: str
    tool_name: str
    params: Dict[str, Any]
    result: Optional[str]
    status: str
    duration_ms: float
    user_feedback: Optional[str] = None
    error_message: Optional[str] = None
    session_id: Optional[str] = None
    agent_type: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionLogEntry":
        return cls(**data)


class ExecutionLogger:
    """执行日志记录器（MySQL版 + 批量写入优化）

    功能：
    - 记录每次工具调用的详细信息到MySQL
    - 支持按任务ID、会话ID检索
    - 提供复盘触发判断
    - 批量写入优化（减少IO次数）
    """

    def __init__(self, db_session=None, batch_size: int = 10, flush_interval: float = 5.0):
        self.db_session = db_session
        self.current_session_id = str(uuid.uuid4())[:8]
        self.current_task_id: Optional[str] = None
        self._task_logs: Dict[str, List[ExecutionLogEntry]] = {}
        self._log_queue: List[ExecutionLogEntry] = []
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._last_flush_time = datetime.now()
        self._pending_count = 0

        logger.info("ExecutionLogger 初始化完成（批量写入优化: batch_size=%d, flush_interval=%.1fs）", batch_size, flush_interval)

    def _get_db_session(self):
        """获取数据库会话"""
        if self.db_session is None:
            try:
                from core.database import get_db_session as get_session
                return get_session()
            except Exception as e:
                logger.warning("数据库会话获取失败: %s", e)
                return None
        return self.db_session

    def start_task(self, task_id: Optional[str] = None, description: Optional[str] = None) -> str:
        """开始一个新任务"""
        if task_id is None:
            task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.current_task_id = task_id
        if task_id not in self._task_logs:
            self._task_logs[task_id] = []

        logger.info("任务开始: %s, 描述: %s", task_id, description)
        return task_id

    def log(
        self,
        tool_name: str,
        params: Dict[str, Any],
        result: Optional[str] = None,
        status: str = ExecutionStatus.SUCCESS.value,
        duration_ms: float = 0,
        user_feedback: Optional[str] = None,
        error_message: Optional[str] = None,
        agent_type: Optional[str] = None,
        notes: Optional[str] = None,
        immediate: bool = False,
    ) -> str:
        """记录一次工具调用

        Args:
            immediate: 是否立即写入（影响批量写入策略）
        """
        if self.current_task_id is None:
            self.start_task()

        log_id = str(uuid.uuid4())[:12]

        log_entry = ExecutionLogEntry(
            log_id=log_id,
            task_id=self.current_task_id,
            timestamp=datetime.now().isoformat(),
            tool_name=tool_name,
            params=params,
            result=result,
            status=status,
            duration_ms=duration_ms,
            user_feedback=user_feedback,
            error_message=error_message,
            session_id=self.current_session_id,
            agent_type=agent_type,
            notes=notes,
        )

        self._task_logs[self.current_task_id].append(log_entry)

        if immediate:
            self._save_log_to_db(log_entry)
        else:
            self._log_queue.append(log_entry)
            self._pending_count += 1
            if self._should_flush():
                self._flush_batch()

        logger.debug(
            "执行日志记录: tool=%s, status=%s, task=%s",
            tool_name, status, self.current_task_id
        )

        return log_id

    def _should_flush(self) -> bool:
        """判断是否应该刷新队列"""
        if len(self._log_queue) >= self._batch_size:
            return True
        elapsed = (datetime.now() - self._last_flush_time).total_seconds()
        if elapsed >= self._flush_interval and self._log_queue:
            return True
        return False

    def _flush_batch(self):
        """批量写入日志到数据库"""
        if not self._log_queue:
            return

        queue_to_write = self._log_queue[:]
        self._log_queue.clear()
        self._pending_count = 0
        self._last_flush_time = datetime.now()

        try:
            from core.database import get_db_session, ExecutionLog

            try:
                with get_db_session() as session:
                    for log_entry in queue_to_write:
                        db_log = ExecutionLog(
                            log_id=log_entry.log_id,
                            task_id=log_entry.task_id,
                            timestamp=datetime.fromisoformat(log_entry.timestamp),
                            tool_name=log_entry.tool_name,
                            params=log_entry.params,
                            result=log_entry.result,
                            status=log_entry.status,
                            duration_ms=log_entry.duration_ms,
                            user_feedback=log_entry.user_feedback,
                            error_message=log_entry.error_message,
                            session_id=log_entry.session_id,
                            agent_type=log_entry.agent_type,
                            notes=log_entry.notes,
                        )
                        session.add(db_log)
                    session.commit()
                    logger.debug("批量写入 %d 条日志到数据库", len(queue_to_write))
            except RuntimeError as db_error:
                if "数据库未初始化" in str(db_error):
                    logger.debug("数据库未初始化，跳过日志持久化")
                else:
                    raise

        except Exception as e:
            logger.warning("批量写入日志失败: %s, 退回队列", e)
            self._log_queue.extend(queue_to_write)
            self._pending_count = len(self._log_queue)

    def flush(self):
        """手动刷新队列（确保所有日志写入）"""
        self._flush_batch()

    def close(self):
        """关闭日志记录器（刷新队列）"""
        self.flush()
        logger.info("ExecutionLogger 已关闭")

    def _save_log_to_db(self, log_entry: ExecutionLogEntry):
        """保存日志到MySQL"""
        try:
            from core.database import get_db_session, ExecutionLog

            try:
                with get_db_session() as session:
                    db_log = ExecutionLog(
                        log_id=log_entry.log_id,
                        task_id=log_entry.task_id,
                        timestamp=datetime.fromisoformat(log_entry.timestamp),
                        tool_name=log_entry.tool_name,
                        params=log_entry.params,
                        result=log_entry.result,
                        status=log_entry.status,
                        duration_ms=log_entry.duration_ms,
                        user_feedback=log_entry.user_feedback,
                        error_message=log_entry.error_message,
                        session_id=log_entry.session_id,
                        agent_type=log_entry.agent_type,
                        notes=log_entry.notes,
                    )

                    session.add(db_log)
            except RuntimeError as db_error:
                if "数据库未初始化" in str(db_error):
                    logger.debug("数据库未初始化，跳过日志持久化")
                else:
                    raise

        except Exception as e:
            logger.warning("保存执行日志到数据库失败: %s", e)

    def get_task_logs(self, task_id: str) -> List[ExecutionLogEntry]:
        """获取指定任务的全部日志"""
        return self._task_logs.get(task_id, [])

    def get_session_logs(self, session_id: Optional[str] = None) -> List[ExecutionLogEntry]:
        """获取指定会话的全部日志"""
        if session_id is None:
            session_id = self.current_session_id

        all_logs = []
        for logs in self._task_logs.values():
            all_logs.extend([log for log in logs if log.session_id == session_id])

        return sorted(all_logs, key=lambda x: x.timestamp)

    def search_logs(
        self,
        query: Optional[str] = None,
        tool_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ExecutionLogEntry]:
        """从数据库搜索日志"""
        try:
            session = self._get_db_session()
            if session is None:
                return []

            from core.database import ExecutionLog
            from sqlalchemy import desc

            q = session.query(ExecutionLog)

            if tool_name:
                q = q.filter(ExecutionLog.tool_name == tool_name)
            if status:
                q = q.filter(ExecutionLog.status == status)
            if query:
                q = q.filter(ExecutionLog.result.contains(query))

            logs = q.order_by(desc(ExecutionLog.timestamp)).limit(limit).all()

            return [
                ExecutionLogEntry(
                    log_id=log.log_id,
                    task_id=log.task_id,
                    timestamp=log.timestamp.isoformat(),
                    tool_name=log.tool_name,
                    params=log.params or {},
                    result=log.result,
                    status=log.status,
                    duration_ms=log.duration_ms,
                    user_feedback=log.user_feedback,
                    error_message=log.error_message,
                    session_id=log.session_id,
                    agent_type=log.agent_type,
                    notes=log.notes,
                )
                for log in logs
            ]

        except Exception as e:
            logger.warning("搜索日志失败: %s", e)
            return []

    def get_statistics(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """获取执行统计"""
        logs = self._task_logs.get(task_id, []) if task_id else self.get_session_logs()

        if not logs:
            return {
                "total_calls": 0,
                "success_count": 0,
                "failed_count": 0,
                "user_corrected_count": 0,
                "total_duration_ms": 0,
                "tools_used": {},
            }

        stats = {
            "total_calls": len(logs),
            "success_count": sum(1 for log in logs if log.status == ExecutionStatus.SUCCESS.value),
            "failed_count": sum(1 for log in logs if log.status == ExecutionStatus.FAILED.value),
            "user_corrected_count": sum(1 for log in logs if log.user_feedback),
            "total_duration_ms": sum(log.duration_ms for log in logs),
            "avg_duration_ms": sum(log.duration_ms for log in logs) / len(logs) if logs else 0,
            "tools_used": {},
        }

        for log in logs:
            stats["tools_used"][log.tool_name] = stats["tools_used"].get(log.tool_name, 0) + 1

        return stats

    def should_trigger_review(self, task_id: Optional[str] = None) -> bool:
        """判断是否应该触发复盘 - 增强版

        触发条件（满足任一）：
        - 工具调用 >= 5次
        - 用户纠正过
        - 有失败后恢复成功
        - 连续失败 >= 3次
        - 失败率 > 50%
        """
        logs = self._task_logs.get(task_id, []) if task_id else self.get_session_logs()

        if len(logs) >= 5:
            return True

        if any(log.user_feedback for log in logs):
            return True

        has_recovery = False
        consecutive_failures = 0
        max_consecutive_failures = 0
        failed_count = 0

        for log in logs:
            if log.status == ExecutionStatus.FAILED.value:
                failed_count += 1
                consecutive_failures += 1
                max_consecutive_failures = max(max_consecutive_failures, consecutive_failures)
                has_recovery = True
            else:
                consecutive_failures = 0

            if has_recovery and log.status == ExecutionStatus.SUCCESS.value:
                return True

        if max_consecutive_failures >= 3:
            logger.info("触发复盘: 连续失败 %d 次", max_consecutive_failures)
            return True

        if len(logs) >= 3 and failed_count > len(logs) / 2:
            logger.info("触发复盘: 失败率 %.0f%% (%d/%d)", failed_count/len(logs)*100, failed_count, len(logs))
            return True

        return False

    def format_logs_for_review(self, task_id: Optional[str] = None) -> str:
        """格式化日志供复盘使用"""
        logs = self._task_logs.get(task_id, []) if task_id else self.get_session_logs()

        formatted = []
        for i, log in enumerate(logs, 1):
            status_icon = "✅" if log.status == ExecutionStatus.SUCCESS.value else "❌"
            params_str = json.dumps(log.params, ensure_ascii=False)[:100]
            formatted.append(
                f"{i}. {status_icon} [{log.tool_name}] "
                f"参数: {params_str}... "
                f"耗时: {log.duration_ms:.0f}ms"
            )
            if log.error_message:
                formatted.append(f"   错误: {log.error_message}")
            if log.user_feedback:
                formatted.append(f"   用户纠正: {log.user_feedback}")

        return "\n".join(formatted)


_execution_logger_instance: Optional[ExecutionLogger] = None


def get_execution_logger() -> ExecutionLogger:
    """获取执行日志器单例"""
    global _execution_logger_instance
    if _execution_logger_instance is None:
        _execution_logger_instance = ExecutionLogger()
    return _execution_logger_instance

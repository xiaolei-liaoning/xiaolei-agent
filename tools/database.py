"""
数据库操作工具 - 真正的数据库操作，不是代码生成

支持：
- SQLite 数据库操作
- MySQL 数据库操作
- SQL 查询助手
- 数据库迁移
"""

import sqlite3
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection(db_path: str, readonly: bool = False):
    """
    数据库连接上下文管理器

    Args:
        db_path: 数据库文件路径
        readonly: 是否只读

    Yields:
        数据库连接对象
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 允许通过列名访问
    if readonly:
        conn.execute("PRAGMA locking_mode=OFF")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_sqlite_query(
    db_path: str,
    query: str,
    params: tuple = None,
    fetch_all: bool = True
) -> List[Dict[str, Any]] or Dict[str, Any]:
    """
    执行 SQLite 查询

    Args:
        db_path: 数据库文件路径
        query: SQL 查询语句
        params: 查询参数（元组）
        fetch_all: 是否获取所有结果

    Returns:
        查询结果列表
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        if fetch_all:
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return results
        else:
            return cursor.fetchone()


def execute_sqlite_command(
    db_path: str,
    command: str,
    params: tuple = None
) -> int:
    """
    执行 SQLite 命令（INSERT, UPDATE, DELETE 等）

    Args:
        db_path: 数据库文件路径
        command: SQL 命令
        params: 命令参数

    Returns:
        影响的行数
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if params:
            cursor.execute(command, params)
        else:
            cursor.execute(command)
        return cursor.rowcount


def create_sqlite_table(
    db_path: str,
    table_name: str,
    columns: Dict[str, str],
    if_not_exists: bool = True
) -> bool:
    """
    创建 SQLite 表

    Args:
        db_path: 数据库文件路径
        table_name: 表名
        columns: 列定义字典 {列名: 类型}
        if_not_exists: 如果表存在是否创建

    Returns:
        是否成功
    """
    column_defs = ", ".join([f"`{name}` {type_}" for name, type_ in columns.items()])
    if_clause = "IF NOT EXISTS" if if_not_exists else ""
    query = f"CREATE TABLE {if_clause} `{table_name}` ({column_defs})"

    try:
        execute_sqlite_command(db_path, query)
        logger.info(f"表创建成功: {table_name}")
        return True
    except Exception as e:
        logger.error(f"表创建失败: {e}")
        raise


def insert_sqlite_data(
    db_path: str,
    table_name: str,
    data: List[Dict[str, Any]] or Dict[str, Any]
) -> int:
    """
    插入数据到 SQLite 表

    Args:
        db_path: 数据库文件路径
        table_name: 表名
        data: 数据列表或字典

    Returns:
        插入的行数
    """
    if isinstance(data, dict):
        data = [data]

    if not data:
        return 0

    keys = list(data[0].keys())
    placeholders = ", ".join(["?"] * len(keys))
    column_names = ", ".join([f"`{k}`" for k in keys])
    values = [tuple(d[k] for k in keys) for d in data]

    query = f"INSERT INTO `{table_name}` ({column_names}) VALUES ({placeholders})"
    return execute_sqlite_command(db_path, query, values)


def update_sqlite_data(
    db_path: str,
    table_name: str,
    data: Dict[str, Any],
    where: str = "1=1",
    params: tuple = None
) -> int:
    """
    更新 SQLite 表数据

    Args:
        db_path: 数据库文件路径
        table_name: 表名
        data: 要更新的字段字典
        where: WHERE 条件
        params: WHERE 条件参数

    Returns:
        更新的行数
    """
    set_clause = ", ".join([f"`{k}` = ?" for k in data.keys()])
    query = f"UPDATE `{table_name}` SET {set_clause} WHERE {where}"
    all_params = tuple(data.values()) + (params or ())

    return execute_sqlite_command(db_path, query, all_params)


def delete_sqlite_data(
    db_path: str,
    table_name: str,
    where: str = "1=1",
    params: tuple = None
) -> int:
    """
    删除 SQLite 表数据

    Args:
        db_path: 数据库文件路径
        table_name: 表名
        where: WHERE 条件
        params: WHERE 条件参数

    Returns:
        删除的行数
    """
    query = f"DELETE FROM `{table_name}` WHERE {where}"
    return execute_sqlite_command(db_path, query, params)


def query_table_info(db_path: str, table_name: str) -> List[Dict[str, Any]]:
    """
    查询表结构信息

    Args:
        db_path: 数据库文件路径
        table_name: 表名

    Returns:
        列信息列表
    """
    query = """
    SELECT
        name as column_name,
        type as data_type,
        pk as is_primary_key,
        not null as is_not_null
    FROM pragma_table_info(?)
    """
    return execute_sqlite_query(db_path, query, (table_name,))


def query_database_stats(db_path: str) -> Dict[str, Any]:
    """
    查询数据库统计信息

    Args:
        db_path: 数据库文件路径

    Returns:
        统计信息
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 表数量
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]

        # 总行数（估算）
        cursor.execute("""
            SELECT SUM(pg_count) FROM (
                SELECT name, pg_count FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'
            )
        """)
        total_rows = cursor.fetchone()[0] or 0

        # 数据库大小
        cursor.execute(f"PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        cursor.execute(f"PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        db_size = page_count * page_size

        return {
            'table_count': table_count,
            'total_rows': total_rows,
            'db_size': db_size,
            'db_size_human': _human_readable_size(db_size)
        }


def create_table_from_csv(
    db_path: str,
    csv_path: str,
    table_name: str = None,
    if_not_exists: bool = True
) -> str:
    """
    从 CSV 文件创建表

    Args:
        db_path: 数据库文件路径
        csv_path: CSV 文件路径
        table_name: 表名（默认使用 CSV 文件名）
        if_not_exists: 如果表存在是否创建

    Returns:
        创建的表名
    """
    import csv
    import os

    if not table_name:
        table_name = os.path.splitext(os.path.basename(csv_path))[0]

    # 读取 CSV 获取列信息
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)

        # 估计数据类型
        columns = {}
        for i, header in enumerate(headers):
            # 尝试读取前几行判断类型
            first_val = None
            for row in reader:
                if row:
                    first_val = row[i]
                    break
                reader = csv.reader([row])
                break

            if first_val is None:
                columns[header] = "TEXT"
            elif first_val.isdigit():
                columns[header] = "INTEGER"
            else:
                columns[header] = "TEXT"

    # 重建 reader 读取所有数据
    reader = csv.DictReader(open(csv_path, 'r', encoding='utf-8'))

    # 创建表
    create_sqlite_table(db_path, table_name, columns, if_not_exists)

    # 插入数据
    insert_sqlite_data(db_path, table_name, [row for row in reader])

    return table_name


def backup_database(db_path: str, backup_path: str) -> bool:
    """
    备份数据库

    Args:
        db_path: 原数据库路径
        backup_path: 备份路径

    Returns:
        是否成功
    """
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        logger.info(f"数据库备份成功: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"数据库备份失败: {e}")
        raise


def _human_readable_size(size_bytes: int) -> str:
    """将字节转换为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


# 导出工具
__all__ = [
    'execute_sqlite_query',
    'execute_sqlite_command',
    'create_sqlite_table',
    'insert_sqlite_data',
    'update_sqlite_data',
    'delete_sqlite_data',
    'query_table_info',
    'query_database_stats',
    'create_table_from_csv',
    'backup_database',
]

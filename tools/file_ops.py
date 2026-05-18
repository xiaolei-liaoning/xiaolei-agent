"""
文件操作工具 - 真正的文件操作，不是代码生成

提供常用的文件系统操作：
- 读取/写入文件
- 目录管理
- 文件搜索
- 文件操作
"""

import os
import json
import csv
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def read_file_content(filepath: str, encoding: str = 'utf-8') -> str:
    """
    读取文件内容

    Args:
        filepath: 文件路径
        encoding: 编码方式，默认utf-8

    Returns:
        文件内容

    Raises:
        FileNotFoundError: 文件不存在
        PermissionError: 权限不足
        Exception: 读取失败
    """
    try:
        with open(filepath, 'r', encoding=encoding) as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"文件不存在: {filepath}")
        raise
    except PermissionError:
        logger.error(f"权限不足: {filepath}")
        raise
    except Exception as e:
        logger.error(f"读取文件失败 {filepath}: {e}")
        raise


def write_file_content(filepath: str, content: str, mode: str = 'w', encoding: str = 'utf-8') -> bool:
    """
    写入文件内容

    Args:
        filepath: 文件路径
        content: 要写入的内容
        mode: 模式，默认'w'
        encoding: 编码方式，默认utf-8

    Returns:
        是否成功

    Raises:
        PermissionError: 权限不足
        Exception: 写入失败
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, mode, encoding=encoding) as f:
            f.write(content)
        logger.info(f"文件写入成功: {filepath}")
        return True
    except PermissionError:
        logger.error(f"权限不足: {filepath}")
        raise
    except Exception as e:
        logger.error(f"写入文件失败 {filepath}: {e}")
        raise


def append_file_content(filepath: str, content: str, encoding: str = 'utf-8') -> bool:
    """
    追加内容到文件

    Args:
        filepath: 文件路径
        content: 要追加的内容
        encoding: 编码方式，默认utf-8

    Returns:
        是否成功
    """
    return write_file_content(filepath, content, mode='a', encoding=encoding)


def read_json_file(filepath: str) -> Dict[str, Any]:
    """
    读取JSON文件

    Args:
        filepath: JSON文件路径

    Returns:
        JSON解析后的字典
    """
    return json.loads(read_file_content(filepath))


def write_json_file(filepath: str, data: Dict[str, Any], indent: int = 2) -> bool:
    """
    写入JSON文件

    Args:
        filepath: 文件路径
        data: 要写入的数据
        indent: 缩进空格数

    Returns:
        是否成功
    """
    return write_file_content(filepath, json.dumps(data, indent=indent, ensure_ascii=False), encoding='utf-8')


def read_csv_file(filepath: str) -> List[Dict[str, str]]:
    """
    读取CSV文件

    Args:
        filepath: CSV文件路径

    Returns:
        解析后的数据列表
    """
    result = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            result.append(row)
    return result


def list_directory(path: str, recursive: bool = False) -> List[Dict[str, Any]]:
    """
    列出目录内容

    Args:
        path: 目录路径
        recursive: 是否递归（默认False）

    Returns:
        文件和目录列表
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"目录不存在: {path}")

    if not path_obj.is_dir():
        raise ValueError(f"路径不是目录: {path}")

    result = []
    if recursive:
        for entry in path_obj.rglob('*'):
            if entry.is_file() or entry.is_dir():
                result.append({
                    'name': entry.name,
                    'path': str(entry),
                    'type': 'file' if entry.is_file() else 'directory',
                    'size': entry.stat().st_size if entry.is_file() else None,
                    'modified': entry.stat().st_mtime
                })
    else:
        for entry in path_obj.iterdir():
            result.append({
                'name': entry.name,
                'path': str(entry),
                'type': 'file' if entry.is_file() else 'directory',
                'size': entry.stat().st_size if entry.is_file() else None,
                'modified': entry.stat().st_mtime
            })

    # 按类型分组
    files = [f for f in result if f['type'] == 'file']
    dirs = [f for f in result if f['type'] == 'directory']
    return {'files': files, 'directories': dirs}


def create_directory(path: str, parents: bool = True, exist_ok: bool = True) -> bool:
    """
    创建目录

    Args:
        path: 目录路径
        parents: 是否创建父目录
        exist_ok: 目录存在是否报错

    Returns:
        是否成功
    """
    try:
        Path(path).mkdir(parents=parents, exist_ok=exist_ok)
        logger.info(f"目录创建成功: {path}")
        return True
    except Exception as e:
        logger.error(f"创建目录失败 {path}: {e}")
        raise


def delete_directory(path: str, recursive: bool = True) -> bool:
    """
    删除目录

    Args:
        path: 目录路径
        recursive: 是否递归删除（目录非空时必须为True）

    Returns:
        是否成功
    """
    try:
        if Path(path).exists():
            if recursive:
                shutil.rmtree(path)
            else:
                Path(path).rmdir()
            logger.info(f"目录删除成功: {path}")
            return True
        return False
    except Exception as e:
        logger.error(f"删除目录失败 {path}: {e}")
        raise


def search_files(
    directory: str,
    pattern: str = None,
    recursive: bool = True,
    file_type: str = None
) -> List[str]:
    """
    搜索文件

    Args:
        directory: 搜索目录
        pattern: 文件名模式（支持通配符）
        recursive: 是否递归搜索
        file_type: 文件类型过滤 ('file' 或 'directory')

    Returns:
        匹配的文件路径列表
    """
    results = []
    path_obj = Path(directory)

    if not path_obj.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")

    for entry in path_obj.rglob('*') if recursive else path_obj.iterdir():
        if entry.is_file():
            if file_type == 'directory':
                continue
        elif entry.is_dir():
            if file_type == 'file':
                continue

        if pattern:
            import fnmatch
            if fnmatch.fnmatch(entry.name, pattern):
                results.append(str(entry))
        else:
            results.append(str(entry))

    return results


def get_file_info(filepath: str) -> Dict[str, Any]:
    """
    获取文件信息

    Args:
        filepath: 文件路径

    Returns:
        文件信息字典
    """
    path_obj = Path(filepath)
    if not path_obj.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    stat = path_obj.stat()

    return {
        'name': path_obj.name,
        'path': str(path_obj),
        'size': stat.st_size,
        'size_human': _human_readable_size(stat.st_size),
        'modified': stat.st_mtime,
        'created': stat.st_ctime,
        'extension': path_obj.suffix,
        'parent': str(path_obj.parent),
        'is_file': path_obj.is_file(),
        'is_directory': path_obj.is_dir()
    }


def _human_readable_size(size_bytes: int) -> str:
    """将字节转换为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def get_file_extension(filepath: str) -> str:
    """
    获取文件扩展名

    Args:
        filepath: 文件路径

    Returns:
        扩展名（包含点，如 '.txt'）
    """
    return Path(filepath).suffix


def rename_file(old_path: str, new_path: str) -> bool:
    """
    重命名文件/目录

    Args:
        old_path: 旧路径
        new_path: 新路径

    Returns:
        是否成功
    """
    try:
        Path(old_path).rename(new_path)
        logger.info(f"重命名成功: {old_path} -> {new_path}")
        return True
    except Exception as e:
        logger.error(f"重命名失败: {e}")
        raise


def copy_file(src: str, dst: str) -> bool:
    """
    复制文件

    Args:
        src: 源文件路径
        dst: 目标文件路径

    Returns:
        是否成功
    """
    try:
        shutil.copy2(src, dst)
        logger.info(f"文件复制成功: {src} -> {dst}")
        return True
    except Exception as e:
        logger.error(f"文件复制失败: {e}")
        raise


def move_file(src: str, dst: str) -> bool:
    """
    移动文件

    Args:
        src: 源文件路径
        dst: 目标文件路径

    Returns:
        是否成功
    """
    return rename_file(src, dst)


def count_files(directory: str, recursive: bool = True) -> Dict[str, int]:
    """
    统计文件数量

    Args:
        directory: 目录路径
        recursive: 是否递归

    Returns:
        各类型文件数量统计
    """
    counts = {
        'total': 0,
        'files': 0,
        'directories': 0
    }

    path_obj = Path(directory)
    if not path_obj.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")

    for entry in path_obj.rglob('*') if recursive else path_obj.iterdir():
        if entry.is_file():
            counts['files'] += 1
            counts['total'] += 1
        elif entry.is_dir():
            counts['directories'] += 1
            if recursive:
                # 递归计算子目录的文件数
                counts['files'] += len(list(entry.rglob('*')))
                counts['total'] += len(list(entry.rglob('*')))

    return counts


# 导出工具
__all__ = [
    'read_file_content',
    'write_file_content',
    'append_file_content',
    'read_json_file',
    'write_json_file',
    'read_csv_file',
    'list_directory',
    'create_directory',
    'delete_directory',
    'search_files',
    'get_file_info',
    'get_file_extension',
    'rename_file',
    'copy_file',
    'move_file',
    'count_files',
]

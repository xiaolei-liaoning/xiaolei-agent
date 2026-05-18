"""系统工具箱处理器（工业级 v3.3.0）

支持：info/time/date/memory/cpu/disk/calculate/file_list/network/ip
依赖：psutil(可选), httpx(可选, 用于IP查询)
"""

import platform
import os
import time
import logging
import subprocess
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class SystemToolboxHandler:
    """系统工具箱处理器。

    工业级特性：
    - 同步/异步双接口
    - httpx连接复用（异步IP查询）
    - 可视化ASCII进度条
    - 安全表达式计算（白名单字符检测）
    - 文件大小自动格式化
    - 完整异常处理，不崩溃

    Attributes:
        _async_client: httpx异步客户端（延迟初始化，仅IP查询使用）
    """

    def __init__(self) -> None:
        """初始化系统工具箱。"""
        self._async_client: Optional[Any] = None
        logger.info("SystemToolboxHandler 初始化完成, 平台: %s", platform.system())

    async def _get_async_client(self) -> Any:
        """获取或创建httpx异步客户端（延迟初始化）。

        Returns:
            httpx.AsyncClient 实例
        """
        if self._async_client is None or self._async_client.is_closed:
            import httpx
            self._async_client = httpx.AsyncClient(timeout=5)
        return self._async_client

    async def close(self) -> None:
        """关闭异步客户端连接。"""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
            self._async_client = None

    def execute(self, action: str = 'info', **kwargs: Any) -> Dict[str, Any]:
        """执行系统操作（同步接口）。

        Args:
            action: 操作类型，支持：
                info - 系统信息
                time - 当前时间
                date - 当前日期
                memory - 内存使用
                cpu - CPU使用
                disk - 磁盘使用
                calculate - 安全表达式计算
                file_list - 文件列表
                network - 网络信息
                ip - 公网IP
            **kwargs: 操作参数

        Returns:
            Dict[str, Any]: 操作结果
        """
        start_time = time.perf_counter()
        try:
            result = self._do_execute(action, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.debug("系统操作完成 [%s], 耗时: %.3fs", action, elapsed)
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("系统操作异常 [%s]: %s", action, e, exc_info=True)
            return {'success': False, 'error': f'系统操作异常: {e}'}

    async def aexecute(self, action: str = 'info', **kwargs: Any) -> Dict[str, Any]:
        """执行系统操作（异步接口）。

        Args:
            action: 操作类型
            **kwargs: 操作参数

        Returns:
            Dict[str, Any]: 操作结果
        """
        start_time = time.perf_counter()
        try:
            result = await self._do_async_execute(action, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.debug("系统操作完成(异步) [%s], 耗时: %.3fs", action, elapsed)
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("系统操作异常(异步) [%s]: %s", action, e, exc_info=True)
            return {'success': False, 'error': f'系统操作异常: {e}'}

    def _do_execute(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """同步核心逻辑。"""
        actions: Dict[str, Any] = {
            'info': self._system_info,
            'time': self._get_time,
            'date': self._get_date,
            'memory': self._memory_usage,
            'cpu': self._cpu_info,
            'disk': self._disk_usage,
            'calculate': self._calculate,
            'file_list': self._file_list,
            'network': self._network_info,
            'ip': self._public_ip,
            'process_list': self._process_list,
            'process_kill': self._process_kill,
            'network_speed': self._network_speed,
        }

        handler = actions.get(action)
        if not handler:
            supported = ', '.join(sorted(actions.keys()))
            logger.warning("未知系统操作: %s, 支持: %s", action, supported)
            return {'success': False, 'error': f'未知操作: {action}，支持: {supported}'}

        return handler(**kwargs)

    async def _do_async_execute(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """异步核心逻辑（IP查询走异步）。"""
        if action == 'ip':
            return await self._public_ip_async()

        # 其他操作直接在协程中运行同步版本
        return self._do_execute(action, **kwargs)

    # ── 格式化工具 ──────────────────────────────────────

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """自动格式化文件大小。

        Args:
            size_bytes: 字节数

        Returns:
            格式化的字符串 (如 "1.5GB")
        """
        for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
            if abs(size_bytes) < 1024:
                return f'{size_bytes:.1f}{unit}' if unit != 'B' else f'{size_bytes}{unit}'
            size_bytes /= 1024
        return f'{size_bytes:.1f}PB'

    @staticmethod
    def _progress_bar(percent: float, length: int = 20) -> str:
        """生成ASCII进度条。

        Args:
            percent: 百分比 (0-100)
            length: 进度条长度（字符数）

        Returns:
            进度条字符串
        """
        filled = int(length * percent / 100)
        return '█' * filled + '░' * (length - filled)

    # ── 系统信息 ────────────────────────────────────────

    def _system_info(self, **kwargs: Any) -> Dict[str, Any]:
        """获取系统信息。

        Returns:
            包含系统/版本/架构等信息的字典
        """
        info: Dict[str, str] = {
            'system': platform.system(),
            'version': platform.version(),
            'release': platform.release(),
            'machine': platform.machine(),
            'processor': platform.processor() or '未知',
            'hostname': platform.node(),
            'python_version': platform.python_version(),
            'architecture': str(platform.architecture()[0]),
        }
        return {
            'success': True,
            'action': '系统信息',
            'data': info,
            'reply': (
                f'💻 系统: {info["system"]} {info["release"]} {info["version"]}\n'
                f'架构: {info["machine"]} {info["architecture"]}\n'
                f'主机: {info["hostname"]}\n'
                f'Python: {info["python_version"]}\n'
                f'处理器: {info["processor"]}'
            ),
        }

    def _get_time(self, **kwargs: Any) -> Dict[str, Any]:
        """获取当前时间。

        Returns:
            包含时间字符串的字典
        """
        now = datetime.now()
        time_str = now.strftime('%H:%M:%S')
        return {
            'success': True, 'action': '当前时间',
            'data': {'time': time_str, 'timestamp': now.isoformat()},
            'reply': f'🕐 当前时间: {time_str}',
        }

    def _get_date(self, **kwargs: Any) -> Dict[str, Any]:
        """获取当前日期。

        Returns:
            包含日期和星期的字典
        """
        now = datetime.now()
        weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        date_str = now.strftime('%Y年%m月%d日')
        weekday = weekdays[now.weekday()]
        return {
            'success': True, 'action': '当前日期',
            'data': {'date': date_str, 'weekday': weekday, 'iso': now.strftime('%Y-%m-%d')},
            'reply': f'📅 今天是: {date_str} {weekday}',
        }

    # ── 资源监控 ────────────────────────────────────────

    def _memory_usage(self, **kwargs: Any) -> Dict[str, Any]:
        """获取内存使用情况。

        需要psutil。不可用时返回错误。

        Returns:
            包含总量/已用/可用/百分比的字典，附带ASCII进度条
        """
        try:
            import psutil  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("psutil未安装")
            return {'success': False, 'error': 'psutil未安装，请运行: pip install psutil'}

        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        percent = mem.percent

        bar = self._progress_bar(percent)
        return {
            'success': True, 'action': '内存',
            'data': {
                'total': f'{total_gb:.1f}GB',
                'used': f'{used_gb:.1f}GB',
                'available': f'{available_gb:.1f}GB',
                'percent': f'{percent}%',
            },
            'reply': (
                f'🧠 内存使用: {percent}%\n'
                f'[{bar}] {used_gb:.1f}GB / {total_gb:.1f}GB\n'
                f'可用: {available_gb:.1f}GB'
            ),
        }

    def _cpu_info(self, **kwargs: Any) -> Dict[str, Any]:
        """获取CPU信息。

        需要psutil。

        Returns:
            包含核心数/使用率/频率的字典
        """
        try:
            import psutil  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("psutil未安装")
            return {'success': False, 'error': 'psutil未安装，请运行: pip install psutil'}

        cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count()
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_freq = psutil.cpu_freq()
        freq_str = f'{cpu_freq.current:.0f}MHz' if cpu_freq else '未知'

        bar = self._progress_bar(cpu_percent)
        return {
            'success': True, 'action': 'CPU',
            'data': {
                'physical_cores': cpu_count,
                'logical_cores': cpu_count_logical,
                'usage': f'{cpu_percent}%',
                'frequency': freq_str,
            },
            'reply': (
                f'⚡ CPU: {cpu_percent}%\n'
                f'[{bar}]\n'
                f'核心: {cpu_count}物理 / {cpu_count_logical}逻辑\n'
                f'频率: {freq_str}'
            ),
        }

    def _disk_usage(self, **kwargs: Any) -> Dict[str, Any]:
        """获取磁盘使用情况。

        使用shutil.disk_usage，无需额外依赖。

        Returns:
            包含总量/已用/可用/百分比的字典
        """
        try:
            import shutil
            total, used, free = shutil.disk_usage('/')
            total_gb = total / (1024 ** 3)
            used_gb = used / (1024 ** 3)
            free_gb = free / (1024 ** 3)
            percent = used / total * 100

            bar = self._progress_bar(percent)
            return {
                'success': True, 'action': '磁盘',
                'data': {
                    'total': f'{total_gb:.1f}GB',
                    'used': f'{used_gb:.1f}GB',
                    'free': f'{free_gb:.1f}GB',
                    'percent': f'{percent:.1f}%',
                },
                'reply': (
                    f'💾 磁盘使用: {percent:.1f}%\n'
                    f'[{bar}] {used_gb:.1f}GB / {total_gb:.1f}GB\n'
                    f'可用: {free_gb:.1f}GB'
                ),
            }
        except Exception as e:
            logger.error("获取磁盘信息失败: %s", e)
            return {'success': False, 'error': f'获取磁盘信息失败: {e}'}

    # ── 工具操作 ────────────────────────────────────────

    def _calculate(self, expression: str = '', **kwargs: Any) -> Dict[str, Any]:
        """安全表达式计算。

        仅允许数字和 + - * / ( ) . 字符，防止代码注入。

        Args:
            expression: 数学表达式（如 "2+3*4"）

        Returns:
            包含计算结果的字典
        """
        if not expression:
            return {'success': False, 'error': '未指定计算表达式'}

        expression = expression.strip()
        allowed: set = set('0123456789+-*/.() ')

        for c in expression:
            if c not in allowed:
                return {'success': False, 'error': f'包含不允许的字符: "{c}"，仅支持数字和 + - * / ( ) .'}

        try:
            # 安全eval：无builtins，无全局变量
            result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
            result = round(float(result), 10) if isinstance(result, float) else result
            logger.debug("计算: %s = %s", expression, result)
            return {
                'success': True, 'action': '计算',
                'data': {'expression': expression, 'result': result},
                'reply': f'🔢 {expression} = {result}',
            }
        except ZeroDivisionError:
            return {'success': False, 'error': '除零错误'}
        except Exception as e:
            logger.warning("计算表达式错误 [%s]: %s", expression, e)
            return {'success': False, 'error': f'计算错误: {e}'}

    def _file_list(self, path: str = '.', **kwargs: Any) -> Dict[str, Any]:
        """列出目录文件，分类显示文件和目录。

        自动格式化文件大小，隐藏点文件。

        Args:
            path: 目录路径，默认当前目录

        Returns:
            包含文件/目录列表的字典
        """
        if not path:
            path = '.'

        try:
            path = os.path.expanduser(path)
            if not os.path.isdir(path):
                return {'success': False, 'error': f'路径不存在或不是目录: {path}'}

            items = os.listdir(path)
            files: List[str] = []
            dirs: List[str] = []

            for item in sorted(items):
                if item.startswith('.'):
                    continue
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    dirs.append(item)
                else:
                    size = os.path.getsize(full_path)
                    files.append(f'{item} ({self._format_size(size)})')

            limit = 30
            files_display = files[:limit]
            dirs_display = dirs[:limit]
            more_files = f'... 还有 {len(files) - limit} 个文件' if len(files) > limit else ''
            more_dirs = f'... 还有 {len(dirs) - limit} 个目录' if len(dirs) > limit else ''

            lines: List[str] = [f'📂 {path}']
            if dirs_display:
                lines.append(f'📁 目录 ({len(dirs)}):')
                lines.extend(f'  {d}' for d in dirs_display)
            if more_dirs:
                lines.append(f'  {more_dirs}')
            if files_display:
                lines.append(f'📄 文件 ({len(files)}):')
                lines.extend(f'  {f}' for f in files_display)
            if more_files:
                lines.append(f'  {more_files}')

            return {
                'success': True, 'action': '文件列表',
                'data': {'files': files, 'dirs': dirs, 'path': path,
                         'total_files': len(files), 'total_dirs': len(dirs)},
                'reply': '\n'.join(lines),
            }
        except PermissionError:
            return {'success': False, 'error': f'无权限访问: {path}'}
        except Exception as e:
            logger.error("文件列表失败 [%s]: %s", path, e)
            return {'success': False, 'error': str(e)}

    # ── 网络信息 ────────────────────────────────────────

    def _network_info(self, **kwargs: Any) -> Dict[str, Any]:
        """获取网络信息（主机名和本地IP）。

        Returns:
            包含主机名和本地IP的字典
        """
        try:
            import socket
            hostname = socket.gethostname()
            try:
                local_ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                local_ip = '未知'
            return {
                'success': True, 'action': '网络信息',
                'data': {'hostname': hostname, 'local_ip': local_ip},
                'reply': f'🌐 主机名: {hostname}\n本地IP: {local_ip}',
            }
        except Exception as e:
            logger.error("获取网络信息失败: %s", e)
            return {'success': False, 'error': str(e)}

    def _public_ip(self, **kwargs: Any) -> Dict[str, Any]:
        """获取公网IP（同步接口）。

        依次尝试多个免费API，返回第一个成功结果。

        Returns:
            包含公网IP的字典
        """
        try:
            import httpx
            apis: List[tuple] = [
                ('https://api.ipify.org?format=json', 'ip'),
                ('https://httpbin.org/ip', 'origin'),
                ('https://ifconfig.me/ip', None),
            ]
            for url, key in apis:
                try:
                    response = httpx.get(url, timeout=5)
                    response.raise_for_status()
                    if key:
                        ip = response.json().get(key, '')
                    else:
                        ip = response.text.strip()
                    if ip:
                        logger.debug("公网IP获取成功: %s", ip)
                        return {
                            'success': True, 'action': '公网IP',
                            'data': {'ip': ip},
                            'reply': f'🌐 公网IP: {ip}',
                        }
                except Exception:
                    continue
            logger.warning("所有公网IP查询接口均失败")
            return {'success': False, 'error': '所有公网IP查询接口均失败'}
        except ImportError:
            return {'success': False, 'error': 'httpx未安装，请运行: pip install httpx'}

    async def _public_ip_async(self, **kwargs: Any) -> Dict[str, Any]:
        """获取公网IP（异步接口，连接复用）。

        Returns:
            包含公网IP的字典
        """
        try:
            client = await self._get_async_client()
            apis: List[tuple] = [
                ('https://api.ipify.org?format=json', 'ip'),
                ('https://httpbin.org/ip', 'origin'),
                ('https://ifconfig.me/ip', None),
            ]
            for url, key in apis:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    if key:
                        ip = response.json().get(key, '')
                    else:
                        ip = response.text.strip()
                    if ip:
                        logger.debug("公网IP获取成功(异步): %s", ip)
                        return {
                            'success': True, 'action': '公网IP',
                            'data': {'ip': ip},
                            'reply': f'🌐 公网IP: {ip}',
                        }
                except Exception:
                    continue
            return {'success': False, 'error': '所有公网IP查询接口均失败'}
        except ImportError:
            return {'success': False, 'error': 'httpx未安装，请运行: pip install httpx'}

    def _process_list(self, **kwargs: Any) -> Dict[str, Any]:
        """获取进程列表

        Returns:
            包含进程信息的字典
        """
        try:
            import psutil

            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.info
                    cpu_percent = pinfo['cpu_percent'] if pinfo['cpu_percent'] is not None else 0.0
                    memory_percent = pinfo['memory_percent'] if pinfo['memory_percent'] is not None else 0.0
                    processes.append({
                        'PID': pinfo['pid'],
                        '名称': pinfo['name'],
                        'CPU%': f"{cpu_percent:.1f}",
                        '内存%': f"{memory_percent:.1f}",
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            processes.sort(key=lambda x: float(x['CPU%']), reverse=True)

            reply_lines = [
                f'📊 进程列表 (Top 20)',
                f'总进程数: {len(processes)}',
                '',
                'PID  | 名称           | CPU% | 内存%',
                '-' * 40,
            ]

            for proc in processes[:20]:
                reply_lines.append(
                    f"{proc['PID']:5d} | {proc['名称'][:14]:14s} | {proc['CPU%']:5s} | {proc['内存%']:6s}"
                )

            return {
                'success': True,
                'action': 'process_list',
                'data': processes,
                'reply': '\n'.join(reply_lines),
            }
        except ImportError:
            return {'success': False, 'error': 'psutil未安装，请运行: pip install psutil'}
        except Exception as e:
            logger.error(f"获取进程列表失败: {e}")
            return {'success': False, 'error': f'获取进程列表失败: {e}'}

    def _process_kill(self, pid: int = None, name: str = None, **kwargs: Any) -> Dict[str, Any]:
        """终止进程

        Args:
            pid: 进程ID
            name: 进程名称

        Returns:
            包含操作结果的字典
        """
        try:
            import psutil

            if pid:
                try:
                    proc = psutil.Process(pid)
                    proc.terminate()
                    return {
                        'success': True,
                        'action': 'process_kill',
                        'pid': pid,
                        'reply': f'✅ 已终止进程 PID: {pid}',
                    }
                except psutil.NoSuchProcess:
                    return {'success': False, 'error': f'进程不存在: PID {pid}'}
                except psutil.AccessDenied:
                    return {'success': False, 'error': f'权限不足，无法终止进程: PID {pid}'}

            elif name:
                killed_count = 0
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] == name:
                            proc.terminate()
                            killed_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                if killed_count > 0:
                    return {
                        'success': True,
                        'action': 'process_kill',
                        'name': name,
                        'killed_count': killed_count,
                        'reply': f'✅ 已终止 {killed_count} 个进程: {name}',
                    }
                else:
                    return {'success': False, 'error': f'未找到进程: {name}'}

            else:
                return {'success': False, 'error': '请指定PID或进程名称'}

        except ImportError:
            return {'success': False, 'error': 'psutil未安装，请运行: pip install psutil'}
        except Exception as e:
            logger.error(f"终止进程失败: {e}")
            return {'success': False, 'error': f'终止进程失败: {e}'}

    def _network_speed(self, **kwargs: Any) -> Dict[str, Any]:
        """获取网络速度

        Returns:
            包含网络速度的字典
        """
        try:
            import psutil
            import time

            net_io1 = psutil.net_io_counters()
            time.sleep(1)
            net_io2 = psutil.net_io_counters()

            bytes_sent = net_io2.bytes_sent - net_io1.bytes_sent
            bytes_recv = net_io2.bytes_recv - net_io1.bytes_recv

            upload_speed = self._format_size(bytes_sent) + '/s'
            download_speed = self._format_size(bytes_recv) + '/s'

            reply_lines = [
                f'📶 网络速度',
                f'上传: {upload_speed}',
                f'下载: {download_speed}',
                '',
                f'总上传: {self._format_size(net_io2.bytes_sent)}',
                f'总下载: {self._format_size(net_io2.bytes_recv)}',
            ]

            return {
                'success': True,
                'action': 'network_speed',
                'data': {
                    'upload_speed': upload_speed,
                    'download_speed': download_speed,
                    'total_sent': net_io2.bytes_sent,
                    'total_recv': net_io2.bytes_recv,
                },
                'reply': '\n'.join(reply_lines),
            }
        except ImportError:
            return {'success': False, 'error': 'psutil未安装，请运行: pip install psutil'}
        except Exception as e:
            logger.error(f"获取网络速度失败: {e}")
            return {'success': False, 'error': f'获取网络速度失败: {e}'}


system_handler = SystemToolboxHandler()
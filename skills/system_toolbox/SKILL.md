# System Toolbox - 系统工具箱

## 📋 功能描述
系统信息查询、计算器、文件操作、进程管理、网络监控等实用工具集合。
- **系统信息**：时间、日期、内存、磁盘、CPU、网络
- **计算功能**：数学表达式计算
- **文件操作**：文件列表、目录浏览
- **进程管理**：进程列表、进程终止
- **网络监控**：网络速度、公网IP查询

## 🔑 触发关键词
- **中文**：系统、时间、日期、计算、内存、磁盘、CPU、网络、文件列表
- **英文**：system, time, date, calculate, memory, disk, cpu, network

## ⚙️ 支持操作
| 操作 | 说明 | 示例 |
|------|------|------|
| info | 系统总览 | CPU/内存/磁盘概况 |
| time | 当前时间 | HH:MM:SS |
| date | 当前日期 | YYYY-MM-DD |
| memory | 内存使用 | 已用/总量/百分比 |
| disk | 磁盘空间 | 各分区使用情况 |
| cpu | CPU信息 | 核心数/使用率 |
| calculate | 数学计算 | "2+3*4" → 14 |
| file_list | 文件列表 | ls命令 |
| network | 网络信息 | IP地址/网速 |
| ip | 公网IP | 查询外网IP |
| process_list | 进程列表 | 显示运行进程 |
| process_kill | 终止进程 | 按PID或名称 |
| network_speed | 网络速度 | 上传/下载速度 |

## 💡 使用示例
```python
# 查询时间
用户: "现在几点"
→ system_toolbox.execute(action='time')

# 计算
用户: "计算 256 * 1024"
→ system_toolbox.execute(action='calculate', expression='256 * 1024')

# 系统信息
用户: "查看内存使用"
→ system_toolbox.execute(action='memory')

# 文件列表
用户: "列出桌面文件"
→ system_toolbox.execute(action='file_list', path='~/Desktop')

# 进程管理
用户: "查看进程列表"
→ system_toolbox.execute(action='process_list')

用户: "终止进程 1234"
→ system_toolbox.execute(action='process_kill', pid=1234)

# 网络监控
用户: "查看网络速度"
→ system_toolbox.execute(action='network_speed')
```

## 📦 依赖
- psutil (系统监控)
- 内置模块 (os, datetime, subprocess)

## 🎯 性能指标
- 响应时间: <50ms
- 准确率: 100% (系统API)
- 资源占用: <1MB
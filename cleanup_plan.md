# 清理计划 - 删除冗余文件

## 目标
减少代码量30%，无功能回归

## 待删除文件清单

### 1. 旧的Agent系统
- ✅ `core/agents/` - 已被 `core/multi_agent_v2/` 替代
- ✅ `core/multi_agent_system.py` - 旧实现
- ✅ `core/agent_coordinator.py` - 旧协调器
- ✅ `core/handlers.py.bak` - 备份文件

### 2. 重复文档
- `docs/` 目录下大量重复的优化报告和总结文档
- 项目根目录下的多个重复报告文件

### 3. 第三方库
- `core/awesome-mcp-servers/` - 是第三方仓库，不应放在core目录

### 4. 临时文件
- `core/修复计划.md` - 临时计划文档

## 保留文件
- 所有功能代码
- 核心文档
- 测试文件

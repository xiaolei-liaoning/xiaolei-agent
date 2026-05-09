# CLI拆分与依赖管理优化计划

## 问题分析

### 1. CLI设计问题
- **问题**：`cli.py` 2500+行，单一文件过于庞大
- **影响**：难以维护和扩展

### 2. 依赖管理问题
- **问题**：`requirements.txt` 缺少版本锁定
- **影响**：不同环境可能行为不一致

---

## 解决方案

### 方案1：CLI拆分

**目标**：将单一CLI文件拆分为模块化结构

**目标结构**：
```
cli/
├── __init__.py       # 导出主CLI类
├── base.py           # 基类和通用工具
├── colors.py         # CliColors颜色管理
├── smart.py          # SmartWorkflowCommand
├── automate.py       # AutomateCommand  
├── scrape.py         # ScrapeCommand
└── analyze.py        # AnalyzeCommand
```

**实施步骤**：
1. 创建 `cli/` 目录
2. 拆分 `cli.py` 中的各个类到独立文件
3. 创建 `__init__.py` 统一导出
4. 更新主入口引用

### 方案2：依赖版本锁定

**目标**：锁定依赖版本，确保环境一致性

**实施步骤**：
1. 使用 `pip-compile` 生成锁定文件
2. 创建 `requirements.txt`（开发依赖）
3. 创建 `requirements-lock.txt`（锁定版本）
4. 添加 `requirements-min.txt`（最小依赖）

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `cli/` | 新建 | CLI模块目录 |
| `cli/__init__.py` | 新建 | 统一导出 |
| `cli/base.py` | 新建 | 基类和通用工具 |
| `cli/colors.py` | 新建 | CliColors |
| `cli/smart.py` | 新建 | SmartWorkflowCommand |
| `cli/automate.py` | 新建 | AutomateCommand |
| `cli/scrape.py` | 新建 | ScrapeCommand |
| `cli/analyze.py` | 新建 | AnalyzeCommand |
| `cli.py` | 修改 | 改为导入cli模块的兼容层 |
| `requirements-min.txt` | 新建 | 最小依赖 |
| `requirements-lock.txt` | 新建 | 锁定版本 |

---

## 风险评估

| 风险 | 描述 | 应对 |
|------|------|------|
| 拆分后导入错误 | 循环依赖或路径问题 | 保留原cli.py作为兼容层 |
| pip-compile不可用 | 工具未安装 | 提供手动生成方案 |

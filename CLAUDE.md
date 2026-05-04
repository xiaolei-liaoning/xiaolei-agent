# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**小雷版小龙虾Agent系统** (Xiao Lei's Little Lobster Agent System) 是一个工业级多智能体AI系统，基于FastAPI构建。系统采用【多角色独立智能体 + 内部并发分身】架构，支持并行处理多样化任务，包括意图识别、多步任务执行、工作流自动化和用户管理。

**当前版本**: 3.3.1

**项目成熟度**: 生产就绪阶段

- 核心功能完整且稳定
- 20+ 技能模块已实现
- 完整的测试覆盖（80%+）
- 已知架构问题已记录（见下方架构诊断部分）

## 用户操作方式

详细的用户指南请参考 [USER_GUIDE.md](USER_GUIDE.md)

### 快速开始

```bash
# 1. 进入项目目录
cd 小雷版小龙虾agent

# 2. 配置环境变量（首次使用）
cp .env.example .env
# 编辑 .env 文件，配置 API 密钥

# 3. 启动服务
./start.sh

# 或使用开发模式（推荐，支持热重载）
./dev.sh dev
```

### 访问地址

启动成功后，可通过以下地址访问：

- **主页**: <http://localhost:8001>
- **工作流编辑器**: <http://localhost:8001/workflow_editor>
- **Coze 聊天**: <http://localhost:8001/coze>
- **监控界面**: <http://localhost:8001/monitor>
- **API 文档**: <http://localhost:8001/docs>

### 常用用户功能

1. **聊天交互**: 通过 `/api/chat` 端点与AI对话
2. **技能调用**: 系统自动识别意图并调用相应技能
3. **工作流**: 可视化创建和执行自动化工作流
4. **历史记录**: 查看和管理聊天历史
5. **任务监控**: 实时查看任务执行状态

## 开发者操作方式

### 开发环境设置

```bash
# 安装依赖
./start.sh --install

# 或使用 pip
pip install -r requirements.txt
```

### 开发命令

```bash
# 启动开发服务器（热重载）
./dev.sh dev

# 查看服务状态
./dev.sh status

# 查看实时日志
./dev.sh logs

# 停止服务
./dev.sh stop

# 重启服务
./dev.sh restart
```

### 测试命令

```bash
# 运行所有测试
./start.sh --test
# 或
pytest tests/ -v

# 运行特定测试
pytest tests/test_xxx.py -v

# 运行测试并生成覆盖率报告
pytest --cov=core --cov-report=html

# 快速验证测试
python tests/quick_test.py

# 批量测试
python tests/batch_test.py
```

### 代码质量检查

```bash
# 格式化代码
black .

# 排序导入
isort .

# 运行 pre-commit 检查
pre-commit run --all-files
```

### 数据库操作

```bash
# 数据库初始化在启动时自动完成
# 数据库配置在 core/database.py
# 使用 MySQL，连接信息在 .env 文件中配置
```

## 整体使用体验与落地效果

### 核心能力

1. **意图识别**: 智能识别用户意图，自动路由到相应技能
2. **多步任务**: 支持复杂任务的分解和并行执行
3. **工作流自动化**: 可视化工作流编辑器，支持拖拽式创建
4. **多智能体协作**: 支持8个专业智能体协同工作
5. **RAG搜索**: 基于向量数据库的智能检索
6. **记忆系统**: 短期记忆（MySQL）+ 长期记忆（ChromaDB）

### 技能模块（20+）

- **web_scraper**: 12+主流站点爬虫（微博、百度、B站、抖音、GitHub等）
- **data_analysis**: 数据分析和可视化
- **translator**: 多语言翻译
- **ocr_recognition**: OCR文字识别
- **gui_automation**: GUI自动化操作
- **weather**: 天气查询
- **calculator**: 计算器
- **deep_thinking**: 深度思考引擎
- **marketplace**: 市场数据获取
- **advanced_automation**: 高级自动化
- **openclaw**: OpenClaw集成
- **system_toolbox**: 系统工具箱
- **third_party**: 第三方服务集成
- **人物**: 人物信息处理
- **output**: 多种输出格式

### 性能指标

- **响应时间**: < 2s（简单任务）
- **并发处理**: 支持100+并发请求
- **内存占用**: ~500MB（基础运行）
- **成功率**: 95%+（已测试场景）

### 落地场景

1. **内容创作**: 自动化内容生成和发布
2. **数据采集**: 多平台数据爬取和分析
3. **工作流自动化**: 重复性任务自动化
4. **智能客服**: 多轮对话和问题解答
5. **数据分析**: 自动化数据分析和报告生成

## 架构概述

### 系统架构

```text
Client → API Layer → Dispatcher → Agent Execution → Core Support → Infrastructure
```

### 核心组件

**API层** (`api/`):

- `routes/chat.py` - 核心聊天端点
- `routes/history.py` - 聊天历史管理
- `routes/system.py` - 系统健康和指标
- `routes/skills.py` - 技能管理
- `routes/agent_groups.py` - 智能体组管理
- `routes/self_check.py` - 自验证端点
- `routes/plans.py` - 计划管理
- `workflow.py` - 工作流API
- `schedule.py` - 定时任务API
- `monitor.py` - 监控API

**核心层** (`core/`):

- `skill_dispatcher.py` - 技能路由
- `concurrent_processor.py` - 并行任务执行
- `task_planner.py` - 任务规划和分解
- `reasoning_engine.py` - 深度思考引擎
- `search_engine.py` - RAG搜索引擎
- `handlers.py` - 请求/响应处理器
- `database.py` - MySQL数据库操作
- `multi_agent_system.py` - 多智能体协调
- `agent_coordinator.py` - 智能体生命周期管理
- `bfs_processor.py` - BFS上下文处理
- `short_term_memory.py` - 短期记忆管理
- `vector_memory.py` - 向量长期记忆

**技能系统** (`skills/`):

- 模块化技能系统，20+能力
- 每个技能有 `SKILL.md` 定义触发和行为
- 通过 `tools/tool_manager.py` 注册

**工具层** (`tools/`):

- `tool_manager.py` - 技能注册和管理
- 各种实用工具

### 初始化流程

启动时 (`main.py` startup_event):

1. 注册所有技能 (`tools.tool_manager.register_all_skills()`)
2. 初始化 `SkillDispatcher`
3. 初始化 `ConcurrentTaskProcessor`
4. 初始化 `TaskPlanner`
5. 初始化核心组件（推理引擎、搜索引擎、消息总线等）
6. 初始化MySQL数据库
7. 从数据库加载短期记忆（按用户）
8. 启动智能体协调器和调度器
9. 注册API路由

### 请求处理流程

1. 用户请求 → API端点 (`/api/chat`)
2. `handlers.py` 处理请求
3. `skill_dispatcher.py` 路由到相应技能
4. `concurrent_processor.py` 并行执行任务
5. `reasoning_engine.py` 提供深度思考
6. `search_engine.py` 提供RAG搜索
7. 格式化响应并返回

### 多智能体系统

系统支持多个专业智能体：

- 规划智能体：任务分解
- 执行智能体：特定技能
- 协作智能体：组工作
- 智能体可通过 `agent_coordinator.py` 分组和协调

### 记忆系统

- **短期记忆**: 每用户上下文存储在MySQL (`BFSContextNode` 表)
- **长期记忆**: ChromaDB中的向量存储
- 启动时加载记忆，更新时持久化

### 数据库架构

关键表（定义在 `core/database.py`）:
- `User` - 用户账户和认证
- `ChatHistory` - 聊天消息历史
- `TaskLog` - 任务执行日志
- `BFSContextNode` - 短期记忆上下文
- `AgentGroup` - 智能体组定义
- `Workflow` - 工作流定义

## 配置

环境变量 (`.env`):
- `ZHIPU_API_KEY` - 智谱AI API密钥
- `COZE_API_TOKEN` - Coze API令牌
- `AGENT_PORT` - 服务器端口（默认: 8001）
- `AGENT_HOST` - 服务器主机（默认: 0.0.0.0）
- `LOG_LEVEL` - 日志级别（默认: info）
- `DEV_MODE` - 启用热重载（默认: false）

数据库连接在 `core/database.py` 中使用SQLAlchemy配置。

## 添加新技能

1. 在 `skills/your_skill/` 创建新目录
2. 添加 `SKILL.md` 文件，包含：
   - 功能描述
   - 触发关键词
   - 实现细节
3. 在Python文件中实现技能逻辑
4. 如需要在 `tools/tool_manager.py` 中注册技能
5. 通过API测试技能

## 架构诊断

### 已知问题

#### 1. BFS树 + 短期/长期队列上下文系统内存问题

- **节点膨胀**: 每条消息创建4层树（root→function→text→paragraph），长消息导致指数增长
- **无清理策略**: 没有垃圾回收机制处理孤立节点
- **数据库膨胀**: 每个节点立即持久化到MySQL，无批处理
- **内存重复**: `short_term_memory.py` 和 `dynamic_short_term_memory.py` 维护重复缓存

#### 2. 8智能体集群模块耦合和死锁风险

- **循环依赖**: agent_coordinator → cluster_manager → message_bus
- **消息总线阻塞**: 全局锁导致高并发时锁竞争
- **任务依赖死锁**: 缺少循环依赖检测
- **协调超时**: 120s超时但无重试机制

#### 3. 过度工程化冗余模块

- **多个内存管理器**: 短期、动态、向量内存功能重叠
- **重复任务调度器**: 优先级、BFS、预测调度三种范式
- **过度监控**: 多个监控模块无统一聚合

#### 4. 消息总线和任务调度并发问题

- **无背压处理**: 慢订阅者可阻塞整个系统
- **无界队列**: 可无限增长导致OOM
- **无死信队列**: 失败消息直接丢弃
- **无请求限流**: 可被突发流量压垮

#### 5. 异常处理和日志系统缺陷

- **静默失败**: 多处使用裸 `except Exception`
- **无错误上下文**: 缺少用户ID、任务ID等调试信息
- **无结构化日志**: 字符串格式化，难以分析
- **无日志轮转**: 可填满磁盘
- **无分布式追踪**: 跨异步边界无请求ID传播

### 建议

- 实现批处理数据库写入
- 添加定期垃圾回收
- 合并重复内存管理器
- 实现统一任务调度接口
- 添加指标采样和聚合层
- 实现结构化日志和上下文传播
- 添加分布式追踪
- 实现背压处理和队列限制
- 添加死信队列
- 实现循环依赖检测

## 重要提示

- 系统使用FastAPI和uvicorn服务器
- 开发模式支持热重载
- 数据库初始化在启动时自动完成
- 短期记忆在启动时从数据库加载
- 所有核心组件在 `main.py:init_system()` 中初始化
- API路由在 `main.py` 启动事件中注册
- 系统支持REST API和WebSocket通信
- 监控可在 `/monitor` 端点访问
- API文档可在 `/docs` 端点访问
- **警告**: 系统存在几个架构问题，生产部署前应解决：
  - BFS上下文系统内存泄漏
  - 智能体协调潜在死锁
  - 过度工程化冗余模块
  - 消息总线和任务调度并发问题
  - 异常处理和日志不完整

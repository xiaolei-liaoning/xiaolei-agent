# 多Agent小组协作场景完整指南

## 概述

本系统实现了两个核心协作场景：

1. **场景1：多Agent小组协作** - 当任务需要多个专业领域Agent协同完成时
2. **场景2：无对应Agent处理** - 当系统中没有配置合适的Agent处理任务时

---

## 场景1：多Agent小组协作

### 工作流程

```
用户输入任务
    ↓
系统自动分析任务需求，识别所需能力
    ↓
匹配对应的Agent小组
    ↓
主协调Agent任务拆解
    ↓
各小组并行/顺序执行子任务
    ↓
标准化信息交互
    ↓
阶段性评审（可选）
    ↓
结果整合，返回用户
```

### 协作策略

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `parallel` | 并行协作，所有子任务同时执行 | 各子任务独立，无依赖关系 |
| `sequential` | 顺序协作，子任务按序执行 | 有依赖关系，需要前序结果 |
| `hierarchical` | 分层协作（待实现） | 复杂多层次任务 |

### API使用指南

#### 1. 分析任务并推荐Agent小组

**接口**: `POST /api/agent-groups/collaborate/analyze`

**请求示例**:
```bash
curl -X POST http://localhost:8001/api/agent-groups/collaborate/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "task": "请分析百度热搜趋势并写一首关于春天的诗",
    "strategy": "parallel"
  }'
```

**响应示例**:
```json
{
  "success": true,
  "task_analysis": {
    "required_capabilities": ["web_search", "data_analysis", "creative_writing"],
    "task_type": "complex"
  },
  "recommended_groups": [
    {
      "group_id": "xxx",
      "name": "技术智囊团",
      "description": "技术问题分析和代码审查团队",
      "capabilities": ["data_analysis", "web_search"],
      "success_rate": 1.0
    },
    {
      "group_id": "yyy",
      "name": "文学创作团队",
      "description": "文学创作和翻译团队",
      "capabilities": ["creative_writing", "translation"],
      "success_rate": 1.0
    }
  ],
  "requires_new_agent": false
}
```

#### 2. 启动协作会话

**接口**: `POST /api/agent-groups/collaborate/start`

**请求示例**:
```bash
curl -X POST http://localhost:8001/api/agent-groups/collaborate/start \
  -H "Content-Type: application/json" \
  -d '{
    "task": "请分析百度热搜趋势并写一首关于春天的诗",
    "strategy": "parallel"
  }'
```

**响应示例**:
```json
{
  "success": true,
  "session_id": "abc123",
  "total_subtasks": 3,
  "participant_groups": ["xxx", "yyy"],
  "subtasks": [
    {
      "subtask_id": "st1",
      "description": "搜索并收集相关信息：请分析百度热搜趋势",
      "required_capability": "web_search",
      "assigned_group": "xxx",
      "priority": 0.8
    },
    {
      "subtask_id": "st2",
      "description": "对相关数据进行分析和统计：请分析百度热搜趋势",
      "required_capability": "data_analysis",
      "assigned_group": "xxx",
      "priority": 0.8
    },
    {
      "subtask_id": "st3",
      "description": "进行文学创作相关工作：请分析百度热搜趋势并写一首关于春天的诗",
      "required_capability": "creative_writing",
      "assigned_group": "yyy",
      "priority": 0.8
    }
  ]
}
```

#### 3. 执行协作任务

**接口**: `POST /api/agent-groups/collaborate/{session_id}/execute`

**请求示例**:
```bash
curl -X POST http://localhost:8001/api/agent-groups/collaborate/abc123/execute
```

**响应示例**:
```json
{
  "success": true,
  "session_id": "abc123",
  "final_result": "【任务执行总结】\n原始任务: 请分析百度热搜趋势并写一首关于春天的诗\n--------------------------------------------------\n✓ 搜索并收集相关信息：请分析百度热搜趋势\n  由 技术智囊团 完成\n✓ 对相关数据进行分析和统计：请分析百度热搜趋势\n  由 技术智囊团 完成\n✓ 进行文学创作相关工作：请分析百度热搜趋势并写一首关于春天的诗\n  由 文学创作团队 完成\n--------------------------------------------------\n共完成 3 个子任务",
  "subtask_results": { ... },
  "total_subtasks": 3
}
```

#### 4. 查询会话状态

**接口**: `GET /api/agent-groups/collaborate/{session_id}/status`

---

## 场景2：无对应Agent处理

### 工作流程

```
用户输入系统未覆盖的任务
    ↓
系统自动分析任务需求
    ↓
确定所需能力领域
    ↓
检查现有Agent库是否有相近能力
    ↓
有相近能力 → 临时调配
    ↓
无相近能力 → 启动临时Agent创建流程
    ↓
通知管理员添加标准Agent
    ↓
临时Agent处理（有人工监督机制）
```

### API使用指南

#### 1. 分析缺失的Agent需求

**接口**: `POST /api/agent-groups/missing-agent/analyze`

**请求示例**:
```bash
curl -X POST http://localhost:8001/api/agent-groups/missing-agent/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "task_example": "帮我开发一个简单的网页应用，需要HTML、CSS和JavaScript"
  }'
```

**响应示例**:
```json
{
  "success": true,
  "requires_new_agent": true,
  "required_capabilities": ["code_generation", "web_search", "reasoning"],
  "suggested_agent": {
    "name": "代码开发专家",
    "description": "专门处理 code_generation, web_search, reasoning 相关任务的专业Agent小组。任务示例: 帮我开发一个简单的网页应用..."
  }
}
```

#### 2. 创建临时Agent

**接口**: `POST /api/agent-groups/missing-agent/create-temporary`

**请求示例**:
```bash
curl -X POST http://localhost:8001/api/agent-groups/missing-agent/create-temporary \
  -H "Content-Type: application/json" \
  -d '{
    "task_example": "帮我开发一个简单的网页应用，需要HTML、CSS和JavaScript",
    "agent_name": "网页开发专家",
    "agent_description": "专注于前端网页开发的专业Agent"
  }'
```

**响应示例**:
```json
{
  "success": true,
  "temporary_agent": {
    "agent_id": "temp_abc123",
    "name": "网页开发专家",
    "description": "专注于前端网页开发的专业Agent",
    "capabilities": ["code_generation", "web_search", "reasoning"],
    "is_temporary": true,
    "created_at": "2026-05-02T...",
    "requires_supervision": true,
    "human_review_threshold": 0.7
  },
  "message": "临时Agent已创建，管理员将收到添加请求",
  "requires_supervision": true
}
```

#### 3. 查看待审批的Agent添加请求

**接口**: `GET /api/agent-groups/missing-agent/pending-requests`

**响应示例**:
```json
{
  "success": true,
  "pending_requests": [
    {
      "request_id": "req1",
      "agent_id": "temp_abc123",
      "agent_config": { ... },
      "request_time": "2026-05-02T...",
      "status": "pending"
    }
  ]
}
```

#### 4. 审批Agent添加请求

**接口**: `POST /api/agent-groups/missing-agent/approve`

**请求示例**:
```bash
curl -X POST http://localhost:8001/api/agent-groups/missing-agent/approve \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req1",
    "approve": true,
    "make_permanent": true
  }'
```

---

## 关键特性总结

### 场景1：多Agent小组协作

| 特性 | 实现状态 | 说明 |
|------|----------|------|
| 自动需求分析 | ✅ | 识别任务需要的能力领域 |
| 智能小组匹配 | ✅ | 推荐最合适的Agent小组组合 |
| 任务自动拆解 | ✅ | 将复杂任务拆分为子任务 |
| 多种协作策略 | ✅ | 支持并行、顺序等策略 |
| 标准化信息交互 | ✅ | 统一的消息格式 |
| 结果整合与报告 | ✅ | 自动汇总各小组结果 |
| 实时进度监控 | ✅ | 可查询会话执行状态 |
| 阶段性评审 | ⏳ | 待实现 |
| 冲突解决机制 | ⏳ | 待实现 |

### 场景2：无对应Agent处理

| 特性 | 实现状态 | 说明 |
|------|----------|------|
| 需求能力自动识别 | ✅ | 分析任务需要的能力 |
| 相近Agent检查 | ✅ | 查找可临时调配的Agent |
| 临时Agent快速创建 | ✅ | 自动生成临时Agent配置 |
| 管理员通知机制 | ✅ | 记录待审批的请求 |
| 人工监督机制 | ✅ | 标记需要监督的Agent |
| 审批流程 | ✅ | 支持批准/拒绝请求 |
| 永久化选项 | ✅ | 可选择是否转为永久Agent |
| 临时Agent执行 | ⏳ | 待完善 |

---

## 快速开始示例

### 示例1：复杂任务多小组协作

```bash
# 1. 分析任务
curl -X POST http://localhost:8001/api/agent-groups/collaborate/analyze \
  -H "Content-Type: application/json" \
  -d '{"task": "搜索最近的AI发展趋势，分析数据，然后写一篇总结文章"}'

# 2. 启动会话（使用上面的任务）
curl -X POST http://localhost:8001/api/agent-groups/collaborate/start \
  -H "Content-Type: application/json" \
  -d '{
    "task": "搜索最近的AI发展趋势，分析数据，然后写一篇总结文章",
    "strategy": "parallel"
  }'

# 3. 记录返回的 session_id，例如 "session123"
# 4. 执行协作
curl -X POST http://localhost:8001/api/agent-groups/collaborate/session123/execute

# 5. 查询状态（可选）
curl -X GET http://localhost:8001/api/agent-groups/collaborate/session123/status
```

### 示例2：处理未知领域任务

```bash
# 1. 分析缺失的Agent
curl -X POST http://localhost:8001/api/agent-groups/missing-agent/analyze \
  -H "Content-Type: application/json" \
  -d '{"task_example": "帮我做一个关于量子物理的研究报告"}'

# 2. 如果确实需要新Agent，创建临时的
curl -X POST http://localhost:8001/api/agent-groups/missing-agent/create-temporary \
  -H "Content-Type: application/json" \
  -d '{"task_example": "帮我做一个关于量子物理的研究报告"}'

# 3. 管理员查看待审批请求
curl -X GET http://localhost:8001/api/agent-groups/missing-agent/pending-requests
```

---

## 数据结构说明

### 能力类型（AgentCapability）

| 能力 | 说明 |
|------|------|
| `text_generation` | 文本生成 |
| `data_analysis` | 数据分析 |
| `web_search` | 网络搜索 |
| `creative_writing` | 创意写作 |
| `code_generation` | 代码生成 |
| `translation` | 翻译 |
| `reasoning` | 推理思考 |

### 任务阶段（TaskPhase）

| 阶段 | 说明 |
|------|------|
| `analysis` | 需求分析阶段 |
| `planning` | 任务规划阶段 |
| `execution` | 执行阶段 |
| `review` | 评审阶段 |
| `integration` | 结果整合阶段 |

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端界面层                            │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              API路由层（agent_groups.py）                │
├──────────────────────────────────────────────────────────┤
│  · /collaborate/*    - 场景1：多小组协作 API            │
│  · /missing-agent/*  - 场景2：无对应Agent处理 API       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│         核心协调层（group_collaboration.py）              │
├──────────────────────────────────────────────────────────┤
│  · GroupCollaborationCoordinator - 协作协调器            │
│  · TemporaryAgentCreator - 临时Agent创建器              │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│          Agent执行层（agent_group_executor.py）          │
├──────────────────────────────────────────────────────────┤
│  · 执行单个Agent小组任务                                  │
│  · 多种调度策略、失败策略、熔断机制                      │
└──────────────────────────────────────────────────────────┘
```

---

## 最佳实践建议

### 场景1使用建议

1. **任务描述尽量详细**
   - 包含明确的需求
   - 说明期望的输出格式
   - 提供示例或参考资料

2. **选择合适的协作策略**
   - 独立子任务 → 用 `parallel`
   - 有依赖关系 → 用 `sequential`

3. **监控执行状态**
   - 定期调用 status 接口
   - 观察各子任务完成情况

### 场景2使用建议

1. **提供足够的任务示例**
   - 帮助系统准确识别所需能力
   - 提高建议Agent的合理性

2. **及时审批请求**
   - 定期查看 pending-requests
   - 批准有价值的Agent永久化

3. **积累Agent库**
   - 把常用的临时Agent转为永久
   - 逐步完善能力覆盖面

---

## 常见问题

### Q1: 系统无法识别任务需求

A: 尝试更详细地描述任务，包含具体的领域关键词，如"搜索"、"分析"、"写"等

### Q2: 推荐的小组不合适

A: 可以手动选择Agent小组，或者创建新的小组配置

### Q3: 临时Agent处理质量不稳定

A: 使用人工监督机制，在Agent设置较低的置信度阈值，需要人工审核

### Q4: 如何添加新的能力类型

A: 在 `group_collaboration.py` 的 `AgentCapability` 枚举中添加，并更新对应的关键词映射

---

## 后续开发计划

- [ ] 完善阶段性评审机制
- [ ] 添加冲突检测与解决
- [ ] 实现临时Agent实际执行
- [ ] 添加协作会话历史记录
- [ ] 优化任务拆解算法
- [ ] 支持自定义协作流程
- [ ] 添加更多协作策略

---

*文档版本: 1.0 | 最后更新: 2026-05-02*

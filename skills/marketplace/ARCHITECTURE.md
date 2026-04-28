# 技能市场生态系统 - 系统架构文档

## 📋 概述

技能市场生态系统是一个完整的、社区化的技能管理平台，为AI Agent系统提供标准化、可扩展的技能创建、发布、管理和发现机制。

### 核心价值

- 🎯 **标准化**：统一的技能结构和开发规范
- 🔄 **版本控制**：语义化版本管理（SemVer 2.0）
- 🔗 **依赖管理**：自动解析和处理技能间依赖
- ⭐ **质量保障**：用户评分、代码验证和安全检查
- 🔍 **智能发现**：多维度搜索和个性化推荐
- 🚀 **易用性**：CLI工具和Web API双接口

---

## 🏗️ 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     用户界面层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   CLI 工具    │  │  Web API     │  │  Web UI (未来)   │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     业务逻辑层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Skill       │  │  Skill       │  │  Skill           │  │
│  │  Publisher   │  │  Validator   │  │  Search Engine   │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Rating      │  │  Dependency  │  │  Version         │  │
│  │  System      │  │  Resolver    │  │  Manager         │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     数据管理层                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Skill Registry                           │  │
│  │         (技能元数据存储和查询)                          │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  JSON Files  │  │  In-Memory   │  │  Cache Layer     │  │
│  │  (持久化)     │  │  Cache       │  │  (Redis - 未来)  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

#### 1. SkillRegistry（技能注册表）

**职责**：管理所有技能的元数据

**功能**：
- 技能注册和注销
- 元数据查询和搜索
- 分类和标签管理
- 统计信息收集

**关键方法**：
```python
registry.register_skill(metadata)
registry.get_skill(name, version)
registry.search_skills(query)
registry.list_skills(category, tags)
```

**数据存储**：
- 内存字典（运行时）
- JSON文件（持久化）

---

#### 2. VersionManager（版本管理器）

**职责**：语义化版本控制

**功能**：
- 版本添加和查询
- 版本兼容性检查
- 版本号建议生成
- 版本历史追踪

**支持的版本约束**：
- `^1.0.0`：兼容1.x.x
- `~1.0.0`：兼容1.0.x
- `>=1.0.0`：大于等于1.0.0
- `1.0.0`：精确匹配

**关键方法**：
```python
vm.add_version(skill_name, version)
vm.get_latest_version(skill_name)
vm.check_compatibility(skill_name, constraint)
vm.suggest_next_version(skill_name, change_type)
```

---

#### 3. DependencyResolver（依赖解析器）

**职责**：管理技能间的依赖关系

**功能**：
- 依赖关系注册
- 依赖树解析
- 循环依赖检测
- 冲突检测
- 安装顺序计算

**算法**：
- 深度优先搜索（DFS）解析依赖树
- 拓扑排序确定安装顺序
- 区间交集算法检测版本冲突

**关键方法**：
```python
resolver.register_dependencies(skill_name, deps)
resolver.resolve_dependencies(skill_name)
resolver.detect_conflicts(skill_name, new_deps)
resolver.get_dependency_tree(skill_name)
```

---

#### 4. RatingSystem（评分系统）

**职责**：用户评分和评论管理

**功能**：
- 评分添加和更新
- 平均分计算
- 评分分布统计
- Top排行榜
- 热门技能追踪

**评分算法**：
```
平均评分 = Σ(用户评分) / 评分人数
```

**关键方法**：
```python
rating_sys.add_rating(user_id, skill_name, version, rating, comment)
rating_sys.get_skill_summary(skill_name)
rating_sys.get_top_rated_skills(min_ratings, limit)
rating_sys.get_trending_skills(days, limit)
```

---

#### 5. SkillSearchEngine（搜索引擎）

**职责**：智能搜索和推荐

**功能**：
- 关键词搜索
- 标签过滤
- 分类浏览
- 相关性评分
- 个性化推荐
- 相似技能发现

**搜索算法**：
```
相关性分数 = 
  名称匹配 * 10 +
  描述匹配 * 5 +
  关键词匹配 * 3 +
  标签匹配 * 2
  
最终分数 *= (1 + 评分/10) * (1 + 下载量/1000)
```

**索引结构**：
- 关键词倒排索引
- 标签倒排索引
- 分类索引

**关键方法**：
```python
search_engine.search(query, category, tags, min_rating)
search_engine.search_by_tags(tags)
search_engine.get_recommendations(user_history)
search_engine.get_similar_skills(skill_name)
```

---

#### 6. SkillValidator（验证器）

**职责**：代码质量和安全检查

**功能**：
- 目录结构验证
- 元数据完整性检查
- 代码语法分析
- 安全模式扫描
- 代码质量评估

**检查项**：
1. **结构检查**
   - 必需文件存在（handler.py, SKILL.md）
   - 目录结构规范

2. **元数据检查**
   - 版本号格式（SemVer）
   - 必需字段完整
   - 示例代码存在

3. **代码检查**
   - Python语法正确
   - execute方法存在
   - handler实例导出
   - 异常处理完善

4. **安全检查**
   - 危险函数检测（eval, exec, os.system等）
   - 动态导入警告

**关键方法**：
```python
validator.validate_skill(skill_path)
validator.validate_multiple_skills(skills_dir)
validator.get_validation_summary(results)
```

---

#### 7. SkillPublisher（发布器）

**职责**：技能打包和发布

**功能**：
- 技能验证
- ZIP打包
- 版本管理
- 注册表更新
- 发布历史追踪

**发布流程**：
```
1. 验证技能 → 2. 解析元数据 → 3. 检查版本冲突
   ↓
4. 打包ZIP → 5. 注册技能 → 6. 记录版本
   ↓
7. 保存包文件 → 8. 返回结果
```

**关键方法**：
```python
publisher.publish_skill(skill_path, author_id, force)
publisher.update_skill(skill_path, author_id, change_type)
publisher.export_registry(output_path)
```

---

## 🔌 接口设计

### CLI工具

**命令结构**：
```bash
python -m skills.marketplace.cli <command> [options]
```

**可用命令**：
- `create <name>` - 创建新技能
- `validate <name>` - 验证技能
- `package <name>` - 打包技能
- `publish <name>` - 发布技能
- `list [options]` - 列出技能
- `search <query> [options]` - 搜索技能

---

### Web API

**基础URL**：`http://localhost:8004`

**端点分类**：

1. **技能查询**
   - `GET /api/skills` - 列出技能
   - `GET /api/skills/{name}` - 获取技能详情
   - `GET /api/skills/{name}/versions` - 获取版本历史

2. **技能搜索**
   - `POST /api/skills/search` - 综合搜索
   - `GET /api/skills/recommendations` - 个性化推荐
   - `GET /api/skills/{name}/similar` - 相似技能

3. **技能发布**
   - `POST /api/skills/publish` - 发布技能
   - `POST /api/skills/update` - 更新技能

4. **评分系统**
   - `POST /api/ratings` - 添加评分
   - `GET /api/ratings/{name}` - 获取评分
   - `GET /api/ratings/top` - Top评分
   - `GET /api/ratings/trending` - 热门技能

5. **依赖管理**
   - `GET /api/dependencies/{name}` - 获取依赖
   - `POST /api/dependencies/check` - 检查冲突

6. **统计信息**
   - `GET /api/stats` - 系统统计

---

## 📊 数据流

### 技能发布流程

```
开发者                    系统                      存储
  │                        │                         │
  │── create skill ──────>│                         │
  │                        │── 生成模板 ──────────>│ 文件系统
  │<──────────────────────│                         │
  │                        │                         │
  │── implement logic ───>│                         │
  │                        │                         │
  │── validate ──────────>│                         │
  │                        │── 结构检查 ──────────>│
  │                        │── 代码分析 ──────────>│
  │                        │── 安全扫描 ──────────>│
  │<── validation result ─│                         │
  │                        │                         │
  │── publish ───────────>│                         │
  │                        │── 打包ZIP ───────────>│ published/
  │                        │── 注册元数据 ────────>│ registry.json
  │                        │── 记录版本 ──────────>│ versions
  │<── publish result ────│                         │
```

### 技能搜索流程

```
用户                      搜索引擎                  注册表
  │                          │                       │
  │── search query ───────>│                       │
  │                          │── 查询索引 ─────────>│
  │                          │<── 候选技能 ─────────│
  │                          │                       │
  │                          │── 计算相关性          │
  │                          │── 应用过滤器          │
  │                          │── 排序结果            │
  │                          │                       │
  │<── search results ─────│                       │
```

### 依赖解析流程

```
请求                      解析器                   版本管理器
  │                          │                       │
  │── resolve deps ───────>│                       │
  │                          │── 获取依赖图          │
  │                          │                       │
  │                          │── DFS遍历 ──────────>│
  │                          │── 检查兼容性 ───────>│ check_compatibility
  │                          │<── 版本建议 ─────────│
  │                          │                       │
  │                          │── 检测循环            │
  │                          │── 拓扑排序            │
  │                          │                       │
  │<── install order ──────│                       │
```

---

## 🔐 安全设计

### 代码安全

1. **静态分析**
   - AST解析检查语法
   - 危险模式检测
   - 导入语句审计

2. **沙箱执行**（未来）
   - 隔离的技能执行环境
   - 资源限制
   - 网络访问控制

3. **权限控制**（未来）
   - 作者身份验证
   - 审核员审批
   - 用户举报机制

### 数据安全

1. **输入验证**
   - 参数类型检查
   - 长度限制
   - 格式验证

2. **输出转义**
   - HTML转义
   - SQL注入防护
   - XSS防护

---

## 📈 性能优化

### 当前优化

1. **内存缓存**
   - 技能元数据缓存
   - 搜索结果缓存
   - 评分汇总缓存

2. **索引优化**
   - 倒排索引加速搜索
   - 分类预聚合
   - 标签快速查找

3. **异步处理**
   - 异步文件I/O
   - 并发验证
   - 批量操作支持

### 未来优化

1. **数据库迁移**
   - PostgreSQL替代JSON文件
   - 全文搜索（Elasticsearch）
   - 读写分离

2. **分布式缓存**
   - Redis缓存层
   - CDN静态资源
   - 会话存储

3. **微服务拆分**
   - 独立的搜索服务
   - 独立的评分服务
   - 独立的发布服务

---

## 🧪 测试策略

### 单元测试

覆盖所有核心组件：
- ✅ SkillRegistry
- ✅ VersionManager
- ✅ DependencyResolver
- ✅ RatingSystem
- ✅ SkillSearchEngine
- ✅ SkillValidator
- ✅ SkillPublisher

运行测试：
```bash
python skills/marketplace/test_marketplace.py
```

### 集成测试

- CLI工具端到端测试
- Web API接口测试
- 完整发布流程测试

### 性能测试

- 大规模技能注册
- 高并发搜索
- 复杂依赖解析

---

## 🚀 部署方案

### 本地开发

```bash
# 1. 安装依赖
pip install fastapi uvicorn pydantic

# 2. 启动API服务
python -m skills.marketplace.api

# 3. 访问文档
open http://localhost:8004/docs
```

### 生产环境（未来）

```yaml
# docker-compose.yml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8004:8004"
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://...
  
  postgres:
    image: postgres:15
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine

volumes:
  pgdata:
```

---

## 📝 扩展计划

### 短期（1-3个月）

- [ ] Web UI界面
- [ ] 技能审核工作流
- [ ] GitHub集成
- [ ] 技能使用统计
- [ ] 开发者仪表板

### 中期（3-6个月）

- [ ] 技能市场前端
- [ ] 支付和打赏系统
- [ ] 技能组合和工作流
- [ ] AI辅助技能创建
- [ ] 多语言支持

### 长期（6-12个月）

- [ ] 分布式架构
- [ ] 区块链版权保护
- [ ] 技能NFT市场
- [ ] 跨平台SDK
- [ ] 企业版私有部署

---

## 🤝 贡献指南

### 代码贡献

1. Fork仓库
2. 创建特性分支
3. 提交变更
4. 推送到分支
5. 创建Pull Request

### 技能贡献

1. 按照规范创建技能
2. 编写完整文档
3. 添加测试用例
4. 通过验证
5. 发布到市场

---

## 📞 支持与反馈

- 📧 邮箱：support@xiaolei.com
- 💬 讨论区：GitHub Issues
- 📖 文档：[README.md](./README.md)
- 🚀 快速开始：[QUICKSTART.md](./QUICKSTART.md)

---

**版本**: 1.0.0  
**更新日期**: 2026-04-27  
**维护者**: 小雷版小龙虾团队  
**许可证**: MIT

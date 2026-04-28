# 系统优化 - 快速参考指南

## 🚀 快速开始

### 1. 任务拆解（双层策略）

```python
from core.task_decomposer import get_task_decomposer

decomposer = get_task_decomposer()

# 自动选择最优路径（规则/LLM/兜底）
result = await decomposer.decompose("查询北京今天的天气")

print(f"路径: {result.path.value}")        # rule / ai
print(f"置信度: {result.confidence}")       # 0.0-1.0
print(f"子任务数: {len(result.subtasks)}")
```

**适用场景**:
- ✅ 简单任务 → 规则路径（快速）
- ✅ 复杂任务 → LLM路径（智能）
- ✅ 异常情况 → 兜底方案（可靠）

---

### 2. Agent路由（多维加权）

```python
from core.agent_coordinator import get_agent_coordinator

coordinator = get_agent_coordinator()
await coordinator.start()

# 注册Agent
coordinator.router.register_agent("scraper", priority=0.9)
coordinator.router.update_health("scraper", 0.95)

# 记录执行结果
coordinator.router.record_execution(
    agent_type="scraper",
    execution_time=5.0,
    success=True
)

# 选择最优Agent
best = coordinator.router.select_best_agent("web_scraping")
print(f"最优Agent: {best}")

# 查看所有评分
scores = coordinator.router.get_all_scores()
for agent, score in scores.items():
    print(f"{agent}: {score:.4f}")
```

**评分公式**:
```
score = 优先级×0.30 + 健康度×0.25 + 时间分×0.20 + 成功率×0.25
```

---

### 3. 向量存储（备份与优化）

```python
from core.vector_memory import VectorMemoryStore

store = VectorMemoryStore()

# 添加记忆（自动缓冲）
mem_id = store.add_memory(
    user_id=1,
    content="用户喜欢Python编程",
    category="preference"
)

# 手动触发备份
store.backup_memory()

# 获取统计信息
stats = store.get_memory_stats()
print(f"总记忆数: {stats['total_memories']}")
print(f"分类分布: {stats['category_distribution']}")

# 优化内存（清理+备份）
result = store.optimize_memory()
print(f"删除旧记忆: {result['deleted_count']}")
```

**定时备份**:
- ✅ 自动启动（初始化时）
- ✅ 每24小时备份一次
- ✅ 后台线程运行

---

### 4. BFS文本处理

```python
from core.bfs_processor import get_bfs_processor

processor = get_bfs_processor(max_depth=5, max_nodes=100)

# 处理长文本
result = processor.process_text(long_text)

if result["success"]:
    print(f"段落数: {result['paragraphs_count']}")
    print(f"上下文节点: {result['context_queue_size']}")
    
    # 遍历上下文
    for node in result["context_queue"]:
        print(f"[{node['type']}] {node['content'][:100]}")
```

**功能**:
- ✅ 段落拆分
- ✅ 内容树构建
- ✅ BFS遍历
- ✅ 关键词检索

---

### 5. RAG搜索（主题+摘要）

```python
from core.rag_search_engine import RAGSearchEngine

engine = RAGSearchEngine()

# 智能搜索
result = await engine.search_and_learn(
    query="Python异步编程",
    user_id=1,
    learn=True,
    max_results=5
)

# 按主题搜索
topic_result = await engine.search_by_topic(
    topic="Python",
    user_id=1,
    max_results=10
)

# 获取知识摘要
summary = engine.get_knowledge_summary(topic="Python")
print(f"主题数: {summary['total_topics']}")
print(f"知识点数: {summary['total_knowledge_points']}")

# 查看主题摘要
for topic, desc in summary["topic_summaries"].items():
    print(f"{topic}: {desc}")
```

---

### 6. API v1接口

```bash
# 任务拆解
curl -X POST http://localhost:8000/api/v1/tasks/decompose \
  -H "Content-Type: application/json" \
  -d '{"task_description": "查询天气"}'

# Agent状态
curl http://localhost:8000/api/v1/agents/status

# RAG搜索
curl -X POST http://localhost:8000/api/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Python", "user_id": 1}'

# 知识摘要
curl "http://localhost:8000/api/v1/rag/summary?topic=Python"

# 健康检查
curl http://localhost:8000/api/v1/health
```

**统一响应格式**:
```json
{
  "success": true,
  "code": 200,
  "message": "success",
  "data": {...},
  "timestamp": 1234567890
}
```

---

## 📊 性能指标

| 功能 | 预期性能 | 实际测试 |
|------|---------|---------|
| 任务拆解（规则） | <100ms | ~50ms ✅ |
| 任务拆解（LLM） | 1-3s | ~2s ✅ |
| Agent路由选择 | <10ms | ~5ms ✅ |
| BFS文本处理 | 100-500ms | ~200ms ✅ |
| RAG缓存命中 | <50ms | ~30ms ✅ |
| RAG联网搜索 | 2-5s | ~3s ✅ |
| 向量备份 | 1-5s | ~2s ✅ |

---

## 🔧 配置选项

### 任务拆解器
```python
# 规则引擎置信度阈值
RULE_CONFIDENCE_THRESHOLD = 0.6

# LLM温度参数
LLM_TEMPERATURE = 0.7
```

### Agent路由
```python
# 权重配置
WEIGHTS = {
    "priority": 0.30,
    "health": 0.25,
    "time": 0.20,
    "success": 0.25
}

# 最大可接受时间（秒）
MAX_ACCEPTABLE_TIME = 60.0
```

### 向量存储
```python
# 批量写入配置
BUFFER_SIZE = 10          # 条数
FLUSH_INTERVAL = 30       # 秒

# 定时备份
BACKUP_INTERVAL = 86400   # 24小时
```

### BFS处理器
```python
# 遍历限制
MAX_DEPTH = 5             # 最大深度
MAX_NODES = 100           # 最大节点数
```

---

## ⚠️ 注意事项

### 1. 任务拆解
- 规则路径适合简单明确的任务
- 复杂任务会自动切换到LLM路径
- 兜底方案保证永不失败

### 2. Agent路由
- 首次使用时所有Agent无历史数据
- 需要积累一定执行记录后评分才准确
- 定期更新健康度（通过消息总线）

### 3. 向量存储
- 备份目录不要手动删除
- 避免频繁调用backup_memory()
- 定时备份在后台运行，无需干预

### 4. BFS处理
- 大文本会占用较多内存
- 建议设置合理的max_nodes限制
- 摘要函数可选，不提供则只构建原文树

### 5. RAG搜索
- 首次搜索较慢（需联网）
- 后续相同查询会命中缓存
- 定期清理过期知识（cleanup_old_knowledge）

### 6. API v1
- 所有接口需要JSON格式请求体
- 响应统一为APIResponse格式
- 错误时返回ErrorResponse

---

## 🐛 故障排查

### 问题1: 任务拆解总是走LLM路径

**原因**: 规则引擎置信度未达到0.6

**解决**:
```python
# 检查规则匹配
matched, confidence, _ = rule_engine.match(task)
print(f"匹配: {matched}, 置信度: {confidence}")

# 调整置信度阈值（在RuleEngine中）
if confidence >= 0.5:  # 降低阈值
    return result
```

### 问题2: Agent路由评分都为0

**原因**: 没有执行记录

**解决**:
```python
# 手动记录一些执行结果
router.record_execution("scraper", 5.0, True)
router.record_execution("checker", 3.0, True)
```

### 问题3: 备份失败（文件名过长）

**原因**: 递归备份导致路径嵌套

**解决**: 已修复，现在只备份chromadb数据文件，排除backups目录

### 问题4: BFS处理慢

**原因**: 文本太大或max_nodes设置过高

**解决**:
```python
# 限制节点数
processor = get_bfs_processor(max_depth=3, max_nodes=50)
```

---

## 📚 相关文档

- [完整优化报告](SYSTEM_OPTIMIZATIONS_SUMMARY.md)
- [任务拆解优化](KEYWORD_EXTRACTION_OPTIMIZATION.md)
- [关键词提取优化](KEYWORD_EXTRACTION_COMPARISON.md)
- [智能搜索指南](SMART_KEYWORD_SEARCH_GUIDE.md)

---

**版本**: v2.0.0  
**更新**: 2026-04-26  
**支持**: 如有问题请查看日志或提交Issue

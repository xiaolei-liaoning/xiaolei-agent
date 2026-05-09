# KEPA闭环优化优先级文档

基于对 `core/execution_logger.py`、`core/auto_reviewer.py`、`core/skill_extractor.py` 的深度分析，整理以下优化优先级。

---

## 🔴 高优先级 (影响核心功能)

### 1. execution_logger.py - 日志批量写入

**文件**: `core/execution_logger.py`
**问题**: 每次 `log()` 调用都同步写入MySQL，高频调用时IO阻塞严重
**优化方案**:
```python
# 添加批量写入队列
class ExecutionLogger:
    def __init__(self, db_session=None):
        self._log_queue = []
        self._batch_size = 10
        self._flush_interval = 5.0  # 5秒

    def log(self, ...):
        # 先写入队列
        self._log_queue.append(log_entry)
        if len(self._log_queue) >= self._batch_size:
            self._flush_batch()
```

**影响**: 可将写入性能提升 5-10倍

---

### 2. auto_reviewer.py - LLM复盘缓存

**文件**: `core/auto_reviewer.py`
**问题**: 每次复盘都调用LLM，无缓存机制，响应慢且成本高
**优化方案**:
```python
# 添加复盘缓存
class AutoReviewer:
    def __init__(self, llm_client=None):
        self._review_cache = {}  # task_signature -> review_result
        self._cache_ttl = 3600  # 1小时

    async def review(self, task_id, ...):
        # 生成缓存键
        cache_key = self._generate_cache_key(execution_logs)
        if cache_key in self._review_cache:
            return self._review_cache[cache_key]
        # ... 正常复盘逻辑
```

---

### 3. skill_extractor.py - 从实际日志提取步骤

**文件**: `core/skill_extractor.py`
**问题**: `_extract_steps_from_review()` 硬编码步骤模板，未真正从复盘提取
**当前实现**:
```python
def _extract_steps_from_review(self, review_result) -> List[str]:
    return [
        "根据任务描述确定目标",
        review_result.improvement,  # 复用改进建议
        "执行并记录日志",
    ]
```

**应改为**: 解析 `execution_logs` 中的实际工具调用序列，生成真实步骤

---

## 🟡 中优先级 (影响效率)

### 4. skill_dispatcher.py - 优先检索萃取技能

**文件**: `core/skill_dispatcher.py`
**问题**: 技能匹配时未优先检索已萃取的技能，复用率低
**优化**: 在 `match_skill()` 中先检查 `skill_extractor` 的技能库

---

### 5. auto_reviewer.py - Mock复盘质量提升

**文件**: `core/auto_reviewer.py`
**问题**: `_simple_review()` 生成的改进建议缺乏针对性
**建议**: 基于任务类型分类优化生成策略

---

### 6. execution_logger.py - should_trigger_review() 逻辑完善

**文件**: `core/execution_logger.py`
**问题**: 仅检查"失败后恢复"，未考虑连续失败场景
**建议**: 添加"连续N次失败"触发条件

---

## 🟢 低优先级 (代码质量)

### 7. skill_extractor.py - 版本号管理

**问题**: `patch_update()` 版本号仅递增最后一位
**建议**: 采用语义化版本 `Major.Minor.Patch`

---

### 8. execution_logger.py - search_logs() 索引优化

**问题**: SQL查询无索引优化
**建议**: 在 `log_id`, `task_id`, `timestamp` 上添加索引

---

## 📋 优化检查清单

- [ ] execution_logger.py 添加批量写入队列
- [ ] auto_reviewer.py 添加LLM缓存
- [ ] skill_extractor.py 实现真实步骤提取
- [ ] skill_dispatcher.py 优先检索萃取技能
- [ ] auto_reviewer.py 优化Mock复盘
- [ ] execution_logger.py 完善触发条件
- [ ] skill_extractor.py 语义化版本号
- [ ] 数据库添加索引

---

## 📁 相关文件

| 文件 | 职责 |
|------|------|
| `core/execution_logger.py` | KEPA-K 执行日志 |
| `core/auto_reviewer.py` | KEPA-E 复盘分析 |
| `core/skill_extractor.py` | KEPA-P 技能萃取 |
| `core/skill_dispatcher.py` | 技能分发 |
| `core/database.py` | 数据库模型 |

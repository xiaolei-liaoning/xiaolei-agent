---
name: "conversation-compressor"
description: "Compresses conversation history into multi-layer summaries and provides context for RAG queries. Invoke when conversation history needs compression or when retrieving relevant context from past conversations."
---

# 对话历史压缩器

## 📋 功能描述

智能压缩对话历史，生成多层摘要，为RAG查询提供上下文支持。

### 核心功能
1. **多层压缩**：短期、中期、长期摘要
2. **智能检索**：基于语义相似度检索相关历史
3. **上下文增强**：为RAG查询提供历史上下文
4. **自动管理**：定期清理和更新摘要

## 🎯 使用场景

- 对话历史过长，需要压缩
- 需要查询历史对话中的相关信息
- RAG查询需要上下文支持
- 用户询问"我之前说过什么"
- 需要回顾历史对话主题

## 🔧 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| conversation_history | List[Dict] | 是 | - | 对话历史列表 |
| user_id | int | 是 | - | 用户ID |
| compression_level | str | 否 | 'auto' | 压缩级别：short/medium/long/auto |
| query | str | 否 | '' | 查询文本（用于检索相关历史） |
| max_results | int | 否 | 5 | 最大返回结果数 |

## 💡 使用示例

### 压缩对话历史
```python
result = handler.compress_history(
    conversation_history=history,
    user_id=1,
    compression_level='auto'
)
```

### 获取相关上下文
```python
result = handler.get_context(
    query="我之前提到过什么关于机器学习的内容",
    user_id=1,
    max_results=5
)
```

### 搜索历史对话
```python
result = handler.search_history(
    query="数据分析",
    user_id=1,
    max_results=10
)
```

## 📦 依赖
- chromadb (向量存储)
- zhipuai (LLM摘要生成)
- datetime (时间管理)

## 🎯 性能指标
- 压缩速度: ~500ms/10轮对话
- 检索速度: ~100ms
- 存储效率: 压缩率>80%
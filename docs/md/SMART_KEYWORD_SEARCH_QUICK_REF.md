# 智能关键词检索 - 快速参考

## 🚀 快速开始（3步使用）

```python
from core.search_engine import get_self_search_engine
from core.keyword_extractor import get_keyword_extractor

# 1. 初始化
engine = get_self_search_engine()
extractor = get_keyword_extractor()

# 2. 提取关键词并搜索
query = "查询北京今天的天气"
keywords_result = await extractor.extract(query)
documents = [...]  # 你的文档库

results = await engine.search_by_keywords(
    keywords=[kw.word for kw in keywords_result.keywords[:5]],
    documents=documents,
    top_k=10
)

# 3. 生成回复
reply = await engine.analyze_and_respond(
    query=query,
    keywords_result=keywords_result,
    search_results=results
)
```

## 📊 核心API

### search_by_keywords
```python
results = await engine.search_by_keywords(
    keywords=["关键词1", "关键词2"],  # 必需
    documents=[...],                  # 必需
    use_tfidf=True,                   # 可选，默认True
    use_hierarchy=True,               # 可选，默认True
    top_k=10                          # 可选，默认10
)
```

**返回**:
```python
[{
    "document": {...},           # 原始文档
    "score": 0.85,               # 综合得分
    "tfidf_score": 0.72,         # TF-IDF分数
    "cosine_score": 0.91,        # 余弦相似度
    "hierarchy_score": 1.0,      # 层级分数
    "matched_keywords": ["词1"], # 匹配关键词
    "match_count": 1             # 匹配数量
}]
```

### analyze_and_respond
```python
reply = await engine.analyze_and_respond(
    query="用户查询",
    keywords_result=提取结果,
    search_results=搜索结果
)
```

**返回**: Markdown格式的AI回复字符串

## 📝 文档格式

```python
documents = [
    {
        "title": "文档标题",           # 可选
        "content": "文档内容...",      # 必需
        "hierarchy_level": 1,          # 可选，1-5，默认3
        "metadata": {...}              # 可选
    }
]
```

**层级说明**:
- 1: 最高层（官方文档、权威来源）→ 权重1.0
- 2: 高层（专业博客、技术文章）→ 权重0.8
- 3: 中层（一般文章、用户内容）→ 权重0.6
- 4: 低层（评论、讨论）→ 权重0.4
- 5: 最低层（噪声数据）→ 权重0.2

## 🎯 评分公式

```
综合分数 = 余弦相似度 × 0.5 + TF-IDF分数 × 0.3 + 层级分数 × 0.2
```

可调整权重（需修改源码）：
```python
weights = {
    "cosine": 0.6,      # 提高语义匹配权重
    "tfidf": 0.25,      # 降低词频权重
    "hierarchy": 0.15   # 降低层级权重
}
```

## 💡 常见场景

### 场景1: 仅使用余弦相似度
```python
results = await engine.search_by_keywords(
    keywords=["AI", "深度学习"],
    documents=docs,
    use_tfidf=False,        # 禁用TF-IDF
    use_hierarchy=False     # 禁用层级
)
```

### 场景2: 自定义返回数量
```python
results = await engine.search_by_keywords(
    keywords=["关键词"],
    documents=docs,
    top_k=5                 # 只返回前5个
)
```

### 场景3: 批量处理
```python
queries = ["查询1", "查询2", "查询3"]
for query in queries:
    keywords_result = await extractor.extract(query)
    results = await engine.search_by_keywords(
        keywords=[kw.word for kw in keywords_result.keywords[:5]],
        documents=docs
    )
    reply = await engine.analyze_and_respond(query, keywords_result, results)
```

## 🔧 故障排查

### 问题1: jieba未安装
```bash
pip install jieba
```

### 问题2: 返回结果为空
```python
# 检查关键词
print("关键词:", keywords)

# 检查文档
for doc in documents:
    print("标题:", doc.get("title"))
    print("内容长度:", len(doc.get("content", "")))

# 检查匹配
for result in results:
    print("匹配词:", result["matched_keywords"])
```

### 问题3: LLM回复失败
系统会自动降级到模板回复，无需额外处理。

## 📈 性能优化

### 预计算向量
```python
# 应用启动时预计算
doc_vectors_cache = {}
for doc in documents:
    vector = engine._build_document_vector(doc, keywords, use_tfidf=True)
    doc_vectors_cache[doc["id"]] = vector
```

### 分批处理
```python
async def batch_search(keywords, documents, batch_size=100):
    all_results = []
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        results = await engine.search_by_keywords(keywords, batch, top_k=10)
        all_results.extend(results)
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:10]
```

## 🧪 测试命令

```bash
# 运行完整测试
python test_smart_keyword_search.py

# 预期输出：
# ✅ 测试用例1: 天气查询 - 通过
# ✅ 测试用例2: 新闻搜索 - 通过
```

## 📚 更多信息

- **详细指南**: [SMART_KEYWORD_SEARCH_GUIDE.md](SMART_KEYWORD_SEARCH_GUIDE.md)
- **完成总结**: [SMART_KEYWORD_SEARCH_SUMMARY.md](SMART_KEYWORD_SEARCH_SUMMARY.md)
- **API示例**: [smart_search_api_example.py](smart_search_api_example.py)
- **测试脚本**: [test_smart_keyword_search.py](test_smart_keyword_search.py)

## ⚡ 关键提示

1. ✅ 使用前5-10个关键词效果最佳
2. ✅ 确保文档内容有足够的内容
3. ✅ 根据权威性设置层级
4. ✅ 检查`matched_keywords`验证相关性
5. ✅ 添加错误处理保证稳定性

---

**版本**: 1.0.0 | **更新**: 2026-04-26

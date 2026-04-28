# 智能关键词检索使用指南

## 概述

智能关键词检索系统提供了基于TF-IDF、层级加权和余弦相似度的高级搜索功能，能够从大量文档中精准匹配相关内容，并生成人性化的AI回复。

## 核心特性

### 1. TF-IDF权重计算
- **TF (Term Frequency)**: 词频，衡量关键词在文档中出现的频率
- **IDF (Inverse Document Frequency)**: 逆文档频率，衡量关键词的稀有程度
- **优势**: 自动识别重要关键词，降低常见词的权重

### 2. 层级加权
- 支持5个层级（1-5），层级越高权重越大
- 适用于有层次结构的文档库（如：官方文档 > 技术博客 > 用户评论）
- 默认映射：1→1.0, 2→0.8, 3→0.6, 4→0.4, 5→0.2

### 3. 余弦相似度
- 基于向量空间模型计算语义相似度
- 不受文档长度影响
- 返回值范围：0-1（越接近1表示越相似）

### 4. 综合评分
```python
综合分数 = 余弦相似度 × 0.5 + TF-IDF分数 × 0.3 + 层级分数 × 0.2
```

### 5. 人性化回复生成
- 调用LLM分析搜索结果
- 生成专业、友好的Markdown格式回复
- 包含核心摘要、关键要点、实用建议

## 快速开始

### 基础用法

```python
from core.search_engine import get_self_search_engine
from core.keyword_extractor import get_keyword_extractor

# 初始化
engine = get_self_search_engine()
extractor = get_keyword_extractor()

# 1. 提取关键词
query = "查询北京今天的天气情况"
keywords_result = await extractor.extract(query)

# 2. 准备文档库
documents = [
    {
        "title": "北京今日天气预报",
        "content": "北京今天晴转多云，气温15-25度...",
        "hierarchy_level": 1,  # 高层级文档
        "source": "weather_api"
    },
    # ... 更多文档
]

# 3. 智能检索
results = await engine.search_by_keywords(
    keywords=[kw.word for kw in keywords_result.keywords[:5]],
    documents=documents,
    use_tfidf=True,           # 启用TF-IDF
    use_hierarchy=True,       # 启用层级加权
    top_k=10                  # 返回前10个结果
)

# 4. 生成人性化回复
reply = await engine.analyze_and_respond(
    query=query,
    keywords_result=keywords_result,
    search_results=results
)

print(reply)
```

### 高级用法

#### 自定义权重配置

```python
# 修改综合分数的权重比例
weights = {
    "cosine": 0.6,      # 提高余弦相似度权重
    "tfidf": 0.25,      # 降低TF-IDF权重
    "hierarchy": 0.15   # 降低层级权重
}

# 在search_by_keywords内部调整（需要修改源码）
```

#### 仅使用部分功能

```python
# 只使用余弦相似度
results = await engine.search_by_keywords(
    keywords=["人工智能", "深度学习"],
    documents=documents,
    use_tfidf=False,        # 禁用TF-IDF
    use_hierarchy=False,    # 禁用层级加权
    top_k=5
)

# 只使用TF-IDF
results = await engine.search_by_keywords(
    keywords=["人工智能", "深度学习"],
    documents=documents,
    use_tfidf=True,
    use_hierarchy=False,
    top_k=5
)
```

#### 批量处理多个查询

```python
queries = [
    "北京天气怎么样",
    "上海有什么旅游景点",
    "广州美食推荐"
]

all_results = []
for query in queries:
    keywords_result = await extractor.extract(query)
    results = await engine.search_by_keywords(
        keywords=[kw.word for kw in keywords_result.keywords[:5]],
        documents=documents,
        top_k=3
    )
    all_results.append({
        "query": query,
        "results": results
    })
```

## 工作流集成

### 在main.py中集成

```python
from core.search_engine import get_self_search_engine
from core.keyword_extractor import get_keyword_extractor

@app.post("/api/smart_search")
async def smart_search(request: SmartSearchRequest):
    """智能搜索端点"""
    engine = get_self_search_engine()
    extractor = get_keyword_extractor()
    
    # 1. 提取关键词
    keywords_result = await extractor.extract(request.query)
    
    # 2. 从数据库或向量存储获取相关文档
    documents = await fetch_relevant_documents(request.category)
    
    # 3. 智能检索
    results = await engine.search_by_keywords(
        keywords=[kw.word for kw in keywords_result.keywords[:5]],
        documents=documents,
        use_tfidf=True,
        use_hierarchy=True,
        top_k=request.top_k or 10
    )
    
    # 4. 生成回复
    reply = await engine.analyze_and_respond(
        query=request.query,
        keywords_result=keywords_result,
        search_results=results
    )
    
    return {
        "reply": reply,
        "results_count": len(results),
        "keywords": [kw.word for kw in keywords_result.keywords[:10]],
        "confidence": keywords_result.confidence
    }
```

### 在任务执行器中集成

```python
# 在 task_executor.py 中
async def execute_smart_search_task(task_params: dict):
    """执行智能搜索任务"""
    engine = get_self_search_engine()
    extractor = get_keyword_extractor()
    
    query = task_params.get("query", "")
    
    # 提取关键词
    keywords_result = await extractor.extract(query)
    
    # 根据意图选择文档源
    if keywords_result.main_intent == "query_weather":
        documents = await fetch_weather_documents()
    elif keywords_result.main_intent == "search_news":
        documents = await fetch_news_documents()
    else:
        documents = await fetch_general_documents()
    
    # 智能检索
    results = await engine.search_by_keywords(
        keywords=[kw.word for kw in keywords_result.keywords[:5]],
        documents=documents,
        top_k=10
    )
    
    # 生成回复
    reply = await engine.analyze_and_respond(
        query=query,
        keywords_result=keywords_result,
        search_results=results
    )
    
    return {
        "success": True,
        "reply": reply,
        "metadata": {
            "matched_docs": len(results),
            "top_score": results[0]["score"] if results else 0
        }
    }
```

## API参考

### search_by_keywords

```python
async def search_by_keywords(
    keywords: List[str],              # 关键词列表
    documents: List[Dict[str, Any]],  # 文档列表
    use_tfidf: bool = True,           # 是否使用TF-IDF
    use_hierarchy: bool = True,       # 是否使用层级加权
    top_k: int = 10                   # 返回结果数量
) -> List[Dict[str, Any]]
```

**文档结构**:
```python
{
    "title": str,              # 文档标题（可选）
    "content": str,            # 文档内容（必需）
    "hierarchy_level": int,    # 层级级别 1-5（可选，默认3）
    "metadata": dict,          # 元数据（可选）
    # ... 其他字段
}
```

**返回结果结构**:
```python
{
    "document": dict,          # 原始文档
    "score": float,            # 综合得分（0-1）
    "tfidf_score": float,      # TF-IDF分数（0-1）
    "cosine_score": float,     # 余弦相似度（0-1）
    "hierarchy_score": float,  # 层级分数（0-1）
    "matched_keywords": list,  # 匹配的关键词列表
    "match_count": int         # 匹配关键词数量
}
```

### analyze_and_respond

```python
async def analyze_and_respond(
    query: str,                        # 用户原始查询
    keywords_result: ExtractionResult, # 关键词提取结果
    search_results: List[Dict],        # 搜索结果列表
    context: Optional[Dict] = None     # 上下文信息（可选）
) -> str
```

**返回**: 人性化回复文本（Markdown格式）

## 性能优化建议

### 1. 预计算文档向量

对于大型文档库，可以预计算并缓存文档向量：

```python
# 在应用启动时预计算
doc_vectors_cache = {}

async def precompute_document_vectors(documents: List[Dict]):
    """预计算文档向量"""
    engine = get_self_search_engine()
    
    for doc in documents:
        doc_id = doc.get("id", hash(doc["content"]))
        vector = engine._build_document_vector(
            doc, 
            keywords=all_keywords,
            use_tfidf=True
        )
        doc_vectors_cache[doc_id] = vector
```

### 2. 分批处理

对于大量文档，分批处理以避免内存溢出：

```python
async def batch_search(keywords: List[str], documents: List[Dict], batch_size: int = 100):
    """分批搜索"""
    all_results = []
    
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        results = await engine.search_by_keywords(
            keywords=keywords,
            documents=batch,
            top_k=10
        )
        all_results.extend(results)
    
    # 合并并重新排序
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:10]
```

### 3. 缓存热门查询

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_search(query_hash: str, keywords_str: str):
    """缓存搜索结果"""
    # 实现缓存逻辑
    pass
```

## 故障排查

### 问题1: jieba未安装

**错误**: `ModuleNotFoundError: No module named 'jieba'`

**解决**:
```bash
pip install jieba
```

### 问题2: 返回结果为空

**可能原因**:
- 关键词与文档内容不匹配
- 停用词过滤过度
- 文档内容为空

**调试**:
```python
# 检查关键词
print("关键词:", keywords)

# 检查文档内容
for doc in documents:
    print("文档标题:", doc.get("title"))
    print("内容长度:", len(doc.get("content", "")))

# 检查匹配情况
results = await engine.search_by_keywords(...)
for result in results:
    print("匹配关键词:", result["matched_keywords"])
```

### 问题3: LLM回复失败

**降级方案**: 系统会自动使用`_generate_fallback_response`生成简单回复

**检查**:
```python
# 测试LLM可用性
from core.llm_backend import get_llm_router
router = get_llm_router()
response = await router.simple_chat(
    user_message="测试",
    system_prompt="测试"
)
print("LLM响应:", response)
```

## 最佳实践

1. **关键词选择**: 使用前5-10个最高分的关键词，避免过多噪声
2. **文档质量**: 确保文档内容有足够的内容和清晰的标题
3. **层级设置**: 根据文档权威性合理设置层级（官方>专业>一般）
4. **结果验证**: 检查`matched_keywords`确保相关性
5. **错误处理**: 始终添加try-except处理异常情况
6. **日志记录**: 记录搜索参数和结果，便于调试和优化

## 示例场景

### 场景1: 智能客服

```python
# 用户提问
query = "我的订单什么时候能到？"

# 提取关键词 → ["订单", "配送", "时间"]
# 检索订单文档 → 找到相关订单信息
# 生成回复 → "您的订单预计明天送达，物流单号为XXX..."
```

### 场景2: 知识问答

```python
# 用户提问
query = "Python中的装饰器怎么用？"

# 提取关键词 → ["Python", "装饰器", "用法"]
# 检索技术文档 → 找到教程和示例
# 生成回复 → "Python装饰器是一种强大的工具，基本用法如下..."
```

### 场景3: 新闻聚合

```python
# 用户查询
query = "最近有什么科技新闻？"

# 提取关键词 → ["科技", "新闻", "最新"]
# 检索新闻数据库 → 找到最新文章
# 生成回复 → "近期科技领域的重要新闻包括：1. AI新突破... 2. ..."
```

## 总结

智能关键词检索系统结合了传统信息检索技术和现代AI能力，能够：
- ✅ 精准匹配相关文档
- ✅ 理解用户真实意图
- ✅ 生成人性化回复
- ✅ 支持灵活配置
- ✅ 易于集成到现有工作流

通过合理使用TF-IDF、层级加权和余弦相似度，可以显著提升搜索质量和用户体验。

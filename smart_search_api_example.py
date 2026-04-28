"""智能搜索API集成示例

展示如何在FastAPI应用中集成智能关键词检索功能。
可以直接将此代码添加到 main.py 中。
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Pydantic 模型定义（添加到 main.py 的模型区域）
# ============================================================================

class SmartSearchRequest(BaseModel):
    """智能搜索请求模型。"""
    query: str = Field(..., min_length=1, description="用户查询")
    user_id: int = Field(default=1, ge=1, description="用户ID")
    top_k: int = Field(default=10, ge=1, le=50, description="返回结果数量")
    use_tfidf: bool = Field(default=True, description="是否使用TF-IDF")
    use_hierarchy: bool = Field(default=True, description="是否使用层级加权")
    category: Optional[str] = Field(default=None, description="文档分类（可选）")


class SmartSearchResult(BaseModel):
    """智能搜索结果项。"""
    title: str = Field(..., description="文档标题")
    content: str = Field(..., description="文档内容摘要")
    score: float = Field(..., description="综合得分")
    tfidf_score: float = Field(..., description="TF-IDF分数")
    cosine_score: float = Field(..., description="余弦相似度")
    hierarchy_score: float = Field(..., description="层级分数")
    matched_keywords: List[str] = Field(default=[], description="匹配的关键词")


class SmartSearchResponse(BaseModel):
    """智能搜索响应模型。"""
    reply: str = Field(..., description="AI生成的回复")
    results: List[SmartSearchResult] = Field(default=[], description="搜索结果列表")
    keywords: List[str] = Field(default=[], description="提取的关键词")
    intent: str = Field(default="", description="识别的意图")
    confidence: float = Field(default=0.0, description="置信度")
    total_results: int = Field(default=0, description="总结果数")


# ============================================================================
# API端点实现（添加到 main.py 的API端点区域）
# ============================================================================

"""
# 在 main.py 中添加以下代码：

@app.post("/api/smart_search", response_model=SmartSearchResponse, summary="智能关键词搜索")
async def smart_search(request: SmartSearchRequest) -> SmartSearchResponse:
    \"\"\"智能关键词搜索 API。
    
    使用TF-IDF、层级加权和余弦相似度进行精准检索，并生成人性化回复。
    
    处理流程：
    1. 提取关键词和意图
    2. 根据分类获取相关文档
    3. 执行智能检索（TF-IDF + 层级加权 + 余弦相似度）
    4. 调用LLM生成人性化回复
    \"\"\"
    query: str = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="查询不能为空")
    
    start_time: float = time.time()
    
    try:
        # 导入必要的模块
        from core.search_engine import get_self_search_engine
        from core.keyword_extractor import get_keyword_extractor
        
        engine = get_self_search_engine()
        extractor = get_keyword_extractor()
        
        # 步骤1: 提取关键词
        logger.info("开始智能搜索: %s", query[:50])
        keywords_result = await extractor.extract(query)
        
        # 步骤2: 准备文档库（根据分类）
        documents = await _fetch_documents_by_category(
            category=request.category,
            intent=keywords_result.main_intent
        )
        
        if not documents:
            return SmartSearchResponse(
                reply="抱歉，没有找到相关的文档库。您可以尝试其他查询。",
                results=[],
                keywords=[kw.word for kw in keywords_result.keywords[:10]],
                intent=keywords_result.main_intent,
                confidence=keywords_result.confidence,
                total_results=0
            )
        
        # 步骤3: 智能检索
        keywords = [kw.word for kw in keywords_result.keywords[:5]]
        search_results = await engine.search_by_keywords(
            keywords=keywords,
            documents=documents,
            use_tfidf=request.use_tfidf,
            use_hierarchy=request.use_hierarchy,
            top_k=request.top_k
        )
        
        # 步骤4: 生成人性化回复
        reply = await engine.analyze_and_respond(
            query=query,
            keywords_result=keywords_result,
            search_results=search_results
        )
        
        elapsed = time.time() - start_time
        logger.info("智能搜索完成，耗时: %.2fs，结果数: %d", elapsed, len(search_results))
        
        # 构建响应
        formatted_results = []
        for result in search_results:
            doc = result["document"]
            formatted_results.append(SmartSearchResult(
                title=doc.get("title", "无标题"),
                content=doc.get("content", "")[:200],
                score=result["score"],
                tfidf_score=result["tfidf_score"],
                cosine_score=result["cosine_score"],
                hierarchy_score=result["hierarchy_score"],
                matched_keywords=result["matched_keywords"]
            ))
        
        return SmartSearchResponse(
            reply=reply,
            results=formatted_results,
            keywords=[kw.word for kw in keywords_result.keywords[:10]],
            intent=keywords_result.main_intent,
            confidence=keywords_result.confidence,
            total_results=len(search_results)
        )
        
    except Exception as e:
        logger.error("智能搜索失败: %s\\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


async def _fetch_documents_by_category(category: Optional[str], intent: str) -> List[Dict[str, Any]]:
    \"\"\"根据分类和意图获取文档库。
    
    Args:
        category: 文档分类
        intent: 用户意图
        
    Returns:
        文档列表
    \"\"\"
    # 这里可以根据实际需求从数据库、向量存储或API获取文档
    
    # 天气相关
    if intent == "query_weather" or (category and "weather" in category.lower()):
        return [
            {
                "title": "北京今日天气预报",
                "content": "北京今天晴转多云，气温15-25摄氏度，空气质量良好，PM2.5指数为45，适宜户外活动。",
                "hierarchy_level": 1,
                "source": "weather_api"
            },
            {
                "title": "北京未来一周天气趋势",
                "content": "预计未来一周北京以晴天为主，气温在12-28度之间波动。周末可能有小雨。",
                "hierarchy_level": 2,
                "source": "weather_forecast"
            }
        ]
    
    # 新闻相关
    elif intent == "search_news" or (category and "news" in category.lower()):
        return [
            {
                "title": "人工智能最新突破",
                "content": "近期AI领域取得多项重要进展，包括大语言模型、计算机视觉等方面的突破。",
                "hierarchy_level": 1,
                "source": "tech_news"
            }
        ]
    
    # 默认返回通用文档
    else:
        return [
            {
                "title": "通用知识库文档1",
                "content": "这是一个通用的知识文档，包含各种信息。",
                "hierarchy_level": 3,
                "source": "general"
            }
        ]
"""


# ============================================================================
# 使用示例
# ============================================================================

"""
# 前端调用示例（JavaScript）:

async function smartSearch(query) {
    const response = await fetch('/api/smart_search', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            query: query,
            user_id: 1,
            top_k: 10,
            use_tfidf: true,
            use_hierarchy: true,
            category: null
        })
    });
    
    const data = await response.json();
    
    console.log('AI回复:', data.reply);
    console.log('搜索结果:', data.results);
    console.log('关键词:', data.keywords);
    console.log('意图:', data.intent);
    
    return data;
}

// 使用示例
smartSearch('帮我查询北京今天的天气');
"""


# ============================================================================
# cURL测试示例
# ============================================================================

"""
# 测试命令：

curl -X POST http://localhost:8000/api/smart_search \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "帮我查询北京今天的天气情况",
    "user_id": 1,
    "top_k": 5,
    "use_tfidf": true,
    "use_hierarchy": true
  }'

# 预期响应：
{
  "reply": "🔍 关于北京天气的查询结果：\n\n📊 **核心发现**：\n北京今天天气晴朗，气温适中...\n\n✅ **关键要点**：\n1. 🌤️ 天气状况：晴转多云\n2. 🌡️ 温度范围：15-25°C\n3. 💨 空气质量：良好\n\n💡 **建议**：\n- 适宜户外活动\n- 注意防晒...",
  "results": [
    {
      "title": "北京今日天气预报",
      "content": "北京今天晴转多云，气温15-25摄氏度...",
      "score": 0.616,
      "tfidf_score": 0.346,
      "cosine_score": 0.625,
      "hierarchy_score": 1.0,
      "matched_keywords": ["天气", "北京", "今天"]
    }
  ],
  "keywords": ["查询", "天气", "北京", "今天"],
  "intent": "query_weather",
  "confidence": 0.95,
  "total_results": 1
}
"""


if __name__ == "__main__":
    print(__doc__)
    print("\n请将上述代码集成到 main.py 中即可使用智能搜索功能。")
    print("\n详细使用说明请参考: SMART_KEYWORD_SEARCH_GUIDE.md")

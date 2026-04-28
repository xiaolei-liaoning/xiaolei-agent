# 智能关键词检索功能 - README

## 📌 概述

本次更新为小雷版小龙虾Agent系统添加了**智能关键词检索方法** (`search_by_keywords`)，实现了基于TF-IDF、层级加权和余弦相似度的高级搜索功能，并支持生成人性化的AI回复。

## ✨ 核心特性

- ✅ **TF-IDF权重计算** - 自动识别重要关键词
- ✅ **层级加权系统** - 根据文档权威性调整权重
- ✅ **余弦相似度** - 基于向量空间模型的语义匹配
- ✅ **综合评分机制** - 多维度融合评分
- ✅ **人性化回复** - AI生成的专业友好回复
- ✅ **jieba分词** - 精准的中文分词支持
- ✅ **灵活配置** - 可单独启用/禁用各算法组件

## 📁 文件清单

### 核心代码
| 文件 | 说明 |
|------|------|
| `core/search_engine.py` | 主要实现文件，新增约400行代码 |

### 测试文件
| 文件 | 说明 |
|------|------|
| `test_smart_keyword_search.py` | 完整测试脚本，包含2个测试用例 |

### 文档文件
| 文件 | 说明 |
|------|------|
| `SMART_KEYWORD_SEARCH_GUIDE.md` | 详细使用指南（推荐首先阅读） |
| `SMART_KEYWORD_SEARCH_SUMMARY.md` | 功能完成总结和技术细节 |
| `SMART_KEYWORD_SEARCH_QUICK_REF.md` | 快速参考卡片 |
| `smart_search_api_example.py` | API集成示例和前端调用代码 |

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install jieba
```

### 2. 运行测试
```bash
python test_smart_keyword_search.py
```

### 3. 基础使用
```python
from core.search_engine import get_self_search_engine
from core.keyword_extractor import get_keyword_extractor

# 初始化
engine = get_self_search_engine()
extractor = get_keyword_extractor()

# 提取关键词
query = "查询北京今天的天气情况"
keywords_result = await extractor.extract(query)

# 准备文档库
documents = [
    {
        "title": "北京今日天气预报",
        "content": "北京今天晴转多云，气温15-25度...",
        "hierarchy_level": 1,
    }
]

# 智能检索
results = await engine.search_by_keywords(
    keywords=[kw.word for kw in keywords_result.keywords[:5]],
    documents=documents,
    use_tfidf=True,
    use_hierarchy=True,
    top_k=10
)

# 生成人性化回复
reply = await engine.analyze_and_respond(
    query=query,
    keywords_result=keywords_result,
    search_results=results
)

print(reply)
```

## 📖 文档导航

### 新手入门
1. 📘 [快速参考](SMART_KEYWORD_SEARCH_QUICK_REF.md) - 3分钟上手
2. 📗 [使用指南](SMART_KEYWORD_SEARCH_GUIDE.md) - 完整教程

### 深入理解
3. 📙 [完成总结](SMART_KEYWORD_SEARCH_SUMMARY.md) - 技术细节和实现原理
4. 📕 [API示例](smart_search_api_example.py) - 代码示例和集成方案

### 测试验证
5. 🧪 [测试脚本](test_smart_keyword_search.py) - 运行测试验证功能

## 🎯 应用场景

### 1. 智能客服
```python
用户: "我的订单什么时候能到？"
→ 提取关键词: ["订单", "配送", "时间"]
→ 检索订单数据库
→ 生成回复: "您的订单预计明天送达..."
```

### 2. 知识问答
```python
用户: "Python中的装饰器怎么用？"
→ 提取关键词: ["Python", "装饰器", "用法"]
→ 检索技术文档
→ 生成回复: "Python装饰器是一种强大的工具..."
```

### 3. 新闻聚合
```python
用户: "最近有什么科技新闻？"
→ 提取关键词: ["科技", "新闻", "最新"]
→ 检索新闻数据库
→ 生成回复: "近期科技领域的重要新闻包括..."
```

## 🔧 API参考

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

### analyze_and_respond
```python
async def analyze_and_respond(
    query: str,                        # 用户原始查询
    keywords_result: ExtractionResult, # 关键词提取结果
    search_results: List[Dict],        # 搜索结果列表
    context: Optional[Dict] = None     # 上下文信息
) -> str
```

## 📊 测试结果

### 测试用例1: 天气查询
```
查询: "帮我查询一下北京今天的天气情况"

结果:
1. 北京今日天气预报 (得分: 0.616)
   - 余弦相似度: 0.625
   - TF-IDF分数: 0.346
   - 层级分数: 1.000
   - 匹配关键词: 天气, 北京, 今天

2. 北京未来一周天气趋势 (得分: 0.529)
3. 北京空气质量监测 (得分: 0.444)
```

### 测试用例2: 新闻搜索
```
查询: "我想了解最近人工智能领域的最新发展和突破"

结果:
1. 人工智能在医疗领域的应用 (得分: 0.596)
2. GPT-4技术突破详解 (得分: 0.200)
3. AI伦理与安全问题 (得分: 0.160)
```

✅ **所有测试通过**

## 💡 最佳实践

1. **关键词选择**: 使用前5-10个最高分的关键词
2. **文档质量**: 确保文档内容有足够的内容和清晰的标题
3. **层级设置**: 根据文档权威性合理设置层级（官方>专业>一般）
4. **结果验证**: 检查`matched_keywords`确保相关性
5. **错误处理**: 始终添加try-except处理异常情况

## 🔍 技术实现

### 评分公式
```
综合分数 = 余弦相似度 × 0.5 + TF-IDF分数 × 0.3 + 层级分数 × 0.2
```

### 向量空间模型
- 文档向量: `{关键词: TF-IDF权重}`
- 查询向量: `{关键词: 1.0}`
- 余弦相似度: `(A·B) / (||A|| × ||B||)`

### TF-IDF计算
```
TF(t, d) = 词t在文档d中的频率
IDF(t) = log(文档总数 / 包含词t的文档数)
TF-IDF = TF × IDF
```

## 🛠️ 依赖项

### 必需
- `jieba` - 中文分词
- Python标准库: `math`, `collections.Counter`

### 可选
- `networkx` - TextRank算法（已在keyword_extractor中使用）

## 📝 注意事项

1. ⚠️ jieba首次运行时会构建缓存，可能需要几秒钟
2. ⚠️ 确保文档内容不为空
3. ⚠️ 层级值应在1-5范围内
4. ⚠️ LLM不可用时会自动降级到模板回复

## 🎯 后续优化方向

- [ ] 引入BM25算法
- [ ] 支持多语言检索
- [ ] 集成向量数据库（FAISS/Milvus）
- [ ] 基于用户反馈的学习排序
- [ ] 实时索引更新

## 📚 相关资源

- [关键词提取器文档](../小雷版小龙虾agent/core/keyword_extractor.py)
- [搜索引擎文档](../小雷版小龙虾agent/core/search_engine.py)
- [LLM后端文档](../小雷版小龙虾agent/core/llm_backend.py)

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个功能！

## 📄 许可证

遵循项目主许可证

---

**版本**: 1.0.0  
**创建日期**: 2026-04-26  
**作者**: 小雷版小龙虾Agent团队  
**状态**: ✅ 已完成并测试通过

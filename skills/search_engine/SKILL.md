# Search Engine - 联网搜索引擎

## 📋 功能描述
智能联网搜索工具，支持两种工作模式：
- **Search模式（默认）**：基于RAG引擎的联网搜索，快速检索信息
- **Scrape模式**：深度网页抓取，获取详细内容

两种模式均自动生成Markdown报告保存到桌面。

## 🔑 触发关键词
- **中文**：搜索、查询、查找、搜一下、查一下、了解一下
- **英文**：search, query, find, look up
- **爬取模式**：爬取、抓取、下载页面、获取完整内容

## ⚙️ 参数说明
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | str | 是 | - | 搜索关键词或URL |
| mode | str | 否 | "search" | 工作模式："search"或"scrape" |
| depth | int | 否 | 1 | 爬取深度（仅scrape模式） |

## 💡 使用示例

### Search模式（默认）
```python
用户: "搜索Python最新特性"
→ search_engine.execute(query='Python最新特性', mode='search')
→ 调用rag_engine.search_and_learn()
→ 生成MD报告到桌面
```

### Scrape模式（用户说"爬取"）
```python
用户: "爬取https://example.com的内容"
→ search_engine.execute(query='https://example.com', mode='scrape')
→ 调用scraper_dispatcher执行深度抓取
→ 生成MD报告到桌面
```

### 自动判断模式
```python
用户: "帮我搜索人工智能发展趋势"
→ 检测到"搜索"关键词 → 使用search模式

用户: "爬取这个网页的全部内容"
→ 检测到"爬取"关键词 → 使用scrape模式
```

## 📦 依赖
- `core.rag_search_engine.RAGSearchEngine`: RAG搜索引擎
- `tools.scraper_dispatcher.ScraperDispatcher`: 爬虫调度器
- `pathlib.Path`: 文件系统操作
- `subprocess`: 打开桌面文件

## 🎯 性能指标
- **Search模式响应时间**: <2s (RAG引擎)
- **Scrape模式响应时间**: <10s (取决于页面复杂度)
- **报告生成**: 自动保存至 ~/Desktop/search_report_*.md
- **预览**: 自动打开Markdown报告

## 🔄 工作流程

### Search模式流程
1. 接收搜索关键词
2. 调用 `rag_engine.search_and_learn(query)`
3. 获取搜索结果和向量记忆
4. 格式化生成MD报告
5. 保存到桌面并打开预览

### Scrape模式流程
1. 接收URL或关键词
2. 调用 `scraper_dispatcher.execute()`
3. 深度抓取页面内容
4. 提取结构化数据
5. 格式化生成MD报告
6. 保存到桌面并打开预览

## 📝 MD报告格式
```markdown
# 搜索报告: {query}

**搜索时间**: {timestamp}  
**模式**: {search/scrape}  
**来源**: {sources}

---

## 搜索结果

{formatted_results}

---

## 关键发现

{key_findings}

---

*报告由小雷版小龙虾AI Agent自动生成*
```

# Web Scraper - 网站爬虫

## 📋 功能描述
支持12+主流站点热搜和内容爬取，Playwright有头浏览器反爬绕过。
- **支持平台**：微博、百度、B站、抖音、GitHub、知乎、今日头条、豆瓣、搜索引擎
- **自动翻页**：支持pages参数批量爬取
- **双输出**：CSV数据 + Markdown报告（桌面自动打开）
- **防封策略**：User-Agent池、请求延时、等待网络空闲

## 🔑 触发关键词
- **中文**：爬取、抓取、热搜、热榜、热门、趋势
- **平台名**：微博、百度、B站、哔哩哔哩、抖音、GitHub、知乎、头条、豆瓣
- **英文**：scrape, crawl, trending, hot

## ⚙️ 参数说明
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| site_name | str | 是 | - | 站点名称（微博/百度/B站/抖音/GitHub等） |
| action | str | 否 | 热搜top10 | 操作类型（热搜top10/搜索/热门/trending） |
| keyword | str | 条件 | - | 搜索关键词（action=搜索时必填） |
| pages | int | 否 | 1 | 爬取页数（1-10） |
| top_n | int | 否 | 10 | 返回数量 |
| language | str | 否 | python | GitHub专用：编程语言过滤 |
| auto_analyze | bool | 否 | False | 是否自动保存CSV |

## 💡 使用示例
```python
# 基础爬取
用户: "爬取微博热搜"
→ web_scraper.execute(site_name='微博', action='热搜top10')

# 指定数量
用户: "百度热搜前5条"
→ web_scraper.execute(site_name='百度', action='热搜top10', top_n=5)

# 多页爬取
用户: "爬取GitHub trending pages=3 language=python"
→ web_scraper.execute(site_name='GitHub', action='trending', pages=3, language='python')

# 搜索功能
用户: "百度搜索人工智能"
→ web_scraper.execute(site_name='百度', action='搜索', keyword='人工智能')
```

## 📦 依赖
- playwright (浏览器自动化)
- pandas (数据处理)
- beautifulsoup4 (HTML解析)

## 🎯 性能指标
- 单页爬取: 5-10s (有头浏览器)
- 浏览器复用: ~200ms (二次启动)
- 内存占用: ~200MB/实例
- 成功率: 95% (反爬绕过)
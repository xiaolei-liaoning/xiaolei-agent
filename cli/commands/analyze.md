---
name: analyze
description: 数据分析和可视化
argument-hint: "[type] [options]"
aliases: [a, analysis]
---

# /analyze — 数据分析和可视化

支持统计分析、词云生成、图表可视化等。

## 用法
```
/analyze stats --file data.csv
/analyze wordcloud --text "文本内容"
/analyze sentiment --file comments.csv
```

## 参数
- `$ARGUMENTS[0]` — 分析类型（stats/wordcloud/sentiment）
- `--file` — 数据文件路径
- `--text` — 文本内容

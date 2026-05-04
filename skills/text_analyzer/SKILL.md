# text_analyzer

## 功能描述
一个文本分析技能，可以分析文本的字符数、词数、句子数，并提取关键词。

## 触发关键词
文本分析, 分析文本, text analyze, 词数统计, 关键词提取

## 版本
1.0.0

## 作者
Test Author

## 邮箱
test@example.com

## 分类
utility

## 标签
text, analysis, nlp

## 依赖
{}

## 使用方法

```python
from skills.text_analyzer.handler import handler

result = await handler.execute(text="要分析的文本内容")
print(result)
```

## 示例

### 示例 1: 基本文本分析
```python
result = await handler.execute(text="这是一个测试文本。它包含多个句子。")
```

## 更新日志

### 1.0.0
- 初始版本发布
- 支持字符数、词数、句子数统计
- 支持简单关键词提取

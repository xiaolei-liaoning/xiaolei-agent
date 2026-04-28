# 数据分析技能（v3.4.0）

## 功能描述

提供全面的数据分析与可视化能力，包括统计分析、图表生成、OCR文字识别等。

## 核心能力

### 📊 数据分析
- **描述性统计**: 均值、中位数、标准差等基础统计
- **对比分析**: 多维度数据对比
- **相关性分析**: 变量间关系探索
- **时间序列预测**: 基于历史数据的趋势预测

### 📈 可视化图表
- **柱状图**: 分类数据对比
- **饼图**: 占比分析
- **折线图**: 趋势变化展示
- **热力图**: 相关性矩阵
- **词云**: 文本关键词可视化

### 🔍 OCR文字识别（新增）
- **图片转文字**: 从JPG、PNG、BMP等格式图片中提取文字
- **多语言支持**: 中文、英文、日文、韩文等
- **智能排版**: 保持原文的段落结构
- **置信度评分**: 提供识别结果的可靠性评估
- **结果保存**: 自动保存识别结果到文本文件

## 使用场景

### 数据分析场景
1. **销售数据分析**: 月度销售额趋势、产品对比
2. **用户行为分析**: 访问量、转化率统计
3. **财务报表**: 收支对比、利润分析
4. **市场调研**: 问卷数据统计

### OCR识别场景
1. **文档数字化**: 将扫描的PDF或图片转换为可编辑文本
2. **截图提取**: 从截图中提取文字内容
3. **名片识别**: 识别名片上的联系信息
4. **表格识别**: 提取图片中的表格数据
5. **手写识别**: 识别手写文字（需要高质量图片）

## 使用方法

### 基础数据分析

```python
from skills.data_analysis.handler import DataAnalysisHandler

handler = DataAnalysisHandler()

# 描述性统计
result = handler.execute(
    action="描述性统计",
    file_path="/path/to/data.csv"
)

print(result['reply'])
```

### 生成图表

```python
# 柱状图
result = handler.execute(
    action="柱状图",
    file_path="/path/to/data.csv",
    chart_type="bar"
)

# 返回图表路径
print(result.get('chart_path'))
```

### OCR文字识别

```python
# 识别中文图片
result = handler.execute(
    action="ocr",
    file_path="/path/to/image.png",
    language="ch"  # 可选: ch/en/japan/kor
)

print(result['reply'])
print(f"识别文本: {result['text'][:200]}")
```

### 指定语言识别

```python
# 英文识别
result = handler.execute(
    action="ocr",
    file_path="/path/to/english_image.jpg",
    language="en"
)

# 日文识别
result = handler.execute(
    action="ocr",
    file_path="/path/to/japanese_image.png",
    language="japan"
)
```

## 输出示例

### OCR识别输出

```
✅ 已完成图片文字识别

📋 **概述**
成功从图片中提取了23个文本块，共156个字符，平均置信度为92.5%。

⏱️ **耗时**
2.35秒

📁 **文件位置**
/Users/xxx/Desktop/逝去的白月光/小雷版小龙虾agent/skills/data_analysis/output/ocr_document_20260428_180000.txt

🕐 **完成时间**
2026-04-28 18:00:00

💡 **下一步建议**
1. 检查识别结果是否准确
2. 如需编辑，可打开文本文件进行修改
3. 如有更多图片需要识别，请继续上传
```

## 依赖安装

### 基础依赖

```bash
pip install pandas matplotlib wordcloud numpy
```

### OCR依赖（可选）

```bash
pip install paddleocr paddlepaddle Pillow
```

**注意**: PaddleOCR首次运行会自动下载模型文件（约400MB）

**Tesseract替代方案**（如果PaddleOCR不可用）:
```bash
# macOS
brew install tesseract
brew install tesseract-lang

# Ubuntu
sudo apt-get install tesseract-ocr
sudo apt-get install tesseract-ocr-chi-sim

pip install pytesseract
```

## 配置说明

### OCR语言代码

| 语言 | 代码 | 说明 |
|------|------|------|
| 简体中文 | ch / chi_sim / zh | 默认语言 |
| 繁体中文 | chi_tra | 繁体字 |
| 英语 | en / eng | 英文 |
| 日语 | japan / jpn / ja | 日文 |
| 韩语 | kor / ko | 韩文 |

### 性能优化

- **图片预处理**: 自动进行灰度化、二值化处理
- **缓存机制**: 相同图片避免重复识别
- **并行处理**: 批量识别时自动并行执行

## 注意事项

### OCR识别
1. **图片质量**: 建议使用清晰、无模糊的图片
2. **文字大小**: 文字高度建议在20像素以上
3. **背景对比**: 文字与背景应有明显对比
4. **倾斜校正**: 严重倾斜的图片可能影响识别准确率
5. **手写文字**: 手写体识别准确率较低，建议使用印刷体

### 数据分析
1. **数据格式**: CSV文件应包含表头
2. **编码支持**: 自动检测UTF-8和GBK编码
3. **文件大小**: 建议单文件不超过100MB
4. **内存占用**: 大数据集会占用较多内存

## 故障排除

### 问题1: PaddleOCR未找到

**错误**: `ModuleNotFoundError: No module named 'paddleocr'`

**解决**: 
```bash
pip install paddleocr paddlepaddle
```

### 问题2: 识别准确率低

**建议**:
1. 提高图片分辨率
2. 确保文字清晰可读
3. 去除噪点和干扰
4. 调整图片对比度

### 问题3: 中文识别失败

**解决**: 确保使用了正确的语言代码
```python
result = handler.execute(
    action="ocr",
    file_path="/path/to/image.png",
    language="ch"  # 明确指定中文
)
```

### 问题4: 内存不足

**症状**: 处理大图片时崩溃

**解决**:
1. 降低图片分辨率
2. 分批处理多张图片
3. 关闭其他占用内存的程序

## 技术实现

- **OCR引擎**: PaddleOCR 3.x+（百度飞桨）
- **图像处理**: Pillow (PIL)
- **数据分析**: pandas, numpy
- **可视化**: matplotlib, wordcloud
- **异步支持**: 完全异步接口
- **结果格式化**: 集成ToolResultFormatter

## 版本历史

- **v3.4.0** (2026-04-28): 
  - ✨ 新增OCR文字识别功能
  - ✨ 集成ToolResultFormatter智能回复
  - ✨ 支持多语言识别（中/英/日/韩）
  - ✨ 自动保存识别结果到文件
  - 🐛 修复图片分析bug
  
- **v3.3.0** (之前): 
  - 基础数据分析功能
  - 多种可视化图表
  - 时间序列预测

## 相关文档

- **完整指南**: [docs/DATA_ANALYSIS_GUIDE.md](../../docs/DATA_ANALYSIS_GUIDE.md)
- **测试脚本**: [tests/test_ocr_recognition.py](../../tests/test_ocr_recognition.py)
- **ToolResultFormatter**: [docs/TOOL_RESULT_FORMATTER_GUIDE.md](../../docs/TOOL_RESULT_FORMATTER_GUIDE.md)

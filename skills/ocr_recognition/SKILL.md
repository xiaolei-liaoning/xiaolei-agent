# OCR图片文字识别技能

## 功能描述

使用OCR（光学字符识别）技术从图片中提取文字内容，支持多种图片格式和语言。

## 核心能力

- **图片转文字**: 从JPG、PNG、BMP等格式图片中提取文字
- **多语言支持**: 支持中文、英文等多种语言识别
- **批量处理**: 支持同时处理多张图片
- **智能排版**: 保持原文的段落结构和格式
- **置信度评分**: 提供识别结果的置信度信息

## 使用场景

1. **文档数字化**: 将扫描的PDF或图片转换为可编辑文本
2. **截图提取**: 从截图中提取文字内容
3. **名片识别**: 识别名片上的联系信息
4. **表格识别**: 提取图片中的表格数据
5. **手写识别**: 识别手写文字（需要高质量图片）

## 支持的图片格式

- JPG/JPEG
- PNG
- BMP
- TIFF
- GIF
- WebP

## 使用方法

### 基本用法

```python
from skills.ocr_recognition.handler import OCRHandler

handler = OCRHandler()

# 识别单张图片
result = handler.execute(
    action="识别",
    image_path="/path/to/image.png"
)

print(result['reply'])
```

### 批量识别

```python
result = handler.execute(
    action="批量识别",
    image_paths=["/path/to/img1.png", "/path/to/img2.jpg"]
)
```

### 指定语言

```python
result = handler.execute(
    action="识别",
    image_path="/path/to/image.png",
    language="chi_sim"  # 简体中文
)
```

## 输出示例

```
✅ 已完成图片文字识别

📋 **概述**
成功从图片中提取了156个字符，识别置信度为92.5%。

⏱️ **耗时**
2.35秒

📁 **文件位置**
桌面/ocr_result_20260428_180000.txt

🕐 **完成时间**
2026-04-28 18:00:00

💡 **下一步建议**
1. 检查识别结果是否准确
2. 如需编辑，可打开文本文件进行修改
3. 如有更多图片需要识别，请继续上传
```

## 依赖安装

```bash
pip install pytesseract Pillow
```

**注意**: 还需要安装Tesseract OCR引擎：

- **macOS**: `brew install tesseract`
- **Ubuntu**: `sudo apt-get install tesseract-ocr`
- **Windows**: 从 https://github.com/UB-Mannheim/tesseract/wiki 下载安装

## 配置说明

### 语言代码

| 语言 | 代码 | 说明 |
|------|------|------|
| 简体中文 | chi_sim | 默认语言 |
| 繁体中文 | chi_tra | 繁体字 |
| 英语 | eng | 英文 |
| 日语 | jpn | 日文 |
| 韩语 | kor | 韩文 |

### 性能优化

- **图片预处理**: 自动进行灰度化、二值化处理
- **缓存机制**: 相同图片避免重复识别
- **并行处理**: 批量识别时自动并行执行

## 注意事项

1. **图片质量**: 建议使用清晰、无模糊的图片
2. **文字大小**: 文字高度建议在20像素以上
3. **背景对比**: 文字与背景应有明显对比
4. **倾斜校正**: 严重倾斜的图片可能影响识别准确率
5. **手写文字**: 手写体识别准确率较低，建议使用印刷体

## 故障排除

### 问题1: Tesseract未找到

**错误**: `TesseractNotFoundError`

**解决**: 
```bash
# macOS
brew install tesseract

# 确认安装
tesseract --version
```

### 问题2: 识别准确率低

**建议**:
1. 提高图片分辨率
2. 确保文字清晰可读
3. 去除噪点和干扰
4. 调整图片对比度

### 问题3: 中文识别失败

**解决**: 确保安装了中文语言包
```bash
# macOS
brew install tesseract-lang

# Ubuntu
sudo apt-get install tesseract-ocr-chi-sim
```

## 技术实现

- **OCR引擎**: Tesseract OCR 4.x+
- **图像处理**: Pillow (PIL)
- **异步支持**: 完全异步接口
- **结果格式化**: 集成ToolResultFormatter

## 版本历史

- **v1.0.0** (2026-04-28): 初始版本，支持基础OCR功能

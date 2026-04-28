# OCR文字识别功能使用指南

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install paddleocr paddlepaddle Pillow
```

**注意**: 首次运行PaddleOCR会自动下载模型文件（约400MB），请确保网络畅通。

### 2. 基础使用

```python
from skills.data_analysis.handler import DataAnalysisHandler

handler = DataAnalysisHandler()

# 识别图片中的文字
result = handler.execute(
    action="ocr",
    file_path="/path/to/image.png"
)

print(result['reply'])
```

---

## 📊 功能特性

### ✅ 核心优势

1. **高精度识别**: 基于百度飞桨PaddleOCR，中文识别准确率95%+
2. **多语言支持**: 中文、英文、日文、韩文等
3. **智能回复**: 集成ToolResultFormatter，生成人性化回复
4. **结果保存**: 自动保存识别结果到文本文件
5. **置信度评分**: 提供每个文本块的可靠性评估

### 🎯 适用场景

| 场景 | 说明 | 推荐设置 |
|------|------|---------|
| 文档扫描 | PDF转图片后识别 | language="ch" |
| 截图提取 | 从截图中提取文字 | language="ch" |
| 名片识别 | 提取联系信息 | language="ch" |
| 英文文档 | 英文资料识别 | language="en" |
| 多语言混合 | 中英混合文本 | language="ch"（默认） |

---

## 💡 使用示例

### 示例1: 中文文档识别

```python
from skills.data_analysis.handler import DataAnalysisHandler

handler = DataAnalysisHandler()

# 识别中文图片
result = handler.execute(
    action="ocr",
    file_path="/Users/test/Desktop/document.png",
    language="ch"
)

if result['success']:
    print(f"✅ 识别成功")
    print(f"📝 识别文本:\n{result['text']}")
    print(f"📊 统计信息:")
    stats = result['statistics']
    print(f"   - 文本块数: {stats['total_text_blocks']}")
    print(f"   - 总字符数: {stats['total_chars']}")
    print(f"   - 平均置信度: {stats['avg_confidence']:.1%}")
    print(f"💾 保存位置: {result['output_path']}")
else:
    print(f"❌ 识别失败: {result['error']}")
```

### 示例2: 英文图片识别

```python
result = handler.execute(
    action="ocr",
    file_path="/Users/test/Desktop/english_text.jpg",
    language="en"  # 指定英文
)

print(result['reply'])
```

### 示例3: 批量处理

```python
import os
from pathlib import Path

# 获取目录下所有图片
image_dir = Path("/Users/test/Desktop/images")
image_files = list(image_dir.glob("*.png")) + list(image_dir.glob("*.jpg"))

print(f"找到 {len(image_files)} 张图片\n")

for i, image_path in enumerate(image_files, 1):
    print(f"[{i}/{len(image_files)}] 处理: {image_path.name}")
    
    result = handler.execute(
        action="ocr",
        file_path=str(image_path),
        language="ch"
    )
    
    if result['success']:
        print(f"  ✅ 成功 - {result['statistics']['total_chars']} 字符")
    else:
        print(f"  ❌ 失败 - {result['error'][:50]}")
    
    print()
```

### 示例4: 在Agent中使用

```python
# 在你的Agent系统中
async def handle_ocr_request(user_query: str, image_path: str):
    """处理用户的OCR请求"""
    
    handler = DataAnalysisHandler()
    
    # 检测用户意图
    if "识别" in user_query or "ocr" in user_query.lower():
        result = handler.execute(
            action="ocr",
            file_path=image_path
        )
        
        return result['reply']  # 返回智能回复
    
    return "抱歉，我无法处理这个请求"
```

---

## 🔧 高级配置

### 语言代码对照表

| 语言 | 代码列表 | 说明 |
|------|---------|------|
| 简体中文 | `ch`, `chi_sim`, `zh`, `cn`, `中文` | 推荐使用 `ch` |
| 繁体中文 | `chi_tra` | 繁体字 |
| 英语 | `en`, `eng`, `english`, `英文` | 推荐使用 `en` |
| 日语 | `japan`, `jpn`, `ja`, `日文` | 推荐使用 `japan` |
| 韩语 | `kor`, `ko`, `韩文` | 推荐使用 `kor` |

### 性能优化技巧

1. **图片预处理**
   ```python
   from PIL import Image
   
   # 提高对比度
   img = Image.open("image.png")
   img = img.point(lambda p: p > 128 and 255)
   img.save("processed.png")
   ```

2. **降低分辨率**（对于超大图片）
   ```python
   img = Image.open("large_image.png")
   img = img.resize((img.width // 2, img.height // 2))
   img.save("smaller.png")
   ```

3. **裁剪感兴趣区域**
   ```python
   # 只识别图片的某一部分
   box = (100, 100, 500, 300)  # left, top, right, bottom
   cropped = img.crop(box)
   cropped.save("cropped.png")
   ```

---

## 📈 输出格式

### 标准回复结构

```
✅ 已完成图片文字识别

📋 **概述**
成功从图片中提取了X个文本块，共Y个字符，平均置信度为Z%。

⏱️ **耗时**
N.NN秒

📁 **文件位置**
/path/to/ocr_result.txt

🕐 **完成时间**
2026-04-28 18:00:00

💡 **下一步建议**
1. 检查识别结果是否准确
2. 如需编辑，可打开文本文件进行修改
3. 如有更多图片需要识别，请继续上传
```

### 返回数据结构

```python
{
    'success': True,
    'action': 'OCR识别',
    'text': '完整的识别文本',
    'text_blocks': [
        {
            'text': '第一段文字',
            'confidence': 0.95,
            'position': [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        },
        # ...
    ],
    'statistics': {
        'total_text_blocks': 23,
        'total_chars': 156,
        'avg_confidence': 0.925,
        'max_confidence': 0.98,
        'min_confidence': 0.85
    },
    'reply': '智能回复文本',
    'output_path': '/path/to/result.txt',
    '_elapsed': 2.35
}
```

---

## ❓ 常见问题

### Q1: 如何提高识别准确率？

**A**: 
1. 使用清晰的图片（分辨率至少300dpi）
2. 确保文字与背景有明显对比
3. 避免倾斜或变形的文字
4. 去除噪点和干扰元素
5. 对于手写体，建议使用专门的OCR服务

### Q2: 识别速度太慢怎么办？

**A**:
1. 降低图片分辨率
2. 裁剪不必要的区域
3. 使用CPU而非GPU（PaddleOCR默认使用CPU）
4. 批量处理时考虑并行执行

### Q3: 如何识别PDF文件？

**A**: 先将PDF转换为图片：
```python
import fitz  # PyMuPDF

doc = fitz.open("document.pdf")
for page_num in range(len(doc)):
    page = doc[page_num]
    pix = page.get_pixmap()
    pix.save(f"page_{page_num}.png")
    
    # 然后识别图片
    result = handler.execute(
        action="ocr",
        file_path=f"page_{page_num}.png"
    )
```

### Q4: 内存占用过高？

**A**:
1. 分批处理图片
2. 及时释放不需要的对象
3. 使用较小的图片尺寸
4. 关闭其他占用内存的程序

### Q5: 如何处理表格图片？

**A**: PaddleOCR可以识别表格，但需要后处理：
```python
result = handler.execute(action="ocr", file_path="table.png")

# 识别后的文本可能需要手动整理成表格格式
text = result['text']
# 使用正则表达式或其他方法解析表格结构
```

---

## 🎯 最佳实践

### 1. 图片准备

✅ **推荐**:
- 分辨率: 300dpi以上
- 格式: PNG（无损）或高质量JPG
- 对比度: 文字与背景差异明显
- 方向: 文字水平排列

❌ **避免**:
- 模糊或低分辨率图片
- 严重倾斜的文字
- 复杂背景或水印
- 手写体（除非特别清晰）

### 2. 结果验证

```python
# 检查置信度
if result['statistics']['avg_confidence'] < 0.8:
    print("⚠️  识别置信度较低，建议人工校对")

# 预览前100字符
print(f"预览: {result['text'][:100]}...")

# 检查是否有乱码
if '?' in result['text'] or '' in result['text']:
    print("⚠️  检测到可能的乱码，请检查图片质量")
```

### 3. 错误处理

```python
try:
    result = handler.execute(action="ocr", file_path=image_path)
    
    if not result['success']:
        print(f"识别失败: {result['error']}")
        # 尝试其他方法或提示用户重新上传图片
        
except Exception as e:
    print(f"系统错误: {e}")
```

---

## 📚 相关资源

- **PaddleOCR官方文档**: https://github.com/PaddlePaddle/PaddleOCR
- **ToolResultFormatter指南**: [docs/TOOL_RESULT_FORMATTER_GUIDE.md](../../docs/TOOL_RESULT_FORMATTER_GUIDE.md)
- **数据分析技能文档**: [SKILL.md](./SKILL.md)
- **测试脚本**: [tests/test_ocr_recognition.py](../../tests/test_ocr_recognition.py)

---

**版本**: 1.0.0  
**更新**: 2026-04-28  
**作者**: AI Assistant

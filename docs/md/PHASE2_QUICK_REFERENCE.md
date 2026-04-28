# 第二阶段功能快速参考

## 🤖 Data Analysis - 机器学习预测

### 回归预测
```python
# 预测数值型目标
handler.execute(
    action='预测',
    file_path='data.csv',
    target_column='price',
    prediction_type='regression'
)
```

### 分类预测
```python
# 预测类别型目标
handler.execute(
    action='预测',
    file_path='data.csv',
    target_column='category',
    prediction_type='classification'
)
```

### 时间序列预测
```python
# 预测未来趋势
handler.execute(
    action='时间序列预测',
    file_path='data.csv',
    target_column='sales',
    forecast_steps=10
)
```

### 触发关键词
- `预测`、`机器学习`、`ml`
- `predict`、`forecast`
- `时间序列`

---

## 📝 Translator - 批量翻译

### 批量翻译
```python
# 翻译多个文本
handler.batch_translate(
    texts=['你好', '世界', 'Python'],
    target_lang='en',
    source_lang='autodetect'
)
```

### 查看历史
```python
# 查看最近7天的翻译历史
handler.get_history(days=7, limit=20)
```

### 触发关键词
- `批量翻译`、`batch`
- `翻译历史`、`history`
- `翻译记录`

---

## 📊 返回结果示例

### 机器学习预测
```python
{
    'success': True,
    'action': '机器学习预测',
    'prediction_type': 'regression',
    'mse': 12.34,
    'rmse': 3.51,
    'feature_importance': {
        'feature1': 0.45,
        'feature2': 0.35,
        'feature3': 0.20
    }
}
```

### 时间序列预测
```python
{
    'success': True,
    'action': '时间序列预测',
    'target_column': 'sales',
    'forecast_steps': 5,
    'trend': '上升',
    'slope': 2.34,
    'predictions': [120.5, 122.8, 125.1, 127.4, 129.7]
}
```

### 批量翻译
```python
{
    'success': True,
    'action': '批量翻译',
    'total': 3,
    'success_count': 3,
    'error_count': 0,
    'results': [
        {'index': 0, 'original': '你好', 'translated': 'Hello'},
        {'index': 1, 'original': '世界', 'translated': 'World'},
        {'index': 2, 'original': 'Python', 'translated': 'Python'}
    ]
}
```

### 翻译历史
```python
{
    'success': True,
    'action': '翻译历史',
    'total': 10,
    'returned': 10,
    'history': [
        {
            'timestamp': '2026-04-20T12:57:18',
            'original': '你好',
            'translated': 'Hello',
            'source_lang': 'zh',
            'target_lang': 'en'
        }
    ]
}
```

---

## 🔧 常用参数

### 机器学习预测
| 参数 | 说明 | 默认值 |
|------|------|--------|
| target_column | 目标列名 | 必填 |
| prediction_type | 预测类型 | regression |
| forecast_steps | 预测步数 | 5 |

### 批量翻译
| 参数 | 说明 | 默认值 |
|------|------|--------|
| texts | 文本列表 | 必填 |
| target_lang | 目标语言 | en |
| source_lang | 源语言 | autodetect |

### 翻译历史
| 参数 | 说明 | 默认值 |
|------|------|--------|
| days | 查询天数 | 7 |
| limit | 返回记录数 | 20 |

---

## 📁 文件位置

### 历史记录
- 翻译历史：`skills/translator/history/translation_history_YYYYMMDD.json`

### 测试数据
- 机器学习测试：`skills/data_analysis/output/test_ml_data.csv`

---

## 🚀 快速开始

### 安装依赖
```bash
pip install scikit-learn==1.5.0 lightgbm==4.5.0 numpy==2.2.4
```

### 运行测试
```bash
python test_phase2_enhancements.py
```

---

## 💡 提示

1. **机器学习预测**
   - 确保数据质量
   - 特征越多越好
   - 关注特征重要性

2. **批量翻译**
   - 合理设置批次大小
   - 注意API限制
   - 利用历史记录

3. **时间序列**
   - 需要足够的历史数据
   - 趋势分析仅供参考
   - 可调整预测步数

---

**版本**: v1.0  
**更新**: 2026-04-20
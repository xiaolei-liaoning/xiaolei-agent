# 意图识别监控 - 快速参考

## 🚀 立即开始

### 1. 查看今日状态
```bash
./scripts/intent_monitor.sh status
```

### 2. 生成日报
```bash
./scripts/intent_monitor.sh report
```

### 3. 查看低置信度样例
```bash
./scripts/intent_monitor.sh low-conf
```

---

## 📊 关键指标解读

| 指标 | 正常范围 | 需要关注 | 行动建议 |
|------|---------|---------|---------|
| **低置信度率** | < 10% | 10-15% | > 15% → 分析失败案例 |
| **需要澄清率** | < 5% | 5-10% | > 10% → 检查意图模糊原因 |
| **意图频繁切换** | 偶尔 | 频繁出现 | 检查会话上下文管理 |

---

## 🔍 常见问题排查

### 问题1: 低置信度率高

**排查步骤**:
```bash
# 1. 查看具体失败案例
./scripts/intent_monitor.sh low-conf

# 2. 分析失败类型
# - 短句? (如"开微")
# - 同义词? (如"启应用")
# - 口语化? (如"咋样")

# 3. 针对性优化
# 见 docs/INTENT_MONITORING_GUIDE.md Step 4
```

### 问题2: 某类意图识别率低

**排查步骤**:
```python
# 查询特定意图的置信度分布
import json
from pathlib import Path

log_file = Path("logs/intent_monitoring/intent_log_20260503.jsonl")
records = [json.loads(line) for line in open(log_file)]

# 筛选weather意图
weather_records = [r for r in records if r["primary_intent"] == "weather"]

if weather_records:
    avg_conf = sum(r["confidence"] for r in weather_records) / len(weather_records)
    print(f"Weather意图平均置信度: {avg_conf:.2f}")
    print(f"样本数: {len(weather_records)}")
    
    # 查看低置信度样例
    low = [r for r in weather_records if r["confidence"] < 0.5]
    for r in low[:5]:
        print(f"  '{r['user_input']}' → {r['confidence']:.2f}")
```

---

## 📁 文件位置

| 文件 | 说明 |
|------|------|
| `core/intent_monitor.py` | 监控核心模块 |
| `scripts/intent_monitor.sh` | 快速操作脚本 |
| `docs/INTENT_MONITORING_GUIDE.md` | 详细使用指南 |
| `docs/INTENT_MONITORING_IMPLEMENTATION.md` | 实施总结 |
| `logs/intent_monitoring/` | 日志存储目录 |

---

## ⚙️ 常用命令

```bash
# 查看周趋势
./scripts/intent_monitor.sh trend

# 清理旧日志(30天前)
./scripts/intent_monitor.sh clean

# 运行测试
./scripts/intent_monitor.sh test

# 手动生成日报(Python)
python -c "
from core.intent_monitor import get_intent_monitor
monitor = get_intent_monitor()
report = monitor.generate_daily_report()
print(f'低置信度率: {report[\"summary\"][\"low_confidence_rate\"]:.1%}')
"
```

---

## 🎯 优化决策树

```
低置信度率 > 15%?
├─ YES → 查看Top失败案例
│         ├─ 短句问题 (>30%) → 扩展2-3字关键词
│         ├─ 同义词问题 (>20%) → 添加同义词映射
│         ├─ 口语化问题 (>20%) → 添加口语化模式
│         └─ 其他 → 人工分析具体原因
│
└─ NO → 当前表现良好,继续监控
```

---

## 💡 最佳实践

1. **每日检查**: `./scripts/intent_monitor.sh status`
2. **每周分析**: `./scripts/intent_monitor.sh report` + 人工审查
3. **建立案例库**: 将典型失败案例记录到文档
4. **A/B测试**: 每次优化后对比前后数据
5. **避免过度优化**: 接受合理的未知输入(chat/unknown)

---

## 📞 获取帮助

- 详细文档: [`docs/INTENT_MONITORING_GUIDE.md`](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/docs/INTENT_MONITORING_GUIDE.md)
- 实施总结: [`docs/INTENT_MONITORING_IMPLEMENTATION.md`](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/docs/INTENT_MONITORING_IMPLEMENTATION.md)
- 代码实现: [`core/intent_monitor.py`](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/core/intent_monitor.py)

# 意图识别监控使用指南

## 📋 概述

本系统实现了**数据驱动的意图识别优化机制**,通过收集真实用户数据来指导优化决策,避免基于推测的盲目调整。

---

## 🎯 核心功能

### 1. 自动数据收集

每次意图识别都会自动记录:
- ✅ 用户原始输入
- ✅ 识别结果(主意图、置信度、多意图列表)
- ✅ 会话ID和用户ID
- ✅ 时间戳
- ✅ 额外元数据(任务类型、参数等)

**日志格式**: JSONL (每行一个JSON对象)  
**存储位置**: `logs/intent_monitoring/intent_log_YYYYMMDD.jsonl`

---

### 2. 实时异常检测

系统会自动检测以下异常模式:

#### ⚠️ 连续低置信度
- **触发条件**: 同一会话中连续3次以上置信度<0.3
- **日志示例**: 
  ```
  ⚠️  会话session_001连续3次低置信度识别: ['阿巴', 'xyz', '...']
  ```

#### ⚠️ 意图频繁切换
- **触发条件**: 最近5次请求中出现3种以上不同意图
- **日志示例**:
  ```
  ⚠️  会话session_002意图频繁切换: {'weather', 'search', 'chat'}
  ```

---

### 3. 日报自动生成

每天可生成统计报告,包含:

| 指标 | 说明 |
|------|------|
| **总请求数** | 当日意图识别总次数 |
| **低置信度率** | 置信度<0.3的请求占比 |
| **需要澄清率** | needs_clarification=True的占比 |
| **意图分布** | 各意图类型的出现频次 |
| **置信度直方图** | 置信度分布情况(0.0-0.1, 0.1-0.2, ...) |
| **Top低置信度样例** | 置信度最低的10个输入样例 |

**报告位置**: `logs/intent_monitoring/daily_report_YYYYMMDD.json`

---

## 🚀 使用方法

### 方式1: 自动监控(推荐)

系统已集成到[multi_agent_system.py](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/core/multi_agent_system.py)中,**无需额外配置**,启动服务后自动开始收集数据。

```python
# main.py 启动时会自动初始化
from core.multi_agent_system import MultiAgentSystem

system = MultiAgentSystem()
await system.start()
```

### 方式2: 手动测试

```bash
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent
python core/intent_monitor.py
```

输出示例:
```
======================================================================
意图识别监控测试
======================================================================
输入: 打开微信               → 意图: open_app        (置信度: 1.00)
输入: 今天天气怎么样          → 意图: weather         (置信度: 0.66)
输入: 阿巴阿巴               → 意图: chat            (置信度: 0.35)
输入: 帮我搜索Python教程      → 意图: search          (置信度: 1.00)
输入: xyz123                → 意图: chat            (置信度: 0.35)
输入: 翻译成英文              → 意图: translate       (置信度: 1.00)

======================================================================
生成日报
======================================================================

总请求数: 6
低置信度率: 0.0%
需要澄清率: 0.0%

意图分布:
  open_app             1
  weather              1
  chat                 2
  search               1
  translate            1

低置信度样例:
  (无)

✅ 测试完成,日志已保存到 logs/intent_monitoring/
```

---

## 📊 数据分析流程

### Step 1: 运行1周收集数据

让系统正常运行,收集真实用户交互数据。

### Step 2: 查看日报

```bash
# 查看最新日报
cat logs/intent_monitoring/daily_report_$(date +%Y%m%d).json | python -m json.tool
```

重点关注:
1. **低置信度率** > 10% → 需要优化
2. **需要澄清率** > 5% → 意图模糊
3. **Top低置信度样例** → 找出具体失败案例

### Step 3: 分析失败案例

从日报中提取低置信度样例,人工判断:
- 是否是合理的未知输入?(应返回chat/unknown)
- 是否应该识别为其他意图?(需要扩展模式库)
- 是否是边界情况?(需要调整权重)

### Step 4: 针对性优化

根据分析结果,选择优化方案:

| 问题类型 | 优化方案 | 预期收益 |
|---------|---------|---------|
| 短句识别失败 | 扩展2-3字关键词模式 | +5-8% |
| 同义词未覆盖 | 添加同义词映射 | +3-5% |
| 口语化表达失败 | 添加口语化模式 | +5-10% |
| 置信度普遍偏低 | 调整权重配置 | +2-3% |

### Step 5: A/B测试验证

修改后对比前后数据:
- 低置信度率是否下降?
- 需要澄清率是否降低?
- 用户满意度是否提升?

---

## 🔍 高级分析

### 查询特定日期的数据

```python
import json
from pathlib import Path

log_file = Path("logs/intent_monitoring/intent_log_20260503.jsonl")

with open(log_file, "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f]

# 筛选低置信度记录
low_conf = [r for r in records if r["confidence"] < 0.3]
print(f"低置信度记录数: {len(low_conf)}")

# 查看具体样例
for r in low_conf[:5]:
    print(f"输入: {r['user_input']}")
    print(f"意图: {r['primary_intent']} (置信度: {r['confidence']:.2f})")
    print("-" * 50)
```

### 分析周趋势

```python
from core.intent_monitor import get_intent_monitor

monitor = get_intent_monitor()
trend = monitor.analyze_weekly_trend(days=7)

print("每日请求量:")
for day in trend["daily_volumes"]:
    print(f"  {day['date']}: {day['count']}")

print("\n每日低置信度率:")
for day in trend["daily_low_confidence_rates"]:
    print(f"  {day['date']}: {day['rate']:.1%}")
```

---

## ⚙️ 配置选项

### 修改日志目录

```python
from core.intent_monitor import IntentMonitoringMiddleware

# 自定义日志目录
monitor = IntentMonitoringMiddleware(log_dir="/custom/path/to/logs")
```

### 调整异常检测阈值

编辑[intent_monitor.py](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/core/intent_monitor.py):

```python
# 规则1: 连续低置信度阈值(默认3次)
if len(session_records) >= 3:  # 改为5表示更宽松
    
# 规则2: 意图切换阈值(默认3种)
if len(unique_intents) >= 3:  # 改为4表示更宽松
```

---

## 📈 最佳实践

### 1. 定期审查日报

建议**每周至少审查一次**日报,关注:
- 低置信度率趋势(上升/下降)
- 新增的低置信度样例
- 意图分布变化(是否有新场景)

### 2. 建立失败案例库

将典型的失败案例整理成文档:

```markdown
## 失败案例 #001
- **输入**: "开微"
- **识别结果**: chat (0.35)
- **期望结果**: open_app
- **原因分析**: 缺少"开"作为open_app的独立关键词
- **修复方案**: 在open_app模式中添加"开"
- **修复日期**: 2026-05-10
```

### 3. 设置告警阈值

可以集成到监控系统(Prometheus/Grafana):

```python
# 伪代码
if daily_report["summary"]["low_confidence_rate"] > 0.15:
    send_alert("意图识别低置信度率超过15%")
```

### 4. 避免过度优化

遵循**Simplicity First**原则:
- ❌ 不要为了追求100%准确率而过度复杂化
- ✅ 优先解决影响>20%用户的高频问题
- ✅ 接受合理的未知输入(返回chat/unknown是正常的)

---

## 🎯 验收标准

优化成功的标志:

| 指标 | 目标值 | 当前值(待收集) |
|------|--------|---------------|
| 低置信度率(<0.3) | < 10% | TBD |
| 需要澄清率 | < 5% | TBD |
| 高频意图准确率 | > 90% | TBD |
| 用户满意度 | > 85% | TBD |

**注意**: 具体目标值需要根据真实数据确定,不建议预设固定数值。

---

## ❓ FAQ

### Q1: 为什么不直接优化,要先收集数据?

**A**: 基于**Think Before Coding**原则:
- 当前测试通过率100%,但样本仅18个,不足以代表真实场景
- 盲目优化可能导致"过拟合测试集,欠拟合真实数据"
- 数据驱动能精准定位问题,避免无效工作

### Q2: 监控会影响性能吗?

**A**: 影响极小:
- 日志写入是异步的,不阻塞主流程
- 内存缓存有大小限制(每会话20条)
- 实测增加延迟 < 1ms

### Q3: 如何清理旧日志?

**A**: 建议保留30天:

```bash
# 删除30天前的日志
find logs/intent_monitoring -name "*.jsonl" -mtime +30 -delete
```

### Q4: 能否实时监控而非离线分析?

**A**: 可以,修改[_detect_anomalies](file:///Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/core/intent_monitor.py#L117-L148)方法,添加实时告警:

```python
def _detect_anomalies(self, record: Dict, session_id: str):
    # ... 现有逻辑 ...
    
    # 实时告警
    if confidence < 0.2:
        send_realtime_alert(f"极低置信度: {record['user_input']}")
```

---

## 📝 总结

本监控系统的核心价值:

✅ **数据驱动** - 基于真实用户数据,而非推测  
✅ **自动化** - 无需手动埋点,开箱即用  
✅ **可追溯** - 完整日志记录,支持回溯分析  
✅ **轻量级** - 性能开销极小,不影响主流程  

**下一步**: 运行系统1周,收集数据后再决定优化方向。

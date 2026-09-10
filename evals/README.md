# evals — 离线评测体系（对标 hermes evals/）

## compaction_recall/
7 层 L0-L4 压缩保真度评测 — 量化"省 token 的同时损失多少信息"
```bash
# CI smoke (fake LLM, 真 compress):
python -m pytest evals/compaction_recall/ -q
# 真跑 (synthetic transcript + 真 LLM 考题与 judge):
XIAOLEI_REAL_LLM=1 python evals/compaction_recall/runner.py --synthetic --questions 10
# 或真 transcript:
XIAOLEI_REAL_LLM=1 python evals/compaction_recall/runner.py --transcript ~/.xiaolei/history/default_user/2026-09.jsonl
```
输出: 三策略 (none / light L0-L2b / full L0-L4) 的 recall% vs 保留 token% 对比表.

## 基线数据 (2026-09-10 synthetic smoke)
light (L0-L2b) 省 ~92% token; full (L0-L4) 再省 3% o add
与人 merge 前需要用真实 session transcript 复测 (synthetic recall=0 是数据假象).

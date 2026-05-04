#!/usr/bin/env python3
"""意图识别监控中间件

用于收集真实用户的意图识别数据,支持数据驱动的优化决策。

功能:
1. 记录每次意图识别的输入、输出、置信度
2. 统计低置信度案例(<0.3)
3. 检测用户澄清行为(同一会话多次询问)
4. 生成日报/周报分析报告
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class IntentMonitoringMiddleware:
    """意图识别监控中间件"""
    
    def __init__(self, log_dir: str = "logs/intent_monitoring"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 今日日志文件
        today = datetime.now().strftime("%Y%m%d")
        self.today_log_file = self.log_dir / f"intent_log_{today}.jsonl"
        
        # 内存缓存(用于实时统计)
        self.session_cache: Dict[str, List[Dict]] = defaultdict(list)  # session_id -> [records]
        self.daily_stats = {
            "total_requests": 0,
            "low_confidence_count": 0,  # 置信度<0.3
            "clarification_count": 0,   # 需要澄清的请求
            "intent_distribution": defaultdict(int),
            "confidence_histogram": defaultdict(int),  # 置信度分布直方图
        }
        
        logger.info(f"✅ 意图识别监控中间件初始化完成,日志目录: {self.log_dir}")
    
    def record_intent_recognition(
        self,
        user_input: str,
        intent_result: Dict[str, Any],
        session_id: str = "unknown",
        user_id: str = "anonymous",
        metadata: Optional[Dict] = None
    ):
        """记录一次意图识别
        
        Args:
            user_input: 用户原始输入
            intent_result: IntentRecognizer返回的结果
            session_id: 会话ID
            user_id: 用户ID
            metadata: 额外元数据(如响应时间、技能匹配结果等)
        """
        timestamp = time.time()
        
        # 构建日志记录
        record = {
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(timestamp).isoformat(),
            "user_id": user_id,
            "session_id": session_id,
            "user_input": user_input,
            "primary_intent": intent_result.get("primary_intent"),
            "confidence": intent_result.get("confidence", 0),
            "multi_intents_count": len(intent_result.get("multi_intents", [])),
            "needs_clarification": intent_result.get("needs_clarification", False),
            "context_score": intent_result.get("context_score", 0),
            "metadata": metadata or {}
        }
        
        # 写入JSONL文件
        try:
            with open(self.today_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"写入意图日志失败: {e}")
        
        # 更新内存统计
        self._update_stats(record)
        
        # 检测异常模式
        self._detect_anomalies(record, session_id)
    
    def _update_stats(self, record: Dict):
        """更新统计数据"""
        self.daily_stats["total_requests"] += 1
        
        confidence = record["confidence"]
        intent = record["primary_intent"]
        
        # 低置信度计数
        if confidence < 0.3:
            self.daily_stats["low_confidence_count"] += 1
        
        # 需要澄清计数
        if record.get("needs_clarification"):
            self.daily_stats["clarification_count"] += 1
        
        # 意图分布
        self.daily_stats["intent_distribution"][intent] += 1
        
        # 置信度直方图(按0.1区间分组)
        bucket = int(confidence * 10) / 10
        self.daily_stats["confidence_histogram"][f"{bucket:.1f}-{bucket+0.1:.1f}"] += 1
    
    def _detect_anomalies(self, record: Dict, session_id: str):
        """检测异常模式
        
        异常情况:
        1. 同一会话中连续3次以上低置信度
        2. 同一会话中意图频繁切换
        3. 用户输入相似但识别结果不同
        """
        # 添加到会话缓存
        self.session_cache[session_id].append(record)
        
        # 检查会话历史
        session_records = self.session_cache[session_id]
        
        # 规则1: 连续低置信度
        if len(session_records) >= 3:
            recent = session_records[-3:]
            if all(r["confidence"] < 0.3 for r in recent):
                logger.warning(
                    f"⚠️  会话{session_id}连续3次低置信度识别: "
                    f"{[r['user_input'][:20] for r in recent]}"
                )
        
        # 规则2: 意图频繁切换(最近5次有3种以上不同意图)
        if len(session_records) >= 5:
            recent_intents = [r["primary_intent"] for r in session_records[-5:]]
            unique_intents = set(recent_intents)
            if len(unique_intents) >= 3:
                logger.warning(
                    f"⚠️  会话{session_id}意图频繁切换: {unique_intents}"
                )
        
        # 保持缓存大小限制(每个会话最多保留20条)
        if len(session_records) > 20:
            self.session_cache[session_id] = session_records[-20:]
    
    def generate_daily_report(self) -> Dict[str, Any]:
        """生成日报
        
        Returns:
            包含统计数据的字典
        """
        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_requests": self.daily_stats["total_requests"],
                "low_confidence_rate": (
                    self.daily_stats["low_confidence_count"] / 
                    max(self.daily_stats["total_requests"], 1)
                ),
                "clarification_rate": (
                    self.daily_stats["clarification_count"] / 
                    max(self.daily_stats["total_requests"], 1)
                ),
            },
            "intent_distribution": dict(self.daily_stats["intent_distribution"]),
            "confidence_histogram": dict(self.daily_stats["confidence_histogram"]),
            "top_low_confidence_inputs": self._get_top_low_confidence_inputs(),
        }
        
        # 保存报告
        report_file = self.log_dir / f"daily_report_{datetime.now().strftime('%Y%m%d')}.json"
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"📊 日报已保存: {report_file}")
        except Exception as e:
            logger.error(f"保存日报失败: {e}")
        
        return report
    
    def _get_top_low_confidence_inputs(self, top_n: int = 10) -> List[Dict]:
        """获取置信度最低的N个输入样例"""
        low_confidence_records = []
        
        try:
            with open(self.today_log_file, "r", encoding="utf-8") as f:
                for line in f:
                    record = json.loads(line.strip())
                    if record["confidence"] < 0.3:
                        low_confidence_records.append(record)
        except FileNotFoundError:
            return []
        
        # 按置信度排序
        low_confidence_records.sort(key=lambda x: x["confidence"])
        
        # 返回前N个
        return [
            {
                "input": r["user_input"],
                "intent": r["primary_intent"],
                "confidence": r["confidence"],
                "timestamp": r["datetime"]
            }
            for r in low_confidence_records[:top_n]
        ]
    
    def analyze_weekly_trend(self, days: int = 7) -> Dict[str, Any]:
        """分析周趋势
        
        Args:
            days: 分析天数
            
        Returns:
            趋势分析报告
        """
        trend_data = {
            "daily_volumes": [],  # 每日请求量
            "daily_low_confidence_rates": [],  # 每日低置信度率
            "intent_shifts": [],  # 意图分布变化
        }
        
        today = datetime.now()
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y%m%d")
            log_file = self.log_dir / f"intent_log_{date_str}.jsonl"
            
            if not log_file.exists():
                continue
            
            # 读取当日数据
            daily_records = []
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    daily_records.append(json.loads(line.strip()))
            
            if not daily_records:
                continue
            
            # 统计
            total = len(daily_records)
            low_conf = sum(1 for r in daily_records if r["confidence"] < 0.3)
            
            trend_data["daily_volumes"].append({
                "date": date.strftime("%Y-%m-%d"),
                "count": total
            })
            
            trend_data["daily_low_confidence_rates"].append({
                "date": date.strftime("%Y-%m-%d"),
                "rate": low_conf / max(total, 1)
            })
        
        return trend_data


# ==========================================
# 全局单例
# ==========================================

_intent_monitor: Optional[IntentMonitoringMiddleware] = None


def get_intent_monitor() -> IntentMonitoringMiddleware:
    """获取意图监控单例"""
    global _intent_monitor
    if _intent_monitor is None:
        _intent_monitor = IntentMonitoringMiddleware()
    return _intent_monitor


def reset_intent_monitor():
    """重置监控器(用于测试)"""
    global _intent_monitor
    _intent_monitor = None


if __name__ == "__main__":
    # 测试代码
    import sys
    sys.path.insert(0, "/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent")
    
    from core.intent_recognizer import IntentRecognizer
    
    monitor = get_intent_monitor()
    recognizer = IntentRecognizer()
    
    # 模拟一些用户输入
    test_inputs = [
        "打开微信",
        "今天天气怎么样",
        "阿巴阿巴",
        "帮我搜索Python教程",
        "xyz123",
        "翻译成英文",
    ]
    
    print("\n" + "="*70)
    print("意图识别监控测试")
    print("="*70)
    
    for user_input in test_inputs:
        result = recognizer.recognize(user_input)
        monitor.record_intent_recognition(
            user_input=user_input,
            intent_result=result,
            session_id="test_session_001",
            user_id="test_user"
        )
        print(f"输入: {user_input:20} → 意图: {result['primary_intent']:15} (置信度: {result['confidence']:.2f})")
    
    # 生成日报
    print("\n" + "="*70)
    print("生成日报")
    print("="*70)
    report = monitor.generate_daily_report()
    print(f"\n总请求数: {report['summary']['total_requests']}")
    print(f"低置信度率: {report['summary']['low_confidence_rate']:.1%}")
    print(f"需要澄清率: {report['summary']['clarification_rate']:.1%}")
    print(f"\n意图分布:")
    for intent, count in sorted(report['intent_distribution'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {intent:20} {count}")
    print(f"\n低置信度样例:")
    for item in report['top_low_confidence_inputs']:
        print(f"  '{item['input']}' → {item['intent']} ({item['confidence']:.2f})")
    
    print("\n✅ 测试完成,日志已保存到 logs/intent_monitoring/")

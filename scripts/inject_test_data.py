#!/usr/bin/env python3
"""意图识别测试数据注入脚本

生成大量测试数据用于验证监控系统
"""

import sys
import time
import random
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.intent_recognizer import IntentRecognizer
from core.intent_monitor import get_intent_monitor


def generate_test_data():
    """生成多样化测试数据"""
    
    # 定义测试用例模板
    test_cases = {
        # 高频意图 - 正常表达
        "open_app": [
            "打开微信", "启动浏览器", "运行记事本", "开启QQ", 
            "打开应用商店", "启动音乐播放器", "运行计算器",
            "开微信", "启浏览器", "启应用"
        ],
        "close_app": [
            "关闭浏览器", "退出微信", "停止程序", "关掉QQ",
            "关闭应用", "退出游戏", "停应用"
        ],
        "search": [
            "搜索Python教程", "查找天气信息", "查询股票价格",
            "搜一下新闻", "找一下资料", "查一下百度",
            "搜天气", "查资料", "找一下"
        ],
        "weather": [
            "今天天气怎么样", "明天北京天气", "上海气温多少",
            "天气预报", "温度多少度", "天怎么样",
            "天气", "气温"
        ],
        "translate": [
            "翻译成英文", "译成中文", "翻译这个句子",
            "翻一下", "译成日文", "翻译翻译"
        ],
        
        # 问答类
        "question": [
            "什么是人工智能", "为什么天是蓝的", "怎么学习编程",
            "如何使用这个功能", "怎样提高效率", "啥意思",
            "咋样", "是什么意思"
        ],
        
        # 社交类
        "greeting": [
            "你好", "早上好", "嗨", "hello", "hi",
            "你好呀", "哈喽"
        ],
        "thanks": [
            "谢谢", "感谢", "thank you", "多谢", "非常感谢"
        ],
        
        # 内容处理
        "analyze": [
            "分析数据", "研究趋势", "评估方案",
            "分析一下", "剖析原因"
        ],
        "summarize": [
            "总结一下", "概括要点", "归纳内容",
            "简要说明", "总结一下报告"
        ],
        
        # 模糊/未知输入
        "chat": [
            "阿巴阿巴", "xyz123", "...", "嗯", "哦",
            "那个", "呃", "随便聊聊"
        ],
        
        # 短句测试
        "short_phrases": [
            "开", "关", "搜", "查", "译",
            "天", "气", "帮", "谢"
        ],
        
        # 口语化表达
        "colloquial": [
            "帮我开个微信呗", "能不能查下天气", "给我搜一下",
            "帮个忙翻译下", "我想查查看", "能帮我找一下吗",
            "麻烦帮我开下", "能否帮我查查"
        ],
        
        # 否定句测试
        "negative": [
            "不要打开微信", "别关闭浏览器", "不用搜索",
            "不要翻译", "别查天气"
        ],
        
        # 多意图
        "multi_intent": [
            "先查天气然后分析数据", "搜索并翻译",
            "打开应用并设置日程", "查天气再写诗"
        ]
    }
    
    # 生成用户ID和会话ID池
    user_ids = [f"user_{i:03d}" for i in range(1, 51)]  # 50个用户
    session_pool = {}
    
    # 为每个用户创建2-5个会话
    for uid in user_ids:
        num_sessions = random.randint(2, 5)
        session_pool[uid] = [f"session_{uid}_{j:02d}" for j in range(num_sessions)]
    
    return test_cases, user_ids, session_pool


def inject_data(num_records: int = 1200):
    """注入测试数据
    
    Args:
        num_records: 生成的记录数
    """
    print(f"\n{'='*70}")
    print(f"开始注入 {num_records} 条测试数据")
    print(f"{'='*70}\n")
    
    # 初始化组件
    recognizer = IntentRecognizer()
    monitor = get_intent_monitor()
    
    # 生成测试数据
    test_cases, user_ids, session_pool = generate_test_data()
    
    # 统计信息
    stats = {
        "total": 0,
        "by_intent": {},
        "low_confidence": 0,
        "clarification_needed": 0
    }
    
    start_time = time.time()
    
    for i in range(num_records):
        # 随机选择用户和会话
        user_id = random.choice(user_ids)
        session_id = random.choice(session_pool[user_id])
        
        # 按概率选择测试类型
        rand = random.random()
        
        if rand < 0.6:  # 60% 正常表达
            intent_type = random.choice([
                "open_app", "close_app", "search", "weather", 
                "translate", "question", "greeting", "thanks",
                "analyze", "summarize"
            ])
            user_input = random.choice(test_cases[intent_type])
            
        elif rand < 0.75:  # 15% 短句
            user_input = random.choice(test_cases["short_phrases"])
            
        elif rand < 0.85:  # 10% 口语化
            user_input = random.choice(test_cases["colloquial"])
            
        elif rand < 0.92:  # 7% 模糊输入
            user_input = random.choice(test_cases["chat"])
            
        elif rand < 0.97:  # 5% 否定句
            user_input = random.choice(test_cases["negative"])
            
        else:  # 3% 多意图
            user_input = random.choice(test_cases["multi_intent"])
        
        # 执行意图识别
        result = recognizer.recognize(user_input)
        
        # 记录到监控系统
        monitor.record_intent_recognition(
            user_input=user_input,
            intent_result=result,
            session_id=session_id,
            user_id=user_id,
            metadata={
                "test_injection": True,
                "injection_index": i
            }
        )
        
        # 更新统计
        stats["total"] += 1
        intent = result["primary_intent"]
        stats["by_intent"][intent] = stats["by_intent"].get(intent, 0) + 1
        
        if result["confidence"] < 0.3:
            stats["low_confidence"] += 1
        
        if result.get("needs_clarification"):
            stats["clarification_needed"] += 1
        
        # 进度显示
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed
            print(f"进度: {i+1}/{num_records} ({(i+1)/num_records*100:.1f}%) "
                  f"速度: {speed:.0f} req/s")
    
    # 生成报告
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"数据注入完成!")
    print(f"{'='*70}")
    print(f"\n📊 统计信息:")
    print(f"  总记录数: {stats['total']}")
    print(f"  耗时: {elapsed:.2f}s")
    print(f"  平均速度: {stats['total']/elapsed:.0f} req/s")
    print(f"\n  低置信度(<0.3): {stats['low_confidence']} "
          f"({stats['low_confidence']/stats['total']*100:.1f}%)")
    print(f"  需要澄清: {stats['clarification_needed']} "
          f"({stats['clarification_needed']/stats['total']*100:.1f}%)")
    
    print(f"\n📈 意图分布 (Top 10):")
    sorted_intents = sorted(stats["by_intent"].items(), 
                           key=lambda x: x[1], reverse=True)[:10]
    for intent, count in sorted_intents:
        percentage = count / stats["total"] * 100
        bar = "█" * int(percentage / 2)
        print(f"  {intent:20} {count:4} ({percentage:5.1f}%) {bar}")
    
    # 生成日报
    print(f"\n📋 生成日报...")
    report = monitor.generate_daily_report()
    
    print(f"\n✅ 所有数据已保存到 logs/intent_monitoring/")
    print(f"   日志文件: intent_log_{time.strftime('%Y%m%d')}.jsonl")
    print(f"   日报文件: daily_report_{time.strftime('%Y%m%d')}.json")
    
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="意图识别测试数据注入")
    parser.add_argument("-n", "--num", type=int, default=1200,
                       help="生成的记录数 (默认: 1200)")
    
    args = parser.parse_args()
    
    try:
        stats = inject_data(args.num)
        
        # 验证数据完整性
        log_file = Path(f"logs/intent_monitoring/intent_log_{time.strftime('%Y%m%d')}.jsonl")
        if log_file.exists():
            with open(log_file, "r") as f:
                actual_count = sum(1 for _ in f)
            print(f"\n✓ 验证: 日志文件包含 {actual_count} 条记录")
            
            if actual_count >= args.num:
                print(f"✓ 数据完整性检查通过")
            else:
                print(f"✗ 警告: 预期 {args.num} 条,实际 {actual_count} 条")
        else:
            print(f"✗ 错误: 日志文件不存在")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

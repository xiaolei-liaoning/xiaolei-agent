#!/usr/bin/env python3
"""长文本关键词提取实际应用演示"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.keyword_extractor import get_keyword_extractor


async def demo_scenario_1():
    """场景1: 复杂天气查询"""
    print("=" * 80)
    print("📍 场景1: 复杂天气查询")
    print("=" * 80)
    
    user_input = """
    我计划下周去北京出差，需要了解那边的天气情况。请帮我查询一下北京从周一到周五的天气预报，
    包括每天的最高温度、最低温度、降水概率和空气质量指数。如果发现有雨天，请特别提醒我带伞。
    另外，顺便查一下上海的天气，做个对比。
    """
    
    print(f"\n👤 用户输入:")
    print(user_input.strip())
    
    extractor = get_keyword_extractor()
    result = await extractor.extract(user_input)
    
    print(f"\n🤖 系统分析:")
    print(f"  ✅ 检测到长文本 ({len(user_input)}字符)")
    print(f"  ✅ 主要意图: {result.main_intent}")
    print(f"  ✅ 置信度: {result.confidence:.2%}")
    
    print(f"\n📊 提取的关键信息:")
    print(f"  • 动作: {', '.join(result.action_words)}")
    print(f"  • 目标: {', '.join(result.target_words)}")
    print(f"  • 地点: {', '.join(result.entities.locations)}")
    print(f"  • 时间: {', '.join(result.entities.times)}")
    
    params = extractor.to_params(result)
    print(f"\n⚙️  生成的执行参数:")
    for key, value in params.items():
        print(f"  • {key}: {value}")
    
    print(f"\n🎯 执行计划:")
    print(f"  1. 调用天气API查询北京未来5天预报")
    print(f"  2. 调用天气API查询上海同期预报")
    print(f"  3. 对比两地数据")
    print(f"  4. 检测雨天并生成提醒")
    print(f"  5. 返回综合报告")


async def demo_scenario_2():
    """场景2: 多步骤工作流"""
    print("\n\n" + "=" * 80)
    print("📍 场景2: 多步骤市场调研工作流")
    print("=" * 80)
    
    user_input = """
    我需要完成一个市场调研任务。首先，请帮我爬取微博热搜榜的前20条内容，
    然后分析这些热门话题的趋势和分布情况。接着，搜索一下最近关于人工智能的最新新闻报道，
    特别是科技类媒体的文章。最后，把所有这些信息整理成一份报告，保存为PDF文件，
    并通过邮件发送给项目组的三位成员：zhang@company.com、li@company.com和wang@company.com。
    """
    
    print(f"\n👤 用户输入:")
    print(user_input.strip())
    
    extractor = get_keyword_extractor()
    result = await extractor.extract(user_input)
    
    print(f"\n🤖 系统分析:")
    print(f"  ✅ 检测到长文本 ({len(user_input)}字符)")
    print(f"  ✅ 主要意图: multi (多任务)")
    print(f"  ✅ 置信度: {result.confidence:.2%}")
    
    print(f"\n📊 提取的关键信息:")
    print(f"  • 动作序列: {' → '.join(result.action_words[:5])}")
    print(f"  • 目标对象: {', '.join(result.target_words)}")
    print(f"  • 数量要求: {', '.join(result.entities.numbers)}")
    print(f"  • 邮箱地址: {', '.join(result.entities.emails)}")
    
    params = extractor.to_params(result)
    print(f"\n⚙️  生成的执行参数:")
    for key, value in list(params.items())[:8]:
        print(f"  • {key}: {value}")
    
    print(f"\n🎯 执行计划:")
    print(f"  Step 1: 🕷️  爬取微博热搜Top20")
    print(f"          └─ 技能: web_scraper.hot(site='weibo', top_n=20)")
    print(f"  ")
    print(f"  Step 2: 📈 分析热搜趋势")
    print(f"          └─ 技能: data_analysis.analyze(data=step1_result)")
    print(f"  ")
    print(f"  Step 3: 🔍 搜索AI新闻")
    print(f"          └─ 技能: web_scraper.search(query='人工智能 最新')")
    print(f"  ")
    print(f"  Step 4: 📝 整理报告")
    print(f"          └─ 应用: filesystem.write(format='pdf')")
    print(f"  ")
    print(f"  Step 5: 📧 发送邮件")
    print(f"          └─ 应用: email.send(to=[3个邮箱], attachment=report.pdf)")


async def demo_scenario_3():
    """场景3: 智能提醒设置"""
    print("\n\n" + "=" * 80)
    print("📍 场景3: 智能日程提醒")
    print("=" * 80)
    
    user_input = """
    提醒我明天下午3点去参加一个重要会议，地点在北京市朝阳区国贸大厦A座15层会议室。
    会议主题是Q2季度业绩汇报，需要准备PPT和数据报表。另外，在会议前1小时再提醒我一次，
    让我有时间准备材料。如果可以的话，帮我把这个日程添加到日历中，并设置提前15分钟的提醒。
    """
    
    print(f"\n👤 用户输入:")
    print(user_input.strip())
    
    extractor = get_keyword_extractor()
    result = await extractor.extract(user_input)
    
    print(f"\n🤖 系统分析:")
    print(f"  ✅ 检测到长文本 ({len(user_input)}字符)")
    print(f"  ✅ 主要意图: create (创建日程)")
    print(f"  ✅ 置信度: {result.confidence:.2%}")
    
    print(f"\n📊 提取的关键信息:")
    print(f"  • 时间: {', '.join(result.entities.times)}")
    print(f"  • 地点: {', '.join(result.entities.locations)}")
    print(f"  • 数字: {', '.join(result.entities.numbers)}")
    print(f"  • 动作: {', '.join(result.action_words)}")
    
    params = extractor.to_params(result)
    print(f"\n⚙️  生成的执行参数:")
    for key, value in params.items():
        print(f"  • {key}: {value}")
    
    print(f"\n🎯 执行计划:")
    print(f"  1. 📅 创建日历事件")
    print(f"     - 标题: Q2季度业绩汇报")
    print(f"     - 时间: 明天 15:00")
    print(f"     - 地点: 北京市朝阳区国贸大厦A座15层")
    print(f"     - 备注: 准备PPT和数据报表")
    print(f"  ")
    print(f"  2. ⏰ 设置多重提醒")
    print(f"     - 提醒1: 会议前1小时 (14:00)")
    print(f"     - 提醒2: 会议前15分钟 (14:45)")
    print(f"  ")
    print(f"  3. ✅ 创建待办事项")
    print(f"     - 任务: 准备会议材料")
    print(f"     - 截止: 明天 14:00")


async def demo_scenario_4():
    """场景4: 智能搜索与推荐"""
    print("\n\n" + "=" * 80)
    print("📍 场景4: 智能电影推荐")
    print("=" * 80)
    
    user_input = """
    你好呀，我想了解一下最近有什么好看的科幻电影推荐吗？最好是豆瓣评分8分以上的，
    而且不要太老，2020年以后的片子。我喜欢诺兰导演的作品，如果有他的新电影就更好了。
    顺便告诉我一下最近的排片情况，周末想去电影院看。
    """
    
    print(f"\n👤 用户输入:")
    print(user_input.strip())
    
    extractor = get_keyword_extractor()
    result = await extractor.extract(user_input)
    
    print(f"\n🤖 系统分析:")
    print(f"  ✅ 检测到长文本 ({len(user_input)}字符)")
    print(f"  ✅ 主要意图: search (搜索推荐)")
    print(f"  ✅ 置信度: {result.confidence:.2%}")
    
    print(f"\n📊 提取的关键信息:")
    print(f"  • 类型: 科幻电影")
    print(f"  • 评分要求: 豆瓣8分以上")
    print(f"  • 时间范围: 2020年以后")
    print(f"  • 导演偏好: 诺兰")
    print(f"  • 附加需求: 排片情况")
    
    params = extractor.to_params(result)
    print(f"\n⚙️  生成的执行参数:")
    for key, value in list(params.items())[:6]:
        print(f"  • {key}: {value}")
    
    print(f"\n🎯 执行计划:")
    print(f"  1. 🔍 搜索豆瓣高分科幻电影 (2020+, 评分≥8)")
    print(f"  2. 🎬 筛选诺兰导演作品")
    print(f"  3. 🎥 查询近期排片信息")
    print(f"  4. 📋 生成推荐列表（含评分、简介、排片）")


async def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("🚀 长文本关键词提取 - 实际应用场景演示")
    print("=" * 80)
    print("\n本演示展示如何从用户的长篇大论中提取关键信息并执行操作\n")
    
    # 运行所有场景
    await demo_scenario_1()
    await demo_scenario_2()
    await demo_scenario_3()
    await demo_scenario_4()
    
    print("\n\n" + "=" * 80)
    print("✨ 演示完成！")
    print("=" * 80)
    
    print("\n💡 核心优势总结:")
    print("  ✓ 自动识别长文本并启动增强处理")
    print("  ✓ 多层级关键词提取（TF-IDF + TextRank + LLM）")
    print("  ✓ 智能实体识别（人名/地点/时间/数字/URL/邮箱）")
    print("  ✓ 自动生成结构化执行参数")
    print("  ✓ 支持复杂多步骤工作流")
    print("  ✓ 高准确率的意图识别")
    
    print("\n📚 更多信息请查看:")
    print("  • LONG_TEXT_KEYWORD_EXTRACTION_GUIDE.md")
    print("  • test_keyword_extraction.py")


if __name__ == "__main__":
    asyncio.run(main())

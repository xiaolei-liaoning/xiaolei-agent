#!/usr/bin/env python3
"""测试智能结果总结器"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_result_summarizer():
    """测试智能结果总结器"""
    
    print("=" * 80)
    print("🧪 智能结果总结器测试")
    print("=" * 80)
    
    from core.result_summarizer import get_result_summarizer
    
    summarizer = get_result_summarizer()
    
    # 测试1: 天气数据总结
    print("\n📝 测试1: 天气数据总结")
    print("-" * 80)
    
    weather_result = {
        "success": True,
        "result": {
            "city": "北京",
            "temperature": "25°C",
            "condition": "晴朗",
            "humidity": "45%",
            "wind": "北风 3级"
        }
    }
    
    reply = await summarizer.summarize("weather", weather_result, "查北京天气")
    print(f"用户消息: 查北京天气")
    print(f"AI回复:\n{reply}\n")
    
    # 测试2: 爬虫数据总结
    print("\n📝 测试2: 爬虫数据总结")
    print("-" * 80)
    
    scraper_result = {
        "success": True,
        "result": {
            "site": "微博",
            "items": [
                {"title": "#某明星官宣#", "views": "500万"},
                {"title": "#新技术发布#", "views": "300万"},
                {"title": "#社会新闻#", "views": "200万"},
                {"title": "#体育赛事#", "views": "150万"},
                {"title": "#娱乐八卦#", "views": "100万"}
            ]
        }
    }
    
    reply = await summarizer.summarize("web_scraper", scraper_result, "爬取微博热搜")
    print(f"用户消息: 爬取微博热搜")
    print(f"AI回复:\n{reply}\n")
    
    # 测试3: 文件路径回复
    print("\n📝 测试3: 文件路径回复（只告知位置）")
    print("-" * 80)
    
    file_result = {
        "success": True,
        "result": "/Users/leiyuxuan/Desktop/report.pdf"
    }
    
    reply = await summarizer.summarize("text_analyzer", file_result, "生成PDF报告")
    print(f"用户消息: 生成PDF报告")
    print(f"AI回复:\n{reply}\n")
    
    # 测试4: 文本内容回复（只告知位置）
    print("\n📝 测试4: 文本内容回复（只告知位置）")
    print("-" * 80)
    
    text_result = {
        "success": True,
        "result": "这是一份详细的分析报告文档，包含了数据分析、趋势预测和建议..."
    }
    
    reply = await summarizer.summarize("summarizer", text_result, "生成分析报告")
    print(f"用户消息: 生成分析报告")
    print(f"AI回复:\n{reply}\n")
    
    # 测试5: 列表数据总结
    print("\n📝 测试5: 列表数据总结")
    print("-" * 80)
    
    list_result = {
        "success": True,
        "result": [
            {"name": "产品A", "sales": 1000},
            {"name": "产品B", "sales": 800},
            {"name": "产品C", "sales": 600}
        ]
    }
    
    reply = await summarizer.summarize("data_analysis", list_result, "分析销售数据")
    print(f"用户消息: 分析销售数据")
    print(f"AI回复:\n{reply}\n")
    
    # 测试6: 失败情况
    print("\n📝 测试6: 失败情况处理")
    print("-" * 80)
    
    error_result = {
        "success": False,
        "error": "API调用失败"
    }
    
    reply = await summarizer.summarize("weather", error_result, "查上海天气")
    print(f"用户消息: 查上海天气")
    print(f"AI回复:\n{reply}\n")
    
    print("\n" + "=" * 80)
    print("✅ 所有测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_result_summarizer())

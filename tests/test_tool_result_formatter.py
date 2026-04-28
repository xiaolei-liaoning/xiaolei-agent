"""工具调用结果格式化器测试

测试ToolResultFormatter的各种场景，包括：
1. 文件处理工具
2. 数据查询工具
3. API调用工具
4. 失败场景
5. 带/不带自检的对比
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.tool_result_formatter import ToolResultFormatter, get_tool_result_formatter


def print_separator(title: str):
    """打印分隔线"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


async def test_file_processing():
    """测试1: 文件处理工具"""
    print_separator("测试1: PDF文件处理")
    
    formatter = ToolResultFormatter(enable_self_check=True)
    
    # 模拟文件处理工具的返回结果
    tool_result = {
        "tool_name": "pdf_processor",
        "success": True,
        "result": {
            "processed_files": 5,
            "output_path": "/Users/test/Desktop/merged_output.pdf",
            "total_pages": 120,
            "file_size_mb": 15.3
        },
        "execution_time": 3.5,
        "timestamp": datetime.now().isoformat()
    }
    
    user_query = "帮我把这5个PDF文件合并成一个"
    
    print(f"\n用户请求: {user_query}")
    print(f"工具: {tool_result['tool_name']}")
    
    # 生成回复
    response = await formatter.format_response(
        user_query=user_query,
        tool_result=tool_result
    )
    
    # 显示结果
    print(f"\n{response.full_reply}")
    print(f"\n--- 结构化信息 ---")
    print(f"概述: {response.overview}")
    print(f"耗时: {response.execution_time}秒")
    print(f"文件位置: {response.file_location}")
    print(f"完成时间: {response.completion_time}")
    print(f"质量评分: {response.quality_score}/100")


async def test_data_query():
    """测试2: 数据查询工具"""
    print_separator("测试2: 天气数据查询")
    
    formatter = ToolResultFormatter(enable_self_check=True)
    
    tool_result = {
        "tool_name": "weather_api",
        "success": True,
        "result": {
            "city": "北京",
            "temperature": 25,
            "humidity": 60,
            "condition": "晴",
            "forecast": ["明天晴", "后天多云"]
        },
        "execution_time": 1.2,
        "timestamp": datetime.now().isoformat()
    }
    
    user_query = "查询北京今天的天气"
    
    print(f"\n用户请求: {user_query}")
    
    response = await formatter.format_response(
        user_query=user_query,
        tool_result=tool_result
    )
    
    print(f"\n{response.full_reply}")


async def test_api_call():
    """测试3: API调用工具"""
    print_separator("测试3: GitHub API调用")
    
    formatter = ToolResultFormatter(enable_self_check=False)  # 关闭自检加快速度
    
    tool_result = {
        "tool_name": "github_api",
        "success": True,
        "result": {
            "repo_name": "awesome-project",
            "stars": 1234,
            "forks": 567,
            "issues_open": 23,
            "last_commit": "2小时前"
        },
        "execution_time": 0.8,
        "timestamp": datetime.now().isoformat()
    }
    
    user_query = "查看awesome-project项目的统计信息"
    
    print(f"\n用户请求: {user_query}")
    
    response = await formatter.format_response(
        user_query=user_query,
        tool_result=tool_result
    )
    
    print(f"\n{response.full_reply}")


async def test_failure_case():
    """测试4: 工具执行失败"""
    print_separator("测试4: 工具执行失败场景")
    
    formatter = ToolResultFormatter(enable_self_check=True)
    
    tool_result = {
        "tool_name": "file_converter",
        "success": False,
        "error": "文件格式不支持：.xyz格式无法转换",
        "result": {},
        "execution_time": 0.3,
        "timestamp": datetime.now().isoformat()
    }
    
    user_query = "把这个.xyz文件转换成PDF"
    
    print(f"\n用户请求: {user_query}")
    print(f"错误: {tool_result['error']}")
    
    response = await formatter.format_response(
        user_query=user_query,
        tool_result=tool_result
    )
    
    print(f"\n{response.full_reply}")


async def test_multiple_files():
    """测试5: 多文件处理"""
    print_separator("测试5: 批量图片处理")
    
    formatter = ToolResultFormatter(enable_self_check=True)
    
    tool_result = {
        "tool_name": "image_processor",
        "success": True,
        "result": {
            "files": [
                {"path": "/Users/test/Desktop/photo1_resized.jpg", "size": "1920x1080"},
                {"path": "/Users/test/Desktop/photo2_resized.jpg", "size": "1920x1080"},
                {"path": "/Users/test/Desktop/photo3_resized.jpg", "size": "1920x1080"}
            ],
            "total_processed": 3,
            "operation": "resize"
        },
        "execution_time": 5.2,
        "timestamp": datetime.now().isoformat()
    }
    
    user_query = "把这3张图片都调整成1920x1080分辨率"
    
    print(f"\n用户请求: {user_query}")
    
    response = await formatter.format_response(
        user_query=user_query,
        tool_result=tool_result
    )
    
    print(f"\n{response.full_reply}")


async def test_comparison():
    """测试6: 有自检 vs 无自检的性能对比"""
    print_separator("测试6: 自检性能对比")
    
    import time
    
    tool_result = {
        "tool_name": "data_analyzer",
        "success": True,
        "result": {"records": 1000, "avg_value": 42.5},
        "execution_time": 2.0,
        "timestamp": datetime.now().isoformat()
    }
    
    user_query = "分析这份数据报告"
    
    # 无自检
    formatter_no_check = ToolResultFormatter(enable_self_check=False)
    start = time.time()
    response_no_check = await formatter_no_check.format_response(
        user_query=user_query,
        tool_result=tool_result
    )
    time_no_check = time.time() - start
    
    # 有自检
    formatter_with_check = ToolResultFormatter(enable_self_check=True)
    start = time.time()
    response_with_check = await formatter_with_check.format_response(
        user_query=user_query,
        tool_result=tool_result
    )
    time_with_check = time.time() - start
    
    print(f"\n无自检:")
    print(f"  耗时: {time_no_check:.2f}秒")
    print(f"  质量评分: 未检测")
    print(f"  回复长度: {len(response_no_check.full_reply)}字符")
    
    print(f"\n有自检:")
    print(f"  耗时: {time_with_check:.2f}秒")
    print(f"  质量评分: {response_with_check.quality_score}/100")
    print(f"  回复长度: {len(response_with_check.full_reply)}字符")
    
    print(f"\n性能对比:")
    print(f"  时间增加: {(time_with_check/time_no_check - 1) * 100:.1f}%")
    print(f"  质量提升: 从未知到 {response_with_check.quality_score}分")


async def main():
    """运行所有测试"""
    print("\n" + "#"*70)
    print("# 工具调用结果格式化器 - 完整测试")
    print("#"*70)
    
    try:
        await test_file_processing()
        await test_data_query()
        await test_api_call()
        await test_failure_case()
        await test_multiple_files()
        await test_comparison()
        
        print("\n" + "#"*70)
        print("# 所有测试完成！")
        print("#"*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ 测试出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""CLI测试工具 - 交互式测试Agent功能"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class CLITester:
    """CLI测试类"""
    
    def __init__(self):
        self.dispatcher = None
        self.clarification_service = None
        self.initialize()
    
    def initialize(self):
        """初始化技能分发器和反问服务"""
        try:
            from core.engine.skill_dispatcher import get_skill_dispatcher
            self.dispatcher = get_skill_dispatcher()
            print("✓ 技能分发器初始化成功")
        except Exception as e:
            print(f"✗ 技能分发器初始化失败: {e}")
        
        try:
            from core.services.clarification_service import get_clarification_service
            self.clarification_service = get_clarification_service()
            print("✓ 独立反问服务初始化成功")
        except Exception as e:
            print(f"✗ 反问服务初始化失败: {e}")
        
        if not self.dispatcher and not self.clarification_service:
            print("✗ 没有可用的服务，退出")
            sys.exit(1)
    
    async def run_interactive_mode(self):
        """运行交互式模式"""
        print("\n" + "="*60)
        print("小龙虾Agent CLI测试工具")
        print("="*60)
        print("输入 'help' 查看帮助")
        print("输入 'quit' 或 'exit' 退出")
        print("-"*60)
        
        while True:
            try:
                user_input = input("\n> ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("感谢使用，再见！")
                    break
                
                if user_input.lower() == 'help':
                    self.show_help()
                    continue
                
                if user_input.lower() == 'skills':
                    self.list_skills()
                    continue
                
                if user_input.lower() == 'test':
                    await self.run_quick_tests()
                    continue
                
                if user_input.lower() == 'clarify':
                    await self.test_clarification()
                    continue
                
                # 处理用户输入
                await self.process_input(user_input)
            
            except KeyboardInterrupt:
                print("\n感谢使用，再见！")
                break
            except Exception as e:
                print(f"错误: {e}")
    
    def show_help(self):
        """显示帮助信息"""
        help_text = """
命令列表:
  help          - 显示此帮助信息
  quit/exit/q   - 退出CLI
  skills        - 列出所有可用技能
  test          - 运行快速测试
  其他输入      - 发送消息给Agent

技能示例:
  日常对话: 你好、谢谢、再见、你是谁
  翻译: 翻译这段英文、中文翻译成英文
  天气: 北京天气、上海气温
  数据分析: 分析数据、生成图表
  系统工具: 现在几点、检查内存
  GUI自动化: 打开浏览器、截图
  Web爬取: 微博热搜、抖音热榜
  MCP检查: 检查MCP服务器
  Fallback: 计算1到100的和
"""
        print(help_text)
    
    def list_skills(self):
        """列出所有可用技能"""
        print("\n可用技能列表:")
        print("-"*40)
        
        skills_info = [
            ("chat", "日常对话", "问候、闲聊、自我介绍"),
            ("translator", "翻译", "中英日韩等语言翻译"),
            ("weather", "天气查询", "查询城市天气"),
            ("data_analysis", "数据分析", "数据分析、图表生成"),
            ("system_toolbox", "系统工具", "时间、内存、CPU查询"),
            ("gui_automation", "GUI自动化", "打开应用、截图、音量控制"),
            ("web_scraper", "网页爬取", "热搜、热榜数据抓取"),
            ("text_analyzer", "文本分析", "总结、摘要、情感分析"),
            ("deep_thinking", "深度思考", "复杂问题推理分析"),
            ("rag_search", "知识搜索", "概念解释、知识问答"),
            ("mcp_check", "MCP检查", "检查MCP服务器状态"),
            ("multi_step", "多步骤任务", "执行多步骤任务"),
        ]
        
        for skill_name, category, desc in skills_info:
            print(f"  {skill_name:<15} - {category}: {desc}")
    
    async def run_quick_tests(self):
        """运行快速测试"""
        print("\n运行快速测试...")
        
        test_cases = [
            ("你好", "日常对话测试"),
            ("翻译这段英文", "翻译测试"),
            ("北京天气", "天气测试"),
            ("分析数据", "数据分析测试"),
            ("现在几点", "系统工具测试"),
            ("检查MCP服务器", "MCP检查测试"),
            ("计算1到100的和", "Fallback测试"),
        ]
        
        for msg, desc in test_cases:
            print(f"\n测试: {desc}")
            print(f"  输入: {msg}")
            await self.process_input(msg, quiet=True)
    
    async def process_input(self, user_input, quiet=False):
        """处理用户输入"""
        if not quiet:
            print(f"\n正在处理: '{user_input}'")
        
        # 1. 检测否定模式
        negation_patterns = ["不要", "不想要", "不是", "不想", "不要用", "别用", "排除"]
        has_negation = any(pattern in user_input for pattern in negation_patterns)
        
        if has_negation:
            processed = user_input
            for pattern in negation_patterns:
                idx = user_input.find(pattern)
                if idx != -1:
                    remaining = user_input[idx + len(pattern):].strip()
                    if "，" in remaining:
                        parts = remaining.split("，", 1)
                        if len(parts) > 1 and len(parts[0]) <= 4:
                            processed = parts[1].strip()
                        else:
                            processed = remaining
                    else:
                        processed = remaining
                    break
            if not quiet:
                print(f"  否定处理后: '{processed}'")
        else:
            processed = user_input
        
        # 2. 意图识别（模糊匹配）
        skill = self.dispatcher._fuzzy_skill_match(processed, processed)
        
        if not quiet:
            print(f"  识别技能: {skill or '未识别'}")
        
        # 3. 反问检测（使用独立反问服务）
        from core.services.clarification_service import get_clarification_service
        cs = get_clarification_service()
        questions = cs.generate_questions(user_input)

        if questions:
            if not quiet:
                print(f"  需要反问:")
                for q in questions:
                    print(f"    - {q.question}")
                    if q.options:
                        print(f"      选项: {', '.join(opt.label for opt in q.options)}")
        else:
            if not quiet:
                print(f"  无需反问")
        cs.reset()
        
        # 4. 如果是简单任务，执行沙盒测试
        if skill is None or skill == 'chat':
            # 尝试使用Fallback机制
            req_type = self.dispatcher._analyze_requirement_type(user_input)
            if not quiet:
                print(f"  需求类型分析: {req_type.split('\\n')[0]}")
            
            # 简单计算测试
            if "计算" in user_input or "求和" in user_input:
                test_code = '''
def solve_problem(message: str) -> dict:
    try:
        import re
        nums = re.findall(r'\\d+', message)
        if len(nums) >= 2:
            start, end = int(nums[0]), int(nums[-1])
            result = sum(range(start, end+1))
            return {"success": True, "result": result, "message": "计算{}到{}的和".format(start, end)}
        else:
            return {"success": False, "result": None, "error": "未找到数字范围"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
'''
                result = await self.dispatcher._execute_in_sandbox(test_code, message=user_input)
                if not quiet:
                    if result.get("success"):
                        print(f"  沙盒执行结果: {result['result']}")
                    else:
                        print(f"  沙盒执行失败: {result.get('error')}")
        
        if not quiet:
            print("  处理完成")
    
    async def test_clarification(self):
        """测试反问服务功能"""
        print("\n=== 反问服务测试 ===")
        
        if not self.clarification_service:
            print("✗ 反问服务未初始化")
            return
        
        test_cases = [
            "查询天气",
            "分析一下这个项目",
            "打开文件",
            "怎么办"
        ]
        
        for msg in test_cases:
            print(f"\n输入: '{msg}'")
            questions = self.clarification_service.generate_questions(msg)
            
            if questions:
                for q in questions:
                    print(f"  反问: {q.question}")
                    print(f"  标签: {q.header}")
                    print(f"  类型: {'多选' if q.question_type.value == 'multi_select' else '单选'}")
                    print(f"  选项:")
                    for opt in q.options:
                        print(f"    - {opt.label}")
                        if opt.description:
                            print(f"      ({opt.description})")
                        if opt.preview:
                            print(f"      预览:\n```\n{opt.preview}\n```")
            else:
                print(f"  无需反问")
        
        # 测试错误场景
        print("\n=== 错误场景测试 ===")
        error_cases = [
            "网络连接超时",
            "权限不足",
            "工具不可用"
        ]
        
        for error in error_cases:
            print(f"\n错误: {error}")
            questions = self.clarification_service.generate_questions("", error_context=error)
            if questions:
                q = questions[0]
                print(f"  反问: {q.question}")
                print(f"  选项: {[opt.label for opt in q.options]}")
    
    async def run_command_mode(self, args):
        """运行命令模式"""
        if not args:
            print("请提供输入参数")
            return
        
        user_input = " ".join(args)
        print(f"处理命令: '{user_input}'")
        await self.process_input(user_input)

async def main():
    """主入口"""
    tester = CLITester()
    
    if len(sys.argv) > 1:
        # 命令模式
        await tester.run_command_mode(sys.argv[1:])
    else:
        # 交互模式
        await tester.run_interactive_mode()

if __name__ == "__main__":
    asyncio.run(main())
"""思考引擎模块 - 显示每一步思考过程

模拟Claude Code的思考过程显示，让用户了解AI正在做什么。

思考过程包括:
1. 意图分析 - 理解用户需求
2. 计划制定 - 规划执行步骤
3. 执行监控 - 跟踪每一步执行
4. 结果总结 - 汇总执行结果

示例输出:
  🤔 正在分析用户意图...
  📋 用户请求: 帮我爬取微博热搜
  🔍 识别到意图: 数据爬取
  💡 计划步骤:
    1. 调用爬虫模块爬取微博热搜
    2. 保存数据到CSV文件
    3. 生成词云分析报告
  
  🚀 开始执行...
  ────────────────────────────
  [步骤 1/3] 爬取微博热搜
    → 正在连接微博服务器...
    → 获取热搜数据成功
    → 共获取 50 条热搜
  
  [步骤 2/3] 保存数据
    → 正在写入文件...
    → 文件保存成功: /output/weibo_hot.csv
  
  [步骤 3/3] 生成报告
    → 正在生成词云...
    → 报告生成成功: /output/report.html
  
  ✅ 任务完成！
"""

import time
from typing import List, Dict, Any, Optional
from enum import Enum
from cli.colors import CliColors, print_color
from cli.ui_components import ProgressBar


class ThinkingState(Enum):
    """思考状态枚举"""
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    SUMMARIZING = "summarizing"


class ThinkingStep:
    """思考步骤对象"""
    
    def __init__(self, step_num: int, title: str, description: str = ""):
        self.step_num = step_num
        self.title = title
        self.description = description
        self.status = "pending"  # pending, running, completed, failed
        self.start_time = None
        self.end_time = None
        self.duration = 0
        self.messages: List[str] = []
    
    def start(self):
        """开始执行此步骤"""
        self.status = "running"
        self.start_time = time.time()
    
    def add_message(self, message: str):
        """添加执行消息"""
        self.messages.append(message)
    
    def complete(self):
        """标记步骤完成"""
        self.status = "completed"
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
    
    def fail(self):
        """标记步骤失败"""
        self.status = "failed"
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time


class ThinkingEngine:
    """思考引擎 - 管理和显示思考过程"""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.current_state = ThinkingState.ANALYZING
        self.steps: List[ThinkingStep] = []
        self.user_request = ""
        self.intent = ""
        self.start_time = None
        self.total_duration = 0
    
    def set_enabled(self, enabled: bool):
        """设置是否启用思考显示"""
        self.enabled = enabled
    
    def is_enabled(self) -> bool:
        """检查是否启用思考显示"""
        return self.enabled
    
    def start_task(self, user_request: str):
        """开始新任务"""
        self.user_request = user_request
        self.start_time = time.time()
        self.steps = []
        self.current_state = ThinkingState.ANALYZING
        
        if self.enabled:
            print()
            print_color("─────────────────────────────────────────────────────", CliColors.GRAY)
            print_color("🤔 正在分析用户意图...", CliColors.YELLOW)
            print_color(f"📋 用户请求: {user_request}", CliColors.WHITE)
    
    def analyze_intent(self, intent: str, confidence: float = 1.0):
        """分析意图"""
        self.intent = intent
        self.current_state = ThinkingState.PLANNING
        
        if self.enabled:
            print_color(f"🔍 识别到意图: {intent}", CliColors.CYAN)
            if confidence < 1.0:
                print_color(f"   置信度: {confidence:.2%}", CliColors.YELLOW)
    
    def plan_steps(self, steps: List[Dict[str, str]]):
        """规划执行步骤"""
        if self.enabled:
            print_color("💡 计划步骤:", CliColors.BOLD)
        
        for i, step_data in enumerate(steps, 1):
            step = ThinkingStep(
                step_num=i,
                title=step_data.get("title", f"步骤 {i}"),
                description=step_data.get("description", "")
            )
            self.steps.append(step)
            
            if self.enabled:
                desc = f" - {step.description}" if step.description else ""
                print_color(f"    {i}. {step.title}{desc}", CliColors.WHITE)
        
        if self.enabled:
            print()
            print_color("🚀 开始执行...", CliColors.GREEN)
            print_color("─────────────────────────────────────────────────────", CliColors.GRAY)
            print()
    
    def display_progress(self):
        """显示执行进度条"""
        if not self.enabled or not self.steps:
            return
        
        completed = sum(1 for s in self.steps if s.status == "completed")
        total = len(self.steps)
        
        progress_bar = ProgressBar(total=total, width=40)
        progress_bar.update(completed)
    
    def start_step(self, step_num: int):
        """开始执行指定步骤"""
        if step_num <= len(self.steps):
            step = self.steps[step_num - 1]
            step.start()
            self.current_state = ThinkingState.EXECUTING
            
            if self.enabled:
                print()
                print_color(f"[步骤 {step_num}/{len(self.steps)}] {step.title}", CliColors.BRIGHT_BLUE + CliColors.BOLD)
    
    def log_step_message(self, message: str, indent: int = 1):
        """记录步骤执行消息"""
        if self.enabled:
            prefix = "    " * indent
            print_color(f"{prefix}→ {message}", CliColors.GRAY)
    
    def complete_step(self, step_num: int, success: bool = True, error_message: str = ""):
        """完成指定步骤"""
        if step_num <= len(self.steps):
            step = self.steps[step_num - 1]
            if success:
                step.complete()
                if self.enabled:
                    print_color(f"    ✅ 完成 ({step.duration:.2f}s)", CliColors.GREEN)
                    self.display_progress()
            else:
                step.fail()
                if self.enabled:
                    print_color(f"    ❌ 失败: {error_message}", CliColors.RED)
    
    def add_step_data(self, step_num: int, data_type: str, data: str):
        """添加步骤输出数据"""
        if self.enabled:
            print_color(f"    📊 {data_type}: {data}", CliColors.CYAN)
    
    def summarize(self, success: bool, result: Dict[str, Any] = None):
        """总结任务结果"""
        self.current_state = ThinkingState.SUMMARIZING
        self.total_duration = time.time() - self.start_time
        
        if self.enabled:
            print()
            print_color("─────────────────────────────────────────────────────", CliColors.GRAY)
            
            if success:
                print_color("✅ 任务完成！", CliColors.GREEN + CliColors.BOLD)
            else:
                print_color("❌ 任务失败", CliColors.RED + CliColors.BOLD)
            
            print_color(f"⏱️  总耗时: {self.total_duration:.2f}秒", CliColors.WHITE)
            
            if result:
                if result.get("report_path"):
                    print_color(f"📄 报告: {result['report_path']}", CliColors.CYAN)
                if result.get("success_count") is not None:
                    print_color(f"📊 成功: {result['success_count']}/{len(self.steps)}", CliColors.GREEN)
            
            print_color("─────────────────────────────────────────────────────", CliColors.GRAY)
            print()
    
    def get_step_status(self, step_num: int) -> str:
        """获取步骤状态"""
        if step_num <= len(self.steps):
            return self.steps[step_num - 1].status
        return "unknown"
    
    def get_summary(self) -> Dict[str, Any]:
        """获取任务摘要"""
        return {
            "user_request": self.user_request,
            "intent": self.intent,
            "total_duration": self.total_duration,
            "steps": [{
                "num": s.step_num,
                "title": s.title,
                "status": s.status,
                "duration": s.duration
            } for s in self.steps]
        }


# 全局思考引擎实例
_global_thinking_engine = ThinkingEngine()


def get_thinking_engine() -> ThinkingEngine:
    """获取全局思考引擎实例"""
    return _global_thinking_engine


# 便捷函数
def think_start(user_request: str):
    """开始思考"""
    _global_thinking_engine.start_task(user_request)


def think_analyze(intent: str, confidence: float = 1.0):
    """分析意图"""
    _global_thinking_engine.analyze_intent(intent, confidence)


def think_plan(steps: List[Dict[str, str]]):
    """规划步骤"""
    _global_thinking_engine.plan_steps(steps)


def think_step(step_num: int):
    """开始步骤"""
    _global_thinking_engine.start_step(step_num)


def think_log(message: str, indent: int = 1):
    """记录日志"""
    _global_thinking_engine.log_step_message(message, indent)


def think_complete(step_num: int, success: bool = True, error: str = ""):
    """完成步骤"""
    _global_thinking_engine.complete_step(step_num, success, error)


def think_data(data_type: str, data: str):
    """添加数据"""
    current_step = None
    for step in _global_thinking_engine.steps:
        if step.status == "running":
            current_step = step
            break
    if current_step:
        _global_thinking_engine.add_step_data(current_step.step_num, data_type, data)


def think_summarize(success: bool, result: Dict[str, Any] = None):
    """总结"""
    _global_thinking_engine.summarize(success, result)


def set_thinking_enabled(enabled: bool):
    """设置思考模式"""
    _global_thinking_engine.set_enabled(enabled)

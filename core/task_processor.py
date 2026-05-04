"""统一任务处理器（简化版）

合并功能：
- 规则匹配（快速）
- 复杂度判断（可选）
- AI 分解（兜底）

使用方式：
    from core.task_processor import task_processor
    result = await task_processor.process("爬取微博热搜并分析")
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from .llm_backend import get_llm_router

logger = logging.getLogger(__name__)


class TaskPath(Enum):
    """任务处理路径"""
    RULE = "rule"
    AI = "ai"


@dataclass
class SubTask:
    """子任务"""
    id: str
    action: str
    params: Dict[str, Any]
    dependencies: List[str]
    priority: int = 5  # 优先级（1-10，数字越大优先级越高）


@dataclass
class TaskResult:
    """处理结果"""
    path: TaskPath
    subtasks: List[SubTask]
    success: bool


class TaskProcessor:
    """统一任务处理器
    
    特性：
    - 规则匹配（快速）
    - AI 分解（兜底）
    """
    
    def __init__(self):
        self.router = get_llm_router()
        logger.info("TaskProcessor 初始化完成")
    
    async def process(self, task: str) -> TaskResult:
        """处理任务
        
        策略：
        1. 先规则匹配（快速）
        2. 失败则 AI 分解（兜底）
        
        Args:
            task: 用户任务
            
        Returns:
            处理结果
        """
        logger.info("处理任务: %s", task[:50])
        
        try:
            async with asyncio.timeout(10):
                # 1. 规则匹配
                rule_result = self._try_rule(task)
                if rule_result:
                    logger.info("规则匹配成功")
                    return rule_result
                
                # 2. AI 分解
                logger.info("规则失败，使用 AI")
                return await self._try_ai(task)
        except asyncio.TimeoutError:
            logger.warning("处理超时")
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "chat", {"message": task}, [])],
                success=False,
            )
    
    def _try_rule(self, task: str) -> Optional[TaskResult]:
        """规则匹配

        全面覆盖简单任务，先尝试规则匹配，匹配不到再尝试AI分解
        """
        task_lower = task.lower()
        task_stripped = task.strip()

        # ========== 天气相关 ==========
        weather_keywords = ["天气", "气温", "温度", "下雨", "下雪", "刮风", "晴天", "阴天", "台风", "雷雨", "暴雨", "大风"]
        if any(kw in task for kw in weather_keywords):
            city = self._extract_city(task) or "北京"
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "weather", {"city": city}, [])],
                success=True,
            )

        # ========== 热搜/爬虫相关 ==========
        if any(kw in task for kw in ["热搜", "热榜", "趋势", "trending"]):
            site_map = {
                "微博": ("web_scraper", {"site_name": "微博", "action": "热搜"}),
                "百度": ("web_scraper", {"site_name": "百度", "action": "热搜"}),
                "知乎": ("web_scraper", {"site_name": "知乎", "action": "热搜"}),
                "抖音": ("web_scraper", {"site_name": "抖音", "action": "热搜"}),
                "B站": ("web_scraper", {"site_name": "B站", "action": "热搜"}),
                "bilibili": ("web_scraper", {"site_name": "B站", "action": "热搜"}),
                "github": ("web_scraper", {"site_name": "GitHub", "action": "trending"}),
            }
            for site, (action, params) in site_map.items():
                if site in task:
                    return TaskResult(
                        path=TaskPath.RULE,
                        subtasks=[SubTask("task_1", action, params, [])],
                        success=True,
                    )
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "web_scraper", {"site_name": "微博", "action": "热搜"}, [])],
                success=True,
            )

        # ========== 爬取/抓取 ==========
        if any(kw in task for kw in ["爬取", "抓取", "scrape", "crawl"]):
            if "知乎" in task:
                return TaskResult(
                    path=TaskPath.RULE,
                    subtasks=[SubTask("task_1", "web_scraper", {"site_name": "知乎", "action": "搜索"}, [])],
                    success=True,
                )
            if "微博" in task:
                return TaskResult(
                    path=TaskPath.RULE,
                    subtasks=[SubTask("task_1", "web_scraper", {"site_name": "微博", "action": "热搜"}, [])],
                    success=True,
                )
            if "百度" in task:
                return TaskResult(
                    path=TaskPath.RULE,
                    subtasks=[SubTask("task_1", "web_scraper", {"site_name": "百度", "action": "热搜"}, [])],
                    success=True,
                )

        # ========== 翻译相关 ==========
        if any(kw in task for kw in ["翻译", "translate", "译成", "译为", "英文", "日文", "韩文", "法文", "德文"]):
            target_lang = "en"
            if "日文" in task or "日语" in task:
                target_lang = "ja"
            elif "韩文" in task or "韩语" in task:
                target_lang = "ko"
            elif "法文" in task or "法语" in task:
                target_lang = "fr"
            elif "德文" in task or "德语" in task:
                target_lang = "de"
            elif "中文" in task and ("英" in task or "英文" in task):
                target_lang = "zh"
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "translator", {"target_lang": target_lang}, [])],
                success=True,
            )

        # ========== GUI 自动化 - 应用启动 ==========
        app_keywords = {
            "微信": ("gui_automation", {"action": "open", "application": "WeChat"}),
            "wechat": ("gui_automation", {"action": "open", "application": "WeChat"}),
            "qq": ("gui_automation", {"action": "open", "application": "QQ"}),
            "钉钉": ("gui_automation", {"action": "open", "application": "DingTalk"}),
            "飞书": ("gui_automation", {"action": "open", "application": "Feishu"}),
            "邮箱": ("gui_automation", {"action": "open", "application": "Mail"}),
            "邮件": ("gui_automation", {"action": "open", "application": "Mail"}),
            "日历": ("gui_automation", {"action": "open", "application": "Calendar"}),
            "计算器": ("gui_automation", {"action": "open", "application": "Calculator"}),
            "备忘录": ("gui_automation", {"action": "open", "application": "Notes"}),
            "浏览器": ("gui_automation", {"action": "open", "application": "Safari"}),
            "chrome": ("gui_automation", {"action": "open", "application": "Chrome"}),
            "safari": ("gui_automation", {"action": "open", "application": "Safari"}),
            "finder": ("gui_automation", {"action": "open", "application": "Finder"}),
            "finder": ("gui_automation", {"action": "open", "application": "Finder"}),
            "终端": ("gui_automation", {"action": "open", "application": "Terminal"}),
            "vscode": ("gui_automation", {"action": "open", "application": "Visual Studio Code"}),
            "微信": ("gui_automation", {"action": "open", "application": "WeChat"}),
        }
        for kw, (action, params) in app_keywords.items():
            if kw in task:
                return TaskResult(
                    path=TaskPath.RULE,
                    subtasks=[SubTask("task_1", action, params, [])],
                    success=True,
                )

        # ========== 打开/运行/启动 ==========
        if any(kw in task_lower for kw in ["打开", "启动", "运行", "open", "launch", "start"]):
            app = self._extract_app_name(task)
            if app:
                return TaskResult(
                    path=TaskPath.RULE,
                    subtasks=[SubTask("task_1", "gui_automation", {"action": "open", "application": app}, [])],
                    success=True,
                )

        # ========== 关闭/退出 ==========
        if any(kw in task_lower for kw in ["关闭", "退出", "quit", "exit", "close"]):
            app = self._extract_app_name(task)
            if app:
                return TaskResult(
                    path=TaskPath.RULE,
                    subtasks=[SubTask("task_1", "gui_automation", {"action": "close", "application": app}, [])],
                    success=True,
                )

        # ========== 系统工具 ==========
        if any(kw in task for kw in ["当前时间", "现在几点", "系统时间", "几点"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "system_toolbox", {"action": "get_time"}, [])],
                success=True,
            )
        if any(kw in task for kw in ["磁盘空间", "硬盘使用", "内存", "cpu"]):
            action = "get_memory" if "内存" in task else "get_disk"
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "system_toolbox", {"action": action}, [])],
                success=True,
            )

        # ========== 搜索/查询 ==========
        if any(kw in task for kw in ["搜索", "查询", "查一下", "搜一下", "search", "lookup"]):
            query = task.replace("搜索", "").replace("查询", "").replace("查一下", "").replace("搜一下", "").strip()
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "rag_search", {"query": query}, [])],
                success=True,
            )

        # ========== 数据分析 ==========
        if any(kw in task for kw in ["数据分析", "统计", "图表", "可视化", "chart", "analyze"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "data_analysis", {"action": "analyze"}, [])],
                success=True,
            )

        # ========== 深度思考 ==========
        if any(kw in task for kw in ["深度思考", "深入分析", "详细分析", "研究", "最新"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "deep_thinking", {"message": task}, [])],
                success=True,
            )

        # ========== 文本分析/总结 ==========
        if any(kw in task for kw in ["总结", "摘要", "概括", "提炼", "summarize", "summary"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "text_analyzer", {"action": "summarize"}, [])],
                success=True,
            )

        # ========== 截图/录屏 ==========
        if any(kw in task for kw in ["截图", "截屏", "screenshot"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "gui_automation", {"action": "screenshot"}, [])],
                success=True,
            )
        if any(kw in task for kw in ["录屏", "screen recording"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "gui_automation", {"action": "screen_record"}, [])],
                success=True,
            )

        # ========== 计算/数学 ==========
        if any(kw in task for kw in ["计算", "算一下", "等于多少", "加起来", "加", "减", "乘", "除", "+", "-", "*", "/"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "calculator", {"expression": task}, [])],
                success=True,
            )

        # ========== 代码执行 ==========
        if any(kw in task for kw in ["运行代码", "执行代码", "跑代码", "run code", "execute code"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "code_sandbox", {"language": "python"}, [])],
                success=True,
            )

        # ========== 待办事项 ==========
        if any(kw in task for kw in ["待办", "todo", "任务列表", "日程"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "advanced_automation", {"action": "todo"}, [])],
                success=True,
            )

        # ========== 问候/闲聊 ==========
        greetings = ["你好", "嗨", "hello", "hi", "您好", "早上好", "晚上好", "晚安"]
        if any(g in task for g in greetings):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "chat", {"message": task}, [])],
                success=True,
            )
        if any(kw in task for kw in ["谢谢", "感谢", "thx", "thanks"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "chat", {"message": "不客气！"}, [])],
                success=True,
            )
        if any(kw in task for kw in ["你是谁", "介绍一下", "什么身份"]):
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "chat", {"message": task}, [])],
                success=True,
            )

        # ========== 检查是否是复杂任务 ==========
        # 只有规则匹配不到时，才检查是否是复杂任务，返回 None 让 AI 处理
        complex_indicators = [
            "并", "然后", "接着", "再", "最后", "之后", "后", "同时",
            "并且", "还有", "以及", "分析", "生成报告", "先...再",
            "首先", "第一步", "第二部", "第三步",
        ]
        if any(ind in task for ind in complex_indicators):
            return None

        return None

    def _extract_city(self, task: str) -> Optional[str]:
        """提取城市名"""
        cities = [
            "北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都",
            "重庆", "西安", "天津", "苏州", "长沙", "郑州", "东莞", "青岛",
            "沈阳", "宁波", "昆明", "大连", "厦门", "福州", "合肥", "济南",
            "温州", "长春", "哈尔滨", "石家庄", "南昌", "贵阳", "太原", "南宁",
            "海口", "兰州", "银川", "西宁", "乌鲁木齐", "呼和浩特", "拉萨",
            "香港", "澳门", "台北", "高雄",
        ]
        for city in cities:
            if city in task:
                return city
        return None

    def _extract_app_name(self, task: str) -> Optional[str]:
        """提取应用名称"""
        apps = [
            "微信", "WeChat", "QQ", "钉钉", "飞书", "Slack", "Telegram",
            "Safari", "Chrome", "Firefox", "Edge", "浏览器",
            "邮件", "Mail", "Outlook", "日历", "Calendar", "备忘录", "Notes",
            "计算器", "Calculator", "Finder", "终端", "Terminal",
            "VSCode", "Visual Studio Code", "Xcode", "PyCharm", "Idea",
            "Photoshop", "Illustrator", "Figma", "Sketch",
            "网易云音乐", "QQ音乐", "Spotify", "酷狗",
            "优酷", "爱奇艺", "腾讯视频", "B站", "Bilibili",
            "淘宝", "京东", "拼多多", "美团", "饿了么",
            "抖音", "快手", "小红书", "微博",
        ]
        for app in apps:
            if app.lower() in task.lower() or app in task:
                return app
        return None
    
    async def _try_ai(self, task: str) -> TaskResult:
        """AI 分解"""
        try:
            # 获取所有可用技能列表
            from core.skill_dispatcher import SkillDispatcher
            dispatcher = SkillDispatcher()
            
            available_skills = []
            for name, keywords, priority in dispatcher.skill_configs:
                available_skills.append(f"- {name}: 关键词={keywords[:3]}")
            
            skills_list = "\n".join(available_skills)
            
            prompt = f"""请将以下任务拆解为多个可执行的子任务。

任务：{task}

**重要约束**：只能使用以下已注册的技能名称（action字段必须严格匹配）：
{skills_list}

**分解原则**：
1. 保持任务的原子性，但不要过度分解
2. "写故事"应该是一个独立任务，不要拆分为"分析+打开编辑器+写入"
3. "搜索热搜"应该直接使用web_scraper或rag_search，不需要额外的分析步骤
4. 每个动作对应一个子任务，避免冗余

返回 JSON 格式（不要用代码块）：
{{
  "subtasks": [
    {{
      "id": "task_1",
      "action": "gui_automation",
      "params": {{"application": "QQ"}},
      "dependencies": []
    }},
    {{
      "id": "task_2",
      "action": "web_scraper",
      "params": {{"site_name": "百度", "action": "热搜"}},
      "dependencies": ["task_1"]
    }}
  ]
}}

注意：
1. 每个子任务都要有 id、action、params、dependencies
2. dependencies 表示依赖的前置任务ID列表
3. action字段必须从上面的可用技能列表中选择，不能自创技能名
4. **关键**: 子任务数量应与用户指令中的动作数量一致，不要额外添加中间步骤
5. 只返回JSON，不要其他内容"""
            
            logger.info("调用 AI 分解: %s", task[:50])
            response = await self.router.simple_chat(
                user_message=prompt,
                system_prompt="你是任务分解助手，只返回JSON格式，不要用代码块",
                temperature=0.7,
            )
            
            logger.info("AI 响应: %s", response[:200] if response else "空")
            
            if not response or not response.strip():
                raise ValueError("AI 返回空响应")
            
            # 处理可能的代码块
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            data = json.loads(response)
            subtasks = []
            
            for st in data.get("subtasks", []):
                subtask = SubTask(
                    id=st["id"],
                    action=st["action"],
                    params=st.get("params", {}),
                    dependencies=st.get("dependencies", []),
                )
                subtasks.append(subtask)
            
            logger.info("AI 分解成功: %d 个子任务", len(subtasks))
            return TaskResult(
                path=TaskPath.AI,
                subtasks=subtasks,
                success=True,
            )
        except Exception as e:
            logger.error("AI 分解失败: %s", e)
            return TaskResult(
                path=TaskPath.RULE,
                subtasks=[SubTask("task_1", "chat", {"message": task}, [])],
                success=False,
            )


# 全局实例
task_processor = TaskProcessor()
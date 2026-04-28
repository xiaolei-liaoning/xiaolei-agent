"""自然语言任务处理器 - 像WorkBuddy一样自然处理任务

特性：
- 智能意图识别
- 上下文理解
- 多轮对话支持
- 应用接口集成
- 任务链自动构建
- 长文本关键词提取
- 执行结果智能分析
"""

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

from .llm_backend import get_llm_router
from .app_interface import AppManager, AppType, get_app_manager
from .keyword_extractor import get_keyword_extractor, ExtractionResult
from .result_analyzer import get_result_analyzer, AnalysisResult

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """意图类型"""
    CHAT = "chat"  # 普通对话
    SKILL = "skill"  # 技能调用
    APP = "app"  # 应用操作
    WORKFLOW = "workflow"  # 工作流
    MULTI = "multi"  # 多任务


@dataclass
class Intent:
    """意图识别结果"""
    type: IntentType
    confidence: float  # 置信度 0-1
    target: str  # 目标（技能名、应用类型等）
    action: str  # 具体动作
    params: Dict[str, Any]  # 参数
    context: Dict[str, Any]  # 上下文信息


@dataclass
class TaskStep:
    """任务步骤"""
    step_id: int
    description: str
    intent: Intent
    dependencies: List[int]  # 依赖的步骤ID


@dataclass
class TaskChain:
    """任务链"""
    user_message: str
    steps: List[TaskStep]
    context: Dict[str, Any]


class NaturalLanguageProcessor:
    """自然语言任务处理器"""
    
    def __init__(self):
        self.router = get_llm_router()
        self.app_manager = get_app_manager()
        self.conversation_history: List[Dict[str, str]] = []
        self.context: Dict[str, Any] = {}
        logger.info("NaturalLanguageProcessor 初始化完成")
    
    async def process(self, message: str) -> TaskChain:
        """处理自然语言消息
        
        Args:
            message: 用户消息
            
        Returns:
            任务链
        """
        logger.info("处理消息: %s", message[:50])
        
        # 1. 添加到对话历史
        self.conversation_history.append({"role": "user", "content": message})
        
        # 2. 检测是否为长文本（超过100字符）
        is_long_text = len(message) > 100
        
        if is_long_text:
            logger.info("检测到长文本，启动关键词提取")
            # 2.1 提取关键词和实体
            extraction_result = await self._extract_keywords_from_long_text(message)
            
            # 2.2 基于提取结果增强意图识别
            intent = await self._recognize_intent_with_keywords(message, extraction_result)
        else:
            # 短文本：直接意图识别
            intent = await self._recognize_intent(message)
        
        logger.info("识别意图: %s, 置信度: %.2f", intent.type.value, intent.confidence)
        
        # 3. 构建任务链
        task_chain = await self._build_task_chain(message, intent)
        
        # 4. 更新上下文
        self._update_context(task_chain)
        
        return task_chain
    
    async def _extract_keywords_from_long_text(self, message: str) -> ExtractionResult:
        """从长文本中提取关键词
        
        Args:
            message: 用户消息
            
        Returns:
            提取结果
        """
        try:
            extractor = get_keyword_extractor()
            result = await extractor.extract(message)
            
            logger.info("关键词提取完成:")
            logger.info("  - 主要意图: %s", result.main_intent)
            logger.info("  - 动作词: %s", result.action_words)
            logger.info("  - 目标词: %s", result.target_words)
            logger.info("  - 地点: %s", result.entities.locations)
            logger.info("  - 时间: %s", result.entities.times)
            logger.info("  - 摘要: %s", result.summary)
            
            # 保存到上下文
            self.context["last_extraction"] = result
            
            return result
        except Exception as e:
            logger.error("关键词提取失败: %s", e)
            # 返回空结果，不影响后续流程
            from .keyword_extractor import ExtractionResult, ExtractedEntities
            return ExtractionResult(
                keywords=[],
                entities=ExtractedEntities([], [], [], [], [], [], []),
                main_intent="chat",
                action_words=[],
                target_words=[],
                summary=message[:100],
                confidence=0.3
            )
    
    async def _recognize_intent_with_keywords(self, message: str, 
                                             extraction: ExtractionResult) -> Intent:
        """基于关键词增强的意图识别
        
        Args:
            message: 原始消息
            extraction: 关键词提取结果
            
        Returns:
            意图
        """
        # 如果提取置信度高，直接使用提取的意图
        if extraction.confidence > 0.7 and extraction.main_intent != "chat":
            logger.info("使用关键词提取的意图: %s", extraction.main_intent)
            
            # 转换为Intent对象
            params = self._extraction_to_params(extraction)
            
            # 映射意图类型
            intent_type_map = {
                "query": IntentType.SKILL,
                "search": IntentType.SKILL,
                "scrape": IntentType.SKILL,
                "send": IntentType.APP,
                "create": IntentType.APP,
                "delete": IntentType.APP,
                "analyze": IntentType.SKILL,
                "translate": IntentType.SKILL,
                "play": IntentType.APP,
                "open": IntentType.APP,
                "close": IntentType.APP,
                "query_weather": IntentType.SKILL,
                "send_email": IntentType.APP,
                "send_wechat": IntentType.APP,
                "scrape_hot": IntentType.SKILL,
            }
            
            intent_type = intent_type_map.get(extraction.main_intent, IntentType.SKILL)
            
            # 确定目标和动作
            target = extraction.target_words[0] if extraction.target_words else ""
            action = extraction.action_words[0] if extraction.action_words else extraction.main_intent
            
            return Intent(
                type=intent_type,
                confidence=extraction.confidence,
                target=target or extraction.main_intent,
                action=action,
                params=params,
                context={"extraction": extraction, "method": "keyword_based"}
            )
        
        # 否则使用原有的意图识别方法
        logger.info("关键词提取置信度较低，使用传统意图识别")
        return await self._recognize_intent(message)
    
    def _extraction_to_params(self, extraction: ExtractionResult) -> Dict[str, Any]:
        """将提取结果转换为参数
        
        Args:
            extraction: 提取结果
            
        Returns:
            参数字典
        """
        params = {}
        
        # 添加实体信息
        if extraction.entities.locations:
            params["location"] = extraction.entities.locations[0]
        if extraction.entities.times:
            params["time"] = extraction.entities.times[0]
        if extraction.entities.numbers:
            params["count"] = extraction.entities.numbers[0]
        if extraction.entities.urls:
            params["url"] = extraction.entities.urls[0]
        if extraction.entities.emails:
            params["email"] = extraction.entities.emails[0]
        if extraction.entities.persons:
            params["person"] = extraction.entities.persons[0]
        
        # 添加关键词
        if extraction.action_words:
            params["action"] = extraction.action_words[0]
        if extraction.target_words:
            params["target"] = extraction.target_words[0]
        
        # 添加摘要
        params["summary"] = extraction.summary
        
        return params
    
    async def _recognize_intent(self, message: str) -> Intent:
        """识别用户意图
        
        使用规则+AI混合识别
        """
        # 1. 快速规则匹配
        rule_intent = self._rule_based_intent(message)
        if rule_intent and rule_intent.confidence > 0.8:
            return rule_intent
        
        # 2. AI 意图识别
        return await self._ai_based_intent(message)
    
    def _rule_based_intent(self, message: str) -> Optional[Intent]:
        """基于规则的意图识别"""
        message_lower = message.lower()
        
        # 应用操作模式
        app_patterns = {
            r"给(.+?)发(微信|消息)": (IntentType.APP, "wechat", "send_message"),
            r"发送(邮件|email)": (IntentType.APP, "email", "send_email"),
            r"读取(文件|file)": (IntentType.APP, "filesystem", "read_file"),
            r"写入(文件|file)": (IntentType.APP, "filesystem", "write_file"),
            r"创建(目录|文件夹)": (IntentType.APP, "filesystem", "create_directory"),
            r"删除(文件|file)": (IntentType.APP, "filesystem", "delete_file"),
            r"列出(文件|目录)": (IntentType.APP, "filesystem", "list_files"),
            r"打开(网页|url|链接)": (IntentType.APP, "browser", "open_url"),
            r"搜索(.+?)": (IntentType.APP, "browser", "search"),
            r"截图": (IntentType.APP, "browser", "take_screenshot"),
            r"创建(日程|事件|日历)": (IntentType.APP, "calendar", "create_event"),
            r"查看(日程|日历)": (IntentType.APP, "calendar", "get_events"),
            r"发送(通知|提醒)": (IntentType.APP, "notification", "send_notification"),
            r"播放(音乐|歌曲)": (IntentType.APP, "music", "play"),
            r"暂停(音乐|歌曲)": (IntentType.APP, "music", "pause"),
            r"下一首": (IntentType.APP, "music", "next"),
            r"上一首": (IntentType.APP, "music", "previous"),
            r"播放(视频)": (IntentType.APP, "video", "play"),
            r"搜索(视频)": (IntentType.APP, "video", "search"),
            r"搜索(地点|位置)": (IntentType.APP, "map", "search_location"),
            r"导航到": (IntentType.APP, "map", "get_directions"),
            r"附近": (IntentType.APP, "map", "get_nearby"),
            r"创建(笔记|note)": (IntentType.APP, "note", "create_note"),
            r"搜索(笔记|note)": (IntentType.APP, "note", "search_notes"),
            r"创建(任务|待办|todo)": (IntentType.APP, "todo", "create_task"),
            r"完成(任务|待办)": (IntentType.APP, "todo", "complete_task"),
            r"列出(任务|待办)": (IntentType.APP, "todo", "list_tasks"),
            r"上传(文件)": (IntentType.APP, "cloud", "upload_file"),
            r"下载(文件)": (IntentType.APP, "cloud", "download_file"),
        }
        
        for pattern, (intent_type, target, action) in app_patterns.items():
            match = re.search(pattern, message_lower)
            if match:
                params = self._extract_params_from_match(message, match)
                return Intent(
                    type=intent_type,
                    confidence=0.9,
                    target=target,
                    action=action,
                    params=params,
                    context={"match": match.group(0)}
                )
        
        # 技能调用模式
        skill_patterns = {
            r"@(\w+)": (IntentType.SKILL, None, "call"),
            r"爬取(.+?)热搜": (IntentType.SKILL, "web_scraper", "hot"),
            r"查询(.+?)天气": (IntentType.SKILL, "weather", "query"),
            r"翻译(.+?)": (IntentType.SKILL, "translator", "translate"),
            r"分析(.+?)": (IntentType.SKILL, "data_analysis", "analyze"),
        }
        
        # 网页爬虫增强模式
        web_scraper_patterns = [
            # 热搜/热榜相关
            r"(?:爬取|获取|查看|查询|抓取)(.+?)(?:热搜|热榜|热门|排行|趋势)",
            r"(.+?)(?:热搜|热榜|热门|排行|趋势)",
            r"(?:微博|B站|bilibili|哔哩哔哩|百度|抖音|知乎|今日头条|GitHub|github)(?:热搜|热榜|热门)",
            
            # 搜索相关
            r"(?:搜索|搜)(.+?)(?:视频|内容)",
            r"在(.+?)(?:搜索|查找)(.+?)",
            
            # 爬取相关
            r"(?:爬取|抓取|获取)(.+?)(?:数据|信息|内容)",
        ]
        
        for pattern in web_scraper_patterns:
            match = re.search(pattern, message_lower)
            if match:
                params = self._extract_params_from_match(message, match)
                
                # 智能识别站点
                site_mapping = {
                    "微博": ["微博", "weibo"],
                    "百度": ["百度", "baidu"],
                    "B站": ["b站", "bilibili", "哔哩哔哩"],
                    "抖音": ["抖音", "douyin"],
                    "知乎": ["知乎", "zhihu"],
                    "今日头条": ["今日头条", "头条", "toutiao"],
                    "GitHub": ["github", "git", "hub"],
                }
                
                site_name = None
                message_lower = message.lower()
                for site, keywords in site_mapping.items():
                    if any(kw in message_lower for kw in keywords):
                        site_name = site
                        break
                
                if site_name:
                    params["site_name"] = site_name
                
                # 智能识别操作类型
                action_keywords = {
                    "hot": ["热搜", "热榜", "热门", "排行", "趋势"],
                    "search": ["搜索", "搜", "查找"],
                    "scrape": ["爬取", "抓取", "获取"],
                }
                
                action_type = "hot"  # 默认为热搜
                for action, keywords in action_keywords.items():
                    if any(kw in message_lower for kw in keywords):
                        action_type = action
                        break
                
                return Intent(
                    type=IntentType.SKILL,
                    confidence=0.85,
                    target="web_scraper",
                    action=action_type,
                    params=params,
                    context={"match": match.group(0)}
                )
        
        for pattern, (intent_type, target, action) in skill_patterns.items():
            match = re.search(pattern, message_lower)
            if match:
                params = self._extract_params_from_match(message, match)
                return Intent(
                    type=intent_type,
                    confidence=0.85,
                    target=target or match.group(1),
                    action=action,
                    params=params,
                    context={"match": match.group(0)}
                )
        
        # 多任务模式
        multi_indicators = ["然后", "接着", "再", "最后", "之后", "同时", "并且"]
        if any(ind in message for ind in multi_indicators):
            return Intent(
                type=IntentType.MULTI,
                confidence=0.7,
                target="multi",
                action="execute",
                params={},
                context={"indicators": [ind for ind in multi_indicators if ind in message]}
            )
        
        return None
    
    def _extract_params_from_match(self, message: str, match) -> Dict[str, Any]:
        """从匹配结果中提取参数"""
        params = {}
        if match.groups():
            for i, group in enumerate(match.groups()):
                if group:
                    params[f"param_{i}"] = group.strip()
        
        # 针对文件系统操作，智能提取文件路径
        action_context = match.group(0) if match else ""
        
        # 检测是否为文件系统操作
        fs_actions = ["读取文件", "写入文件", "删除文件", "创建目录", "列出文件", 
                      "read_file", "write_file", "delete_file", "create_directory", "list_files"]
        is_fs_operation = any(action in message for action in fs_actions)
        
        if is_fs_operation:
            # 提取文件路径（支持 /path/to/file 或 ./path 格式）
            path_pattern = r'([\/\w\-\.]+(?:\/[\w\-\.]+)*\.[\w]+)'
            path_matches = re.findall(path_pattern, message)
            
            # 过滤掉常见的非路径词
            valid_paths = [p for p in path_matches if not p.startswith('http') and len(p) > 3]
            
            if valid_paths:
                # 根据操作类型设置不同的参数名
                if "删除" in message or "delete" in action_context.lower():
                    params["file_path"] = valid_paths[0]
                elif "读取" in message or "read" in action_context.lower():
                    params["file_path"] = valid_paths[0]
                elif "写入" in message or "write" in action_context.lower():
                    params["file_path"] = valid_paths[0]
                elif "创建" in message or "create" in action_context.lower():
                    params["directory"] = valid_paths[0]
                elif "列出" in message or "list" in action_context.lower():
                    params["directory"] = valid_paths[0] if valid_paths else "."
            
            # 如果没有找到带扩展名的路径，尝试查找目录路径
            if not valid_paths:
                dir_pattern = r'(\/[\w\-\.\/]+)'
                dir_matches = re.findall(dir_pattern, message)
                if dir_matches:
                    if "删除" in message or "delete" in action_context.lower():
                        params["file_path"] = dir_matches[0]
                    elif "创建" in message or "create" in action_context.lower():
                        params["directory"] = dir_matches[0]
                    elif "列出" in message or "list" in action_context.lower():
                        params["directory"] = dir_matches[0]
        
        return params
    
    async def _ai_based_intent(self, message: str) -> Intent:
        """基于AI的意图识别"""
        try:
            # 获取可用应用和技能
            available_apps = self.app_manager.get_available_apps()
            
            prompt = f"""请识别以下用户消息的意图。

用户消息：{message}

对话历史（最近3条）：
{json.dumps(self.conversation_history[-6:], ensure_ascii=False, indent=2)}

当前上下文：
{json.dumps(self.context, ensure_ascii=False, indent=2)}

可用应用：
{json.dumps(available_apps, ensure_ascii=False, indent=2)}

可用技能：
- web_scraper: 网站爬取
- data_analysis: 数据分析
- translator: 翻译
- weather: 天气查询
- gui_automation: GUI自动化
- rag_search: 智能搜索

意图类型：
- chat: 普通对话
- skill: 技能调用
- app: 应用操作
- workflow: 工作流
- multi: 多任务

返回JSON格式（不要用代码块）：
{{
  "type": "意图类型",
  "confidence": 0.9,
  "target": "目标（技能名、应用类型等）",
  "action": "具体动作",
  "params": {{"key": "value"}},
  "reasoning": "推理过程"
}}

注意：
1. confidence 是0-1之间的置信度
2. 只返回JSON，不要其他内容"""
            
            response = await self.router.simple_chat(
                user_message=prompt,
                system_prompt="你是意图识别助手，只返回JSON格式，不要用代码块",
                temperature=0.3,
            )
            
            if not response or not response.strip():
                raise ValueError("AI 返回空响应")
            
            # 处理可能的 markdown 代码块
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            data = json.loads(response)
            
            return Intent(
                type=IntentType(data.get("type", "chat")),
                confidence=data.get("confidence", 0.5),
                target=data.get("target", ""),
                action=data.get("action", ""),
                params=data.get("params", {}),
                context={"reasoning": data.get("reasoning", "")}
            )
        except Exception as e:
            logger.error("AI 意图识别失败: %s", e)
            # 降级为普通对话
            return Intent(
                type=IntentType.CHAT,
                confidence=0.5,
                target="chat",
                action="respond",
                params={},
                context={"error": str(e)}
            )
    
    async def _build_task_chain(self, message: str, intent: Intent) -> TaskChain:
        """构建任务链
        
        根据意图类型构建不同的任务链
        """
        steps = []
        
        if intent.type == IntentType.CHAT:
            # 普通对话
            steps.append(TaskStep(
                step_id=1,
                description="普通对话",
                intent=intent,
                dependencies=[]
            ))
        
        elif intent.type == IntentType.SKILL:
            # 技能调用
            steps.append(TaskStep(
                step_id=1,
                description=f"调用技能: {intent.target}",
                intent=intent,
                dependencies=[]
            ))
        
        elif intent.type == IntentType.APP:
            # 应用操作
            steps.append(TaskStep(
                step_id=1,
                description=f"应用操作: {intent.target}.{intent.action}",
                intent=intent,
                dependencies=[]
            ))
        
        elif intent.type == IntentType.MULTI:
            # 多任务 - 使用AI分解
            steps = await self._decompose_multi_task(message)
        
        elif intent.type == IntentType.WORKFLOW:
            # 工作流
            steps.append(TaskStep(
                step_id=1,
                description="执行工作流",
                intent=intent,
                dependencies=[]
            ))
        
        return TaskChain(
            user_message=message,
            steps=steps,
            context=self.context.copy()
        )
    
    async def _decompose_multi_task(self, message: str) -> List[TaskStep]:
        """分解多任务
        
        使用AI将复杂任务分解为多个步骤
        """
        try:
            prompt = f"""请将以下任务分解为多个步骤。

任务：{message}

返回JSON格式（不要用代码块）：
{{
  "steps": [
    {{
      "step_id": 1,
      "description": "步骤描述",
      "intent_type": "意图类型",
      "target": "目标",
      "action": "动作",
      "params": {{"key": "value"}},
      "dependencies": []
    }}
  ]
}}

注意：
1. 步骤按执行顺序排列
2. dependencies 表示依赖的前置步骤ID列表
3. 只返回JSON，不要其他内容"""
            
            response = await self.router.simple_chat(
                user_message=prompt,
                system_prompt="你是任务分解助手，只返回JSON格式，不要用代码块",
                temperature=0.5,
            )
            
            if not response or not response.strip():
                raise ValueError("AI 返回空响应")
            
            # 处理可能的 markdown 代码块
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            data = json.loads(response)
            
            steps = []
            for step_data in data.get("steps", []):
                intent = Intent(
                    type=IntentType(step_data.get("intent_type", "skill")),
                    confidence=0.8,
                    target=step_data.get("target", ""),
                    action=step_data.get("action", ""),
                    params=step_data.get("params", {}),
                    context={}
                )
                
                steps.append(TaskStep(
                    step_id=step_data.get("step_id", 1),
                    description=step_data.get("description", ""),
                    intent=intent,
                    dependencies=step_data.get("dependencies", [])
                ))
            
            return steps
        except Exception as e:
            logger.error("任务分解失败: %s", e)
            # 降级为单步骤
            return [TaskStep(
                step_id=1,
                description="执行任务",
                intent=Intent(
                    type=IntentType.CHAT,
                    confidence=0.5,
                    target="chat",
                    action="respond",
                    params={},
                    context={"error": str(e)}
                ),
                dependencies=[]
            )]
    
    def _update_context(self, task_chain: TaskChain):
        """更新上下文
        
        保存任务链的关键信息到上下文中
        """
        for step in task_chain.steps:
            if step.intent.type == IntentType.APP:
                app_key = f"last_{step.intent.target}"
                self.context[app_key] = {
                    "action": step.intent.action,
                    "params": step.intent.params,
                    "timestamp": asyncio.get_event_loop().time()
                }
            elif step.intent.type == IntentType.SKILL:
                skill_key = f"last_{step.intent.target}"
                self.context[skill_key] = {
                    "action": step.intent.action,
                    "params": step.intent.params,
                    "timestamp": asyncio.get_event_loop().time()
                }
    
    async def execute_task_chain(self, task_chain: TaskChain) -> List[Dict[str, Any]]:
        """执行任务链
        
        Args:
            task_chain: 任务链
            
        Returns:
            执行结果列表
        """
        results = []
        
        for step in task_chain.steps:
            try:
                logger.info("执行步骤 %d: %s", step.step_id, step.description)
                
                result = await self._execute_step(step)
                results.append({
                    "step_id": step.step_id,
                    "description": step.description,
                    "success": result.get("success", False),
                    "result": result
                })
                
                # 检查依赖
                if step.dependencies:
                    for dep_id in step.dependencies:
                        dep_result = next((r for r in results if r["step_id"] == dep_id), None)
                        if dep_result and not dep_result["success"]:
                            logger.warning("步骤 %d 的依赖 %d 失败，跳过", step.step_id, dep_id)
                            break
            except Exception as e:
                logger.error("步骤 %d 执行失败: %s", step.step_id, e)
                results.append({
                    "step_id": step.step_id,
                    "description": step.description,
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    async def execute_and_analyze(self, task_chain: TaskChain) -> Dict[str, Any]:
        """执行任务链并进行智能分析
        
        Args:
            task_chain: 任务链
            
        Returns:
            包含执行结果和分析结果的字典
        """
        # 1. 执行任务链
        execution_results = await self.execute_task_chain(task_chain)
        
        # 2. 获取关键词提取结果（如果有）
        extraction = None
        if task_chain.steps:
            first_intent = task_chain.steps[0].intent
            if "extraction" in first_intent.context:
                extraction = first_intent.context["extraction"]
        
        # 3. 智能分析执行结果
        analyzer = get_result_analyzer()
        analysis = await analyzer.analyze(
            original_query=task_chain.user_message,
            execution_results=execution_results,
            extraction=extraction
        )
        
        return {
            "execution_results": execution_results,
            "analysis": analysis,
            "formatted_reply": analysis.formatted_reply
        }

    async def _execute_step(self, step: TaskStep) -> Dict[str, Any]:
        """执行单个步骤
        
        Args:
            step: 任务步骤
            
        Returns:
            执行结果
        """
        intent = step.intent
        
        if intent.type == IntentType.CHAT:
            # 普通对话
            return await self._execute_chat(intent)
        elif intent.type == IntentType.SKILL:
            # 技能调用
            return await self._execute_skill(intent)
        elif intent.type == IntentType.APP:
            # 应用操作
            return await self._execute_app(intent)
        else:
            return {"success": False, "error": f"不支持的意图类型: {intent.type}"}
    
    async def _execute_chat(self, intent: Intent) -> Dict[str, Any]:
        """执行普通对话"""
        try:
            response = await self.router.simple_chat(
                user_message=intent.params.get("message", ""),
                system_prompt="你是一个友好的AI助手",
                temperature=0.7,
            )
            
            return {
                "success": True,
                "response": response
            }
        except Exception as e:
            logger.error("对话执行失败: %s", e)
            return {"success": False, "error": str(e)}
    
    async def _execute_skill(self, intent: Intent) -> Dict[str, Any]:
        """执行技能调用"""
        try:
            # 这里应该调用实际的技能执行器
            # 示例实现
            result = {
                "skill": intent.target,
                "action": intent.action,
                "params": intent.params,
                "status": "executed"
            }
            
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            logger.error("技能执行失败: %s", e)
            return {"success": False, "error": str(e)}
    
    async def _execute_app(self, intent: Intent) -> Dict[str, Any]:
        """执行应用操作"""
        try:
            app_type = AppType(intent.target)
            action = intent.action
            params = intent.params
            
            result = await self.app_manager.execute(app_type, action, params)
            
            return {
                "success": result.success,
                "result": result.result,
                "error": result.error
            }
        except Exception as e:
            logger.error("应用操作失败: %s", e)
            return {"success": False, "error": str(e)}
    
    def clear_context(self):
        """清空上下文"""
        self.context = {}
        self.conversation_history = []
        logger.info("上下文已清空")


# 全局处理器实例
_nlp_processor: Optional[NaturalLanguageProcessor] = None


def get_nlp_processor() -> NaturalLanguageProcessor:
    """获取自然语言处理器单例"""
    global _nlp_processor
    if _nlp_processor is None:
        _nlp_processor = NaturalLanguageProcessor()
    return _nlp_processor
"""独立反问服务模块

提供解耦、可复用的反问功能，支持：
1. 多问题管理
2. 单选/多选模式
3. 选项预览功能
4. 上下文感知
5. 错误处理反问
6. 权限请求集成
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 导入权限服务
try:
    from .permission_service import get_permission_service, PermissionType, PermissionDecision
    HAS_PERMISSION_SERVICE = True
except ImportError:
    HAS_PERMISSION_SERVICE = False
    logger.warning("未找到权限服务模块")

# 导入Forked Agent服务
try:
    from .forked_agent_service import get_forked_agent_service, ForkedResult
    HAS_FORKED_AGENT_SERVICE = True
except ImportError:
    HAS_FORKED_AGENT_SERVICE = False
    logger.warning("未找到Forked Agent服务模块")


class QuestionType(Enum):
    """问题类型枚举"""
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"


@dataclass
class QuestionOption:
    """问题选项"""
    label: str  # 显示文本（1-5个词）
    description: str = ""  # 选项说明
    preview: Optional[str] = None  # 预览内容（代码片段、mockup等）
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"label": self.label, "description": self.description}
        if self.preview:
            result["preview"] = self.preview
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuestionOption":
        return cls(
            label=data.get("label", ""),
            description=data.get("description", ""),
            preview=data.get("preview")
        )


@dataclass
class ClarificationQuestion:
    """反问问题"""
    question: str  # 完整问题文本
    header: str = ""  # 标签/芯片显示（最大12字符）
    options: List[QuestionOption] = field(default_factory=list)
    question_type: QuestionType = QuestionType.SINGLE_SELECT
    max_selections: int = 1  # 最大可选数量
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "header": self.header,
            "options": [opt.to_dict() for opt in self.options],
            "question_type": self.question_type.value,
            "max_selections": self.max_selections
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClarificationQuestion":
        return cls(
            question=data.get("question", ""),
            header=data.get("header", ""),
            options=[QuestionOption.from_dict(opt) for opt in data.get("options", [])],
            question_type=QuestionType(data.get("question_type", "single_select")),
            max_selections=data.get("max_selections", 1)
        )
    
    @classmethod
    def from_template(cls, template_name: str) -> Optional["ClarificationQuestion"]:
        """从模板创建问题"""
        templates = {
            "missing_city": cls(
                question="请问您想查询哪个城市的天气？",
                header="城市",
                options=[
                    QuestionOption("北京", "中国首都"),
                    QuestionOption("上海", "国际化大都市"),
                    QuestionOption("广州", "南方经济中心"),
                    QuestionOption("深圳", "科技创新之城")
                ]
            ),
            "missing_time_range": cls(
                question="请问您想查询哪个时间范围的数据？",
                header="时间范围",
                options=[
                    QuestionOption("今天", "当日数据"),
                    QuestionOption("本周", "最近7天"),
                    QuestionOption("本月", "当前月份"),
                    QuestionOption("自定义", "指定时间段")
                ]
            ),
            "unclear_analysis_dimension": cls(
                question="请问您希望从哪些维度进行分析？",
                header="分析维度",
                options=[
                    QuestionOption("性能", "系统性能指标"),
                    QuestionOption("代码质量", "代码规范和复杂度"),
                    QuestionOption("依赖安全", "第三方库安全风险"),
                    QuestionOption("全面分析", "以上所有维度")
                ],
                question_type=QuestionType.MULTI_SELECT,
                max_selections=4
            ),
            "vague_intent": cls(
                question="为了更好地帮助您，请提供更多信息或选择一个方向：",
                header="需求澄清",
                options=[
                    QuestionOption("详细说明", "请进一步描述您的需求"),
                    QuestionOption("提供示例", "给我一个参考示例"),
                    QuestionOption("直接尝试", "根据现有信息执行"),
                    QuestionOption("放弃任务", "取消当前操作")
                ]
            ),
            "missing_target_file": cls(
                question="您想操作哪个文件？",
                header="目标文件",
                options=[
                    QuestionOption("README.md", "项目说明文档"),
                    QuestionOption("配置文件", "系统配置"),
                    QuestionOption("日志文件", "运行日志"),
                    QuestionOption("指定路径", "自定义路径")
                ]
            ),
            "missing_search_query": cls(
                question="请问您想搜索什么内容？",
                header="搜索关键词",
                options=[
                    QuestionOption("新闻资讯", "最新新闻动态"),
                    QuestionOption("技术文档", "技术资料和文档"),
                    QuestionOption("学术论文", "学术研究资料"),
                    QuestionOption("自定义", "输入具体关键词")
                ]
            ),
            "missing_code_requirement": cls(
                question="请问您想编写什么样的程序？请描述功能需求。",
                header="编程需求",
                options=[
                    QuestionOption("数据处理", "读写文件、转换格式、分析数据"),
                    QuestionOption("网络工具", "爬虫、API调用、网络请求"),
                    QuestionOption("自动化脚本", "批量操作、定时任务"),
                    QuestionOption("其他", "其他类型的程序")
                ]
            ),
            "missing_automation_target": cls(
                question="请问您想自动化什么操作？",
                header="自动化目标",
                options=[
                    QuestionOption("文件操作", "复制、移动、整理文件"),
                    QuestionOption("应用操作", "打开软件、模拟点击"),
                    QuestionOption("网页操作", "自动填写、点击、抓取"),
                    QuestionOption("批量处理", "批量处理多个项目")
                ]
            ),
            "missing_data_source": cls(
                question="请问您想分析什么数据？",
                header="数据来源",
                options=[
                    QuestionOption("文件数据", "CSV/Excel/JSON等文件"),
                    QuestionOption("网页数据", "从网页抓取的数据"),
                    QuestionOption("数据库", "数据库中的数据"),
                    QuestionOption("手动输入", "我手动提供数据")
                ]
            ),
            "missing_scrape_target": cls(
                question="请问您想爬取哪个网站的数据？",
                header="爬虫目标",
                options=[
                    QuestionOption("微博", "微博热搜/话题"),
                    QuestionOption("知乎", "知乎热榜/回答"),
                    QuestionOption("B站", "B站热门视频"),
                    QuestionOption("其他", "其他网站")
                ]
            ),
        }
        return templates.get(template_name)


@dataclass
class ClarificationResult:
    """反问结果"""
    answers: Dict[str, Union[str, List[str]]]  # 问题 -> 答案（多选时为列表）
    annotations: Optional[Dict[str, Dict[str, str]]] = None  # 用户注释
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "answers": self.answers,
            "annotations": self.annotations
        }


@dataclass
class ClarificationHistory:
    """反问历史记录"""
    round: int
    timestamp: datetime
    message: str
    error_context: Optional[str]
    questions: List[Dict[str, Any]]
    context_info: Dict[str, Any]
    result: Optional[ClarificationResult] = None


class ClarificationService:
    """独立反问服务
    
    核心功能：
    1. 检测是否需要反问
    2. 生成反问问题
    3. 管理多轮反问
    4. 处理用户回答
    """
    
    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds
        self.current_round = 0
        self.history: List[ClarificationHistory] = []
        self.clarification_needed = False
        self.current_questions: List[ClarificationQuestion] = []
        
        # 权限服务
        self._permission_service = None
        if HAS_PERMISSION_SERVICE:
            try:
                self._permission_service = get_permission_service()
                logger.info("✅ 权限服务集成成功")
            except Exception as e:
                logger.warning(f"权限服务初始化失败: {e}")
        
        # Forked Agent服务（用于侧问题处理）
        self._forked_agent_service = None
        if HAS_FORKED_AGENT_SERVICE:
            try:
                self._forked_agent_service = get_forked_agent_service()
                logger.info("✅ Forked Agent服务集成成功")
            except Exception as e:
                logger.warning(f"Forked Agent服务初始化失败: {e}")
        
    def reset(self):
        """重置反问状态"""
        self.current_round = 0
        self.clarification_needed = False
        self.current_questions = []
    
    async def handle_side_question(self, question: str) -> Optional[str]:
        """处理侧问题（使用Forked Agent，不中断主流程）
        
        Args:
            question: 用户的侧问题
            
        Returns:
            侧问题的回答（如果Forked Agent服务可用）
        """
        if not self._forked_agent_service:
            logger.warning("Forked Agent服务不可用，无法处理侧问题")
            return None
        
        try:
            result = await self._forked_agent_service.create_side_question(question)
            if result.status.value == "completed" and result.response:
                return result.response
            else:
                logger.warning(f"侧问题处理失败: {result.error}")
                return None
        except Exception as e:
            logger.error(f"侧问题处理异常: {e}")
            return None
    
    def _check_permission_and_clarify_sync(self, permission_type: 'PermissionType',
                                          target: Optional[str] = None,
                                          reason: Optional[str] = None) -> Optional[ClarificationQuestion]:
        """检查权限并生成权限请求反问（同步版）"""
        if not self._permission_service:
            return None
        decision = self._permission_service.check_permission(permission_type, target, reason)
        if decision == PermissionDecision.ALLOW or decision == PermissionDecision.DENY:
            return None
        return self._generate_permission_question(permission_type, target, reason)

    async def _check_permission_and_clarify(self, permission_type: 'PermissionType',
                                           target: Optional[str] = None,
                                           reason: Optional[str] = None) -> Optional[ClarificationQuestion]:
        """检查权限并生成权限请求反问（异步版，委托同步版）"""
        return self._check_permission_and_clarify_sync(permission_type, target, reason)
    
    def _generate_permission_question(self, permission_type: PermissionType, 
                                     target: Optional[str] = None,
                                     reason: Optional[str] = None) -> ClarificationQuestion:
        """生成权限请求反问问题"""
        level_icons = {
            "low": "🔵",
            "medium": "🟡", 
            "high": "🟠",
            "critical": "🔴"
        }
        
        permission_descriptions = {
            PermissionType.READ_FILE: f"读取文件: {target}" if target else "读取文件",
            PermissionType.WRITE_FILE: f"写入文件: {target}" if target else "写入文件",
            PermissionType.DELETE_FILE: f"删除文件: {target}" if target else "删除文件",
            PermissionType.EXECUTE_FILE: f"执行文件: {target}" if target else "执行文件",
            PermissionType.SYSTEM_INFO: "获取系统信息",
            PermissionType.PROCESS_MANAGEMENT: "进程管理",
            PermissionType.NETWORK_ACCESS: "网络访问",
            PermissionType.GUI_AUTOMATION: "GUI自动化操作",
            PermissionType.SCREEN_CAPTURE: "屏幕截图",
            PermissionType.MCP_SERVER_ACCESS: "访问MCP服务器",
            PermissionType.CODE_EXECUTION: "代码执行",
            PermissionType.WEB_REQUEST: "网络请求",
            PermissionType.DANGEROUS_OPERATION: f"危险操作: {target}" if target else "危险操作",
            PermissionType.SANDBOX_MODULE_ACCESS: f"沙盒模块: {target}" if target else "沙盒模块访问"
        }
        
        level = self._permission_service._rules.get(permission_type)
        level_label = level.level.value if level else "medium"
        icon = level_icons.get(level_label, "⚪")
        
        description = permission_descriptions.get(permission_type, str(permission_type.value))
        reason_text = f"\n原因: {reason}" if reason else ""
        
        question_text = f"{icon} 需要授权: {description}{reason_text}"
        
        return ClarificationQuestion(
            question=question_text,
            header="权限请求",
            options=[
                QuestionOption("允许", "授予此权限"),
                QuestionOption("拒绝", "拒绝此权限"),
                QuestionOption("仅本次", "仅本次会话有效")
            ],
            question_type=QuestionType.SINGLE_SELECT
        )
    
    def _get_recent_context(self) -> Dict[str, Any]:
        """获取对话历史上下文（增强版）
        
        改进点：
        1. 从短时记忆获取真实对话历史
        2. 支持多层次检索
        3. 提取关键实体（城市、文件、应用等）
        4. 结合反思机制的结果
        """
        try:
            from core.memory.short_term_memory import ShortTermMemoryManager
            
            memory_manager = ShortTermMemoryManager()
            
            # 获取最近5条对话记录
            recent_messages = []
            for i in range(5):
                context = memory_manager.get_context("default_user", depth=1, limit=1)
                if context:
                    for msg in context:
                        if msg.get("content"):
                            recent_messages.append(msg.get("content", ""))
            
            # 提取关键实体
            entities = self._extract_entities_from_messages(recent_messages)
            
            # 获取反思结果（如果有）
            reflection_result = self._get_reflection_context()
            
            return {
                "recent_messages": recent_messages,
                "entities": entities,
                "reflection": reflection_result,
                "user_preferences": self._get_user_preferences(),
                "execution_history": self._get_execution_history()
            }
        except Exception as e:
            logger.debug(f"获取上下文失败，使用默认实现: {e}")
            return {
                "recent_messages": [],
                "entities": {},
                "reflection": None,
                "user_preferences": {},
                "execution_history": []
            }
    
    def _extract_entities_from_messages(self, messages: List[str]) -> Dict[str, List[str]]:
        """从消息中提取关键实体
        
        Args:
            messages: 消息列表
            
        Returns:
            实体字典 {实体类型: [实体列表]}
        """
        import re
        
        entities = {
            "cities": [],
            "files": [],
            "apps": [],
            "time_periods": [],
            "numbers": []
        }
        
        for msg in messages:
            # 提取城市
            cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "天津", "重庆", 
                     "西安", "苏州", "重庆", "青岛", "长沙", "郑州", "沈阳", "大连", "厦门", "昆明"]
            for city in cities:
                if city in msg and city not in entities["cities"]:
                    entities["cities"].append(city)
            
            # 提取文件
            file_pattern = r'\b[\w\-\.]+\.(md|txt|json|py|js|ts|csv|yaml|yml|pdf|png|jpg)\b'
            files = re.findall(file_pattern, msg, re.IGNORECASE)
            for f in files:
                if f not in entities["files"]:
                    entities["files"].append(f)
            
            # 提取应用
            apps = ["微信", "QQ", "浏览器", "终端", "VSCode", "PyCharm", "计算器", "日历", "Safari", "Chrome"]
            for app in apps:
                if app in msg and app not in entities["apps"]:
                    entities["apps"].append(app)
            
            # 提取时间段
            time_periods = ["今天", "昨天", "明天", "本周", "上周", "本月", "上月", "今年", "去年", "最近"]
            for tp in time_periods:
                if tp in msg and tp not in entities["time_periods"]:
                    entities["time_periods"].append(tp)
            
            # 提取数字
            numbers = re.findall(r'\d+(?:\.\d+)?', msg)
            entities["numbers"].extend(numbers[:5])  # 限制数量
        
        return entities
    
    def _get_reflection_context(self) -> Optional[Dict[str, Any]]:
        """获取反思机制的结果
        
        Returns:
            反思结果（如果有）
        """
        try:
            from core.memory.reflection_mechanism import get_reflection_mechanism
            
            reflection = get_reflection_mechanism()
            if hasattr(reflection, 'get_last_reflection'):
                return reflection.get_last_reflection()
        except Exception as e:
            logger.debug(f"获取反思上下文失败: {e}")
        
        return None
    
    def _get_user_preferences(self) -> Dict[str, Any]:
        """获取用户偏好设置
        
        Returns:
            用户偏好字典
        """
        try:
            from core.memory.short_term_memory import ShortTermMemoryManager
            
            memory_manager = ShortTermMemoryManager()
            prefs = memory_manager.get_context("default_user:preferences", depth=1, limit=1)
            if prefs:
                return {"preferences": prefs}
        except Exception as e:
            logger.debug(f"获取用户偏好失败: {e}")
        
        return {}
    
    def _get_execution_history(self) -> List[Dict[str, Any]]:
        """获取执行历史
        
        Returns:
            执行历史列表
        """
        try:
            from core.memory.short_term_memory import ShortTermMemoryManager
            
            memory_manager = ShortTermMemoryManager()
            history = memory_manager.get_context("default_user:execution", depth=3, limit=3)
            if history:
                return [{"content": h} for h in history if isinstance(h, dict)]
        except Exception as e:
            logger.debug(f"获取执行历史失败: {e}")
        
        return []
    
    def _enhance_question_with_context(self, question: ClarificationQuestion, 
                                       context_info: Dict[str, Any]) -> ClarificationQuestion:
        """结合上下文优化问题（增强版）
        
        改进点：
        1. 使用实体提取结果，更精准地推荐选项
        2. 结合反思机制的结果
        3. 根据执行历史优化问题
        
        Args:
            question: 原始问题
            context_info: 上下文信息
            
        Returns:
            增强后的问题
        """
        entities = context_info.get("entities", {})
        reflection = context_info.get("reflection")
        
        # 从上下文中获取实体
        cities_in_context = entities.get("cities", [])
        files_in_context = entities.get("files", [])
        apps_in_context = entities.get("apps", [])
        time_periods_in_context = entities.get("time_periods", [])
        
        # 如果上下文中提到过城市，添加到天气相关问题的选项中
        if question.header == "城市" and cities_in_context:
            # 将上下文中的城市添加到选项前面
            for city in cities_in_context[:3]:  # 最多添加3个
                found = False
                for opt in question.options:
                    if city == opt.label:
                        found = True
                        break
                if not found:
                    question.options.insert(0, QuestionOption(city, "上下文中提到的城市"))
        
        # 如果上下文中提到过文件，添加到文件相关问题的选项中
        if question.header == "目标文件" and files_in_context:
            for file in files_in_context[:3]:
                found = False
                for opt in question.options:
                    if file in opt.label:
                        found = True
                        break
                if not found:
                    question.options.insert(0, QuestionOption(file, "上下文中提到的文件"))
        
        # 如果上下文中提到过应用，添加到应用相关问题的选项中
        if question.header == "应用" and apps_in_context:
            for app in apps_in_context[:3]:
                found = False
                for opt in question.options:
                    if app == opt.label:
                        found = True
                        break
                if not found:
                    question.options.insert(0, QuestionOption(app, "上下文中提到的应用"))
        
        # 如果有反思结果，结合到问题中
        if reflection:
            # 如果反思表明之前执行失败，添加相关选项
            if "error" in str(reflection).lower() or "失败" in str(reflection):
                # 添加"使用替代方案"选项
                fallback_option = QuestionOption(
                    "使用替代方案", 
                    "反思建议：之前的方法可能不适用，尝试其他方案"
                )
                if fallback_option.label not in [opt.label for opt in question.options]:
                    question.options.append(fallback_option)
        
        # 如果有执行历史，结合到问题中
        execution_history = context_info.get("execution_history", [])
        if execution_history:
            # 检查是否有类似任务的执行记录
            for exec_item in execution_history:
                if isinstance(exec_item, dict) and "content" in exec_item:
                    exec_content = str(exec_item["content"])
                    # 如果执行成功，添加"重复上次操作"选项
                    if "success" in exec_content.lower() or "成功" in exec_content:
                        repeat_option = QuestionOption(
                            "重复上次操作",
                            "根据之前的成功经验重复执行"
                        )
                        if repeat_option.label not in [opt.label for opt in question.options]:
                            question.options.append(repeat_option)
                        break
        
        return question
    
    def _generate_error_clarification(self, error_context: str, 
                                      context_info: Dict[str, Any]) -> Optional[ClarificationQuestion]:
        """生成错误处理相关的反问"""
        error_keywords = {
            "network": ["网络", "连接", "超时", "无法访问"],
            "permission": ["权限", "禁止", "拒绝", "无权限"],
            "tool_error": ["工具", "执行失败", "错误", "异常"],
            "not_found": ["找不到", "不存在", "未找到"]
        }
        
        error_type = "unknown"
        for etype, keywords in error_keywords.items():
            if any(kw in error_context for kw in keywords):
                error_type = etype
                break
        
        error_templates = {
            "network": ClarificationQuestion(
                question="网络连接出现问题，您希望如何处理？",
                header="网络错误",
                options=[
                    QuestionOption("重试", "重新尝试连接"),
                    QuestionOption("检查网络", "检查网络设置"),
                    QuestionOption("使用缓存", "使用缓存数据"),
                    QuestionOption("放弃", "取消当前操作")
                ]
            ),
            "permission": ClarificationQuestion(
                question="当前操作需要权限，您希望如何处理？",
                header="权限不足",
                options=[
                    QuestionOption("请求权限", "申请必要权限"),
                    QuestionOption("使用替代方案", "尝试其他方法"),
                    QuestionOption("跳过此步骤", "继续其他任务"),
                    QuestionOption("放弃", "取消当前操作")
                ]
            ),
            "tool_error": ClarificationQuestion(
                question=f"工具执行失败: {error_context}，您希望如何处理？",
                header="执行错误",
                options=[
                    QuestionOption("重试", "重新执行"),
                    QuestionOption("调试", "查看详细错误信息"),
                    QuestionOption("使用Fallback", "尝试备用方案"),
                    QuestionOption("放弃", "取消当前操作")
                ]
            ),
            "not_found": ClarificationQuestion(
                question="目标资源未找到，您希望如何处理？",
                header="资源不存在",
                options=[
                    QuestionOption("确认路径", "检查路径是否正确"),
                    QuestionOption("搜索", "搜索相关资源"),
                    QuestionOption("创建", "创建新资源"),
                    QuestionOption("放弃", "取消当前操作")
                ]
            ),
            "unknown": ClarificationQuestion(
                question=f"执行过程中出现问题: {error_context}，您希望如何处理？",
                header="执行异常",
                options=[
                    QuestionOption("重试", "重新执行"),
                    QuestionOption("详细信息", "查看错误详情"),
                    QuestionOption("放弃", "取消当前操作")
                ]
            )
        }
        
        return error_templates.get(error_type)
    
    def _determine_required_permission(self, message: str) -> Optional[PermissionType]:
        """根据消息内容判断需要的权限类型"""
        if not HAS_PERMISSION_SERVICE:
            return None
        
        message_lower = message.lower()
        
        permission_rules = [
            (["读取", "read", "文件"], PermissionType.READ_FILE),
            (["写入", "write", "保存"], PermissionType.WRITE_FILE),
            (["删除", "delete", "移除"], PermissionType.DELETE_FILE),
            (["执行", "execute", "运行"], PermissionType.EXECUTE_FILE),
            (["截图", "screen", "capture"], PermissionType.SCREEN_CAPTURE),
            (["自动化", "automation", "控制"], PermissionType.GUI_AUTOMATION),
            (["网络", "network", "请求"], PermissionType.NETWORK_ACCESS),
            (["代码", "code", "python"], PermissionType.CODE_EXECUTION),
            (["进程", "process", "管理"], PermissionType.PROCESS_MANAGEMENT),
        ]
        
        for keywords, perm_type in permission_rules:
            if any(kw in message_lower for kw in keywords):
                return perm_type
        
        return None
    
    def detect_clarification_needed(self, message: str, 
                                    error_context: Optional[str] = None) -> bool:
        """检测是否需要反问用户"""
        questions = self.generate_questions(message, error_context)
        return len(questions) > 0
    
    async def handle_execution_failure(self, error_context: str, 
                                      original_message: str,
                                      retry_count: int = 0) -> Optional[ClarificationQuestion]:
        """处理执行失败时的反问（新增功能）
        
        当工具执行失败时，自动触发反问机制：
        1. 分析错误类型
        2. 结合短时记忆和反思机制
        3. 生成智能反问问题
        4. 提供可行的解决方案选项
        
        Args:
            error_context: 错误上下文
            original_message: 用户的原始消息
            retry_count: 重试次数
            
        Returns:
            反问问题（如果有）
        """
        logger.info(f"处理执行失败: {error_context}")
        
        # 获取增强后的上下文
        context_info = self._get_recent_context()
        
        # 分析错误类型
        error_type = self._classify_error(error_context)
        
        # 根据错误类型生成反问
        question = self._generate_error_clarification(error_context, context_info)
        
        if question:
            # 增加重试次数相关的说明
            if retry_count > 0:
                question.question += f"\n\n（已重试 {retry_count} 次）"
            
            # 增强问题选项
            question = self._enhance_question_with_context(question, context_info)
            
            # 检查是否超过最大反问轮数
            if self.current_round >= self.max_rounds:
                logger.info(f"已达到最大反问轮数({self.max_rounds})，不再反问")
                return None
            
            # 记录反问历史
            self.current_questions = [question]
            self.clarification_needed = True
            
            self.history.append(ClarificationHistory(
                round=self.current_round + 1,
                timestamp=datetime.now(),
                message=original_message,
                error_context=error_context,
                questions=[question.to_dict()],
                context_info=context_info
            ))
            
            self.current_round += 1
            
            return question
        
        return None
    
    def _classify_error(self, error_context: str) -> str:
        """分类错误类型
        
        Args:
            error_context: 错误上下文
            
        Returns:
            错误类型：network, permission, tool_error, not_found, timeout, unknown
        """
        error_context_lower = error_context.lower()
        
        # 网络错误
        if any(kw in error_context_lower for kw in ["network", "网络", "连接", "connection", 
                                                      "timeout", "超时", "refused", "无法连接"]):
            return "network"
        
        # 权限错误
        if any(kw in error_context_lower for kw in ["permission", "权限", "denied", "拒绝", 
                                                      "unauthorized", "禁止"]):
            return "permission"
        
        # 工具错误
        if any(kw in error_context_lower for kw in ["tool", "工具", "执行", "error", "错误", 
                                                      "exception", "failed"]):
            return "tool_error"
        
        # 找不到资源
        if any(kw in error_context_lower for kw in ["not found", "找不到", "不存在", "未找到", 
                                                      "404", "ENOENT"]):
            return "not_found"
        
        # 超时错误
        if any(kw in error_context_lower for kw in ["timeout", "超时", "timed out", "deadline"]):
            return "timeout"
        
        return "unknown"
    
    def generate_questions(self, message: str, 
                           error_context: Optional[str] = None,
                           check_permission: bool = True) -> List[ClarificationQuestion]:
        """生成反问问题列表
        
        Args:
            message: 用户输入消息
            error_context: 错误上下文（用于执行失败时的反问）
            check_permission: 是否检查权限
            
        Returns:
            反问问题列表
        """
        questions = []
        message_lower = message.lower()
        
        # 检查是否超过最大反问轮数
        if self.current_round >= self.max_rounds:
            logger.info(f"已达到最大反问轮数({self.max_rounds})，不再反问")
            return []
        
        # 获取对话历史上下文
        context_info = self._get_recent_context()
        
        # 检查权限（如果需要）
        if check_permission and self._permission_service:
            permission_type = self._determine_required_permission(message)
            if permission_type:
                perm_question = self._check_permission_and_clarify_sync(
                    permission_type, None, message[:100]
                )
                if perm_question:
                    questions.append(perm_question)
        
        # 模板配置
        clarification_templates = {
            "missing_city": {
                "keywords": ["天气", "温度", "气温", "weather"],
                "exclude_keywords": ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "天津", "重庆"],
                "template": "missing_city"
            },
            "missing_time_range": {
                "keywords": ["最近", "过去", "以前", "未来", "历史"],
                "exclude_keywords": ["今天", "昨天", "明天", "这周", "上周", "这个月", "上个月", "今年", "去年"],
                "template": "missing_time_range"
            },
            "unclear_analysis_dimension": {
                "keywords": ["分析", "analyze", "评估", "检查"],
                "exclude_keywords": ["性能", "代码质量", "依赖", "全面", "统计"],
                "template": "unclear_analysis_dimension"
            },
            "missing_target_file": {
                "keywords": ["文件", "文档", "读取", "处理", "打开"],
                "exclude_keywords": ["readme", ".md", ".txt", ".json", ".py", "config", "log", "当前"],
                "template": "missing_target_file"
            },
            "vague_intent": {
                "keywords": ["怎么做", "怎么办", "如何", "哪个", "哪里", "什么"],
                "exclude_keywords": [],
                "template": "vague_intent"
            },
            "missing_search_query": {
                "keywords": ["搜索", "搜一下", "查一下", "查找", "search", "查询"],
                "exclude_keywords": ["天气", "温度", "气温", "weather", "词典", "翻译"],
                "template": "missing_search_query"
            },
            "missing_code_requirement": {
                "keywords": ["写一个", "写个", "编个", "编写", "编程", "代码", "程序", "脚本"],
                "exclude_keywords": ["文件", "文档", "读取", "处理"],
                "template": "missing_code_requirement"
            },
            "missing_automation_target": {
                "keywords": ["自动化", "自动", "批量", "一键"],
                "exclude_keywords": ["下载", "上传", "备份", "清理"],
                "template": "missing_automation_target"
            },
            "missing_data_source": {
                "keywords": ["数据分析", "分析数据", "统计", "数据挖掘", "数据可视化"],
                "exclude_keywords": ["csv", ".csv", ".xlsx", ".json", "文件"],
                "template": "missing_data_source"
            },
            "missing_scrape_target": {
                "keywords": ["爬取", "抓取", "爬虫", "采集", "爬", "scrape"],
                "exclude_keywords": ["微博", "知乎", "b站", "bilibili", "抖音", "github", "百度", "头条"],
                "template": "missing_scrape_target"
            }
        }
        
        needs_clarification = False
        
        for category, config in clarification_templates.items():
            has_keyword = any(kw in message_lower for kw in config["keywords"])
            if not has_keyword:
                continue
            
            has_exclude_info = any(ex_kw in message_lower for ex_kw in config.get("exclude_keywords", []))
            if has_exclude_info:
                continue
            
            template_name = config.get("template")
            if template_name:
                question = ClarificationQuestion.from_template(template_name)
                if question:
                    question = self._enhance_question_with_context(question, context_info)
                    questions.append(question)
                    needs_clarification = True
        
        # 如果有错误上下文，添加执行失败相关的反问
        if error_context:
            error_question = self._generate_error_clarification(error_context, context_info)
            if error_question:
                questions.append(error_question)
                needs_clarification = True

        # 记录反问历史
        if needs_clarification:
            self.current_questions = questions
            self.clarification_needed = True
            
            self.history.append(ClarificationHistory(
                round=self.current_round + 1,
                timestamp=datetime.now(),
                message=message,
                error_context=error_context,
                questions=[q.to_dict() for q in questions],
                context_info=context_info
            ))
        
        return questions
    
    def process_answers(self, answers: Dict[str, Union[str, List[str]]],
                        annotations: Optional[Dict[str, Dict[str, str]]] = None) -> ClarificationResult:
        """处理用户回答"""
        result = ClarificationResult(answers=answers, annotations=annotations)
        
        # 更新历史记录
        if self.history:
            self.history[-1].result = result
        
        # 增加反问轮数
        self.current_round += 1
        self.clarification_needed = False
        
        return result
    
    async def async_detect_clarification(self, message: str) -> List[ClarificationQuestion]:
        """异步反问检测：先跑关键词模板，没匹配到再用LLM判断"""
        questions = self.generate_questions(message)
        if questions:
            return questions

        # LLM 后备判断
        if len(message) < 200:
            try:
                from ..engine.llm_backend import get_llm_router
                router = get_llm_router()
                if router and router.is_available():
                    llm_prompt = (
                        f"用户说: {message}\n\n"
                        f"判断是否需要追问才能执行。"
                        f"需要追问回复Y+追问内容，否则只回复N。"
                    )
                    llm_check = await router.simple_chat(
                        user_message=llm_prompt,
                        system_prompt="需要追问回复Y+问题，不需要只回复N",
                        temperature=0.1,
                    )
                    if llm_check and llm_check.strip().startswith("Y"):
                        question_text = llm_check[1:].strip() or "请提供更多信息"
                        questions.append(ClarificationQuestion(
                            question=question_text,
                            header="需求澄清",
                            options=[
                                QuestionOption("详细说明", "进一步描述需求"),
                                QuestionOption("提供示例", "给出参考例子"),
                                QuestionOption("直接执行", "按现有信息尝试"),
                            ],
                        ))
            except Exception:
                pass
        return questions

    def get_history(self) -> List[Dict[str, Any]]:
        """获取反问历史记录"""
        return [
            {
                "round": h.round,
                "timestamp": h.timestamp.isoformat(),
                "message": h.message,
                "error_context": h.error_context,
                "questions": h.questions,
                "result": h.result.to_dict() if h.result else None
            }
            for h in self.history
        ]


# 全局单例
_clarification_service = None

def get_clarification_service() -> ClarificationService:
    """获取反问服务实例"""
    global _clarification_service
    if _clarification_service is None:
        _clarification_service = ClarificationService()
    return _clarification_service
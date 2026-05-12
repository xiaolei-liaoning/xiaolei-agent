"""工具框架模块 - 借鉴Claude Code的buildTool模式

提供统一的工具抽象和构建器模式，支持：
1. 标准化的工具定义接口
2. 输入/输出Schema验证
3. 权限检查机制
4. 工具注册和发现
5. 统一的结果渲染
6. 第三方工具适配器
7. 动态工具调度

设计模式:
- Builder模式 - build_tool() 函数
- 策略模式 - 权限检查和渲染方法
- 工厂模式 - ToolRegistry
- 适配器模式 - ThirdPartyToolAdapter
- 策略模式 - ToolScheduler
"""

import inspect
import asyncio
import logging
from typing import Any, Dict, List, Optional, Callable, Type, Union
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ToolPermission(Enum):
    """工具权限级别"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: Type
    description: str
    required: bool = True
    default: Any = None
    validator: Optional[Callable[[Any], bool]] = None


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any = None
    error: str = ""
    message: str = ""
    metadata: Optional[Dict[str, Any]] = None


class ToolMetadata:
    """工具元数据"""
    
    def __init__(self, 
                 name: str,
                 description: str,
                 permissions: List[ToolPermission] = None,
                 category: str = "general",
                 version: str = "1.0.0",
                 tags: List[str] = None):
        self.name = name
        self.description = description
        self.permissions = permissions or []
        self.category = category
        self.version = version
        self.tags = tags or []


class BaseTool(ABC):
    """工具基类"""
    
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        pass
    
    async def check_permissions(self, context: Dict[str, Any]) -> bool:
        """检查权限"""
        return True
    
    def render_result(self, result: ToolResult) -> str:
        """渲染结果"""
        if result.success:
            return f"✅ {result.message or '操作成功'}"
        return f"❌ {result.error or '操作失败'}"
    
    def get_input_schema(self) -> List[ToolParameter]:
        """获取输入Schema"""
        return []
    
    def get_output_schema(self) -> Dict[str, Type]:
        """获取输出Schema"""
        return {}


class ToolBuilder:
    """工具构建器"""
    
    def __init__(self):
        self._metadata = None
        self._execute_func = None
        self._permission_check_func = None
        self._render_func = None
        self._input_schema = []
        self._output_schema = {}
    
    def name(self, name: str) -> 'ToolBuilder':
        """设置工具名称"""
        if not self._metadata:
            self._metadata = ToolMetadata(name=name, description="")
        else:
            self._metadata.name = name
        return self
    
    def description(self, description: str) -> 'ToolBuilder':
        """设置工具描述"""
        if not self._metadata:
            self._metadata = ToolMetadata(name="", description=description)
        else:
            self._metadata.description = description
        return self
    
    def permission(self, permission: ToolPermission) -> 'ToolBuilder':
        """添加权限要求"""
        if not self._metadata:
            self._metadata = ToolMetadata(name="", description="", permissions=[permission])
        else:
            self._metadata.permissions.append(permission)
        return self
    
    def category(self, category: str) -> 'ToolBuilder':
        """设置工具类别"""
        if not self._metadata:
            self._metadata = ToolMetadata(name="", description="", category=category)
        else:
            self._metadata.category = category
        return self
    
    def version(self, version: str) -> 'ToolBuilder':
        """设置版本号"""
        if not self._metadata:
            self._metadata = ToolMetadata(name="", description="", version=version)
        else:
            self._metadata.version = version
        return self
    
    def tag(self, tag: str) -> 'ToolBuilder':
        """添加标签"""
        if not self._metadata:
            self._metadata = ToolMetadata(name="", description="", tags=[tag])
        else:
            self._metadata.tags.append(tag)
        return self
    
    def param(self, name: str, type: Type, description: str, required: bool = True, 
              default: Any = None, validator: Optional[Callable[[Any], bool]] = None) -> 'ToolBuilder':
        """添加参数定义"""
        self._input_schema.append(ToolParameter(
            name=name,
            type=type,
            description=description,
            required=required,
            default=default,
            validator=validator
        ))
        return self
    
    def output_field(self, name: str, type: Type) -> 'ToolBuilder':
        """添加输出字段"""
        self._output_schema[name] = type
        return self
    
    def executes(self, func: Callable) -> 'ToolBuilder':
        """设置执行函数"""
        self._execute_func = func
        return self
    
    def check_permissions_with(self, func: Callable) -> 'ToolBuilder':
        """设置权限检查函数"""
        self._permission_check_func = func
        return self
    
    def renders_with(self, func: Callable) -> 'ToolBuilder':
        """设置结果渲染函数"""
        self._render_func = func
        return self
    
    def build(self) -> BaseTool:
        """构建工具实例"""
        if not self._metadata:
            raise ValueError("工具名称和描述不能为空")
        if not self._execute_func:
            raise ValueError("必须提供执行函数")
        
        metadata = self._metadata
        execute_func = self._execute_func
        permission_check_func = self._permission_check_func
        render_func = self._render_func
        input_schema = self._input_schema
        output_schema = self._output_schema
        
        class BuiltTool(BaseTool):
            def __init__(self):
                super().__init__(metadata=metadata)
            
            async def execute(self, **kwargs) -> ToolResult:
                for param in input_schema:
                    if param.required and param.name not in kwargs:
                        return ToolResult(
                            success=False,
                            error=f"缺少必需参数: {param.name}"
                        )
                    if param.name in kwargs:
                        value = kwargs[param.name]
                        if not isinstance(value, param.type):
                            try:
                                kwargs[param.name] = param.type(value)
                            except (ValueError, TypeError):
                                return ToolResult(
                                    success=False,
                                    error=f"参数 {param.name} 类型错误，期望 {param.type.__name__}"
                                )
                        if param.validator and not param.validator(value):
                            return ToolResult(
                                success=False,
                                error=f"参数 {param.name} 验证失败"
                            )
                
                if inspect.iscoroutinefunction(execute_func):
                    return await execute_func(**kwargs)
                else:
                    return execute_func(**kwargs)
            
            async def check_permissions(self, context: Dict[str, Any]) -> bool:
                if permission_check_func:
                    if inspect.iscoroutinefunction(permission_check_func):
                        return await permission_check_func(context)
                    else:
                        return permission_check_func(context)
                return True
            
            def render_result(self, result: ToolResult) -> str:
                if render_func:
                    return render_func(result)
                return super().render_result(result)
            
            def get_input_schema(self) -> List[ToolParameter]:
                return input_schema
            
            def get_output_schema(self) -> Dict[str, Type]:
                return output_schema
        
        return BuiltTool()


class ToolRegistry:
    """工具注册表"""
    
    _instance = None
    _tools: Dict[str, BaseTool] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, tool: BaseTool):
        """注册工具"""
        self._tools[tool.metadata.name] = tool
    
    def register_multiple(self, tools: List[BaseTool]):
        """批量注册工具"""
        for tool in tools:
            self.register(tool)
    
    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_all(self) -> List[BaseTool]:
        """获取所有工具"""
        return list(self._tools.values())
    
    def list_by_category(self, category: str) -> List[BaseTool]:
        """按类别获取工具"""
        return [tool for tool in self._tools.values() 
                if tool.metadata.category == category]
    
    def search(self, keyword: str) -> List[BaseTool]:
        """搜索工具"""
        keyword_lower = keyword.lower()
        return [tool for tool in self._tools.values() 
                if (keyword_lower in tool.metadata.name.lower() or
                    keyword_lower in tool.metadata.description.lower() or
                    any(keyword_lower in tag.lower() for tag in tool.metadata.tags))]
    
    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取工具信息"""
        tool = self.get(name)
        if not tool:
            return None
        
        return {
            "name": tool.metadata.name,
            "description": tool.metadata.description,
            "category": tool.metadata.category,
            "version": tool.metadata.version,
            "permissions": [p.value for p in tool.metadata.permissions],
            "tags": tool.metadata.tags,
            "input_schema": [
                {
                    "name": p.name,
                    "type": p.type.__name__,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default
                } for p in tool.get_input_schema()
            ],
            "output_schema": {
                k: v.__name__ for k, v in tool.get_output_schema().items()
            }
        }


# 便捷函数
def build_tool(name: str = "", description: str = "") -> ToolBuilder:
    """创建工具构建器"""
    builder = ToolBuilder()
    if name:
        builder.name(name)
    if description:
        builder.description(description)
    return builder


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表实例"""
    return ToolRegistry()


def register_tool(tool: BaseTool):
    """注册工具"""
    get_tool_registry().register(tool)


# 第三方工具适配器
class ThirdPartyToolAdapter(BaseTool, ABC):
    """第三方工具适配器基类
    
    为第三方工具提供统一的接口适配，隐藏底层工具的实现细节。
    """
    
    def __init__(self, metadata: ToolMetadata, tool_instance: Any = None):
        super().__init__(metadata)
        self.tool_instance = tool_instance
        self._setup_adapter()
    
    def _setup_adapter(self):
        """初始化适配器"""
        pass
    
    @abstractmethod
    def _call_native_tool(self, **kwargs) -> Any:
        """调用原生工具"""
        pass
    
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具（带错误处理）"""
        try:
            # 参数验证
            for param in self.get_input_schema():
                if param.required and param.name not in kwargs:
                    return ToolResult(
                        success=False,
                        error=f"缺少必需参数: {param.name}"
                    )
            
            # 调用原生工具
            result = self._call_native_tool(**kwargs)
            
            # 处理异步结果
            if asyncio.iscoroutine(result):
                result = await result
            
            # 转换为统一的ToolResult格式
            return self._convert_result(result)
            
        except Exception as e:
            logger.error(f"调用第三方工具 {self.metadata.name} 失败: {e}")
            return ToolResult(
                success=False,
                error=str(e),
                message="调用第三方工具失败"
            )
    
    @abstractmethod
    def _convert_result(self, native_result: Any) -> ToolResult:
        """将原生工具结果转换为统一格式"""
        pass
    
    def get_native_tool(self) -> Any:
        """获取原生工具实例"""
        return self.tool_instance


class ThirdPartyToolBuilder(ToolBuilder):
    """第三方工具构建器"""
    
    def __init__(self):
        super().__init__()
        self._native_tool_class = None
        self._native_tool_args = {}
        self._result_converter = None
        self._error_handler = None
        self._method_name = None
    
    def native_tool(self, tool_class: Type, method_name: str = None, **kwargs) -> 'ThirdPartyToolBuilder':
        """设置原生工具类和初始化参数
        
        Args:
            tool_class: 原生工具类
            method_name: 要调用的方法名称（可选，默认自动检测execute/__call__/run）
            **kwargs: 工具初始化参数
        """
        self._native_tool_class = tool_class
        self._native_tool_args = kwargs
        self._method_name = method_name
        return self
    
    def converts_result_with(self, func: Callable[[Any], ToolResult]) -> 'ThirdPartyToolBuilder':
        """设置结果转换器"""
        self._result_converter = func
        return self
    
    def handles_errors_with(self, func: Callable[[Exception], ToolResult]) -> 'ThirdPartyToolBuilder':
        """设置错误处理器"""
        self._error_handler = func
        return self
    
    def build(self) -> ThirdPartyToolAdapter:
        """构建第三方工具适配器"""
        if not self._metadata:
            raise ValueError("工具名称和描述不能为空")
        if not self._native_tool_class:
            raise ValueError("必须提供原生工具类")
        
        metadata = self._metadata
        native_tool_class = self._native_tool_class
        native_tool_args = self._native_tool_args
        result_converter = self._result_converter
        error_handler = self._error_handler
        input_schema = self._input_schema
        method_name = self._method_name
        
        class BuiltThirdPartyAdapter(ThirdPartyToolAdapter):
            def __init__(self):
                tool_instance = native_tool_class(**native_tool_args) if native_tool_args else native_tool_class()
                super().__init__(metadata=metadata, tool_instance=tool_instance)
            
            def _call_native_tool(self, **kwargs) -> Any:
                # 如果指定了方法名，直接调用
                if method_name:
                    if hasattr(self.tool_instance, method_name):
                        method = getattr(self.tool_instance, method_name)
                        return method(**kwargs)
                    else:
                        raise NotImplementedError(f"原生工具没有方法: {method_name}")
                
                # 自动检测可调用方法
                if hasattr(self.tool_instance, 'execute'):
                    return self.tool_instance.execute(**kwargs)
                elif hasattr(self.tool_instance, '__call__'):
                    return self.tool_instance(**kwargs)
                elif hasattr(self.tool_instance, 'run'):
                    return self.tool_instance.run(**kwargs)
                else:
                    # 尝试查找第一个可调用的公共方法
                    for attr_name in dir(self.tool_instance):
                        if not attr_name.startswith('_'):
                            attr = getattr(self.tool_instance, attr_name)
                            if callable(attr):
                                return attr(**kwargs)
                    raise NotImplementedError("原生工具没有可调用的方法")
            
            def _convert_result(self, native_result: Any) -> ToolResult:
                if result_converter:
                    return result_converter(native_result)
                # 默认转换
                if isinstance(native_result, dict):
                    success = native_result.get('success', True)
                    return ToolResult(
                        success=success,
                        data=native_result.get('data'),
                        error=native_result.get('error', ''),
                        message=native_result.get('message', '')
                    )
                return ToolResult(
                    success=True,
                    data=native_result,
                    message="执行成功"
                )
            
            async def execute(self, **kwargs) -> ToolResult:
                try:
                    # 参数验证
                    for param in input_schema:
                        if param.required and param.name not in kwargs:
                            return ToolResult(
                                success=False,
                                error=f"缺少必需参数: {param.name}"
                            )
                    
                    result = self._call_native_tool(**kwargs)
                    if asyncio.iscoroutine(result):
                        result = await result
                    
                    return self._convert_result(result)
                except Exception as e:
                    logger.error(f"第三方工具执行失败: {e}")
                    if error_handler:
                        return error_handler(e)
                    return ToolResult(
                        success=False,
                        error=str(e),
                        message="调用第三方工具失败"
                    )
            
            def get_input_schema(self) -> List[ToolParameter]:
                return input_schema
        
        return BuiltThirdPartyAdapter()


# 工具调度器
class ToolScheduler:
    """工具调度器 - 动态决定使用哪个工具"""
    
    def __init__(self):
        self.registry = ToolRegistry()
        self._tool_scores: Dict[str, float] = {}
        self._usage_history: Dict[str, List[Dict]] = {}
    
    async def select_tool(self, task_description: str, 
                          context: Optional[Dict[str, Any]] = None) -> Optional[BaseTool]:
        """根据任务描述选择最合适的工具"""
        tools = self._get_candidate_tools(task_description)
        
        if not tools:
            return None
        
        # 计算每个工具的匹配度
        scores = await self._calculate_scores(tools, task_description, context)
        
        if not scores:
            return None
        
        # 选择得分最高的工具
        best_tool_name = max(scores, key=scores.get)
        best_score = scores[best_tool_name]
        
        # 如果得分太低，返回None
        if best_score < 0.3:
            logger.warning(f"没有找到匹配度足够的工具，最高得分: {best_score}")
            return None
        
        logger.info(f"选择工具: {best_tool_name}, 得分: {best_score}")
        return self.registry.get(best_tool_name)
    
    def _get_candidate_tools(self, task_description: str) -> List[BaseTool]:
        """获取候选工具"""
        # 首先尝试搜索
        search_results = self.registry.search(task_description)
        if search_results:
            return search_results
        
        # 如果搜索没有结果，返回所有工具
        return self.registry.list_all()
    
    async def _calculate_scores(self, tools: List[BaseTool], 
                                task_description: str, 
                                context: Optional[Dict]) -> Dict[str, float]:
        """计算工具匹配度得分"""
        scores = {}
        task_lower = task_description.lower()
        
        for tool in tools:
            score = 0.0
            
            # 名称匹配
            if tool.metadata.name.lower() in task_lower:
                score += 0.3
            
            # 描述匹配
            if any(word in task_lower for word in tool.metadata.description.lower().split()):
                score += 0.3
            
            # 标签匹配
            for tag in tool.metadata.tags:
                if tag.lower() in task_lower:
                    score += 0.1
            
            # 使用历史加分
            if tool.metadata.name in self._usage_history:
                success_rate = self._calculate_success_rate(tool.metadata.name)
                score += success_rate * 0.2
            
            # 类别匹配
            if context and 'category' in context:
                if tool.metadata.category == context['category']:
                    score += 0.1
            
            # 限制最高得分
            score = min(score, 1.0)
            scores[tool.metadata.name] = score
        
        return scores
    
    def _calculate_success_rate(self, tool_name: str) -> float:
        """计算工具成功使用率"""
        history = self._usage_history.get(tool_name, [])
        if not history:
            return 0.5
        
        success_count = sum(1 for h in history if h.get('success'))
        return success_count / len(history)
    
    async def execute_with_best_tool(self, task_description: str, 
                                     **kwargs) -> ToolResult:
        """使用最佳工具执行任务"""
        tool = await self.select_tool(task_description)
        
        if not tool:
            return ToolResult(
                success=False,
                error="没有找到合适的工具",
                message=f"无法找到处理'{task_description}'的工具"
            )
        
        # 执行工具
        result = await tool.execute(**kwargs)
        
        # 记录使用历史
        self._record_usage(tool.metadata.name, result.success)
        
        return result
    
    def _record_usage(self, tool_name: str, success: bool):
        """记录工具使用历史"""
        if tool_name not in self._usage_history:
            self._usage_history[tool_name] = []
        
        self._usage_history[tool_name].append({
            'success': success,
            'timestamp': asyncio.get_event_loop().time()
        })
        
        # 保留最近100条记录
        if len(self._usage_history[tool_name]) > 100:
            self._usage_history[tool_name] = self._usage_history[tool_name][-100:]
    
    def get_tool_performance(self, tool_name: str) -> Dict[str, Any]:
        """获取工具性能统计"""
        history = self._usage_history.get(tool_name, [])
        if not history:
            return {
                'tool_name': tool_name,
                'total_uses': 0,
                'success_rate': 0.0,
                'avg_latency': 0.0
            }
        
        success_count = sum(1 for h in history if h.get('success'))
        return {
            'tool_name': tool_name,
            'total_uses': len(history),
            'success_rate': success_count / len(history),
            'avg_latency': 0.0  # 可以扩展记录延迟
        }


# 工具调用上下文
class ToolCallContext:
    """工具调用上下文"""
    
    def __init__(self, user_id: str = None, session_id: str = None, 
                 permissions: List[str] = None, metadata: Dict = None):
        self.user_id = user_id
        self.session_id = session_id
        self.permissions = permissions or []
        self.metadata = metadata or {}
        self.start_time = asyncio.get_event_loop().time()
        self.execution_stack = []
    
    def add_to_stack(self, tool_name: str):
        """添加到执行栈"""
        self.execution_stack.append(tool_name)
    
    def remove_from_stack(self):
        """从执行栈移除"""
        if self.execution_stack:
            return self.execution_stack.pop()
    
    def get_execution_time(self) -> float:
        """获取执行时间"""
        return asyncio.get_event_loop().time() - self.start_time
    
    def has_permission(self, permission: str) -> bool:
        """检查权限"""
        return permission in self.permissions


# 工具执行器
class ToolExecutor:
    """工具执行器 - 统一的工具执行入口"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.scheduler = ToolScheduler()
        return cls._instance
    
    async def execute(self, tool_name: str, context: Optional[ToolCallContext] = None, 
                      **kwargs) -> ToolResult:
        """执行指定工具"""
        tool = self.scheduler.registry.get(tool_name)
        
        if not tool:
            return ToolResult(
                success=False,
                error=f"工具 '{tool_name}' 不存在",
                message=f"未找到工具: {tool_name}"
            )
        
        # 检查权限
        if context:
            has_permission = await tool.check_permissions({
                'permissions': context.permissions,
                'user_id': context.user_id
            })
            if not has_permission:
                return ToolResult(
                    success=False,
                    error="权限不足",
                    message=f"您没有执行 {tool_name} 的权限"
                )
        
        # 添加到执行栈
        if context:
            context.add_to_stack(tool_name)
        
        try:
            result = await tool.execute(**kwargs)
            
            # 记录使用历史
            self.scheduler._record_usage(tool_name, result.success)
            
            return result
        finally:
            if context:
                context.remove_from_stack()
    
    async def execute_by_task(self, task_description: str, 
                             context: Optional[ToolCallContext] = None,
                             **kwargs) -> ToolResult:
        """根据任务描述自动选择并执行工具"""
        if context:
            context.add_to_stack(f"auto_select:{task_description}")
        
        try:
            result = await self.scheduler.execute_with_best_tool(task_description, **kwargs)
            return result
        finally:
            if context:
                context.remove_from_stack()
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取所有可用工具信息"""
        tools = self.scheduler.registry.list_all()
        return [self.scheduler.registry.get_tool_info(t.metadata.name) for t in tools]


# 便捷函数
def build_third_party_tool(name: str = "", description: str = "") -> ThirdPartyToolBuilder:
    """创建第三方工具构建器"""
    builder = ThirdPartyToolBuilder()
    if name:
        builder.name(name)
    if description:
        builder.description(description)
    return builder


def get_tool_executor() -> ToolExecutor:
    """获取工具执行器实例"""
    return ToolExecutor()


def get_tool_scheduler() -> ToolScheduler:
    """获取工具调度器实例"""
    return ToolScheduler()


# 示例工具
def create_example_tools():
    """创建示例工具"""
    
    # 文件读取工具
    read_file_tool = (
        build_tool("file_read", "读取文件内容")
        .category("file")
        .permission(ToolPermission.READ)
        .tag("read")
        .tag("file")
        .param("path", str, "文件路径", required=True)
        .param("encoding", str, "文件编码", required=False, default="utf-8")
        .output_field("content", str)
        .output_field("size", int)
        .executes(lambda path, encoding="utf-8": ToolResult(
            success=True,
            data={"content": "文件内容示例", "size": 100},
            message="文件读取成功"
        ))
        .renders_with(lambda result: f"📄 文件内容 ({result.data.get('size', 0)}字节):\n{result.data.get('content', '')[:100]}...")
        .build()
    )
    
    # 天气查询工具
    weather_tool = (
        build_tool("weather", "查询天气信息")
        .category("api")
        .tag("weather")
        .tag("query")
        .param("city", str, "城市名称", required=True)
        .param("days", int, "查询天数", required=False, default=1)
        .output_field("city", str)
        .output_field("temperature", float)
        .output_field("condition", str)
        .executes(lambda city, days=1: ToolResult(
            success=True,
            data={"city": city, "temperature": 25.5, "condition": "晴"},
            message=f"{city}天气查询成功"
        ))
        .renders_with(lambda result: f"🌤️ {result.data['city']}: {result.data['condition']}, {result.data['temperature']}°C")
        .build()
    )
    
    # 注册示例工具
    register_tool(read_file_tool)
    register_tool(weather_tool)
    
    return [read_file_tool, weather_tool]


# 示例第三方工具适配器
def create_example_third_party_adapter():
    """创建示例第三方工具适配器"""
    
    # 模拟第三方工具类
    class MockThirdPartyWeatherAPI:
        def get_weather(self, city: str):
            return {
                'city': city,
                'temp': 26.0,
                'condition': 'sunny',
                'humidity': 60
            }
    
    # 创建适配器
    weather_adapter = (
        build_third_party_tool("third_party_weather", "第三方天气API")
        .category("api")
        .tag("weather")
        .tag("third_party")
        .param("city", str, "城市名称", required=True)
        .native_tool(MockThirdPartyWeatherAPI)
        .converts_result_with(lambda native_result: ToolResult(
            success=True,
            data={
                "city": native_result['city'],
                "temperature": native_result['temp'],
                "condition": native_result['condition'],
                "humidity": native_result['humidity']
            },
            message=f"{native_result['city']}天气查询成功"
        ))
        .handles_errors_with(lambda e: ToolResult(
            success=False,
            error=str(e),
            message="第三方天气API调用失败"
        ))
        .build()
    )
    
    register_tool(weather_adapter)
    return weather_adapter
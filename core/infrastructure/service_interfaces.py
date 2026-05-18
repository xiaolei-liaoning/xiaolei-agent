"""服务接口定义 - 依赖注入的核心契约

所有核心服务都应实现对应的接口，确保：
- 依赖关系明确
- 易于测试和模拟
- 实现可替换
"""

from typing import Protocol, Dict, Any, List, Optional, runtime_checkable


@runtime_checkable
class ISkillDispatcher(Protocol):
    """技能分发器接口"""
    
    def match_skill(self, message: str) -> str:
        """匹配技能
        
        Args:
            message: 用户消息
            
        Returns:
            匹配的技能名称
        """
        ...
    
    def register_tool(self, name: str, keywords: List[str] = None,
                      priority: int = 3, description: str = "") -> None:
        """注册工具"""
        ...
    
    def is_multi_step(self, message: str) -> bool:
        """检测是否为多步任务"""
        ...
    
    def extract_params(self, message: str, skill_name: str) -> Dict[str, Any]:
        """提取参数"""
        ...


@runtime_checkable
class ITaskProcessor(Protocol):
    """任务处理器接口"""
    
    async def process(self, message: str) -> Any:
        """处理任务"""
        ...
    
    async def submit_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """提交多个任务"""
        ...


@runtime_checkable
class ITaskPlanner(Protocol):
    """任务规划器接口"""
    
    async def plan(self, goal: str) -> Dict[str, Any]:
        """规划任务"""
        ...
    
    async def decompose(self, task: str) -> List[Dict[str, Any]]:
        """分解任务"""
        ...


@runtime_checkable
class IBFSProcessor(Protocol):
    """BFS处理器接口"""
    
    def get_context(self, user_id: int, depth: int = 2, limit: int = 10) -> List[Dict[str, Any]]:
        """获取上下文"""
        ...
    
    def add_node(self, user_id: int, role: str, content: str, 
                 summary: str = "", metadata: Dict[str, Any] = None) -> Any:
        """添加节点"""
        ...


@runtime_checkable
class IRAGEngine(Protocol):
    """RAG搜索引擎接口"""
    
    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索知识库"""
        ...
    
    async def learn(self, content: str, metadata: Dict[str, Any] = None) -> bool:
        """学习新知识"""
        ...


@runtime_checkable
class ILLMBackend(Protocol):
    """LLM后端接口"""
    
    async def chat(self, messages: List[Dict[str, str]], model: str = "default") -> Dict[str, Any]:
        """聊天"""
        ...
    
    async def chat_stream(self, messages: List[Dict[str, str]], model: str = "default"):
        """流式聊天"""
        ...


@runtime_checkable
class IMessageBus(Protocol):
    """消息总线接口"""
    
    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        """发布消息"""
        ...
    
    async def subscribe(self, topic: str, callback: Any) -> None:
        """订阅主题"""
        ...


@runtime_checkable
class IDatabase(Protocol):
    """数据库接口"""
    
    def get_session(self) -> Any:
        """获取会话"""
        ...
    
    def is_initialized(self) -> bool:
        """是否已初始化"""
        ...


@runtime_checkable
class ICacheManager(Protocol):
    """缓存管理器接口"""
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        ...
    
    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """设置缓存"""
        ...
    
    def delete(self, key: str) -> None:
        """删除缓存"""
        ...


@runtime_checkable
class IMonitoringManager(Protocol):
    """监控管理器接口"""
    
    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None) -> None:
        """记录指标"""
        ...
    
    def start(self) -> None:
        """启动监控"""
        ...


@runtime_checkable
class ICircuitBreaker(Protocol):
    """熔断器接口"""
    
    def is_allowed(self) -> bool:
        """是否允许请求"""
        ...
    
    def record_success(self) -> None:
        """记录成功"""
        ...
    
    def record_failure(self) -> None:
        """记录失败"""
        ...


@runtime_checkable
class IAgentCoordinator(Protocol):
    """Agent协调器接口"""

    async def route_task(self, task_type: str, params: Dict[str, Any]) -> Any:
        """路由任务"""
        ...

    async def get_agent_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        ...


@runtime_checkable
class ISandboxExecutor(Protocol):
    """沙盒执行器接口"""

    async def execute_python(self, code: str, limits: Any = None,
                             context: Optional[Dict[str, Any]] = None,
                             skip_module_check: bool = False) -> Any:
        """执行Python代码"""
        ...

    async def execute_shell(self, command: str, limits: Any = None) -> Any:
        """执行Shell命令"""
        ...

    def check_forbidden_modules(self, code: str, limits: Any) -> List[str]:
        """检测禁止模块（不抛出异常）"""
        ...


@runtime_checkable
class IClarificationService(Protocol):
    """反问服务接口"""

    def generate_questions(self, message: str,
                          error_context: Optional[str] = None,
                          check_permission: bool = True) -> List[Any]:
        """生成反问问题"""
        ...

    async def handle_execution_failure(self, error_context: str,
                                       original_message: str,
                                       retry_count: int = 0) -> Optional[Any]:
        """处理执行失败的反问"""
        ...

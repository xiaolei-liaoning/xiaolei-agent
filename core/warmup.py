"""系统热启动 - 预加载常用数据

特性：
- 预加载工具管理器
- 预加载技能配置
- 预加载常用数据
- 预热连接池
- 缓存常用查询

使用方式：
    from core.warmup import warmup_system
    
    # 系统启动时调用
    await warmup_system()
"""

import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class WarmupManager:
    """热启动管理器"""
    
    def __init__(self):
        self._warmed_up = False
        self._cache: Dict[str, Any] = {}
        self._warmup_time: float = 0.0
        
        logger.info("WarmupManager 初始化完成")
    
    async def warmup(self) -> Dict[str, Any]:
        """执行热启动
        
        Returns:
            热启动结果
        """
        if self._warmed_up:
            logger.info("系统已热启动，跳过")
            return {"status": "already_warmed", "time": 0.0}
        
        start_time = datetime.now().timestamp()
        logger.info("开始系统热启动...")
        
        try:
            # 1. 预加载工具管理器
            await self._warmup_tool_manager()
            
            # 2. 预加载技能配置
            await self._warmup_skill_configs()
            
            # 3. 预加载常用数据
            await self._warmup_common_data()
            
            # 4. 预热连接池
            await self._warmup_connections()
            
            # 5. 预加载任务处理器
            await self._warmup_task_processor()
            
            # 6. 预加载任务队列
            await self._warmup_task_queue()
            
            self._warmup_time = datetime.now().timestamp() - start_time
            self._warmed_up = True
            
            logger.info("系统热启动完成 (耗时: %.2fs)", self._warmup_time)
            
            return {
                "status": "success",
                "time": self._warmup_time,
                "cache_size": len(self._cache),
            }
            
        except Exception as e:
            logger.error("系统热启动失败: %s", e)
            return {
                "status": "failed",
                "error": str(e),
                "time": datetime.now().timestamp() - start_time,
            }
    
    async def _warmup_tool_manager(self):
        """预加载工具管理器"""
        logger.info("预加载工具管理器...")
        
        try:
            from tools.tool_manager import ToolManager, register_all_skills
            
            # 获取单例
            tm = ToolManager.get_instance()
            
            # 注册所有技能
            register_all_skills()
            
            # 列出所有工具
            tools = tm.list_tools()
            
            # 缓存工具列表
            self._cache["tools"] = tools
            self._cache["tool_count"] = len(tools)
            
            logger.info("工具管理器预加载完成 (%d 个工具)", len(tools))
            
        except Exception as e:
            logger.error("工具管理器预加载失败: %s", e)
    
    async def _warmup_skill_configs(self):
        """预加载技能配置"""
        logger.info("预加载技能配置...")
        
        try:
            from core.skill_dispatcher import SKILL_CONFIGS
            
            # 缓存技能配置
            self._cache["skill_configs"] = SKILL_CONFIGS
            self._cache["skill_count"] = len(SKILL_CONFIGS)
            
            logger.info("技能配置预加载完成 (%d 个技能)", len(SKILL_CONFIGS))
            
        except Exception as e:
            logger.error("技能配置预加载失败: %s", e)
    
    async def _warmup_common_data(self):
        """预加载常用数据"""
        logger.info("预加载常用数据...")
        
        try:
            # 预加载常用城市列表（天气查询）
            common_cities = ["北京", "上海", "广州", "深圳", "杭州"]
            self._cache["common_cities"] = common_cities
            
            # 预加载常用网站（爬虫）
            common_sites = ["微博", "百度", "B站", "抖音", "知乎"]
            self._cache["common_sites"] = common_sites
            
            # 预加载常用翻译语言
            common_languages = ["en", "ja", "ko", "fr", "de"]
            self._cache["common_languages"] = common_languages
            
            logger.info("常用数据预加载完成")
            
        except Exception as e:
            logger.error("常用数据预加载失败: %s", e)
    
    async def _warmup_connections(self):
        """预热连接池"""
        logger.info("预热连接池...")
        
        try:
            # 预热数据库连接
            try:
                from core.database import init_db
                init_db()
                logger.info("数据库连接预热完成")
            except Exception as e:
                logger.warning("数据库连接预热失败: %s", e)
            
            # 预热 Redis 连接
            try:
                import redis
                redis_client = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True,
                )
                redis_client.ping()
                logger.info("Redis 连接预热完成")
            except Exception as e:
                logger.warning("Redis 连接预热失败: %s", e)
            
        except Exception as e:
            logger.error("连接池预热失败: %s", e)
    
    async def _warmup_task_processor(self):
        """预加载任务处理器"""
        logger.info("预加载任务处理器...")
        
        try:
            from core.task_processor import task_processor
            
            # 预加载 LLM 路由
            from core.llm_backend import get_llm_router
            router = get_llm_router()
            
            # 检查可用性
            is_available = router.is_available()
            
            # 缓存状态
            self._cache["llm_available"] = is_available
            self._cache["llm_model"] = router._model if hasattr(router, '_model') else None
            
            logger.info("任务处理器预加载完成 (LLM: %s)", is_available)
            
        except Exception as e:
            logger.error("任务处理器预加载失败: %s", e)
    
    async def _warmup_task_queue(self):
        """预加载任务队列"""
        logger.info("预加载任务队列...")
        
        try:
            from core.task_queue import task_queue
            
            # 启动队列处理器
            await task_queue.start()
            
            # 缓存队列状态
            self._cache["queue_started"] = True
            
            logger.info("任务队列预加载完成")
            
        except Exception as e:
            logger.error("任务队列预加载失败: %s", e)
    
    def get_cache(self, key: str) -> Any:
        """获取缓存"""
        return self._cache.get(key)
    
    def set_cache(self, key: str, value: Any):
        """设置缓存"""
        self._cache[key] = value
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("缓存已清空")
    
    def get_status(self) -> Dict[str, Any]:
        """获取热启动状态"""
        return {
            "warmed_up": self._warmed_up,
            "warmup_time": self._warmup_time,
            "cache_size": len(self._cache),
        }


# 全局实例
warmup_manager = WarmupManager()


async def warmup_system() -> Dict[str, Any]:
    """系统热启动（便捷函数）"""
    return await warmup_manager.warmup()
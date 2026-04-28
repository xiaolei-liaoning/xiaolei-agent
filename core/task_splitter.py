"""任务拆解模块 - 规则兜底 + LLM智能泛化（增强版）

新增功能：
1. 全局任务缓存
2. 任务执行结果缓存
3. 更智能的任务分解逻辑
"""

import logging
import hashlib
import time
from typing import List, Dict, Any, Optional
import json

from .llm_backend import get_llm_router

logger = logging.getLogger(__name__)


# 全局任务缓存（类级别）
_global_task_cache = {}
_global_cache_access_order = []
_global_cache_max_size = 500
_global_cache_ttl = 7200  # 2小时


def _global_clean_expired_cache():
    """清理全局缓存中的过期项"""
    current_time = time.time()
    expired_keys = []
    
    for cache_key, cached_data in _global_task_cache.items():
        if current_time - cached_data["timestamp"] > _global_cache_ttl:
            expired_keys.append(cache_key)
    
    for cache_key in expired_keys:
        del _global_task_cache[cache_key]
        if cache_key in _global_cache_access_order:
            _global_cache_access_order.remove(cache_key)
    
    if expired_keys:
        logger.info(f"全局缓存清理了 {len(expired_keys)} 个过期项")


def _global_get_cache_stats() -> Dict[str, Any]:
    """获取全局缓存统计"""
    current_time = time.time()
    expired_count = sum(1 for cached_data in _global_task_cache.values() 
                      if current_time - cached_data["timestamp"] > _global_cache_ttl)
    
    return {
        "cache_size": len(_global_task_cache),
        "max_size": _global_cache_max_size,
        "expired_count": expired_count,
        "ttl": _global_cache_ttl
    }


class TaskSplitter:
    """任务拆解器（增强版）"""
    
    def __init__(self, cache_max_size: int = 100, cache_ttl: int = 3600):
        # 任务拆解规则（扩展版）
        self.split_rules = {
            "research_topic": {
                "description": "研究一个主题",
                "steps": [
                    {"type": "search", "params": {"query": "$topic"}},
                    {"type": "scrape", "params": {"url": "$search_result"}},
                    {"type": "analyze", "params": {"data": "$scraped_content"}},
                    {"type": "summarize", "params": {"text": "$analysis_result"}}
                ],
                "requires_context": False
            },
            "compare_products": {
                "description": "比较两个产品",
                "steps": [
                    {"type": "search", "params": {"query": "$product1"}},
                    {"type": "search", "params": {"query": "$product2"}},
                    {"type": "scrape", "params": {"url": "$search_result1"}},
                    {"type": "scrape", "params": {"url": "$search_result2"}},
                    {"type": "analyze", "params": {"data": "$scraped_content1"}},
                    {"type": "analyze", "params": {"data": "$scraped_content2"}},
                    {"type": "summarize", "params": {"text": "$analysis_result1"}},
                    {"type": "summarize", "params": {"text": "$analysis_result2"}},
                    {"type": "compare", "params": {"item1": "$summary1", "item2": "$summary2"}}
                ],
                "requires_context": False
            },
            "analyze_website": {
                "description": "分析网站内容",
                "steps": [
                    {"type": "scrape", "params": {"url": "$url"}},
                    {"type": "analyze", "params": {"data": "$scraped_content"}},
                    {"type": "summarize", "params": {"text": "$analysis_result"}}
                ],
                "requires_context": False
            },
            "research_ai": {
                "description": "研究AI相关主题",
                "steps": [
                    {"type": "search", "params": {"query": "人工智能最新发展"}},
                    {"type": "search", "params": {"query": "人工智能应用领域"}},
                    {"type": "search", "params": {"query": "人工智能未来趋势"}},
                    {"type": "scrape", "params": {"url": "$search_result1"}},
                    {"type": "scrape", "params": {"url": "$search_result2"}},
                    {"type": "scrape", "params": {"url": "$search_result3"}},
                    {"type": "analyze", "params": {"data": "$scraped_content1"}},
                    {"type": "analyze", "params": {"data": "$scraped_content2"}},
                    {"type": "analyze", "params": {"data": "$scraped_content3"}},
                    {"type": "summarize", "params": {"text": "$analysis_result1"}},
                    {"type": "summarize", "params": {"text": "$analysis_result2"}},
                    {"type": "summarize", "params": {"text": "$analysis_result3"}},
                    {"type": "summarize", "params": {"text": "$summary1 $summary2 $summary3"}}
                ],
                "requires_context": False
            },
            "multi_step_action": {
                "description": "多步骤操作任务",
                "steps": [
                    {"type": "search", "params": {"query": "$query1"}},
                    {"type": "process", "params": {"input": "$search_result"}},
                    {"type": "summarize", "params": {"text": "$processed_result"}}
                ],
                "requires_context": True
            },
            "data_pipeline": {
                "description": "数据处理管道",
                "steps": [
                    {"type": "fetch", "params": {"source": "$source"}},
                    {"type": "process", "params": {"data": "$fetched_data"}},
                    {"type": "analyze", "params": {"data": "$processed_data"}},
                    {"type": "generate", "params": {"input": "$analysis_result"}}
                ],
                "requires_context": False
            }
        }
        self.router = get_llm_router()
        
        # 本地缓存配置
        self.cache_max_size = cache_max_size
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._cache_access_order = []
        
        # 任务执行结果缓存
        self._execution_cache = {}
    
    def _generate_cache_key(self, task_type: str, params: Dict[str, Any]) -> str:
        """生成缓存键
        
        Args:
            task_type: 任务类型
            params: 任务参数
            
        Returns:
            缓存键
        """
        params_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        key_str = f"{task_type}:{params_str}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_from_cache(self, cache_key: str) -> List[Dict[str, Any]]:
        """从缓存获取
        
        Args:
            cache_key: 缓存键
            
        Returns:
            缓存的子任务列表，如果不存在或过期则返回None
        """
        if cache_key not in self._cache:
            return None
        
        cached_data = self._cache[cache_key]
        
        # 检查是否过期
        if time.time() - cached_data["timestamp"] > self.cache_ttl:
            del self._cache[cache_key]
            if cache_key in self._cache_access_order:
                self._cache_access_order.remove(cache_key)
            return None
        
        # 更新访问顺序（LRU）
        if cache_key in self._cache_access_order:
            self._cache_access_order.remove(cache_key)
        self._cache_access_order.append(cache_key)
        
        logger.info(f"缓存命中: {cache_key}")
        return cached_data["sub_tasks"]
    
    def _save_to_cache(self, cache_key: str, sub_tasks: List[Dict[str, Any]]):
        """保存到缓存
        
        Args:
            cache_key: 缓存键
            sub_tasks: 子任务列表
        """
        # 检查缓存大小限制
        if len(self._cache) >= self.cache_max_size and cache_key not in self._cache:
            # 移除最久未使用的缓存项
            oldest_key = self._cache_access_order.pop(0)
            del self._cache[oldest_key]
            logger.info(f"缓存已满，移除最久未使用的项: {oldest_key}")
        
        # 保存到缓存
        self._cache[cache_key] = {
            "sub_tasks": sub_tasks,
            "timestamp": time.time()
        }
        
        # 更新访问顺序
        if cache_key in self._cache_access_order:
            self._cache_access_order.remove(cache_key)
        self._cache_access_order.append(cache_key)
        
        logger.info(f"保存到缓存: {cache_key}")
    
    def _clean_expired_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = []
        
        for cache_key, cached_data in self._cache.items():
            if current_time - cached_data["timestamp"] > self.cache_ttl:
                expired_keys.append(cache_key)
        
        for cache_key in expired_keys:
            del self._cache[cache_key]
            if cache_key in self._cache_access_order:
                self._cache_access_order.remove(cache_key)
        
        if expired_keys:
            logger.info(f"清理了 {len(expired_keys)} 个过期缓存项")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息
        
        Returns:
            缓存统计信息
        """
        current_time = time.time()
        expired_count = sum(1 for cached_data in self._cache.values() 
                          if current_time - cached_data["timestamp"] > self.cache_ttl)
        
        return {
            "cache_size": len(self._cache),
            "max_size": self.cache_max_size,
            "expired_count": expired_count,
            "ttl": self.cache_ttl
        }
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._cache_access_order.clear()
        logger.info("缓存已清空")
    
    async def split(self, task_type: str, params: Dict[str, Any], 
                    context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """拆解任务（增强版）
        
        Args:
            task_type: 任务类型
            params: 任务参数
            context: 上下文信息（可选）
            
        Returns:
            子任务列表
        """
        # 1. 清理过期缓存
        self._clean_expired_cache()
        _global_clean_expired_cache()
        
        # 2. 检查全局缓存
        global_cache_key = self._generate_global_cache_key(task_type, params)
        global_cached = self._get_from_global_cache(global_cache_key)
        if global_cached is not None:
            logger.info(f"使用全局缓存拆解任务 {task_type}，生成 {len(global_cached)} 个子任务")
            return global_cached
        
        # 3. 规则兜底
        if task_type in self.split_rules:
            sub_tasks = self._split_by_rule(task_type, params)
            
            # 验证子任务
            if self._validate_subtasks(sub_tasks):
                logger.info(f"使用规则拆解任务 {task_type}，生成 {len(sub_tasks)} 个子任务")
                self._save_to_global_cache(global_cache_key, sub_tasks)
                return sub_tasks
            else:
                logger.warning("规则拆解的子任务验证失败，尝试LLM路径")
        
        # 4. 检查本地缓存
        cache_key = self._generate_cache_key(task_type, params)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            logger.info(f"使用本地缓存拆解任务 {task_type}，生成 {len(cached_result)} 个子任务")
            self._save_to_global_cache(global_cache_key, cached_result)
            return cached_result
        
        # 5. LLM智能泛化（带上下文）
        sub_tasks = await self._split_by_llm(task_type, params, context)
        
        # 6. 验证并修复
        if not self._validate_subtasks(sub_tasks):
            sub_tasks = self._fix_subtasks(sub_tasks)
        
        # 7. 保存到缓存
        self._save_to_cache(cache_key, sub_tasks)
        self._save_to_global_cache(global_cache_key, sub_tasks)
        
        logger.info(f"使用LLM拆解任务 {task_type}，生成 {len(sub_tasks)} 个子任务")
        return sub_tasks
    
    def _validate_subtasks(self, sub_tasks: List[Dict[str, Any]]) -> bool:
        """验证子任务列表
        
        Args:
            sub_tasks: 子任务列表
            
        Returns:
            是否有效
        """
        if not sub_tasks:
            return False
        
        # 检查每个子任务是否有必要字段
        for i, task in enumerate(sub_tasks):
            if "type" not in task:
                logger.error(f"子任务 {i} 缺少 type 字段")
                return False
            if "params" not in task:
                task["params"] = {}
        
        return True
    
    def _fix_subtasks(self, sub_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """修复子任务列表
        
        Args:
            sub_tasks: 子任务列表
            
        Returns:
            修复后的子任务列表
        """
        fixed = []
        for i, task in enumerate(sub_tasks):
            fixed_task = {
                "type": task.get("type", "process"),
                "params": task.get("params", {}),
                "step": i + 1,
                "total_steps": len(sub_tasks)
            }
            fixed.append(fixed_task)
        
        return fixed
    
    def _generate_global_cache_key(self, task_type: str, params: Dict[str, Any]) -> str:
        """生成全局缓存键"""
        params_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        key_str = f"GLOBAL:{task_type}:{params_str}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_from_global_cache(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """从全局缓存获取"""
        if cache_key not in _global_task_cache:
            return None
        
        cached_data = _global_task_cache[cache_key]
        
        # 检查是否过期
        if time.time() - cached_data["timestamp"] > _global_cache_ttl:
            del _global_task_cache[cache_key]
            if cache_key in _global_cache_access_order:
                _global_cache_access_order.remove(cache_key)
            return None
        
        # 更新访问顺序
        if cache_key in _global_cache_access_order:
            _global_cache_access_order.remove(cache_key)
        _global_cache_access_order.append(cache_key)
        
        return cached_data["sub_tasks"]
    
    def _save_to_global_cache(self, cache_key: str, sub_tasks: List[Dict[str, Any]]):
        """保存到全局缓存"""
        # 检查缓存大小限制
        if len(_global_task_cache) >= _global_cache_max_size and cache_key not in _global_task_cache:
            oldest_key = _global_cache_access_order.pop(0)
            del _global_task_cache[oldest_key]
            logger.info(f"全局缓存已满，移除最久未使用的项: {oldest_key}")
        
        _global_task_cache[cache_key] = {
            "sub_tasks": sub_tasks,
            "timestamp": time.time()
        }
        
        if cache_key in _global_cache_access_order:
            _global_cache_access_order.remove(cache_key)
        _global_cache_access_order.append(cache_key)
    
    def cache_execution_result(self, task_type: str, params: Dict[str, Any], 
                               result: Any, success: bool):
        """缓存任务执行结果
        
        Args:
            task_type: 任务类型
            params: 任务参数
            result: 执行结果
            success: 是否成功
        """
        cache_key = self._generate_cache_key(task_type, params)
        self._execution_cache[cache_key] = {
            "result": result,
            "success": success,
            "timestamp": time.time()
        }
        logger.debug(f"已缓存任务执行结果: {task_type}")
    
    def get_cached_execution(self, task_type: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取缓存的执行结果
        
        Args:
            task_type: 任务类型
            params: 任务参数
            
        Returns:
            缓存的执行结果，如果不存在或过期返回None
        """
        cache_key = self._generate_cache_key(task_type, params)
        if cache_key not in self._execution_cache:
            return None
        
        cached = self._execution_cache[cache_key]
        
        # 检查是否过期（1小时）
        if time.time() - cached["timestamp"] > 3600:
            del self._execution_cache[cache_key]
            return None
        
        return cached
    
    def _split_by_rule(self, task_type: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """基于规则拆解任务（支持新旧格式）"""
        sub_tasks = []
        
        # 获取规则配置
        rule_config = self.split_rules.get(task_type)
        if not rule_config:
            return []
        
        # 获取步骤列表（支持新旧两种格式）
        if isinstance(rule_config, dict) and "steps" in rule_config:
            rule = rule_config["steps"]
        elif isinstance(rule_config, list):
            rule = rule_config
        else:
            return []
        
        for i, sub_task_template in enumerate(rule):
            sub_task = {
                "type": sub_task_template["type"],
                "params": {}
            }
            
            # 替换参数中的占位符
            for key, value in sub_task_template["params"].items():
                if value.startswith("$"):
                    # 从原始参数中获取值
                    param_name = value[1:]
                    sub_task["params"][key] = params.get(param_name, value)
                else:
                    sub_task["params"][key] = value
            
            # 添加步骤信息
            sub_task["step_number"] = i + 1
            sub_task["total_steps"] = len(rule)
            
            sub_tasks.append(sub_task)
            logger.info(f"生成子任务 {i+1}: {sub_task['type']} - {sub_task['params']}")
        
        return sub_tasks
    
    async def _split_by_llm(self, task_type: str, params: Dict[str, Any], 
                           context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """基于LLM智能拆解任务（增强版，支持上下文）"""
        try:
            # 构建上下文信息
            context_info = ""
            if context:
                context_info = f"\n上下文信息：{json.dumps(context, ensure_ascii=False)}"
            
            prompt = f"""请将以下任务拆解为具体的子任务步骤。

任务类型：{task_type}
任务参数：{json.dumps(params, ensure_ascii=False)}{context_info}

要求：
1. 分解为多个具体的子任务，每个子任务必须包含 type 和 params 字段
2. 子任务应该按逻辑执行顺序排列
3. 子任务类型可以是：search, scrape, analyze, summarize, compare, fetch, process, generate, transform 等
4. params 中可以使用 $ 开头的占位符表示依赖前序任务的结果
5. 复杂任务考虑并发执行可能性
6. 返回JSON格式，不要包含其他内容

示例输出：
[
  {{"type": "search", "params": {{"query": "关键词"}}}},
  {{"type": "scrape", "params": {{"url": "$search_result"}}}},
  {{"type": "analyze", "params": {{"data": "$scraped_content"}}}},
  {{"type": "summarize", "params": {{"text": "$analysis_result"}}}}
]
"""
            
            response = await self.router.simple_chat(
                user_message=prompt,
                system_prompt="你是任务拆解专家，擅长将复杂任务分解为可执行的子任务序列。只返回JSON格式的子任务列表，不要包含其他内容。",
                temperature=0.4,
            )
            
            if not response or not response.strip():
                raise ValueError("LLM返回空响应")
            
            # 处理可能的markdown代码块
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            sub_tasks = json.loads(response)
            
            # 验证输出格式
            if not isinstance(sub_tasks, list):
                raise ValueError("LLM返回格式错误")
            
            # 为每个子任务添加默认值和元信息
            for i, sub_task in enumerate(sub_tasks):
                if "type" not in sub_task:
                    sub_task["type"] = "process"
                if "params" not in sub_task:
                    sub_task["params"] = {}
                # 添加步骤信息
                sub_task["step_number"] = i + 1
                sub_task["total_steps"] = len(sub_tasks)
                logger.info(f"LLM生成子任务 {i+1}/{len(sub_tasks)}: {sub_task['type']} - {sub_task['params']}")
            
            return sub_tasks
        except Exception as e:
            logger.error(f"LLM任务拆解失败: {e}")
            # 降级为单任务
            return [{"type": task_type, "params": params, "step_number": 1, "total_steps": 1}]
    
    def get_global_cache_stats(self) -> Dict[str, Any]:
        """获取全局缓存统计"""
        return _global_get_cache_stats()
    
    def clear_global_cache(self):
        """清空全局缓存"""
        global _global_task_cache, _global_cache_access_order
        _global_task_cache.clear()
        _global_cache_access_order.clear()
        logger.info("全局任务缓存已清空")
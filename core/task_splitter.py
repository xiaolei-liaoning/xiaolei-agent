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
        # 预定义的拆解规则（增强版：注入系统Agent实现分层处理）
        self.decomposition_rules = {
            "research_topic": {
                "description": "研究主题任务（分层处理）",
                "steps": [
                    # 阶段1: 任务规划（PlanningAgent - 系统Agent）
                    {
                        "type": "create_plan",
                        "params": {
                            "goal": "研究主题: $query",
                            "constraints": ["需要搜索", "需要分析", "需要总结"]
                        }
                    },
                    # 阶段2: 功能执行（ScraperAgent - 功能Agent）
                    {
                        "type": "search",
                        "params": {
                            "query": "$query"
                        }
                    },
                    # 阶段3: 数据分析（DataAnalysisAgent - 功能Agent）
                    {
                        "type": "analyze",
                        "params": {
                            "task": "研究主题: $query"
                        }
                    },
                    # 阶段4: 安全检查（VulnerabilityAgent - 系统Agent）
                    {
                        "type": "scan",
                        "params": {
                            "target": "分析结果"
                        }
                    },
                    # 阶段5: 总结报告（SummarizerAgent - 系统Agent）
                    {
                        "type": "summary",
                        "params": {
                            "text": "安全检查后的最终结果"
                        }
                    }
                ],
                "requires_context": True
            },
            "data_analysis": {
                "description": "数据分析任务（分层处理）",
                "steps": [
                    # 阶段1: 文本/意图分析
                    {
                        "type": "analyze_text",
                        "params": {
                            "text": "数据分析任务: $query"
                        }
                    },
                    # 阶段2: 核心数据分析
                    {
                        "type": "analyze",
                        "params": {
                            "data": "$query"
                        }
                    },
                    # 阶段3: 安全检查
                    {
                        "type": "scan",
                        "params": {
                            "target": "$query"
                        }
                    },
                    # 阶段4: 总结报告
                    {
                        "type": "summary",
                        "params": {
                            "text": "$query"
                        }
                    }
                ],
                "requires_context": False
            },
            "compare_products": {
                "description": "比较多个产品",
                "steps": [
                    {"type": "search", "params": {"query": "$product1"}},
                    {"type": "search", "params": {"query": "$product2"}},
                    {"type": "analyze", "params": {"data": "比较 $product1 和 $product2"}},
                    {"type": "summary", "params": {"text": "产品对比分析结果"}}
                ],
                "requires_context": False
            },
            "analyze_news": {
                "description": "分析新闻事件",
                "steps": [
                    {"type": "search", "params": {"query": "$event"}},
                    {"type": "analyze_text", "params": {"text": "$event"}},
                    {"type": "summary", "params": {"text": "$event"}}
                ],
                "requires_context": False
            },
            "data_pipeline": {
                "description": "数据处理管道",
                "steps": [
                    {"type": "search", "params": {"query": "$source"}},
                    {"type": "analyze_text", "params": {"text": "$fetched_data"}},
                    {"type": "analyze", "params": {"data": "$processed_data"}},
                    {"type": "summary", "params": {"text": "$analysis_result"}}
                ],
                "requires_context": False
            },
            "research_with_dependencies": {
                "description": "真实数据依赖的复杂任务",
                "steps": [
                    {
                        "type": "search",
                        "params": {
                            "query": "$query"
                        }
                    },
                    {
                        "type": "scrape",
                        "params": {
                            "urls": "$search_result"  # 真正依赖search的结果
                        }
                    },
                    {
                        "type": "analyze",
                        "params": {
                            "content": "$scraped_content"  # 真正依赖scrape的结果
                        }
                    },
                    {
                        "type": "scan",
                        "params": {
                            "target": "$analysis_result"  # 真正依赖analyze的结果
                        }
                    }
                ],
                "requires_context": True
            },
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
        # 深度复制并标准化参数，确保相同内容生成相同键
        normalized_params = self._normalize_params(params)
        params_str = json.dumps(normalized_params, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        key_str = f"{task_type}:{params_str}"
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
    
    def _normalize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """标准化参数，确保缓存键一致性"""
        if not isinstance(params, dict):
            return {}
        
        normalized = {}
        for key, value in params.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                normalized[key] = value
            elif isinstance(value, (list, tuple)):
                normalized[key] = [self._normalize_value(v) for v in value]
            elif isinstance(value, dict):
                normalized[key] = self._normalize_params(value)
            else:
                # 对于复杂对象，转换为字符串表示
                normalized[key] = str(value)
        return normalized
    
    def _normalize_value(self, value: Any) -> Any:
        """标准化单个值"""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, (list, tuple)):
            return [self._normalize_value(v) for v in value]
        elif isinstance(value, dict):
            return self._normalize_params(value)
        else:
            return str(value)
    
    def _generate_global_cache_key(self, task_type: str, params: Dict[str, Any]) -> str:
        """生成全局缓存键"""
        normalized_params = self._normalize_params(params)
        params_str = json.dumps(normalized_params, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        key_str = f"GLOBAL:{task_type}:{params_str}"
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
    
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
    
    async def split(self, task_type: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """拆解复杂任务为子任务序列"""
        if task_type not in self.decomposition_rules:
            # 不支持的任务类型，返回原任务
            return [{"type": task_type, "params": params}]
        
        rule = self.decomposition_rules[task_type]
        steps = rule["steps"]
        
        # 替换占位符
        processed_steps = []
        for step in steps:
            processed_step = step.copy()
            processed_step["params"] = self._replace_placeholders(step["params"], params)
            processed_steps.append(processed_step)
        
        return processed_steps
    
    def _replace_placeholders(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """替换参数中的占位符"""
        import re
        
        result = {}
        for key, value in params.items():
            if isinstance(value, str):
                # 在字符串中查找并替换所有 $xxx 占位符
                def replace_match(match):
                    placeholder_name = match.group(1)
                    if placeholder_name in context:
                        return str(context[placeholder_name])
                    else:
                        return match.group(0)  # 保持原样
                
                replaced_value = re.sub(r'\$(\w+)', replace_match, value)
                result[key] = replaced_value
            else:
                result[key] = value
        return result
    
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
        """根据预定义规则拆解任务"""
        # 获取规则配置
        rule_config = self.decomposition_rules.get(task_type)  # 修正：split_rules → decomposition_rules
        
        if not rule_config:
            return []
        
        # 获取步骤列表（支持新旧两种格式）
        if isinstance(rule_config, dict) and "steps" in rule_config:
            rule = rule_config["steps"]
        elif isinstance(rule_config, list):
            rule = rule_config
        else:
            return []
        
        # 初始化sub_tasks列表
        sub_tasks = []
        for i, sub_task_template in enumerate(rule):
            sub_task = {
                "type": sub_task_template["type"],
                "params": {}
            }
            
            # 替换参数中的占位符
            for key, value in sub_task_template["params"].items():
                if isinstance(value, str) and value.startswith("$"):
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
4. 功能Agent使用独立参数，不需要复杂的依赖处理，请勿添加 id 或 depends_on 字段
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
            
            # 处理可能的代码块
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
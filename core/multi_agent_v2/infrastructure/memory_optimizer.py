"""
MemoryOptimizer - 状态压缩与内存优化
冷热数据分离，减少内存占用
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)


class MemoryStage(Enum):
    """数据存储阶段"""
    HOT = "hot"        # 热数据 - 在内存中
    WARM = "warm"      # 温数据 - 在Redis中
    COLD = "cold"      # 冷数据 - 在磁盘中


@dataclass
class CompressedState:
    """压缩后的状态"""
    agent_id: str
    core_data: Dict[str, Any]
    hot_data: List[Dict]
    warm_data_key: Optional[str] = None
    cold_data_key: Optional[str] = None
    compression_ratio: float = 0.0
    created_at: float = 0.0


class MemoryOptimizer:
    """内存优化器
    
    核心功能：
    - 状态压缩
    - 冷热分离
    - 自动降级
    """
    
    def __init__(
        self,
        hot_threshold: int = 10,  # 热数据数量
        warm_ttl: int = 3600,     # 温数据TTL（秒）
        cold_ttl: int = 86400,  # 冷数据TTL（秒）
    ):
        self.hot_threshold = hot_threshold
        self.warm_ttl = warm_ttl
        self.cold_ttl = cold_ttl
        
        # 存储引用（实际存储在SharedComponents中
        self._shared = None
    
    def _get_shared(self):
        """获取共享组件"""
        if self._shared is None:
            from core.multi_agent_v2.infrastructure.shared_components import get_shared
            self._shared = get_shared()
        return self._shared
    
    async def compress_agent_state(self, agent) -> CompressedState:
        """压缩Agent状态
        
        Args:
            agent: Agent实例
            
        Returns:
            CompressedState
        """
        start_time = time.time()
        
        # 获取完整状态
        full_state = await self._get_full_state(agent)
        
        # 分离数据
        hot_data, warm_data, cold_data = self._split_data(full_state)
        
        # 保存温数据到Redis
        warm_key = None
        if warm_data:
            warm_key = await self._save_warm_data(agent.agent_id, warm_data)
        
        # 保存冷数据（模拟保存）
        cold_key = None
        if cold_data:
            cold_key = await self._save_cold_data(agent.agent_id, cold_data)
        
        # 计算压缩率
        original_size = self._estimate_size(full_state)
        compressed_size = self._estimate_size(hot_data)
        compression_ratio = 1.0 - (compressed_size / original_size) if original_size > 0 else 0
        
        # 组装压缩状态
        compressed = CompressedState(
            agent_id=agent.agent_id,
            core_data=self._extract_core_data(agent, full_state),
            hot_data=hot_data,
            warm_data_key=warm_key,
            cold_data_key=cold_key,
            compression_ratio=compression_ratio,
            created_at=time.time()
        )
        
        elapsed = time.time() - start_time
        logger.debug(f"State compressed: {compressed.compression_ratio:.1%} ({elapsed:.2f}s")
        
        return compressed
    
    async def restore_agent_state(self, agent, compressed: CompressedState) -> None:
        """恢复Agent状态
        
        Args:
            agent: Agent实例
            compressed: 压缩状态
        """
        logger.info(f"Restoring state for {agent.agent_id}")
        
        # 恢复核心数据
        await self._restore_core_data(agent, compressed.core_data)
        
        # 恢复热数据
        await self._restore_hot_data(agent, compressed.hot_data)
        
        # 按需恢复温数据
        if compressed.warm_data_key:
            warm_data = await self._load_warm_data(compressed.warm_data_key)
            if warm_data:
                await self._restore_warm_data(agent, warm_data)
        
        logger.debug(f"State restored for {agent.agent_id}")
    
    def _split_data(self, full_state: Dict) -> Tuple[List, List, List]:
        """数据分离
        
        Returns:
            (热数据, 温数据, 冷数据)
        """
        history = full_state.get('history', [])
        
        if isinstance(history, list):
            # 最新的10条是热数据
            hot_data = history[-self.hot_threshold:] if len(history) > self.hot_threshold else history
            
            # 接下来的100条是温数据
            warm_start = max(0, len(history) - self.hot_threshold - 100)
            warm_data = history[warm_start:-self.hot_threshold] if len(history) else []
            
            # 更早的是冷数据
            cold_data = history[:warm_start] if len(history) else []
        else:
            hot_data = []
            warm_data = []
            cold_data = []
        
        return hot_data, warm_data, cold_data
    
    def _extract_core_data(self, agent, full_state: Dict) -> Dict:
        """提取核心数据"""
        return {
            'agent_id': full_state.get('agent_id', agent.agent_id),
            'state': full_state.get('state', 'idle'),
            'capabilities': full_state.get('capabilities', []),
            'last_activity': time.time()
        }
    
    async def _save_warm_data(self, agent_id: str, data: List) -> Optional[str]:
        """保存温数据到Redis"""
        shared = self._get_shared()
        if not shared.redis_storage:
            logger.warning("Redis storage not initialized")
            return None
        
        key = f"warm:{agent_id}"
        try:
            await shared.redis_storage.set(
                key,
                json.dumps(data),
                ttl=self.warm_ttl
            )
            return key
        except Exception as e:
            logger.warning(f"Failed to save warm data: {e}")
            return None
    
    async def _load_warm_data(self, key: str) -> Optional[List]:
        """从Redis加载温数据"""
        try:
            shared = self._get_shared()
            data_str = await shared.redis_storage.get(key)
            if data_str:
                return json.loads(data_str)
        except Exception as e:
            logger.warning(f"Failed to load warm data: {e}")
        return None
    
    async def _save_cold_data(self, agent_id: str, data: List) -> Optional[str]:
        """保存冷数据（模拟）"""
        # 实际项目中可以保存到文件、S3等
        # 这里只返回一个key
        key = f"cold:{agent_id}"
        return key
    
    async def _get_full_state(self, agent) -> Dict:
        """获取Agent的完整状态"""
        state = {}
        
        if hasattr(agent, 'get_state'):
            state = agent.get_state()
        elif hasattr(agent, 'memory'):
            state['history'] = getattr(agent.memory, 'short_term', [])
        
        return state
    
    async def _restore_core_data(self, agent, core_data: Dict) -> None:
        """恢复核心数据"""
        if hasattr(agent, 'state'):
            from core.multi_agent_v2.agents.base.base_agent import AgentState
            try:
                agent.state = AgentState(core_data.get('state', 'idle'))
            except:
                agent.state = AgentState.IDLE
    
    async def _restore_hot_data(self, agent, hot_data: List) -> None:
        """恢复热数据"""
        if hasattr(agent, 'memory') and hasattr(agent.memory, 'short_term'):
            agent.memory.short_term = hot_data
    
    async def _restore_warm_data(self, agent, warm_data: List) -> None:
        """恢复温数据"""
        pass
    
    def _estimate_size(self, data) -> int:
        """估算数据大小（字节）"""
        import sys
        try:
            return len(json.dumps(data))
        except:
            return 0


class StateTracker:
    """状态追踪器"""
    
    def __init__(self):
        self.agent_states: Dict[str, CompressedState] = {}
        self.last_usage_stats: Dict[str, Dict] = {}
    
    def track(self, compressed: CompressedState) -> None:
        """追踪压缩状态"""
        self.agent_states[compressed.agent_id] = compressed
        
        stats = {
            'last_compressed': time.time(),
            'compression_ratio': compressed.compression_ratio,
            'has_warm': bool(compressed.warm_data_key is not None),
            'has_cold': bool(compressed.cold_data_key is not None)
        }
        
        self.last_usage_stats[compressed.agent_id] = stats
    
    def get_summary(self) -> Dict[str, Any]:
        """获取摘要"""
        total_agents = len(self.agent_states)
        avg_ratio = sum(
            s.compression_ratio for s in self.agent_states.values()
        ) / total_agents if total_agents > 0 else 0
        
        return {
            'total_agents': total_agents,
            'avg_compression_ratio': round(avg_ratio, 3),
            'with_warm_data': sum(
                1 for s in self.agent_states.values()
                if s.warm_data_key
            ),
            'with_cold_data': sum(
                1 for s in self.agent_states.values()
                if s.cold_data_key
            )
        }


# 快捷函数
_global_optimizer: Optional[MemoryOptimizer] = None
_global_tracker: Optional[StateTracker] = None


def get_memory_optimizer() -> MemoryOptimizer:
    """获取内存优化器"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = MemoryOptimizer()
    return _global_optimizer


def get_state_tracker() -> StateTracker:
    """获取状态追踪器"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = StateTracker()
    return _global_tracker

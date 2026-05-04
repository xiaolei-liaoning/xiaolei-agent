"""边界管理器模块

实现模块间的调用规则和限制
包括调用优先级、互斥规则和速率限制
"""

import logging
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class BoundaryManager:
    """边界管理器"""
    
    def __init__(self):
        self.priority_rules = {
            "deep_thinking": 1,
            "search_engine": 2,
            "weather": 3,
            "web_scraper": 3,
            "data_analysis": 3,
            "gui_automation": 3,
            "translator": 6,
            "advanced_automation": 7,
            "rag_search": 3,
            "system_toolbox": 3,
            "libai": 4,
            "goddess": 4,
            "first_love": 4,
            "bestfriend": 4,
            "linus_torvalds": 4,
            "john_carmack": 4
        }
        
        # 互斥规则：(skill1, skill2) 表示这两个技能不能同时执行
        self.mutex_rules = {
            ("gui_automation", "deep_thinking"),
            ("gui_automation", "search_engine"),
            ("advanced_automation", "deep_thinking"),
            ("advanced_automation", "search_engine")
        }
        
        # 速率限制：{skill: (max_calls, time_window)}
        self.rate_limits = {
            "deep_thinking": (10, 60),  # 每分钟10次
            "search_engine": (30, 60),  # 每分钟30次
            "weather": (60, 60),        # 每分钟60次
            "web_scraper": (20, 60),     # 每分钟20次
            "data_analysis": (15, 60),    # 每分钟15次
            "gui_automation": (5, 60),    # 每分钟5次
            "translator": (60, 60),       # 每分钟60次
            "advanced_automation": (5, 60),  # 每分钟5次
            "rag_search": (30, 60),       # 每分钟30次
            "system_toolbox": (60, 60),    # 每分钟60次
            "libai": (20, 60),            # 每分钟20次
            "goddess": (20, 60),          # 每分钟20次
            "first_love": (20, 60),        # 每分钟20次
            "bestfriend": (20, 60),        # 每分钟20次
            "linus_torvalds": (20, 60),    # 每分钟20次
            "john_carmack": (20, 60)       # 每分钟20次
        }
        
        # 调用计数，用于速率限制
        self.call_counts = {}
        
        logger.info("边界管理器初始化完成")
    
    def get_priority(self, skill: str) -> int:
        """获取技能优先级
        
        Args:
            skill: 技能名称
            
        Returns:
            优先级，值越小优先级越高
        """
        return self.priority_rules.get(skill, 5)
    
    def is_mutex(self, skill1: str, skill2: str) -> bool:
        """检查两个技能是否互斥
        
        Args:
            skill1: 第一个技能
            skill2: 第二个技能
            
        Returns:
            是否互斥
        """
        return (skill1, skill2) in self.mutex_rules or (skill2, skill1) in self.mutex_rules
    
    def check_rate_limit(self, skill: str) -> bool:
        """检查技能速率限制
        
        Args:
            skill: 技能名称
            
        Returns:
            是否允许调用
        """
        if skill not in self.rate_limits:
            return True
        
        import time
        current_time = time.time()
        max_calls, time_window = self.rate_limits[skill]
        
        if skill not in self.call_counts:
            self.call_counts[skill] = []
        
        # 清理过期的调用记录
        self.call_counts[skill] = [call_time for call_time in self.call_counts[skill] 
                                 if current_time - call_time < time_window]
        
        # 检查是否超过限制
        if len(self.call_counts[skill]) < max_calls:
            self.call_counts[skill].append(current_time)
            return True
        
        logger.warning(f"技能 {skill} 调用过于频繁，已达到速率限制")
        return False
    
    def add_call(self, skill: str):
        """添加调用记录
        
        Args:
            skill: 技能名称
        """
        if skill in self.rate_limits:
            import time
            current_time = time.time()
            if skill not in self.call_counts:
                self.call_counts[skill] = []
            self.call_counts[skill].append(current_time)
    
    def get_rate_limit_info(self, skill: str) -> Dict:
        """获取速率限制信息
        
        Args:
            skill: 技能名称
            
        Returns:
            速率限制信息
        """
        if skill not in self.rate_limits:
            return {
                "max_calls": "unlimited",
                "time_window": "unlimited",
                "current_calls": 0
            }
        
        max_calls, time_window = self.rate_limits[skill]
        current_calls = len(self.call_counts.get(skill, []))
        
        return {
            "max_calls": max_calls,
            "time_window": time_window,
            "current_calls": current_calls
        }
    
    def get_priority_rules(self) -> Dict[str, int]:
        """获取优先级规则
        
        Returns:
            优先级规则
        """
        return self.priority_rules
    
    def get_mutex_rules(self) -> Set[tuple]:
        """获取互斥规则
        
        Returns:
            互斥规则
        """
        return self.mutex_rules
    
    def get_rate_limits(self) -> Dict[str, tuple]:
        """获取速率限制
        
        Returns:
            速率限制
        """
        return self.rate_limits


# 全局边界管理器实例
boundary_manager = BoundaryManager()
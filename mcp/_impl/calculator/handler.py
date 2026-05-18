"""计算器技能 - 提供数学计算功能"""

import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class CalculatorHandler:
    """计算器处理器"""
    
    def execute(self, action: str = 'calculate', **kwargs) -> Dict[str, Any]:
        """同步执行接口"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop is not None:
            # 如果已有事件循环，直接调用异步方法
            return asyncio.create_task(self.aexecute(action, **kwargs))
        
        # 否则使用asyncio.run
        return asyncio.run(self.aexecute(action, **kwargs))
    
    async def aexecute(self, action: str = 'calculate', **kwargs) -> Dict[str, Any]:
        """异步执行接口"""
        actions = {
            'calculate': self._calculate,
            'history': self._get_history,
            'clear': self._clear_history
        }
        
        if action not in actions:
            return {'success': False, 'error': f'未知操作: {action}'}
        
        try:
            return await actions[action](**kwargs)
        except Exception as e:
            logger.error(f"计算器执行失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def _calculate(self, expression: str, **kwargs) -> Dict[str, Any]:
        """执行数学计算"""
        try:
            # 安全的表达式评估(仅允许基本运算)
            allowed_chars = set('0123456789+-*/(). ')
            if not all(c in allowed_chars for c in expression):
                return {'success': False, 'error': '表达式包含非法字符'}
            
            result = eval(expression)
            return {
                'success': True,
                'expression': expression,
                'result': result
            }
        except Exception as e:
            return {'success': False, 'error': f'计算错误: {str(e)}'}
    
    async def _get_history(self, **kwargs) -> Dict[str, Any]:
        """获取计算历史"""
        return {'success': True, 'history': []}
    
    async def _clear_history(self, **kwargs) -> Dict[str, Any]:
        """清空历史记录"""
        return {'success': True, 'message': '历史记录已清空'}


# 全局单例
_handler = CalculatorHandler()

def get_calculator_handler() -> CalculatorHandler:
    """获取处理器单例"""
    return _handler

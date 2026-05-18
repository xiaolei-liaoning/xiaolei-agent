"""第三方应用批量操作模块"""
import asyncio
from typing import Dict, Any, List, Optional

from .handler import app_manager


class BatchOperationManager:
    """批量操作管理器"""
    
    async def execute_batch(self, operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量执行操作
        
        Args:
            operations: 操作列表，每个操作包含以下字段：
                - app_name: 应用名称
                - action: 操作名称
                - params: 操作参数
                - timeout: 超时时间（可选，默认30秒）
                
        Returns:
            操作结果列表
        """
        tasks = []
        
        for operation in operations:
            app_name = operation.get('app_name')
            action = operation.get('action')
            params = operation.get('params', {})
            timeout = operation.get('timeout', 30)
            
            task = self._execute_with_timeout(app_name, action, params, timeout)
            tasks.append(task)
        
        # 并发执行所有操作
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'app_name': operations[i].get('app_name'),
                    'action': operations[i].get('action'),
                    'success': False,
                    'error': str(result)
                })
            else:
                processed_results.append({
                    'app_name': operations[i].get('app_name'),
                    'action': operations[i].get('action'),
                    **result
                })
        
        return processed_results
    
    async def _execute_with_timeout(self, app_name: str, action: str, params: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        """带超时的执行操作
        
        Args:
            app_name: 应用名称
            action: 操作名称
            params: 操作参数
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        try:
            result = await asyncio.wait_for(
                app_manager.execute(app_name, action, params),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': f'操作超时 ({timeout}秒)'
            }
    
    async def sync_data(self, source_app: str, target_apps: List[str], data_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """同步数据到多个应用
        
        Args:
            source_app: 数据源应用
            target_apps: 目标应用列表
            data_type: 数据类型（如 'issue', 'task', 'message' 等）
            params: 操作参数
            
        Returns:
            同步结果
        """
        # 1. 从源应用获取数据
        source_result = await app_manager.execute(source_app, f'get_{data_type}', params)
        
        if not source_result.get('success'):
            return {
                'success': False,
                'error': f'从源应用获取数据失败: {source_result.get("error")}'
            }
        
        # 2. 准备批量操作
        operations = []
        for target_app in target_apps:
            operations.append({
                'app_name': target_app,
                'action': f'create_{data_type}',
                'params': {
                    **params,
                    'data': source_result.get('data')
                }
            })
        
        # 3. 执行批量操作
        sync_results = await self.execute_batch(operations)
        
        # 4. 汇总结果
        success_count = sum(1 for result in sync_results if result.get('success'))
        failure_count = len(sync_results) - success_count
        
        return {
            'success': failure_count == 0,
            'source_app': source_app,
            'target_apps': target_apps,
            'data_type': data_type,
            'success_count': success_count,
            'failure_count': failure_count,
            'results': sync_results
        }
    
    async def compare_data(self, apps: List[str], data_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """比较多个应用的数据
        
        Args:
            apps: 应用列表
            data_type: 数据类型
            params: 操作参数
            
        Returns:
            比较结果
        """
        # 准备批量操作
        operations = []
        for app in apps:
            operations.append({
                'app_name': app,
                'action': f'get_{data_type}',
                'params': params
            })
        
        # 执行批量操作
        results = await self.execute_batch(operations)
        
        # 提取数据
        app_data = {}
        for i, result in enumerate(results):
            app_name = apps[i]
            if result.get('success'):
                app_data[app_name] = result.get('data')
            else:
                app_data[app_name] = None
        
        # 比较数据
        # 这里可以根据具体数据类型实现更复杂的比较逻辑
        # 简单示例：检查所有应用是否都返回了数据
        all_have_data = all(data is not None for data in app_data.values())
        
        return {
            'success': True,
            'apps': apps,
            'data_type': data_type,
            'all_have_data': all_have_data,
            'app_data': app_data
        }


# 全局批量操作管理器实例
batch_manager = BatchOperationManager()
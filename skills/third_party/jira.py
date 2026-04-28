"""Jira应用实现"""
import httpx
from typing import Dict, Any

from .handler import ThirdPartyApp


class JiraApp(ThirdPartyApp):
    """Jira应用"""
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行操作
        
        Args:
            action: 操作名称
            params: 操作参数
            
        Returns:
            执行结果
        """
        email = self.config.get('config', {}).get('email')
        api_token = self.config.get('config', {}).get('api_token')
        
        # 检查API密钥是否配置
        if not email or not api_token or api_token == 'your_jira_api_token':
            return {
                'success': False,
                'error': 'Jira API 密钥未配置，请在 skills/third_party/config.yml 中设置有效的 email 和 api_token'
            }
        
        auth = (email, api_token)
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            async with httpx.AsyncClient(auth=auth) as client:
                if action == 'get_project':
                    return await self._get_project(client, headers, params)
                elif action == 'create_issue':
                    return await self._create_issue(client, headers, params)
                elif action == 'get_issue':
                    return await self._get_issue(client, headers, params)
                else:
                    return {
                        'success': False,
                        'error': f'未知操作: {action}'
                    }
        except httpx.HTTPError as e:
            return {
                'success': False,
                'error': f'HTTP 错误: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'执行错误: {str(e)}'
            }
    
    async def _get_project(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """获取项目信息"""
        project_key = params.get('project_key')
        if not project_key:
            return {'success': False, 'error': '缺少必要参数: project_key'}
        
        url = f'{self.api_url}/rest/api/2/project/{project_key}'
        response = await client.get(url, headers=headers)
        return response.json()
    
    async def _create_issue(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """创建问题"""
        project_key = params.get('project_key')
        summary = params.get('summary')
        description = params.get('description')
        issue_type = params.get('issue_type', 'Task')
        
        if not project_key or not summary:
            return {'success': False, 'error': '缺少必要参数: project_key 和 summary'}
        
        url = f'{self.api_url}/rest/api/2/issue'
        payload = {
            'fields': {
                'project': {'key': project_key},
                'summary': summary,
                'description': description,
                'issuetype': {'name': issue_type}
            }
        }
        response = await client.post(url, headers=headers, json=payload)
        return response.json()
    
    async def _get_issue(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """获取问题信息"""
        issue_key = params.get('issue_key')
        if not issue_key:
            return {'success': False, 'error': '缺少必要参数: issue_key'}
        
        url = f'{self.api_url}/rest/api/2/issue/{issue_key}'
        response = await client.get(url, headers=headers)
        return response.json()
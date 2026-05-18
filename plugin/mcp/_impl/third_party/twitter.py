"""Twitter应用实现"""
import httpx
from typing import Dict, Any

from .handler import ThirdPartyApp


class TwitterApp(ThirdPartyApp):
    """Twitter应用"""
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行操作
        
        Args:
            action: 操作名称
            params: 操作参数
            
        Returns:
            执行结果
        """
        token = await self.get_auth_token()
        
        # 检查API密钥是否配置
        if not token or token == 'your_twitter_bearer_token':
            return {
                'success': False,
                'error': 'Twitter API 密钥未配置，请在 mcp/_impl/third_party/config.yml 中设置有效的 Bearer Token'
            }
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with httpx.AsyncClient() as client:
                if action == 'get_user':
                    return await self._get_user(client, headers, params)
                elif action == 'get_tweets':
                    return await self._get_tweets(client, headers, params)
                elif action == 'search_tweets':
                    return await self._search_tweets(client, headers, params)
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
    
    async def _get_user(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """获取用户信息"""
        username = params.get('username')
        if not username:
            return {'success': False, 'error': '缺少必要参数: username'}
        
        url = f'{self.api_url}/2/users/by/username/{username}'
        response = await client.get(url, headers=headers, params={'user.fields': 'created_at,description,public_metrics'})
        return response.json()
    
    async def _get_tweets(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """获取用户推文"""
        username = params.get('username')
        if not username:
            return {'success': False, 'error': '缺少必要参数: username'}
        
        # 先获取用户ID
        user_url = f'{self.api_url}/2/users/by/username/{username}'
        user_response = await client.get(user_url, headers=headers)
        user_data = user_response.json()
        
        if 'data' not in user_data:
            return {'success': False, 'error': '用户不存在'}
        
        user_id = user_data['data']['id']
        
        # 获取用户推文
        tweets_url = f'{self.api_url}/2/users/{user_id}/tweets'
        response = await client.get(tweets_url, headers=headers, params={'tweet.fields': 'created_at,public_metrics'})
        return response.json()
    
    async def _search_tweets(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索推文"""
        query = params.get('query')
        if not query:
            return {'success': False, 'error': '缺少必要参数: query'}
        
        url = f'{self.api_url}/2/tweets/search/recent'
        response = await client.get(url, headers=headers, params={'query': query, 'tweet.fields': 'created_at,public_metrics'})
        return response.json()
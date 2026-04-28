"""飞书应用实现"""
import httpx
from typing import Dict, Any

from .handler import ThirdPartyApp


class FeishuApp(ThirdPartyApp):
    """飞书应用"""
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行操作
        
        Args:
            action: 操作名称
            params: 操作参数
            
        Returns:
            执行结果
        """
        app_id = self.config.get('config', {}).get('app_id')
        app_secret = self.config.get('config', {}).get('app_secret')
        
        # 检查API密钥是否配置
        if not app_id or not app_secret or app_id == 'your_feishu_app_id' or app_secret == 'your_feishu_app_secret':
            return {
                'success': False,
                'error': '飞书API 密钥未配置，请在 skills/third_party/config.yml 中设置有效的 app_id 和 app_secret'
            }
        
        try:
            async with httpx.AsyncClient() as client:
                if action == 'get_access_token':
                    return await self._get_access_token(client, app_id, app_secret)
                elif action == 'get_user_info':
                    return await self._get_user_info(client, app_id, app_secret, params)
                elif action == 'send_message':
                    return await self._send_message(client, app_id, app_secret, params)
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
    
    async def _get_access_token(self, client: httpx.AsyncClient, app_id: str, app_secret: str) -> Dict[str, Any]:
        """获取访问令牌"""
        url = f'{self.api_url}/open-apis/auth/v3/app_access_token/internal'
        payload = {
            'app_id': app_id,
            'app_secret': app_secret
        }
        response = await client.post(url, json=payload)
        return response.json()
    
    async def _get_user_info(self, client: httpx.AsyncClient, app_id: str, app_secret: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取用户信息"""
        user_id = params.get('user_id')
        if not user_id:
            return {'success': False, 'error': '缺少必要参数: user_id'}
        
        # 先获取访问令牌
        token_response = await self._get_access_token(client, app_id, app_secret)
        if 'app_access_token' not in token_response.get('data', {}):
            return token_response
        
        access_token = token_response['data']['app_access_token']
        url = f'{self.api_url}/open-apis/contact/v3/users/{user_id}'
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        response = await client.get(url, headers=headers)
        return response.json()
    
    async def _send_message(self, client: httpx.AsyncClient, app_id: str, app_secret: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        user_id = params.get('user_id')
        message = params.get('message')
        if not user_id or not message:
            return {'success': False, 'error': '缺少必要参数: user_id, message'}
        
        # 先获取访问令牌
        token_response = await self._get_access_token(client, app_id, app_secret)
        if 'app_access_token' not in token_response.get('data', {}):
            return token_response
        
        access_token = token_response['data']['app_access_token']
        url = f'{self.api_url}/open-apis/im/v1/messages'
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        payload = {
            'receive_id_type': 'user_id',
            'receive_id': user_id,
            'content': '{"text":"' + message + '"}',
            'msg_type': 'text'
        }
        response = await client.post(url, headers=headers, json=payload)
        return response.json()
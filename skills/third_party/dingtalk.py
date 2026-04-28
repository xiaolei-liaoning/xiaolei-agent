"""钉钉应用实现"""
import httpx
from typing import Dict, Any

from .handler import ThirdPartyApp


class DingTalkApp(ThirdPartyApp):
    """钉钉应用"""
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行操作
        
        Args:
            action: 操作名称
            params: 操作参数
            
        Returns:
            执行结果
        """
        app_key = self.config.get('config', {}).get('app_key')
        app_secret = self.config.get('config', {}).get('app_secret')
        
        # 检查API密钥是否配置
        if not app_key or not app_secret or app_key == 'your_dingtalk_app_key' or app_secret == 'your_dingtalk_app_secret':
            return {
                'success': False,
                'error': '钉钉API 密钥未配置，请在 skills/third_party/config.yml 中设置有效的 app_key 和 app_secret'
            }
        
        try:
            async with httpx.AsyncClient() as client:
                if action == 'get_access_token':
                    return await self._get_access_token(client, app_key, app_secret)
                elif action == 'get_enterprise_info':
                    return await self._get_enterprise_info(client, app_key, app_secret)
                elif action == 'send_message':
                    return await self._send_message(client, app_key, app_secret, params)
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
    
    async def _get_access_token(self, client: httpx.AsyncClient, app_key: str, app_secret: str) -> Dict[str, Any]:
        """获取访问令牌"""
        url = f'{self.api_url}/gettoken'
        params = {
            'appkey': app_key,
            'appsecret': app_secret
        }
        response = await client.get(url, params=params)
        return response.json()
    
    async def _get_enterprise_info(self, client: httpx.AsyncClient, app_key: str, app_secret: str) -> Dict[str, Any]:
        """获取企业信息"""
        # 先获取访问令牌
        token_response = await self._get_access_token(client, app_key, app_secret)
        if 'access_token' not in token_response:
            return token_response
        
        access_token = token_response['access_token']
        url = f'{self.api_url}/topapi/v2/organization/get'
        payload = {}
        response = await client.post(url, params={'access_token': access_token}, json=payload)
        return response.json()
    
    async def _send_message(self, client: httpx.AsyncClient, app_key: str, app_secret: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        user_id = params.get('user_id')
        message = params.get('message')
        if not user_id or not message:
            return {'success': False, 'error': '缺少必要参数: user_id, message'}
        
        # 先获取访问令牌
        token_response = await self._get_access_token(client, app_key, app_secret)
        if 'access_token' not in token_response:
            return token_response
        
        access_token = token_response['access_token']
        url = f'{self.api_url}/topapi/message/corpconversation/asyncsend_v2'
        payload = {
            'userid_list': user_id,
            'msg': {
                'msgtype': 'text',
                'text': {
                    'content': message
                }
            }
        }
        response = await client.post(url, params={'access_token': access_token}, json=payload)
        return response.json()
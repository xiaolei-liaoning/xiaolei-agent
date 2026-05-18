"""微信应用实现"""
import httpx
from typing import Dict, Any

from .handler import ThirdPartyApp


class WechatApp(ThirdPartyApp):
    """微信应用"""
    
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
        if not app_id or not app_secret or app_id == 'your_wechat_app_id' or app_secret == 'your_wechat_app_secret':
            return {
                'success': False,
                'error': '微信API 密钥未配置，请在 mcp/_impl/third_party/config.yml 中设置有效的 app_id 和 app_secret'
            }
        
        try:
            async with httpx.AsyncClient() as client:
                if action == 'get_access_token':
                    return await self._get_access_token(client, app_id, app_secret)
                elif action == 'get_user_info':
                    return await self._get_user_info(client, app_id, app_secret, params)
                elif action == 'send_template_message':
                    return await self._send_template_message(client, app_id, app_secret, params)
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
        url = f'{self.api_url}/cgi-bin/token'
        params = {
            'grant_type': 'client_credential',
            'appid': app_id,
            'secret': app_secret
        }
        response = await client.get(url, params=params)
        return response.json()
    
    async def _get_user_info(self, client: httpx.AsyncClient, app_id: str, app_secret: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取用户信息"""
        openid = params.get('openid')
        if not openid:
            return {'success': False, 'error': '缺少必要参数: openid'}
        
        # 先获取访问令牌
        token_response = await self._get_access_token(client, app_id, app_secret)
        if 'access_token' not in token_response:
            return token_response
        
        access_token = token_response['access_token']
        url = f'{self.api_url}/cgi-bin/user/info'
        request_params = {
            'access_token': access_token,
            'openid': openid,
            'lang': 'zh_CN'
        }
        response = await client.get(url, params=request_params)
        return response.json()
    
    async def _send_template_message(self, client: httpx.AsyncClient, app_id: str, app_secret: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送模板消息"""
        openid = params.get('openid')
        template_id = params.get('template_id')
        data = params.get('data')
        if not openid or not template_id or not data:
            return {'success': False, 'error': '缺少必要参数: openid, template_id, data'}
        
        # 先获取访问令牌
        token_response = await self._get_access_token(client, app_id, app_secret)
        if 'access_token' not in token_response:
            return token_response
        
        access_token = token_response['access_token']
        url = f'{self.api_url}/cgi-bin/message/template/send'
        payload = {
            'touser': openid,
            'template_id': template_id,
            'data': data
        }
        response = await client.post(url, params={'access_token': access_token}, json=payload)
        return response.json()
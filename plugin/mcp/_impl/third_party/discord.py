"""Discord应用实现"""
import httpx
from typing import Dict, Any

from .handler import ThirdPartyApp


class DiscordApp(ThirdPartyApp):
    """Discord应用"""
    
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
        if not token or token == 'your_discord_token':
            return {
                'success': False,
                'error': 'Discord API 密钥未配置，请在 mcp/_impl/third_party/config.yml 中设置有效的 Bot Token'
            }
        
        headers = {
            'Authorization': f'Bot {token}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with httpx.AsyncClient() as client:
                if action == 'get_guild':
                    return await self._get_guild(client, headers, params)
                elif action == 'send_message':
                    return await self._send_message(client, headers, params)
                elif action == 'get_channel':
                    return await self._get_channel(client, headers, params)
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
    
    async def _get_guild(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """获取服务器信息"""
        guild_id = params.get('guild_id')
        if not guild_id:
            return {'success': False, 'error': '缺少必要参数: guild_id'}
        
        url = f'{self.api_url}/guilds/{guild_id}'
        response = await client.get(url, headers=headers)
        return response.json()
    
    async def _send_message(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        channel_id = params.get('channel_id')
        message = params.get('message')
        if not channel_id or not message:
            return {'success': False, 'error': '缺少必要参数: channel_id 和 message'}
        
        url = f'{self.api_url}/channels/{channel_id}/messages'
        response = await client.post(url, headers=headers, json={'content': message})
        return response.json()
    
    async def _get_channel(self, client: httpx.AsyncClient, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """获取频道信息"""
        channel_id = params.get('channel_id')
        if not channel_id:
            return {'success': False, 'error': '缺少必要参数: channel_id'}
        
        url = f'{self.api_url}/channels/{channel_id}'
        response = await client.get(url, headers=headers)
        return response.json()
"""第三方应用处理模块"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from .config import load_config
from .monitoring import app_monitor

logger = logging.getLogger(__name__)


class ThirdPartyApp(ABC):
    """第三方应用基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化
        
        Args:
            config: 应用配置
        """
        self.config = config
        self.name = config.get('name')
        self.api_url = config.get('api_url')
        self.auth_method = config.get('auth_method', 'api_key')
        self._auth_token = None
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行操作
        
        Args:
            action: 操作名称
            params: 操作参数
            
        Returns:
            执行结果
        """
        return {
            'success': False,
            'error': f'应用 {self.name} 未实现 {action} 操作'
        }
    
    async def authenticate(self) -> Optional[str]:
        """认证方法
        
        Returns:
            认证令牌
        """
        if self.auth_method == 'api_key':
            return self.config.get('config', {}).get('api_key')
        return None
    
    async def get_auth_token(self) -> Optional[str]:
        """获取认证令牌
        
        Returns:
            认证令牌
        """
        if self._auth_token is None:
            self._auth_token = await self.authenticate()
        return self._auth_token


class ThirdPartyAppManager:
    """第三方应用管理器"""
    
    def __init__(self):
        """初始化"""
        self.apps = {}
        self._load_apps()
    
    def _load_apps(self):
        """加载应用"""
        config = load_config()
        for app_name, app_config in config.get('apps', {}).items():
            # 根据应用名称动态创建对应的应用实例
            try:
                if app_name == 'twitter':
                    from .twitter import TwitterApp
                    self.apps[app_name] = TwitterApp(app_config)
                elif app_name == 'discord':
                    from .discord import DiscordApp
                    self.apps[app_name] = DiscordApp(app_config)
                elif app_name == 'jira':
                    from .jira import JiraApp
                    self.apps[app_name] = JiraApp(app_config)
                elif app_name == 'wechat':
                    from .wechat import WechatApp
                    self.apps[app_name] = WechatApp(app_config)
                elif app_name == 'dingtalk':
                    from .dingtalk import DingTalkApp
                    self.apps[app_name] = DingTalkApp(app_config)
                elif app_name == 'feishu':
                    from .feishu import FeishuApp
                    self.apps[app_name] = FeishuApp(app_config)
                else:
                    # 对于其他应用，使用基类作为占位
                    self.apps[app_name] = ThirdPartyApp(app_config)
                logger.info(f"加载第三方应用: {app_name}")
            except Exception as e:
                logger.error(f"加载第三方应用 {app_name} 失败: {e}")
                # 使用基类作为 fallback
                self.apps[app_name] = ThirdPartyApp(app_config)
    
    def get_app(self, app_name: str) -> Optional[ThirdPartyApp]:
        """获取应用实例
        
        Args:
            app_name: 应用名称
            
        Returns:
            应用实例
        """
        return self.apps.get(app_name)
    
    async def execute(self, app_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行应用操作
        
        Args:
            app_name: 应用名称
            action: 操作名称
            params: 操作参数
            
        Returns:
            执行结果
        """
        app = self.get_app(app_name)
        if not app:
            return {
                'success': False,
                'error': f'应用 {app_name} 不存在'
            }
        
        # 开始监控
        request_context = app_monitor.start_request(app_name, action)
        
        try:
            result = await app.execute(action, params)
            success = result.get('success', True)
            
            # 结束监控
            app_monitor.end_request(request_context, success, result)
            
            return {
                'success': success,
                'data': result
            }
        except Exception as e:
            logger.error(f"执行应用操作失败: {e}")
            error_result = {
                'success': False,
                'error': str(e)
            }
            # 结束监控
            app_monitor.end_request(request_context, False, error_result)
            return error_result


# 全局应用管理器实例
app_manager = ThirdPartyAppManager()


def register_third_party_skills(skill_dispatcher):
    """注册第三方应用技能
    
    Args:
        skill_dispatcher: 技能分发器实例
    """
    config = load_config()
    for app_name, app_config in config.get('apps', {}).items():
        skill_name = f'third_party_{app_name}'
        skill_dispatcher.register_tool(
            name=skill_name,
            keywords=app_config.get('keywords', []),
            priority=app_config.get('priority', 3),
            description=app_config.get('description', '')
        )
        logger.info(f"注册第三方应用技能: {skill_name}")
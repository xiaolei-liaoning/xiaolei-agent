"""第三方应用配置管理"""
import yaml
from pathlib import Path
from typing import Dict, Any

# 配置文件路径
CONFIG_PATH = Path(__file__).parent / 'config.yml'


def load_config() -> Dict[str, Any]:
    """加载配置
    
    Returns:
        配置字典，格式如下：
        {
            "apps": {
                "app_name": {
                    "name": "应用名称",
                    "api_url": "API地址",
                    "auth_method": "认证方式",
                    "keywords": ["关键词1", "关键词2"],
                    "priority": 优先级,
                    "description": "描述",
                    "config": {
                        "api_key": "API密钥",
                        # 其他配置
                    }
                }
            }
        }
    """
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return {'apps': {}}
    return {'apps': {}}


def save_config(config: Dict[str, Any]) -> bool:
    """保存配置
    
    Args:
        config: 配置字典
        
    Returns:
        是否保存成功
    """
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False


def get_app_config(app_name: str) -> Dict[str, Any]:
    """获取应用配置
    
    Args:
        app_name: 应用名称
        
    Returns:
        应用配置字典
    """
    config = load_config()
    return config.get('apps', {}).get(app_name, {})


def add_app_config(app_name: str, app_config: Dict[str, Any]) -> bool:
    """添加应用配置
    
    Args:
        app_name: 应用名称
        app_config: 应用配置
        
    Returns:
        是否添加成功
    """
    config = load_config()
    if 'apps' not in config:
        config['apps'] = {}
    config['apps'][app_name] = app_config
    return save_config(config)


def remove_app_config(app_name: str) -> bool:
    """移除应用配置
    
    Args:
        app_name: 应用名称
        
    Returns:
        是否移除成功
    """
    config = load_config()
    if 'apps' in config and app_name in config['apps']:
        del config['apps'][app_name]
        return save_config(config)
    return False
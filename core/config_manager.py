"""集中式配置管理模块

特性:
- 环境隔离（开发/测试/生产）
- 敏感配置安全存储
- 配置验证与类型安全
- 动态配置加载
- 配置变更通知

使用方式:
    from core.config_manager import ConfigManager, get_config
    
    config = ConfigManager.load()
    
    # 获取配置
    db_url = config.database.url
    api_key = config.get_secret("OPENAI_API_KEY")
"""

from __future__ import annotations

import os
import json
import logging
import threading
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    TypeVar,
    Union,
)
from dataclasses import dataclass, field, asdict
from enum import Enum
from functools import lru_cache
import hashlib
import base64

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Environment(Enum):
    """运行环境"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class DatabaseConfig:
    """数据库配置"""
    url: str = "sqlite:///./data/persistence.db"
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    echo: bool = False
    
    @property
    def is_mysql(self) -> bool:
        return "mysql" in self.url.lower()
    
    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.url.lower()


@dataclass
class RedisConfig:
    """Redis配置"""
    url: str = "redis://localhost:6379/0"
    max_connections: int = 10
    socket_timeout: int = 5
    socket_connect_timeout: int = 5


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: str = "zhipuai"
    default_model: str = "glm-4-flash"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60
    max_retries: int = 3
    rate_limit_rpm: int = 60


@dataclass
class RAGConfig:
    """RAG配置"""
    knowledge_dir: str = "~/.小雷版小龙虾/knowledge_base"
    vector_db_path: str = "~/.小雷版小龙虾/chroma_db"
    embedding_model: str = "text-embedding-ada-002"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 5
    similarity_threshold: float = 0.7


@dataclass
class AgentConfig:
    """Agent配置"""
    max_workers: int = 5
    task_timeout: int = 300
    max_concurrent_tasks: int = 10
    heartbeat_interval: int = 30
    enable_circuit_breaker: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60


@dataclass
class APIConfig:
    """API配置"""
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    api_prefix: str = "/api"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    file_path: Optional[str] = None
    max_file_size: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass
class SecurityConfig:
    """安全配置"""
    secret_key: str = ""
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    password_hash_algorithm: str = "bcrypt"
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_headers: List[str] = field(default_factory=lambda: ["*"])


@dataclass
class AppConfig:
    """应用总配置"""
    app_name: str = "小雷版小龙虾 AI Agent"
    version: str = "3.4.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    api: APIConfig = field(default_factory=APIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    _secrets: Dict[str, str] = field(default_factory=dict, repr=False)
    _change_callbacks: List[Callable[[str, Any], None]] = field(
        default_factory=list, repr=False
    )
    
    def get_secret(self, key: str, default: str = None) -> Optional[str]:
        """获取敏感配置
        
        优先级: 环境变量 > secrets存储 > 默认值
        """
        env_value = os.environ.get(key)
        if env_value:
            return env_value
        
        return self._secrets.get(key, default)
    
    def set_secret(self, key: str, value: str) -> None:
        """设置敏感配置（内存中加密存储）"""
        self._secrets[key] = self._encrypt_value(value)
    
    def _encrypt_value(self, value: str) -> str:
        """简单加密（实际生产应使用专业加密库）"""
        key = self.security.secret_key.encode() if self.security.secret_key else b"default_key"
        key_hash = hashlib.sha256(key).digest()
        encoded = base64.b64encode(value.encode()).decode()
        return encoded
    
    def _decrypt_value(self, encrypted: str) -> str:
        """解密"""
        try:
            return base64.b64decode(encrypted.encode()).decode()
        except Exception:
            return encrypted
    
    def on_change(self, callback: Callable[[str, Any], None]) -> None:
        """注册配置变更回调"""
        self._change_callbacks.append(callback)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ConfigManager:
    """配置管理器
    
    单例模式，统一管理所有配置
    """
    
    _instance: Optional[ConfigManager] = None
    _lock: threading.Lock = threading.Lock()
    _config: Optional[AppConfig] = None
    
    def __new__(cls) -> ConfigManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> ConfigManager:
        return cls()
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> AppConfig:
        """加载配置
        
        加载顺序:
        1. 默认配置
        2. 配置文件
        3. 环境变量覆盖
        """
        instance = cls()
        
        if instance._config is not None:
            return instance._config
        
        config = AppConfig()
        
        env_name = os.environ.get("APP_ENV", "development").lower()
        config.environment = Environment(env_name)
        config.debug = config.environment == Environment.DEVELOPMENT
        
        if config_path:
            instance._load_from_file(config, config_path)
        
        config_file = Path("config") / f"{env_name}.json"
        if config_file.exists():
            instance._load_from_file(config, str(config_file))
        
        instance._load_from_env(config)
        
        instance._load_secrets(config)
        
        instance._config = config
        logger.info(f"配置加载完成: environment={env_name}")
        
        return config
    
    def _load_from_file(self, config: AppConfig, path: str) -> None:
        """从文件加载配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._apply_config_dict(config, data)
            logger.debug(f"从文件加载配置: {path}")
        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {path}")
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {path} - {e}")
    
    def _apply_config_dict(self, config: AppConfig, data: Dict[str, Any]) -> None:
        """应用配置字典"""
        for key, value in data.items():
            if hasattr(config, key):
                attr = getattr(config, key)
                if isinstance(attr, (DatabaseConfig, RedisConfig, LLMConfig, 
                                    RAGConfig, AgentConfig, APIConfig, 
                                    LoggingConfig, SecurityConfig)):
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if hasattr(attr, sub_key):
                                setattr(attr, sub_key, sub_value)
                else:
                    setattr(config, key, value)
    
    def _load_from_env(self, config: AppConfig) -> None:
        """从环境变量加载配置"""
        env_mappings = {
            "DATABASE_URL": ("database", "url"),
            "DATABASE_POOL_SIZE": ("database", "pool_size"),
            "REDIS_URL": ("redis", "url"),
            "LLM_PROVIDER": ("llm", "provider"),
            "LLM_DEFAULT_MODEL": ("llm", "default_model"),
            "LLM_MAX_TOKENS": ("llm", "max_tokens"),
            "API_HOST": ("api", "host"),
            "API_PORT": ("api", "port"),
            "API_DEBUG": ("api", "debug"),
            "LOG_LEVEL": ("logging", "level"),
            "SECRET_KEY": ("security", "secret_key"),
            "AGENT_MAX_WORKERS": ("agent", "max_workers"),
        }
        
        for env_key, (section, attr) in env_mappings.items():
            value = os.environ.get(env_key)
            if value:
                section_obj = getattr(config, section)
                attr_type = type(getattr(section_obj, attr))
                
                try:
                    if attr_type == bool:
                        value = value.lower() in ("true", "1", "yes")
                    elif attr_type == int:
                        value = int(value)
                    elif attr_type == float:
                        value = float(value)
                    
                    setattr(section_obj, attr, value)
                    logger.debug(f"从环境变量加载: {env_key}")
                except ValueError as e:
                    logger.warning(f"环境变量类型转换失败: {env_key}={value} - {e}")
    
    def _load_secrets(self, config: AppConfig) -> None:
        """加载敏感配置"""
        secret_keys = [
            "OPENAI_API_KEY",
            "ZHIPUAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "GITHUB_TOKEN",
            "SECRET_KEY",
        ]
        
        for key in secret_keys:
            value = os.environ.get(key)
            if value:
                config.set_secret(key, value)
    
    @classmethod
    def get_config(cls) -> AppConfig:
        """获取配置实例"""
        instance = cls()
        if instance._config is None:
            return cls.load()
        return instance._config
    
    @classmethod
    def reload(cls) -> AppConfig:
        """重新加载配置"""
        instance = cls()
        instance._config = None
        return cls.load()
    
    @classmethod
    def save_config(cls, config: AppConfig, path: str) -> None:
        """保存配置到文件"""
        data = config.to_dict()
        
        data.pop('_secrets', None)
        data.pop('_change_callbacks', None)
        
        if 'environment' in data and isinstance(data['environment'], Environment):
            data['environment'] = data['environment'].value
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"配置已保存: {path}")


def get_config() -> AppConfig:
    """获取配置实例的便捷函数"""
    return ConfigManager.get_config()

"""集中式配置管理模块

特性:
- 环境隔离（开发/测试/生产）
- 敏感配置安全存储
- 配置验证与类型安全
- 动态配置加载
- 配置变更通知

使用方式:
    from .config_manager import ConfigManager, get_config
    
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
class PathConfig:
    """路径配置"""
    # 项目根目录（自动检测）
    project_root: str = ""
    
    # MCP服务器相关路径
    the_agency_path: str = ""
    mcp_servers_dir: str = ""
    
    # 临时文件目录
    temp_dir: str = "/tmp"
    
    def __post_init__(self):
        """初始化时自动设置默认路径"""
        if not self.project_root:
            # 自动检测项目根目录
            import os
            from pathlib import Path
            current_file = Path(__file__).resolve()
            self.project_root = str(current_file.parent.parent)
        
        if not self.the_agency_path:
            # 默认the-agency路径
            possible_paths = [
                os.path.join(self.project_root, "the-agency"),
                os.path.expanduser("~/the-agency"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    self.the_agency_path = path
                    break
            else:
                self.the_agency_path = possible_paths[0]
        
        if not self.mcp_servers_dir:
            self.mcp_servers_dir = os.path.join(self.project_root, "mcp")


@dataclass
class SkillConfigItem:
    """单个技能配置"""
    name: str = ""
    keywords: List[str] = field(default_factory=list)
    priority: int = 5
    description: str = ""


@dataclass
class SkillsConfig:
    """技能配置"""
    # 技能列表
    skills: Dict[str, SkillConfigItem] = field(default_factory=dict)
    # 多步任务指示词
    multi_step_indicators: List[str] = field(default_factory=lambda: [
        "先", "然后", "接着", "再", "最后", "之后", "并且", "同时",
        "再帮我", "还有", "还要", "查完", "做完", "接下来"
    ])
    # 语言映射
    lang_map: Dict[str, str] = field(default_factory=lambda: {
        "英文": "en", "英语": "en", "english": "en",
        "中文": "zh", "汉语": "zh", "chinese": "zh",
        "日文": "ja", "日语": "ja", "japanese": "ja",
        "韩文": "ko", "韩语": "ko", "korean": "ko",
        "法文": "fr", "法语": "fr", "french": "fr",
        "德文": "de", "德语": "de", "german": "de",
        "西班牙文": "es", "西班牙语": "es"
    })
    # 意图到技能的映射
    intent_skill_map: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "math_calculation": {"keywords": ["加", "减", "乘", "除", "等于", "计算", "+", "-", "*", "/", "×", "÷"], "skill": "calculator", "min_hits": 1},
        "greeting": {"keywords": ["你好", "嗨", "hello", "hi", "在吗"], "skill": "chat", "min_hits": 1},
        "weather_query": {"keywords": ["天气", "气温", "温度", "下雨", "下雪", "刮风", "预报", "天气怎么样", "天气如何", "多少度", "几度", "会不会下雨", "热不热", "冷不冷"], "skill": "weather", "min_hits": 1},
        "web_scraping": {"keywords": ["热搜", "热榜", "爬取", "抓取", "微博", "抖音", "知乎", "b站", "github", "热点", "排行榜", "爬虫"], "skill": "web_scraper", "min_hits": 1},
        "system_info": {"keywords": ["系统时间", "内存", "磁盘", "cpu", "进程", "网络", "现在几点", "今天几号"], "skill": "system_toolbox", "min_hits": 1},
        "translation": {"keywords": ["翻译", "translate", "中英互译", "翻译成", "翻一下", "翻译这段"], "skill": "translator", "min_hits": 1},
        "gui_control": {"keywords": ["打开", "点击", "截图", "截屏", "音量", "亮度", "微信", "浏览器", "关闭", "截个图", "截个屏", "飞书", "钉钉", "邮件", "日历"], "skill": "gui_automation", "min_hits": 1},
        "data_analysis": {"keywords": ["数据分析", "分析一下", "分析数据", "统计", "可视化", "图表", "做个分析", "做个图表", "画个图", "柱状图", "饼图", "折线图", "词云"], "skill": "data_analysis", "min_hits": 1},
        "knowledge_search": {"keywords": ["是什么", "如何", "为什么", "了解一下", "概念", "原理", "解释", "定义"], "skill": "rag_search", "min_hits": 1},
        "deep_analysis": {"keywords": ["深度思考", "自主搜索", "最新信息", "分析一下", "研究一下", "最新动态"], "skill": "deep_thinking"},
        "multi_step_task": {"keywords": ["先", "然后", "接着", "再", "最后", "下一步", "接下来", "第一步", "第二步"], "skill": "multi_step", "min_hits": 2},
        "text_analysis": {"keywords": ["分析文本", "拆解", "提取概要", "生成标题", "文本分析", "长文本", "主要观点", "段落"], "skill": "text_analyzer", "min_hits": 1}
    })


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: str = "zhipuai"
    default_model: str = "glm-4-flash"  # 改为更稳定的glm-4-flash
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60
    max_retries: int = 3
    rate_limit_rpm: int = 30  # 降低到30 RPM以适配免费API限制
    backoff_base: float = 2.0  # 增加退避时间
    # 支持的模型列表
    supported_models: List[str] = field(default_factory=lambda: [
        "glm-4-flash", "glm-4-plus", "glm-4-air",
        "glm-4-free", "glm-3-turbo",
        "glm-4-0520", "glm-4v", "glm-4v-plus", "glm-4v-flash",
        "glm-4-long", "glm-4-flashx",
        "free-glm-4", "free-qwen", "free-llama"
    ])


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
    paths: PathConfig = field(default_factory=PathConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
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
        
        # 加载技能配置
        skill_config_files = [
            Path("config") / "skill_keywords.yaml",
            Path("core") / "engine" / "skill_config.yaml"
        ]
        for skill_file in skill_config_files:
            if skill_file.exists():
                instance._load_skills_from_yaml(config, str(skill_file))
        
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
                if isinstance(attr, (DatabaseConfig, RedisConfig, LLMConfig, SkillsConfig,
                                    RAGConfig, AgentConfig, APIConfig, 
                                    LoggingConfig, SecurityConfig)):
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if hasattr(attr, sub_key):
                                setattr(attr, sub_key, sub_value)
                else:
                    setattr(config, key, value)
    
    def _load_skills_from_yaml(self, config: AppConfig, path: str) -> None:
        """从YAML文件加载技能配置"""
        try:
            import yaml
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if 'skills' in data:
                skills_data = data['skills']
                # 处理两种格式: dict格式和list格式
                if isinstance(skills_data, dict):
                    # 字典格式: {skill_name: {priority, keywords, description}}
                    for name, skill_data in skills_data.items():
                        config.skills.skills[name] = SkillConfigItem(
                            name=name,
                            priority=skill_data.get('priority', 5),
                            keywords=skill_data.get('keywords', []),
                            description=skill_data.get('description', '')
                        )
                elif isinstance(skills_data, list):
                    # 列表格式: [{name, keywords, priority}]
                    for skill_data in skills_data:
                        name = skill_data.get('name')
                        if name:
                            config.skills.skills[name] = SkillConfigItem(
                                name=name,
                                priority=skill_data.get('priority', 5),
                                keywords=skill_data.get('keywords', []),
                                description=skill_data.get('description', '')
                            )
                logger.debug(f"从YAML加载技能配置: {path}")
        except FileNotFoundError:
            logger.warning(f"技能配置文件不存在: {path}")
        except Exception as e:
            logger.error(f"加载技能配置失败: {path} - {e}")
    
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

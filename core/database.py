"""MySQL 数据库管理（工业级 SQLAlchemy 2.0）

- users / chat_history / characters / task_logs 四张表
- 数据库不存在自动 CREATE DATABASE
- passlib 密码哈希
- 5 个预设角色种子数据
"""
import os
import logging
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
    Boolean,
    JSON,
    event,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker,
    Session,
    Mapped,
    mapped_column,
)
from sqlalchemy.exc import OperationalError
from datetime import datetime
from passlib.context import CryptContext

load_dotenv()

logger = logging.getLogger(__name__)

# ─── 密码哈希上下文 ──────────────────────────────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ─── ORM Base ────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
#  表定义
# ═══════════════════════════════════════════════════════════════════════════════


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column("name", String(255), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column("password", String(255), nullable=False)
    email: Mapped[str] = mapped_column("email", String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column("phone", String(20))
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime, default=datetime.now)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    character_id: Mapped[str] = mapped_column(String(50), default="default")
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_call: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_type: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    params: Mapped[Optional[dict]] = mapped_column(JSON)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    duration: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class UserSkillInstallation(Base):
    """用户技能安装记录表"""
    __tablename__ = "user_skill_installations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="用户ID")
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="技能名称")
    skill_version: Mapped[str] = mapped_column(String(20), default="1.0.0", comment="技能版本")
    status: Mapped[str] = mapped_column(String(20), default="enabled", comment="状态: enabled/disabled")
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="技能配置")
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="安装时间")
    enabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="启用时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def __repr__(self):
        return f"<UserSkillInstallation(user_id={self.user_id}, skill='{self.skill_name}', status='{self.status}')>"


class AgentGroup(Base):
    """Agent小组表"""
    __tablename__ = "agent_groups"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="小组ID(UUID)")
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="小组名称")
    members: Mapped[list] = mapped_column(JSON, nullable=False, comment="Agent成员列表")
    strategy: Mapped[str] = mapped_column(String(50), nullable=False, default="weighted_round_robin", comment="调度策略")
    circuit_breaker: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用熔断机制")
    elastic_scaling: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用弹性伸缩")
    status: Mapped[str] = mapped_column(String(20), default="离线", comment="状态: 运行中/休眠/离线")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后活跃时间")

    def __repr__(self):
        return f"<AgentGroup(id='{self.id}', name='{self.name}', status='{self.status}')>"


class AgentGroupAuditLog(Base):
    """Agent小组操作审计日志表"""
    __tablename__ = "agent_group_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="小组ID")
    action: Mapped[str] = mapped_column(String(20), nullable=False, comment="操作类型: CREATE/UPDATE/DELETE/START/STOP")
    operator_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="操作者ID")
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="操作详情")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="操作时间")

    def __repr__(self):
        return f"<AgentGroupAuditLog(group_id='{self.group_id}', action='{self.action}')>"

# ═══════════════════════════════════════════════════════════════════════════════
#  引擎 & 会话管理
# ═══════════════════════════════════════════════════════════════════════════════

_engine = None
_SessionLocal: Optional[sessionmaker] = None

MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_DB = os.getenv("MYSQL_DB", "xiaolei_agent")
MYSQL_CHARSET = "utf8mb4"


def _build_url(db_name: str = MYSQL_DB) -> str:
    return (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}/{db_name}?charset={MYSQL_CHARSET}"
    )


def get_engine():
    """获取 SQLAlchemy Engine（需先调用 init_db）"""
    if _engine is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return _engine


def get_session() -> Session:
    """获取一个新的数据库会话"""
    if _SessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return _SessionLocal()


# ═══════════════════════════════════════════════════════════════════════════════
#  初始化 & 种子数据
# ═══════════════════════════════════════════════════════════════════════════════

# 5 个预设角色
_SEED_CHARACTERS = [
    Character(
        character_id="default",
        name="小龙虾助手",
        is_default=True,
        description="你的默认AI助手",
        system_prompt="你是小雷版小龙虾AI助手，友好、专业、高效。帮助用户完成各种任务。",
    ),
    Character(
        character_id="first_love",
        name="温柔初恋",
        description="温柔体贴的初恋角色",
        system_prompt="你是温柔的初恋角色，说话温柔体贴，善解人意。",
    ),
    Character(
        character_id="bestfriend",
        name="知心闺蜜",
        description="最懂你的闺蜜",
        system_prompt="你是用户的知心闺蜜，可以畅所欲言，分享秘密。",
    ),
    Character(
        character_id="goddess",
        name="高冷女神",
        description="高冷但有内涵的女神",
        system_prompt="你是高冷女神，说话简洁有力，但内心温柔。",
    ),
    Character(
        character_id="libai",
        name="诗仙李白",
        description="唐代诗仙李白",
        system_prompt="你是诗仙李白，性格豪放不羁，说话常带诗意和酒意。",
    ),
]


def init_db():
    """创建数据库（如不存在）→ 建表 → 插入种子数据"""
    global _engine, _SessionLocal

    # 1. 确保数据库存在
    _ensure_database_exists()

    # 2. 创建引擎 + 建表
    db_url = _build_url()
    _engine = create_engine(db_url, pool_recycle=3600, pool_pre_ping=True, echo=False)

    # MySQL 语法：datetime.now 函数
    @event.listens_for(_engine, "connect", insert=True)
    def _set_sql_mode(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE'")
        cursor.close()

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)

    # 3. 种子数据
    _seed_default_data()

    logger.info("数据库初始化完成: %s@%s/%s", MYSQL_USER, MYSQL_HOST, MYSQL_DB)


def _ensure_database_exists():
    """如果数据库不存在则自动创建"""
    no_db_url = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}/?charset={MYSQL_CHARSET}"
    )
    init_engine = create_engine(no_db_url, echo=False)
    try:
        with init_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` "
                    f"DEFAULT CHARACTER SET {MYSQL_CHARSET} COLLATE {MYSQL_CHARSET}_unicode_ci"
                )
            )
            conn.commit()
        logger.info("数据库 '%s' 已就绪", MYSQL_DB)
    except OperationalError as e:
        logger.error("连接 MySQL 失败（请检查 MySQL 是否运行）: %s", e)
        raise
    finally:
        init_engine.dispose()


def _seed_default_data():
    """插入 5 个预设角色（仅当角色表为空时）"""
    session = get_session()
    try:
        exists = session.query(Character).filter_by(character_id="default").first()
        if exists:
            logger.debug("种子角色已存在，跳过")
            return
        session.add_all(_SEED_CHARACTERS)
        session.commit()
        logger.info("已插入 %d 个预设角色", len(_SEED_CHARACTERS))
    except Exception as e:
        logger.error("种子数据插入失败: %s", e)
        session.rollback()
    finally:
        session.close()

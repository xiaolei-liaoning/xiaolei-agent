"""Agent小组管理API

提供Agent小组的CRUD操作、状态管理、成员配置等功能
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-groups", tags=["Agent小组管理"])

# ==================== 数据模型 ====================

# 系统已注册的Agent列表
REGISTERED_AGENTS = {
    'checker': 'Checker',
    'scraper': 'Scraper',
    'vulnerability': 'Vulnerability',
    'summarizer': 'Summarizer',
    'data_analysis': 'DataAnalysis',
    'nlp': 'NLP',
    'text_analyzer': 'TextAnalyzer',
    'planning': 'Planning',
    'processor': 'Processor',
    'transformer': 'Transformer',
    'scanner': 'Scanner',
    'analyzer': 'Analyzer'
}

class AgentGroupCreate(BaseModel):
    """创建Agent小组请求模型"""
    name: str = Field(..., min_length=1, max_length=100, description="小组名称")
    members: List[str] = Field(..., min_items=1, max_items=10, description="Agent成员列表")
    strategy: str = Field(default="weighted_round_robin", description="调度策略")
    circuit_breaker: bool = Field(default=False, description="是否启用熔断机制")
    elastic_scaling: bool = Field(default=False, description="是否启用弹性伸缩")
    
    @validator('name')
    def validate_name(cls, v):
        """验证小组名称格式"""
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_\-()\u3002\uff0c\uff1a\uff1b\uff01\uff1f]+$', v):
            raise ValueError('小组名称只能包含中文、英文、数字、下划线、连字符和中文标点')
        if len(v.strip()) < 2:
            raise ValueError('小组名称至少需要2个字符')
        return v.strip()
    
    @validator('members')
    def validate_members(cls, v):
        """验证成员有效性"""
        if not v:
            raise ValueError('成员列表不能为空')
        
        # 检查重复成员
        if len(v) != len(set(v)):
            raise ValueError('成员列表中存在重复的Agent')
        
        # 验证成员是否在已注册列表中
        valid_members_lower = {agent.lower(): agent for agent in REGISTERED_AGENTS.values()}
        invalid_members = []
        for member in v:
            if member.lower() not in valid_members_lower:
                invalid_members.append(member)
        
        if invalid_members:
            valid_list = ', '.join(REGISTERED_AGENTS.values())
            raise ValueError(f'以下Agent未注册: {", ".join(invalid_members)}。已注册的Agent: {valid_list}')
        
        return v
    
    @validator('strategy')
    def validate_strategy(cls, v):
        """验证调度策略"""
        valid_strategies = ['weighted_round_robin', 'least_load', 'random', 'priority']
        if v not in valid_strategies:
            raise ValueError(f'不支持的调度策略: {v}。支持的策略: {", ".join(valid_strategies)}')
        return v

class AgentGroupUpdate(BaseModel):
    """更新Agent小组请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="小组名称")
    members: Optional[List[str]] = Field(None, min_items=1, max_items=10, description="Agent成员列表")
    strategy: Optional[str] = Field(None, description="调度策略")
    circuit_breaker: Optional[bool] = Field(None, description="是否启用熔断机制")
    elastic_scaling: Optional[bool] = Field(None, description="是否启用弹性伸缩")
    
    @validator('name')
    def validate_name(cls, v):
        """验证小组名称格式"""
        if v is not None:
            if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_\-()\u3002\uff0c\uff1a\uff1b\uff01\uff1f]+$', v):
                raise ValueError('小组名称只能包含中文、英文、数字、下划线、连字符和中文标点')
            if len(v.strip()) < 2:
                raise ValueError('小组名称至少需要2个字符')
            return v.strip()
        return v
    
    @validator('members')
    def validate_members(cls, v):
        """验证成员有效性"""
        if v is not None:
            if not v:
                raise ValueError('成员列表不能为空')
            
            # 检查重复成员
            if len(v) != len(set(v)):
                raise ValueError('成员列表中存在重复的Agent')
            
            # 验证成员是否在已注册列表中
            valid_members_lower = {agent.lower(): agent for agent in REGISTERED_AGENTS.values()}
            invalid_members = []
            for member in v:
                if member.lower() not in valid_members_lower:
                    invalid_members.append(member)
            
            if invalid_members:
                valid_list = ', '.join(REGISTERED_AGENTS.values())
                raise ValueError(f'以下Agent未注册: {", ".join(invalid_members)}。已注册的Agent: {valid_list}')
            
            return v
        return v
    
    @validator('strategy')
    def validate_strategy(cls, v):
        """验证调度策略"""
        if v is not None:
            valid_strategies = ['weighted_round_robin', 'least_load', 'random', 'priority']
            if v not in valid_strategies:
                raise ValueError(f'不支持的调度策略: {v}。支持的策略: {", ".join(valid_strategies)}')
        return v

class AgentGroupResponse(BaseModel):
    """Agent小组响应模型"""
    id: str
    name: str
    members: List[str]
    strategy: str  # 这里返回中文显示名称
    circuit_breaker: bool
    elastic_scaling: bool
    status: str  # 运行中、休眠、离线
    created_at: str
    updated_at: str
    members_count: int
    last_active: Optional[str] = None

class AgentGroupListResponse(BaseModel):
    """Agent小组列表响应模型"""
    total: int
    groups: List[AgentGroupResponse]

# ==================== 策略名称映射 ====================

STRATEGY_NAMES = {
    'weighted_round_robin': '加权轮询',
    'least_load': '最小负载',
    'random': '随机选择',
    'priority': '优先级调度'
}

# ==================== 审计日志工具类 ====================

class AuditLogger:
    """审计日志记录工具"""
    
    # 内存存储审计日志（降级方案）
    _logs: List[Dict[str, Any]] = []

    @classmethod
    def log(cls, action: str, group_id: str, details: Dict[str, Any], operator_id: int = 1):
        """记录审计日志"""
        log_entry = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'group_id': group_id,
            'operator_id': operator_id,
            'details': details
        }
        cls._logs.append(log_entry)
        
        # 尝试写入数据库
        try:
            _log_audit_action(action, group_id, details, operator_id)
        except Exception as e:
            logger.warning(f"写入数据库审计日志失败，仅保存到内存: {e}")

    @classmethod
    def get_logs(cls, group_id: Optional[str] = None, action: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取审计日志"""
        # 尝试从数据库读取
        try:
            from core.database import get_session, AgentGroupAuditLog
            db = get_session()
            try:
                query = db.query(AgentGroupAuditLog)
                if group_id:
                    query = query.filter(AgentGroupAuditLog.group_id == group_id)
                if action:
                    query = query.filter(AgentGroupAuditLog.action == action)
                
                # 按时间倒序
                query = query.order_by(AgentGroupAuditLog.timestamp.desc()).limit(limit)
                
                db_logs = []
                for log in query.all():
                    db_logs.append({
                        'id': log.id,
                        'timestamp': log.timestamp.isoformat(),
                        'action': log.action,
                        'group_id': log.group_id,
                        'operator_id': log.operator_id,
                        'details': log.details
                    })
                return db_logs
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"从数据库读取审计日志失败，使用内存数据: {e}")
        
        # 降级：从内存读取
        filtered_logs = cls._logs
        if group_id:
            filtered_logs = [l for l in filtered_logs if l['group_id'] == group_id]
        if action:
            filtered_logs = [l for l in filtered_logs if l['action'] == action]
        
        # 按时间倒序并限制数量
        filtered_logs = sorted(filtered_logs, key=lambda x: x['timestamp'], reverse=True)[:limit]
        return filtered_logs

# ==================== 内存存储(降级方案) ====================

# 模拟数据库存储
_agent_groups: Dict[str, Dict[str, Any]] = {}

def _check_db_available() -> bool:
    """检查数据库是否可用"""
    try:
        from core.database import get_session
        session = get_session()
        session.execute("SELECT 1")
        session.close()
        return True
    except Exception:
        return False

def _get_or_create_group_from_db(group_id: str) -> Optional[Dict[str, Any]]:
    """从数据库获取或创建小组数据"""
    try:
        from core.database import get_session, AgentGroup
        
        db = get_session()
        try:
            group = db.query(AgentGroup).filter(AgentGroup.id == group_id).first()
            if not group:
                return None
            
            return {
                'id': group.id,
                'name': group.name,
                'members': group.members,
                'strategy': group.strategy,
                'circuit_breaker': group.circuit_breaker,
                'elastic_scaling': group.elastic_scaling,
                'status': group.status,
                'created_at': group.created_at.isoformat(),
                'updated_at': group.updated_at.isoformat(),
                'last_active': group.last_active.isoformat() if group.last_active else None
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"从数据库获取小组失败: {e}")
        return None

def _save_group_to_db(group_data: Dict[str, Any]) -> bool:
    """保存小组数据到数据库"""
    try:
        from core.database import get_session, AgentGroup
        
        db = get_session()
        try:
            # 检查是否存在
            existing = db.query(AgentGroup).filter(AgentGroup.id == group_data['id']).first()
            
            if existing:
                # 更新
                existing.name = group_data['name']
                existing.members = group_data['members']
                existing.strategy = group_data['strategy']
                existing.circuit_breaker = group_data['circuit_breaker']
                existing.elastic_scaling = group_data['elastic_scaling']
                existing.status = group_data['status']
                existing.updated_at = datetime.fromisoformat(group_data['updated_at'])
                if group_data.get('last_active'):
                    existing.last_active = datetime.fromisoformat(group_data['last_active'])
            else:
                # 创建
                new_group = AgentGroup(
                    id=group_data['id'],
                    name=group_data['name'],
                    members=group_data['members'],
                    strategy=group_data['strategy'],
                    circuit_breaker=group_data['circuit_breaker'],
                    elastic_scaling=group_data['elastic_scaling'],
                    status=group_data['status'],
                    created_at=datetime.fromisoformat(group_data['created_at']),
                    updated_at=datetime.fromisoformat(group_data['updated_at']),
                    last_active=datetime.fromisoformat(group_data['last_active']) if group_data.get('last_active') else None
                )
                db.add(new_group)
            
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"保存小组到数据库失败: {e}")
            return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"数据库操作失败: {e}")
        return False

def _delete_group_from_db(group_id: str) -> bool:
    """从数据库删除小组"""
    try:
        from core.database import get_session, AgentGroup
        
        db = get_session()
        try:
            group = db.query(AgentGroup).filter(AgentGroup.id == group_id).first()
            if group:
                db.delete(group)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"删除小组失败: {e}")
            return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"数据库操作失败: {e}")
        return False

def _log_audit_action(action: str, group_id: str, details: Dict[str, Any], operator_id: int = 1):
    """记录审计日志到数据库"""
    try:
        from core.database import get_session, AgentGroupAuditLog
        
        db = get_session()
        try:
            audit_log = AgentGroupAuditLog(
                group_id=group_id,
                action=action,
                operator_id=operator_id,
                details=details
            )
            db.add(audit_log)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"记录审计日志失败: {e}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"数据库操作失败: {e}")

# 初始化示例数据
def _init_sample_data():
    """初始化示例Agent小组数据"""
    if not _agent_groups:
        now = datetime.now().isoformat()
        _agent_groups.update({
            'group_1': {
                'id': 'group_1',
                'name': '数据处理小组',
                'members': ['Processor', 'Transformer'],
                'strategy': 'least_load',
                'circuit_breaker': True,
                'elastic_scaling': False,
                'status': '休眠',
                'created_at': now,
                'updated_at': now,
                'last_active': None
            },
            'group_2': {
                'id': 'group_2',
                'name': '安全检测小组',
                'members': ['Vulnerability', 'Scanner'],
                'strategy': 'random',
                'circuit_breaker': False,
                'elastic_scaling': False,
                'status': '离线',
                'created_at': now,
                'updated_at': now,
                'last_active': None
            },
            'group_3': {
                'id': 'group_3',
                'name': '智能分析小组',
                'members': ['Checker', 'Scraper', 'Analyzer'],
                'strategy': 'weighted_round_robin',
                'circuit_breaker': True,
                'elastic_scaling': True,
                'status': '运行中',
                'created_at': now,
                'updated_at': now,
                'last_active': now
            }
        })
        logger.info("初始化示例Agent小组数据完成")

# 启动时初始化示例数据
_init_sample_data()

# ==================== API路由 ====================

@router.get("/strategies", summary="获取支持的调度策略")
async def get_strategies():
    """获取所有支持的调度策略
    
    注意: 此路由必须放在 /{group_id} 之前,避免被动态路由拦截
    """
    try:
        strategies = [
            {
                "key": key,
                "name": name,
                "description": _get_strategy_description(key)
            }
            for key, name in STRATEGY_NAMES.items()
        ]
        
        return {
            "success": True,
            "strategies": strategies
        }
    except Exception as e:
        logger.error(f"获取调度策略失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取调度策略失败: {str(e)}")

@router.get("/audit-logs", summary="获取操作审计日志")
async def get_audit_logs(
    group_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100
):
    """获取操作审计日志
    
    Args:
        group_id: 可选的小组ID筛选
        action: 可选的操作类型筛选 (CREATE, UPDATE, DELETE, START, STOP)
        limit: 返回的最大记录数
    
    Returns:
        审计日志列表
    """
    try:
        logs = AuditLogger.get_logs(group_id=group_id, action=action, limit=limit)
        return {
            "success": True,
            "total": len(logs),
            "logs": logs
        }
    except Exception as e:
        logger.error(f"获取审计日志失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取审计日志失败: {str(e)}")

@router.get("", response_model=AgentGroupListResponse)
async def list_agent_groups(status: Optional[str] = None):
    """获取所有Agent小组列表
    
    Args:
        status: 可选的状态筛选（运行中、休眠、离线）
    
    Returns:
        Agent小组列表
    """
    try:
        # 尝试从数据库加载数据
        if _check_db_available():
            try:
                from core.database import get_session, AgentGroup
                db = get_session()
                try:
                    query = db.query(AgentGroup)
                    if status:
                        query = query.filter(AgentGroup.status == status)
                    
                    db_groups = query.all()
                    
                    # 更新内存缓存
                    _agent_groups.clear()
                    for group in db_groups:
                        _agent_groups[group.id] = {
                            'id': group.id,
                            'name': group.name,
                            'members': group.members,
                            'strategy': group.strategy,
                            'circuit_breaker': group.circuit_breaker,
                            'elastic_scaling': group.elastic_scaling,
                            'status': group.status,
                            'created_at': group.created_at.isoformat(),
                            'updated_at': group.updated_at.isoformat(),
                            'last_active': group.last_active.isoformat() if group.last_active else None
                        }
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"从数据库同步数据失败，使用内存数据: {e}")
        
        groups = list(_agent_groups.values())
        
        # 状态筛选
        if status:
            groups = [g for g in groups if g['status'] == status]
        
        # 转换为响应模型
        response_groups = []
        for group in groups:
            response_groups.append(AgentGroupResponse(
                id=group['id'],
                name=group['name'],
                members=group['members'],
                strategy=STRATEGY_NAMES.get(group['strategy'], group['strategy']),
                circuit_breaker=group['circuit_breaker'],
                elastic_scaling=group['elastic_scaling'],
                status=group['status'],
                created_at=group['created_at'],
                updated_at=group['updated_at'],
                members_count=len(group['members']),
                last_active=group.get('last_active')
            ))
        
        return AgentGroupListResponse(
            total=len(response_groups),
            groups=response_groups
        )
    except Exception as e:
        logger.error(f"获取Agent小组列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取Agent小组列表失败: {str(e)}")

@router.get("/{group_id}", response_model=AgentGroupResponse)
async def get_agent_group(group_id: str):
    """获取指定Agent小组详情
    
    Args:
        group_id: 小组ID
    
    Returns:
        Agent小组详情
    """
    try:
        # 先从内存查找，如果没有再尝试数据库
        if group_id not in _agent_groups:
            if _check_db_available():
                db_group = _get_or_create_group_from_db(group_id)
                if db_group:
                    _agent_groups[group_id] = db_group
                else:
                    raise HTTPException(status_code=404, detail=f"Agent小组不存在: {group_id}")
            else:
                raise HTTPException(status_code=404, detail=f"Agent小组不存在: {group_id}")
        
        group = _agent_groups[group_id]
        return AgentGroupResponse(
            id=group['id'],
            name=group['name'],
            members=group['members'],
            strategy=STRATEGY_NAMES.get(group['strategy'], group['strategy']),
            circuit_breaker=group['circuit_breaker'],
            elastic_scaling=group['elastic_scaling'],
            status=group['status'],
            created_at=group['created_at'],
            updated_at=group['updated_at'],
            members_count=len(group['members']),
            last_active=group.get('last_active')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取Agent小组详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取Agent小组详情失败: {str(e)}")

@router.post("", response_model=AgentGroupResponse, status_code=201)
async def create_agent_group(group_data: AgentGroupCreate):
    """创建新的Agent小组
    
    Args:
        group_data: 小组创建数据
    
    Returns:
        创建的Agent小组
    """
    try:
        # 验证调度策略
        if group_data.strategy not in STRATEGY_NAMES:
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的调度策略: {group_data.strategy}。支持的策略: {list(STRATEGY_NAMES.keys())}"
            )
        
        # 检查名称唯一性
        existing_names = [g['name'] for g in _agent_groups.values()]
        if group_data.name in existing_names:
            raise HTTPException(status_code=409, detail=f"小组名称已存在: {group_data.name}")
        
        # 生成唯一ID
        group_id = f"group_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        
        # 创建小组
        new_group = {
            'id': group_id,
            'name': group_data.name,
            'members': group_data.members,
            'strategy': group_data.strategy,
            'circuit_breaker': group_data.circuit_breaker,
            'elastic_scaling': group_data.elastic_scaling,
            'status': '离线',  # 新创建的小组默认为离线状态
            'created_at': now,
            'updated_at': now,
            'last_active': None
        }
        
        # 保存到内存
        _agent_groups[group_id] = new_group
        
        # 尝试保存到数据库
        if _check_db_available():
            if not _save_group_to_db(new_group):
                logger.warning(f"保存小组到数据库失败，仅保存到内存: {group_id}")
        
        logger.info(f"创建Agent小组成功: {group_data.name} (ID: {group_id})")
        
        # 记录审计日志
        AuditLogger.log('CREATE', group_id, {
            'name': group_data.name,
            'members': group_data.members,
            'strategy': group_data.strategy
        })
        
        return AgentGroupResponse(
            id=group_id,
            name=group_data.name,
            members=group_data.members,
            strategy=STRATEGY_NAMES[group_data.strategy],
            circuit_breaker=group_data.circuit_breaker,
            elastic_scaling=group_data.elastic_scaling,
            status='离线',
            created_at=now,
            updated_at=now,
            members_count=len(group_data.members),
            last_active=None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建Agent小组失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建Agent小组失败: {str(e)}")

@router.put("/{group_id}", response_model=AgentGroupResponse)
async def update_agent_group(group_id: str, group_data: AgentGroupUpdate):
    """更新Agent小组配置
    
    Args:
        group_id: 小组ID
        group_data: 更新数据
    
    Returns:
        更新后的Agent小组
    """
    try:
        if group_id not in _agent_groups:
            raise HTTPException(status_code=404, detail=f"Agent小组不存在: {group_id}")
        
        group = _agent_groups[group_id]
        
        # 验证调度策略
        if group_data.strategy and group_data.strategy not in STRATEGY_NAMES:
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的调度策略: {group_data.strategy}。支持的策略: {list(STRATEGY_NAMES.keys())}"
            )
        
        # 更新字段
        if group_data.name is not None:
            group['name'] = group_data.name
        if group_data.members is not None:
            group['members'] = group_data.members
        if group_data.strategy is not None:
            group['strategy'] = group_data.strategy
        if group_data.circuit_breaker is not None:
            group['circuit_breaker'] = group_data.circuit_breaker
        if group_data.elastic_scaling is not None:
            group['elastic_scaling'] = group_data.elastic_scaling
        
        group['updated_at'] = datetime.now().isoformat()
        
        # 尝试保存到数据库
        if _check_db_available():
            if not _save_group_to_db(group):
                logger.warning(f"更新小组到数据库失败，仅更新内存: {group_id}")
        
        logger.info(f"更新Agent小组成功: {group['name']} (ID: {group_id})")
        
        # 记录审计日志
        AuditLogger.log('UPDATE', group_id, {
            'name': group['name'],
            'members': group['members'],
            'strategy': group['strategy']
        })
        
        return AgentGroupResponse(
            id=group['id'],
            name=group['name'],
            members=group['members'],
            strategy=STRATEGY_NAMES.get(group['strategy'], group['strategy']),
            circuit_breaker=group['circuit_breaker'],
            elastic_scaling=group['elastic_scaling'],
            status=group['status'],
            created_at=group['created_at'],
            updated_at=group['updated_at'],
            members_count=len(group['members']),
            last_active=group.get('last_active')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新Agent小组失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新Agent小组失败: {str(e)}")

@router.delete("/{group_id}")
async def delete_agent_group(group_id: str):
    """删除Agent小组
    
    Args:
        group_id: 小组ID
    
    Returns:
        删除结果
    """
    try:
        if group_id not in _agent_groups:
            raise HTTPException(status_code=404, detail=f"Agent小组不存在: {group_id}")
        
        group_name = _agent_groups[group_id]['name']
        
        # 从内存删除
        del _agent_groups[group_id]
        
        # 尝试从数据库删除
        if _check_db_available():
            if not _delete_group_from_db(group_id):
                logger.warning(f"从数据库删除小组失败，仅删除内存数据: {group_id}")
        
        logger.info(f"删除Agent小组成功: {group_name} (ID: {group_id})")
        
        # 记录审计日志
        AuditLogger.log('DELETE', group_id, {
            'name': group_name
        })
        
        return {
            "success": True,
            "message": f"Agent小组 '{group_name}' 已删除",
            "group_id": group_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除Agent小组失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除Agent小组失败: {str(e)}")

@router.post("/{group_id}/start")
async def start_agent_group(group_id: str):
    """启动Agent小组
    
    Args:
        group_id: 小组ID
    
    Returns:
        启动结果
    """
    try:
        if group_id not in _agent_groups:
            raise HTTPException(status_code=404, detail=f"Agent小组不存在: {group_id}")
        
        group = _agent_groups[group_id]
        
        # 检查是否已经在运行
        if group['status'] == '运行中':
            return {
                "success": True,
                "message": f"Agent小组 '{group['name']}' 已经在运行中",
                "status": group['status']
            }
        
        # 更新状态
        old_status = group['status']
        group['status'] = '运行中'
        group['updated_at'] = datetime.now().isoformat()
        group['last_active'] = datetime.now().isoformat()
        
        # 尝试保存到数据库
        if _check_db_available():
            if not _save_group_to_db(group):
                logger.warning(f"更新小组状态到数据库失败，仅更新内存: {group_id}")
        
        logger.info(f"启动Agent小组成功: {group['name']} (ID: {group_id}, {old_status} → 运行中)")
        
        # 记录审计日志
        AuditLogger.log('START', group_id, {
            'name': group['name'],
            'previous_status': old_status,
            'members': group['members']
        })
        
        # TODO: 这里可以添加实际启动Agent的逻辑
        # 例如：调用agent_coordinator.start_group(group_id)
        
        return {
            "success": True,
            "message": f"Agent小组 '{group['name']}' 已启动",
            "status": "运行中",
            "members": group['members'],
            "strategy": STRATEGY_NAMES.get(group['strategy'], group['strategy'])
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动Agent小组失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动Agent小组失败: {str(e)}")

@router.post("/{group_id}/stop")
async def stop_agent_group(group_id: str):
    """停止Agent小组
    
    Args:
        group_id: 小组ID
    
    Returns:
        停止结果
    """
    try:
        if group_id not in _agent_groups:
            raise HTTPException(status_code=404, detail=f"Agent小组不存在: {group_id}")
        
        group = _agent_groups[group_id]
        
        # 检查是否已经停止
        if group['status'] == '离线':
            return {
                "success": True,
                "message": f"Agent小组 '{group['name']}' 已经停止",
                "status": group['status']
            }
        
        # 更新状态
        old_status = group['status']
        group['status'] = '休眠'
        group['updated_at'] = datetime.now().isoformat()
        
        # 尝试保存到数据库
        if _check_db_available():
            if not _save_group_to_db(group):
                logger.warning(f"更新小组状态到数据库失败，仅更新内存: {group_id}")
        
        logger.info(f"停止Agent小组成功: {group['name']} (ID: {group_id}, {old_status} → 休眠)")
        
        # 记录审计日志
        AuditLogger.log('STOP', group_id, {
            'name': group['name'],
            'previous_status': old_status
        })
        
        # TODO: 这里可以添加实际停止Agent的逻辑
        # 例如：调用agent_coordinator.stop_group(group_id)
        
        return {
            "success": True,
            "message": f"Agent小组 '{group['name']}' 已停止",
            "status": "休眠",
            "previous_status": old_status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止Agent小组失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"停止Agent小组失败: {str(e)}")

def _get_strategy_description(strategy_key: str) -> str:
    """获取调度策略的描述"""
    descriptions = {
        'weighted_round_robin': '根据Agent权重轮询分配任务',
        'least_load': '将任务分配给当前负载最低的Agent',
        'random': '随机选择Agent执行任务',
        'priority': '根据优先级顺序分配任务'
    }
    return descriptions.get(strategy_key, '未知策略')

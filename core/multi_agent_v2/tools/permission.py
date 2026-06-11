"""
权限系统 — 三级权限控制

allow: 自动执行
ask: 需要用户确认
deny: 禁止执行

对标 gemini-cli 的 PolicyEngine
"""

import fnmatch
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PermissionLevel(Enum):
    """权限级别"""
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class PermissionRule:
    """权限规则"""
    pattern: str
    level: PermissionLevel
    reason: str = ""
    priority: int = 0  # 数值越大优先级越高


@dataclass
class PermissionResult:
    """权限检查结果"""
    allowed: bool
    level: PermissionLevel
    reason: str = ""
    need_ask: bool = False
    matched_rule: Optional[PermissionRule] = None


# 默认规则：全部 allow（除了危险操作 deny）
DEFAULT_RULES = [
    # ── 读操作：自动允许 ──
    PermissionRule("read:*", PermissionLevel.ALLOW, "读取文件"),
    PermissionRule("file:read", PermissionLevel.ALLOW, "读取文件"),
    PermissionRule("web_search:*", PermissionLevel.ALLOW, "网络搜索"),
    PermissionRule("fetch_url:*", PermissionLevel.ALLOW, "获取网页"),
    PermissionRule("fetch_json:*", PermissionLevel.ALLOW, "获取JSON"),
    PermissionRule("rag_search:*", PermissionLevel.ALLOW, "RAG搜索"),
    PermissionRule("browser_snapshot", PermissionLevel.ALLOW, "浏览器快照"),
    PermissionRule("browser_screenshot", PermissionLevel.ALLOW, "浏览器截图"),
    PermissionRule("browser_navigate:*", PermissionLevel.ALLOW, "浏览器导航"),
    PermissionRule("browser_click:*", PermissionLevel.ALLOW, "浏览器点击"),
    PermissionRule("browser_type:*", PermissionLevel.ALLOW, "浏览器输入"),

    # ── 写操作：自动允许（默认同意模式）──
    PermissionRule("file:write", PermissionLevel.ALLOW, "写入文件"),
    PermissionRule("file:create", PermissionLevel.ALLOW, "创建文件"),
    PermissionRule("file:edit", PermissionLevel.ALLOW, "编辑文件"),
    PermissionRule("file:delete", PermissionLevel.ALLOW, "删除文件"),
    PermissionRule("execute_python:*", PermissionLevel.ALLOW, "执行Python代码"),
    PermissionRule("execute_shell:*", PermissionLevel.ALLOW, "执行Shell命令"),
    PermissionRule("execute_command:*", PermissionLevel.ALLOW, "执行命令"),
    PermissionRule("execute_script:*", PermissionLevel.ALLOW, "执行脚本"),
    PermissionRule("open_app:*", PermissionLevel.ALLOW, "打开应用"),

    # ── 通配符：所有其他操作允许 ──
    PermissionRule("*", PermissionLevel.ALLOW, "默认允许"),

    # ── 危险操作：禁止（最高优先级）──
    PermissionRule("execute_shell:rm -rf /", PermissionLevel.DENY, "禁止递归删除根目录"),
    PermissionRule("execute_shell:rm -rf /*", PermissionLevel.DENY, "禁止递归删除根目录"),
    PermissionRule("execute_python:import os; os.system(*)", PermissionLevel.DENY, "禁止系统命令执行"),
    PermissionRule("write_file:/etc/*", PermissionLevel.DENY, "禁止写入系统目录"),
    PermissionRule("write_file:/usr/*", PermissionLevel.DENY, "禁止写入系统目录"),
    PermissionRule("write_file:/var/*", PermissionLevel.DENY, "禁止写入系统目录"),
    PermissionRule("write_file:~/.ssh/*", PermissionLevel.DENY, "禁止写入SSH密钥目录"),
    PermissionRule("write_file:~/.aws/*", PermissionLevel.DENY, "禁止写入AWS凭证目录"),
]


class PermissionService:
    """三级权限服务"""

    def __init__(self, config_path: Optional[str] = None):
        self.rules: List[PermissionRule] = []
        self.cache: Dict[str, PermissionResult] = {}
        self._load_rules(config_path)

    def _load_rules(self, config_path: Optional[str] = None):
        """加载权限规则"""
        # 先加载默认规则
        self.rules.extend(DEFAULT_RULES)

        # 尝试从文件加载自定义规则
        if config_path and os.path.exists(config_path):
            try:
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)

                if config and "permissions" in config:
                    perms = config["permissions"]
                    for level_str, patterns in perms.items():
                        try:
                            level = PermissionLevel(level_str)
                        except ValueError:
                            continue
                        for pattern in patterns:
                            if isinstance(pattern, str):
                                self.rules.append(
                                    PermissionRule(pattern, level, f"自定义规则: {level_str}")
                                )
                            elif isinstance(pattern, dict):
                                self.rules.append(
                                    PermissionRule(
                                        pattern.get("pattern", ""),
                                        level,
                                        pattern.get("reason", ""),
                                        pattern.get("priority", 0),
                                    )
                                )
                logger.info(f"从 {config_path} 加载了 {len(self.rules)} 条权限规则")
            except Exception as e:
                logger.warning(f"加载权限配置失败: {e}，使用默认规则")

    def _match_pattern(self, tool_name: str, arguments: dict, pattern: str) -> bool:
        """匹配工具名和参数模式"""
        # 分离工具名和参数模式
        if ":" in pattern:
            pattern_tool, pattern_args = pattern.split(":", 1)
        else:
            pattern_tool = pattern
            pattern_args = None

        # 检查工具名
        if not fnmatch.fnmatch(tool_name, pattern_tool):
            return False

        # 如果没有参数模式，匹配成功
        if pattern_args is None:
            return True

        # 检查参数
        if arguments:
            # 匹配 action 字段（文件操作）
            if "action" in arguments:
                action = arguments["action"]
                if fnmatch.fnmatch(action, pattern_args):
                    return True
            # 匹配 command 字段（Shell 命令）
            if "command" in arguments:
                cmd = arguments["command"]
                if fnmatch.fnmatch(cmd, pattern_args):
                    return True
            # 匹配 code 字段（Python 代码）
            if "code" in arguments:
                code = arguments["code"]
                if fnmatch.fnmatch(code, pattern_args):
                    return True
            # 匹配 path 字段（文件路径）
            if "path" in arguments:
                path = arguments["path"]
                if fnmatch.fnmatch(path, pattern_args):
                    return True
            # 匹配 query 字段（搜索查询）
            if "query" in arguments:
                query = arguments["query"]
                if fnmatch.fnmatch(query, pattern_args):
                    return True
            # 匹配 url 字段（网络请求）
            if "url" in arguments:
                url = arguments["url"]
                if fnmatch.fnmatch(url, pattern_args):
                    return True
            # 最后匹配整个参数字符串
            args_str = str(arguments)
            if fnmatch.fnmatch(args_str, pattern_args):
                return True

        return False

    def check(self, tool_name: str, arguments: Optional[dict] = None) -> PermissionResult:
        """
        检查工具调用权限

        按优先级匹配规则：deny > ask > allow
        """
        if arguments is None:
            arguments = {}

        # 生成缓存键
        cache_key = f"{tool_name}:{str(sorted(arguments.items()))}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # 按优先级排序规则
        sorted_rules = sorted(self.rules, key=lambda r: -r.priority)

        # 收集匹配的规则
        matched_rules = []
        for rule in sorted_rules:
            if self._match_pattern(tool_name, arguments, rule.pattern):
                matched_rules.append(rule)

        if not matched_rules:
            # 没有匹配的规则，默认 ask
            result = PermissionResult(
                allowed=False,
                level=PermissionLevel.ASK,
                reason="无匹配规则，需要用户确认",
                need_ask=True,
            )
        else:
            # 按优先级选择最高优先级的规则
            # deny > ask > allow
            deny_rules = [r for r in matched_rules if r.level == PermissionLevel.DENY]
            ask_rules = [r for r in matched_rules if r.level == PermissionLevel.ASK]
            allow_rules = [r for r in matched_rules if r.level == PermissionLevel.ALLOW]

            if deny_rules:
                rule = deny_rules[0]
                result = PermissionResult(
                    allowed=False,
                    level=PermissionLevel.DENY,
                    reason=rule.reason,
                    need_ask=False,
                    matched_rule=rule,
                )
            elif ask_rules:
                rule = ask_rules[0]
                result = PermissionResult(
                    allowed=False,
                    level=PermissionLevel.ASK,
                    reason=rule.reason,
                    need_ask=True,
                    matched_rule=rule,
                )
            else:
                rule = allow_rules[0]
                result = PermissionResult(
                    allowed=True,
                    level=PermissionLevel.ALLOW,
                    reason=rule.reason,
                    need_ask=False,
                    matched_rule=rule,
                )

        # 缓存结果
        self.cache[cache_key] = result
        return result

    def add_rule(self, pattern: str, level: PermissionLevel, reason: str = "", priority: int = 0):
        """动态添加规则"""
        rule = PermissionRule(pattern, level, reason, priority)
        self.rules.append(rule)
        logger.info(f"添加权限规则: {pattern} -> {level.value}")

    def remove_rule(self, pattern: str):
        """移除规则"""
        self.rules = [r for r in self.rules if r.pattern != pattern]
        logger.info(f"移除权限规则: {pattern}")

    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()


# 全局权限服务实例
_permission_service: Optional[PermissionService] = None


def get_permission_service(config_path: Optional[str] = None) -> PermissionService:
    """获取全局权限服务实例"""
    global _permission_service
    if _permission_service is None:
        _permission_service = PermissionService(config_path)
    return _permission_service

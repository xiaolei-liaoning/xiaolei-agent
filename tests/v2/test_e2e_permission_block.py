"""
E2E 测试: Permission 拦截

验证 ShellGuard 危险命令扫描 → 权限拦截
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.multi_agent_v2.agents.react_core import RunContext


class TestPermissionBlock:
    """权限拦截 e2e 流程"""

    def test_permission_service_deny_rm_rf(self):
        """PermissionService 拦截 rm -rf /"""
        from core.multi_agent_v2.tools.permission import get_permission_service
        svc = get_permission_service()
        result = svc.check("execute_shell", {"command": "rm -rf /"})
        assert result.allowed is False
        assert "禁止" in result.reason

    def test_permission_service_deny_rm_rf_star(self):
        """PermissionService 拦截 rm -rf /*"""
        from core.multi_agent_v2.tools.permission import get_permission_service
        svc = get_permission_service()
        result = svc.check("execute_shell", {"command": "rm -rf /*"})
        assert result.allowed is False

    def test_permission_service_allow_normal_command(self):
        """PermissionService 允许正常命令"""
        from core.multi_agent_v2.tools.permission import get_permission_service
        svc = get_permission_service()
        result = svc.check("execute_shell", {"command": "ls -la"})
        assert result.allowed is True

    def test_permission_service_deny_system_dir_write(self):
        """PermissionService 拒绝写入系统目录"""
        from core.multi_agent_v2.tools.permission import get_permission_service
        svc = get_permission_service()
        result = svc.check("write_file", {"path": "/etc/passwd", "content": "x"})
        assert result.allowed is False
        assert "禁止" in result.reason

    def test_shell_guard_detects_dangerous(self):
        """ShellGuard 检测危险命令"""
        from core.multi_agent_v2.tools.shell_guard import get_shell_guard
        guard = get_shell_guard()
        scan = guard.scan("rm -rf /")
        assert scan.safe is False
        high_risks = [r for r in scan.risks if r.level == "high"]
        assert len(high_risks) > 0

    def test_shell_guard_allows_safe(self):
        """ShellGuard 允许安全命令"""
        from core.multi_agent_v2.tools.shell_guard import get_shell_guard
        guard = get_shell_guard()
        scan = guard.scan("ls -la /tmp")
        assert scan.safe is True


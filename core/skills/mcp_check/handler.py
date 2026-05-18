"""MCP可用性检查技能

当所有工具都无法使用时，提供MCP服务器可用性检查功能，帮助用户诊断问题。
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class MCPCheckHandler:
    """MCP可用性检查处理器"""
    
    def __init__(self):
        self.available_servers = []
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行MCP可用性检查
        
        Returns:
            检查结果字典，包含所有可用MCP服务器信息
        """
        logger.info("执行MCP可用性检查")
        
        try:
            # 检查所有可用的MCP服务器
            servers = await self._check_all_servers()
            
            if servers:
                result = {
                    "success": True,
                    "message": f"发现 {len(servers)} 个可用的MCP服务器",
                    "servers": servers,
                    "suggestion": self._generate_suggestion(servers)
                }
            else:
                result = {
                    "success": False,
                    "message": "未发现可用的MCP服务器",
                    "servers": [],
                    "suggestion": "请检查MCP服务器是否已启动，或尝试连接the-agency"
                }
            
            return result
            
        except Exception as e:
            logger.error(f"MCP检查失败: {e}")
            return {
                "success": False,
                "message": f"MCP检查失败: {str(e)}",
                "servers": [],
                "suggestion": "请检查MCP服务器配置"
            }
    
    async def _check_all_servers(self) -> List[Dict[str, Any]]:
        """检查所有可用的MCP服务器"""
        servers = []
        
        # 检查awesome-mcp-servers中的服务器
        servers.extend(await self._check_awesome_mcp())
        
        # 检查本地MCP服务器
        servers.extend(await self._check_local_mcp())
        
        # 检查the-agency
        servers.extend(await self._check_agency())
        
        return servers
    
    async def _check_awesome_mcp(self) -> List[Dict[str, Any]]:
        """检查awesome-mcp-servers"""
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager
            
            available = awesome_mcp_manager.get_available_quick_connect()
            return [
                {
                    "name": server["name"],
                    "type": "awesome-mcp",
                    "description": server.get("description", ""),
                    "status": "available"
                }
                for server in available
            ]
        except Exception as e:
            logger.debug(f"检查awesome-mcp失败: {e}")
            return []
    
    async def _check_local_mcp(self) -> List[Dict[str, Any]]:
        """检查本地MCP服务器"""
        import os
        
        servers = []
        mcp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "mcp")
        
        # 检查本地MCP服务器文件
        local_servers = [
            ("calculator", "计算器MCP服务器", "calculator_mcp_server.py"),
            ("weather", "天气MCP服务器", "weather_mcp_server.py"),
            ("fun", "趣味MCP服务器", "fun_mcp_server.py"),
        ]
        
        for name, desc, filename in local_servers:
            filepath = os.path.join(mcp_dir, filename)
            if os.path.exists(filepath):
                servers.append({
                    "name": name,
                    "type": "local",
                    "description": desc,
                    "status": "available" if self._is_server_running(name) else "stopped",
                    "path": filepath
                })
        
        return servers
    
    def _is_server_running(self, server_name: str) -> bool:
        """检查服务器是否正在运行（简化版）"""
        # 在实际实现中，可以检查端口是否被占用
        # 这里简化处理，假设本地服务器未运行
        return False
    
    async def _check_agency(self) -> List[Dict[str, Any]]:
        """检查the-agency服务器"""
        try:
            from core.mcp.mcp_client import mcp_client
            
            # 检查是否已连接
            servers = await mcp_client.list_servers()
            if "the-agency" in servers:
                return [{
                    "name": "the-agency",
                    "type": "agency",
                    "description": "Anthropic Agency服务器",
                    "status": "connected"
                }]
        except Exception as e:
            logger.debug(f"检查the-agency失败: {e}")
        
        return []
    
    def _generate_suggestion(self, servers: List[Dict[str, Any]]) -> str:
        """根据可用服务器生成建议"""
        if not servers:
            return "未发现可用的MCP服务器，请检查配置"
        
        suggestions = []
        
        # 分类建议
        weather_servers = [s for s in servers if "weather" in s["name"].lower()]
        calc_servers = [s for s in servers if "calculator" in s["name"].lower()]
        search_servers = [s for s in servers if any(k in s["name"].lower() for k in ["search", "brave", "tavily"])]
        
        if weather_servers:
            suggestions.append(f"天气查询：可用服务器 {', '.join(s['name'] for s in weather_servers)}")
        
        if calc_servers:
            suggestions.append(f"计算器：可用服务器 {', '.join(s['name'] for s in calc_servers)}")
        
        if search_servers:
            suggestions.append(f"搜索：可用服务器 {', '.join(s['name'] for s in search_servers)}")
        
        if suggestions:
            return "可用功能：\n" + "\n".join(f"• {s}" for s in suggestions)
        
        return "发现可用MCP服务器"


# 全局处理器实例
_mcp_check_handler = None


def get_mcp_check_handler() -> MCPCheckHandler:
    """获取MCP检查处理器单例"""
    global _mcp_check_handler
    if _mcp_check_handler is None:
        _mcp_check_handler = MCPCheckHandler()
    return _mcp_check_handler


# 快捷执行函数
async def check_mcp_availability() -> Dict[str, Any]:
    """检查MCP服务器可用性"""
    handler = get_mcp_check_handler()
    return await handler.execute()


# 同步包装
def check_mcp_availability_sync() -> Dict[str, Any]:
    """同步检查MCP服务器可用性"""
    return asyncio.run(check_mcp_availability())
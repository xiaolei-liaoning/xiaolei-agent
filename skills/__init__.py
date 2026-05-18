"""Skills 模块 — 旧 handler 体系已迁移到 MCP

所有工具型技能 → <project>/mcp/*_mcp_server.py (独立进程)
所有指导型技能 → <project>/core/guidance_skills.py (原生嵌入 SkillRegistry)

skills/ 目录现仅保留：
- 人物/ — 角色扮演配置
- marketplace/ — 独立技能市场系统
- mcp_connector/ — MCP 连接器
- mcp_orchestrator/ — MCP 协调器
- workflow_engine.py — 工作流引擎
"""

"""
单步任务处理器 — 原始执行函数（不含认知闭环）

CognitivePipeline._execute 直接调用此模块中的函数完成技能执行，
避免 pipeline 自我递归调用。
"""

import asyncio
import re
import logging
from typing import Dict, Any

from ..services.clarification_service import get_clarification_service

logger = logging.getLogger(__name__)


async def execute_tool(
    message: str,
    skill_name: str,
    user_id: int,
    dispatcher,
    db_initialized: bool = False,
) -> Dict[str, Any]:
    """执行一个技能调用（不经过认知闭环）

    Args:
        message: 用户消息
        skill_name: 匹配的技能名
        user_id: 用户ID
        dispatcher: SkillDispatcher 实例
        db_initialized: 数据库是否已初始化

    Returns:
        执行结果
    """
    if skill_name == "chat":
        from .chat_handler import handle_chat
        return await handle_chat(message, user_id, "default", db_initialized)

    if skill_name == "mcp_suggestion":
        return await _handle_mcp_suggestion(message)

    params: Dict[str, Any] = dispatcher.extract_params(message, skill_name)

    if skill_name == "rag_search":
        params["query"] = message
        params["user_id"] = user_id
    elif skill_name == "system_toolbox":
        if "时间" in message or "几点" in message:
            params["action"] = "time"
        elif "日期" in message or "几号" in message:
            params["action"] = "date"

    if skill_name.startswith("third_party_"):
        result = await _handle_third_party(skill_name, message, params)
    elif skill_name == "batch_operations":
        result = await _handle_batch_operations(params)
    elif skill_name == "text_analyzer":
        result = await _handle_text_analyzer(message)
    else:
        # 优先使用统一 SkillRegistry 接口
        from ..skill_base import get_skill_registry
        skill_reg = get_skill_registry()
        skill = skill_reg.get(skill_name)
        if skill:
            result = await skill.execute(params, context=None)
        else:
            result = await _handle_tool(skill_name, params)

    if not isinstance(result, dict):
        result = {"success": True, "result": str(result)}

    result["tool_call"] = {"name": skill_name, "params": params}

    return result


async def _handle_third_party(skill_name: str, message: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """处理第三方应用技能"""
    try:
        from mcp._impl.third_party.handler import app_manager
        app_name = skill_name.replace("third_party_", "")

        action = params.get("action")
        if not action:
            action = _extract_third_party_action(app_name, message, params)

        result = await app_manager.execute(app_name, action, params)

        if not result.get("success"):
            error_msg = result.get('error', result.get('data', {}).get('error', '未知错误'))
            if '密钥未配置' in error_msg or 'API key' in error_msg.lower() or 'token' in error_msg.lower():
                result["reply"] = f"⚠️ {app_name} 功能需要配置API密钥才能使用。\n\n" \
                                f"您可以在 skills/third_party/config.yml 中配置 {app_name} 的API密钥。"
            else:
                result["reply"] = f"{app_name} 应用执行失败: {error_msg}"
        else:
            data = result.get("data", {})
            if isinstance(data, dict):
                if data.get('success') is False:
                    error_msg = data.get('error', '未知错误')
                    if '密钥未配置' in error_msg or 'API key' in error_msg.lower():
                        result["reply"] = f"⚠️ {app_name} 功能需要配置API密钥才能使用。"
                    else:
                        result["reply"] = f"{app_name} 应用执行失败: {error_msg}"
                else:
                    result["reply"] = f"{app_name} 应用执行成功:\n" + "\n".join([f"{k}: {v}" for k, v in data.items()])
            else:
                result["reply"] = f"{app_name} 应用执行成功: {data}"
    except Exception as e:
        logger.error("第三方应用 %s 执行异常: %s", skill_name, e)
        result = {"success": False, "error": str(e), "reply": f"第三方应用执行异常: {str(e)}"}

    return result


def _extract_third_party_action(app_name: str, message: str, params: Dict[str, Any]) -> str:
    """从消息中提取第三方应用的操作类型"""
    if app_name == "github":
        if "仓库" in message or "repo" in message.lower():
            repo_match = re.search(r'(?:查看|查询|获取)\s*(\w+)/([\w-]+)\s*(?:仓库|repo)', message)
            if repo_match:
                params["owner"] = repo_match.group(1)
                params["repo"] = repo_match.group(2)
                return "get_repo"
            return "get_info"
        elif "用户" in message or "user" in message.lower():
            user_match = re.search(r'(?:查看|查询|获取)\s*(?:用户|user)\s*(\w+)', message)
            if user_match:
                params["username"] = user_match.group(1)
                return "get_user"
            return "get_info"
        return "get_info"
    elif app_name == "twitter":
        if "用户" in message or "user" in message.lower():
            user_match = re.search(r'(?:查看|查询|获取)\s*(?:用户|user)\s*(\w+)', message)
            if user_match:
                params["username"] = user_match.group(1)
                return "get_user"
            return "get_info"
        elif "推文" in message or "tweet" in message.lower():
            user_match = re.search(r'(?:查看|查询|获取)\s*(\w+)\s*(?:的|\'s)\s*(?:推文|tweet)', message)
            if user_match:
                params["username"] = user_match.group(1)
                return "get_tweets"
            return "get_info"
        return "get_info"
    return "get_info"


async def _handle_batch_operations(params: Dict[str, Any]) -> Dict[str, Any]:
    """处理批量操作"""
    try:
        from mcp._impl.third_party.batch_operations import batch_manager
        operation_type = params.get("operation_type", "execute_batch")

        if operation_type == "execute_batch":
            operations = params.get("operations", [])
            result = await batch_manager.execute_batch(operations)
            success_count = sum(1 for r in result if r.get('success'))
            failure_count = len(result) - success_count
            result["reply"] = f"批量操作完成: 成功 {success_count} 个, 失败 {failure_count} 个"
        elif operation_type == "sync_data":
            source_app = params.get("source_app")
            target_apps = params.get("target_apps", [])
            data_type = params.get("data_type")
            sync_params = params.get("params", {})
            result = await batch_manager.sync_data(source_app, target_apps, data_type, sync_params)
            result["reply"] = f"数据同步完成: 成功 {result.get('success_count', 0)} 个"
        elif operation_type == "compare_data":
            apps = params.get("apps", [])
            data_type = params.get("data_type")
            compare_params = params.get("params", {})
            result = await batch_manager.compare_data(apps, data_type, compare_params)
            result["reply"] = f"数据比较完成"
        else:
            result = {"success": False, "error": f"未知操作类型: {operation_type}"}
    except Exception as e:
        logger.error("批量操作执行异常: %s", e)
        result = {"success": False, "error": str(e), "reply": f"批量操作执行异常: {str(e)}"}

    return result


async def _handle_text_analyzer(message: str) -> Dict[str, Any]:
    """处理文本分析"""
    try:
        from ..tasks.task_execution_interface import get_text_analyzer_agent
        from ..search.keyword_extractor import get_keyword_extractor

        analyzer_class = get_text_analyzer_agent()
        analyzer = analyzer_class()
        text_content = message.replace("文本分析:", "").strip()
        extractor = get_keyword_extractor()
        extraction = await extractor.extract(text_content)
        paragraphs = analyzer._split_into_paragraphs(text_content)
        summaries = []
        for i, paragraph in enumerate(paragraphs):
            summary = analyzer._generate_summary(paragraph)
            summaries.append({
                "paragraph_index": i,
                "content": paragraph,
                "summary": summary
            })
        title = analyzer._generate_title(text_content)
        tree = analyzer._build_content_tree(title, paragraphs, summaries)
        analyzer._update_context_memory(tree)
        keywords = [kw.word for kw in extraction.keywords[:5]] if extraction.keywords else []

        reply = f"📊 **文本分析完成**\n\n**标题**: {title}\n**段落数**: {len(paragraphs)}\n"
        if keywords:
            reply += f"🔑 **关键词**: {', '.join(keywords)}\n"

        result = {"success": True, "reply": reply}
    except Exception as e:
        logger.error("文本分析执行异常: %s", e)
        result = {"success": False, "error": str(e), "reply": f"❌ 文本分析失败: {str(e)}"}

    return result


async def _handle_tool(skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """通过 SkillRegistry 或 ToolManager 执行工具

    优先使用 SkillRegistry（已注册 GuidanceSkill + MCP Skills），
    回退到 ToolManager（仅保留 code_sandbox）。
    """
    try:
        from ..skill_base import get_skill_registry
        reg = get_skill_registry()
        skill = reg.get(skill_name)
        if skill:
            return await skill.execute(params, context=None)
    except Exception:
        pass

    # 回退到 ToolManager
    try:
        from tools.tool_manager import ToolManager
        tm = ToolManager.get_instance()
        result = tm.execute(skill_name, **params)
        if asyncio.iscoroutine(result):
            result = await result
    except Exception as e:
        logger.error("工具 %s 执行异常: %s", skill_name, e)
        result = {"success": False, "error": str(e)}

    return result


async def _handle_mcp_suggestion(message: str) -> Dict[str, Any]:
    """处理MCP建议"""
    try:
        from core.mcp.awesome_mcp_manager import awesome_mcp_manager

        available_servers = awesome_mcp_manager.get_available_quick_connect()

        if not available_servers:
            return {
                "success": True,
                "reply": "抱歉，我没有理解您的需求。您可以尝试更详细地描述您的问题。",
                "tool_call": {"name": "chat", "params": {}}
            }

        reply = f"🤔 我注意到您提到的需求可能无法通过现有技能直接处理。\n\n"
        reply += f"💡 **不过，我可以帮您使用 MCP 服务器来完成这个任务！**\n\n"
        reply += f"当前可用的 MCP 服务器有 {len(available_servers)} 个：\n\n"

        popular_servers = available_servers[:10]
        descriptions = {
            "calculator": "计算器服务", "weather": "天气查询",
            "fun": "趣味工具", "file-ops": "文件操作",
            "text-processing": "文本处理", "github": "GitHub集成",
            "playwright": "浏览器自动化", "sqlite": "SQLite数据库",
            "postgres": "PostgreSQL数据库", "brave-search": "Brave搜索引擎",
            "slack": "Slack集成", "discord": "Discord集成",
            "filesystem": "文件系统访问", "fetch": "HTTP请求",
            "tavily": "AI搜索", "sequential-thinking": "顺序思考",
            "e2b": "代码沙盒", "gitlab": "GitLab集成",
            "sentry": "错误监控", "chroma": "向量数据库",
        }
        for i, server in enumerate(popular_servers, 1):
            desc = descriptions.get(server, "")
            reply += f"{i}. **{server}** - {desc}\n"

        if len(available_servers) > 10:
            reply += f"\n... 还有 {len(available_servers) - 10} 个其他服务器\n"

        reply += f"\n📝 **使用方法**：\n"
        reply += f"• 输入 `/mcp connect <服务器名>` 连接服务器\n"
        reply += f"• 然后使用 `/mcp quick <工具名> 参数` 调用工具\n"
        reply += f"• 或输入 `/mcp` 查看完整帮助\n\n"
        reply += f"❓ **您需要我帮您连接哪个 MCP 服务器吗？**"

        return {
            "success": True, "reply": reply,
            "tool_call": {"name": "mcp_suggestion", "params": {"available_servers": available_servers}},
            "md_path": None
        }
    except Exception as e:
        logger.error(f"MCP建议生成失败: {e}")
        return {
            "success": True,
            "reply": "抱歉，我没有理解您的需求。您可以尝试更详细地描述您的问题。",
            "tool_call": {"name": "chat", "params": {}}
        }


async def _route_to_multi_agent(message: str, user_id: int,
                                 skill_name: str) -> Dict[str, Any]:
    """多Agent系统已移除，返回简单回复。"""
    return {
        "success": True,
        "reply": f"已收到: {message[:100]}",
        "multi_agent_result": False,
    }

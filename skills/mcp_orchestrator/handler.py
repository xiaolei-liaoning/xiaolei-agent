"""MCP协调器技能 - 引导LLM进行任务规划和工具选择

这个技能不执行具体操作，而是：
1. 分析用户请求
2. 规划任务步骤
3. 选择合适的MCP工具
4. 在MCP失败时触发降级机制（代码生成 → 反思分析）
"""
import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class MCPOrchestratorHandler:
    """MCP协调器 - 负责任务规划和降级处理"""
    
    def __init__(self):
        self.name = "mcp_orchestrator"
        self.description = "MCP任务协调器 - 规划任务并处理工具失败降级"
    
    async def execute(self, 
                     user_request: str,
                     mcp_server: str = "",
                     mcp_tool: str = "",
                     params: Dict[str, Any] = None,
                     **kwargs) -> Dict[str, Any]:
        """执行MCP协调任务
        
        三层降级机制：
        1. 检查参数完整性 → 缺少则触发clarification
        2. 尝试MCP工具 → 失败则触发代码生成
        3. 代码生成失败 → 触发反思机制
        
        Args:
            user_request: 用户原始请求
            mcp_server: MCP服务器名称
            mcp_tool: MCP工具名称
            params: 工具参数
            
        Returns:
            执行结果，包含降级策略
        """
        params = params or {}
        
        logger.info(f"MCP协调器收到请求: {user_request[:50]}...")
        logger.info(f"目标MCP: {mcp_server}/{mcp_tool}")
        
        # ── 第1层：检查参数完整性 ──
        missing_params = self._check_required_params(mcp_tool, params)
        if missing_params:
            logger.warning(f"缺少必要参数: {missing_params}")
            return {
                "success": False,
                "requires_clarification": True,
                "missing_params": missing_params,
                "clarification_message": f"需要补充以下信息：{', '.join(missing_params)}",
                "original_request": user_request
            }
        
        # ── 第2层：尝试执行MCP工具 ──
        mcp_success = False
        mcp_result = None
        error_msg = ""
        
        try:
#             from core.multi_agent_v2.agents.expert.mcp_agent import get_mcp_agent
            
            mcp_agent = get_mcp_agent()
            mcp_result = await mcp_agent.call(mcp_server, mcp_tool, **params)
            
            if mcp_result.get("success"):
                mcp_success = True
                return {
                    "success": True,
                    "mcp_executed": True,
                    "result": mcp_result.get("result"),
                    "message": mcp_result.get("message", "MCP工具执行成功")
                }
            
            # MCP调用失败
            error_msg = mcp_result.get("error", "未知错误")
            logger.warning(f"MCP工具执行失败: {error_msg}")
            
        except ImportError:
            error_msg = "MCP Agent模块未加载"
            logger.error(error_msg)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"MCP工具执行异常: {e}")
        
        # ─ 第3层：触发代码生成降级 ─
        if not mcp_success:
            logger.info("MCP失败，触发代码生成降级机制")
            code_gen_result = await self._try_code_generation_fallback(
                user_request, mcp_server, mcp_tool, params, error_msg
            )
            
            # 如果代码生成成功且需要用户确认，则直接返回预览，暂停流程
            if code_gen_result.get("success") and code_gen_result.get("need_confirmation"):
                return code_gen_result
            
            # 如果代码生成成功且不需要确认（例如某些自动执行场景，虽然当前实现总是要求确认，但保留扩展性）
            if code_gen_result.get("success"):
                return {
                    "success": True,
                    "code_generated": True,
                    "result": code_gen_result.get("result"),
                    "message": f"通过代码生成解决问题：{code_gen_result.get('message', '')}"
                }
            
            # ── 第4层：触发反思机制 ──
            # 只有在代码生成完全失败（未生成方案或LLM不可用）时才进入反思
            logger.info("代码生成也失败，触发反思机制")
            reflection_result = await self._try_reflection_fallback(
                user_request, mcp_server, mcp_tool, params, error_msg
            )
            
            return {
                "success": False,
                "requires_reflection": True,
                "reflection_result": reflection_result,
                "error": error_msg
            }
        
        return {"success": False, "error": "未知错误"}
    
    def _check_required_params(self, tool: str, params: Dict) -> List[str]:
        """检查工具的必要参数"""
        required_params_map = {
            "get_weather": ["city"],
            "search": ["query"],
            "calculate": ["expression"],
        }
        
        required = required_params_map.get(tool, [])
        missing = [p for p in required if p not in params]
        return missing
    
    async def _try_code_generation_fallback(self,
                                           user_request: str,
                                           mcp_server: str,
                                           mcp_tool: str,
                                           params: Dict,
                                           error_msg: str) -> Dict[str, Any]:
        """代码生成降级 - 让LLM生成替代方案代码（需要用户确认）
        
        执行流程：
        1. LLM分析问题并生成解决方案
        2. 返回方案预览，等待用户确认
        3. 用户确认后，再执行代码
        """
        try:
            from core.engine.llm_backend import get_llm_router
            
            router = get_llm_router()
            if not router.is_available():
                logger.warning("LLM不可用，跳过代码生成")
                return {"success": False}
            
            prompt = f"""你是一个智能编程助手。用户需要执行一个任务，但MCP工具不可用。

【用户需求】
{user_request}

【尝试的MCP工具】
服务器: {mcp_server}
工具: {mcp_tool}
参数: {params}
错误: {error_msg}

【任务】
请分析用户需求，判断是否可以通过编写Python/Shell脚本来解决。

如果可以，请：
1. 简要说明解决思路（1-2句话）
2. 生成可执行的Python代码（优先）或Shell命令
3. 代码必须安全、简洁，不要使用危险操作

如果无法通过代码解决，请回复："无法通过代码解决"

【输出格式】
解决思路：
[你的思路]

```python
# 你的代码
```
"""
            
            response = await router.simple_chat(
                user_message=prompt,
                system_prompt="你是一个专业的代码生成助手，擅长根据需求生成安全可执行的脚本。",
                temperature=0.3
            )
            
            if not response or "无法通过代码解决" in response:
                logger.info("LLM判断无法通过代码解决")
                return {"success": False}
            
            # 提取代码块
            code_match = re.search(r'```(?:python|bash|sh)?\s*\n(.*?)\n```', response, re.DOTALL)
            if not code_match:
                logger.warning("未找到代码块")
                return {"success": False}
            
            code = code_match.group(1).strip()
            if not code:
                return {"success": False}
            
            # 提取解决思路
            idea_match = re.search(r'解决思路：\s*(.*?)\n', response)
            idea = idea_match.group(1) if idea_match else ""
            
            # ⚠️ 关键修改：不直接执行，先返回方案让用户确认
            solution_preview = f"🔧 **检测到需要代码生成来解决您的问题**\n\n"
            solution_preview += f"**问题分析**: MCP工具 `{mcp_server}/{mcp_tool}` 执行失败\n"
            solution_preview += f"**错误信息**: {error_msg[:200]}\n\n"
            solution_preview += f"**解决方案**:\n{idea}\n\n"
            solution_preview += f"**生成的代码**:\n```{'python' if 'python' in code_match.group(0).lower() else 'bash'}\n{code[:500]}{'...' if len(code) > 500 else ''}\n```\n\n"
            solution_preview += f"⚠️ **注意**: 此代码将在沙盒环境中执行（超时30秒，内存限制256MB）\n\n"
            solution_preview += f"请回复 **继续** 以执行此方案，或回复 **取消** 放弃。"
            
            logger.info(f"生成代码方案，等待用户确认: {idea}")
            
            # 保存生成的代码到实例变量，供后续确认执行
            self._pending_code = {
                "code": code,
                "is_python": 'python' in code_match.group(0).lower(),
                "idea": idea
            }
            
            return {
                "success": True, 
                "reply": solution_preview,
                "need_confirmation": True,  # 标记需要用户确认
                "code_generated": True
            }
                
        except Exception as e:
            logger.error(f"代码生成降级异常: {e}")
            return {"success": False}
    
    async def execute_confirmed_code(self) -> Dict[str, Any]:
        """执行用户已确认的代码
        
        Returns:
            执行结果
        """
        if not hasattr(self, '_pending_code') or not self._pending_code:
            return {"success": False, "error": "没有待执行的代码"}
        
        try:
            from tools.tool_manager import ToolManager
            
            code_info = self._pending_code
            code = code_info["code"]
            is_python = code_info["is_python"]
            idea = code_info["idea"]
            
            # 清除待执行代码
            self._pending_code = None
            
            # 在沙盒中执行代码
            tm = ToolManager.get_instance()
            result = await tm.execute_in_sandbox(
                code=code,
                language="python" if is_python else "shell",
                timeout=30,
                max_memory_mb=256
            )
            
            if result.get("success"):
                logger.info(f"用户确认的代码执行成功: {idea}")
                return {
                    "success": True,
                    "result": result.get("result", result.get("stdout")),
                    "message": f"✅ 代码执行成功\n\n{idea}",
                    "code_executed": True
                }
            else:
                logger.warning(f"用户确认的代码执行失败: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get('error'),
                    "message": f"❌ 代码执行失败: {result.get('error')}"
                }
                
        except Exception as e:
            logger.error(f"代码执行异常: {e}")
            return {"success": False, "error": str(e)}
    
    async def _try_reflection_fallback(self,
                                      user_request: str,
                                      mcp_server: str,
                                      mcp_tool: str,
                                      params: Dict,
                                      error_msg: str) -> Dict[str, Any]:
        """反思机制降级 - 分析问题并提出改进方案（需要用户确认）
        
        执行流程：
        1. LLM分析问题失败原因
        2. 生成多个改进方案
        3. 返回方案预览，等待用户选择
        4. 用户确认后，执行选定的方案
        """
        try:
            from core.engine.llm_backend import get_llm_router
            
            router = get_llm_router()
            if not router.is_available():
                return {"success": False, "message": "LLM不可用"}
            
            prompt = f"""你是一个系统架构师和智能编程助手，需要分析一个执行失败的任务并提供解决方案。

【用户需求】
{user_request}

【执行失败信息】
MCP服务器: {mcp_server}
MCP工具: {mcp_tool}
参数: {params}
错误: {error_msg}

【任务】
请进行深度反思分析，并提供可执行的解决方案：

1. **失败原因分析**（简要说明为什么失败）
2. **系统缺失能力**（缺少什么工具或功能）
3. **可行解决方案**（提供1-3个具体方案，每个方案包含）：
   - 方案描述（1-2句话）
   - 实现方式（是否需要代码生成、配置修改等）
   - 优先级（高/中/低）

对于每个方案，如果可以立即通过代码解决，请生成对应的Python/Shell代码。

【输出格式】
失败原因：
[分析]

系统缺失：
[缺失内容]

推荐方案：
方案1（优先级：高）：
描述：[方案描述]
实现：[实现方式]
```python
# 如果可以通过代码解决，在这里生成代码
```

方案2（优先级：中）：
描述：[方案描述]
实现：[实现方式]
```python
# 如果需要代码
```

方案3（优先级：低）：
描述：[方案描述]
实现：[实现方式]
"""
            
            response = await router.simple_chat(
                user_message=prompt,
                system_prompt="你是一个专业的系统架构师和编程助手，擅长分析问题并提供可执行的解决方案。",
                temperature=0.3
            )
            
            if not response:
                return {"success": False, "message": "LLM未返回有效响应"}
            
            # 提取各个方案
            solutions = []
            solution_pattern = r'方案\d+（优先级：(\w+)）：\s*描述：(.*?)\s*实现：(.*?)(?:```(?:python|bash|sh)?\s*\n(.*?)\n```)?'
            matches = re.findall(solution_pattern, response, re.DOTALL)
            
            for priority, desc, impl, code in matches:
                solutions.append({
                    "priority": priority,
                    "description": desc.strip(),
                    "implementation": impl.strip(),
                    "code": code.strip() if code else None
                })
            
            # 如果没有匹配到结构化方案，使用整个响应作为分析
            if not solutions:
                solutions.append({
                    "priority": "中",
                    "description": "系统分析完成，请查看详细报告",
                    "implementation": "需要人工介入",
                    "code": None
                })
            
            # 构建方案预览
            preview = f"🔍 **系统反思分析报告**\n\n"
            
            # 提取失败原因和系统缺失
            failure_match = re.search(r'失败原因：\s*(.*?)(?=系统缺失：)', response, re.DOTALL)
            missing_match = re.search(r'系统缺失：\s*(.*?)(?=推荐方案：)', response, re.DOTALL)
            
            if failure_match:
                preview += f"**失败原因**: {failure_match.group(1).strip()[:300]}\n\n"
            if missing_match:
                preview += f"**系统缺失**: {missing_match.group(1).strip()[:300]}\n\n"
            
            preview += f"**推荐解决方案**:\n\n"
            for i, sol in enumerate(solutions, 1):
                preview += f"{i}. 【{sol['priority']}优先级】{sol['description'][:150]}\n"
                if sol.get('code'):
                    preview += f"   - 可通过代码自动生成解决\n"
                preview += f"\n"
            
            preview += f"请回复方案编号（如 **1** 或 **2**）以执行对应方案，或回复 **取消** 放弃。"
            
            # 保存待执行的方案
            self._pending_solutions = {
                "solutions": solutions,
                "full_analysis": response
            }
            
            logger.info(f"生成反思分析，提供{len(solutions)}个方案")
            
            return {
                "success": True,
                "reply": preview,
                "need_confirmation": True,
                "reflection_completed": True,
                "solution_count": len(solutions)
            }
            
        except Exception as e:
            logger.error(f"反思机制异常: {e}")
            return {"success": False, "message": str(e)}
    
    async def execute_selected_solution(self, solution_index: int) -> Dict[str, Any]:
        """执行用户选择的解决方案
        
        Args:
            solution_index: 方案索引（从1开始）
            
        Returns:
            执行结果
        """
        if not hasattr(self, '_pending_solutions') or not self._pending_solutions:
            return {"success": False, "error": "没有待执行的方案"}
        
        solutions = self._pending_solutions.get("solutions", [])
        if solution_index < 1 or solution_index > len(solutions):
            return {"success": False, "error": f"无效的方案编号，请选择1-{len(solutions)}"}
        
        selected_solution = solutions[solution_index - 1]
        
        # 如果方案包含代码，执行代码
        if selected_solution.get("code"):
            logger.info(f"执行方案{solution_index}: {selected_solution['description'][:50]}")
            
            code = selected_solution["code"]
            is_python = "python" in selected_solution.get("implementation", "").lower() or "代码" in selected_solution.get("implementation", "")
            
            try:
                from tools.tool_manager import ToolManager
                
                tm = ToolManager.get_instance()
                result = await tm.execute_in_sandbox(
                    code=code,
                    language="python" if is_python else "shell",
                    timeout=30,
                    max_memory_mb=256
                )
                
                if result.get("success"):
                    return {
                        "success": True,
                        "result": result.get("result", result.get("stdout")),
                        "message": f"✅ 方案{solution_index}执行成功\n\n{selected_solution['description']}",
                        "solution_executed": True
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get('error'),
                        "message": f"❌ 方案{solution_index}执行失败: {result.get('error')}"
                    }
            except Exception as e:
                logger.error(f"方案执行异常: {e}")
                return {"success": False, "error": str(e)}
        else:
            # 方案不包含代码，返回分析供用户参考
            return {
                "success": True,
                "message": f"📋 方案{solution_index}分析报告:\n\n{selected_solution['description']}\n\n实现方式: {selected_solution['implementation']}",
                "analysis_only": True
            }


def get_mcp_orchestrator_handler():
    """获取MCP协调器处理器单例"""
    return MCPOrchestratorHandler()

"""工作流执行控制器

包含 WorkflowEngine 类及其核心执行逻辑，以及模块级单例和辅助函数。
XML相关的解析和优化逻辑委托给 xml_parser 模块。
节点执行逻辑委托给 node_executor 模块。
"""

import json
import logging
import asyncio
import importlib
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

from skills.workflow_engine.node_executor import WorkflowNode
from skills.workflow_engine.xml_parser import (
    detect_cycle,
    optimize_node_order,
    suggest_skill_replacements,
    optimize_xml_workflow as parse_optimize_xml,
    parse_xml_to_workflow,
)

logger = logging.getLogger(__name__)

WORKFLOW_DIR = Path(__file__).resolve().parent.parent.parent / "workflows"
WORKFLOW_DIR.mkdir(exist_ok=True)


class WorkflowEngine:
    """工作流引擎

    整合了 hybrid_skill_agent 的技能链编排功能：
    - 动态技能加载和管理
    - 技能链编排（支持上下文变量传递）
    - XML工作流优化
    """

    def __init__(self):
        self.workflows: Dict[str, Dict[str, Any]] = {}
        # 技能注册表（整合自hybrid_skill_agent）
        self.skills_registry: Dict[str, Any] = {}
        self.skill_metadata: Dict[str, Dict[str, Any]] = {}
        self.loaded_skills: List[str] = []

        # 注册所有技能
        self._register_skills()
        self._load_workflows()
        # 加载社区技能（整合自hybrid_skill_agent）
        self._load_community_skills()

    def _register_skills(self):
        """注册技能（已迁移到 SkillRegistry + MCP，保留空方法做兼容）"""
        pass

    def _load_workflows(self):
        """加载已有工作流"""
        for wf_file in WORKFLOW_DIR.glob("*.json"):
            try:
                with open(wf_file, 'r', encoding='utf-8') as f:
                    workflow = json.load(f)
                    self.workflows[workflow['id']] = workflow
                logger.info(f"加载工作流: {workflow['name']}")
            except Exception as e:
                logger.error(f"加载工作流失败 {wf_file}: {e}")

    def _load_community_skills(self):
        """加载社区技能（整合自hybrid_skill_agent）"""
        skills_dir = Path(__file__).resolve().parent.parent

        # 扫描技能目录
        for skill_name in os.listdir(skills_dir):
            skill_path = skills_dir / skill_name

            # 跳过非目录和系统目录
            if not skill_path.is_dir() or skill_name.startswith('_') or skill_name == '.DS_Store':
                continue

            # 尝试加载技能
            try:
                module_path = f"skills.{skill_name}.handler"
                module = importlib.import_module(module_path)

                # 检查是否有导出的技能实例
                if hasattr(module, "handler"):
                    self.skills_registry[skill_name] = module.handler
                    self.loaded_skills.append(skill_name)

                    # 加载技能元数据
                    metadata = self._load_skill_metadata(skill_path)
                    self.skill_metadata[skill_name] = metadata

                    logger.info(f"加载社区技能成功: {skill_name}")
                elif hasattr(module, skill_name):
                    # 尝试以目录名为属性名加载
                    skill_instance = getattr(module, skill_name)
                    self.skills_registry[skill_name] = skill_instance
                    self.loaded_skills.append(skill_name)

                    # 加载技能元数据
                    metadata = self._load_skill_metadata(skill_path)
                    self.skill_metadata[skill_name] = metadata

                    logger.info(f"加载社区技能成功: {skill_name}")
                else:
                    logger.warning(f"技能 {skill_name} 缺少导出的实例")
            except Exception as e:
                logger.warning(f"加载技能 {skill_name} 失败: {e}")

    def _load_skill_metadata(self, skill_path: Path) -> Dict[str, Any]:
        """加载技能元数据（整合自hybrid_skill_agent）"""
        metadata = {
            "name": skill_path.name,
            "description": "",
            "version": "1.0.0",
            "author": "Community",
            "keywords": [],
            "actions": []
        }

        # 尝试从 SKILL.md 文件加载元数据
        skill_md_path = skill_path / "SKILL.md"
        if skill_md_path.exists():
            try:
                with open(skill_md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 简单解析 SKILL.md 文件
                    if "# " in content:
                        metadata["name"] = content.split("# ")[1].split("\n")[0].strip()
                    if "## 描述" in content:
                        desc_part = content.split("## 描述")[1].split("##")[0].strip()
                        metadata["description"] = desc_part
            except Exception as e:
                logger.warning(f"解析 SKILL.md 失败: {e}")

        return metadata

    def get_available_skills(self) -> List[Dict[str, Any]]:
        """获取可用技能列表（整合自hybrid_skill_agent）"""
        skills_list = []
        for skill_name in self.loaded_skills:
            skills_list.append({
                "name": skill_name,
                "metadata": self.skill_metadata.get(skill_name, {})
            })
        return skills_list

    async def execute_skill_chain(self, skill_chain: List[Dict[str, Any]]) -> Dict[str, Any]:
        """执行技能链（整合自hybrid_skill_agent）

        Args:
            skill_chain: 技能链列表，每个元素包含 skill_name 和 params

        Returns:
            执行结果
        """
        results = []
        context = {}

        for i, step in enumerate(skill_chain):
            skill_name = step.get("skill_name")
            params = step.get("params", {})

            # 注入上下文变量
            for key, value in context.items():
                for param_key, param_value in params.items():
                    if isinstance(param_value, str) and f"${key}" in param_value:
                        params[param_key] = param_value.replace(f"${key}", str(value))

            # 执行技能
            result = await self.execute_skill(skill_name, **params)
            results.append({
                "step": i + 1,
                "skill_name": skill_name,
                "result": result
            })

            # 更新上下文
            if result.get("success"):
                context[f"step_{i+1}_result"] = result.get("result", result.get("reply"))
            else:
                # 技能执行失败，停止执行
                return {
                    "success": False,
                    "error": f"步骤 {i+1} 执行失败: {result.get('error')}",
                    "results": results
                }

        return {
            "success": True,
            "results": results,
            "context": context
        }

    async def execute_skill(self, skill_name: str, **params) -> Dict[str, Any]:
        """执行单个技能（整合自hybrid_skill_agent）"""
        if skill_name not in self.skills_registry:
            return {
                "success": False,
                "error": f"技能 {skill_name} 不存在"
            }

        try:
            skill = self.skills_registry[skill_name]

            # 检查技能是否有 execute 方法
            if hasattr(skill, "execute"):
                # 检查是同步还是异步方法
                if asyncio.iscoroutinefunction(skill.execute):
                    result = await skill.execute(**params)
                else:
                    result = skill.execute(**params)
            elif callable(skill):
                # 如果技能本身是可调用对象
                result = skill(**params)
            else:
                return {
                    "success": False,
                    "error": f"技能 {skill_name} 不支持执行"
                }

            # 确保返回格式一致
            if isinstance(result, dict):
                return result
            else:
                return {
                    "success": True,
                    "result": result
                }
        except Exception as e:
            logger.error(f"执行技能 {skill_name} 失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def create_skill_chain(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """创建技能链（整合自hybrid_skill_agent）"""
        skill_chain = []

        for task in tasks:
            description = task.get("description")
            params = task.get("params", {})

            # 简单的技能匹配逻辑
            skill_name = self._match_skill(description)
            if skill_name:
                skill_chain.append({
                    "skill_name": skill_name,
                    "params": params
                })
            else:
                logger.warning(f"无法匹配技能: {description}")

        return skill_chain

    def _match_skill(self, description: str) -> Optional[str]:
        """根据描述匹配技能（整合自hybrid_skill_agent）"""
        # 简单的关键词匹配
        keyword_skill_map = {
            "天气": "weather",
            "爬取": "web_scraper",
            "分析": "data_analysis",
            "打开": "gui_automation",
            "翻译": "translator",
            "搜索": "search_engine",
            "系统": "system_toolbox",
            "自动化": "advanced_automation"
        }

        description_lower = description.lower()
        for keyword, skill_name in keyword_skill_map.items():
            if keyword in description_lower and skill_name in self.skills_registry:
                return skill_name

        return None

    # ------------------------------------------------------------------
    # XML 工作流方法（委托给 xml_parser 模块）
    # ------------------------------------------------------------------

    def optimize_xml_workflow(self, xml_content: str) -> Dict[str, Any]:
        """优化XML工作流（整合自hybrid_skill_agent）

        委托给 xml_parser.optimize_xml_workflow。
        """
        return parse_optimize_xml(xml_content, self.skills_registry)

    def create_from_xml(self, xml_content: str) -> Dict[str, Any]:
        """从XML创建工作流（AI分析后生成）

        委托 xml_parser.parse_xml_to_workflow 完成解析，
        然后在引擎层保存到磁盘。
        """
        try:
            workflow = parse_xml_to_workflow(xml_content)

            # 检查解析是否失败
            if isinstance(workflow, dict) and workflow.get("success") is False:
                return workflow

            # 保存工作流
            wf_file = WORKFLOW_DIR / f"{workflow['id']}.json"
            with open(wf_file, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, ensure_ascii=False, indent=2)

            self.workflows[workflow['id']] = workflow

            logger.info(f"从XML创建工作流: {workflow['name']}")
            return {
                "success": True,
                "workflow_id": workflow["id"],
                "name": workflow["name"],
                "node_count": len(workflow["nodes"]),
            }

        except Exception as e:
            logger.error(f"从XML创建工作流失败: {e}")
            return {"success": False, "error": str(e)}

    async def execute_xml_workflow(self, xml_content: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """直接执行XML工作流

        Args:
            xml_content: XML内容字符串
            input_data: 输入数据

        Returns:
            执行结果
        """
        try:
            from core.workflow.xml_workflow_mapper import xml_workflow_mapper

            # 解析XML工作流
            parse_result = xml_workflow_mapper.parse_xml_workflow(xml_content)
            if not parse_result["success"]:
                return {
                    "success": False,
                    "error": f"XML解析失败: {parse_result.get('error', '未知错误')}"
                }

            workflow = parse_result["workflow"]
            logger.info(f"执行XML工作流: {workflow['name']}")

            # 直接执行映射后的工作流
            if "steps" in workflow:
                return await self._execute_steps_format(workflow, input_data)
            elif "nodes" in workflow:
                return await self._execute_nodes_format(workflow, input_data)
            else:
                return {"success": False, "error": "工作流格式错误"}

        except Exception as e:
            logger.error(f"执行XML工作流失败: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # 工作流执行核心方法
    # ------------------------------------------------------------------

    async def execute(self, workflow_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行工作流"""
        if workflow_id not in self.workflows:
            return {"success": False, "error": f"工作流不存在: {workflow_id}"}

        workflow = self.workflows[workflow_id]

        # 支持两种格式：nodes/edges格式和steps格式
        if "steps" in workflow:
            return await self._execute_steps_format(workflow, input_data)
        elif "nodes" in workflow:
            return await self._execute_nodes_format(workflow, input_data)
        else:
            return {"success": False, "error": "工作流格式错误，缺少nodes或steps字段"}

    async def _execute_steps_format(self, workflow: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行steps格式的工作流"""
        context = {"input": input_data}

        # 检查是否启用并行执行
        parallel = workflow.get("parallel", False)

        if parallel:
            # 并行执行模式
            results = await self._execute_steps_parallel(workflow.get("steps", []), context)

            # 整合结果到上下文
            for i, (step, result) in enumerate(zip(workflow.get("steps", []), results)):
                if not result.get("success"):
                    return result
                step_type = step.get("type")
                self._update_context_with_result(context, f"{step_type}_{i}", result)
        else:
            # 串行执行模式
            for step in workflow.get("steps", []):
                step_type = step.get("type")
                site = step.get("site")
                action = step.get("action")
                config = step.get("config", {})

                # 智能准备参数，基于前一步的结果
                prepared_params = self._prepare_step_params(step_type, config, context)

                # 调用实际的技能系统
                result = await self._execute_skill_step(step_type, site, action, prepared_params, context)

                if not result.get("success"):
                    return result

                # 智能更新上下文，确保工具间数据传递流畅
                self._update_context_with_result(context, step_type, result)

        # 生成报告
        if workflow.get("generate_report", False):
            report = {
                "workflow_id": workflow.get("id"),
                "name": workflow.get("name"),
                "steps_executed": len(workflow.get("steps", [])),
                "results": context,
                "execution_mode": "parallel" if parallel else "sequential"
            }
            return {"success": True, "result": report, "context": context}

        return {"success": True, "result": context, "context": context}

    async def _execute_steps_parallel(self, steps: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """并行执行工作流步骤"""
        import asyncio

        # 准备所有步骤的执行任务
        tasks = []
        for step in steps:
            step_type = step.get("type")
            site = step.get("site")
            action = step.get("action")
            config = step.get("config", {})

            # 准备参数（并行模式下，所有步骤使用相同的初始上下文）
            prepared_params = self._prepare_step_params(step_type, config, context)

            # 创建任务
            task = self._execute_skill_step(step_type, site, action, prepared_params, context.copy())
            tasks.append(task)

        # 并行执行所有任务
        results = await asyncio.gather(*tasks)
        return results

    def _prepare_step_params(self, step_type: str, config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """智能准备步骤参数，基于前一步的结果"""
        prepared = config.copy()

        # 智能参数映射
        if step_type == "analyze":
            # 分析步骤自动使用前一步的结果作为数据
            if "data" not in prepared:
                # 查找最近的可用数据
                recent_data = self._find_recent_data(context)
                if recent_data:
                    prepared["data"] = recent_data

        # 变量替换
        for key, value in prepared.items():
            if isinstance(value, str):
                prepared[key] = self._replace_variables(value, context)
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, str):
                        value[sub_key] = self._replace_variables(sub_value, context)

        return prepared

    def _find_recent_data(self, context: Dict[str, Any]) -> Any:
        """查找最近的可用数据"""
        # 优先查找特定的数据源
        data_sources = ["data", "results", "content", "items"]
        for source in data_sources:
            if source in context:
                return context[source]

        # 查找最近的步骤结果
        step_results = [key for key in context if key.startswith("step_")]
        if step_results:
            # 按步骤执行顺序选择最后一个
            last_step = step_results[-1]
            last_result = context[last_step]
            if isinstance(last_result, dict):
                # 从结果中提取数据
                for source in data_sources:
                    if source in last_result:
                        return last_result[source]
                return last_result
            return last_result

        return {}

    def _replace_variables(self, text: str, context: Dict[str, Any]) -> str:
        """替换文本中的变量"""
        result = text
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                if isinstance(value, str):
                    result = result.replace(placeholder, value)
                elif isinstance(value, (int, float, bool)):
                    result = result.replace(placeholder, str(value))
                elif isinstance(value, (list, dict)):
                    # 对于复杂类型，使用简单表示
                    result = result.replace(placeholder, str(value)[:100] + "..." if len(str(value)) > 100 else str(value))
        return result

    def _update_context_with_result(self, context: Dict[str, Any], step_type: str, result: Dict[str, Any]) -> None:
        """智能更新上下文，确保工具间数据传递流畅"""
        if not result.get("data"):
            return

        data = result["data"]

        # 存储步骤结果
        context[f"step_{step_type}"] = data

        # 智能提取关键数据
        if isinstance(data, dict):
            # 提取常见的关键数据字段
            key_fields = ["data", "results", "content", "items", "output", "result"]
            for field in key_fields:
                if field in data and field not in context:
                    context[field] = data[field]

            # 特殊处理不同类型的结果
            if step_type == "scrape":
                # 网页爬取结果
                if "results" in data:
                    context["scraped_data"] = data["results"]
                    context["data"] = data["results"]
            elif step_type == "analyze":
                # 数据分析结果
                if "analysis" in data:
                    context["analysis_result"] = data["analysis"]
                    context["data"] = data["analysis"]
            elif step_type == "weather":
                # 天气查询结果
                if "weather" in data:
                    context["weather_data"] = data["weather"]
                    context["data"] = data["weather"]

        # 确保data字段始终存在
        if "data" not in context:
            context["data"] = data

    async def _execute_skill_step(self, step_type: str, site: str, action: str, config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行技能步骤"""
        try:
            from tools.tool_manager import ToolManager
            manager = ToolManager.get_instance()

            if step_type == "scrape":
                # 调用网页爬取技能
                params = {
                    "action": action,
                    "site": site,
                    "top_n": config.get("top_n", 10)
                }
                # 替换参数中的变量
                for key, value in params.items():
                    if isinstance(value, str):
                        for ctx_key, ctx_val in context.items():
                            placeholder = f"{{{{{ctx_key}}}}}"
                            if isinstance(ctx_val, str):
                                params[key] = value.replace(placeholder, ctx_val)

                result = manager.execute("web_scraper", **params)
                return {"success": True, "data": result}

            elif step_type == "analyze":
                # 调用数据分析技能
                params = {
                    "analysis_type": config.get("analysis_type", "basic"),
                    "data": context.get("data", {})
                }
                # 替换参数中的变量
                for key, value in params.items():
                    if isinstance(value, str):
                        for ctx_key, ctx_val in context.items():
                            placeholder = f"{{{{{ctx_key}}}}}"
                            if isinstance(ctx_val, str):
                                params[key] = value.replace(placeholder, ctx_val)

                result = manager.execute("data_analysis", **params)
                return {"success": True, "data": result}

            elif step_type == "weather":
                # 调用天气查询技能
                params = {
                    "city": config.get("city", "北京")
                }
                result = manager.execute("weather", **params)
                return {"success": True, "data": result}

            elif step_type == "tool":
                # 通用工具调用
                tool_name = config.get("tool", "")
                tool_params = config.get("params", {})
                # 替换参数中的变量
                for key, value in tool_params.items():
                    if isinstance(value, str):
                        for ctx_key, ctx_val in context.items():
                            placeholder = f"{{{{{ctx_key}}}}}"
                            if isinstance(ctx_val, str):
                                tool_params[key] = value.replace(placeholder, ctx_val)

                result = manager.execute(tool_name, **tool_params)
                return {"success": True, "data": result}

            else:
                return {"success": False, "error": f"未知步骤类型: {step_type}"}

        except Exception as e:
            logger.error(f"执行技能步骤失败: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_branch(self, nodes: Dict[str, WorkflowNode], adj: Dict[str, List[Dict[str, Any]]], start_node: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行并行分支"""
        current_node = start_node
        branch_context = context.copy()
        visited = set()

        while current_node and current_node not in visited:
            visited.add(current_node)

            node = nodes[current_node]
            result = await node.execute(branch_context)

            if not result.get("success"):
                return result

            # 更新分支上下文
            if result.get("data"):
                branch_context[node.node_id] = result["data"]
                if isinstance(result["data"], dict):
                    branch_context.update(result["data"])

            # 检查是否结束
            if result.get("final"):
                return result

            # 找下一个节点
            next_nodes = adj.get(current_node, [])
            if not next_nodes:
                break

            # 简化处理，取第一个后续节点
            current_node = next_nodes[0]["target"]

        return {"success": True, "data": branch_context}

    async def _execute_nodes_format(self, workflow: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行nodes/edges格式的工作流（基于DAG拓扑排序）"""
        nodes = {n["id"]: WorkflowNode(n["id"], n["type"], n["config"]) for n in workflow["nodes"]}

        # 构建邻接表（支持循环）
        adj = {}
        for edge in workflow["edges"]:
            if edge["source"] not in adj:
                adj[edge["source"]] = []
            adj[edge["source"]].append({
                "target": edge["target"],
                "condition": edge.get("condition", ""),
                "sourceDirection": edge.get("sourceDirection", "right"),
                "targetDirection": edge.get("targetDirection", "left"),
            })

        # 找到开始节点
        start_node = None
        for node in workflow["nodes"]:
            if node["type"] == "start":
                start_node = node["id"]
                break

        if not start_node:
            return {"success": False, "error": "未找到开始节点"}

        # 执行工作流（使用递归方式，支持循环）
        context = {"input": input_data}
        executed_nodes = set()
        loop_stack = set()  # 检测循环执行中的节点

        # 递归执行节点
        async def execute_node(node_id: str):
            # 检测递归调用（循环）
            if node_id in loop_stack:
                logger.debug(f"检测到循环节点 {node_id}，跳过重复执行")
                return {"success": True, "data": context.get(node_id, {})}

            if node_id in executed_nodes and nodes[node_id].node_type != "loop":
                return {"success": True, "data": context.get(node_id, {})}

            node = nodes[node_id]

            # 检查条件边：如果当前节点有前置条件，需验证是否满足
            if not self._check_entry_conditions(node_id, workflow["edges"], context):
                logger.info(f"跳过节点 {node_id}：条件不满足")
                return {"success": True, "data": {}}

            # 执行节点（带超时控制）
            timeout = node.config.get("timeout", 60)
            try:
                result = await asyncio.wait_for(node.execute(context), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"节点 {node_id} 执行超时（{timeout}秒）")
                return {"success": False, "error": f"节点 {node_id} 执行超时"}

            if not result.get("success"):
                return result

            # 更新上下文
            if result.get("data"):
                context[node.node_id] = result["data"]
                if isinstance(result["data"], dict):
                    context.update(result["data"])

            executed_nodes.add(node_id)

            # 检查是否结束
            if result.get("final"):
                return result

            # 处理循环节点（特殊处理）
            if node.node_type == "loop":
                loop_stack.add(node_id)
                loop_data = result.get("data", {})
                iterations = loop_data.get("iterations", 0)

                logger.info(f"循环节点 {node_id} 需要执行 {iterations} 次")

                # 获取循环体节点（连接到循环底部的节点）
                loop_body_nodes = []
                if node_id in adj:
                    for edge in adj[node_id]:
                        if edge.get("sourceDirection") == "bottom":
                            loop_body_nodes.append(edge["target"])

                # 执行循环体
                for i in range(iterations):
                    # 更新循环变量到上下文
                    if "index" in context:
                        context["loop_index"] = context["index"]
                    if "iteration" in context:
                        context["loop_iteration"] = context["iteration"]

                    # 执行循环体中的节点
                    for body_node_id in loop_body_nodes:
                        body_result = await execute_node(body_node_id)
                        if not body_result.get("success"):
                            loop_stack.remove(node_id)
                            return body_result

                loop_stack.remove(node_id)

            # 处理并行节点
            elif node.node_type == "parallel":
                parallel_result = await self._execute_parallel_branches(node_id, adj, nodes, context)
                if not parallel_result.get("success"):
                    return parallel_result
                if parallel_result.get("data"):
                    context.update(parallel_result["data"])

            # 执行后续节点
            if node_id in adj:
                for edge in adj[node_id]:
                    if edge.get("sourceDirection", "right") == "right":
                        next_result = await execute_node(edge["target"])
                        if not next_result.get("success"):
                            return next_result
                        if next_result.get("final"):
                            return next_result

            return {"success": True, "data": context.get(node_id, {})}

        # 从开始节点执行
        final_result = await execute_node(start_node)

        if final_result.get("final"):
            return {"success": True, "result": final_result.get("data", context), "context": context}

        return {"success": True, "result": context, "context": context}

    def _topological_sort(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Optional[List[str]]:
        """DAG拓扑排序（Kahn算法）

        Returns:
            执行顺序列表，如果存在环则返回None
        """
        # 计算每个节点的入度
        in_degree = {node["id"]: 0 for node in nodes}
        for edge in edges:
            if edge["target"] in in_degree:
                in_degree[edge["target"]] += 1

        # 将所有入度为0的节点加入队列
        from collections import deque
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])

        execution_order = []

        while queue:
            current = queue.popleft()
            execution_order.append(current)

            # 减少后续节点的入度
            for edge in edges:
                if edge["source"] == current:
                    target = edge["target"]
                    in_degree[target] -= 1
                    if in_degree[target] == 0:
                        queue.append(target)

        # 如果所有节点都被处理，说明无环；否则存在环
        if len(execution_order) == len(nodes):
            return execution_order
        else:
            return None

    def _check_entry_conditions(self, node_id: str, edges: List[Dict[str, Any]], context: Dict[str, Any]) -> bool:
        """检查节点的入口条件（条件边逻辑）

        Args:
            node_id: 目标节点ID
            edges: 所有边的列表
            context: 当前上下文

        Returns:
            是否满足进入该节点的条件
        """
        from jinja2 import Template

        # 找到指向该节点的所有边
        incoming_edges = [edge for edge in edges if edge["target"] == node_id]

        # 如果没有入边（开始节点），直接允许执行
        if not incoming_edges:
            return True

        # 检查所有入边的条件，至少有一条满足即可
        for edge in incoming_edges:
            condition = edge.get("condition", "")
            if not condition:
                # 无条件边，直接允许
                return True

            try:
                # 使用Jinja2求值条件表达式
                template = Template(condition)
                result = template.render(**context)

                # 将结果转换为布尔值
                if result.lower() in ["true", "1", "yes"]:
                    return True
            except Exception as e:
                logger.warning(f"条件表达式求值失败: {e}，默认允许执行")
                return True

        # 所有条件都不满足
        return False

    async def _execute_parallel_branches(self, parallel_node_id: str, adj: Dict[str, List[Dict[str, Any]]],
                                         nodes: Dict[str, WorkflowNode], context: Dict[str, Any]) -> Dict[str, Any]:
        """真并行执行分支（异步并发+结果隔离）

        Args:
            parallel_node_id: 并行节点ID
            adj: 邻接表
            nodes: 节点字典
            context: 共享上下文（只读）

        Returns:
            合并后的结果
        """
        next_edges = adj.get(parallel_node_id, [])
        if not next_edges:
            return {"success": True, "data": {}}

        # 为每个分支创建独立的上下文副本（避免竞态条件）
        branch_tasks = []
        for i, edge in enumerate(next_edges):
            branch_context = context.copy()
            task = self._execute_branch_with_isolation(edge["target"], adj, nodes, branch_context, f"branch_{i}")
            branch_tasks.append(task)

        # 异步并发执行所有分支
        results = await asyncio.gather(*branch_tasks, return_exceptions=True)

        # 合并结果
        merged_data = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"分支 {i} 执行异常: {result}")
                return {"success": False, "error": f"分支 {i} 执行失败: {str(result)}"}

            if result.get("success") and result.get("data"):
                branch_key = f"branch_{i}"
                merged_data[branch_key] = result["data"]
                if isinstance(result["data"], dict):
                    merged_data.update(result["data"])

        return {"success": True, "data": merged_data}

    async def _execute_branch_with_isolation(self, start_node: str, adj: Dict[str, List[Dict[str, Any]]],
                                             nodes: Dict[str, WorkflowNode], context: Dict[str, Any],
                                             branch_id: str) -> Dict[str, Any]:
        """执行独立分支（带上下文隔离）

        Args:
            start_node: 起始节点ID
            adj: 邻接表
            nodes: 节点字典
            context: 分支独立上下文
            branch_id: 分支标识（用于日志）
        """
        current_node = start_node
        visited = set()

        while current_node and current_node not in visited:
            visited.add(current_node)

            node = nodes[current_node]

            # 超时控制
            timeout = node.config.get("timeout", 60)
            try:
                result = await asyncio.wait_for(node.execute(context), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"分支 {branch_id} 节点 {current_node} 执行超时")
                return {"success": False, "error": f"节点 {current_node} 执行超时"}

            if not result.get("success"):
                return result

            # 更新分支独立上下文
            if result.get("data"):
                context[node.node_id] = result["data"]
                if isinstance(result["data"], dict):
                    context.update(result["data"])

            # 找下一个节点
            next_nodes = adj.get(current_node, [])
            if not next_nodes:
                break

            # 简化处理，取第一个后续节点
            current_node = next_nodes[0]["target"]

        return {"success": True, "data": context}

    def list_workflows(self) -> List[Dict[str, Any]]:
        """列出所有工作流"""
        return [
            {
                "id": wf["id"],
                "name": wf["name"],
                "description": wf.get("description", ""),
                "node_count": len(wf.get("nodes", [])),
                "step_count": len(wf.get("steps", [])),
                "created_at": wf.get("created_at", ""),
                "format": "steps" if "steps" in wf else "nodes"
            }
            for wf in self.workflows.values()
        ]

    def delete_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """删除工作流"""
        if workflow_id not in self.workflows:
            return {"success": False, "error": "工作流不存在"}

        wf_file = WORKFLOW_DIR / f"{workflow_id}.json"
        if wf_file.exists():
            wf_file.unlink()

        del self.workflows[workflow_id]
        return {"success": True}


# 全局单例
workflow_engine = WorkflowEngine()


def get_workflow_manager():
    """获取工作流管理器（兼容旧接口）"""
    return workflow_engine

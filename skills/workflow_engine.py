"""AI工作流引擎 - 类似Coze的可视化工作流搭建"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

WORKFLOW_DIR = Path(__file__).parent.parent / "workflows"
WORKFLOW_DIR.mkdir(exist_ok=True)


class WorkflowNode:
    """工作流节点"""
    
    def __init__(self, node_id: str, node_type: str, config: Dict[str, Any]):
        self.node_id = node_id
        self.node_type = node_type  # start, llm, tool, condition, end
        self.config = config
        self.inputs = {}
        self.outputs = {}
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行节点"""
        logger.info(f"执行节点 [{self.node_type}]: {self.node_id}")
        
        if self.node_type == "start":
            return self._execute_start(context)
        elif self.node_type == "llm":
            return await self._execute_llm(context)
        elif self.node_type == "tool":
            return self._execute_tool(context)
        elif self.node_type == "condition":
            return self._execute_condition(context)
        elif self.node_type == "loop":
            return await self._execute_loop(context)
        elif self.node_type == "parallel":
            return await self._execute_parallel(context)
        elif self.node_type == "end":
            return self._execute_end(context)
        
        return {"success": False, "error": f"未知节点类型: {self.node_type}"}
    
    def _execute_start(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """开始节点 - 初始化上下文"""
        return {"success": True, "data": context.get("input", {})}
    
    async def _execute_llm(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """LLM节点 - 调用大模型"""
        try:
            from core.llm_backend import get_llm_router
            
            prompt_template = self.config.get("prompt", "")
            model = self.config.get("model", "gpt-4")
            
            # 替换变量（支持嵌套对象访问）
            prompt = prompt_template
            
            # 第一层：替换简单变量 {{key}}
            for key, value in context.items():
                placeholder = f"{{{{{key}}}}}"
                if isinstance(value, str):
                    prompt = prompt.replace(placeholder, value)
                elif isinstance(value, dict):
                    # 第二层：替换嵌套变量 {{key.subkey}}
                    for subkey, subvalue in value.items():
                        nested_placeholder = f"{{{{{key}.{subkey}}}}}"
                        if isinstance(subvalue, str):
                            prompt = prompt.replace(nested_placeholder, subvalue)
                        else:
                            prompt = prompt.replace(nested_placeholder, str(subvalue))
            
            logger.info(f"LLM Prompt (after substitution): {prompt[:200]}...")
            
            client = get_llm_router()
            response = await client.chat([
                {"role": "user", "content": prompt}
            ], model=model)
            
            return {"success": True, "data": response, "model": model}
        except Exception as e:
            logger.error(f"LLM节点执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_tool(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """工具节点 - 调用Skill"""
        try:
            tool_name = self.config.get("tool", "")
            params = self.config.get("params", {})
            
            # 替换参数中的变量
            for key, value in params.items():
                if isinstance(value, str):
                    for ctx_key, ctx_val in context.items():
                        placeholder = f"{{{{{ctx_key}}}}}"
                        if isinstance(ctx_val, str):
                            params[key] = value.replace(placeholder, ctx_val)
            
            # 调用工具
            from tools.tool_manager import ToolManager
            manager = ToolManager.get_instance()
            
            result = manager.execute(tool_name, **params)
            
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"工具节点执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_condition(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """条件节点 - 分支判断"""
        condition = self.config.get("condition", "")
        
        # 简单条件评估
        try:
            # 替换变量
            for key, value in context.items():
                placeholder = f"{{{{{key}}}}}"
                if isinstance(value, (str, int, float, bool)):
                    condition = condition.replace(placeholder, str(value))
            
            result = eval(condition)
            return {"success": True, "data": {"branch": "true" if result else "false"}}
        except Exception as e:
            logger.error(f"条件节点执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_loop(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """循环节点 - 支持三种循环类型（参考 Coze 设计）
        
        循环类型：
        1. array: 数组循环（最常用）- 遍历数组，每轮产生 item 和 index
        2. times: 固定次数循环 - 执行指定次数
        3. while: 条件循环（While）- 满足条件时继续循环
        
        循环体内可使用的变量：
        - item: 当前遍历到的元素（仅数组循环）
        - index: 当前索引，从 0 开始（所有循环类型）
        - iteration: 当前迭代次数，从 1 开始（所有循环类型）
        """
        try:
            # 获取循环配置
            loop_type = self.config.get("loop_type", "array")  # array | times | while
            max_iterations = int(self.config.get("max_iterations", 100))  # 安全限制
            
            loop_results = []
            items = []
            
            # ========== 类型 1: 数组循环（最常用）==========
            if loop_type == "array":
                items_expr = self.config.get("items", "{{list}}")
                variable_name = self.config.get("variable", "item")
                
                # 替换变量表达式
                items_str = self._replace_template_vars(items_expr, context)
                
                # 解析列表
                items = self._parse_items(items_str, context)
                
                if not isinstance(items, list):
                    items = [items]
                
                # 限制迭代次数（防止死循环）
                items = items[:max_iterations]
                
                logger.info(f"数组循环: 共 {len(items)} 项，最大迭代 {max_iterations} 次")
                
                # 执行循环体
                for i, item in enumerate(items):
                    # 创建循环上下文（注入 item 和 index 变量）
                    loop_context = context.copy()
                    loop_context[variable_name] = item  # 当前元素
                    loop_context["index"] = i  # 当前索引（从0开始）
                    loop_context["iteration"] = i + 1  # 迭代次数（从1开始）
                    
                    # 执行循环体节点（由工作流引擎通过连线确定）
                    # 这里只准备上下文，实际执行在引擎层完成
                    loop_results.append({
                        "index": i,
                        "item": item,
                        "context": loop_context
                    })
            
            # ========== 类型 2: 固定次数循环 ==========
            elif loop_type == "times":
                count = int(self.config.get("items", 1))
                count = min(count, max_iterations)  # 限制最大次数
                
                logger.info(f"固定次数循环: 执行 {count} 次")
                
                for i in range(count):
                    # 创建循环上下文
                    loop_context = context.copy()
                    loop_context["index"] = i  # 当前索引（从0开始）
                    loop_context["iteration"] = i + 1  # 当前迭代次数（从1开始）
                    
                    loop_results.append({
                        "index": i,
                        "iteration": i + 1,
                        "context": loop_context
                    })
            
            # ========== 类型 3: 条件循环（While）==========
            elif loop_type == "while":
                condition_expr = self.config.get("items", "true")
                variable_name = self.config.get("variable", "item")
                
                logger.info(f"条件循环: 条件表达式 = {condition_expr}")
                
                i = 0
                while i < max_iterations:
                    # 评估条件
                    condition_result = self._evaluate_condition(condition_expr, context)
                    
                    if not condition_result:
                        logger.info(f"条件不满足，退出循环（已执行 {i} 次）")
                        break
                    
                    # 创建循环上下文
                    loop_context = context.copy()
                    loop_context["index"] = i  # 当前索引（从0开始）
                    loop_context["iteration"] = i + 1  # 迭代次数（从1开始）
                    
                    loop_results.append({
                        "index": i,
                        "iteration": i + 1,
                        "context": loop_context
                    })
                    
                    i += 1
                
                if i >= max_iterations:
                    logger.warning(f"达到最大迭代次数 {max_iterations}，强制退出循环")
            
            else:
                return {
                    "success": False,
                    "error": f"未知的循环类型: {loop_type}，支持: array, times, while"
                }
            
            # 返回循环结果
            return {
                "success": True,
                "data": {
                    "loop_type": loop_type,
                    "items": items if loop_type == "array" else [],
                    "variable": self.config.get("variable", "item"),
                    "iterations": len(loop_results),
                    "results": loop_results,
                    "output_array": [r.get("result") for r in loop_results if r.get("result")]
                }
            }
            
        except Exception as e:
            logger.error(f"循环节点执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _replace_template_vars(self, template: str, context: Dict[str, Any]) -> str:
        """替换模板中的变量（支持嵌套对象访问）
        
        支持格式：
        - {{variable}} - 简单变量
        - {{obj.key}} - 嵌套对象访问
        - {{arr[0]}} - 数组索引访问
        """
        result = template
        
        # 第一层：替换简单变量 {{key}}
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, str):
                result = result.replace(placeholder, value)
            elif isinstance(value, (int, float, bool)):
                result = result.replace(placeholder, str(value))
        
        # 第二层：替换嵌套变量 {{key.subkey}}
        for key, value in context.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    nested_placeholder = f"{{{{{key}.{subkey}}}}}"
                    if isinstance(subvalue, str):
                        result = result.replace(nested_placeholder, subvalue)
                    else:
                        result = result.replace(nested_placeholder, str(subvalue))
        
        return result
    
    def _parse_items(self, items_str: str, context: Dict[str, Any]) -> List[Any]:
        """解析列表数据
        
        支持格式：
        1. {{variable}} - 从上下文获取变量
        2. [1, 2, 3] - JSON 数组字符串
        3. 其他尝试 eval 解析
        """
        # 格式 1: 从上下文获取变量
        if items_str.startswith("{{") and items_str.endswith("}}"):
            var_name = items_str[2:-2].strip()
            items = context.get(var_name, [])
            return items if isinstance(items, list) else [items]
        
        # 格式 2: JSON 数组字符串
        if items_str.strip().startswith("[") and items_str.strip().endswith("]"):
            try:
                import json
                items = json.loads(items_str)
                return items if isinstance(items, list) else [items]
            except:
                pass
        
        # 格式 3: 尝试 eval 解析
        try:
            items = eval(items_str)
            return items if isinstance(items, list) else [items]
        except:
            return []
    
    def _evaluate_condition(self, condition_expr: str, context: Dict[str, Any]) -> bool:
        """评估条件表达式
        
        支持格式：
        - {{variable}} > 10
        - {{obj.count}} < 5
        - true / false
        """
        try:
            # 先替换变量
            evaluated = self._replace_template_vars(condition_expr, context)
            
            # 特殊处理布尔值
            if evaluated.lower() in ["true", "false"]:
                return evaluated.lower() == "true"
            
            # 评估表达式
            result = eval(evaluated)
            return bool(result)
        except Exception as e:
            logger.error(f"条件评估失败: {condition_expr}, 错误: {e}")
            return False  # 默认退出循环，避免死循环
    
    async def _execute_parallel(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """并行节点 - 并发执行多个分支"""
        try:
            # 获取配置
            branch_count = int(self.config.get("branch_count", 2))
            sync_mode = self.config.get("sync_mode", "wait_all")
            branches = self.config.get("branches", [])
            
            # 这里需要执行多个分支
            # 由于工作流执行是线性的，我们需要通过连线来确定分支
            # 暂时返回并行信息，实际执行由工作流引擎处理
            
            return {
                "success": True,
                "data": {
                    "branch_count": branch_count,
                    "sync_mode": sync_mode,
                    "branches": branches,
                    "parallel_execution": True
                }
            }
        except Exception as e:
            logger.error(f"并行节点执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_end(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """结束节点 - 输出结果"""
        output_template = self.config.get("output", "{{result}}")
        
        # 替换变量
        output = output_template
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, str):
                output = output.replace(placeholder, value)
        
        return {"success": True, "data": output, "final": True}


class WorkflowEngine:
    """工作流引擎"""
    
    def __init__(self):
        self.workflows: Dict[str, Dict[str, Any]] = {}
        # 注册所有技能
        self._register_skills()
        self._load_workflows()
    
    def _register_skills(self):
        """注册所有技能"""
        try:
            from tools.tool_manager import register_all_skills
            register_all_skills()
            logger.info("技能注册完成")
        except Exception as e:
            logger.error("技能注册失败: %s", e)
    
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
    
    def create_from_xml(self, xml_content: str) -> Dict[str, Any]:
        """从XML创建工作流（AI分析后生成）"""
        try:
            root = ET.fromstring(xml_content)
            
            workflow_id = f"wf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            workflow = {
                "id": workflow_id,
                "name": root.attrib.get("name", "未命名工作流"),
                "description": root.attrib.get("description", ""),
                "nodes": [],
                "edges": [],
                "created_at": datetime.now().isoformat(),
            }
            
            # 解析节点
            for node_elem in root.findall(".//node"):
                node = {
                    "id": node_elem.attrib["id"],
                    "type": node_elem.attrib["type"],
                    "config": {},
                }
                
                # 解析配置
                for config_elem in node_elem.findall("config/*"):
                    node["config"][config_elem.tag] = config_elem.text or ""
                
                workflow["nodes"].append(node)
            
            # 解析边
            for edge_elem in root.findall(".//edge"):
                edge = {
                    "source": edge_elem.attrib["source"],
                    "target": edge_elem.attrib["target"],
                    "condition": edge_elem.attrib.get("condition", ""),
                }
                workflow["edges"].append(edge)
            
            # 保存工作流
            wf_file = WORKFLOW_DIR / f"{workflow_id}.json"
            with open(wf_file, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, ensure_ascii=False, indent=2)
            
            self.workflows[workflow_id] = workflow
            
            logger.info(f"从XML创建工作流: {workflow['name']}")
            return {
                "success": True,
                "workflow_id": workflow_id,
                "name": workflow["name"],
                "node_count": len(workflow["nodes"]),
            }
            
        except Exception as e:
            logger.error(f"从XML创建工作流失败: {e}")
            return {"success": False, "error": str(e)}
    
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
        """执行nodes/edges格式的工作流"""
        nodes = {n["id"]: WorkflowNode(n["id"], n["type"], n["config"]) for n in workflow["nodes"]}
        
        # 构建邻接表
        adj = {}
        for edge in workflow["edges"]:
            if edge["source"] not in adj:
                adj[edge["source"]] = []
            adj[edge["source"]].append({
                "target": edge["target"],
                "condition": edge.get("condition", ""),
            })
        
        # 找到开始节点
        start_node = None
        for node in workflow["nodes"]:
            if node["type"] == "start":
                start_node = node["id"]
                break
        
        if not start_node:
            return {"success": False, "error": "未找到开始节点"}
        
        # 执行工作流
        context = {"input": input_data}
        current_node = start_node
        visited = set()
        
        while current_node and current_node not in visited:
            visited.add(current_node)
            
            node = nodes[current_node]
            result = await node.execute(context)
            
            if not result.get("success"):
                return result
            
            # 更新上下文
            if result.get("data"):
                context[node.node_id] = result["data"]
                if isinstance(result["data"], dict):
                    context.update(result["data"])
            
            # 检查是否结束
            if result.get("final"):
                return {"success": True, "result": result["data"], "context": context}
            
            # 找下一个节点
            next_nodes = adj.get(current_node, [])
            if not next_nodes:
                break
            
            # 检查当前节点是否为并行节点
            if nodes[current_node].node_type == "parallel":
                # 并行执行所有分支
                import asyncio
                branch_tasks = []
                
                for next_edge in next_nodes:
                    branch_context = context.copy()
                    branch_task = self._execute_branch(nodes, adj, next_edge["target"], branch_context)
                    branch_tasks.append(branch_task)
                
                # 执行所有分支
                branch_results = await asyncio.gather(*branch_tasks, return_exceptions=True)
                
                # 处理分支结果
                for i, result in enumerate(branch_results):
                    if isinstance(result, Exception):
                        logger.error(f"分支执行失败: {result}")
                    elif result.get("success"):
                        # 合并分支结果到主上下文
                        if result.get("data"):
                            branch_key = f"branch_{i}"
                            context[branch_key] = result["data"]
                            if isinstance(result["data"], dict):
                                context.update(result["data"])
                
                # 并行节点执行完成后，找到所有分支的共同后续节点
                # 这里简化处理，取第一个分支的后续节点
                if next_nodes:
                    first_branch_target = next_nodes[0]["target"]
                    # 找到第一个分支的下一个节点
                    branch_next_nodes = adj.get(first_branch_target, [])
                    if branch_next_nodes:
                        current_node = branch_next_nodes[0]["target"]
                    else:
                        break
                else:
                    break
            elif nodes[current_node].node_type == "loop":
                # ========== 循环节点处理（参考 Coze 设计）==========
                loop_config = nodes[current_node].config
                loop_type = loop_config.get("loop_type", "array")
                variable_name = loop_config.get("variable", "item")
                
                logger.info(f"开始执行循环节点: {current_node}, 类型: {loop_type}")
                
                # 1. 先执行循环节点本身，获取循环配置和迭代信息
                loop_result = await nodes[current_node].execute(context)
                
                if not loop_result.get("success"):
                    return loop_result
                
                loop_data = loop_result.get("data", {})
                iterations = loop_data.get("iterations", 0)
                loop_results = loop_data.get("results", [])
                
                logger.info(f"循环共 {iterations} 次迭代")
                
                # 2. 执行每次迭代的循环体
                all_iteration_results = []
                
                for i, iteration_info in enumerate(loop_results):
                    loop_context = iteration_info.get("context", context.copy())
                    
                    logger.info(f"执行第 {i+1}/{iterations} 次迭代")
                    
                    # 执行循环体节点（通过上下连接点确定）
                    for next_edge in next_nodes:
                        target_node = next_edge["target"]
                        
                        # 检查是否是回边（避免无限循环）
                        if target_node == current_node:
                            continue
                        
                        # 执行循环体分支
                        branch_result = await self._execute_branch(
                            nodes, adj, target_node, loop_context
                        )
                        
                        if branch_result.get("success"):
                            # 保存本次迭代的结果
                            iteration_result = branch_result.get("data", {})
                            all_iteration_results.append(iteration_result)
                            
                            # 将结果注入到循环上下文（供下次迭代使用）
                            if isinstance(iteration_result, dict):
                                loop_context.update(iteration_result)
                                
                                # 特殊处理：如果是数组循环，累加到输出数组
                                if loop_type == "array":
                                    context[f"{variable_name}_result_{i}"] = iteration_result
                    
                    # 更新主上下文中的循环进度
                    context[f"loop_iteration_{i}"] = all_iteration_results[-1] if all_iteration_results else {}
                    context["current_iteration"] = i + 1
                    context["total_iterations"] = iterations
                
                # 3. 循环结束后，整合所有结果
                context["loop_results"] = all_iteration_results
                context["loop_completed"] = True
                context["loop_iterations_count"] = iterations
                
                # 4. 继续执行循环后的下一个节点（右侧连接的节点）
                right_next_nodes = [
                    edge for edge in next_nodes 
                    if edge["target"] != current_node  # 排除回边
                ]
                
                if right_next_nodes:
                    current_node = right_next_nodes[0]["target"]
                    logger.info(f"循环结束，继续执行节点: {current_node}")
                else:
                    logger.info("循环结束，无后续节点")
                    break
            else:
                # 常规节点处理
                # 如果有多个分支，根据条件选择
                if len(next_nodes) > 1:
                    for next_edge in next_nodes:
                        if not next_edge["condition"]:
                            current_node = next_edge["target"]
                            break
                    else:
                        current_node = next_nodes[0]["target"]
                else:
                    current_node = next_nodes[0]["target"]
        
        return {"success": True, "result": context, "context": context}
    
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
    
    async def execute_xml_workflow(self, xml_content: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """直接执行XML工作流
        
        Args:
            xml_content: XML内容字符串
            input_data: 输入数据
            
        Returns:
            执行结果
        """
        try:
            from core.xml_workflow_mapper import xml_workflow_mapper
            
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


# 全局单例
workflow_engine = WorkflowEngine()
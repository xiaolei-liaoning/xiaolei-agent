"""AI工作流引擎 - 类似Coze的可视化工作流搭建

整合了 hybrid_skill_agent 的技能链编排功能：
- 动态技能加载和管理
- 技能链编排（支持上下文变量传递）
- XML工作流优化（循环检测、节点去重、拓扑排序）
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
        # 重试配置
        self.max_retries = config.get("max_retries", 0)  # 默认不重试
        self.retry_delay = config.get("retry_delay", 1)  # 重试间隔（秒）
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行节点（带重试机制）"""
        logger.info(f"执行节点 [{self.node_type}]: {self.node_id}")
        
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"节点 {self.node_id} 第{attempt}次重试...")
                    await asyncio.sleep(self.retry_delay)
                
                result = await self._execute_node(context)
                
                # 如果成功或已达到最大重试次数，返回结果
                if result.get("success", False) or attempt == self.max_retries:
                    return result
                    
            except Exception as e:
                last_error = e
                logger.warning(f"节点 {self.node_id} 第{attempt+1}次尝试失败: {e}")
                if attempt == self.max_retries:
                    break
        
        # 所有重试都失败
        return {"success": False, "error": str(last_error), "retries": self.max_retries}
    
    async def _execute_node(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行具体节点逻辑（子类可重写）"""
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
            from core.engine.llm_backend import get_llm_router
            from jinja2 import Template
            
            prompt_template = self.config.get("prompt", "")
            model = self.config.get("model", "gpt-4")
            
            # 使用Jinja2模板引擎替换变量（支持嵌套访问和复杂表达式）
            template = Template(prompt_template)
            prompt = template.render(**context)
            
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
            from jinja2 import Template
            tool_name = self.config.get("tool", "")
            params = self.config.get("params", {})
            
            if not tool_name:
                return {"success": False, "error": "工具名称未指定"}
            
            # 使用Jinja2替换参数中的变量
            prepared_params = {}
            for key, value in params.items():
                if isinstance(value, str):
                    template = Template(value)
                    prepared_params[key] = template.render(**context)
                else:
                    prepared_params[key] = value
            
            # 调用工具（支持多种方式）
            result = None
            
            # 方式1：尝试使用 ToolManager
            try:
                from tools.tool_manager import ToolManager
                manager = ToolManager.get_instance()
                result = manager.execute(tool_name, **prepared_params)
            except (ImportError, AttributeError):
                # 方式2：尝试使用技能调度器
                try:
                    from core.engine.skill_dispatcher import SkillDispatcher
                    dispatcher = SkillDispatcher.get_instance()
                    result = dispatcher.execute_skill(tool_name, prepared_params)
                except (ImportError, AttributeError):
                    # 方式3：尝试直接调用技能模块
                    try:
                        import importlib
                        module_path = f"skills.{tool_name}.handler"
                        module = importlib.import_module(module_path)
                        handler = getattr(module, f"{tool_name}_handler", None) or getattr(module, "handler", None)
                        if handler and callable(handler):
                            result = handler.execute(**prepared_params)
                        elif hasattr(module, "execute") and callable(module.execute):
                            result = module.execute(**prepared_params)
                    except Exception as e:
                        logger.warning(f"无法调用工具 {tool_name}: {e}")
            
            if result is None:
                return {"success": False, "error": f"无法找到或调用工具: {tool_name}"}
            
            # 标准化结果格式
            if isinstance(result, dict):
                return {"success": True, "data": result}
            else:
                return {"success": True, "data": {"result": result}}
                
        except Exception as e:
            logger.error(f"工具节点执行失败: {e}", exc_info=True)
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
            except (json.JSONDecodeError, ValueError):
                pass
        
        # 格式 3: 尝试 eval 解析
        try:
            items = eval(items_str)
            return items if isinstance(items, list) else [items]
        except Exception:
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
        skills_dir = Path(__file__).parent
        
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
    
    def optimize_xml_workflow(self, xml_content: str) -> Dict[str, Any]:
        """优化XML工作流（整合自hybrid_skill_agent）"""
        try:
            root = ET.fromstring(xml_content)
            
            # 分析工作流结构
            nodes = []
            edges = []
            
            for node in root.findall("./nodes/node"):
                node_id = node.attrib.get("id")
                node_type = node.attrib.get("type")
                node_name = node.attrib.get("name")
                
                nodes.append({
                    "id": node_id,
                    "type": node_type,
                    "name": node_name
                })
            
            for edge in root.findall("./edges/edge"):
                source = edge.attrib.get("source")
                target = edge.attrib.get("target")
                
                edges.append({
                    "source": source,
                    "target": target
                })
            
            # 优化策略
            optimizations = []
            
            # 1. 检测并移除重复节点
            seen_nodes = set()
            duplicate_nodes = []
            for node in nodes:
                node_key = (node["type"], node["name"])
                if node_key in seen_nodes:
                    duplicate_nodes.append(node["id"])
                else:
                    seen_nodes.add(node_key)
            
            if duplicate_nodes:
                optimizations.append({
                    "type": "remove_duplicates",
                    "description": f"移除重复节点: {duplicate_nodes}"
                })
            
            # 2. 检测并修复循环依赖
            has_cycle, cycle_path = self._detect_cycle(edges)
            if has_cycle:
                optimizations.append({
                    "type": "fix_cycle",
                    "description": f"检测到循环依赖: {cycle_path}"
                })
            
            # 3. 优化节点顺序
            optimized_order = self._optimize_node_order(nodes, edges)
            if optimized_order:
                optimizations.append({
                    "type": "optimize_order",
                    "description": "优化节点执行顺序",
                    "order": optimized_order
                })
            
            # 4. 建议技能替换
            skill_suggestions = self._suggest_skill_replacements(nodes)
            if skill_suggestions:
                optimizations.append({
                    "type": "skill_suggestions",
                    "description": "技能替换建议",
                    "suggestions": skill_suggestions
                })
            
            return {
                "success": True,
                "nodes_count": len(nodes),
                "edges_count": len(edges),
                "optimizations": optimizations
            }
        except Exception as e:
            logger.error(f"优化XML工作流失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _detect_cycle(self, edges: List[Dict[str, str]]) -> tuple:
        """检测循环依赖（整合自hybrid_skill_agent）"""
        # 简单的循环检测
        graph = {}
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            if source not in graph:
                graph[source] = []
            graph[source].append(target)
        
        visited = set()
        recursion_stack = set()
        
        def has_cycle(node):
            visited.add(node)
            recursion_stack.add(node)
            
            if node in graph:
                for neighbor in graph[node]:
                    if neighbor not in visited:
                        if has_cycle(neighbor):
                            return True
                    elif neighbor in recursion_stack:
                        return True
            
            recursion_stack.remove(node)
            return False
        
        for node in graph:
            if node not in visited:
                if has_cycle(node):
                    return True, list(recursion_stack)
        
        return False, []
    
    def _optimize_node_order(self, nodes: List[Dict[str, str]], edges: List[Dict[str, str]]) -> List[str]:
        """优化节点执行顺序（整合自hybrid_skill_agent）"""
        # 构建依赖图
        dependencies = {}
        for node in nodes:
            dependencies[node["id"]] = set()
        
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            if target in dependencies:
                dependencies[target].add(source)
        
        # 拓扑排序
        visited = set()
        order = []
        
        def topological_sort(node):
            if node in visited:
                return
            visited.add(node)
            
            for dep in dependencies.get(node, []):
                topological_sort(dep)
            
            order.append(node)
        
        for node in nodes:
            topological_sort(node["id"])
        
        return order
    
    def _suggest_skill_replacements(self, nodes: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """建议技能替换（整合自hybrid_skill_agent）"""
        suggestions = []
        
        # 技能替换建议映射
        replacement_map = {
            "旧爬虫": "web_scraper",
            "旧分析": "data_analysis",
            "旧自动化": "advanced_automation"
        }
        
        for node in nodes:
            node_name = node.get("name", "")
            for old_name, new_skill in replacement_map.items():
                if old_name in node_name and new_skill in self.skills_registry:
                    suggestions.append({
                        "node_id": node["id"],
                        "current_name": node_name,
                        "suggested_skill": new_skill
                    })
        
        return suggestions
    
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
                
                # 解析配置（支持嵌套参数）
                for config_elem in node_elem.findall("config/*"):
                    if config_elem.tag == "params":
                        params = {}
                        for param_elem in config_elem.findall("*"):
                            params[param_elem.tag] = param_elem.text or ""
                        node["config"]["params"] = params
                    else:
                        node["config"][config_elem.tag] = config_elem.text or ""
                
                workflow["nodes"].append(node)
            
            # 解析边（支持条件和方向）
            for edge_elem in root.findall(".//edge"):
                edge = {
                    "source": edge_elem.attrib["source"],
                    "target": edge_elem.attrib["target"],
                    "condition": edge_elem.attrib.get("condition", ""),
                    "sourceDirection": edge_elem.attrib.get("sourceDirection", "right"),
                    "targetDirection": edge_elem.attrib.get("targetDirection", "left"),
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


# 全局单例
workflow_engine = WorkflowEngine()


def get_workflow_manager():
    """获取工作流管理器（兼容旧接口）"""
    return workflow_engine
"""工作流节点执行逻辑

包含 WorkflowNode 类及其所有节点类型的执行方法：
- start, end: 开始/结束节点
- llm: 大模型调用节点
- tool: 工具调用节点
- condition: 条件分支节点
- loop: 循环节点（array/times/while）
- parallel: 并行执行节点
"""

import json
import logging
import asyncio
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


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

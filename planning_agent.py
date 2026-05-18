#!/usr/bin/env python3
"""智能任务规划代理

将 AdvancedAutomationHub 升华为一个智能的任务规划和执行系统，
能够处理复杂的任务需求，包括任务分解、智能规划、工具协调、状态管理和结果汇总。

支持多种调用方式：
1. 直接代码调用
2. API 调用 (POST /api/v1/tasks/execute)
3. 命令行调用 (python -m planning_agent "任务描述")
"""

import logging
import asyncio
from typing import Dict, Any, List
from mcp._impl.advanced_automation.handler import automation_hub
from core.tasks.task_processor import task_processor

logger = logging.getLogger(__name__)


class PlanningAgent:
    """智能任务规划代理"""
    
    def __init__(self):
        self.automation_hub = automation_hub
        logger.info("Planning Agent 初始化完成")
    
    async def execute(self, task_description: str) -> dict:
        """执行复杂任务
        
        Args:
            task_description: 自然语言任务描述
            
        Returns:
            执行结果字典，包含：
            - success: 是否全部成功
            - total_tasks: 总任务数
            - completed_tasks: 成功任务数
            - results: 各任务执行结果列表
            - message: 总结消息
            - estimated_time: 预估执行时间（秒）
            - actual_time: 实际执行时间（秒）
            - detailed_steps: 详细执行步骤
        """
        import time
        start_time = time.time()
        
        logger.info(f"Planning Agent 接收到任务: {task_description}")
        
        try:
            # 1. 任务处理/分解
            decomposition_result = await task_processor.process(task_description)
            logger.info(f"任务分解完成，共 {len(decomposition_result.subtasks)} 个子任务")
            
            # 2. 生成执行计划
            plan = self._generate_plan(decomposition_result)
            logger.info(f"执行计划生成完成，预估执行时间: {plan['estimated_time']} 秒")
            
            # 3. 执行计划
            results = await self._execute_plan(plan)
            
            # 4. 汇总结果
            summary = self._summarize_results(results, plan)
            
            # 计算实际执行时间
            actual_time = time.time() - start_time
            summary["estimated_time"] = plan["estimated_time"]
            summary["actual_time"] = round(actual_time, 2)
            summary["detailed_steps"] = plan["detailed_steps"]
            
            logger.info(f"任务执行完成: {summary['message']}，实际执行时间: {actual_time:.2f} 秒")
            return summary
            
        except Exception as e:
            logger.error(f"任务执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "total_tasks": 0,
                "completed_tasks": 0,
                "results": [],
                "message": f"任务执行失败: {str(e)}",
                "estimated_time": 0,
                "actual_time": round(time.time() - start_time, 2),
                "detailed_steps": []
            }
    
    def _generate_plan(self, decomposition_result):
        """生成执行计划
        
        分析子任务的依赖关系，确定执行顺序和并行策略，提供详细的操作指导和时间预估
        """
        plan = {
            "tasks": [],
            "dependencies": {},
            "estimated_time": 0,
            "detailed_steps": []
        }
        
        for subtask in decomposition_result.subtasks:
            # 预估每个任务的执行时间（秒）
            estimated_time = self._estimate_task_time(subtask.action, subtask.params)
            plan["estimated_time"] += estimated_time
            
            # 生成详细的操作指导
            operation_guide = self._generate_operation_guide(subtask.action, subtask.params)
            
            task_info = {
                "id": subtask.id,
                "action": subtask.action,
                "params": subtask.params or {},
                "priority": subtask.priority,
                "description": getattr(subtask, 'description', ''),
                "estimated_time": estimated_time,
                "operation_guide": operation_guide
            }
            plan["tasks"].append(task_info)
            plan["dependencies"][subtask.id] = subtask.dependencies or []
            
            # 添加到详细步骤
            plan["detailed_steps"].append({
                "step": len(plan["detailed_steps"]) + 1,
                "task_id": subtask.id,
                "action": subtask.action,
                "description": getattr(subtask, 'description', ''),
                "estimated_time": estimated_time,
                "operation_guide": operation_guide
            })
        
        return plan
    
    def _estimate_task_time(self, action, params):
        """预估任务执行时间（秒）
        
        根据任务类型和参数估算执行时间
        """
        time_estimates = {
            "send_email": 5,
            "open_app": 3,
            "workflow_crawl_analyze": 30,
            "gui_automation": 15,
            "file_operation": 10,
            "query_weather": 5,
            "search_knowledge": 10,
            "send_message": 5,
            "security_scan": 60
        }
        
        return time_estimates.get(action, 10)  # 默认10秒
    
    def _generate_operation_guide(self, action, params):
        """生成详细的操作指导
        
        根据任务类型和参数生成具体的操作步骤
        """
        guides = {
            "send_email": "1. 准备邮件内容\n2. 填写收件人地址\n3. 添加主题和正文\n4. 发送邮件",
            "open_app": "1. 打开指定应用\n2. 等待应用启动\n3. 确认应用已正常运行",
            "workflow_crawl_analyze": "1. 访问目标网站\n2. 爬取相关数据\n3. 分析数据内容\n4. 生成分析报告",
            "gui_automation": "1. 定位目标界面元素\n2. 执行点击/输入操作\n3. 验证操作结果",
            "file_operation": "1. 定位目标文件\n2. 执行文件操作\n3. 验证操作结果",
            "query_weather": "1. 确定查询地点\n2. 获取天气数据\n3. 整理天气信息\n4. 返回查询结果",
            "search_knowledge": "1. 分析查询意图\n2. 在知识库中搜索\n3. 整理搜索结果\n4. 返回相关信息",
            "send_message": "1. 准备消息内容\n2. 确定接收方\n3. 发送消息\n4. 确认发送成功",
            "security_scan": "1. 扫描系统漏洞\n2. 分析安全风险\n3. 生成安全报告\n4. 提供修复建议"
        }
        
        return guides.get(action, "执行指定任务")
    
    def _map_task_to_automation_action(self, task):
        """将分解后的子任务映射到 AdvancedAutomationHub 支持的 action
        
        支持智能关键词识别和参数提取
        """
        action = task["action"]
        params = task.get("params", {})
        description = task.get("description", "")
        
        # 合并描述和参数用于关键词匹配
        full_text = f"{action} {description} {params}"
        full_text_lower = full_text.lower()
        
        # ==================== 深度思考者相关 ====================
        # 深度思考任务（GLM可能生成的action）
        if action in ["deep_thinking", "thinking", "reasoning", "predict", "forecast", "analyze_deep"]:
            query = params.get("query", params.get("input", params.get("topic", "")))
            return "deep_thinking", {"input": query}
        
        # 包含思考相关关键词
        elif any(kw in full_text for kw in ["思考", "深度", "think", "推理", "reason", "预测", "推断"]):
            query = params.get("query", params.get("input", ""))
            return "deep_thinking", {"input": query}
        
        # ==================== 研究员相关 ====================
        # 研究任务（GLM可能生成的action）
        if action in ["research", "researcher", "content_curation", "literature_search", "scholarly_search"]:
            query = params.get("query", params.get("topic", params.get("keywords", "")))
            return "researcher", {"query": query}
        
        # 包含研究相关关键词
        elif any(kw in full_text for kw in ["研究", "调研", "research", "文献", "学术", "资料"]):
            query = self._extract_query(full_text)
            return "researcher", {"query": query}
        
        # ==================== 计算器相关 ====================
        # 计算器任务
        if action in ["calculator", "calculate", "math", "arithmetic", "compute"]:
            expr = params.get("expression", params.get("query", params.get("input", "2+2")))
            return "calculator", {"expression": expr}
        
        # 包含计算相关关键词
        elif any(kw in full_text for kw in ["计算", "calculator", "calc", "math", "数学", "运算"]):
            expr = params.get("expression", params.get("query", "2+2"))
            return "calculator", {"expression": expr}
        
        # ==================== 聊天助手相关 ====================
        # 聊天任务（GLM可能生成的action）
        if action in ["chat", "conversation", "message", "dialog"]:
            message = params.get("message", params.get("query", params.get("input", "你好")))
            return "chat", {"message": message}
        
        # 包含聊天相关关键词
        elif any(kw in full_text for kw in ["聊天", "对话", "chat", "talk", "你好", "怎么样", "你呢"]):
            message = params.get("message", params.get("query", "你好"))
            return "chat", {"message": message}
        
        # ==================== 系统助手相关 ====================
        # 系统工具任务（GLM可能生成的action）
        if action in ["system", "system_tool", "system_info", "sys_info", "system_monitor"]:
            command = "info"
            if any(kw in full_text for kw in ["时间", "time"]):
                command = "time"
            elif any(kw in full_text for kw in ["日期", "date"]):
                command = "date"
            elif any(kw in full_text for kw in ["cpu", "内存", "memory"]):
                command = "info"
            return "system_toolbox", {"command": command}
        
        # 包含系统相关关键词
        elif any(kw in full_text for kw in ["系统", "时间", "日期", "cpu", "内存", "disk", "system", "time", "date"]):
            if any(kw in full_text for kw in ["时间", "time"]):
                return "system_toolbox", {"command": "time"}
            elif any(kw in full_text for kw in ["日期", "date"]):
                return "system_toolbox", {"command": "date"}
            elif any(kw in full_text for kw in ["cpu", "内存", "memory"]):
                return "system_toolbox", {"command": "info"}
            else:
                return "system_toolbox", {"command": "info"}
        
        # ==================== OpenClaw相关 ====================
        # OpenClaw任务（GLM可能生成的action）
        if action in ["openclaw", "workflow", "database_query", "workflow_list", "workflow_execute"]:
            query_action = params.get("action", params.get("task", "list"))
            return "openclaw", {"action": query_action}
        
        # 包含工作流相关关键词
        elif any(kw in full_text for kw in ["工作流", "任务流", "workflow", "自动化流程"]):
            query_action = params.get("action", "list")
            return "openclaw", {"action": query_action}
        
        # ==================== 邮件相关任务 ====================
        elif any(kw in full_text for kw in ["邮件", "email", "send_mail"]):
            return "send_email", self._extract_email_params(params, full_text)
        
        # ==================== 浏览器相关任务 ====================
        elif any(kw in full_text for kw in ["浏览器", "browser", "打开网页"]):
            return "open_app", {"app": "浏览器"}
        
        # ==================== 爬取相关任务 ====================
        elif any(kw in full_text for kw in ["爬取", "抓取", "crawl", "scrape", "热搜"]):
            site = self._extract_site_name(full_text)
            return "workflow_crawl_analyze", {"site": site, "analyze": True}
        
        # ==================== GUI自动化任务 ====================
        elif any(kw in full_text for kw in ["点击", "输入", "gui", "界面操作"]):
            return "gui_automation", params
        
        # ==================== 文件操作任务 ====================
        elif any(kw in full_text for kw in ["文件", "下载", "上传", "file"]):
            return "file_operation", params
        
        # ==================== 天气查询任务 ====================
        elif any(kw in full_text for kw in ["天气", "weather", "气温", "预报"]):
            location = self._extract_location(full_text)
            return "query_weather", {"location": location}
        
        # ==================== 分析任务 ====================
        elif any(kw in full_text for kw in ["分析", "统计", "analyze", "analysis"]):
            query = self._extract_query(full_text)
            return "workflow_crawl_analyze", {"site": "analysis", "analyze": True, "query": query}
        
        # ==================== 整理/处理任务 ====================
        elif any(kw in full_text for kw in ["整理", "处理", "process", "organize"]):
            return "search_knowledge", {"query": "整理数据"}
        
        # ==================== 信息检索任务 ====================
        elif any(kw in full_text for kw in ["检索", "搜索", "查找", "search", "查询"]):
            query = self._extract_query(full_text)
            return "search_knowledge", {"query": query}
        
        # ==================== 消息发送任务 ====================
        elif any(kw in full_text for kw in ["发送", "消息", "通知", "send", "message", "notify"]):
            recipient = self._extract_recipient(full_text)
            message_content = self._extract_message_content(full_text)
            return "send_message", {"message": message_content, "recipient": recipient}
        
        # ==================== 安全检测任务 ====================
        elif any(kw in full_text for kw in ["安全", "检测", "漏洞", "security", "scan", "vulnerability"]):
            return "security_scan", params
        
        # ==================== 翻译任务 ====================
        elif any(kw in full_text for kw in ["翻译", "translate", "translator", "英文", "中文", "日语", "韩语"]):
            text = params.get("text", params.get("query", "Hello"))
            target_lang = "zh"
            if "英文" in full_text or "english" in full_text.lower():
                target_lang = "en"
            elif "日语" in full_text or "japanese" in full_text.lower():
                target_lang = "ja"
            return "translator", {"text": text, "target_lang": target_lang}
        
        # ==================== 文本分析任务 ====================
        elif any(kw in full_text for kw in ["文本", "分析", "总结", "摘要", "text", "summary"]):
            text = params.get("text", params.get("query", ""))
            return "text_analyzer", {"text": text}
        
        # ==================== 搜索引擎任务 ====================
        elif any(kw in full_text for kw in ["搜索", "search", "查找", "查询", "检索"]):
            query = self._extract_query(full_text)
            return "search_engine", {"query": query}
        
        # 默认返回原任务（如果action已经是automation_hub支持的）
        supported_actions = [
            "send_email", "open_app", "workflow_crawl_analyze", "gui_automation",
            "file_operation", "query_weather", "search_knowledge", "send_message",
            "security_scan", "calculator", "system_toolbox", "translator",
            "text_analyzer", "deep_thinking", "chat", "search_engine",
            "openclaw", "researcher", "rag_search", "web_scraper", "data_analysis"
        ]
        
        if action in supported_actions:
            return action, params
        
        # 对于未知的action，尝试根据描述推断
        # 如果描述中包含可识别的关键词，重新匹配
        if description:
            return self._map_task_to_automation_action({"action": "", "params": params, "description": description})
        
        # 最终兜底：返回search_knowledge
        return "search_knowledge", {"query": full_text}
    
    def _extract_location(self, text):
        """从文本中提取地点信息"""
        # 简单的地点提取逻辑
        locations = ["北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安"]
        for loc in locations:
            if loc in text:
                return loc
        return "北京"  # 默认北京
    
    def _extract_query(self, text):
        """从文本中提取查询内容"""
        # 简单的查询提取逻辑
        # 移除常见的查询动词
        query = text
        for verb in ["搜索", "查找", "查询", "检索", "search", "find", "query"]:
            query = query.replace(verb, "")
        return query.strip()
    
    def _extract_site_name(self, full_text):
        """从文本中提取网站名称"""
        sites = {
            "微博": ["微博", "weibo"],
            "知乎": ["知乎", "zhihu"],
            "GitHub": ["github", "GitHub"],
            "百度": ["百度", "baidu"],
            "抖音": ["抖音", "douyin"],
            "小红书": ["小红书", "xiaohongshu"],
            "淘宝": ["淘宝", "taobao"],
            "京东": ["京东", "jd"],
            "新闻": ["新闻", "news", "news.sina", "news.163"]
        }
        
        for site_name, keywords in sites.items():
            if any(kw in full_text for kw in keywords):
                return site_name
        
        return "通用网站"
    
    def _extract_email_params(self, params, full_text):
        """提取邮件参数"""
        email_params = {
            "to": params.get("to", params.get("recipient", "")),
            "subject": params.get("subject", params.get("title", "无主题")),
            "body": params.get("body", params.get("content", "无内容"))
        }
        
        # 尝试从文本中提取邮箱地址
        import re
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        emails = re.findall(email_pattern, full_text)
        if emails and not email_params["to"]:
            email_params["to"] = emails[0]
        
        return email_params
    
    def _extract_site_name(self, full_text):
        """从文本中提取网站名称"""
        sites = {
            "微博": ["微博", "weibo"],
            "知乎": ["知乎", "zhihu"],
            "GitHub": ["github", "GitHub"],
            "百度": ["百度", "baidu"],
            "抖音": ["抖音", "douyin"],
            "小红书": ["小红书", "xiaohongshu"]
        }
        
        for site_name, keywords in sites.items():
            if any(kw in full_text for kw in keywords):
                return site_name
        
        return "通用网站"
    
    def _extract_recipient(self, text):
        """从文本中提取接收者（如微信等）"""
        recipients = {
            "微信": ["微信", "wechat"],
            "QQ": ["QQ", "qq"],
            "钉钉": ["钉钉", "dingtalk"],
            "飞书": ["飞书", "feishu"],
        }
        
        for recipient_name, keywords in recipients.items():
            if any(kw in text for kw in keywords):
                return recipient_name
        
        return "微信"  # 默认微信
    
    def _extract_message_content(self, text):
        """从文本中提取要发送的消息内容"""
        # 移除常见的前缀词
        prefixes = ["发送", "消息", "通知", "给", "把", "将", "请", "要", "然后", "接着", "之后"]
        message_content = text
        
        for prefix in prefixes:
            message_content = message_content.replace(prefix, "")
        
        # 移除接收者相关词汇
        receiver_words = ["微信", "wechat", "QQ", "钉钉", "飞书"]
        for word in receiver_words:
            message_content = message_content.replace(word, "")
        
        return message_content.strip() or "已完成数据分析"
    
    async def _execute_plan(self, plan):
        """执行计划
        
        根据依赖关系和优先级执行任务：
        1. 检查依赖是否满足
        2. 无依赖任务可并行执行
        3. 有依赖任务按顺序执行
        """
        results = []
        executed_tasks = set()
        
        # 按优先级排序（高优先级先执行）
        # 先按依赖关系排序，确保依赖任务先执行
        # 使用拓扑排序：没有依赖的任务先执行
        sorted_tasks = []
        remaining_tasks = list(plan["tasks"])
        executed_ids = set()
        
        while remaining_tasks:
            ready_tasks = [
                t for t in remaining_tasks 
                if all(dep in executed_ids for dep in plan["dependencies"].get(t["id"], []))
            ]
            
            if not ready_tasks:
                # 如果没有就绪任务，按优先级选择一个执行（避免死锁）
                ready_tasks = [max(remaining_tasks, key=lambda x: x["priority"])]
            
            # 按优先级排序就绪任务
            ready_tasks.sort(key=lambda x: x["priority"], reverse=True)
            
            task = ready_tasks[0]
            remaining_tasks.remove(task)
            sorted_tasks.append(task)
            executed_ids.add(task["id"])
        
        # 重置执行任务集合
        executed_tasks = set()
        
        # 最多重试3次
        max_retries = 3
        
        for task in sorted_tasks:
            task_id = task["id"]
            
            # 检查依赖是否满足（应该已经满足，但再检查一次以防万一）
            dependencies = plan["dependencies"].get(task_id, [])
            if not all(dep in executed_tasks for dep in dependencies):
                logger.warning(f"任务 {task_id} 的依赖未满足，跳过")
                results.append({
                    "task_id": task_id,
                    "action": task["action"],
                    "status": "skipped",
                    "result": {"success": False, "error": "依赖未满足"}
                })
                continue
            
            # 执行任务（带重试机制）
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    # 映射任务到 AdvancedAutomationHub 支持的 action
                    action, params = self._map_task_to_automation_action(task)
                    logger.info(f"执行任务: {action} (原始动作: {task['action']})")
                    
                    # 确保 params 中不包含 action 键
                    if "action" in params:
                        del params["action"]
                    
                    # 执行任务
                    result = await self.automation_hub.execute(action, **params)
                    
                    results.append({
                        "task_id": task_id,
                        "action": action,
                        "original_action": task["action"],
                        "result": result
                    })
                    
                    if result.get("success", False):
                        success = True
                        executed_tasks.add(task_id)
                        logger.info(f"任务 {task_id} 执行成功")
                    else:
                        retry_count += 1
                        logger.warning(f"任务 {task_id} 执行失败，重试 {retry_count}/{max_retries}")
                        
                except Exception as e:
                    retry_count += 1
                    logger.error(f"任务 {task_id} 执行异常: {e}，重试 {retry_count}/{max_retries}")
            
            if not success:
                logger.error(f"任务 {task_id} 最终执行失败")
        
        return results
    
    def _summarize_results(self, results, plan):
        """汇总执行结果
        
        生成详细的执行报告
        """
        success_count = sum(1 for r in results if r.get("result", {}).get("success", False))
        total_count = len(results)
        
        # 生成详细结果摘要
        result_summary = []
        for r in results:
            result_summary.append({
                "task_id": r["task_id"],
                "action": r["action"],
                "success": r.get("result", {}).get("success", False),
                "message": r.get("result", {}).get("reply") or r.get("result", {}).get("message", "")
            })
        
        summary = {
            "success": success_count == total_count and total_count > 0,
            "total_tasks": total_count,
            "success_count": success_count,
            "results": result_summary,
            "message": f"任务执行完成，成功 {success_count}/{total_count} 个任务"
        }
        
        if success_count < total_count:
            failed_tasks = [r for r in results if not r.get("result", {}).get("success", False)]
            summary["failed_tasks"] = [
                {"task_id": r["task_id"], "action": r["action"]}
                for r in failed_tasks
            ]
        
        return summary


# 全局单例
planning_agent = PlanningAgent()


# ============================================================================
# 命令行入口
# ============================================================================

async def main():
    """命令行入口函数"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python -m planning_agent <任务描述>")
        print("示例:")
        print('  python -m planning_agent "打开浏览器"')
        print('  python -m planning_agent "发送邮件给test@example.com"')
        print('  python -m planning_agent "爬取微博热搜并分析趋势"')
        sys.exit(1)
    
    task_description = " ".join(sys.argv[1:])
    print(f"🤖 Planning Agent 正在执行: {task_description}\n")
    
    result = await planning_agent.execute(task_description)
    
    print("\n" + "="*60)
    print(f"✅ 执行结果: {result['message']}")
    print(f"📊 任务统计: 成功 {result.get('success_count', result.get('completed_tasks', 0))}/{result.get('total_tasks', 0)}")
    
    if result.get("results"):
        print("\n📋 详细结果:")
        for i, r in enumerate(result["results"], 1):
            status = "✅" if r["success"] else "❌"
            print(f"  {i}. {status} {r['action']}: {r['message']}")
    
    print("="*60)
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
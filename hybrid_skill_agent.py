#!/usr/bin/env python3
"""混合技能代理（HybridSkillAgent）

用于动态加载和组合社区创建的技能，提供技能的组装和编排能力。
"""

import os
import importlib
import logging
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class HybridSkillAgent:
    """混合技能代理"""
    
    def __init__(self):
        self.skills_registry: Dict[str, Any] = {}
        self.skill_metadata: Dict[str, Dict[str, Any]] = {}
        self.loaded_skills: List[str] = []
        self._load_community_skills()
        logger.info("HybridSkillAgent 初始化完成，加载了 %d 个社区技能", len(self.loaded_skills))
    
    def _load_community_skills(self):
        """加载社区技能"""
        skills_dir = os.path.join(os.path.dirname(__file__), "skills")
        
        # 扫描技能目录
        for skill_name in os.listdir(skills_dir):
            skill_path = os.path.join(skills_dir, skill_name)
            
            # 跳过非目录和系统目录
            if not os.path.isdir(skill_path) or skill_name.startswith('_') or skill_name == '.DS_Store':
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
    
    def _load_skill_metadata(self, skill_path: str) -> Dict[str, Any]:
        """加载技能元数据"""
        metadata = {
            "name": os.path.basename(skill_path),
            "description": "",
            "version": "1.0.0",
            "author": "Community",
            "keywords": [],
            "actions": []
        }
        
        # 尝试从 SKILL.md 文件加载元数据
        skill_md_path = os.path.join(skill_path, "SKILL.md")
        if os.path.exists(skill_md_path):
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
        """获取可用技能列表"""
        skills_list = []
        for skill_name in self.loaded_skills:
            skills_list.append({
                "name": skill_name,
                "metadata": self.skill_metadata.get(skill_name, {})
            })
        return skills_list
    
    async def execute_skill(self, skill_name: str, **params) -> Dict[str, Any]:
        """执行单个技能"""
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
    
    async def execute_skill_chain(self, skill_chain: List[Dict[str, Any]]) -> Dict[str, Any]:
        """执行技能链
        
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
    
    def create_skill_chain(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """创建技能链
        
        Args:
            tasks: 任务列表，每个任务包含 description 和 params
            
        Returns:
            技能链
        """
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
        """根据描述匹配技能"""
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
        """优化XML工作流
        
        Args:
            xml_content: XML工作流内容
            
        Returns:
            优化后的工作流信息
        """
        try:
            import xml.etree.ElementTree as ET
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
        """检测循环依赖"""
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
        """优化节点执行顺序"""
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
        """建议技能替换"""
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


# 全局单例
hybrid_skill_agent = HybridSkillAgent()


if __name__ == "__main__":
    import asyncio
    
    async def test_hybrid_agent():
        """测试混合技能代理"""
        print("=== 测试混合技能代理 ===")
        
        # 获取可用技能
        skills = hybrid_skill_agent.get_available_skills()
        print(f"\n可用技能: {[skill['name'] for skill in skills]}")
        
        # 测试执行单个技能
        print("\n测试执行天气技能:")
        weather_result = await hybrid_skill_agent.execute_skill("weather", city="北京")
        print(f"结果: {weather_result}")
        
        # 测试执行技能链
        print("\n测试执行技能链:")
        skill_chain = [
            {"skill_name": "weather", "params": {"city": "北京"}},
            {"skill_name": "translator", "params": {"text": "今天天气很好", "target_language": "en"}}
        ]
        chain_result = await hybrid_skill_agent.execute_skill_chain(skill_chain)
        print(f"结果: {chain_result}")
        
        print("\n=== 测试完成 ===")
    
    asyncio.run(test_hybrid_agent())
"""XML工作流解析逻辑

包含独立的XML解析和优化函数：
- detect_cycle: 检测循环依赖
- optimize_node_order: 优化节点执行顺序
- suggest_skill_replacements: 建议技能替换
- optimize_xml_workflow: 完整的XML工作流优化
- parse_xml_to_workflow: 从XML解析工作流结构
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


def detect_cycle(edges: List[Dict[str, str]]) -> Tuple[bool, List[str]]:
    """检测循环依赖

    Args:
        edges: 边列表，每条边包含 source 和 target

    Returns:
        (是否有环, 环路径)
    """
    graph = {}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source not in graph:
            graph[source] = []
        graph[source].append(target)

    visited = set()
    recursion_stack = set()

    def _has_cycle(node: str) -> bool:
        visited.add(node)
        recursion_stack.add(node)

        if node in graph:
            for neighbor in graph[node]:
                if neighbor not in visited:
                    if _has_cycle(neighbor):
                        return True
                elif neighbor in recursion_stack:
                    return True

        recursion_stack.remove(node)
        return False

    for node in graph:
        if node not in visited:
            if _has_cycle(node):
                return True, list(recursion_stack)

    return False, []


def optimize_node_order(nodes: List[Dict[str, str]], edges: List[Dict[str, str]]) -> List[str]:
    """优化节点执行顺序（拓扑排序）

    Args:
        nodes: 节点列表，每个节点包含 id
        edges: 边列表，每条边包含 source 和 target

    Returns:
        优化后的节点ID顺序列表
    """
    dependencies = {}
    for node in nodes:
        dependencies[node["id"]] = set()

    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if target in dependencies:
            dependencies[target].add(source)

    visited = set()
    order = []

    def topological_sort(node: str) -> None:
        if node in visited:
            return
        visited.add(node)

        for dep in dependencies.get(node, []):
            topological_sort(dep)

        order.append(node)

    for node in nodes:
        topological_sort(node["id"])

    return order


def suggest_skill_replacements(nodes: List[Dict[str, str]], skills_registry: Dict[str, Any]) -> List[Dict[str, str]]:
    """建议技能替换

    Args:
        nodes: 节点列表
        skills_registry: 技能注册表

    Returns:
        替换建议列表
    """
    suggestions = []

    replacement_map = {
        "旧爬虫": "web_scraper",
        "旧分析": "data_analysis",
        "旧自动化": "advanced_automation",
    }

    for node in nodes:
        node_name = node.get("name", "")
        for old_name, new_skill in replacement_map.items():
            if old_name in node_name and new_skill in skills_registry:
                suggestions.append({
                    "node_id": node["id"],
                    "current_name": node_name,
                    "suggested_skill": new_skill,
                })

    return suggestions


def optimize_xml_workflow(xml_content: str, skills_registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """优化XML工作流

    分析XML工作流结构，提供优化建议：
    - 移除重复节点
    - 检测循环依赖
    - 优化执行顺序
    - 技能替换建议

    Args:
        xml_content: XML内容字符串
        skills_registry: 技能注册表（可选，用于技能替换建议）

    Returns:
        优化结果，包含节点数、边数、优化建议列表
    """
    try:
        root = ET.fromstring(xml_content)

        nodes = []
        edges = []

        for node in root.findall("./nodes/node"):
            node_id = node.attrib.get("id")
            node_type = node.attrib.get("type")
            node_name = node.attrib.get("name")

            nodes.append({
                "id": node_id,
                "type": node_type,
                "name": node_name,
            })

        for edge in root.findall("./edges/edge"):
            source = edge.attrib.get("source")
            target = edge.attrib.get("target")

            edges.append({
                "source": source,
                "target": target,
            })

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
                "description": f"移除重复节点: {duplicate_nodes}",
            })

        # 2. 检测并修复循环依赖
        has_cycle, cycle_path = detect_cycle(edges)
        if has_cycle:
            optimizations.append({
                "type": "fix_cycle",
                "description": f"检测到循环依赖: {cycle_path}",
            })

        # 3. 优化节点顺序
        optimized_order = optimize_node_order(nodes, edges)
        if optimized_order:
            optimizations.append({
                "type": "optimize_order",
                "description": "优化节点执行顺序",
                "order": optimized_order,
            })

        # 4. 建议技能替换
        if skills_registry:
            skill_suggestions = suggest_skill_replacements(nodes, skills_registry)
            if skill_suggestions:
                optimizations.append({
                    "type": "skill_suggestions",
                    "description": "技能替换建议",
                    "suggestions": skill_suggestions,
                })

        return {
            "success": True,
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "optimizations": optimizations,
        }
    except Exception as e:
        logger.error(f"优化XML工作流失败: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def parse_xml_to_workflow(xml_content: str) -> Dict[str, Any]:
    """从XML解析工作流结构

    解析XML内容为内部工作流数据格式，包含节点和边。

    Args:
        xml_content: XML内容字符串

    Returns:
        成功返回工作流字典（包含id, name, nodes, edges等字段），
        失败返回 {"success": False, "error": "..."}
    """
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

        return workflow

    except Exception as e:
        logger.error(f"解析XML工作流失败: {e}")
        return {"success": False, "error": str(e)}

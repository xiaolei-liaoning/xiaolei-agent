"""XML工作流映射器 - 直接执行XML工作流

功能:
- XML结构到JSON结构的映射
- 每个节点类型对应特定的JSON结构
- 直接执行XML工作流，无需转换文件
- 支持所有节点类型：start, llm, tool, condition, end
"""

import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class XMLWorkflowMapper:
    """XML工作流映射器
    
    负责将XML工作流映射为可执行的JSON结构，并直接执行。
    """
    
    # 节点类型映射规则
    NODE_TYPE_MAPPING = {
        "start": {
            "json_template": {
                "id": "{node_id}",
                "type": "start",
                "config": {
                    "input": "用户输入"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["input"],
            "description": "开始节点 - 工作流的起点，接收用户输入"
        },
        "llm": {
            "json_template": {
                "id": "{node_id}",
                "type": "llm",
                "config": {
                    "prompt": "",
                    "model": "glm-4-flash"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["prompt", "model"],
            "description": "LLM节点 - 调用大语言模型生成文本"
        },
        "tool": {
            "json_template": {
                "id": "{node_id}",
                "type": "tool",
                "config": {
                    "tool": "",
                    "params": ""
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["tool", "params"],
            "description": "工具节点 - 调用外部工具执行特定任务"
        },
        "calculator": {
            "json_template": {
                "id": "{node_id}",
                "type": "calculator",
                "config": {
                    "operation": "add",
                    "operand1": "1",
                    "operand2": "2"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["operation", "operand1", "operand2"],
            "description": "计算节点 - 执行数学运算"
        },
        "http": {
            "json_template": {
                "id": "{node_id}",
                "type": "http",
                "config": {
                    "method": "GET",
                    "url": "https://api.example.com",
                    "headers": "",
                    "body": ""
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["method", "url", "headers", "body"],
            "description": "HTTP节点 - 发送HTTP请求"
        },
        "condition": {
            "json_template": {
                "id": "{node_id}",
                "type": "condition",
                "config": {
                    "condition": "{{result}} > 10",
                    "true_branch": "node_true",
                    "false_branch": "node_false"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["condition", "true_branch", "false_branch"],
            "description": "条件节点 - 根据条件执行不同分支"
        },
        "loop": {
            "json_template": {
                "id": "{node_id}",
                "type": "loop",
                "config": {
                    "max_iterations": 100,
                    "loop_type": "array"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["max_iterations", "loop_type"],
            "description": "循环节点 - 重复执行工作流框内的节点"
        },
        "parallel": {
            "json_template": {
                "id": "{node_id}",
                "type": "parallel",
                "config": {
                    "branches": "",
                    "branch_count": 2,
                    "sync_mode": "wait_all"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["branches", "branch_count", "sync_mode"],
            "description": "并行节点 - 同时执行多个分支"
        },
        "end": {
            "json_template": {
                "id": "{node_id}",
                "type": "end",
                "config": {
                    "output": "{{result}}"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["output"],
            "description": "结束节点 - 工作流的终点，输出结果"
        }
    }
    
    def __init__(self):
        self.xml_cache: Dict[str, ET.Element] = {}
        self.json_cache: Dict[str, Dict[str, Any]] = {}
    
    def parse_xml_workflow(self, xml_content: str) -> Dict[str, Any]:
        """解析XML工作流为JSON结构
        
        Args:
            xml_content: XML内容字符串
            
        Returns:
            JSON格式的工作流结构
        """
        try:
            root = ET.fromstring(xml_content)
            
            # 基础工作流结构
            workflow = {
                "id": f"xml_wf_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                "name": root.attrib.get("name", "未命名XML工作流"),
                "description": root.attrib.get("description", ""),
                "nodes": [],
                "edges": [],
                "created_at": datetime.now().isoformat(),
                "source_format": "xml"
            }
            
            # 映射节点
            nodes_map = {}
            for node_elem in root.findall(".//node"):
                node_json = self._map_node(node_elem)
                if node_json:
                    workflow["nodes"].append(node_json)
                    nodes_map[node_json["id"]] = node_json
            
            # 映射连线
            for edge_elem in root.findall(".//edge"):
                edge_json = self._map_edge(edge_elem)
                if edge_json:
                    workflow["edges"].append(edge_json)
            
            # 验证工作流
            validation_result = self._validate_workflow(workflow)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": f"工作流验证失败: {validation_result['message']}",
                    "details": validation_result
                }
            
            logger.info(f"XML工作流解析成功: {workflow['name']} ({len(workflow['nodes'])}个节点)")
            return {
                "success": True,
                "workflow": workflow,
                "nodes_count": len(workflow["nodes"]),
                "edges_count": len(workflow["edges"])
            }
            
        except ET.ParseError as e:
            logger.error(f"XML解析失败: {e}")
            return {
                "success": False,
                "error": f"XML解析错误: {e}"
            }
        except Exception as e:
            logger.error(f"XML工作流映射失败: {e}")
            return {
                "success": False,
                "error": f"映射失败: {e}"
            }
    
    def _map_node(self, node_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """映射单个XML节点为JSON节点
        
        Args:
            node_elem: XML节点元素
            
        Returns:
            JSON格式的节点，如果映射失败返回None
        """
        try:
            node_type = node_elem.attrib.get("type", "")
            node_id = node_elem.attrib.get("id", "")
            
            if not node_type or not node_id:
                logger.warning(f"节点缺少必要属性: {node_elem.attrib}")
                return None
            
            # 获取节点类型映射规则
            if node_type not in self.NODE_TYPE_MAPPING:
                logger.warning(f"不支持的节点类型: {node_type}")
                return None
            
            mapping_rule = self.NODE_TYPE_MAPPING[node_type]
            template = mapping_rule["json_template"].copy()
            
            # 填充节点ID
            template["id"] = node_id
            template["type"] = node_type
            
            # 解析配置
            config_elem = node_elem.find("config")
            if config_elem is not None:
                config_dict = {}
                for child in config_elem:
                    if child.text and child.text.strip():
                        config_dict[child.tag] = child.text.strip()
                    elif child.attrib:
                        # 处理嵌套配置
                        config_dict[child.tag] = dict(child.attrib)
                
                template["config"] = config_dict
            
            return template
            
        except Exception as e:
            logger.error(f"节点映射失败 [{node_elem.attrib.get('id', 'unknown')}]: {e}")
            return None
    
    def _map_edge(self, edge_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """映射XML连线为JSON连线
        
        Args:
            edge_elem: XML连线元素
            
        Returns:
            JSON格式的连线，如果映射失败返回None
        """
        try:
            source = edge_elem.attrib.get("source", "")
            target = edge_elem.attrib.get("target", "")
            condition = edge_elem.attrib.get("condition", "")
            
            if not source or not target:
                logger.warning(f"连线缺少必要属性: {edge_elem.attrib}")
                return None
            
            return {
                "source": source,
                "target": target,
                "condition": condition
            }
            
        except Exception as e:
            logger.error(f"连线映射失败: {e}")
            return None
    
    def _validate_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """验证工作流结构的完整性
        
        Args:
            workflow: JSON格式的工作流
            
        Returns:
            验证结果字典
        """
        errors = []
        
        # 检查是否有开始节点
        has_start = any(node["type"] == "start" for node in workflow["nodes"])
        if not has_start:
            errors.append("缺少开始节点")
        
        # 检查是否有结束节点
        has_end = any(node["type"] == "end" for node in workflow["nodes"])
        if not has_end:
            errors.append("缺少结束节点")
        
        # 检查节点ID唯一性
        node_ids = [node["id"] for node in workflow["nodes"]]
        if len(node_ids) != len(set(node_ids)):
            errors.append("存在重复的节点ID")
        
        # 检查连线有效性
        node_id_set = set(node_ids)
        for edge in workflow["edges"]:
            if edge["source"] not in node_id_set:
                errors.append(f"连线源节点不存在: {edge['source']}")
            if edge["target"] not in node_id_set:
                errors.append(f"连线目标节点不存在: {edge['target']}")
        
        return {
            "valid": len(errors) == 0,
            "message": "; ".join(errors) if errors else "验证通过",
            "errors": errors
        }
    
    def create_steps_format(self, xml_content: str) -> Dict[str, Any]:
        """将XML工作流转换为steps格式
        
        Args:
            xml_content: XML内容字符串
            
        Returns:
            steps格式的工作流
        """
        parse_result = self.parse_xml_workflow(xml_content)
        if not parse_result["success"]:
            return parse_result
        
        nodes_workflow = parse_result["workflow"]
        
        # 转换为steps格式
        steps = []
        node_map = {node["id"]: node for node in nodes_workflow["nodes"]}
        
        # 找到开始节点
        start_node = None
        for node in nodes_workflow["nodes"]:
            if node["type"] == "start":
                start_node = node
                break
        
        if not start_node:
            return {
                "success": False,
                "error": "未找到开始节点"
            }
        
        # 构建执行顺序
        current_node_id = start_node["id"]
        visited = set()
        
        while current_node_id and current_node_id not in visited:
            visited.add(current_node_id)
            current_node = node_map[current_node_id]
            
            # 跳过开始和结束节点
            if current_node["type"] not in ["start", "end"]:
                step = self._node_to_step(current_node)
                if step:
                    steps.append(step)
            
            # 找下一个节点
            next_edges = [edge for edge in nodes_workflow["edges"] 
                         if edge["source"] == current_node_id]
            if next_edges:
                current_node_id = next_edges[0]["target"]
            else:
                break
        
        steps_workflow = {
            "id": f"steps_wf_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "name": nodes_workflow["name"],
            "description": nodes_workflow["description"],
            "format": "steps",
            "steps": steps,
            "generate_report": True,
            "created_at": datetime.now().isoformat(),
            "source_format": "xml"
        }
        
        return {
            "success": True,
            "workflow": steps_workflow,
            "steps_count": len(steps)
        }
    
    def _node_to_step(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将节点转换为步骤格式
        
        Args:
            node: JSON格式的节点
            
        Returns:
            steps格式的步骤
        """
        node_type = node["type"]
        config = node.get("config", {})
        
        if node_type == "llm":
            return {
                "type": "llm",
                "config": {
                    "prompt": config.get("prompt", ""),
                    "model": config.get("model", "glm-4-flash")
                }
            }
        elif node_type == "tool":
            return {
                "type": "tool",
                "config": config
            }
        elif node_type == "condition":
            return {
                "type": "condition",
                "config": config
            }
        elif node_type == "calculator":
            return {
                "type": "calculator",
                "config": config
            }
        elif node_type == "http":
            return {
                "type": "http",
                "config": config
            }
        elif node_type == "loop":
            return {
                "type": "loop",
                "config": config
            }
        elif node_type == "parallel":
            return {
                "type": "parallel",
                "config": config
            }
        else:
            logger.warning(f"不支持的步骤类型: {node_type}")
            return None


# 全局单例
xml_workflow_mapper = XMLWorkflowMapper()
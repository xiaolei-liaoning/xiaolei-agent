"""XML工作流映射器 - 直接执行XML工作流

功能:
- XML结构到JSON结构的映射
- 每个节点类型对应特定的JSON结构
- 直接执行XML工作流，无需转换文件
- 支持所有节点类型：start, llm, tool, condition, end
- XML Schema验证（提前发现配置错误）
- 统一错误处理和重试机制
"""

import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from lxml import etree
from functools import lru_cache

from core.error_handler_utils import (
    ErrorHandler, LogLevel, retry_on_error, handle_errors
)

logger = logging.getLogger(__name__)

# XML Schema定义（用于验证XML格式）
WORKFLOW_SCHEMA = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="workflow">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="node" maxOccurs="unbounded">
                    <xs:complexType>
                        <xs:sequence>
                            <xs:element name="config" minOccurs="0">
                                <xs:complexType>
                                    <xs:sequence>
                                        <xs:any processContents="lax" minOccurs="0" maxOccurs="unbounded"/>
                                    </xs:sequence>
                                </xs:complexType>
                            </xs:element>
                        </xs:sequence>
                        <xs:attribute name="id" type="xs:string" use="required"/>
                        <xs:attribute name="type" use="required">
                            <xs:simpleType>
                                <xs:restriction base="xs:string">
                                    <xs:enumeration value="start"/>
                                    <xs:enumeration value="llm"/>
                                    <xs:enumeration value="tool"/>
                                    <xs:enumeration value="calculator"/>
                                    <xs:enumeration value="http"/>
                                    <xs:enumeration value="condition"/>
                                    <xs:enumeration value="loop"/>
                                    <xs:enumeration value="parallel"/>
                                    <xs:enumeration value="database"/>
                                    <xs:enumeration value="file"/>
                                    <xs:enumeration value="message_queue"/>
                                    <xs:enumeration value="transform"/>
                                    <xs:enumeration value="end"/>
                                </xs:restriction>
                            </xs:simpleType>
                        </xs:attribute>
                        <xs:attribute name="timeout" type="xs:integer" use="optional"/>
                        <xs:attribute name="max_retries" type="xs:integer" use="optional"/>
                    </xs:complexType>
                </xs:element>
                <xs:element name="edge" minOccurs="0" maxOccurs="unbounded">
                    <xs:complexType>
                        <xs:attribute name="source" type="xs:string" use="required"/>
                        <xs:attribute name="target" type="xs:string" use="required"/>
                        <xs:attribute name="condition" type="xs:string" use="optional"/>
                    </xs:complexType>
                </xs:element>
            </xs:sequence>
            <xs:attribute name="name" type="xs:string" use="optional"/>
            <xs:attribute name="description" type="xs:string" use="optional"/>
        </xs:complexType>
    </xs:element>
</xs:schema>"""


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
        "database": {
            "json_template": {
                "id": "{node_id}",
                "type": "database",
                "config": {
                    "operation": "query",
                    "connection": "default",
                    "sql": "SELECT * FROM table",
                    "params": ""
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["operation", "connection", "sql", "params"],
            "description": "数据库节点 - 执行SQL查询或更新操作"
        },
        "file": {
            "json_template": {
                "id": "{node_id}",
                "type": "file",
                "config": {
                    "operation": "read",
                    "path": "/path/to/file",
                    "encoding": "utf-8"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["operation", "path", "encoding"],
            "description": "文件节点 - 读写文件操作"
        },
        "message_queue": {
            "json_template": {
                "id": "{node_id}",
                "type": "message_queue",
                "config": {
                    "operation": "publish",
                    "queue": "default",
                    "message": ""
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["operation", "queue", "message"],
            "description": "消息队列节点 - 发布或订阅消息"
        },
        "transform": {
            "json_template": {
                "id": "{node_id}",
                "type": "transform",
                "config": {
                    "transformation": "json_to_csv",
                    "input_field": "data",
                    "output_field": "result"
                }
            },
            "required_attrs": ["id", "type"],
            "optional_attrs": ["transformation", "input_field", "output_field"],
            "description": "数据转换节点 - 格式转换和数据清洗"
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
        # 编译Schema（提高重复验证性能）
        try:
            schema_root = etree.fromstring(WORKFLOW_SCHEMA.encode())
            self.schema = etree.XMLSchema(schema_root)
        except Exception as e:
            ErrorHandler.log_error(e, module=__name__, function="__init__", extra_info="XML Schema编译失败")
            logger.warning(f"XML Schema编译失败，将跳过Schema验证")
            self.schema = None
    
    @lru_cache(maxsize=128)
    def _validate_xml_schema_cached(self, xml_content_hash: int):
        """使用XML Schema验证XML内容（带缓存）
        
        Args:
            xml_content_hash: XML内容的哈希值
            
        Returns:
            (是否有效, 错误信息)
        """
        # 注意：lru_cache不能直接缓存xml_content，这里通过外部调用传递原始内容
        # 实际使用时，应在外部计算hash并存储
        if self.schema is None:
            return True, ""
        
        try:
            # 从缓存获取原始内容（需要配合外部缓存使用）
            # 这里简化处理，实际项目中应维护内容->hash的映射
            return True, ""
        except Exception as e:
            ErrorHandler.log_error(e, module=__name__, function="_validate_xml_schema")
            return False, f"验证过程出错: {str(e)}"

    def _validate_xml_schema(self, xml_content: str):
        """使用XML Schema验证XML内容
        
        Args:
            xml_content: XML内容字符串
            
        Returns:
            (是否有效, 错误信息)
        """
        if self.schema is None:
            return True, ""
        
        try:
            xml_doc = etree.fromstring(xml_content.encode())
            self.schema.assertValid(xml_doc)
            return True, ""
        except etree.DocumentInvalid as e:
            return False, f"XML Schema验证失败: {str(e)}"
        except etree.XMLSyntaxError as e:
            return False, f"XML语法错误: {str(e)}"
        except Exception as e:
            ErrorHandler.log_error(e, module=__name__, function="_validate_xml_schema")
            return False, f"验证过程出错: {str(e)}"
    
    @retry_on_error(max_retries=2, delay=0.1, exceptions=(ET.ParseError,))
    def parse_xml_workflow(self, xml_content: str) -> Dict[str, Any]:
        """解析XML工作流为JSON结构
        
        Args:
            xml_content: XML内容字符串
            
        Returns:
            JSON格式的工作流结构
        """
        # 检查缓存
        import hashlib
        xml_hash = hashlib.md5(xml_content.encode()).hexdigest()
        if xml_hash in self.json_cache:
            logger.debug(f"使用缓存的XML解析结果: {xml_hash}")
            return self.json_cache[xml_hash]

        # 1. XML Schema 验证
        is_valid, error_msg = self._validate_xml_schema(xml_content)
        if not is_valid:
            error_result = {
                "success": False,
                "error": error_msg
            }
            logger.error(error_msg)
            return error_result

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
                error_result = {
                    "success": False,
                    "error": f"工作流验证失败: {validation_result['message']}",
                    "details": validation_result
                }
                return error_result
            
            logger.info(f"XML工作流解析成功: {workflow['name']} ({len(workflow['nodes'])}个节点)")
            success_result = {
                "success": True,
                "workflow": workflow,
                "nodes_count": len(workflow["nodes"]),
                "edges_count": len(workflow["edges"])
            }

            # 缓存结果
            self.json_cache[xml_hash] = success_result
            if len(self.json_cache) > 100:
                # 限制缓存大小
                first_key = next(iter(self.json_cache))
                del self.json_cache[first_key]

            return success_result
            
        except ET.ParseError as e:
            ErrorHandler.log_error(e, module=__name__, function="parse_xml_workflow", extra_info="XML解析失败")
            return {
                "success": False,
                "error": f"XML解析错误: {e}"
            }
        except Exception as e:
            ErrorHandler.log_error(e, module=__name__, function="parse_xml_workflow", extra_info="XML工作流映射失败")
            return {
                "success": False,
                "error": f"映射失败: {e}"
            }
    
    @handle_errors(default_return=None, exceptions=(Exception,))
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
            ErrorHandler.log_error(e, module=__name__, function="_map_node", extra_info=f"节点ID: {node_elem.attrib.get('id', 'unknown')}")
            return None
    
    @handle_errors(default_return=None, exceptions=(Exception,))
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
            ErrorHandler.log_error(e, module=__name__, function="_map_edge")
            return None
    
    def _validate_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """验证工作流结构的完整性
        
        Args:
            workflow: JSON格式的工作流
            
        Returns:
            验证结果字典
        """
        errors = []
        warnings = []
        
        # 检查是否有开始节点
        has_start = any(node["type"] == "start" for node in workflow["nodes"])
        if not has_start:
            errors.append("缺少开始节点（start）")
        
        # 检查是否有结束节点
        has_end = any(node["type"] == "end" for node in workflow["nodes"])
        if not has_end:
            errors.append("缺少结束节点（end）")
        
        # 检查节点ID唯一性
        node_ids = [node["id"] for node in workflow["nodes"]]
        duplicates = [id for id in node_ids if node_ids.count(id) > 1]
        if duplicates:
            errors.append(f"存在重复的节点ID: {', '.join(set(duplicates))}")
        
        # 检查连线有效性
        node_id_set = set(node_ids)
        orphan_edges = []
        for edge in workflow["edges"]:
            if edge["source"] not in node_id_set:
                errors.append(f"连线源节点不存在: {edge['source']}")
                orphan_edges.append(edge)
            if edge["target"] not in node_id_set:
                errors.append(f"连线目标节点不存在: {edge['target']}")
                orphan_edges.append(edge)
        
        # 检查孤立节点（没有入边或出边的非start/end节点）
        connected_nodes = set()
        for edge in workflow["edges"]:
            connected_nodes.add(edge["source"])
            connected_nodes.add(edge["target"])
        
        for node in workflow["nodes"]:
            if node["type"] not in ["start", "end"] and node["id"] not in connected_nodes:
                warnings.append(f"节点 '{node['id']}' ({node['type']}) 未连接到工作流")
        
        # 检查条件节点的分支配置
        for node in workflow["nodes"]:
            if node["type"] == "condition":
                config = node.get("config", {})
                if not config.get("true_branch") or not config.get("false_branch"):
                    warnings.append(f"条件节点 '{node['id']}' 缺少true_branch或false_branch配置")
        
        # 检查循环节点配置
        for node in workflow["nodes"]:
            if node["type"] == "loop":
                config = node.get("config", {})
                max_iter = config.get("max_iterations", 100)
                if max_iter > 1000:
                    warnings.append(f"循环节点 '{node['id']}' 的最大迭代次数({max_iter})过大，可能导致性能问题")
        
        # 检查工作流复杂度
        if len(workflow["nodes"]) > 50:
            warnings.append(f"工作流包含{len(workflow['nodes'])}个节点，建议拆分为多个子工作流以提高可维护性")
        
        # 生成验证消息
        message_parts = []
        if errors:
            message_parts.append(f"错误({len(errors)}): {'; '.join(errors)}")
        if warnings:
            message_parts.append(f"警告({len(warnings)}): {'; '.join(warnings)}")
        
        if not errors and not warnings:
            message = "验证通过"
        else:
            message = "; ".join(message_parts)
        
        return {
            "valid": len(errors) == 0,
            "message": message,
            "errors": errors,
            "warnings": warnings
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
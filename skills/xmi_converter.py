"""XMI到多任务工作流转换器 - 将XMI文件转换为可执行的多任务提示词"""

import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class XMIParser:
    """XMI文件解析器"""
    
    def __init__(self, xmi_content: str = None, xmi_file_path: str = None):
        """
        初始化XMI解析器
        
        Args:
            xmi_content: XMI文件的XML字符串内容
            xmi_file_path: XMI文件路径
        """
        if xmi_content:
            self.xmi_content = xmi_content
        elif xmi_file_path:
            with open(xmi_file_path, 'r', encoding='utf-8') as f:
                self.xmi_content = f.read()
        else:
            raise ValueError("必须提供xmi_content或xmi_file_path")
        
        self.tree = ET.fromstring(self.xmi_content)
        self.nodes = []
        self.edges = []
        self.metadata = {}
        
    def parse(self) -> Dict[str, Any]:
        """
        解析XMI文件，提取节点和边
        
        Returns:
            包含nodes、edges和metadata的字典
        """
        logger.info("开始解析XMI文件...")
        
        # 尝试不同的命名空间
        namespaces = self._detect_namespaces()
        
        # 提取节点
        self._extract_nodes(namespaces)
        
        # 提取边（连接关系）
        self._extract_edges(namespaces)
        
        # 提取元数据
        self._extract_metadata(namespaces)
        
        result = {
            "nodes": self.nodes,
            "edges": self.edges,
            "metadata": self.metadata,
            "parsed_at": datetime.now().isoformat()
        }
        
        logger.info(f"解析完成: {len(self.nodes)}个节点, {len(self.edges)}条边")
        return result
    
    def _detect_namespaces(self) -> Dict[str, str]:
        """检测XML命名空间"""
        # 常见的UML/XMI命名空间
        common_ns = {
            'uml': 'http://www.eclipse.org/uml2/5.0.0/UML',
            'xmi': 'http://www.omg.org/spec/XMI/20131001',
            'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
        }
        
        # 从根元素提取实际命名空间
        root_tag = self.tree.tag
        if '{' in root_tag:
            ns_uri = root_tag.split('{')[1].split('}')[0]
            return {'default': ns_uri}
        
        return {}
    
    def _extract_nodes(self, namespaces: Dict[str, str]):
        """提取所有节点"""
        # 查找packagedElement元素（它们通常包含实际的节点定义）
        packaged_elements = self.tree.findall('.//packagedElement')
        
        for elem in packaged_elements:
            # 获取type属性（可能在不同的命名空间中）
            type_attr = (elem.get('{http://www.omg.org/spec/XMI/20131001}type') or 
                        elem.get('xmi:type') or 
                        elem.get('type'))
            
            if not type_attr:
                continue
            
            # 提取实际的UML类型（如 uml:InitialNode -> InitialNode）
            if ':' in type_attr:
                actual_type = type_attr.split(':')[-1]
            else:
                actual_type = type_attr
            
            # 临时设置tag以便正确解析
            original_tag = elem.tag
            elem.tag = actual_type
            
            # 解析节点
            node = self._parse_node(elem)
            
            # 恢复原始tag
            elem.tag = original_tag
            
            if node:
                self.nodes.append(node)
    
    def _parse_node(self, element) -> Optional[Dict[str, Any]]:
        """解析单个节点"""
        try:
            node_id = element.get('id') or element.get('xmi:id')
            name = element.get('name') or element.get('text') or '未命名节点'
            
            # 确定节点类型
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            node_type = self._map_node_type(tag)
            
            # 提取配置
            config = {
                'name': name,
                'type': node_type,
                'original_tag': tag,
                'attributes': dict(element.attrib)
            }
            
            # 提取子元素信息
            for child in element:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child.text and child.text.strip():
                    config[child_tag] = child.text.strip()
            
            return {
                'id': node_id or f"node_{len(self.nodes) + 1}",
                'name': name,
                'type': node_type,
                'config': config
            }
        except Exception as e:
            logger.warning(f"解析节点失败: {e}")
            return None
    
    def _map_node_type(self, tag: str) -> str:
        """将XMI标签映射为标准节点类型"""
        type_mapping = {
            'InitialNode': 'start',
            'FinalNode': 'end',
            'ActivityFinalNode': 'end',
            'Action': 'task',
            'CallOperationAction': 'tool',
            'SendSignalAction': 'notification',
            'AcceptEventAction': 'trigger',
            'DecisionNode': 'condition',
            'MergeNode': 'merge',
            'ForkNode': 'parallel',
            'JoinNode': 'join',
            'Task': 'task',
            'ServiceTask': 'tool',
            'UserTask': 'manual',
            'ScriptTask': 'script',
            'Process': 'subprocess',
        }
        
        return type_mapping.get(tag, 'task')
    
    def _extract_edges(self, namespaces: Dict[str, str]):
        """提取所有边（连接关系）"""
        edge_elements = []
        
        # 方法1: 直接查找边类型
        edge_types_direct = [
            './/{*}Edge',
            './/{*}SequenceFlow',
            './/{*}ControlFlow',
            './/{*}ObjectFlow',
        ]
        
        for xpath in edge_types_direct:
            edge_elements.extend(self.tree.findall(xpath))
        
        # 方法2: 查找edge元素
        edge_elements.extend(self.tree.findall('.//{*}edge'))
        
        # 解析所有边
        seen_edges = set()
        for element in edge_elements:
            source = element.get('source') or element.get('xmi:source') or element.get('sourceRef')
            target = element.get('target') or element.get('xmi:target') or element.get('targetRef')
            
            if not source or not target:
                continue
            
            edge_key = f"{source}->{target}"
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            
            edge = self._parse_edge(element)
            if edge:
                self.edges.append(edge)
    
    def _parse_edge(self, element) -> Optional[Dict[str, Any]]:
        """解析单个边"""
        try:
            source = element.get('source') or element.get('xmi:source') or element.get('sourceRef')
            target = element.get('target') or element.get('xmi:target') or element.get('targetRef')
            
            if not source or not target:
                return None
            
            # 提取条件（如果有）
            condition = None
            guard = element.find('.//{*}guard') or element.find('.//{*}condition')
            if guard is not None and guard.text:
                condition = guard.text.strip()
            
            return {
                'source': source,
                'target': target,
                'condition': condition,
                'type': 'control_flow'
            }
        except Exception as e:
            logger.warning(f"解析边失败: {e}")
            return None
    
    def _extract_metadata(self, namespaces: Dict[str, str]):
        """提取元数据"""
        # 提取文档信息
        doc_element = self.tree.find('.//{*}Documentation') or self.tree.find('.//{*}description')
        if doc_element is not None:
            self.metadata['description'] = doc_element.text or ''
        
        # 提取作者信息
        author = self.tree.get('author') or self.tree.get('creator')
        if author:
            self.metadata['author'] = author
        
        # 提取版本信息
        version = self.tree.get('version') or self.tree.get('xmi:version')
        if version:
            self.metadata['version'] = version


class WorkflowConverter:
    """工作流转换器 - 将解析后的XMI转换为多任务提示词"""
    
    def __init__(self, parsed_data: Dict[str, Any]):
        self.parsed_data = parsed_data
        self.nodes = {node['id']: node for node in parsed_data['nodes']}
        self.edges = parsed_data['edges']
    
    def convert_to_multitask_prompt(self) -> str:
        """
        转换为多任务处理提示词
        
        Returns:
            格式化的多任务提示词字符串
        """
        # 构建执行顺序
        execution_order = self._build_execution_order()
        
        # 生成提示词
        prompt_parts = []
        prompt_parts.append("# 多任务工作流执行计划\n")
        prompt_parts.append(f"**工作流名称**: {self.parsed_data['metadata'].get('name', '未命名')}\n")
        prompt_parts.append(f"**节点数量**: {len(self.nodes)}\n")
        prompt_parts.append(f"**生成时间**: {self.parsed_data.get('parsed_at', '未知')}\n")
        
        if self.parsed_data['metadata'].get('description'):
            prompt_parts.append(f"\n**描述**: {self.parsed_data['metadata']['description']}\n")
        
        prompt_parts.append("\n## 执行步骤\n")
        
        for step_num, (node_id, node_info) in enumerate(execution_order, 1):
            node = self.nodes[node_id]
            prompt_parts.append(self._format_step(step_num, node, node_info))
        
        # 添加并行任务说明
        parallel_tasks = self._find_parallel_tasks()
        if parallel_tasks:
            prompt_parts.append("\n## 并行任务\n")
            for group_num, task_group in enumerate(parallel_tasks, 1):
                prompt_parts.append(f"### 并行组 {group_num}")
                for task_id in task_group:
                    task_name = self.nodes[task_id]['name']
                    prompt_parts.append(f"- {task_name}")
                prompt_parts.append("")
        
        # 添加条件分支说明
        conditions = self._find_conditions()
        if conditions:
            prompt_parts.append("\n## 条件分支\n")
            for cond in conditions:
                prompt_parts.append(f"- **如果** {cond['condition']}: 执行 {cond['target']}")
            prompt_parts.append("")
        
        return "\n".join(prompt_parts)
    
    def convert_to_json_workflow(self) -> Dict[str, Any]:
        """
        转换为JSON格式的工作流定义
        
        Returns:
            JSON格式的工作流
        """
        execution_order = self._build_execution_order()
        
        workflow_nodes = []
        for node_id, _ in execution_order:
            node = self.nodes[node_id]
            workflow_nodes.append({
                "id": node_id,
                "name": node['name'],
                "type": node['type'],
                "config": node['config']
            })
        
        return {
            "id": f"wf_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "name": self.parsed_data['metadata'].get('name', '从XMI导入的工作流'),
            "description": self.parsed_data['metadata'].get('description', ''),
            "nodes": workflow_nodes,
            "edges": self.edges,
            "created_at": datetime.now().isoformat(),
            "source": "xmi_import"
        }
    
    def _build_execution_order(self) -> List[tuple]:
        """构建执行顺序（拓扑排序）"""
        # 简单的拓扑排序
        visited = set()
        order = []
        
        # 找到起始节点
        start_nodes = []
        all_targets = {edge['target'] for edge in self.edges}
        
        for node_id in self.nodes:
            if node_id not in all_targets:
                start_nodes.append(node_id)
        
        # 如果没有明确的起始节点，使用第一个节点
        if not start_nodes:
            start_nodes = [list(self.nodes.keys())[0]]
        
        # DFS遍历
        def dfs(node_id):
            if node_id in visited:
                return
            visited.add(node_id)
            
            # 先处理依赖
            for edge in self.edges:
                if edge['target'] == node_id:
                    dfs(edge['source'])
            
            order.append((node_id, {'step': len(order) + 1}))
        
        for start_node in start_nodes:
            dfs(start_node)
        
        return order
    
    def _find_parallel_tasks(self) -> List[List[str]]:
        """查找并行任务组"""
        parallel_groups = []
        
        # 查找Fork节点
        for node_id, node in self.nodes.items():
            if node['type'] == 'parallel':
                # 找到Fork节点的所有输出
                outputs = [edge['target'] for edge in self.edges if edge['source'] == node_id]
                if outputs:
                    parallel_groups.append(outputs)
        
        return parallel_groups
    
    def _find_conditions(self) -> List[Dict[str, str]]:
        """查找条件分支"""
        conditions = []
        
        for edge in self.edges:
            if edge.get('condition'):
                target_name = self.nodes.get(edge['target'], {}).get('name', edge['target'])
                conditions.append({
                    'condition': edge['condition'],
                    'target': target_name
                })
        
        return conditions
    
    def _format_step(self, step_num: int, node: Dict[str, Any], node_info: Dict[str, Any]) -> str:
        """格式化单个步骤"""
        lines = []
        lines.append(f"### 步骤 {step_num}: {node['name']}")
        lines.append(f"- **类型**: {node['type']}")
        
        # 添加详细描述
        if node['config'].get('description'):
            lines.append(f"- **描述**: {node['config']['description']}")
        
        # 添加工具调用（如果是tool类型）
        if node['type'] == 'tool':
            tool_name = node['config'].get('operation') or node['config'].get('tool')
            if tool_name:
                lines.append(f"- **调用工具**: {tool_name}")
        
        # 添加LLM配置（如果是llm类型）
        if node['type'] == 'task':
            prompt = node['config'].get('prompt') or node['config'].get('body')
            if prompt:
                lines.append(f"- **提示词**: {prompt[:100]}..." if len(prompt) > 100 else f"- **提示词**: {prompt}")
        
        lines.append("")
        return "\n".join(lines)


def convert_xmi_to_workflow(xmi_content: str = None, xmi_file_path: str = None, 
                           output_format: str = "prompt") -> str:
    """
    便捷函数：将XMI文件转换为工作流
    
    Args:
        xmi_content: XMI内容字符串
        xmi_file_path: XMI文件路径
        output_format: 输出格式 ("prompt" 或 "json")
    
    Returns:
        转换后的工作流（提示词字符串或JSON字符串）
    """
    # 解析XMI
    parser = XMIParser(xmi_content=xmi_content, xmi_file_path=xmi_file_path)
    parsed_data = parser.parse()
    
    # 转换
    converter = WorkflowConverter(parsed_data)
    
    if output_format == "json":
        workflow = converter.convert_to_json_workflow()
        return json.dumps(workflow, ensure_ascii=False, indent=2)
    else:
        return converter.convert_to_multitask_prompt()


# 使用示例
if __name__ == "__main__":
    # 示例：从文件转换
    # result = convert_xmi_to_workflow(xmi_file_path="path/to/file.xmi")
    # print(result)
    
    # 示例：从字符串转换
    sample_xmi = """<?xml version="1.0" encoding="UTF-8"?>
    <xmi:XMI xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
        <uml:Activity name="示例工作流">
            <node xsi:type="uml:InitialNode" name="开始"/>
            <node xsi:type="uml:Action" name="获取数据"/>
            <node xsi:type="uml:Action" name="处理数据"/>
            <node xsi:type="uml:ActivityFinalNode" name="结束"/>
        </uml:Activity>
    </xmi:XMI>
    """
    
    result = convert_xmi_to_workflow(xmi_content=sample_xmi)
    print(result)

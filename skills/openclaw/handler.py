"""OpenClaw网格工作流引擎增强技能

扩展现有工作流引擎,提供高级网格工作流功能:
- 动态工作流生成
- 工作流模板库
- 工作流性能分析
- 工作流版本管理
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 工作流存储目录
WORKFLOW_STORAGE_DIR = Path(__file__).parent.parent / "workflows" / "openclaw"
WORKFLOW_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class OpenClawHandler:
    """OpenClaw网格工作流引擎处理器
    
    提供高级工作流功能,与现有workflow_engine.py互补
    """
    
    def __init__(self):
        self.workflow_templates = {}  # 工作流模板库
        self.workflow_versions = {}   # 工作流版本历史
        self._load_templates()
    
    def execute(self, action: str = 'list', **kwargs) -> Dict[str, Any]:
        """执行OpenClaw操作(同步接口)
        
        Args:
            action: 操作类型
                - list: 列出所有工作流
                - create: 创建工作流
                - execute: 执行工作流
                - validate: 验证工作流
                - template: 获取模板
                - version: 版本管理
                - analyze: 性能分析
            
            **kwargs: 操作参数
        
        Returns:
            {"success": bool, "result/error": ...}
        """
        return asyncio.run(self.aexecute(action, **kwargs))
    
    async def aexecute(self, action: str = 'list', **kwargs) -> Dict[str, Any]:
        """执行OpenClaw操作(异步接口)"""
        actions = {
            'list': self._list_workflows,
            'create': self._create_workflow,
            'execute': self._execute_workflow,
            'validate': self._validate_workflow,
            'template': self._get_template,
            'version': self._manage_version,
            'analyze': self._analyze_performance,
            'delete': self._delete_workflow,
            'export': self._export_workflow,
            'import': self._import_workflow
        }
        
        if action not in actions:
            return {
                'success': False, 
                'error': f'未知操作: {action}。支持的操作: {list(actions.keys())}'
            }
        
        try:
            return await actions[action](**kwargs)
        except Exception as e:
            logger.error(f"OpenClaw执行失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def _create_workflow(self, workflow_id: str, definition: Dict[str, Any], 
                              description: str = '', tags: List[str] = None, **kwargs) -> Dict[str, Any]:
        """创建工作流并保存
        
        Args:
            workflow_id: 工作流唯一ID
            definition: 工作流定义(nodes, edges等)
            description: 工作流描述
            tags: 标签列表
        """
        # 验证工作流定义
        validation = await self._validate_workflow(definition=definition)
        if not validation['success']:
            return validation
        
        # 构建完整的工作流元数据
        workflow_data = {
            'id': workflow_id,
            'definition': definition,
            'description': description,
            'tags': tags or [],
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'version': '1.0.0',
            'status': 'draft'
        }
        
        # 保存到文件
        workflow_file = WORKFLOW_STORAGE_DIR / f"{workflow_id}.json"
        with open(workflow_file, 'w', encoding='utf-8') as f:
            json.dump(workflow_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"OpenClaw工作流创建成功: {workflow_id}")
        return {
            'success': True,
            'message': f"工作流 '{workflow_id}' 创建成功",
            'workflow_id': workflow_id,
            'file_path': str(workflow_file)
        }
    
    async def _validate_workflow(self, definition: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """验证工作流定义的完整性
        
        检查项:
        - nodes和edges字段存在性
        - 节点ID唯一性
        - 边的引用有效性
        - 循环依赖检测
        """
        errors = []
        warnings = []
        
        # 检查必需字段
        if 'nodes' not in definition:
            errors.append('缺少 nodes 字段')
        elif not isinstance(definition['nodes'], list):
            errors.append('nodes 必须是列表')
        
        if 'edges' not in definition:
            errors.append('缺少 edges 字段')
        elif not isinstance(definition['edges'], list):
            errors.append('edges 必须是列表')
        
        # 检查节点定义
        node_ids = set()
        if 'nodes' in definition and isinstance(definition['nodes'], list):
            for node in definition['nodes']:
                if 'id' not in node:
                    errors.append('节点缺少 id 字段')
                else:
                    if node['id'] in node_ids:
                        errors.append(f"节点ID重复: {node['id']}")
                    node_ids.add(node['id'])
                
                # 检查节点类型
                if 'type' not in node:
                    warnings.append(f"节点 {node.get('id', 'unknown')} 缺少 type 字段")
        
        # 检查边的引用
        if 'edges' in definition and isinstance(definition['edges'], list):
            for edge in definition['edges']:
                if 'from_node' in edge and edge['from_node'] not in node_ids:
                    errors.append(f"边引用不存在的源节点: {edge['from_node']}")
                if 'to_node' in edge and edge['to_node'] not in node_ids:
                    errors.append(f"边引用不存在的目标节点: {edge['to_node']}")
        
        # 循环依赖检测
        if node_ids and 'edges' in definition:
            has_cycle = self._detect_cycle(definition['edges'])
            if has_cycle:
                warnings.append("检测到循环依赖,请确认是否为预期的循环节点")
        
        if errors:
            return {'success': False, 'errors': errors, 'warnings': warnings}
        
        return {
            'success': True, 
            'message': '工作流定义验证通过',
            'warnings': warnings,
            'stats': {
                'node_count': len(node_ids),
                'edge_count': len(definition.get('edges', []))
            }
        }
    
    async def _execute_workflow(self, workflow_id: str = None, definition: Dict[str, Any] = None,
                               input_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        """执行工作流
        
        Args:
            workflow_id: 已保存的工作流ID
            definition: 直接传入的工作流定义
            input_data: 输入数据
        """
        # 获取工作流定义
        if workflow_id:
            workflow_data = await self._load_workflow(workflow_id)
            if not workflow_data:
                return {'success': False, 'error': f'工作流不存在: {workflow_id}'}
            wf_def = workflow_data['definition']
        elif definition:
            wf_def = definition
            workflow_id = 'temp_workflow'
        else:
            return {'success': False, 'error': '必须提供 workflow_id 或 definition'}
        
        logger.info(f"开始执行OpenClaw工作流: {workflow_id}")
        
        try:
            # 这里可以集成现有的workflow_engine.py
            # 暂时返回模拟结果
            result = {
                'workflow_id': workflow_id,
                'execution_time': datetime.now().isoformat(),
                'status': 'completed',
                'output': input_data or {}
            }
            
            return {
                'success': True,
                'result': result,
                'message': '工作流执行完成'
            }
        
        except Exception as e:
            logger.error(f"工作流执行失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def _list_workflows(self, tag: str = None, status: str = None, **kwargs) -> Dict[str, Any]:
        """列出所有工作流
        
        Args:
            tag: 按标签筛选
            status: 按状态筛选(draft/published/archived)
        """
        workflows = []
        
        for wf_file in WORKFLOW_STORAGE_DIR.glob("*.json"):
            try:
                with open(wf_file, 'r', encoding='utf-8') as f:
                    wf_data = json.load(f)
                
                # 应用筛选条件
                if tag and tag not in wf_data.get('tags', []):
                    continue
                if status and wf_data.get('status') != status:
                    continue
                
                workflows.append({
                    'id': wf_data['id'],
                    'description': wf_data.get('description', ''),
                    'tags': wf_data.get('tags', []),
                    'status': wf_data.get('status', 'draft'),
                    'version': wf_data.get('version', '1.0.0'),
                    'created_at': wf_data.get('created_at', ''),
                    'node_count': len(wf_data.get('definition', {}).get('nodes', []))
                })
            except Exception as e:
                logger.warning(f"加载工作流文件失败 {wf_file}: {e}")
        
        return {
            'success': True,
            'workflows': workflows,
            'total': len(workflows)
        }
    
    async def _get_template(self, template_name: str, **kwargs) -> Dict[str, Any]:
        """获取工作流模板
        
        内置模板:
        - data_pipeline: 数据处理流水线
        - web_scraper_flow: 网页爬取流程
        - analysis_report: 分析报告生成
        - multi_agent_coordination: 多Agent协调
        """
        templates = {
            'data_pipeline': {
                'name': '数据处理流水线',
                'description': '数据采集 → 清洗 → 转换 → 存储',
                'definition': {
                    'nodes': [
                        {'id': 'collect', 'type': 'tool', 'action': 'web_scraper'},
                        {'id': 'clean', 'type': 'task', 'action': 'filter'},
                        {'id': 'transform', 'type': 'task', 'action': 'transform'},
                        {'id': 'store', 'type': 'tool', 'action': 'database'}
                    ],
                    'edges': [
                        {'from_node': 'collect', 'to_node': 'clean'},
                        {'from_node': 'clean', 'to_node': 'transform'},
                        {'from_node': 'transform', 'to_node': 'store'}
                    ]
                }
            },
            'web_scraper_flow': {
                'name': '网页爬取流程',
                'description': 'URL输入 → 爬取 → 解析 → 输出',
                'definition': {
                    'nodes': [
                        {'id': 'input', 'type': 'start'},
                        {'id': 'scrape', 'type': 'tool', 'action': 'web_scraper'},
                        {'id': 'parse', 'type': 'llm', 'model': 'gpt-4'},
                        {'id': 'output', 'type': 'end'}
                    ],
                    'edges': [
                        {'from_node': 'input', 'to_node': 'scrape'},
                        {'from_node': 'scrape', 'to_node': 'parse'},
                        {'from_node': 'parse', 'to_node': 'output'}
                    ]
                }
            },
            'analysis_report': {
                'name': '分析报告生成',
                'description': '数据输入 → 分析 → 可视化 → 报告',
                'definition': {
                    'nodes': [
                        {'id': 'data', 'type': 'start'},
                        {'id': 'analyze', 'type': 'tool', 'action': 'data_analysis'},
                        {'id': 'visualize', 'type': 'task', 'action': 'chart'},
                        {'id': 'report', 'type': 'llm', 'model': 'gpt-4'},
                        {'id': 'end', 'type': 'end'}
                    ],
                    'edges': [
                        {'from_node': 'data', 'to_node': 'analyze'},
                        {'from_node': 'analyze', 'to_node': 'visualize'},
                        {'from_node': 'visualize', 'to_node': 'report'},
                        {'from_node': 'report', 'to_node': 'end'}
                    ]
                }
            },
            'multi_agent_coordination': {
                'name': '多Agent协调',
                'description': '任务分发 → 并行处理 → 结果汇总',
                'definition': {
                    'nodes': [
                        {'id': 'dispatcher', 'type': 'start'},
                        {'id': 'agent1', 'type': 'parallel', 'agents': ['checker', 'scraper']},
                        {'id': 'agent2', 'type': 'parallel', 'agents': ['analyzer', 'summarizer']},
                        {'id': 'aggregator', 'type': 'task', 'action': 'merge'},
                        {'id': 'end', 'type': 'end'}
                    ],
                    'edges': [
                        {'from_node': 'dispatcher', 'to_node': 'agent1'},
                        {'from_node': 'agent1', 'to_node': 'agent2'},
                        {'from_node': 'agent2', 'to_node': 'aggregator'},
                        {'from_node': 'aggregator', 'to_node': 'end'}
                    ]
                }
            }
        }
        
        if template_name not in templates:
            return {
                'success': False,
                'error': f'模板不存在: {template_name}。可用模板: {list(templates.keys())}'
            }
        
        template = templates[template_name]
        return {
            'success': True,
            'template': template
        }
    
    async def _manage_version(self, workflow_id: str, version_action: str = 'list', 
                             version: str = None, **kwargs) -> Dict[str, Any]:
        """管理工作流版本
        
        Args:
            workflow_id: 工作流ID
            version_action: 操作(list/create/rollback)
            version: 版本号(用于create/rollback)
        """
        if version_action == 'list':
            # 列出所有版本
            versions = []
            version_dir = WORKFLOW_STORAGE_DIR / "versions" / workflow_id
            if version_dir.exists():
                for v_file in version_dir.glob("*.json"):
                    try:
                        with open(v_file, 'r', encoding='utf-8') as f:
                            v_data = json.load(f)
                        versions.append({
                            'version': v_data.get('version', ''),
                            'created_at': v_data.get('created_at', ''),
                            'description': v_data.get('description', '')
                        })
                    except Exception:
                        # 忽略损坏的版本文件
                        pass
            
            return {
                'success': True,
                'versions': sorted(versions, key=lambda x: x['version'], reverse=True)
            }
        
        elif version_action == 'create':
            # 创建新版本
            workflow_data = await self._load_workflow(workflow_id)
            if not workflow_data:
                return {'success': False, 'error': f'工作流不存在: {workflow_id}'}
            
            # 确定版本号
            target_version = version or workflow_data.get('version', '1.0.0')
            
            version_dir = WORKFLOW_STORAGE_DIR / "versions" / workflow_id
            version_dir.mkdir(parents=True, exist_ok=True)
            
            version_file = version_dir / f"{target_version}.json"
            
            # 更新元数据
            workflow_data['version'] = target_version
            workflow_data['updated_at'] = datetime.now().isoformat()
            
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(workflow_data, f, ensure_ascii=False, indent=2)
            
            return {
                'success': True,
                'message': f"版本 {target_version} 创建成功",
                'version': target_version
            }
        
        elif version_action == 'rollback':
            # 回滚到指定版本
            if not version:
                return {'success': False, 'error': '回滚操作必须指定版本号'}

            version_file = WORKFLOW_STORAGE_DIR / "versions" / workflow_id / f"{version}.json"
            if not version_file.exists():
                return {'success': False, 'error': f'版本不存在: {version}'}
            
            try:
                with open(version_file, 'r', encoding='utf-8') as f:
                    version_data = json.load(f)
            except Exception as e:
                return {'success': False, 'error': f'读取版本文件失败: {str(e)}'}
            
            # 恢复工作流到主存储区
            workflow_file = WORKFLOW_STORAGE_DIR / f"{workflow_id}.json"
            with open(workflow_file, 'w', encoding='utf-8') as f:
                json.dump(version_data, f, ensure_ascii=False, indent=2)
            
            return {
                'success': True,
                'message': f"已回滚到版本 {version}"
            }
        
        else:
            return {'success': False, 'error': f'未知版本操作: {version_action}'}
    
    async def _analyze_performance(self, workflow_id: str, **kwargs) -> Dict[str, Any]:
        """分析工作流性能
        
        返回:
        - 节点数量统计
        - 执行路径分析
        - 潜在瓶颈检测
        - 优化建议
        """
        workflow_data = await self._load_workflow(workflow_id)
        if not workflow_data:
            return {'success': False, 'error': f'工作流不存在: {workflow_id}'}
        
        definition = workflow_data['definition']
        nodes = definition.get('nodes', [])
        edges = definition.get('edges', [])
        
        # 统计分析
        node_types = {}
        for node in nodes:
            node_type = node.get('type', 'unknown')
            node_types[node_type] = node_types.get(node_type, 0) + 1
        
        # 检测潜在问题
        issues = []
        
        # 检查孤立节点
        connected_nodes = set()
        for edge in edges:
            connected_nodes.add(edge.get('from_node'))
            connected_nodes.add(edge.get('to_node'))
        
        all_nodes = {node['id'] for node in nodes}
        isolated_nodes = all_nodes - connected_nodes
        if isolated_nodes:
            issues.append({
                'type': 'warning',
                'message': f'发现孤立节点: {", ".join(isolated_nodes)}',
                'nodes': list(isolated_nodes)
            })
        
        # 检查深度过深
        max_depth = self._calculate_max_depth(edges)
        if max_depth > 10:
            issues.append({
                'type': 'performance',
                'message': f'工作流深度过大({max_depth}),可能影响执行效率',
                'recommendation': '考虑拆分为子工作流'
            })
        
        # 优化建议
        recommendations = []
        if len(nodes) > 20:
            recommendations.append('工作流节点较多,建议使用子工作流模块化')
        if node_types.get('llm', 0) > 5:
            recommendations.append('LLM节点较多,考虑批量处理以降低成本')
        if node_types.get('parallel', 0) == 0 and len(nodes) > 10:
            recommendations.append('未使用并行节点,可优化执行效率')
        
        return {
            'success': True,
            'analysis': {
                'workflow_id': workflow_id,
                'total_nodes': len(nodes),
                'total_edges': len(edges),
                'node_types': node_types,
                'max_depth': max_depth,
                'issues': issues,
                'recommendations': recommendations
            }
        }
    
    async def _delete_workflow(self, workflow_id: str, **kwargs) -> Dict[str, Any]:
        """删除工作流"""
        workflow_file = WORKFLOW_STORAGE_DIR / f"{workflow_id}.json"
        if not workflow_file.exists():
            return {'success': False, 'error': f'工作流不存在: {workflow_id}'}
        
        workflow_file.unlink()
        logger.info(f"OpenClaw工作流删除成功: {workflow_id}")
        return {
            'success': True,
            'message': f"工作流 '{workflow_id}' 已删除"
        }
    
    async def _export_workflow(self, workflow_id: str, format: str = 'json', **kwargs) -> Dict[str, Any]:
        """导出工作流
        
        Args:
            workflow_id: 工作流ID
            format: 导出格式(json/xml/yaml)
        """
        workflow_data = await self._load_workflow(workflow_id)
        if not workflow_data:
            return {'success': False, 'error': f'工作流不存在: {workflow_id}'}
        
        if format == 'json':
            return {
                'success': True,
                'format': 'json',
                'data': workflow_data
            }
        elif format == 'xml':
            # 转换为XML格式
            xml_content = self._convert_to_xml(workflow_data)
            return {
                'success': True,
                'format': 'xml',
                'data': xml_content
            }
        else:
            return {'success': False, 'error': f'不支持的导出格式: {format}'}
    
    async def _import_workflow(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """导入工作流"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
            
            workflow_id = workflow_data.get('id', 'imported_workflow')
            
            # 保存导入的工作流
            workflow_file = WORKFLOW_STORAGE_DIR / f"{workflow_id}.json"
            with open(workflow_file, 'w', encoding='utf-8') as f:
                json.dump(workflow_data, f, ensure_ascii=False, indent=2)
            
            return {
                'success': True,
                'message': f"工作流导入成功: {workflow_id}",
                'workflow_id': workflow_id
            }
        except Exception as e:
            return {'success': False, 'error': f'导入失败: {str(e)}'}
    
    # ========== 辅助方法 ==========
    
    async def _load_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """加载工作流数据"""
        workflow_file = WORKFLOW_STORAGE_DIR / f"{workflow_id}.json"
        if not workflow_file.exists():
            return None
        
        try:
            with open(workflow_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载工作流失败 {workflow_id}: {e}")
            return None
    
    def _detect_cycle(self, edges: List[Dict[str, str]]) -> bool:
        """检测图中是否存在循环依赖"""
        graph = {}
        for edge in edges:
            from_node = edge.get('from_node')
            to_node = edge.get('to_node')
            if from_node not in graph:
                graph[from_node] = []
            graph[from_node].append(to_node)
        
        visited = set()
        rec_stack = set()
        
        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.discard(node)
            return False
        
        for node in graph:
            if node not in visited:
                if dfs(node):
                    return True
        
        return False
    
    def _calculate_max_depth(self, edges: List[Dict[str, str]]) -> int:
        """计算工作流的最大深度"""
        if not edges:
            return 0
        
        # 构建邻接表
        graph = {}
        for edge in edges:
            from_node = edge.get('from_node')
            to_node = edge.get('to_node')
            if from_node not in graph:
                graph[from_node] = []
            graph[from_node].append(to_node)
        
        # BFS计算最大深度
        max_depth = 0
        visited = set()
        
        # 找到起始节点(没有入边的节点)
        all_targets = {edge.get('to_node') for edge in edges}
        all_sources = {edge.get('from_node') for edge in edges}
        start_nodes = all_sources - all_targets
        
        if not start_nodes:
            start_nodes = {list(graph.keys())[0]} if graph else set()
        
        for start in start_nodes:
            queue = [(start, 1)]
            while queue:
                node, depth = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                max_depth = max(max_depth, depth)
                
                for neighbor in graph.get(node, []):
                    if neighbor not in visited:
                        queue.append((neighbor, depth + 1))
        
        return max_depth
    
    def _convert_to_xml(self, workflow_data: Dict[str, Any]) -> str:
        """将工作流转换为XML格式"""
        import xml.etree.ElementTree as ET
        
        root = ET.Element("workflow")
        ET.SubElement(root, "id").text = workflow_data.get('id', '')
        ET.SubElement(root, "description").text = workflow_data.get('description', '')
        
        # 添加节点
        nodes_elem = ET.SubElement(root, "nodes")
        for node in workflow_data.get('definition', {}).get('nodes', []):
            node_elem = ET.SubElement(nodes_elem, "node")
            ET.SubElement(node_elem, "id").text = node.get('id', '')
            ET.SubElement(node_elem, "type").text = node.get('type', '')
            if 'action' in node:
                ET.SubElement(node_elem, "action").text = node['action']
        
        # 添加边
        edges_elem = ET.SubElement(root, "edges")
        for edge in workflow_data.get('definition', {}).get('edges', []):
            edge_elem = ET.SubElement(edges_elem, "edge")
            ET.SubElement(edge_elem, "from").text = edge.get('from_node', '')
            ET.SubElement(edge_elem, "to").text = edge.get('to_node', '')
        
        return ET.tostring(root, encoding='unicode')
    
    def _load_templates(self):
        """加载内置模板"""
        # 模板已在_get_template中定义,此处可扩展从文件加载
        pass


# 全局单例
_openclaw_handler = OpenClawHandler()

def get_openclaw_handler() -> OpenClawHandler:
    """获取OpenClaw处理器单例"""
    return _openclaw_handler

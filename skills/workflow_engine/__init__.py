"""AI工作流引擎包 - 类似Coze的可视化工作流搭建

整合了 hybrid_skill_agent 的技能链编排功能：
- 动态技能加载和管理
- 技能链编排（支持上下文变量传递）
- XML工作流优化（循环检测、节点去重、拓扑排序）
"""

from skills.workflow_engine.flow_controller import (
    WorkflowEngine,
    WORKFLOW_DIR,
    workflow_engine,
    get_workflow_manager,
)
from skills.workflow_engine.node_executor import WorkflowNode
from skills.workflow_engine.xml_parser import (
    detect_cycle,
    optimize_node_order,
    suggest_skill_replacements,
    optimize_xml_workflow,
    parse_xml_to_workflow,
)

__all__ = [
    "WorkflowEngine",
    "WorkflowNode",
    "WORKFLOW_DIR",
    "workflow_engine",
    "get_workflow_manager",
    "detect_cycle",
    "optimize_node_order",
    "suggest_skill_replacements",
    "optimize_xml_workflow",
    "parse_xml_to_workflow",
]

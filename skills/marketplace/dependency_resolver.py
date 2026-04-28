"""
技能依赖解析器 - Dependency Resolver

解析和管理技能之间的依赖关系，支持依赖安装、冲突检测等功能。
"""

import logging
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from .version_manager import SemanticVersion, VersionManager

logger = logging.getLogger(__name__)


class DependencyResolver:
    """
    依赖解析器
    
    负责解析技能的依赖关系，检测依赖冲突，提供依赖安装顺序。
    """
    
    def __init__(self, version_manager: Optional[VersionManager] = None):
        """
        初始化依赖解析器
        
        Args:
            version_manager: 版本管理器实例
        """
        self._version_manager = version_manager or VersionManager()
        self._dependency_graph: Dict[str, Dict[str, str]] = {}  # skill -> {dep: version_constraint}
        self._reverse_deps: Dict[str, Set[str]] = defaultdict(set)  # dep -> set of dependents
    
    def register_dependencies(self, skill_name: str, dependencies: Dict[str, str]) -> bool:
        """
        注册技能的依赖关系
        
        Args:
            skill_name: 技能名称
            dependencies: 依赖字典 {skill_name: version_constraint}
            
        Returns:
            bool: 注册是否成功
        """
        try:
            self._dependency_graph[skill_name] = dependencies.copy()
            
            # 更新反向依赖
            for dep_name in dependencies.keys():
                self._reverse_deps[dep_name].add(skill_name)
            
            logger.info(f"Registered dependencies for {skill_name}: {dependencies}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register dependencies: {e}")
            return False
    
    def resolve_dependencies(self, skill_name: str, 
                           visited: Optional[Set[str]] = None,
                           resolution_order: Optional[List[str]] = None) -> Tuple[bool, List[str], List[str]]:
        """
        解析技能的完整依赖树
        
        Args:
            skill_name: 要解析的技能名称
            visited: 已访问的技能集合（用于循环检测）
            resolution_order: 解析顺序列表
            
        Returns:
            Tuple[bool, List[str], List[str]]: (成功标志, 安装顺序, 错误信息)
        """
        if visited is None:
            visited = set()
        
        if resolution_order is None:
            resolution_order = []
        
        errors = []
        
        # 循环依赖检测
        if skill_name in visited:
            errors.append(f"Circular dependency detected: {skill_name}")
            return False, [], errors
        
        visited.add(skill_name)
        
        # 获取技能的依赖
        dependencies = self._dependency_graph.get(skill_name, {})
        
        if not dependencies:
            # 没有依赖，添加到安装顺序
            if skill_name not in resolution_order:
                resolution_order.append(skill_name)
            return True, resolution_order, errors
        
        # 递归解析每个依赖
        for dep_name, version_constraint in dependencies.items():
            # 检查版本兼容性
            compatible, recommended = self._version_manager.check_compatibility(
                dep_name, version_constraint
            )
            
            if not compatible:
                errors.append(f"Incompatible dependency: {dep_name} ({version_constraint}) - {recommended}")
                continue
            
            # 递归解析依赖的依赖
            success, _, dep_errors = self.resolve_dependencies(
                dep_name, visited.copy(), resolution_order
            )
            
            if not success:
                errors.extend(dep_errors)
                return False, [], errors
        
        # 所有依赖解析完成后，添加当前技能
        if skill_name not in resolution_order:
            resolution_order.append(skill_name)
        
        return True, resolution_order, errors
    
    def detect_conflicts(self, skill_name: str, new_dependencies: Dict[str, str]) -> List[Dict]:
        """
        检测依赖冲突
        
        Args:
            skill_name: 技能名称
            new_dependencies: 新的依赖关系
            
        Returns:
            List[Dict]: 冲突列表
        """
        conflicts = []
        
        # 获取现有的依赖
        existing_deps = self._dependency_graph.get(skill_name, {})
        
        # 检查与新依赖的冲突
        for dep_name, new_constraint in new_dependencies.items():
            if dep_name in existing_deps:
                old_constraint = existing_deps[dep_name]
                
                # 检查两个约束是否兼容
                if not self._are_constraints_compatible(old_constraint, new_constraint):
                    conflicts.append({
                        'dependency': dep_name,
                        'existing_constraint': old_constraint,
                        'new_constraint': new_constraint,
                        'message': f"Conflict for {dep_name}: {old_constraint} vs {new_constraint}"
                    })
        
        # 检查与其他技能的依赖冲突
        for other_skill, other_deps in self._dependency_graph.items():
            if other_skill == skill_name:
                continue
            
            for dep_name, other_constraint in other_deps.items():
                if dep_name in new_dependencies:
                    new_constraint = new_dependencies[dep_name]
                    
                    if not self._are_constraints_compatible(other_constraint, new_constraint):
                        conflicts.append({
                            'dependency': dep_name,
                            'skill1': skill_name,
                            'constraint1': new_constraint,
                            'skill2': other_skill,
                            'constraint2': other_constraint,
                            'message': f"Cross-skill conflict for {dep_name}: "
                                      f"{skill_name} requires {new_constraint}, "
                                      f"{other_skill} requires {other_constraint}"
                        })
        
        return conflicts
    
    def get_dependents(self, skill_name: str) -> Set[str]:
        """
        获取依赖指定技能的所有技能
        
        Args:
            skill_name: 技能名称
            
        Returns:
            Set[str]: 依赖该技能的技能集合
        """
        return self._reverse_deps.get(skill_name, set()).copy()
    
    def get_dependency_tree(self, skill_name: str, max_depth: int = 5) -> Dict:
        """
        获取依赖树（可视化结构）
        
        Args:
            skill_name: 技能名称
            max_depth: 最大深度
            
        Returns:
            Dict: 依赖树结构
        """
        def build_tree(name: str, depth: int, visited: Set[str]) -> Dict:
            if depth > max_depth or name in visited:
                return {'name': name, 'version': '?', 'children': []}
            
            visited.add(name)
            
            dependencies = self._dependency_graph.get(name, {})
            children = []
            
            for dep_name, constraint in dependencies.items():
                child_tree = build_tree(dep_name, depth + 1, visited.copy())
                child_tree['constraint'] = constraint
                children.append(child_tree)
            
            latest_version = self._version_manager.get_latest_version(name)
            
            return {
                'name': name,
                'version': latest_version or '?',
                'children': children
            }
        
        return build_tree(skill_name, 0, set())
    
    def _are_constraints_compatible(self, constraint1: str, constraint2: str) -> bool:
        """
        检查两个版本约束是否兼容
        
        Args:
            constraint1: 第一个约束
            constraint2: 第二个约束
            
        Returns:
            bool: 是否兼容
        """
        # 简化实现：如果两个约束都能被某个版本满足，则认为兼容
        # 实际实现可能需要更复杂的区间交集计算
        
        try:
            # 尝试找到一个能同时满足两个约束的版本
            test_versions = [
                "1.0.0", "1.1.0", "1.2.0", "2.0.0", "2.1.0", "3.0.0"
            ]
            
            for version_str in test_versions:
                version = SemanticVersion.parse(version_str)
                if (version.is_compatible_with(constraint1) and 
                    version.is_compatible_with(constraint2)):
                    return True
            
            return False
            
        except ValueError:
            return False
    
    def get_statistics(self) -> Dict:
        """获取依赖统计信息"""
        total_skills = len(self._dependency_graph)
        skills_with_deps = sum(
            1 for deps in self._dependency_graph.values() if deps
        )
        total_dependencies = sum(
            len(deps) for deps in self._dependency_graph.values()
        )
        
        return {
            'total_skills': total_skills,
            'skills_with_dependencies': skills_with_deps,
            'total_dependencies': total_dependencies,
            'average_dependencies_per_skill': (
                total_dependencies / total_skills if total_skills > 0 else 0
            )
        }

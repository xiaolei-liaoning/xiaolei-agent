"""
技能验证器 - Skill Validator

验证技能的结构、代码质量和安全性，确保发布的技能符合规范。
"""

import ast
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ValidationResult:
    """验证结果"""
    
    def __init__(self):
        self.is_valid: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.suggestions: List[str] = []
    
    def add_error(self, message: str):
        self.is_valid = False
        self.errors.append(message)
    
    def add_warning(self, message: str):
        self.warnings.append(message)
    
    def add_suggestion(self, message: str):
        self.suggestions.append(message)
    
    def to_dict(self) -> Dict:
        return {
            'is_valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'suggestions': self.suggestions,
            'total_issues': len(self.errors) + len(self.warnings) + len(self.suggestions)
        }


class SkillValidator:
    """
    技能验证器
    
    验证技能的目录结构、代码规范、安全性等。
    """
    
    REQUIRED_FILES = ['handler.py', 'SKILL.md']
    OPTIONAL_FILES = ['config.py', 'requirements.txt', '__init__.py']
    
    def __init__(self):
        self._security_patterns = [
            r'os\.system\s*\(',
            r'subprocess\.(call|run|Popen)\s*\(',
            r'eval\s*\(',
            r'exec\s*\(',
            r'__import__\s*\(',
            r'importlib\.(import_module|reload)\s*\(',
        ]
    
    def validate_skill(self, skill_path: Path) -> ValidationResult:
        """
        验证技能
        
        Args:
            skill_path: 技能目录路径
            
        Returns:
            ValidationResult: 验证结果
        """
        result = ValidationResult()
        
        # 1. 验证目录结构
        self._validate_structure(skill_path, result)
        
        # 2. 验证元数据文件
        self._validate_metadata(skill_path, result)
        
        # 3. 验证处理器代码
        handler_file = skill_path / 'handler.py'
        if handler_file.exists():
            self._validate_handler(handler_file, result)
        
        # 4. 安全检查
        self._security_check(skill_path, result)
        
        # 5. 代码质量检查
        self._code_quality_check(skill_path, result)
        
        logger.info(f"Validation result for {skill_path.name}: "
                   f"valid={result.is_valid}, "
                   f"errors={len(result.errors)}, "
                   f"warnings={len(result.warnings)}")
        
        return result
    
    def _validate_structure(self, skill_path: Path, result: ValidationResult):
        """验证目录结构"""
        if not skill_path.exists():
            result.add_error(f"Skill directory does not exist: {skill_path}")
            return
        
        if not skill_path.is_dir():
            result.add_error(f"Skill path is not a directory: {skill_path}")
            return
        
        # 检查必需文件
        for required_file in self.REQUIRED_FILES:
            file_path = skill_path / required_file
            if not file_path.exists():
                result.add_error(f"Missing required file: {required_file}")
        
        # 检查可选文件并提供建议
        has_requirements = (skill_path / 'requirements.txt').exists()
        if not has_requirements:
            result.add_suggestion("Consider adding requirements.txt for dependency management")
    
    def _validate_metadata(self, skill_path: Path, result: ValidationResult):
        """验证元数据文件"""
        md_file = skill_path / 'SKILL.md'
        
        if not md_file.exists():
            return  # 已在结构验证中处理
        
        try:
            content = md_file.read_text(encoding='utf-8')
            
            # 检查必需字段
            required_fields = [
                ('# ', 'Skill name (H1 heading)'),
                ('## Description', 'Description section'),
                ('## Version', 'Version field'),
                ('## Author', 'Author field'),
            ]
            
            for pattern, field_name in required_fields:
                if pattern not in content:
                    result.add_warning(f"Missing or incomplete {field_name} in SKILL.md")
            
            # 检查版本格式
            version_match = re.search(r'## Version\s*\n\s*(\d+\.\d+\.\d+)', content)
            if version_match:
                version = version_match.group(1)
                if not self._is_valid_semver(version):
                    result.add_error(f"Invalid version format: {version}. Use semantic versioning (e.g., 1.0.0)")
            else:
                result.add_warning("Version not found or invalid format")
            
            # 检查是否有示例代码
            if '```python' not in content and '```' not in content:
                result.add_suggestion("Add usage examples in SKILL.md")
            
        except Exception as e:
            result.add_error(f"Failed to read SKILL.md: {str(e)}")
    
    def _validate_handler(self, handler_file: Path, result: ValidationResult):
        """验证处理器代码"""
        try:
            content = handler_file.read_text(encoding='utf-8')
            
            # 解析AST
            tree = ast.parse(content)
            
            # 检查是否有handler实例
            has_handler_instance = False
            has_execute_method = False
            
            for node in ast.walk(tree):
                # 查找类定义
                if isinstance(node, ast.ClassDef):
                    # 检查是否有execute方法
                    for item in node.body:
                        if isinstance(item, ast.AsyncFunctionDef) and item.name == 'execute':
                            has_execute_method = True
                
                # 查找handler实例化
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == 'handler':
                            has_handler_instance = True
            
            if not has_execute_method:
                result.add_error("Handler class must have an 'async def execute' method")
            
            if not has_handler_instance:
                result.add_warning("No 'handler = ClassName()' instance found at module level")
            
            # 检查导入语句
            imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
            if not imports:
                result.add_suggestion("Consider adding docstring and imports")
            
        except SyntaxError as e:
            result.add_error(f"Syntax error in handler.py: {str(e)}")
        except Exception as e:
            result.add_error(f"Failed to parse handler.py: {str(e)}")
    
    def _security_check(self, skill_path: Path, result: ValidationResult):
        """安全检查"""
        # 扫描Python文件
        for py_file in skill_path.rglob('*.py'):
            try:
                content = py_file.read_text(encoding='utf-8')
                
                for pattern in self._security_patterns:
                    if re.search(pattern, content):
                        result.add_warning(
                            f"Potentially dangerous code in {py_file.name}: "
                            f"detected '{pattern}'"
                        )
            
            except Exception:
                continue
    
    def _code_quality_check(self, skill_path: Path, result: ValidationResult):
        """代码质量检查"""
        handler_file = skill_path / 'handler.py'
        
        if not handler_file.exists():
            return
        
        try:
            content = handler_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            # 检查文件长度
            if len(lines) > 500:
                result.add_warning(f"Handler file is very long ({len(lines)} lines). Consider splitting into modules.")
            
            # 检查函数长度
            in_function = False
            function_lines = 0
            function_name = ""
            
            for line in lines:
                if line.strip().startswith('async def ') or line.strip().startswith('def '):
                    if in_function and function_lines > 50:
                        result.add_warning(
                            f"Function '{function_name}' is very long ({function_lines} lines). "
                            f"Consider refactoring."
                        )
                    
                    in_function = True
                    function_name = line.strip().split('(')[0].replace('async def ', '').replace('def ', '')
                    function_lines = 0
                elif in_function:
                    function_lines += 1
            
            # 检查是否有文档字符串
            if '"""' not in content and "'''" not in content:
                result.add_suggestion("Add docstrings to improve code documentation")
            
            # 检查异常处理
            if 'try:' not in content or 'except' not in content:
                result.add_warning("No exception handling found. Consider adding try-except blocks.")
            
        except Exception as e:
            logger.debug(f"Code quality check failed: {e}")
    
    def _is_valid_semver(self, version: str) -> bool:
        """检查是否为有效的语义化版本号"""
        pattern = r'^\d+\.\d+\.\d+$'
        return bool(re.match(pattern, version))
    
    def validate_multiple_skills(self, skills_dir: Path) -> Dict[str, ValidationResult]:
        """
        批量验证多个技能
        
        Args:
            skills_dir: 技能目录
            
        Returns:
            Dict[str, ValidationResult]: 每个技能的验证结果
        """
        results = {}
        
        if not skills_dir.exists():
            return results
        
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and not skill_dir.name.startswith('_'):
                result = self.validate_skill(skill_dir)
                results[skill_dir.name] = result
        
        return results
    
    def get_validation_summary(self, results: Dict[str, ValidationResult]) -> Dict:
        """
        获取验证摘要
        
        Args:
            results: 验证结果字典
            
        Returns:
            Dict: 验证摘要
        """
        total = len(results)
        valid_count = sum(1 for r in results.values() if r.is_valid)
        total_errors = sum(len(r.errors) for r in results.values())
        total_warnings = sum(len(r.warnings) for r in results.values())
        
        return {
            'total_skills': total,
            'valid_skills': valid_count,
            'invalid_skills': total - valid_count,
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'validation_rate': round(valid_count / total * 100, 2) if total > 0 else 0
        }

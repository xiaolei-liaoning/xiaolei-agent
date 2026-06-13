"""文件内容检测与补全

从 react_core.py 提取，负责：
- write_file 后的文件完整性校验
- HTML/Python/JS/CSS 文件类型检测
- 截断检测与续写指令注入
- script 空代码检测与补充指令
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)


def get_prefix(agent=None) -> str:
    """获取 Agent 名称前缀"""
    if agent and hasattr(agent, "name"):
        return f"[{agent.name}]"
    return "[Agent]"


def validate_file_content(
    path: str,
    content: str,
    actual_content: Optional[str] = None,
    ctx=None,
    agent=None,
) -> None:
    """验证写入的文件内容，发现问题时设置 forced_instructions
    
    Args:
        path: 文件路径
        content: 传入的内容
        actual_content: 实际写入的内容（从磁盘读取）
        ctx: RunContext（用于设置 forced_instructions）
        agent: Agent 实例（用于获取前缀）
    """
    prefix = get_prefix(agent)
    
    # 统一重试计数器（避免无限循环）
    _retry_key = f"write_retry:{path}"
    if not hasattr(ctx, '_write_retries') if ctx else True:
        if ctx:
            ctx._write_retries = {}
    _retry_count = ctx._write_retries.get(_retry_key, 0) if ctx else 0
    
    if not actual_content:
        # 文件不存在或无法读取 → 强制重写
        logger.error(f"文件 {path} 写入后无法读取！传入了{len(content)}字符")
        print(f"{prefix}    \033[1;31m❌ 文件 {path} 写入失败（磁盘上不存在）！\033[0m")
        if ctx:
            ctx._write_retries[_retry_key] = _retry_count + 1
            if _retry_count >= 2:
                ctx.forced_instructions = (
                    f"文件 {path} 多次尝试后仍找不到（第{_retry_count + 1}次）。\n"
                    "不要继续重试 write_file。请：\n"
                    "1. 直接输出最终结果，告诉用户文件可能被系统拦截\n"
                    "2. 或尝试换一个文件名/路径"
                )
            else:
                ctx.forced_instructions = (
                    f"文件 {path} 写入失败！磁盘上不存在该文件。\n"
                    "请重新调用 write_file 写入完整代码。\n"
                    f"路径: {path}\n"
                    "内容必须包含完整的 HTML/CSS/JavaScript。"
                )
        return
    
    # 检查文件大小
    if len(actual_content) < len(content) * 0.5 and len(content) > 100:
        # 文件比传入内容小很多 → 写入不完整
        logger.warning(f"文件 {path} 实际大小({len(actual_content)}) 远小于传入内容({len(content)})")
        print(f"{prefix}    \033[1;33m⚠️ 文件写入不完整: 传入{len(content)}字符, 实际{len(actual_content)}字符\033[0m")
        if ctx:
            ctx._write_retries[_retry_key] = _retry_count + 1

            if _retry_count >= 2:
                # 已经重试多次，让 agent 换策略
                ctx.forced_instructions = (
                    f"文件 {path} 写入仍然不完整（第{_retry_count + 1}次尝试）。\n"
                    "不要再用 write_file 重试同一内容。请选择：\n"
                    "1. 使用 force=true 参数强制覆盖\n"
                    "2. 简化内容后重新写入\n"
                    "3. 直接输出最终结果"
                )
            else:
                ctx.forced_instructions = (
                    f"文件 {path} 写入不完整！传入了{len(content)}字符但文件只有{len(actual_content)}字符。\n"
                    "请用 write_file 重新写入完整代码，确保内容完整无截断。"
                )
        return
    elif content and len(actual_content) < len(content) * 0.8:
        # 文件略有截断但不算严重
        logger.info(f"文件 {path} 略有截断: 传入{len(content)}, 实际{len(actual_content)}")
    
    if not content:
        return
    
    # 根据文件扩展名进行完整性校验
    needs_regeneration = False
    missing_parts = []
    
    # HTML 文件校验 — 只检查基本结构，不强制 script/style（静态报告不需要）
    if path.endswith((".html", ".htm")):
        content_lower = content.lower()
        has_doctype = "<!doctype" in content_lower or "<!DOCTYPE" in content
        has_html = "<html" in content_lower
        
        # 只有 DOCTYPE 和 html 标签都缺失才需要重新生成
        if not has_doctype and not has_html:
            needs_regeneration = True
            missing_parts.append("基本 HTML 结构 (DOCTYPE + <html>)")
    
    # Python 文件校验
    elif path.endswith(".py"):
        has_def = "def " in content
        has_class = "class " in content
        has_print = "print(" in content
        
        # 检查是否只是空壳或简单打印
        if len(content) < 100 and not has_def and not has_class:
            needs_regeneration = True
            missing_parts.append("完整的函数/类定义")
        if not has_print and not has_def and not has_class:
            missing_parts.append("实际执行逻辑")
    
    # JavaScript/TypeScript 文件校验
    elif path.endswith((".js", ".ts", ".jsx", ".tsx")):
        has_function = "function " in content or "=>" in content or "async " in content
        
        if len(content) < 100 and not has_function:
            needs_regeneration = True
            missing_parts.append("函数定义")
    
    # CSS 文件校验
    elif path.endswith((".css", ".scss", ".less")):
        has_selector = "{" in content and "}" in content
        
        if len(content) < 50:
            needs_regeneration = True
            missing_parts.append("完整的 CSS 规则")
    
    # 通用代码文件校验（太短可能只是占位符）
    elif len(content) < 50 and any(kw in path for kw in ["game", "Game", "app", "App", "main", "Main"]):
        needs_regeneration = True
        missing_parts.append("完整的代码实现")
    
    # 生成警告信息
    if needs_regeneration:
        logger.warning(f"文件 {path} 内容不完整，缺少: {', '.join(missing_parts)}")
        print(f"{prefix}    \033[1;33m⚠️ 文件内容不完整，诱导补充完整代码\033[0m")
        if ctx:
            ctx.forced_instructions = (
                f"文件 {path} 内容不完整！缺少：{', '.join(missing_parts)}\n"
                f"你必须重新用 write_file 写入完整的代码文件！\n"
                "使用 write_file(path='原路径', content='完整代码') 重新写入。"
            )
    elif missing_parts:
        # 轻微问题，只警告不强制
        logger.info(f"文件 {path} 可能缺少: {', '.join(missing_parts)}")
    
    # ── 截断检测：读回文件检查是否缺少闭合标签，注入续写指令 ──
    if actual_content and path.endswith(('.html', '.htm')):
        actual_lower = actual_content.lower()
        missing_close = []
        if '<script' in actual_lower and '</script>' not in actual_lower:
            missing_close.append("</script>")
        if '<style' in actual_lower and '</style>' not in actual_lower:
            missing_close.append("</style>")
        if '<body' in actual_lower and '</body>' not in actual_lower:
            missing_close.append("</body>")
        if '</html>' not in actual_lower:
            missing_close.append("</html>")
        
        if missing_close:
            print(f"{prefix}    \033[1;33m⚠️ 文件被截断，缺少: {', '.join(missing_close)}，注入续写指令\033[0m")
            if ctx:
                ctx.forced_instructions = (
                    f"代码被截断！文件 {path} 缺少: {', '.join(missing_close)}\n"
                    f"当前文件已有 {len(actual_content)} 字符。\n"
                    "请使用 write_file 继续生成剩余代码。\n"
                    "重要：在 content 参数中只写缺失的部分（从断点继续），不要重复已有内容。\n"
                    f"路径: {path}\n"
                    "示例：write_file(path='同上', content='缺失的HTML/JS代码...')"
                )
        # 检测 <script> 只有注释没有实际代码
        elif '<script' in actual_lower:
            script_match = re.search(r'<script[^>]*>(.*?)</script>', actual_content, re.DOTALL | re.IGNORECASE)
            if script_match:
                script_body = script_match.group(1).strip()
                # 去掉注释后检查是否有实际代码
                code_only = re.sub(r'//.*?\n', '\n', script_body)
                code_only = re.sub(r'/\*.*?\*/', '', code_only, flags=re.DOTALL)
                code_only = code_only.strip()
                if len(code_only) < 20:
                    print(f"{prefix}    \033[1;33m⚠️ <script> 中只有注释没有实际代码，注入补充指令\033[0m")
                    # 更强制的指令，明确告诉LLM必须立即补充代码
                    if ctx:
                        ctx.forced_instructions = (
                            f"【紧急】文件 {path} 的 <script> 标签中只有注释，没有实际的 JavaScript 代码！\n"
                            "你必须立即用 write_file 补充完整的游戏逻辑代码！\n\n"
                            "要求：\n"
                            "1. 用 write_file 工具，path 参数与刚才相同\n"
                            "2. content 参数必须是完整的 HTML 文件（包含 CSS + JavaScript）\n"
                            "3. JavaScript 代码必须包含实际的游戏逻辑（初始化、事件处理、状态管理等）\n"
                            "4. 不能只有注释，必须有可执行的代码\n\n"
                            "示例：write_file(path='同上', content='<!DOCTYPE html>...<script>function init(){...}</script>...')"
                        )

        # ── 游戏类 HTML 交互性提示（仅日志，不阻断） ──
        if actual_content and _is_game_file(path, actual_content):
            logger.info(f"游戏类文件: {path} ({len(actual_content)}字符)")


def _is_game_file(path: str, content: str) -> bool:
    """判断文件是否属于游戏类"""
    game_keywords = ['game', 'puzzle', '八数码', '数码', 'zombie', '僵尸', '植物大战',
                     '游戏', 'play', '贪吃蛇', '俄罗斯方块', '2048', '斗地主']
    name = os.path.basename(path).lower()
    if any(kw in name for kw in game_keywords):
        return True
    content_lower = content.lower()
    if any(kw in content_lower for kw in ['game', '游戏', 'puzzle', '僵尸', 'play']):
        return True
    return False


def check_python_code_quality(content: str, path: str) -> dict:
    """检查 Python 代码质量
    
    Returns:
        dict: {"valid": bool, "issues": list}
    """
    issues = []
    
    if len(content) < 50:
        issues.append("代码过短（<50字符）")
    
    has_def = "def " in content
    has_class = "class " in content
    has_import = "import " in content or "from " in content
    has_print = "print(" in content
    
    if not has_def and not has_class and not has_import:
        issues.append("缺少函数/类定义和import语句")
    
    if not has_print and not has_def:
        issues.append("没有 print() 输出或函数定义")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


def check_html_completeness(content: str) -> dict:
    """检查 HTML 文件完整性
    
    Returns:
        dict: {"valid": bool, "missing": list, "has_script": bool, "has_style": bool}
    """
    missing = []
    content_lower = content.lower()
    
    if "<!doctype" not in content_lower and "<!doctype html>" not in content_lower:
        missing.append("DOCTYPE")
    if "<html" not in content_lower:
        missing.append("<html>")
    if "</html>" not in content_lower:
        missing.append("</html>")
    if "<body" not in content_lower:
        missing.append("<body>")
    if "</body>" not in content_lower:
        missing.append("</body>")
    
    has_script = "<script" in content_lower
    has_style = "<style" in content_lower
    
    # 检查 script 是否有实际代码
    script_has_code = False
    if has_script:
        script_match = re.search(r'<script[^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)
        if script_match:
            script_body = script_match.group(1).strip()
            code_only = re.sub(r'//.*?\n', '\n', script_body)
            code_only = re.sub(r'/\*.*?\*/', '', code_only, flags=re.DOTALL)
            script_has_code = len(code_only.strip()) > 20
    
    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "has_script": has_script,
        "has_style": has_style,
        "script_has_code": script_has_code,
    }


def validate_code_quality(path: str, content: str, ctx=None, agent=None) -> bool:
    """验证代码质量，发现问题时设置强制指令
    
    Args:
        path: 文件路径
        content: 代码内容
        ctx: RunContext
        agent: Agent 实例
        
    Returns:
        bool: 是否通过质量检查
    """
    try:
        from core.multi_agent_v2.agents.code_quality_checker import CodeQualityChecker
        
        prefix = get_prefix(agent)
        checker = CodeQualityChecker()
        
        if path.endswith(('.html', '.htm')):
            report = checker.check_html(content)
        elif path.endswith('.js'):
            report = checker.check_javascript(content)
        else:
            return True  # 其他文件类型跳过检查
        
        # 检查是否有严重错误
        errors = [i for i in report.issues if i.severity == 'error']
        warnings = [i for i in report.issues if i.severity == 'warning']
        
        if errors:
            error_msg = '\n'.join([f"  - {e.message} (行{e.line})" for e in errors[:3]])
            print(f"{prefix}    \033[1;31m❌ 代码质量检查失败:\n{error_msg}\033[0m")
            
            if ctx:
                ctx.forced_instructions = (
                    f"代码质量检查失败！发现 {len(errors)} 个错误:\n"
                    f"{error_msg}\n\n"
                    "请修复以下问题后重新写入:\n"
                )
                for s in report.suggestions:
                    ctx.forced_instructions += f"  - {s}\n"
            
            return False
        
        if warnings:
            warning_msg = '\n'.join([f"  - {w.message}" for w in warnings[:3]])
            print(f"{prefix}    \033[1;33m⚠️ 代码质量警告:\n{warning_msg}\033[0m")
        
        return True
        
    except Exception as e:
        logger.debug(f"代码质量检查异常: {e}")
        return True  # 检查异常时不阻止写入

"""
Tail Call — 工具链式调用

允许工具在执行后请求调用另一个工具
对标 gemini-cli 的 Tail Call 功能
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TailCallRequest:
    """Tail Call 请求"""
    tool_name: str              # 下一个工具名
    arguments: Dict[str, Any] = field(default_factory=dict)  # 参数
    reason: str = ""            # 原因说明
    max_depth: int = 5          # 最大链式深度


@dataclass
class TailCallChain:
    """Tail Call 链"""
    calls: List[TailCallRequest] = field(default_factory=list)
    results: List[Dict] = field(default_factory=list)
    current_depth: int = 0
    max_depth: int = 5


class TailCallHandler:
    """Tail Call 处理器"""

    def __init__(self):
        self._chains: Dict[str, TailCallChain] = {}
        self._handlers: Dict[str, Callable] = {}

    def register_handler(self, tool_name: str, handler: Callable) -> None:
        """注册工具的 Tail Call 处理器"""
        self._handlers[tool_name] = handler
        logger.debug(f"注册 Tail Call 处理器: {tool_name}")

    def extract_tail_call(self, tool_result: Any) -> Optional[TailCallRequest]:
        """
        从工具结果中提取 Tail Call 请求

        支持两种格式：
        1. 结果中包含 __tail_call__ 字段
        2. 结果是字符串，包含 JSON 格式的 Tail Call 请求
        """
        if not tool_result:
            return None

        # 格式 1：字典中包含 __tail_call__
        if isinstance(tool_result, dict):
            if "__tail_call__" in tool_result:
                tc = tool_result["__tail_call__"]
                return TailCallRequest(
                    tool_name=tc.get("tool", tc.get("name", "")),
                    arguments=tc.get("arguments", tc.get("args", {})),
                    reason=tc.get("reason", ""),
                    max_depth=tc.get("max_depth", 5),
                )

            # 检查 result 字段
            if "result" in tool_result and isinstance(tool_result["result"], dict):
                if "__tail_call__" in tool_result["result"]:
                    tc = tool_result["result"]["__tail_call__"]
                    return TailCallRequest(
                        tool_name=tc.get("tool", tc.get("name", "")),
                        arguments=tc.get("arguments", tc.get("args", {})),
                        reason=tc.get("reason", ""),
                        max_depth=tc.get("max_depth", 5),
                    )

        # 格式 2：字符串中包含 JSON
        if isinstance(tool_result, str):
            try:
                data = json.loads(tool_result)
                if isinstance(data, dict) and "__tail_call__" in data:
                    tc = data["__tail_call__"]
                    return TailCallRequest(
                        tool_name=tc.get("tool", tc.get("name", "")),
                        arguments=tc.get("arguments", tc.get("args", {})),
                        reason=tc.get("reason", ""),
                        max_depth=tc.get("max_depth", 5),
                    )
            except (json.JSONDecodeError, TypeError):
                pass

            # 尝试从文本中提取 JSON
            import re
            match = re.search(r'\{[^{}]*"__tail_call__"[^{}]*\}', tool_result)
            if match:
                try:
                    data = json.loads(match.group())
                    if "__tail_call__" in data:
                        tc = data["__tail_call__"]
                        return TailCallRequest(
                            tool_name=tc.get("tool", tc.get("name", "")),
                            arguments=tc.get("arguments", tc.get("args", {})),
                            reason=tc.get("reason", ""),
                            max_depth=tc.get("max_depth", 5),
                        )
                except (json.JSONDecodeError, TypeError):
                    pass

        return None

    def create_chain(self, chain_id: str, max_depth: int = 5) -> TailCallChain:
        """创建 Tail Call 链"""
        chain = TailCallChain(max_depth=max_depth)
        self._chains[chain_id] = chain
        return chain

    def add_to_chain(self, chain_id: str, request: TailCallRequest) -> bool:
        """添加到链"""
        if chain_id not in self._chains:
            return False

        chain = self._chains[chain_id]
        if chain.current_depth >= chain.max_depth:
            logger.warning(f"Tail Call 链深度超过限制: {chain.max_depth}")
            return False

        chain.calls.append(request)
        chain.current_depth += 1
        return True

    def get_next_call(self, chain_id: str) -> Optional[TailCallRequest]:
        """获取下一个调用"""
        if chain_id not in self._chains:
            return None

        chain = self._chains[chain_id]
        if chain.calls:
            return chain.calls[0]
        return None

    def complete_call(self, chain_id: str, result: Any) -> None:
        """完成一个调用"""
        if chain_id not in self._chains:
            return

        chain = self._chains[chain_id]
        if chain.calls:
            chain.calls.pop(0)
            chain.results.append({"result": result})

    def is_chain_complete(self, chain_id: str) -> bool:
        """检查链是否完成"""
        if chain_id not in self._chains:
            return True

        chain = self._chains[chain_id]
        return len(chain.calls) == 0

    def get_chain_results(self, chain_id: str) -> List[Dict]:
        """获取链的所有结果"""
        if chain_id not in self._chains:
            return []

        return self._chains[chain_id].results

    def clear_chain(self, chain_id: str) -> None:
        """清除链"""
        self._chains.pop(chain_id, None)


def create_tail_call_response(
    tool_name: str,
    arguments: Dict[str, Any],
    reason: str = "",
    max_depth: int = 5,
) -> Dict:
    """
    创建 Tail Call 响应

    工具可以在返回结果中包含此响应，触发 Tail Call
    """
    return {
        "__tail_call__": {
            "tool": tool_name,
            "arguments": arguments,
            "reason": reason,
            "max_depth": max_depth,
        }
    }


# 示例：工具返回 Tail Call 响应
def example_fetch_and_process():
    """示例：获取数据并处理"""
    # 工具执行后，返回 Tail Call 请求
    return create_tail_call_response(
        tool_name="execute_python",
        arguments={
            "code": "import json; print(json.dumps(data, indent=2))"
        },
        reason="获取数据后需要格式化处理",
        max_depth=3,
    )


# 全局处理器实例
_tail_call_handler: Optional[TailCallHandler] = None


def get_tail_call_handler() -> TailCallHandler:
    """获取全局 Tail Call 处理器"""
    global _tail_call_handler
    if _tail_call_handler is None:
        _tail_call_handler = TailCallHandler()
    return _tail_call_handler

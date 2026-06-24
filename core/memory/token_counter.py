"""Unified token counter for context compression.

Provides CJK-aware token estimation without external dependencies.
Ratios are approximate; good enough for compression thresholds.
"""

import re
from typing import List, Dict


# ponytail: hardcoded ratios — good enough for context sizing, use tiktoken if precision matters
_CJK_RE = re.compile(r'[一-鿿぀-ヿ]')


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = max(0, len(text) - cjk - ascii_chars)
    return int(cjk * 1.5 + ascii_chars / 4 + other / 2) + 1


def count_messages_tokens(messages: List[Dict[str, str]]) -> int:
    return sum(estimate_tokens(m.get("content", "")) for m in messages)


def get_context_usage(messages: List[Dict[str, str]], model_limit: int = 8000) -> float:
    return min(count_messages_tokens(messages) / model_limit * 100, 100.0)


class _TokenCounter:
    """Simple namespace binding the three functions."""

    estimate_tokens = staticmethod(estimate_tokens)
    count_messages_tokens = staticmethod(count_messages_tokens)
    get_context_usage = staticmethod(get_context_usage)


_counter = _TokenCounter()


def get_token_counter() -> _TokenCounter:
    return _counter

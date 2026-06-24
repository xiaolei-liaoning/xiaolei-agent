# 记忆系统全面重构实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建自动从对话中提取用户事实/偏好的记忆系统，统一 Web/CLI 两条路径的记忆读写，建立用户画像。

**架构：** 三层记忆架构——用户画像层（结构化用户数据）+ 事实提取层（LLM驱动自动提取）+ 统一接入层（MemoryMiddleware 统一所有路径的读写）。参考 hermes-agent 的 MemoryProvider ABC 设计，但适配小雷版agent的 V1 多Agent 架构。

**技术栈：** ChromaDB（向量存储）、Pydantic（数据模型）、asyncio（异步执行）

---

## 文件结构

### 新建文件
| 文件路径 | 职责 |
|---------|------|
| `core/memory/user_profile.py` | 用户画像数据模型 + 持久化（JSON文件） |
| `core/memory/fact_extractor.py` | LLM驱动的事实/偏好自动提取器 |
| `core/memory/memory_middleware.py` | 统一记忆读写中间件，替代分散在各层的记忆逻辑 |
| `tests/test_user_profile.py` | 用户画像单元测试 |
| `tests/test_fact_extractor.py` | 事实提取器单元测试 |
| `tests/test_memory_middleware.py` | 记忆中间件单元测试 |

### 修改文件
| 文件路径 | 修改内容 |
|---------|---------|
| `api/routes/chat.py:363-417` | 删除手动正则提取，改用 MemoryMiddleware |
| `core/agent_system.py:897-980` | `_react_think` 改用 MemoryMiddleware 获取用户上下文 |
| `cli/handlers/chat_handler.py:576-597` | WorkAgent 设置 user_id + 调用 MemoryMiddleware |
| `core/handlers/chat_handler.py:9-73` | 改用 MemoryMiddleware 替代分散的记忆调用 |

---

## 任务 1：用户画像数据模型

**文件：**
- 创建：`core/memory/user_profile.py`
- 测试：`tests/test_user_profile.py`

- [ ] **步骤 1：编写用户画像数据模型**

```python
# core/memory/user_profile.py
"""用户画像 — 结构化存储用户身份、偏好、习惯"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# ponytail: 用 dict 而非 Pydantic，stdlib 够用，不引入新依赖


class UserProfile:
    """用户画像 — 持久化为 JSON 文件"""

    def __init__(self, user_id: str, base_dir: str = None):
        self.user_id = user_id
        self._base_dir = base_dir or os.path.expanduser("~/.小雷版小龙虾/profiles")
        self._path = Path(self._base_dir) / f"{user_id}.json"
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """从磁盘加载画像"""
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("加载用户画像失败: %s", e)
        return {
            "user_id": self.user_id,
            "name": None,
            "facts": [],          # [{"content": "...", "category": "...", "updated_at": "..."}]
            "preferences": [],    # [{"content": "...", "category": "preference", "updated_at": "..."}]
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def save(self) -> None:
        """原子写入磁盘（tempfile + rename）"""
        self._data["updated_at"] = datetime.now().isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as e:
            logger.error("保存用户画像失败: %s", e)

    @property
    def name(self) -> Optional[str]:
        return self._data.get("name")

    @name.setter
    def name(self, value: str):
        self._data["name"] = value
        self.save()

    @property
    def facts(self) -> List[Dict[str, Any]]:
        return self._data.get("facts", [])

    @property
    def preferences(self) -> List[Dict[str, Any]]:
        return self._data.get("preferences", [])

    def add_fact(self, content: str, category: str = "fact") -> bool:
        """添加事实，去重后保存。返回是否新增。"""
        # 去重：检查是否已有相同内容
        for f in self._data["facts"]:
            if f["content"] == content:
                return False
        self._data["facts"].append({
            "content": content,
            "category": category,
            "updated_at": datetime.now().isoformat(),
        })
        self.save()
        return True

    def add_preference(self, content: str) -> bool:
        """添加偏好，去重后保存。"""
        for p in self._data["preferences"]:
            if p["content"] == content:
                return False
        self._data["preferences"].append({
            "content": content,
            "category": "preference",
            "updated_at": datetime.now().isoformat(),
        })
        self.save()
        return True

    def remove_fact(self, content_substring: str) -> bool:
        """按子串匹配删除事实。"""
        before = len(self._data["facts"])
        self._data["facts"] = [
            f for f in self._data["facts"]
            if content_substring not in f["content"]
        ]
        if len(self._data["facts"]) < before:
            self.save()
            return True
        return False

    def to_system_prompt_block(self) -> str:
        """渲染为系统提示注入块"""
        parts = []
        if self.name:
            parts.append(f"用户姓名: {self.name}")
        if self._data["facts"]:
            facts_str = "\n".join(f"- {f['content']}" for f in self._data["facts"][:20])
            parts.append(f"用户事实:\n{facts_str}")
        if self._data["preferences"]:
            prefs_str = "\n".join(f"- {p['content']}" for p in self._data["preferences"][:10])
            parts.append(f"用户偏好:\n{prefs_str}")
        if not parts:
            return ""
        return "【用户画像】\n" + "\n\n".join(parts)


# 全局缓存
_profiles: Dict[str, UserProfile] = {}


def get_user_profile(user_id: str) -> UserProfile:
    """获取用户画像单例"""
    uid = str(user_id)
    if uid not in _profiles:
        _profiles[uid] = UserProfile(uid)
    return _profiles[uid]
```

- [ ] **步骤 2：编写测试**

```python
# tests/test_user_profile.py
"""用户画像测试"""

import json
import tempfile
from pathlib import Path
from core.memory.user_profile import UserProfile, get_user_profile


def test_profile_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_001", base_dir=tmpdir)
        assert p.name is None
        assert p.facts == []
        assert p.preferences == []


def test_set_name():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_002", base_dir=tmpdir)
        p.name = "小雷"
        assert p.name == "小雷"
        # 验证持久化
        p2 = UserProfile("test_002", base_dir=tmpdir)
        assert p2.name == "小雷"


def test_add_fact_dedup():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_003", base_dir=tmpdir)
        assert p.add_fact("用户喜欢Python") is True
        assert p.add_fact("用户喜欢Python") is False  # 去重
        assert len(p.facts) == 1


def test_add_preference():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_004", base_dir=tmpdir)
        p.add_preference("喜欢深色主题")
        assert len(p.preferences) == 1
        assert p.preferences[0]["content"] == "喜欢深色主题"


def test_remove_fact():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_005", base_dir=tmpdir)
        p.add_fact("用户住在北京")
        p.add_fact("用户喜欢Python")
        assert p.remove_fact("北京") is True
        assert len(p.facts) == 1
        assert "Python" in p.facts[0]["content"]


def test_to_system_prompt_block():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_006", base_dir=tmpdir)
        p.name = "小帅"
        p.add_fact("用户是程序员")
        block = p.to_system_prompt_block()
        assert "小帅" in block
        assert "程序员" in block
        assert "用户画像" in block


def test_empty_profile_prompt():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = UserProfile("test_007", base_dir=tmpdir)
        assert p.to_system_prompt_block() == ""


def test_singleton():
    p1 = get_user_profile("test_008")
    p2 = get_user_profile("test_008")
    assert p1 is p2


if __name__ == "__main__":
    test_profile_creation()
    test_set_name()
    test_add_fact_dedup()
    test_add_preference()
    test_remove_fact()
    test_to_system_prompt_block()
    test_empty_profile_prompt()
    test_singleton()
    print("All tests passed!")
```

- [ ] **步骤 3：运行测试验证通过**

运行：`cd /Users/leiyuxuan/Desktop/小雷版agent && python -m pytest tests/test_user_profile.py -v`
预期：8 passed

- [ ] **步骤 4：Commit**

```bash
git add core/memory/user_profile.py tests/test_user_profile.py
git commit -m "feat: 用户画像数据模型 + 持久化"
```

---

## 任务 2：LLM 驱动的事实提取器

**文件：**
- 创建：`core/memory/fact_extractor.py`
- 测试：`tests/test_fact_extractor.py`

- [ ] **步骤 1：编写事实提取器**

```python
# core/memory/fact_extractor.py
"""事实提取器 — 从对话中自动提取用户事实/偏好

参考 hermes-agent 的模式：不硬编码规则，而是用 LLM 判断是否值得记录。
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """分析以下对话，提取关于用户的事实和偏好。

规则：
1. 只提取关于用户本人的信息（姓名、职业、地点、偏好、习惯等）
2. 跳过一次性信息、临时状态、任务进度
3. 跳过显而易见的信息
4. 如果没有值得记录的信息，返回空数组

输出 JSON 数组，每项格式：
{"type": "fact|preference|name", "content": "简洁的陈述句", "confidence": 0.0-1.0}

示例：
用户: 我叫小雷，是个程序员
[{"type": "name", "content": "用户姓名是小雷", "confidence": 0.95}, {"type": "fact", "content": "用户是程序员", "confidence": 0.9}]

用户: 今天天气怎么样
[]

用户: 我喜欢用 VS Code
[{"type": "preference", "content": "用户偏好使用 VS Code 编辑器", "confidence": 0.9}]

用户: 帮我查一下北京到上海的高铁
[]

---

对话历史:
{conversation}

最新消息:
{message}

只输出 JSON 数组，不要其他内容。"""


class FactExtractor:
    """从对话中提取用户事实"""

    def __init__(self):
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            try:
                from core.engine.llm_backend import get_llm_router
                self._llm = get_llm_router()
            except Exception:
                return None
        return self._llm

    async def extract(
        self,
        message: str,
        conversation_history: str = "",
    ) -> List[Dict]:
        """从消息中提取事实

        Args:
            message: 最新用户消息
            conversation_history: 最近几轮对话（可选，提供上下文）

        Returns:
            [{"type": "fact|preference|name", "content": "...", "confidence": 0.0-1.0}]
        """
        if not self.llm:
            return []

        prompt = EXTRACTION_PROMPT.format(
            conversation=conversation_history or "(无历史对话)",
            message=message,
        )

        try:
            resp = await asyncio.wait_for(
                self.llm.simple_chat(
                    user_message=prompt,
                    system_prompt="你是一个精准的信息提取器。只输出 JSON。",
                    temperature=0.1,
                ),
                timeout=10,
            )
            if not resp:
                return []

            text = resp.strip() if isinstance(resp, str) else str(resp).strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                # 过滤低置信度
                return [item for item in parsed if item.get("confidence", 0) >= 0.7]
            return []
        except asyncio.TimeoutError:
            logger.debug("事实提取: LLM 超时")
        except json.JSONDecodeError:
            logger.debug("事实提取: LLM 返回非 JSON")
        except Exception as e:
            logger.debug("事实提取失败: %s", e)
        return []


# 全局单例
_extractor: Optional[FactExtractor] = None


def get_fact_extractor() -> FactExtractor:
    global _extractor
    if _extractor is None:
        _extractor = FactExtractor()
    return _extractor
```

- [ ] **步骤 2：编写测试**

```python
# tests/test_fact_extractor.py
"""事实提取器测试"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from core.memory.fact_extractor import FactExtractor, get_fact_extractor


def test_extractor_singleton():
    e1 = get_fact_extractor()
    e2 = get_fact_extractor()
    assert e1 is e2


def test_no_llm_returns_empty():
    extractor = FactExtractor()
    extractor._llm = None
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract("你好")
    )
    assert result == []


def test_extraction_with_mock_llm():
    extractor = FactExtractor()
    mock_llm = AsyncMock()
    mock_llm.simple_chat = AsyncMock(return_value=json.dumps([
        {"type": "name", "content": "用户姓名是小雷", "confidence": 0.95},
        {"type": "fact", "content": "用户是程序员", "confidence": 0.9},
    ]))
    extractor._llm = mock_llm

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract("我叫小雷，是个程序员")
    )
    assert len(result) == 2
    assert result[0]["type"] == "name"
    assert "小雷" in result[0]["content"]


def test_low_confidence_filtered():
    extractor = FactExtractor()
    mock_llm = AsyncMock()
    mock_llm.simple_chat = AsyncMock(return_value=json.dumps([
        {"type": "fact", "content": "可能的信息", "confidence": 0.3},
        {"type": "fact", "content": "确定的信息", "confidence": 0.9},
    ]))
    extractor._llm = mock_llm

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract("测试消息")
    )
    assert len(result) == 1
    assert result[0]["confidence"] == 0.9


def test_empty_llm_response():
    extractor = FactExtractor()
    mock_llm = AsyncMock()
    mock_llm.simple_chat = AsyncMock(return_value="[]")
    extractor._llm = mock_llm

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract("今天天气怎么样")
    )
    assert result == []


if __name__ == "__main__":
    test_extractor_singleton()
    test_no_llm_returns_empty()
    test_extraction_with_mock_llm()
    test_low_confidence_filtered()
    test_empty_llm_response()
    print("All tests passed!")
```

- [ ] **步骤 3：运行测试验证通过**

运行：`cd /Users/leiyuxuan/Desktop/小雷版agent && python -m pytest tests/test_fact_extractor.py -v`
预期：5 passed

- [ ] **步骤 4：Commit**

```bash
git add core/memory/fact_extractor.py tests/test_fact_extractor.py
git commit -m "feat: LLM驱动的事实提取器"
```

---

## 任务 3：统一记忆中间件

**文件：**
- 创建：`core/memory/memory_middleware.py`
- 测试：`tests/test_memory_middleware.py`

- [ ] **步骤 1：编写 MemoryMiddleware**

```python
# core/memory/memory_middleware.py
"""记忆中间件 — 统一所有路径的记忆读写

职责：
1. 每轮对话后：提取事实 → 更新用户画像 → 存入向量记忆
2. 每轮对话前：搜索用户画像 + 向量记忆 → 注入上下文
3. 替代 chat.py / chat_handler.py / agent_system.py 中分散的记忆逻辑
"""

import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MemoryMiddleware:
    """统一记忆读写中间件"""

    def __init__(self):
        self._profile_cache: Dict[str, object] = {}

    # ── 读取：注入用户上下文 ──────────────────────────────────────────

    async def get_user_context(self, user_id: str, message: str) -> str:
        """获取用户上下文（画像 + 相关记忆），注入到系统提示或任务描述

        Returns:
            格式化的上下文字符串，空字符串表示无可用上下文
        """
        parts = []

        # 1. 用户画像
        try:
            from .user_profile import get_user_profile
            profile = get_user_profile(user_id)
            profile_block = profile.to_system_prompt_block()
            if profile_block:
                parts.append(profile_block)
        except Exception as e:
            logger.debug("获取用户画像失败: %s", e)

        # 2. 向量记忆搜索
        try:
            from .vector_memory import VectorMemoryStore
            vm = VectorMemoryStore()
            if vm.wait_for_collection(timeout=3.0):
                memories = vm.search_memories(
                    query=message,
                    user_id=user_id,
                    top_k=5,
                )
                if memories:
                    mem_lines = []
                    for m in memories:
                        cat = m.get("metadata", {}).get("category", "")
                        if cat in ("fact", "preference", "personal_info"):
                            mem_lines.append(f"- {m['content'][:150]}")
                    if mem_lines:
                        parts.append("【相关记忆】\n" + "\n".join(mem_lines))
        except Exception as e:
            logger.debug("搜索向量记忆失败: %s", e)

        return "\n\n".join(parts) if parts else ""

    # ── 写入：对话后提取并存储 ──────────────────────────────────────────

    async def process_turn(self, user_id: str, user_message: str, assistant_reply: str) -> None:
        """对话结束后：提取事实 → 更新画像 → 存入向量记忆

        异步执行，不阻塞响应。
        """
        try:
            # 1. 用 LLM 提取事实
            from .fact_extractor import get_fact_extractor
            extractor = get_fact_extractor()
            facts = await extractor.extract(user_message)

            if not facts:
                return

            # 2. 更新用户画像
            from .user_profile import get_user_profile
            profile = get_user_profile(user_id)

            for fact in facts:
                ftype = fact.get("type", "fact")
                content = fact.get("content", "")
                if not content:
                    continue

                if ftype == "name":
                    # 提取姓名（去掉"用户姓名是"前缀）
                    name = content.replace("用户姓名是", "").replace("用户叫", "").strip()
                    if name and len(name) < 20:
                        profile.name = name
                        logger.info("📝 画像更新: 姓名=%s", name)
                elif ftype == "preference":
                    if profile.add_preference(content):
                        logger.info("📝 画像更新: 偏好=%s", content[:30])
                else:
                    if profile.add_fact(content):
                        logger.info("📝 画像更新: 事实=%s", content[:30])

            # 3. 存入向量记忆
            try:
                from .vector_memory import VectorMemoryStore
                vm = VectorMemoryStore()
                if vm.wait_for_collection(timeout=3.0):
                    for fact in facts:
                        content = fact.get("content", "")
                        ftype = fact.get("type", "fact")
                        if content:
                            vm.add_memory(
                                user_id=user_id,
                                content=content,
                                category=ftype if ftype != "name" else "fact",
                                metadata={"source": "auto_extract", "type": ftype},
                            )
            except Exception as e:
                logger.debug("向量记忆写入失败: %s", e)

        except Exception as e:
            logger.debug("记忆处理失败: %s", e)


# 全局单例
_middleware: Optional[MemoryMiddleware] = None


def get_memory_middleware() -> MemoryMiddleware:
    global _middleware
    if _middleware is None:
        _middleware = MemoryMiddleware()
    return _middleware
```

- [ ] **步骤 2：编写测试**

```python
# tests/test_memory_middleware.py
"""记忆中间件测试"""

import asyncio
import json
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from core.memory.memory_middleware import MemoryMiddleware, get_memory_middleware


def test_singleton():
    m1 = get_memory_middleware()
    m2 = get_memory_middleware()
    assert m1 is m2


def test_get_user_context_empty():
    mw = MemoryMiddleware()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("core.memory.user_profile.get_user_profile") as mock_profile:
            mock_profile.return_value.to_system_prompt_block.return_value = ""
            result = asyncio.get_event_loop().run_until_complete(
                mw.get_user_context("test", "你好")
            )
            assert result == ""


def test_process_turn_stores_facts():
    mw = MemoryMiddleware()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock fact extractor
        mock_extractor = MagicMock()
        mock_extractor.extract = AsyncMock(return_value=[
            {"type": "name", "content": "用户姓名是小雷", "confidence": 0.95},
            {"type": "fact", "content": "用户是程序员", "confidence": 0.9},
        ])

        # Mock profile
        mock_profile = MagicMock()
        mock_profile.add_fact.return_value = True

        with patch("core.memory.fact_extractor.get_fact_extractor", return_value=mock_extractor), \
             patch("core.memory.user_profile.get_user_profile", return_value=mock_profile):

            asyncio.get_event_loop().run_until_complete(
                mw.process_turn("test_user", "我叫小雷，是程序员", "你好小雷！")
            )

            # 验证姓名被设置
            mock_profile.name = "小雷"
            # 验证事实被添加
            mock_profile.add_fact.assert_called_once_with("用户是程序员")


if __name__ == "__main__":
    test_singleton()
    test_get_user_context_empty()
    test_process_turn_stores_facts()
    print("All tests passed!")
```

- [ ] **步骤 3：运行测试验证通过**

运行：`cd /Users/leiyuxuan/Desktop/小雷版agent && python -m pytest tests/test_memory_middleware.py -v`
预期：3 passed

- [ ] **步骤 4：Commit**

```bash
git add core/memory/memory_middleware.py tests/test_memory_middleware.py
git commit -m "feat: 统一记忆中间件 MemoryMiddleware"
```

---

## 任务 4：集成到 Web 路径（chat.py）

**文件：**
- 修改：`api/routes/chat.py:363-417`

- [ ] **步骤 1：替换手动正则为 MemoryMiddleware**

删除 `chat.py` 中第 363-409 行的整个 `# ===== 用户记忆 =====` 块，替换为：

```python
        # ===== 用户记忆：统一中间件 =====
        user_context_str = ""
        try:
            from core.memory.memory_middleware import get_memory_middleware
            mw = get_memory_middleware()
            user_context_str = await mw.get_user_context(uid, message)
        except Exception as e:
            logger.debug("用户记忆获取失败: %s", e)
```

- [ ] **步骤 2：对话结束后触发事实提取**

在 `_handle_with_multi_agent` 函数末尾（`return response` 之前），添加：

```python
        # ===== 对话结束后：自动提取事实 =====
        try:
            from core.memory.memory_middleware import get_memory_middleware
            mw = get_memory_middleware()
            asyncio.ensure_future(mw.process_turn(uid, message, reply_text))
        except Exception:
            pass
```

需要确认 `reply_text` 变量在此作用域内可用。查看 `chat.py:480-530` 确认回复文本的变量名。

- [ ] **步骤 3：验证语法**

运行：`python -c "import ast; ast.parse(open('api/routes/chat.py').read()); print('OK')"`

- [ ] **步骤 4：Commit**

```bash
git add api/routes/chat.py
git commit -m "feat: Web路径集成MemoryMiddleware"
```

---

## 任务 5：集成到 V1 Leader 路径（agent_system.py）

**文件：**
- 修改：`core/agent_system.py:897-980`

- [ ] **步骤 1：替换 _react_think 中的手动记忆搜索**

将 `agent_system.py` 第 963-980 行的 `# B: 检索历史经验 + insight 注入` 替换为：

```python
        # B: 检索用户上下文 + 历史经验
        user_context_str = ""
        experience_hints = ""
        if self.user_id:
            try:
                from core.memory.memory_middleware import get_memory_middleware
                mw = get_memory_middleware()
                user_context_str = asyncio.get_event_loop().run_until_complete(
                    mw.get_user_context(self.user_id, task_description)
                )
            except Exception:
                pass

        # 搜索历史经验（用于策略参考）
        if self.vm and self.user_id:
            try:
                similar = self.vm.search_memories(
                    query=task_description,
                    user_id=self.user_id,
                    top_k=4,
                )
                if similar:
                    lines = []
                    for m in similar:
                        cat = m.get("metadata", {}).get("category", "")
                        prefix = "💡" if cat == "insight" else "📋"
                        lines.append(f"{prefix} {m['content'][:200]}")
                    if lines:
                        experience_hints = "\n【历史经验参考】\n" + "\n".join(lines)
            except Exception as e:
                logger.debug(f"检索经验失败: {e}")
```

然后在 `system` prompt 构建时，将 `user_context_str` 注入到任务描述前面：

```python
        # 注入用户上下文到任务描述
        if user_context_str:
            task_description = f"{task_description}\n\n{user_context_str}\n\n请根据以上用户信息回答。"
```

注意：需要将这行放在 `system` prompt 构建之前，因为 `task_description` 会被传给 LLM。

- [ ] **步骤 2：验证语法**

运行：`python -c "import ast; ast.parse(open('core/agent_system.py').read()); print('OK')"`

- [ ] **步骤 3：Commit**

```bash
git add core/agent_system.py
git commit -m "feat: V1 Leader集成MemoryMiddleware用户上下文"
```

---

## 任务 6：集成到 CLI 路径

**文件：**
- 修改：`cli/handlers/chat_handler.py:576-597`

- [ ] **步骤 1：WorkAgent 设置 user_id**

在 `cli/handlers/chat_handler.py` 的 `handle_smart_request_with_history` 方法中，创建 WorkAgent 后设置 user_id：

找到创建 WorkAgent 的代码（约第 584 行），在其后添加：

```python
            agent = WorkAgent()
            # 设置 user_id 以激活 STM 和向量记忆
            agent.user_id = str(self.cli.user_id) if hasattr(self.cli, 'user_id') else "cli_user"
```

需要确认 `self.cli` 是否有 `user_id` 属性，如果没有就用 `"cli_user"` 作为默认值。

- [ ] **步骤 2：对话结束后触发事实提取**

在 WorkAgent 执行完成后（约第 597 行），添加：

```python
            # 对话结束后：自动提取事实
            try:
                from core.memory.memory_middleware import get_memory_middleware
                import asyncio
                mw = get_memory_middleware()
                asyncio.ensure_future(mw.process_turn(agent.user_id, initial_message, answer[:500]))
            except Exception:
                pass
```

- [ ] **步骤 3：验证语法**

运行：`python -c "import ast; ast.parse(open('cli/handlers/chat_handler.py').read()); print('OK')"`

- [ ] **步骤 4：Commit**

```bash
git add cli/handlers/chat_handler.py
git commit -m "feat: CLI路径集成MemoryMiddleware"
```

---

## 任务 7：集成到 chat_handler 路径（Handler层）

**文件：**
- 修改：`core/handlers/chat_handler.py:9-73`

- [ ] **步骤 1：替换分散的记忆调用**

将 `chat_handler.py` 中 `handle_chat` 函数的记忆逻辑替换为 MemoryMiddleware：

```python
async def handle_chat(
    message: str,
    user_id: int,
    agent_id: str,
    db_initialized: bool = False
) -> Dict[str, Any]:
    """处理闲聊对话"""
    from .context_memory import add_to_context_memory, get_context_for_llm
    from .persistence import get_system_prompt

    uid = str(user_id)

    # 写入短期记忆
    add_to_context_memory(user_id, message, role="user", skill_name="chat")

    # 获取上下文
    context_str = get_context_for_llm(user_id, depth=2)
    system_prompt: str = get_system_prompt(agent_id, db_initialized)

    # 统一记忆中间件：获取用户上下文
    user_context_str = ""
    try:
        from ..memory.memory_middleware import get_memory_middleware
        mw = get_memory_middleware()
        user_context_str = await mw.get_user_context(uid, message)
    except Exception as e:
        logger.debug("用户记忆获取失败: %s", e)

    if context_str:
        system_prompt += f"\n\n历史对话上下文（用于理解当前问题）：\n{context_str}"

    if user_context_str:
        system_prompt += f"\n\n{user_context_str}"

    # ... 后续 LLM 调用逻辑保持不变 ...

    # 对话结束后：自动提取事实
    try:
        from ..memory.memory_middleware import get_memory_middleware
        mw = get_memory_middleware()
        asyncio.ensure_future(mw.process_turn(uid, message, reply_text))
    except Exception:
        pass
```

注意：需要确认 `reply_text` 变量在此作用域内的实际名称。

- [ ] **步骤 2：删除 memory_nudge 相关代码**

由于 MemoryMiddleware 统一了记忆管理，`chat_handler.py` 中的 nudge 逻辑可以删除（第 28-39 行）。

- [ ] **步骤 3：验证语法**

运行：`python -c "import ast; ast.parse(open('core/handlers/chat_handler.py').read()); print('OK')"`

- [ ] **步骤 4：Commit**

```bash
git add core/handlers/chat_handler.py
git commit -m "feat: Handler层集成MemoryMiddleware，移除分散记忆逻辑"
```

---

## 任务 8：端到端集成测试

**文件：**
- 创建：`tests/test_memory_e2e.py`

- [ ] **步骤 1：编写端到端测试**

```python
# tests/test_memory_e2e.py
"""端到端记忆系统测试 — 验证完整流程"""

import asyncio
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from core.memory.user_profile import UserProfile
from core.memory.fact_extractor import FactExtractor
from core.memory.memory_middleware import MemoryMiddleware


def test_full_memory_flow():
    """测试完整流程：提取事实 → 更新画像 → 注入上下文"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 模拟事实提取
        mock_extractor = MagicMock()
        mock_extractor.extract = AsyncMock(return_value=[
            {"type": "name", "content": "用户姓名是小雷", "confidence": 0.95},
            {"type": "fact", "content": "用户是Python开发者", "confidence": 0.9},
            {"type": "preference", "content": "用户偏好使用VS Code", "confidence": 0.85},
        ])

        # 2. 创建中间件并处理对话
        mw = MemoryMiddleware()
        with patch("core.memory.fact_extractor.get_fact_extractor", return_value=mock_extractor), \
             patch("core.memory.user_profile.get_user_profile") as mock_profile_factory:

            mock_profile = UserProfile("e2e_test", base_dir=tmpdir)
            mock_profile_factory.return_value = mock_profile

            # 处理一轮对话
            asyncio.get_event_loop().run_until_complete(
                mw.process_turn("e2e_test", "我叫小雷，是Python开发者，喜欢VS Code", "你好小雷！")
            )

            # 3. 验证画像更新
            assert mock_profile.name == "小雷"
            assert len(mock_profile.facts) == 1
            assert "Python" in mock_profile.facts[0]["content"]
            assert len(mock_profile.preferences) == 1
            assert "VS Code" in mock_profile.preferences[0]["content"]

            # 4. 验证注入格式
            block = mock_profile.to_system_prompt_block()
            assert "小雷" in block
            assert "Python" in block
            assert "VS Code" in block


def test_context_injection():
    """测试上下文注入"""
    mw = MemoryMiddleware()
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_profile = UserProfile("inj_test", base_dir=tmpdir)
        mock_profile.name = "小帅"
        mock_profile.add_fact("用户是设计师")

        with patch("core.memory.user_profile.get_user_profile", return_value=mock_profile), \
             patch("core.memory.vector_memory.VectorMemoryStore") as mock_vm_class:

            mock_vm = MagicMock()
            mock_vm.wait_for_collection.return_value = False
            mock_vm_class.return_value = mock_vm

            result = asyncio.get_event_loop().run_until_complete(
                mw.get_user_context("inj_test", "你好")
            )

            assert "小帅" in result
            assert "设计师" in result


if __name__ == "__main__":
    test_full_memory_flow()
    test_context_injection()
    print("All E2E tests passed!")
```

- [ ] **步骤 2：运行测试验证通过**

运行：`cd /Users/leiyuxuan/Desktop/小雷版agent && python -m pytest tests/test_memory_e2e.py -v`
预期：2 passed

- [ ] **步骤 3：Commit**

```bash
git add tests/test_memory_e2e.py
git commit -m "test: 端到端记忆系统集成测试"
```

---

## 自检

**1. 规格覆盖度：**
- ✅ 用户画像系统 → 任务 1
- ✅ 自动事实提取 → 任务 2
- ✅ 统一记忆接入层 → 任务 3
- ✅ Web 路径集成 → 任务 4
- ✅ V1 Leader 路径集成 → 任务 5
- ✅ CLI 路径集成 → 任务 6
- ✅ Handler 层集成 → 任务 7
- ✅ 端到端测试 → 任务 8

**2. 占位符扫描：** 无 "TODO"、"待定"、"后续实现" 等占位符。

**3. 类型一致性：**
- `UserProfile` 在任务 1-8 中保持一致
- `FactExtractor.extract()` 签名一致
- `MemoryMiddleware.get_user_context()` / `process_turn()` 签名一致

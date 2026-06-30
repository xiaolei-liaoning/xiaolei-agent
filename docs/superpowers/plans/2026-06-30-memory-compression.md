# 保存时记忆压缩 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在对话结束时提取结构化记忆存入索引，后续轮次只注入索引而非原始消息。

**架构：** MemoryMiddleware.on_think_start() 改为注入 MEMORY.md 索引 + 用户画像；on_finish() 追加 consolidate_session() 提取洞察。

**技术栈：** Python, LLM (DeepSeek), file-based .md 存储

---

### 任务 1：创建 consolidator.py

**文件：** 创建 `core/memory/consolidator.py`

- [ ] **步骤 1：编写 consolidator.py**

```python
"""会话结束时提取结构化记忆（保存时压缩）"""
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_MEMORY_BASE = Path.home() / ".小雷版小龙虾" / "memories"
_INDEX_NAME = "MEMORY.md"
_MAX_MEMORIES_PER_SESSION = 3

_SYSTEM_PROMPT = """\
你是一个记忆提取助手。分析这段对话，提取 0-3 条值得长期保存的关键信息。

只保存：
- 用户的个人事实、偏好、角色信息
- 行为反馈（做什么/不做什么）
- 项目上下文（非代码可推导的）

不保存：
- 代码模式、文件路径、架构
- git 历史、调试过程
- 临时任务状态

返回 JSON 格式：
{"memories": [{"name": "简短名称", "type": "fact|preference|experience|insight", "content": "一句话描述"}]}
没有值得保存的信息时返回 {"memories": []}"""


async def consolidate_session(
    user_id: str,
    user_message: str,
    assistant_reply: str,
) -> List[Dict]:
    """从一轮对话中提取结构化记忆并存入索引"""
    if len(user_message) < 20 and len(assistant_reply) < 20:
        return []

    memories = await _extract_memories(user_message, assistant_reply)
    if not memories:
        return []

    saved = []
    mem_dir = _MEMORY_BASE / user_id
    mem_dir.mkdir(parents=True, exist_ok=True)

    for mem in memories[: _MAX_MEMORIES_PER_SESSION]:
        name = mem.get("name", "").strip()
        content = mem.get("content", "").strip()
        mem_type = mem.get("type", "fact")
        if not name or not content:
            continue

        slug = _slugify(name)
        fp = mem_dir / f"{slug}.md"
        fp.write_text(
            f"---\nname: {name}\ntype: {mem_type}\n---\n\n{content}\n"
        )
        saved.append({"name": name, "content": content, "type": mem_type})

    _rebuild_index(user_id)
    return saved


async def _extract_memories(user_message: str, assistant_reply: str) -> List[Dict]:
    """调 LLM 提取结构化记忆"""
    try:
        from core.engine.llm_backend import LLM
        text = f"用户: {user_message[:1000]}\n助手: {assistant_reply[:1000]}"
        result = await LLM(
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        import json
        if isinstance(result, str):
            parsed = json.loads(result)
        elif isinstance(result, dict):
            parsed = result
        else:
            parsed = getattr(result, "__dict__", {})
        return parsed.get("memories", [])
    except Exception as e:
        logger.debug(f"consolidate session 提取失败: {e}")
        return []


def _slugify(name: str) -> str:
    s = name.lower().strip().replace(" ", "_")
    return "".join(c for c in s if c.isalnum() or c == "_")[:60]


def _rebuild_index(user_id: str) -> None:
    mem_dir = _MEMORY_BASE / user_id
    if not mem_dir.exists():
        return
    entries = sorted(mem_dir.glob("*.md"))
    lines = []
    for fp in entries:
        if fp.name == _INDEX_NAME:
            continue
        try:
            content = fp.read_text()
            name_line = ""
            body_preview = ""
            for line in content.splitlines():
                if line.startswith("name: "):
                    name_line = line[6:]
                elif line == "---" and name_line:
                    continue
            preview = ""
            body_start = content.find("---\n\n")
            if body_start > 0:
                raw = content[body_start + 5 :].strip()[:80]
                preview = raw.replace("\n", " ")
            if name_line:
                lines.append(f"- [{name_line}]({fp.name}) — {preview}")
        except Exception:
            continue
    index_path = mem_dir / _INDEX_NAME
    index_path.write_text("\n".join(lines) + ("\n" if lines else ""))


def load_index(user_id: str) -> str:
    """加载 MEMORY.md 索引内容"""
    index_path = _MEMORY_BASE / user_id / _INDEX_NAME
    if index_path.exists():
        return index_path.read_text().strip()
    return ""
```

- [ ] **步骤 2：Commit**

```bash
git add core/memory/consolidator.py
git commit -m "feat: add consolidate_session for write-time memory compression"
```

### 任务 2：修改 MemoryMiddleware

**文件：** 修改 `core/multi_agent_v2/agents/memory_middleware.py`

- [ ] **步骤 1：修改 on_think_start 注入索引 + 画像替代原始消息**

将第 62-88 行改为：

```python
    async def on_think_start(self, ctx: RunContext) -> None:
        """每轮注入记忆索引 + 用户画像（不含原始消息）"""
        user_id = self._get_user_id()
        parts = []

        # 1. 记忆索引
        try:
            from core.memory.consolidator import load_index
            index = load_index(user_id)
            if index:
                parts.append(f"[记忆索引]\n{index}")
        except Exception as e:
            logger.debug(f"加载记忆索引失败: {e}")

        # 2. 用户画像（简短）
        try:
            from core.memory.user_profile import get_user_profile
            profile = get_user_profile(user_id)
            p = profile.to_system_prompt_block()
            if p:
                parts.append(p)
        except Exception as e:
            logger.debug(f"加载用户画像失败: {e}")

        if parts:
            ctx.knowledge_context += (
                f"\n── 记忆上下文 ──\n" + "\n\n".join(parts) + "\n──"
            )
            total = sum(len(p) for p in parts)
            print(f"    \033[1;35m🧠 记忆: {total} 字符上下文已注入\033[0m")
        else:
            print(f"    \033[2;35m🧠 记忆: 无相关历史\033[0m")
```

- [ ] **步骤 2：修改 on_finish 追加 consolidate_session**

在第 137 行（process_turn 之后）追加：

```python
            try:
                from core.memory.consolidator import consolidate_session
                saved = await consolidate_session(user_id, ctx.task_description, final_answer)
                if saved:
                    logger.info(f"🧠 保存时压缩: {len(saved)} 条记忆已提取")
            except Exception as e:
                logger.debug(f"consolidate_session 失败: {e}")
```

完整 `on_finish` 方法改为：

```python
    async def on_finish(self, ctx: RunContext) -> None:
        """任务结束时：持久化记忆 + 保存时压缩"""
        final_answer = ctx.final_answer
        if not final_answer:
            return

        user_id = self._get_user_id()
        v1_mw = self._ensure_v1_mw()
        if v1_mw is not None:
            try:
                await v1_mw.process_turn(user_id, ctx.task_description, final_answer)
                print(f"    \033[1;35m🧠 记忆: 已持久化当前对话\033[0m")
            except Exception as e:
                logger.debug(f"V1 process_turn 失败: {e}")

        # 保存时压缩：从对话提取结构化记忆
        try:
            from core.memory.consolidator import consolidate_session
            saved = await consolidate_session(user_id, ctx.task_description, final_answer)
            if saved:
                logger.info(f"🧠 保存时压缩: {len(saved)} 条记忆已提取")
        except Exception as e:
            logger.debug(f"consolidate_session 失败: {e}")

        self._tool_experiences.clear()
        asyncio.ensure_future(self._after_finish_nudge(user_id, ctx))
```

- [ ] **步骤 3：Commit**

```bash
git add core/multi_agent_v2/agents/memory_middleware.py
git commit -m "feat: inject memory index + profile instead of raw messages; add consolidate to on_finish"
```

### 任务 3：添加 query_raw_memory 工具

**文件：** 修改 `core/multi_agent_v2/tools/tool_registry.py`

- [ ] **步骤 1：在 _handle_query_memory 后添加 handler**

在第 1435 行后添加：

```python
async def _handle_query_raw_memory(args: Dict) -> Dict:
    """查询短期记忆原始消息"""
    from core.memory.short_term_memory import get_memory_manager
    from core.multi_agent_v2.tools.tool_result import ok, err
    limit = min(args.get("limit", 10), 50)
    keyword = args.get("keyword", "")
    try:
        stm = get_memory_manager()
        context = stm.get_context("cli_user")
        if not context:
            return ok("暂无短期记忆")
        messages = []
        for msg in context[-limit:]:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if keyword and keyword.lower() not in content.lower():
                continue
            messages.append(f"[{role}] {content[:300]}")
        if not messages:
            return ok("未找到匹配的短期记忆")
        return ok(f"最近 {len(messages)} 条短期记忆:\n" + "\n".join(messages))
    except Exception as e:
        return err(f"读取短期记忆失败: {e}")
```

- [ ] **步骤 2：在 _SANDBOX_TOOL_DEFS 中添加 ToolDefinition**

在 query_memory 的 ToolDefinition（第 1673 行）后追加：

```python
    ToolDefinition(
        name="query_raw_memory",
        server=SERVER_BUILTIN,
        tags=["memory", "search"],
        description="查询短期记忆的原始对话消息。\n- 按时间倒序返回最近 N 条消息\n- 支持按关键词过滤\n- 适用于回顾刚才的对话详情",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "返回多少条最近消息，默认10，最大50"},
                "keyword": {"type": "string", "description": "可选关键词，只返回包含此词的消息"},
            },
        },
        handler=_handle_query_raw_memory,
    ),
```

- [ ] **步骤 3：Commit**

```bash
git add core/multi_agent_v2/tools/tool_registry.py
git commit -m "feat: add query_raw_memory tool for short-term memory drill-down"
```

### 任务 4：集成测试验证

- [ ] **步骤 1：编写测试 `tests/test_consolidator.py`**

```python
"""测试保存时压缩"""
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_slugify():
    from core.memory.consolidator import _slugify
    assert _slugify("Prefers Green Tea") == "prefers_green_tea"
    assert _slugify("Hello World! 123") == "hello_world_123"
    assert len(_slugify("a" * 100)) <= 60

def test_rebuild_index():
    from core.memory.consolidator import _rebuild_index, _MEMORY_BASE, _INDEX_NAME
    import tempfile
    import os
    
    # 使用临时目录替换 _MEMORY_BASE
    original = _MEMORY_BASE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            import core.memory.consolidator as c
            c._MEMORY_BASE = Path(tmp)
            user_dir = Path(tmp) / "test_user"
            user_dir.mkdir()
            
            # 创建一个记忆文件
            fp = user_dir / "test_memory.md"
            fp.write_text("---\nname: test\ntype: fact\n---\n\nuser is a developer\n")
            
            _rebuild_index("test_user")
            index = user_dir / _INDEX_NAME
            assert index.exists()
            content = index.read_text()
            assert "[test]" in content
    finally:
        c._MEMORY_BASE = original
```

- [ ] **步骤 2：运行测试**

```bash
python -m pytest tests/test_consolidator.py -v
```

预期：PASS

- [ ] **步骤 3：Commit**

```bash
git add tests/test_consolidator.py
git commit -m "test: add consolidator unit tests"
```

### 任务 5：端到端验证

- [ ] **步骤 1：启动 CLI 测试**

```bash
python cli.py 查看记忆
```

预期：注入的上下文应显示 `[记忆索引]` 而非 `[最近对话]` 原始消息

- [ ] **步骤 2：验证记忆文件被创建**

```bash
ls -la ~/.小雷版小龙虾/memories/cli_user/
cat ~/.小雷版小龙虾/memories/cli_user/MEMORY.md
```

# Workflow 模板靶向注入 实现计划

> **面向 AI 代理的工作者：** 使用 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让 LLM 生成 JS workflow 时只看到匹配模式的示例代码，而非全部 10 个模式的全量 prompt。

**架构：** 只改 `_llm_write_workflow` 一处。匹配阶段不变（只发匹配表+任务），拼接阶段改为从 `.workflow_prompt_template.md` 提取对应编号的代码段，不发送整个模板文件。

**技术栈：** Python 3.14+, 正则文本提取

**文件清单：**
- 修改：`cli/handlers/chat_handler.py:217-298`（`_llm_write_workflow` 方法）
- 不动：`workflows/.workflow_prompt_template.md`（模板内容不变）
- 不动：其他文件

---

### 任务 1：模板段落提取函数

**文件：**
- 修改：`cli/handlers/chat_handler.py`（新增 `_extract_pattern_sections` 方法）

- [ ] **步骤 1：在 ChatHandler 中添加 `_extract_pattern_sections` 方法**

```python
def _extract_pattern_sections(self, pattern_str: str) -> str:
    """从 .workflow_prompt_template.md 中提取匹配编号的代码段。
    
    支持多编号如 "⑤+②"，每段从 ### 标题 截取到下一个 --- 或文件末尾。
    """
    md_path = os.path.join(os.path.dirname(__file__), "..", "..", "workflows", ".workflow_prompt_template.md")
    md_path = os.path.abspath(md_path)
    if not os.path.exists(md_path):
        return ""
    
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 提取编号列表: "⑤+②" → ["⑤", "②"]
    nums = re.findall(r"[①-⑩]", pattern_str)
    if not nums:
        return ""
    
    # 按 ### 分割段落
    sections = re.split(r"\n(?=### \d)", content)
    
    results = []
    for section in sections:
        for num in nums:
            if section.startswith(f"### {num}") or section.lstrip().startswith(f"### {num}"):
                results.append(section.strip())
                break
    
    return "\n\n---\n\n".join(results)
```

添加到 `_validate_workflow_script` 方法之前。

- [ ] **步骤 2：运行快速手工验证**

```bash
cd /path/to/project && python3 -c "
import sys; sys.path.insert(0, '.')
from cli.handlers.chat_handler import ChatHandler
from cli.enhanced_cli import EnhancedCLI
from cli.logging_system import init_logger
init_logger()
cli = EnhancedCLI()
cli._init_session()
h = ChatHandler(cli)
r = h._extract_pattern_sections('⑤')
print(f'⑤ only: {len(r)} chars')
assert len(r) > 50
assert 'codegraph' in r.lower()

r2 = h._extract_pattern_sections('⑤+②')
print(f'⑤+②: {len(r2)} chars')
assert len(r2) > 100
print('OK')
"
```

预期：> 50 字符，包含 codegraph 关键词，多编号正确拼接。

- [ ] **步骤 3：Commit**

```bash
git add cli/handlers/chat_handler.py
git commit -m "feat: add _extract_pattern_sections for targeted template injection"
```

### 任务 2：重构 _llm_write_workflow 拼接逻辑

**文件：**
- 修改：`cli/handlers/chat_handler.py:245-252`

- [ ] **步骤 1：修改拼接阶段为靶向注入**

将：
```python
base_prompt = self._prompt_template.replace("{{task}}", task[:600])
prompt = (
    f"【匹配 Pattern: {matched_pattern}】\n"
    "严格按照该 pattern 的示例代码结构生成 workflow。\n"
    "独立模块必须用 parallel() 并行，禁止串行。\n\n"
    + base_prompt
)
```

改为：
```python
# ponytail: 靶向注入，只喂匹配编号的模板，不走全量 prompt
extracted = self._extract_pattern_sections(matched_pattern)
if extracted:
    rules = (
        "严格按照以下模板的结构生成 workflow。\n"
        "独立模块必须用 parallel() 并行，禁止串行。\n"
        "可以组合/嵌套多个模板来满足任务需求。\n"
    )
    prompt = (
        f"【匹配 Pattern: {matched_pattern}】\n"
        + rules
        + "\n参考模板：\n" + extracted + "\n\n"
        + "任务：" + task[:600]
    )
else:
    base_prompt = self._prompt_template.replace("{{task}}", task[:600])
    prompt = (
        f"【匹配 Pattern: {matched_pattern}】\n"
        "严格按照该 pattern 的示例代码结构生成 workflow。\n"
        "独立模块必须用 parallel() 并行，禁止串行。\n\n"
        + base_prompt
    )
```

同时导入 `re`（如果未导入）。

- [ ] **步骤 2：运行验证**

```bash
cd /path/to/project && python3 -c "
import sys; sys.path.insert(0, '.')
from cli.handlers.chat_handler import ChatHandler
from cli.enhanced_cli import EnhancedCLI
from cli.logging_system import init_logger
init_logger()
cli = EnhancedCLI()
cli._init_session()
h = ChatHandler(cli)

import asyncio
async def test():
    script = await h._llm_write_workflow('搜索百度热点')
    assert 'export const meta' in script
    assert 'export default async function' in script
    print(f'OK: script len={len(script)}')

asyncio.run(test())
"
```

预期：生成的 workflow 语法正确，包含 `export const meta` 和 `export default async function`。

- [ ] **步骤 3：端到端测试**

```bash
cd /path/to/project && python3 -m cli.cli /orchestrate 搜索百度热搜 2>&1 | grep -E '成功|耗时|排名'
```

预期：正常搜索并返回结果。

- [ ] **步骤 4：Commit**

```bash
git add cli/handlers/chat_handler.py
git commit -m "feat: refactor workflow template injection to target-only pattern sections"
```

### 任务 3：更新 prompt 模板（移除冗余）

**文件：**
- 修改：`workflows/.workflow_prompt_template.md`
- 修改：`cli/handlers/chat_handler.py`

- [ ] **步骤 1：在 prompt 模板头部添加多编号说明**

在 `workflows/.workflow_prompt_template.md` 的匹配表底部加一行：

```
| 多阶段任务 | 可返回多个编号，如 "⑤+②" |
```

加到 L20 附近。

- [ ] **步骤 2：验证多编号匹配生效**

```bash
cd /path/to/project && python3 -c "
import sys; sys.path.insert(0, '.')
from cli.handlers.chat_handler import ChatHandler
from cli.enhanced_cli import EnhancedCLI
from cli.logging_system import init_logger
init_logger()
cli = EnhancedCLI()
cli._init_session()
h = ChatHandler(cli)
r = h._extract_pattern_sections('⑤+②')
print(f'⑤+②: {len(r)} chars')
assert 'codegraph' in r and '串行' in r
print('OK: multi-pattern extraction works')
"
```

- [ ] **步骤 3：Commit**

```bash
git add workflows/.workflow_prompt_template.md
git commit -m "docs: add multi-pattern matching hint to template prompt"
```

### 任务 4：清理（删除未使用的代码）

- [ ] **步骤 1：检查 `_prompt_template` 和 `_load_prompt_template` 是否还用到**

这两个方法只在旧拼接逻辑中被调用。检查是否还有其他引用：

```bash
cd /path/to/project && grep -rn '_prompt_template\|_load_prompt_template' cli/ --include='*.py'
```

如果有其他引用要保留，如果没有则标记为可删除（但可以暂不删以保留回退路径）。

- [ ] **步骤 2：运行完整测试套件**

```bash
cd /path/to/project && python3 -m pytest tests/ -x -v 2>&1 | tail -20
```

预期：之前通过的测试全部仍然通过，不影响非 workflow 功能。

- [ ] **步骤 3：Commit**

```bash
git add .
git commit -m "chore: cleanup unused template code"
```

# 四项优化：LLM截断 / Expert角色映射 / 路径警告 / Tool调用顺序

**日期**: 2026-06-19
**项目**: 小雷版小龙虾 AI Agent (xiaolongxia-agent v3.4.0)
**状态**: 设计文档（待实施）

---

## 背景

在修复 import 路径错误并恢复 Expert 角色文件后，通过 `/run`/`/smart`/`/agents` 三项测试发现四个可优化点：
1. LLM 输出频繁被 `finish_reason=length` 截断（影响了 PvZ/八数码生成）
2. 搜索类任务匹配到的 Expert Persona 是"后端架构师"而非采集相关角色
3. `everything-claude-code` 路径不存在导致每次启动 warning
4. DeepSeek API 偶发 400 报错 `tool message order`

## 改动清单

所有改动遵循 Ponytail ultra 原则：最小改动，现有行为不变。

---

## 1. LLM max_tokens 全局放大

### 现状

`GLMBackend.chat()` 和 `LLMRouter.chat()` 默认 `max_tokens=2000`，代码生成任务经常被截断（`finish_reason=length`），截断部分内容丢失。

### 改动

| 文件 | 位置 | 旧值 | 新值 |
|------|------|------|------|
| `core/engine/llm_backend.py` | `_chat_impl` 签名 | `max_tokens=2000` | `max_tokens=4096` |
| 同上 | `chat()` 签名 | `max_tokens=2000` | `max_tokens=4096` |
| 同上 | `chat_stream()` 签名 | `max_tokens=2000` | `max_tokens=4096` |
| 同上 | `chat_structured()` 签名 | `max_tokens=2000` | `max_tokens=4096` |
| 同上 | `chat_structured_stream()` 签名 | `max_tokens=2000` | `max_tokens=4096` |
| 同上 | `LLMRouter` 同名方法 | 同上 | 同上 |

**不设 8192 的原因**：4096 对聊天已足够，且给输入留了一半空间（glm-4-flash / DeepSeek 上限均为 8192）。

### 文件

只动 `core/engine/llm_backend.py`。

---

## 2. Expert 角色映射优化

### 现状

`base_skills.py:42` 中 `web_scraper` 映射到 `["engineering", "marketing"]`。Engineering 类别第一个专家是"后端架构师"，LLM 选中了它。

### 改动

| 文件 | 行 | 旧值 | 新值 |
|------|----|------|------|
| `core/skills/base_skills.py` | 42 | `"web_scraper": ["engineering", "marketing"]` | `"web_scraper": ["engineering", "specialized"]` |

`specialized` 类别包含数据相关专家，比 `marketing` 更适合搜索/采集类任务。

### 文件

只动 `core/skills/base_skills.py`（一行）。

---

## 3. everything-claude-code 路径警告降级

### 现状

`guidance_skills.py:80` 在每个 session 启动时检查 `~/Desktop/claude/everything-claude-code-main/.agents/skills`，不存在则输出 `WARNING`。该目录已不存在，纯属噪音。

### 改动

| 文件 | 行 | 旧 | 新 |
|------|----|-----|-----|
| `core/guidance_skills.py` | 80 | `logger.warning(...)` | `logger.debug(...)` |

行为不变——路径不存在时仍然跳过 SKILL.md 加载，只是不再在终端刷 warning。

### 文件

只动 `core/guidance_skills.py`（一行）。

---

## 4. DeepSeek API tool 消息顺序清理

### 现状

ReAct 循环在上下文压缩/恢复时可能产生顺序错乱的消息序列（如多个 `tool_result` 无前置 `tool_calls`），DeepSeek API 要求严格的消息顺序，报 `400 invalid_request_error`。fallback 到 GLM 后正常。

### 改动

在 `core/engine/llm_backend.py` 的 `GLMBackend._chat_impl()` 方法开头插入消息过滤逻辑。过滤逻辑：
- 只有当前面有 `assistant` 角色且包含 `tool_calls` 时，才保留 `tool` 消息
- 孤立的 `tool` 消息（无前置 `tool_calls`）被丢弃
- 对正常消息序列无影响
- 即使过滤失败也不影响 fallback 链路

### 文件

只动 `core/engine/llm_backend.py`。

---

## 涉及文件总览

| 文件 | 改动类型 |
|------|----------|
| `core/engine/llm_backend.py` | max_tokens 默认值放大 + tool 消息顺序清理 |
| `core/skills/base_skills.py` | Expert 映射改一行 |
| `core/guidance_skills.py` | warning → debug 降级 |

共 **3 个文件**，变更简单、互不依赖，可全部在一次 commit 中完成。

---

## 验证方法

| 项目 | 验证方式 |
|------|----------|
| max_tokens | 运行 `/smart "生成长代码"`，观察截断次数减少 |
| Expert 映射 | 运行 `/smart "搜索百度热搜"`，观察 `👤 Expert:` 不再显示"后端架构师" |
| 路径警告 | 启动 CLI，确认无 `everything-claude-code` WARNING |
| tool 顺序 | 反复运行复杂任务，确认无 DeepSeek 400 报错 |

# 系统稳定性修复设计

**版本**: 1.0  
**日期**: 2026-06-30  
**状态**: 设计草案  

## 概述

修复小雷版小龙虾 AI Agent v3.4.0 中发现的 4 个关键稳定性问题：
1. 向量检索错误（最严重）
2. MCP 服务器连接失败
3. LLM JSON 解析失败
4. 搜索引擎返回 0 结果

## 修复 1：向量检索修复

### 问题根因
- `LocalEmbeddingFunction` 不是 `chromadb.EmbeddingFunction` 子类
- ChromaDB 内部调用 `.dimensionality` 属性时得到 dict
- `len()` 被调用在 int 上
- 文件：`core/memory/vector_memory.py`

### 修复方案
1. `LocalEmbeddingFunction` 继承 `chromadb.api.types.EmbeddingFunction`
2. 添加 `dimensionality` 属性返回 768
3. `__call__` 添加输入验证，确保 `List[List[float]]` 返回类型
4. 修复空输入边界情况

### 修改文件
- `core/memory/vector_memory.py`

### 验证
- `pytest tests/test_vector_memory.py`

## 修复 2：MCP 连接修复

### 问题根因（5 个）
| 问题 | 影响 |
|------|------|
| stderr 从不消费 | 管道缓冲区满，进程阻塞 |
| 无过期连接清理 | 死进程永久占用 |
| 超时锁竞争 | 一个超时阻塞所有请求 |
| `npx` 进程创建超时太短 | npm 下载超时 |
| Request ID 复用 | 响应混淆 |

### 修复方案
1. **stderr 消费**: `asyncio.create_task` 异步读取 stderr 到日志缓冲
2. **连接清理**: 重试 3 次失败后调用 `_cleanup_connection`，标记 `self._connections[name] = None`
3. **锁优化**: 锁获取设置超时，超时后释放
4. **npx 超时**: 从 10s 提升到 60s，添加 `process_timeout` 配置
5. **Request ID**: 递增 ID（`self._request_counter`），避免响应混淆

### 修改文件
- `core/mcp/mcp_client.py`

### 验证
- 启动系统 → 检查 MCP 连接日志
- 模拟 stderr 满 → 验证消费
- 模拟超时 → 验证重试和清理

## 修复 3：LLM JSON 解析失败

### 问题根因
- LLM 返回非 JSON 格式普通文本，`json.loads` 失败
- 重试仅重试同一请求，不调整 prompt

### 修复方案
1. JSON 解析失败时，用 LLM 提取 JSON（prompt：`"从中提取 JSON"`）
2. 仍失败则生成默认响应，而非崩溃
3. prompt 中添加更明确的 JSON 格式约束

### 修改文件
- `core/agent_system.py`

## 修复 4：搜索引擎返回 0 结果

### 问题根因（两层）
1. **反爬虫阻止**：百度对服务器端请求返回验证码/空白页，无 cookie 持久化且缺少关键标头
2. **解析逻辑脆弱**：`soup.find_all('h3')` 定位不准确，百度摘要使用 `<span class="c-abstract">` 而非 `<p>` 标签
3. **工厂优先级错误**：`BaiduSearch` 排第一且永不抛异常，`DuckDuckGoSearch` 永远不被尝试

### 修复方案
1. **修复 BaiduSearch 解析逻辑**
   - 改用 `.result.c-container` CSS 选择器
   - 摘要从 `<span class="c-abstract">` 提取
   - 添加基本 cookie 管理
2. **调整工厂优先级**：先尝试 `duckduckgo` → `bing` → `baidu`
3. **添加详细搜索失败日志**

### 修改文件
- `core/search/search_engine_factory.py`

### 验证
- 发送搜索请求 → 检查是否返回结果
- 模拟 Baidu 失败 → 验证 DuckDuckGo 回退

## 实施顺序
1. Fix 1：向量检索（核心功能）
2. Fix 2：MCP 连接（工具调用）
3. Fix 3：LLM JSON 解析
4. Fix 4：搜索引擎

## 回滚策略
- 每个 fix 独立提交，便于回滚
- 修复后运行完整测试套件

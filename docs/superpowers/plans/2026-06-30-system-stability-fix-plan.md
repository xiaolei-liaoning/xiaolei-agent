# 系统稳定性修复 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 4 个关键稳定性问题：向量检索错误、MCP 连接失败、LLM JSON 解析失败、搜索引擎返回 0 结果。

**架构：** 渐进式修复，每个 fix 独立可测试，按优先级顺序实施。

**技术栈：** chromadb 1.5.9, asyncio, JSON-RPC, bs4

---

### 任务 1：Fix 1 - 向量检索修复

**文件：**
- 修改：`core/memory/vector_memory.py:89-149`
- 测试：`tests/test_vector_memory_fix.py`

- [ ] **步骤 1：编写失败的测试**

```python
import pytest
from core.memory.vector_memory import LocalEmbeddingFunction

def test_local_embedding_is_chromadb_compatible():
    """验证 LocalEmbeddingFunction 满足 ChromaDB EmbeddingFunction 协议"""
    emb_fn = LocalEmbeddingFunction()
    # 必须可调用，接受 List[str] 返回 List[List[float]]
    result = emb_fn(["hello world"])
    assert isinstance(result, list)
    assert all(isinstance(v, list) for v in result)
    assert all(isinstance(x, float) for v in result for x in v)
    assert len(result[0]) == 768  # DIM

def test_local_embedding_has_dimensionality():
    """必须包含 dimensionality 属性供 ChromaDB 使用"""
    emb_fn = LocalEmbeddingFunction()
    assert hasattr(emb_fn, "dimensionality")
    assert emb_fn.dimensionality == 768

def test_local_embedding_empty_input():
    """空输入必须返回 []"""
    emb_fn = LocalEmbeddingFunction()
    assert emb_fn([]) == []
    assert emb_fn(None) == []
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_vector_memory_fix.py -v`
预期：FAIL，报错 "dimensionality not defined"

- [ ] **步骤 3：实现修复**

同时给 `SentenceTransformerEmbeddingFunction` 添加 `dimensionality` 属性（第 236 行附近）：

```python
@property
def dimensionality(self) -> int:
    """Chromadb 需要的向量维度属性"""
    return self.model_config["dim"]
```

测试也覆盖 `SentenceTransformerEmbeddingFunction`：

```python
def test_sentence_transformer_has_dimensionality():
    emb_fn = SentenceTransformerEmbeddingFunction(model_type="local")
    assert hasattr(emb_fn, "dimensionality")
    assert emb_fn.dimensionality == 768
```

```python
# ponytail: 不继承 chromadb.EmbeddingFunction（版本兼容性），通过 duck typing 满足协议
class LocalEmbeddingFunction:
    """本地固定维度哈希 Embedding（离线，永不联网）"""
    
    DIM = 768

    def __init__(self):
        self._dimension = self.DIM

    @property
    def dimensionality(self) -> int:
        """Chromadb 需要此属性来验证向量维度"""
        return self.DIM

    def __call__(self, input):
        if input is None:
            return []
        if not isinstance(input, list):
            input = [input]
        if not input:
            return []
        vectors = []
        for text in input:
            if not isinstance(text, str):
                text = str(text)
            vec = [0.0] * self.DIM
            tokens = self._tokenize(text)
            if not tokens:
                vectors.append(vec)
                continue
            for token in tokens:
                idx = self._hash_token(token)
                sgn = self._hash_sign(token)
                vec[idx] += sgn
            norm = math.sqrt(sum(x * x for x in vec))
            if norm > 0:
                vec = [x / norm for x in vec]
            vectors.append(vec)
        return vectors

    def embed_query(self, input=None, text=None, **kwargs):
        t = input if input is not None else text
        if isinstance(t, list):
            t = t[0] if t else ""
        result = self([t]) if t else [[0.0] * self.DIM]
        return result[0]
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_vector_memory_fix.py -v`
预期：PASS

- [ ] **步骤 5：修复 `add_memory` 类型安全性**

在 `add_memory`（约第 455 行）中添加 `content` 类型转换：

```python
def add_memory(self, user_id: str, content: str, category: str = "general"):
    content = str(content)  # 确保是 str，避免 int 传入 ChromaDB 导致 len() 失败
```

在 `_flush_buffer`（约第 510 行）中也确保：

```python
docs = [str(item[1]) for item in self._memory_buffer]
```

测试：

```python
def test_add_memory_handles_int_content():
    store = VectorMemoryStore(...)
    mem_id = store.add_memory("test_user", 12345, "general")  # int content
    assert mem_id is not None
```

- [ ] **步骤 6：Commit**

```bash
git add core/memory/vector_memory.py tests/test_vector_memory_fix.py
git commit -m "fix: vector_memory LocalEmbeddingFunction chromadb compat + int-safe add_memory"
```

---

### 任务 2：Fix 2 - MCP 连接修复

**文件：**
- 修改：`core/mcp/mcp_client.py:302-400`

- [ ] **步骤 1：修复 stderr 消费（添加 background task）**

```python
async def _create_process(self, name: str) -> asyncio.subprocess.Process:
    config = self._server_configs.get(name)
    if not config:
        raise ValueError(f"服务器 '{name}' 未配置")
    proc_env = None
    if config.get("env"):
        proc_env = os.environ.copy()
        proc_env.update(config["env"])
    process_timeout = config.get("process_timeout", 60.0)  # 默认 60s
    process = await asyncio.wait_for(
        asyncio.create_subprocess_exec(
            config["command"],
            *config["args"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config["cwd"],
            env=proc_env,
        ),
        timeout=process_timeout,
    )
    # 异步消费 stderr，防止管道缓冲区满导致进程阻塞
    asyncio.create_task(self._consume_stderr(name, process))
    return process

async def _consume_stderr(self, name: str, process: asyncio.subprocess.Process):
    """异步读取并记录 stderr，防止管道缓冲区满"""
    try:
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            logger.debug(f"[mcp:{name}] {line.decode().rstrip()}")
    except Exception as e:
        logger.debug(f"[mcp:{name}] stderr consumer 结束: {e}")
```

- [ ] **步骤 2：添加过期连接清理**

修改 `_send_request_with_retry`，失败后清理连接：

```python
async def _send_request_with_retry(
    self,
    process: asyncio.subprocess.Process,
    method: str,
    params: Optional[dict] = None,
    request_id: int = 1,
    server_name: str = "",
) -> Optional[dict]:
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await self._send_request(process, method, params, request_id, server_name=server_name)
        except (ConnectionError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"请求重试 {attempt + 1}/{_MAX_RETRIES}: {method} "
                    f"(等待 {delay:.1f}s, 错误: {e})"
                )
                await asyncio.sleep(delay)
    # 最后重试失败后清理连接
    logger.error(f"请求失败（已达最大重试次数）: {method}: {last_error}")
    await self._cleanup_connection(server_name)
    return None
```

- [ ] **步骤 3：锁超时优化**

```python
async def _send_request(self, ...):
    lock = self._get_server_lock(server_name)
    try:
        await asyncio.wait_for(lock.acquire(), timeout=35.0)
    except asyncio.TimeoutError:
        logger.error(f"[mcp:{server_name}] 锁获取超时")
        return None
    try:
        # 原有请求逻辑
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params
        request_str = json.dumps(request) + "\n"
        process.stdin.write(request_str.encode())
        await process.stdin.drain()
        response_line = await asyncio.wait_for(
            process.stdout.readline(), timeout=30.0
        )
        return json.loads(response_line.decode()) if response_line else None
    finally:
        lock.release()
```

- [ ] **步骤 4：Request ID 递增**

添加 `self._request_counter = {}` 在 `__init__`，每个 server 独立计数：

```python
# 在 __init__ 中
self._request_counter: Dict[str, int] = {}

def _get_request_id(self, server_name: str) -> int:
    counter = self._request_counter.get(server_name, 0) + 1
    self._request_counter[server_name] = counter
    return counter
```

然后修改所有 `request_id=2` 为 `request_id=self._get_request_id(server_name)`。

- [ ] **步骤 5：Commit**

```bash
git add core/mcp/mcp_client.py
git commit -m "fix: mcp stderr consumption, connection cleanup, lock timeout, request id"
```

---

### 任务 3：Fix 3 - LLM JSON 解析失败

**文件：**
- 修改：`core/agent_system.py:146-173`

- [ ] **步骤 1：添加 JSON 提取兜底逻辑**

修改 `_llm_json` 函数，在两次尝试失败后尝试用 LLM 提取 JSON：

```python
async def _llm_json(system_prompt: str, user_message: str, max_tokens: int = 500) -> Dict:
    """调用 LLM 并返回解析后的 JSON（含 1 次重试 + 提取兜底）"""
    last_error = None
    for attempt in range(2):
        try:
            router = _get_llm_router()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            async with _llm_semaphore:
                response = await router.chat(messages, temperature=0.7, max_tokens=max_tokens)
            cleaned = (response or "").strip().strip("```json").strip("```").strip()
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_error = str(e)
            if attempt == 0:
                logger.warning(f"LLM JSON 解析失败，重试中: {e}")
                user_message += f"\n\n（注意：上次返回的 JSON 格式无效，错误: {e}。请确保只输出有效 JSON。）"
            else:
                logger.warning(f"LLM JSON 解析重试仍失败: {e}")
        except Exception as e:
            logger.warning(f"LLM 调用/解析失败: {e}/{e.__class__.__name__}")
            last_error = str(e)
            if attempt == 0:
                user_message += f"\n\n（注意：上次 LLM 调用失败: {e}。请重试。）"
                continue
    # 兜底：尝试用 LLM 提取 JSON
    try:
        router = _get_llm_router()
        extract_prompt = f"从以下文本中提取 JSON 对象并返回（仅返回 JSON）：\n\n{user_message}"
        messages = [
            {"role": "system", "content": "你是一个 JSON 提取器，只输出 JSON 格式。"},
            {"role": "user", "content": extract_prompt},
        ]
        async with _llm_semaphore:
            response = await router.chat(messages, temperature=0.3, max_tokens=max_tokens)
        cleaned = (response or "").strip().strip("```json").strip("```").strip()
        return json.loads(cleaned)
    except Exception:
        pass
    logger.warning(f"LLM JSON 解析最终失败: {last_error}")
    return {}
```

- [ ] **步骤 2：Commit**

```bash
git add core/agent_system.py
git commit -m "fix: add json extraction fallback for llm parse failure"
```

---

### 任务 4：Fix 4 - 搜索引擎返回 0 结果

**文件：**
- 修改：`core/search/search_engine_factory.py:57-107, 212-225`

- [ ] **步骤 1：修复 BaiduSearch 解析逻辑**

```python
class BaiduSearch(BaseSearchEngine):
    """百度搜索（国内用户使用）"""
    
    def __init__(self):
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        self._session = None
    
    def _get_session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update(self._headers)
        return self._session
    
    def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """执行百度搜索"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            # ponytail: 基本 session 复用 + cookie，完整反爬需要 Playwright
            session = self._get_session()
            url = f"https://www.baidu.com/s?wd={requests.utils.quote(query)}&rn={num_results}"
            response = session.get(url, headers=self._headers, timeout=15)
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # 使用稳定的 CSS 选择器
            for container in soup.select('.result.c-container')[:num_results]:
                h3 = container.find('h3')
                if not h3:
                    continue
                link = h3.find('a')
                if not link:
                    continue
                title = h3.get_text(strip=True)
                link_url = link.get('href', '')
                
                # 摘要从 span.c-abstract 提取
                abstract = container.select_one('.c-abstract')
                snippet = abstract.get_text(strip=True)[:500] if abstract else ''
                
                results.append({
                    "title": title,
                    "url": link_url,
                    "snippet": snippet,
                    "source": "baidu"
                })
            
            logger.info(f"百度搜索成功: {len(results)} 个结果")
            if not results:
                logger.warning(f"百度搜索返回 0 个结果, 响应长度: {len(response.text)}")
            return results
        
        except ImportError:
            logger.error("请安装 requests 和 beautifulsoup4: pip install requests beautifulsoup4")
            return []
        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
            return []
```

- [ ] **步骤 2：调整工厂优先级，DuckDuckGo 优先**

```python
@classmethod
def create_with_fallback(cls) -> BaseSearchEngine:
    # ponytail: duckduckgo 优先使用库，baidu 解析脆弱
    for engine_type in ["duckduckgo", "bing", "baidu"]:
        try:
            engine = cls.create(engine_type)
            # 添加连通性检查延迟初始化
            logger.info(f"尝试搜索引擎: {engine_type}")
            return engine
        except Exception as e:
            logger.warning(f"搜索引擎 {engine_type} 不可用: {e}")
    # 终极兜底
    return FallbackSearch()
```

- [ ] **步骤 3：Commit**

```bash
git add core/search/search_engine_factory.py
git commit -m "fix: improve baidu parsing, prefer duckduckgo in factory"
```

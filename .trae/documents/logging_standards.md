# 日志级别规范

## 原则

1. **DEBUG** - 开发调试用，生产环境禁用
2. **INFO** - 正常运行流程，记录关键操作
3. **WARNING** - 可恢复的错误，需要关注但不需要立即处理
4. **ERROR** - 不可恢复的错误，需要记录和调查
5. **CRITICAL** - 系统级严重错误，可能影响核心功能

---

## 错误级别规范

### WARNING（警告）

适用于：可恢复的错误、异常情况但系统能继续运行

| 场景 | 示例 |
|------|------|
| 超时 | `logger.warning(f"请求超时: {url}, 正在重试...")` |
| 网络波动 | `logger.warning("网络连接不稳定，尝试重新连接")` |
| 限流 | `logger.warning("API限流，降低请求频率")` |
| 参数不完整 | `logger.warning(f"缺少参数: {param}, 使用默认值")` |
| 缓存未命中 | `logger.warning("缓存过期，重新获取数据")` |
| 部分失败 | `logger.warning(f"部分任务失败: {failed}/{total}")` |

### ERROR（错误）

适用于：操作失败、需要人工干预的错误

| 场景 | 示例 |
|------|------|
| 连接失败 | `logger.error(f"数据库连接失败: {e}")` |
| 认证失败 | `logger.error(f"认证失败: {username}")` |
| 权限不足 | `logger.error(f"权限不足: {user}, 操作: {action}")` |
| 文件不存在 | `logger.error(f"配置文件不存在: {path}")` |
| 解析失败 | `logger.error(f"JSON解析失败: {content[:50]}...")` |
| 重试耗尽 | `logger.error(f"重试{MAX_RETRIES}次后仍然失败: {url}")` |

### CRITICAL（严重）

适用于：系统级故障、可能导致数据丢失或安全问题

| 场景 | 示例 |
|------|------|
| 数据库崩溃 | `logger.critical("数据库连接池耗尽，系统无法继续")` |
| 安全漏洞 | `logger.critical(f"检测到未授权访问: {ip}")` |
| 数据损坏 | `logger.critical("关键数据损坏，启动恢复流程")` |

---

## 错误日志格式

```
[错误类型] 错误消息 | 额外信息 | 模块.函数
```

示例：
```
[TimeoutError] 请求超时: https://api.example.com, 正在重试... | 重试 2/3 | core.web_client.fetch
[ConnectionError] 数据库连接失败: too many connections | 连接池: 100/100 | core.db.session
```

---

## 错误恢复机制

### 1. 自动重试

使用 `@retry_on_error` 装饰器：

```python
@retry_on_error(max_retries=3, delay=1.0, backoff=2.0)
async def fetch_data(url: str):
    ...
```

### 2. 熔断器

使用 `CircuitBreaker` 防止故障扩散：

```python
breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
result = await breaker.call(dangerous_function)
```

### 3. 优雅降级

使用 `ErrorRecovery.graceful_degrade`：

```python
result = ErrorRecovery.graceful_degrade(error, default_value={})
```

---

## 禁止行为

1. ❌ 所有错误都用 `logger.error`
2. ❌ 用 `print` 代替日志
3. ❌ 异常被静默吞掉（无任何日志）
4. ❌ 敏感信息写入日志（密码、Token等）
5. ❌ 日志中出现中文（保持英文便于分析）

# 自我校验系统 - 快速参考

## 🚀 5分钟快速上手

### 1. 安装与启动

```bash
# 进入项目目录
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent

# 启动服务
python main.py
```

### 2. 第一次调用（cURL）

```bash
curl -X POST http://localhost:8001/api/v1/self-check/check \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "什么是量子计算？",
    "pass_score": 80,
    "max_retry": 3
  }'
```

### 3. Python代码调用

```python
import asyncio
from core.self_check_middleware import SelfCheckMiddleware
from core.llm_backend import get_llm_router

async def main():
    # 创建中间件
    checker = SelfCheckMiddleware(pass_score=80, max_retry=3)
    llm_router = get_llm_router()
    
    # 定义生成函数
    async def generate(query: str, context=None) -> str:
        return await llm_router.simple_chat(query, temperature=0.7)
    
    # 执行自检
    result = await checker.check_and_optimize(
        user_query="什么是量子计算？",
        generate_func=generate
    )
    
    print(f"得分: {result.score}")
    print(f"答案: {result.answer[:200]}...")

asyncio.run(main())
```

---

## 📊 核心API速查

### 执行自检

```
POST /api/v1/self-check/check
```

**请求体**:
```json
{
  "user_query": "你的问题",
  "pass_score": 80,
  "max_retry": 3,
  "temperature": 0.7
}
```

**响应**:
```json
{
  "success": true,
  "answer": "答案内容",
  "score": 85,
  "retry_count": 1,
  "is_passed": true,
  "history": [...],
  "total_time": 5.23
}
```

### 获取统计

```
GET /api/v1/self-check/stats
```

### 批量处理

```
POST /api/v1/self-check/batch
```

**请求体**:
```json
{
  "queries": ["问题1", "问题2", "问题3"],
  "pass_score": 80,
  "max_retry": 2
}
```

---

## ⚙️ 配置速查表

### 场景推荐配置

| 场景 | pass_score | max_retry | 说明 |
|------|-----------|-----------|------|
| 日常对话 | 75-80 | 2 | 快速响应 |
| 知识问答 | 80-85 | 3 | 平衡质量 |
| 代码生成 | 85-90 | 3-4 | 严格要求 |
| 数学计算 | 90-95 | 3-4 | 确保准确 |
| 专业咨询 | 90-95 | 4-5 | 最高标准 |

### 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 事实准确性 | 40分 | 信息真实可靠 |
| 逻辑通顺度 | 30分 | 推理清晰合理 |
| 贴合问题 | 20分 | 直接回答问题 |
| 无幻觉编造 | 10分 | 无虚构内容 |

---

## 💡 常用代码片段

### 集成到Agent

```python
class MyAgent:
    def __init__(self):
        self.checker = SelfCheckMiddleware(pass_score=85)
    
    async def process(self, query: str) -> str:
        result = await self.checker.check_and_optimize(
            user_query=query,
            generate_func=self.generate_answer
        )
        return result.answer if result.is_passed else result.answer
```

### 场景化配置

```python
SCENARIOS = {
    "code": {"pass_score": 85, "max_retry": 3},
    "math": {"pass_score": 90, "max_retry": 3},
    "chat": {"pass_score": 80, "max_retry": 2},
}

def get_checker(scenario: str):
    config = SCENARIOS.get(scenario, SCENARIOS["chat"])
    return SelfCheckMiddleware(**config)
```

### 自定义提示词

```python
CUSTOM_PROMPT = """
你是评审专家，请打分（满分100，合格线{pass_score}）。

评分维度：
1. 准确性 40分
2. 逻辑性 30分
3. 相关性 20分
4. 真实性 10分

输出格式：
得分：xx
问题：xxx
优化建议：xxx

用户问题：{user_query}
待评测内容：{content}
"""

result = await checker.check_and_optimize(
    user_query=query,
    generate_func=generate,
    custom_prompt_template=CUSTOM_PROMPT
)
```

### 错误处理

```python
try:
    result = await checker.check_and_optimize(...)
    if not result.is_passed:
        logger.warning(f"未通过，得分: {result.score}")
except Exception as e:
    logger.error(f"自检失败: {e}")
    # 降级处理
    answer = await llm_router.simple_chat(query)
```

---

## 🔍 调试技巧

### 查看详细日志

```python
# 启用详细日志
checker = SelfCheckMiddleware(enable_logging=True)

# 查看每轮迭代
for round_info in result.history:
    print(f"第{round_info['round']}轮: 得分={round_info['score']}")
    print(f"  问题: {round_info['problems']}")
    print(f"  建议: {round_info['suggestions']}")
```

### 监控统计

```python
stats = checker.get_stats()
print(f"总检查数: {stats['total_checks']}")
print(f"通过率: {stats['pass_rate']}%")
print(f"平均重试: {stats['avg_retry_count']}次")
```

### 性能测试

```python
import time

start = time.time()
result = await checker.check_and_optimize(...)
elapsed = time.time() - start

print(f"耗时: {elapsed:.2f}秒")
print(f"得分: {result.score}")
print(f"重试: {result.retry_count}次")
```

---

## ❓ 常见问题

### Q1: 如何选择合适的合格线？

**A**: 根据场景重要性选择：
- 一般对话：75-80分
- 重要任务：85-90分
- 关键业务：90-95分

### Q2: 自检太慢怎么办？

**A**: 
1. 减少max_retry（如从3改为2）
2. 降低pass_score（如从85改为80）
3. 使用更快的模型（glm-4-flash）

### Q3: 如何提高通过率？

**A**:
1. 优化系统提示词
2. 降低合格线
3. 增加重试次数
4. 使用更强大的模型

### Q4: 能否关闭自检？

**A**: 可以，直接调用LLM而不经过中间件：

```python
# 不使用自检
answer = await llm_router.simple_chat(query)

# 使用自检
result = await checker.check_and_optimize(...)
answer = result.answer
```

---

## 📚 更多资源

- **完整文档**: [SELF_CHECK_SYSTEM_GUIDE.md](./SELF_CHECK_SYSTEM_GUIDE.md)
- **测试示例**: [tests/test_self_check_middleware.py](../tests/test_self_check_middleware.py)
- **API文档**: http://localhost:8001/docs

---

**版本**: 1.0.0  
**更新**: 2026-04-28

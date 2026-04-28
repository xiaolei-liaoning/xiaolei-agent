# 自我校验与循环迭代评分系统 - 完整使用指南

## 📋 目录

- [概述](#概述)
- [核心特性](#核心特性)
- [快速开始](#快速开始)
- [API 使用](#api-使用)
- [代码集成](#代码集成)
- [配置说明](#配置说明)
- [最佳实践](#最佳实践)
- [性能优化](#性能优化)
- [故障排查](#故障排查)

---

## 概述

**自我校验与循环迭代评分系统**是一个通用的大模型输出质量保障中间件，采用"自我校验 + 循环迭代打分 + 阈值放行"机制，完美解决大模型「胡说、错答、不自检」的致命问题。

### 核心逻辑

```
用户问题
    ↓
【主生成模型】→ 产出初始答案
    ↓
【评审打分模型】
   - 评分：0~100
   - 指出问题
    ↓
分数 ≥ 合格阈值？
✅ 是 → 输出答案
❌ 否 → 带着问题反馈，回到主模型重新生成
（限制最大循环次数，防止死循环）
```

### 适用场景

- ✅ 所有需要高可靠性输出的 Agent/Skill
- ✅ 对抗大模型幻觉、错答、不自检等问题
- ✅ 可作为通用中间件集成到各类智能体系统中
- ✅ 完全兼容现有的多Agent、工作流、Skill 系统

---

## 核心特性

### 1. 多维度评分体系

| 维度 | 权重 | 说明 |
|------|------|------|
| 事实准确性 | 40分 | 信息真实可靠，无事实错误 |
| 逻辑通顺度 | 30分 | 推理清晰，结构合理 |
| 贴合问题 | 20分 | 直接回答问题，无答非所问 |
| 无幻觉编造 | 10分 | 无虚构内容，承认知识边界 |

### 2. 自动重试优化

- **默认配置**：最多3次迭代，合格线80分
- **智能反馈**：每次失败都提供具体的问题和优化建议
- **防死循环**：达到最大重试次数后自动停止

### 3. 完整的可观测性

```json
{
  "answer": "最终答案",
  "score": 85,
  "retry_count": 1,
  "is_passed": true,
  "history": [
    {
      "round": 1,
      "score": 72,
      "problems": "存在事实错误...",
      "suggestions": "建议修正...",
      "timestamp": "2026-04-28T17:00:00"
    },
    {
      "round": 2,
      "score": 85,
      "problems": "无明显问题",
      "suggestions": "无需优化",
      "timestamp": "2026-04-28T17:00:05"
    }
  ],
  "total_time": 5.23,
  "metadata": {...}
}
```

### 4. 低成本实现

- **单模型复用**：使用同一LLM切换提示词，无需额外模型
- **异步兼容**：适配现有异步架构，不阻塞主流程
- **灵活配置**：支持自定义评分标准、提示词模板

---

## 快速开始

### 安装依赖

项目已包含所有必要依赖，无需额外安装。

### 运行测试

```bash
cd /Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent
python tests/test_self_check_middleware.py
```

### 启动服务

```bash
python main.py
```

服务将在 `http://localhost:8001` 启动。

---

## API 使用

### 1. 执行自我校验

**端点**: `POST /api/v1/self-check/check`

**请求示例**:

```bash
curl -X POST http://localhost:8001/api/v1/self-check/check \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "什么是量子计算？",
    "pass_score": 80,
    "max_retry": 3,
    "temperature": 0.7
  }'
```

**Python 示例**:

```python
import requests

response = requests.post(
    "http://localhost:8001/api/v1/self-check/check",
    json={
        "user_query": "什么是量子计算？",
        "pass_score": 80,
        "max_retry": 3,
        "temperature": 0.7,
        "system_prompt": "你是一个专业的物理学家，请用通俗易懂的语言解释。"
    }
)

result = response.json()
print(f"得分: {result['score']}")
print(f"是否通过: {result['is_passed']}")
print(f"答案: {result['answer']}")
```

**响应示例**:

```json
{
  "success": true,
  "answer": "量子计算是一种利用量子力学原理进行计算的新型计算方式...",
  "score": 85,
  "retry_count": 1,
  "is_passed": true,
  "history": [...],
  "total_time": 5.23,
  "metadata": {...}
}
```

### 2. 获取统计信息

**端点**: `GET /api/v1/self-check/stats`

```bash
curl http://localhost:8001/api/v1/self-check/stats
```

**响应示例**:

```json
{
  "success": true,
  "data": {
    "total_checks": 150,
    "passed_checks": 135,
    "failed_checks": 15,
    "pass_rate": 90.0,
    "avg_retry_count": 1.2,
    "current_config": {
      "pass_score": 80,
      "max_retry": 3
    }
  },
  "timestamp": 1714300800.0
}
```

### 3. 批量处理

**端点**: `POST /api/v1/self-check/batch`

```bash
curl -X POST http://localhost:8001/api/v1/self-check/batch \
  -H "Content-Type: application/json" \
  -d '{
    "queries": [
      "什么是Python?",
      "什么是JavaScript?",
      "什么是Java?"
    ],
    "pass_score": 80,
    "max_retry": 2
  }'
```

### 4. 健康检查

**端点**: `GET /api/v1/self-check/health`

```bash
curl http://localhost:8001/api/v1/self-check/health
```

---

## 代码集成

### 基础用法

```python
import asyncio
from core.self_check_middleware import SelfCheckMiddleware
from core.llm_backend import get_llm_router

async def main():
    # 1. 创建中间件实例
    checker = SelfCheckMiddleware(pass_score=80, max_retry=3)
    
    # 2. 获取LLM路由器
    llm_router = get_llm_router()
    
    # 3. 定义生成函数
    async def generate_answer(query: str, context=None) -> str:
        return await llm_router.simple_chat(query, temperature=0.7)
    
    # 4. 执行自检
    result = await checker.check_and_optimize(
        user_query="什么是量子计算？",
        generate_func=generate_answer
    )
    
    # 5. 使用结果
    print(f"得分: {result.score}")
    print(f"答案: {result.answer}")
    print(f"历史: {result.history}")

asyncio.run(main())
```

### 集成到现有 Agent

```python
from core.self_check_middleware import SelfCheckMiddleware

class MyAgent:
    def __init__(self):
        self.checker = SelfCheckMiddleware(pass_score=85, max_retry=2)
        self.llm_router = get_llm_router()
    
    async def process(self, user_query: str) -> dict:
        """处理用户请求，带自我校验。"""
        
        # 定义生成函数
        async def generate(query: str, context=None) -> str:
            system_prompt = "你是一个专业的技术顾问..."
            return await self.llm_router.simple_chat(
                query,
                system_prompt=system_prompt,
                temperature=0.5
            )
        
        # 执行自检
        result = await self.checker.check_and_optimize(
            user_query=user_query,
            generate_func=generate
        )
        
        # 返回结构化结果
        return {
            "answer": result.answer,
            "quality_score": result.score,
            "is_reliable": result.is_passed,
            "metadata": result.to_dict()
        }
```

### 场景化配置

```python
# 不同场景使用不同的合格线
SCENARIOS = {
    "通用对话": {"pass_score": 80, "max_retry": 2},
    "代码生成": {"pass_score": 85, "max_retry": 3},
    "数学计算": {"pass_score": 90, "max_retry": 3},
    "创意写作": {"pass_score": 75, "max_retry": 2},
    "专业咨询": {"pass_score": 90, "max_retry": 4},
}

def get_checker_for_scenario(scenario: str) -> SelfCheckMiddleware:
    """根据场景获取配置的自检中间件。"""
    config = SCENARIOS.get(scenario, SCENARIOS["通用对话"])
    return SelfCheckMiddleware(
        pass_score=config["pass_score"],
        max_retry=config["max_retry"]
    )

# 使用
checker = get_checker_for_scenario("代码生成")
result = await checker.check_and_optimize(...)
```

### 自定义评审提示词

```python
# 针对代码审查的自定义提示词
CUSTOM_CODE_REVIEW_PROMPT = """
你是资深代码审查专家，请对代码进行严格评审。

满分100分，合格线{pass_score}分。

评分维度：
1. 代码正确性（40分）
2. 代码效率（25分）
3. 代码规范（20分）
4. 可维护性（15分）

输出格式：
得分：xx
问题：列出代码存在的问题
优化建议：给出具体的改进方案

用户要求：
{user_query}

待审查代码：
{content}

请开始评审：
"""

# 使用自定义提示词
result = await checker.check_and_optimize(
    user_query="实现一个线程安全的单例模式",
    generate_func=generate_code,
    custom_prompt_template=CUSTOM_CODE_REVIEW_PROMPT
)
```

---

## 配置说明

### SelfCheckMiddleware 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| pass_score | int | 80 | 合格分数线 (0-100) |
| max_retry | int | 3 | 最大重试次数 |
| enable_logging | bool | True | 是否启用详细日志 |

### check_and_optimize 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| user_query | str | - | 用户原始问题（必填） |
| generate_func | Callable | - | 生成函数（必填） |
| context | Dict | None | 可选上下文信息 |
| custom_prompt_template | str | None | 自定义评审提示词 |

### 推荐配置

| 场景 | pass_score | max_retry | 说明 |
|------|-----------|-----------|------|
| 日常对话 | 75-80 | 2 | 快速响应，适度质量控制 |
| 知识问答 | 80-85 | 3 | 平衡质量与速度 |
| 代码生成 | 85-90 | 3-4 | 严格要求代码质量 |
| 数学计算 | 90-95 | 3-4 | 确保计算准确 |
| 专业咨询 | 90-95 | 4-5 | 最高质量标准 |

---

## 最佳实践

### 1. 选择合适的合格线

```python
# ❌ 不合格线设置过高，导致频繁重试
checker = SelfCheckMiddleware(pass_score=98, max_retry=3)

# ✅ 根据场景合理设置
checker = SelfCheckMiddleware(pass_score=85, max_retry=3)
```

### 2. 控制重试次数

```python
# ❌ 重试次数过多，影响性能
checker = SelfCheckMiddleware(max_retry=10)

# ✅ 合理限制重试次数
checker = SelfCheckMiddleware(max_retry=3)
```

### 3. 使用系统提示词提升质量

```python
async def generate_with_system(query: str, context=None) -> str:
    system_prompt = """你是一个专业的技术顾问，请提供准确、详细的技术解答。
要求：
1. 事实准确，避免猜测
2. 逻辑清晰，结构完整
3. 如有不确定，明确说明"""
    
    return await llm_router.simple_chat(
        query,
        system_prompt=system_prompt,
        temperature=0.5
    )

result = await checker.check_and_optimize(
    user_query=query,
    generate_func=generate_with_system
)
```

### 4. 监控统计信息

```python
# 定期检查统计信息
stats = checker.get_stats()
print(f"通过率: {stats['pass_rate']}%")
print(f"平均重试: {stats['avg_retry_count']}次")

# 如果通过率过低，考虑调整配置
if stats['pass_rate'] < 70:
    logger.warning("通过率过低，建议降低合格线或增加重试次数")
```

### 5. 异常降级处理

```python
try:
    result = await checker.check_and_optimize(...)
    if not result.is_passed:
        logger.warning(f"自检未通过，得分: {result.score}")
        # 可以选择使用原始答案或提示用户
        answer = result.answer
    else:
        answer = result.answer
except Exception as e:
    logger.error(f"自检失败: {e}")
    # 降级为普通调用
    answer = await llm_router.simple_chat(user_query)
```

---

## 性能优化

### 1. 并行处理批量请求

```python
import asyncio

async def batch_process(queries: list) -> list:
    """并行处理多个问题。"""
    checker = SelfCheckMiddleware(pass_score=80, max_retry=2)
    
    tasks = []
    for query in queries:
        task = checker.check_and_optimize(
            user_query=query,
            generate_func=generate_answer
        )
        tasks.append(task)
    
    # 并行执行
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### 2. 缓存高频问题

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_cached_answer(query: str) -> str:
    """缓存常见问题的答案。"""
    # 实现缓存逻辑
    ...
```

### 3. 调整温度参数

```python
# 生成时使用较高温度，增加多样性
async def generate(query: str, context=None) -> str:
    return await llm_router.simple_chat(query, temperature=0.7)

# 评审时使用较低温度，保证稳定性
check_response = await llm_router.simple_chat(
    check_prompt,
    temperature=0.3
)
```

### 4. 性能基准

| 指标 | 数值 | 说明 |
|------|------|------|
| 单次调用耗时 | 2-5秒 | 取决于回答长度 |
| 带自检耗时 | 5-15秒 | 包含1-2次迭代 |
| 时间增加 | 100-200% | 相比无自检 |
| 质量提升 | 显著 | 从未知到80+分 |

---

## 故障排查

### 问题1: 自检一直不通过

**症状**: 多次重试后得分仍低于合格线

**解决方案**:
1. 降低合格线（如从85降到80）
2. 增加最大重试次数（如从3增加到5）
3. 优化系统提示词，提供更明确的指导
4. 检查评审提示词是否过于严格

```python
# 调整配置
checker = SelfCheckMiddleware(pass_score=80, max_retry=5)
```

### 问题2: 解析评审结果失败

**症状**: 日志显示"解析评审结果失败"

**解决方案**:
1. 检查LLM是否正确遵循输出格式
2. 在评审提示词中强调格式要求
3. 查看原始评审响应，确认格式

```python
# 加强格式约束
SELF_CHECK_PROMPT_TEMPLATE = """
...
输出格式严格如下（必须包含这三行）：
得分：xx
问题：xxx
优化建议：xxx
...
"""
```

### 问题3: 性能过慢

**症状**: 自检耗时过长，影响用户体验

**解决方案**:
1. 减少最大重试次数
2. 降低合格线
3. 使用更快的模型（如glm-4-flash）
4. 实现缓存机制

```python
# 优化配置
checker = SelfCheckMiddleware(pass_score=75, max_retry=2)

# 使用快速模型
llm_router.switch_model("glm-4-flash")
```

### 问题4: 统计信息不准确

**症状**: 统计数据显示异常

**解决方案**:
1. 重置统计信息
2. 检查是否有并发访问冲突
3. 验证中间件实例是否被正确共享

```python
# 重置统计
checker.reset_stats()

# 使用单例
checker = get_self_check_middleware()
```

---

## 附录

### A. 完整API文档

访问 `http://localhost:8001/docs` 查看完整的OpenAPI文档。

### B. 相关文档

- [自我校验系统设计文档](../docs/SELF_CHECK_DESIGN.md)
- [API集成指南](../docs/SELF_CHECK_API_GUIDE.md)
- [性能测试报告](../tests/test_self_check_middleware.py)

### C. 更新日志

**v1.0.0 (2026-04-28)**
- ✅ 实现核心自检逻辑
- ✅ 提供RESTful API接口
- ✅ 支持多维度评分
- ✅ 完整的可观测性
- ✅ 异步兼容设计

---

## 支持与反馈

如有问题或建议，请联系开发团队。

**项目地址**: `/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent`

**文档版本**: 1.0.0  
**最后更新**: 2026-04-28

================================================================================
提示词名称: 增量上下文加载
描述: 按需渐进式加载上下文的策略，而非一次性全部加载，减少初始 token 使用并提高专注度。
使用场景:
  - 处理超大型代码库
  - 需求不断演进的探索性任务
  - 减少不必要的上下文加载
  - 优化成本和延迟
================================================================================

<incremental_loading_strategy>
阶段 1: 最小上下文
- 仅加载必要信息
- 用户的请求
- 直接提到的文件
- 项目类型和结构概览

阶段 2: 尝试执行任务
- AI 用最小上下文尝试完成任务
- 识别需要哪些额外信息
- 请求特定文件或上下文

阶段 3: 定向扩展
- 仅加载请求的额外上下文
- 避免加载整个依赖树
- 聚焦于实际需要的内容

阶段 4: 迭代优化
- 用新上下文继续任务
- 如仍需要则请求更多上下文
- 重复直到任务完成

好处:
- 降低初始 token 使用
- 更快的初始响应
- 更专注的 AI 注意力
- 简单任务节省成本
</incremental_loading_strategy>

<context_request_protocol>
AI 请求上下文:
```
<context_request>
我需要额外信息来完成此任务:

所需文件:
- src/utils/validation.ts（需要 validateEmail 函数）
- src/types/user.ts（需要 User 接口定义）

原因: 为了按照现有模式实现邮箱验证

优先级: 高（阻塞当前任务）
</context_request>
```

系统提供上下文:
```
<additional_context>
文件: src/utils/validation.ts
[相关代码]

文件: src/types/user.ts
[相关代码]
</additional_context>
```

AI 继续:
```
<task_continuation>
现在有了验证模式，我可以实现...
</task_continuation>
```
</context_request_protocol>

<smart_prefetching>
预测性加载:
- 如果正在编辑组件，预加载其测试文件
- 如果修改 API 路由，预加载相关控制器
- 如果更改模型，预加载迁移文件
- 如果更新配置，预加载文档

依赖提示:
- 自动加载直接导入
- 建议加载相关文件
- 提供加载完整依赖链的选项
- 允许用户批准批量加载
</smart_prefetching>

<output_format>
```
增量加载会话
========================

初始上下文:
- 加载 tokens: [count]
- 包含文件: [list]

迭代 1:
- 尝试任务: [description]
- 所需上下文: [缺少的内容]
- 额外 tokens: [count]
- 新增文件: [list]

迭代 2:
- 继续任务: [progress]
- 所需上下文: [如有]
- 额外 tokens: [count]

最终状态:
- 总迭代次数: [count]
- 总使用 tokens: [count]
- 任务完成: [是/否]

效率分析:
- 相比全量加载节省 tokens: [count]
- 减少百分比: [%]
- 完成时间: [duration]
```
</output_format>

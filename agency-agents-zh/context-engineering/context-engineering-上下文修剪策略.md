================================================================================
提示词名称: 上下文修剪策略
描述: 智能移除不太相关信息的技术，在 token 限制内保留关键细节。
使用场景:
  - 在有限上下文窗口中管理大型代码库
  - 优化 token 使用和成本
  - 维护对话历史而不溢出
  - 让 AI 聚焦于相关信息
================================================================================

<pruning_techniques>
1. 基于时效性的修剪:
   - 保留最近的 N 条消息/文件
   - 最先丢弃最旧的内容
   - 保留近期上下文以保持连续性

2. 基于相关性的修剪:
   - 为每条上下文按相关性评分
   - 保留高分项目
   - 丢弃低分项目，不论新旧

3. 分层修剪:
   - 保留详细的近期上下文
   - 摘要化中期上下文
   - 仅保留旧上下文中的关键事实

4. 语义修剪:
   - 移除冗余信息
   - 合并相似内容
   - 仅保留唯一信息

5. 结构化修剪:
   - 保留函数签名，丢弃实现
   - 保留类定义，丢弃方法体
   - 保留导入导出，丢弃内部逻辑
</pruning_techniques>

<pruning_rules>
始终保留:
- 当前任务描述
- 用户明确提到的文件
- 错误消息和堆栈跟踪
- 最近的用户纠正或反馈
- 关键配置

安全移除:
- 重复信息
- 样板代码
- 注释（如果代码自解释）
- 空白和格式
- 已完成的子任务
- 已确认的信息

用摘要替代移除:
- 长函数实现
- 详细文档
- 历史上下文
- 背景信息
- 相关但非关键的文件

绝不移除:
- 用户的原始请求
- 安全关键信息
- 影响正确性的数据
- 独特的领域知识
- 活跃的错误上下文
</pruning_rules>

<pruning_algorithms>
算法 1: Token 预算修剪
```
1. 计算所需总 token 数
2. 如果在预算内，全部包含
3. 如果超出预算:
   a. 按重要性对所有上下文排序
   b. 包含排名最高的，直到达到预算
   c. 如果空间允许，摘要化下一层
   d. 丢弃排名最低的项目
```

算法 2: 带摘要的滑动窗口
```
1. 保留最近 N 轮交互的完整详情
2. 摘要化第 N 到 2N 轮交互
3. 仅保留 > 2N 轮交互的关键事实
4. 完全丢弃 > 3N 轮的交互
```

算法 3: 相关性衰减
```
1. 为每条上下文评分: 基础相关度 * 衰减因子^年龄
2. 按分数排序
3. 包含适合预算的前 K 个项目
4. 摘要化下一层
5. 丢弃其余
```

算法 4: 依赖感知修剪
```
1. 构建文件的依赖图
2. 保留从入口到目标路径上的所有文件
3. 修剪不在关键路径上的文件
4. 摘要化相邻文件
5. 丢弃远距离文件
```
</pruning_algorithms>

<implementation_example>
```python
def prune_context(context_items, token_budget, current_task):
    """
    智能修剪上下文以适配 token 预算。
    """
    # 为每个项目评分
    scored_items = []
    for item in context_items:
        score = calculate_relevance_score(item, current_task)
        scored_items.append((score, item))
    
    # 按分数排序（最高分在前）
    scored_items.sort(reverse=True, key=lambda x: x[0])
    
    # 包含项目直到预算耗尽
    included = []
    tokens_used = 0
    
    for score, item in scored_items:
        item_tokens = count_tokens(item)
        
        if tokens_used + item_tokens <= token_budget:
            included.append(item)
            tokens_used += item_tokens
        elif tokens_used + item_tokens/2 <= token_budget:
            # 尝试摘要化，如果完整版本放不下
            summary = summarize(item)
            included.append(summary)
            tokens_used += count_tokens(summary)
        else:
            # 跳过此项目
            continue
    
    return included
```
</implementation_example>

<output_format>
```
上下文修剪报告
========================

修剪前:
- 总项目数: [count]
- 总 tokens: [count]
- 预算: [tokens]
- 溢出: [超出预算的 tokens]

修剪策略:
- 方法: [使用的算法]
- 标准: [决定保留/移除的依据]

修剪后:
- 保留项目（完整）: [count]
- 摘要化项目: [count]
- 移除项目: [count]
- 总 tokens: [count]
- 剩余预算: [tokens]

已移除项目:
- [item]: [移除原因]

已摘要化项目:
- [item]: [原始 tokens] → [摘要 tokens]

质量影响:
- 保留信息: [百分比]
- 关键上下文保留: [是/否]
- 风险等级: [低/中/高]
```
</output_format>

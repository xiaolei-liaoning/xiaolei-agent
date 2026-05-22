---
name: task-memory-logging
description: 每次完成任务后必须写入记忆系统，记录关键发现和决策
metadata: 
  node_type: memory
  type: feedback
  originSessionId: aee0cd68-184a-4d3c-a30f-dacb4f717a00
---

每次完成任务后，必须将任务中涉及的关键发现、决策、用户偏好、项目状态变化等信息写入 memory 系统。

**Why:** 用户需要记忆系统持续积累上下文，避免重复说明同一件事，确保跨会话的连续性。

**How to apply:** 任务完成后，评估是否有值得记录的信息（新的用户偏好、项目决策、架构变更、踩坑经验等），如有则创建或更新对应的 memory 文件，并在 MEMORY.md 中添加索引条目。

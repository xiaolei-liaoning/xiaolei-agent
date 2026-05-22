---
name: sandbox-reverse-question
description: 沙盒禁止模块时不用直接否决，而是反问用户是否继续执行
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9d6abbc4-cd58-4faa-866f-08d54e055168
---

沙盒执行遇到禁止导入的模块（如 `requests`）时，不要直接否决/拒绝执行，而是应该使用反问机制询问用户是否确认要继续执行。

**Why:** 模块虽然被沙盒禁止，但用户可能知道风险并愿意承担，或者有替代方案。直接否决中断了工作流程，反问机制把选择权交给用户。

**How to apply:** 在沙盒检测到禁止导入时，改为反问用户："检测到模块 X 被沙盒禁止，是否仍要继续执行？" 而不是直接标记失败并降级。

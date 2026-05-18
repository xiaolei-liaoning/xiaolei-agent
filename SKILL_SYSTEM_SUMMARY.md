# 技能系统现状总结

## 四个注册表，互不相通

```
注册方式                        → 注册到哪里               → 谁查这里
──────────────────────────────────────────────────────────────────────
SkillDispatcher.register_tool() → ToolRegistry              ← WorkerAgent 查
                                 (class级别, 全局一份)
                                    
plugin_loader._register_skill_md() → SkillRegistry           ← 没人查
                                 (get_skill_registry() 单例)

SkillDispatcher.match_skill()   → skill_configs             ← SkillDispatcher 自己查
                                 (dispatcher 内部配置)

tools.tool_manager              → ToolManager             ← 旧代码直接调
                                 (另一个单例, 独立)
```

## 三类 Skill 的实际命运

| 类型 | 举例 | 注册到哪 | 能执行吗 |
|------|------|---------|---------|
| **角色 Skill** | 李白/Carmack/bestfriend | `ToolRegistry` ✅ (via `register_tool()`) | 能，但靠 handler.py 里硬编码的 system prompt 调 LLM |
| **Guidance Skill** | everything-claude-code 的技能、含 SKILL.md 的子插件 | `SkillRegistry` ❌ | **不能**，WorkerAgent 不查这个注册表 |
| **mcp/_impl/** | calculator/weather/web_scraper | 不注册到任何表 | 被旧代码直接 import 调用 |

## 执行流程

```
用户说 "写一首月亮诗"
  ↓
WorkerAgent._decide_execution_with_llm()
  → LLM 判断: "general"
  ↓
_execute_general()
  → ToolRegistry.match("写一首月亮诗")    ❌ 查不到（关键词不匹配）
  → 直接调 LLM: system="你是一个通用助手"
  → 结果: 没有李白特色
```

**如果用户说 "李白"**
```
WorkerAgent._decide_execution_with_llm()
  → LLM 可能判断: "general"
  ↓
_execute_general()
  → ToolRegistry.match("李白") → 匹配到 "libai" ✅
  → ToolRegistry.execute("libai") → LibaiHandler.execute()
  → handler.py 里硬编码: system_prompt="你是唐代诗人李白..."
  → 调 LLM → 李白风格回复 ✅
```

## handler.py 的真实现状

| 文件 | 代码量 | 真实作用 |
|------|--------|---------|
| `skills/人物/` ×6 | 各~80行 | **一模一样的模板代码**，区别只有角色名和 system prompt |
| `skills/ocr_recognition/` | 22行 | 一行委托给 `mcp/_impl/data_analysis` |
| `skills/mvp_checker/` | 17行 | 空壳，返回"待实现" |
| `skills/mcp_connector/` | ~100行 | 有真实 MCP 连接逻辑 |
| `skills/mcp_orchestrator/` | ~200行 | 有真实协调逻辑 |
| `skills/workflow_engine.py` | 单独文件 | 工作流引擎 |

## 真正的问题

1. **三个注册表**（ToolRegistry / SkillRegistry / skill_configs）没有打通
2. **GuidanceSkill + SKILL.md 注册到了 SkillRegistry**，但 WorkerAgent 和 SkillDispatcher 都不查这里
3. **6个角色 handler.py 是纯重复代码**，SKILL.md 内容和 handler.py 的 system prompt 完全重复
4. **WorkerAgent._execute_general() 用固定 system prompt**，不会加载 SKILL.md

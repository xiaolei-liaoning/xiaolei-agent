# V2 项目分析能力 — 真实测试评估报告

**测试日期:** 2026-06-22
**测试项目:** Gemini CLI (Google 开源)
**测试路径:** `/Users/leiyuxuan/Desktop/gemini-cli`
**测试命令:** `python cli.py 分析一下 /path 这个项目...`
**架构链路:** CLI → `handle_smart_request` → `WorkAgent.execute()` → `run_react()`

---

## 测试结果

| 维度 | 数据 |
|------|------|
| Skill 匹配 | `project_analyzer` ✅ |
| Expert 匹配 | `项目结构分析师` ✅ |
| 总轮次 | 15/15（跑满） |
| 工具使用 | 全部 `read_file`，从未调用 `analyze_project` ❌ |
| 读取文件 | ~18 个文件（目录+配置+入口） |
| 耗时 | ~45s |

**V2 实际分析结论：** "Google Gemini API 的 CLI 工具，TypeScript + React + Ink"

**应该能产出的：** "Google 开源、Apache 2.0、0.47.0-nightly、7 packages monorepo、agents/commands/context/mcp 分层架构、1M token 窗口、Google Search grounding、esbuild + Vitest + Docker、免费 60req/min"

---

## 根因

1. **LLM 无视了 `_PROJECT_ANALYSIS_PROMPT`** — prompt 是建议不是命令
2. **`read_file` 太顺手** — LLM 习惯逐文件读，不会主动选陌生的 `analyze_project`
3. **15 轮读 ~18 个文件** — 逐文件低效，`analyze_project` 1 轮就能读 12+ 个
4. **没有确定性路径** — 所有任务都走通用 ReAct，分析项目这种确定性流程不该让 LLM 自己决策

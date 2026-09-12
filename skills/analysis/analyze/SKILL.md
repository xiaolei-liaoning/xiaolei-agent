---
name: analyze
description: "Analyze codebases and projects with parallel sub-agents for depth."
version: 1.0.0
author: 小雷版 Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [analysis, code-review, project-inspection, subagent]
    category: analysis
    related_skills: []
---

# Analyze Skill

You are a code analyst. You deeply read, search, and analyze code to produce structured, actionable findings.

This skill is for **analysis-only** tasks — you do NOT edit or create files. Your job is to understand, trace, and report.

## When to Use

- User asks to "analyze", "understand", "inspect", or "研究" a project or codebase
- User mentions "子代理" or "parallel" in the context of analysis
- The target project has multiple independent modules, directories, or concerns
- The analysis scope is large enough that a single agent would miss context

## Prerequisites

None. This skill works with any project that has source files.

## How to Run — CRITICAL: Use Sub-Agents for Large Projects

**If the project has more than ~50 files, or has multiple independent modules/directories:**

You MUST use the `task` tool to spawn parallel sub-agents. Do NOT do this work alone with serial `read_file` calls.

```
1. Identify 3-8 independent analysis dimensions (e.g., per-module, per-layer, per-concern)
2. Call `task` once per dimension with `subagent_type=analyze`
3. Each sub-agent gets a focused prompt like:
   "Analyze the {module_name} module. Focus on: architecture, key classes, data flow, and risks."
4. Wait for all sub-agents to complete
5. Synthesize results into a unified report
```

**If the project is small (<50 files, single module):**

You may analyze directly with `read_file`, `search_files`, and `execute_shell`. Still prefer breadth over depth — trace execution paths across files.

## Procedure

### Step 1: Scope the project

Use `search_files` and `execute_shell` to understand the project structure:
```
search_files → discover files matching patterns
execute_shell → ls, find, wc -l to estimate scope
```

### Step 2: Decide serial vs parallel

| Project size | Approach |
|---|---|
| < 50 files, 1 module | Serial (direct analysis) |
| 50-200 files, few modules | 2-3 sub-agents via `task` |
| > 200 files, many modules | 5-8 sub-agents via `task` |

### Step 3: Execute analysis

**Serial path:**
- Read key files (entry points, configs, main modules)
- Use `search_files` to trace dependencies and call sites
- Use `execute_shell` for metrics (LOC, file counts)
- Present findings ordered by importance

**Parallel path (preferred for large projects):**
- Call `task` with `subagent_type=analyze` for each dimension
- Give each sub-agent a clear, focused prompt
- Wait for results, then synthesize

### Step 4: Report

Present findings in this order:
1. **Architecture overview** — what is this project, what does it do
2. **Key findings** — ordered by importance (critical / important / minor)
3. **Risks and issues** — bugs, design problems, security concerns
4. **Recommendations** — what to improve, what to watch

Include exact file paths and line numbers for each finding.

## Guidelines

- Read widely before concluding. Don't draw conclusions from a single file — trace the full execution path.
- Use `search_files` to find usages and dependencies across the codebase.
- Use `execute_shell` to discover files and get metrics.
- Present findings in order of importance (critical / important / minor).
- Include exact file paths and line numbers for each finding.
- When analyzing a bug, identify root cause vs symptom.
- When comparing options, list tradeoffs with concrete evidence from the code.
- **Do NOT edit or create any files. You are read-only.**
- Do not use emojis unless asked.

## Verification

After analysis, verify your findings by:
- Checking that file paths exist
- Confirming line numbers match actual code
- Ensuring conclusions are supported by evidence, not assumptions

<div align="center">

<!-- Hero Section -->
<img src="https://img.shields.io/badge/小雷版小龙虾-AI%20Agent%20v3.4-8B5CF6?style=for-the-badge&logo=python&logoColor=white&labelColor=1E1B4B" alt="Title">

<br>

> 一套代码，两套架构 · 从单次对话到复杂编排，总有一种模式适合你

<br>

![V1](https://img.shields.io/badge/▸_V1_队长_队员-分工协作-8B5CF6?style=flat-square&labelColor=1E1B4B)
![V2-Single](https://img.shields.io/badge/▸_V2_单Agent-工具直通-10B981?style=flat-square&labelColor=064E3B)
![V2-Multi](https://img.shields.io/badge/▸_V2_多Agent_JS_Workflow-工作流编排-F59E0B?style=flat-square&labelColor=451A03)
![Python](https://img.shields.io/badge/Python_3.13-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![DeepSeek](https://img.shields.io/badge/DeepSeek_|_GLM-FF6B6B?style=flat-square)
![MCP](https://img.shields.io/badge/35＋_Tools-845EF7?style=flat-square)
![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6B35?style=flat-square)

---

<!-- Architecture SVG -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 80" width="100%" style="max-width:900px;">
  <defs>
    <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#8B5CF6"/>
      <stop offset="100%" stop-color="#6366F1"/>
    </linearGradient>
    <linearGradient id="g2" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#10B981"/>
      <stop offset="100%" stop-color="#059669"/>
    </linearGradient>
    <linearGradient id="g3" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#F59E0B"/>
      <stop offset="100%" stop-color="#D97706"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="280" height="60" rx="10" fill="url(#g1)" opacity="0.95"/>
  <text x="140" y="36" text-anchor="middle" fill="white" font-size="16" font-weight="700" font-family="system-ui">V1 队长-队员模式</text>
  <line x1="290" y1="30" x2="340" y2="30" stroke="#CBD5E1" stroke-width="2" stroke-dasharray="6,4"/>
  <rect x="350" y="0" width="260" height="60" rx="10" fill="url(#g2)" opacity="0.95"/>
  <text x="480" y="36" text-anchor="middle" fill="white" font-size="16" font-weight="700" font-family="system-ui">V2 单Agent</text>
  <line x1="620" y1="30" x2="670" y2="30" stroke="#CBD5E1" stroke-width="2" stroke-dasharray="6,4"/>
  <rect x="680" y="0" width="210" height="60" rx="10" fill="url(#g3)" opacity="0.95"/>
  <text x="785" y="36" text-anchor="middle" fill="white" font-size="16" font-weight="700" font-family="system-ui">V2 多Agent</text>
</svg>

</div>

<br>

---

## 目录

<span style="color:#94A3B8;font-size:14px;">
[一、系统总览](#一系统总览) · [二、V1 架构](#二v1-架构队长-队员模式) · [三、V2 架构](#三v2-架构统一工具型) · [四、架构对比](#四架构对比) · [五、功能矩阵](#五功能矩阵) · [六、快速开始](#六快速开始) · [七、项目结构](#七项目结构)
</span>

---

## 一、系统总览

<div style="display:flex;flex-wrap:wrap;gap:12px;margin:16px 0;">

<div style="flex:1;min-width:260px;padding:16px 20px;background:linear-gradient(135deg,#1E1B4B,#312E81);border-radius:12px;color:white;">
<h3 style="margin:0 0 6px">🧠 双引擎</h3>
<p style="margin:0;opacity:0.8;font-size:14px">DeepSeek + GLM，4 种路由策略 · round_robin · least_load · priority · fallback_chain</p>
</div>

<div style="flex:1;min-width:260px;padding:16px 20px;background:linear-gradient(135deg,#064E3B,#047857);border-radius:12px;color:white;">
<h3 style="margin:0 0 6px">🛠️ 35+ 工具</h3>
<p style="margin:0;opacity:0.8;font-size:14px">10 内置 + 25+ MCP · 自动发现即插即用 · 沙箱隔离</p>
</div>

<div style="flex:1;min-width:260px;padding:16px 20px;background:linear-gradient(135deg,#1E3A5F,#1E40AF);border-radius:12px;color:white;">
<h3 style="margin:0 0 6px">🗃️ 三层记忆</h3>
<p style="margin:0;opacity:0.8;font-size:14px">短期记忆 (STM) · 向量记忆 (ChromaDB) · 自我进化引擎</p>
</div>

<div style="flex:1;min-width:260px;padding:16px 20px;background:linear-gradient(135deg,#4C1D95,#6D28D9);border-radius:12px;color:white;">
<h3 style="margin:0 0 6px">🔍 RAG 增强</h3>
<p style="margin:0;opacity:0.8;font-size:14px">多引擎搜索 · 百度/知乎/微博/抖音 · 实时检索注入</p>
</div>

<div style="flex:1;min-width:260px;padding:16px 20px;background:linear-gradient(135deg,#7C2D12,#C2410C);border-radius:12px;color:white;">
<h3 style="margin:0 0 6px">🔌 插件系统</h3>
<p style="margin:0;opacity:0.8;font-size:14px">第三方热加载 · Remotion 视频渲染 · 自定义技能</p>
</div>

</div>

</div>

<br>

---

## 二、V1 架构：队长-队员模式

<div align="center">

<!-- V1 Architecture SVG -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" width="100%" style="max-width:760px;">
  <defs>
    <linearGradient id="v1_leader" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#7C3AED"/>
      <stop offset="100%" stop-color="#5B21B6"/>
    </linearGradient>
    <linearGradient id="v1_worker" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#6366F1"/>
      <stop offset="100%" stop-color="#4338CA"/>
    </linearGradient>
    <linearGradient id="v1_tools" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#14B8A6"/>
      <stop offset="100%" stop-color="#0D9488"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect x="0" y="0" width="760" height="420" rx="16" fill="#F8FAFC" stroke="#E2E8F0" stroke-width="1"/>
  <rect x="0" y="0" width="760" height="420" rx="16" fill="url(#v1_bg)" opacity="0.02"/>

  <!-- Title -->
  <text x="380" y="36" text-anchor="middle" fill="#1E293B" font-size="18" font-weight="700" font-family="system-ui">V1 队长-队员模式 · 执行流程</text>

  <!-- Leader box -->
  <rect x="290" y="56" width="180" height="70" rx="12" fill="url(#v1_leader)"/>
  <text x="380" y="86" text-anchor="middle" fill="white" font-size="16" font-weight="700" font-family="system-ui">LeaderAgent</text>
  <text x="380" y="108" text-anchor="middle" fill="#C4B5FD" font-size="13" font-family="system-ui">队长 · 任务分解 · 动态规划</text>

  <!-- ReAct label -->
  <text x="380" y="150" text-anchor="middle" fill="#64748B" font-size="12" font-family="system-ui">ReAct 循环: Thought → Action → Observation → 继续/完成</text>

  <!-- Arrow down -->
  <polygon points="380,155 374,155 380,165 386,155" fill="#94A3B8"/>
  <line x1="380" y1="126" x2="380" y2="155" stroke="#94A3B8" stroke-width="1.5"/>

  <!-- Action types row -->
  <rect x="20" y="170" width="135" height="44" rx="8" fill="#EDE9FE" stroke="#C4B5FD" stroke-width="1"/>
  <text x="87" y="196" text-anchor="middle" fill="#7C3AED" font-size="12" font-weight="600" font-family="monospace">delegate ▸</text>

  <rect x="165" y="170" width="145" height="44" rx="8" fill="#EDE9FE" stroke="#C4B5FD" stroke-width="1"/>
  <text x="237" y="196" text-anchor="middle" fill="#7C3AED" font-size="11" font-weight="600" font-family="monospace">batch_delegate ▸</text>

  <rect x="320" y="170" width="100" height="44" rx="8" fill="#EDE9FE" stroke="#C4B5FD" stroke-width="1"/>
  <text x="370" y="196" text-anchor="middle" fill="#7C3AED" font-size="12" font-weight="600" font-family="monospace">tool ▸</text>

  <rect x="430" y="170" width="120" height="44" rx="8" fill="#EDE9FE" stroke="#C4B5FD" stroke-width="1"/>
  <text x="490" y="196" text-anchor="middle" fill="#7C3AED" font-size="10" font-weight="600" font-family="monospace">process_results ▸</text>

  <rect x="560" y="170" width="180" height="44" rx="8" fill="#FEF3C7" stroke="#F59E0B" stroke-width="1"/>
  <text x="650" y="196" text-anchor="middle" fill="#92400E" font-size="11" font-weight="600" font-family="monospace">KEPA 反思 (≤3次重试)</text>

  <!-- Arrow down to workers -->
  <polygon points="380,218 374,218 380,228 386,218" fill="#94A3B8"/>
  <line x1="380" y1="214" x2="380" y2="218" stroke="#94A3B8" stroke-width="1.5"/>

  <!-- Workers -->
  <text x="380" y="248" text-anchor="middle" fill="#64748B" font-size="11" font-family="system-ui">WorkerAgent 池 (3~5个并行执行)</text>

  <rect x="40" y="258" width="140" height="58" rx="10" fill="url(#v1_worker)"/>
  <text x="110" y="286" text-anchor="middle" fill="white" font-size="14" font-weight="600" font-family="system-ui">Worker 1</text>
  <text x="110" y="303" text-anchor="middle" fill="#A5B4FC" font-size="11" font-family="system-ui">并行任务</text>

  <rect x="230" y="258" width="140" height="58" rx="10" fill="url(#v1_worker)"/>
  <text x="300" y="286" text-anchor="middle" fill="white" font-size="14" font-weight="600" font-family="system-ui">Worker 2</text>
  <text x="300" y="303" text-anchor="middle" fill="#A5B4FC" font-size="11" font-family="system-ui">并行任务</text>

  <rect x="420" y="258" width="140" height="58" rx="10" fill="url(#v1_worker)"/>
  <text x="490" y="286" text-anchor="middle" fill="white" font-size="14" font-weight="600" font-family="system-ui">Worker 3</text>
  <text x="490" y="303" text-anchor="middle" fill="#A5B4FC" font-size="11" font-family="system-ui">并行任务</text>

  <rect x="600" y="258" width="130" height="58" rx="10" fill="url(#v1_worker)" opacity="0.7"/>
  <text x="665" y="286" text-anchor="middle" fill="white" font-size="14" font-weight="600" font-family="system-ui">...</text>

  <!-- Tools -->
  <polygon points="380,321 374,321 380,331 386,321" fill="#94A3B8"/>
  <line x1="380" y1="316" x2="380" y2="321" stroke="#94A3B8" stroke-width="1.5"/>

  <rect x="20" y="338" width="230" height="64" rx="10" fill="url(#v1_tools)"/>
  <text x="135" y="367" text-anchor="middle" fill="white" font-size="14" font-weight="600" font-family="system-ui">10 内置工具</text>
  <text x="135" y="387" text-anchor="middle" fill="#A7F3D0" font-size="11" font-family="system-ui">search · fetch · read · write · code · shell · git</text>

  <rect x="265" y="338" width="230" height="64" rx="10" fill="url(#v1_tools)"/>
  <text x="380" y="367" text-anchor="middle" fill="white" font-size="14" font-weight="600" font-family="system-ui">25+ MCP 工具</text>
  <text x="380" y="387" text-anchor="middle" fill="#A7F3D0" font-size="11" font-family="system-ui">Playwright · Weather · Translate · CodeGraph · GUI</text>

  <!-- Memory -->
  <rect x="510" y="338" width="230" height="64" rx="10" fill="#312E81"/>
  <text x="625" y="367" text-anchor="middle" fill="#C4B5FD" font-size="14" font-weight="600" font-family="system-ui">三层记忆注入</text>
  <text x="625" y="387" text-anchor="middle" fill="#A78BFA" font-size="10" font-family="system-ui">ContextMemory · STM · RAG · 经验向量库</text>

  <!-- Feedback loop arrow -->
  <path d="M 520 60 Q 700 60 700 130 Q 700 200 520 200" fill="none" stroke="#A78BFA" stroke-width="1.5" stroke-dasharray="6,3"/>
  <text x="720" y="130" fill="#7C3AED" font-size="10" font-weight="600" font-family="system-ui" transform="rotate(90,720,130)">反馈循环</text>
</svg>

<br>

</div>

### 工作流

<div>

**第 1 轮** &nbsp;&nbsp; `Thought` 队长分析任务 → `Action` **batch_delegate** → `["搜索热搜", "分析数据"]`
<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ← 两个 Worker 并行搜索 + 数据读取 → ✅

**第 2 轮** &nbsp;&nbsp; `Thought` 需要生成报告 → `Action` **delegate** → `"整理数据存到桌面"`
<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ← Worker 调用 `write_file` → ✅

**第 3 轮** &nbsp;&nbsp; `Thought` 已全部完成 → `Action` **完成** ✅

</div>

<br>

### V1 核心组件

| 组件 | 文件 | 核心职责 |
|------|------|---------|
| **LeaderAgent** | `core/agent_system.py` | ReAct 决策循环 · 拆解任务 · 分配 Worker · 分析结果 |
| **LLMAgent** (Worker) | `core/agent_system.py` | 执行子任务 · 工具调用 · KEPA 反思 |
| **V1LeaderPool** | `core/agent_system.py` | Agent 池化管理 · Worker 复用 (上限 10) |
| **ContextMemory** | `core/agent_system.py` | 每轮对话记忆 (最近 20 条) |
| **KEPA 反思** | `core/agent_system.py` | Think → Act → Reflect 闭环 |

### V1 关键特性

- 🔀 **角色分离** — 队长只决策不执行，队员只执行不决策
- ⚡ **并行加速** — `batch_delegate` 多 Worker 并行执行
- 🔄 **自我修复** — KEPA 自动重试失败任务 (≤3 次)
- 🧠 **多元记忆** — RAG 检索 + 短期记忆 + 经验向量库
- 🌱 **自我进化** — 执行后分析经验，提炼洞察存入知识库

<br>

---

## 三、V2 架构：统一工具型

<div align="center">

<!-- V2 Architecture SVG -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 520" width="100%" style="max-width:760px;">
  <defs>
    <linearGradient id="v2_base" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1E293B"/>
      <stop offset="100%" stop-color="#0F172A"/>
    </linearGradient>
    <linearGradient id="v2_single" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#10B981"/>
      <stop offset="100%" stop-color="#047857"/>
    </linearGradient>
    <linearGradient id="v2_multi" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#F59E0B"/>
      <stop offset="100%" stop-color="#B45309"/>
    </linearGradient>
  </defs>

  <rect x="0" y="0" width="760" height="520" rx="16" fill="#F8FAFC" stroke="#E2E8F0" stroke-width="1"/>

  <!-- Title -->
  <text x="380" y="36" text-anchor="middle" fill="#1E293B" font-size="18" font-weight="700" font-family="system-ui">V2 统一工具型架构 · 两种模式</text>

  <!-- Shared Base -->
  <rect x="30" y="55" width="700" height="160" rx="14" fill="url(#v2_base)"/>
  <text x="380" y="80" text-anchor="middle" fill="#94A3B8" font-size="13" font-weight="600" font-family="system-ui">共享工具底盘</text>

  <!-- ToolRegistry -->
  <rect x="50" y="95" width="200" height="50" rx="8" fill="#334155"/>
  <text x="150" y="118" text-anchor="middle" fill="#E2E8F0" font-size="13" font-weight="600" font-family="system-ui">ToolRegistry</text>
  <text x="150" y="135" text-anchor="middle" fill="#94A3B8" font-size="11" font-family="system-ui">10 内置 + 25+ MCP</text>

  <!-- LLM Router -->
  <rect x="280" y="95" width="200" height="50" rx="8" fill="#334155"/>
  <text x="380" y="118" text-anchor="middle" fill="#E2E8F0" font-size="13" font-weight="600" font-family="system-ui">LLM Router</text>
  <text x="380" y="135" text-anchor="middle" fill="#94A3B8" font-size="11" font-family="system-ui">DeepSeek / GLM · 4 种策略</text>

  <!-- MiddlewareChain -->
  <rect x="510" y="95" width="200" height="50" rx="8" fill="#334155"/>
  <text x="610" y="118" text-anchor="middle" fill="#E2E8F0" font-size="13" font-weight="600" font-family="system-ui">MiddlewareChain</text>
  <text x="610" y="135" text-anchor="middle" fill="#94A3B8" font-size="11" font-family="system-ui">4 层中间件 · Depth/ReAct/Ref/KEPA</text>

  <!-- Shared resources row -->
  <rect x="50" y="155" width="660" height="46" rx="8" fill="#475569"/>
  <text x="380" y="176" text-anchor="middle" fill="#CBD5E1" font-size="12" font-weight="600" font-family="system-ui">共享受限资源</text>
  <text x="380" y="193" text-anchor="middle" fill="#94A3B8" font-size="11" font-family="system-ui">3 并发信号量 · 沙箱管理器 · 文件缓存 · 输出截断</text>

  <!-- Arrow to modes -->
  <line x1="380" y1="215" x2="380" y2="238" stroke="#94A3B8" stroke-width="1.5"/>
  <polygon points="380,242 374,242 380,248 386,242" fill="#94A3B8"/>

  <!-- Mode ① - Single Agent -->
  <rect x="30" y="255" width="360" height="245" rx="14" fill="#ECFDF5" stroke="#10B981" stroke-width="1.5"/>
  <text x="210" y="282" text-anchor="middle" fill="#065F46" font-size="15" font-weight="700" font-family="system-ui">① V2 单Agent</text>

  <!-- AgentPool -->
  <rect x="55" y="296" width="140" height="44" rx="8" fill="#A7F3D0"/>
  <text x="125" y="320" text-anchor="middle" fill="#065F46" font-size="13" font-weight="600" font-family="system-ui">AgentPool</text>
  <text x="125" y="335" text-anchor="middle" fill="#047857" font-size="11" font-family="system-ui">8 个预热 Worker</text>

  <line x1="195" y1="318" x2="225" y2="318" stroke="#10B981" stroke-width="1.5"/>
  <polygon points="227,318 221,314 221,322" fill="#10B981"/>

  <rect x="230" y="296" width="140" height="44" rx="8" fill="#10B981"/>
  <text x="300" y="320" text-anchor="middle" fill="white" font-size="13" font-weight="600" font-family="system-ui">WorkAgent</text>
  <text x="300" y="335" text-anchor="middle" fill="#A7F3D0" font-size="10" font-family="system-ui">acquire → execute → release</text>

  <!-- Flow -->
  <line x1="300" y1="340" x2="300" y2="358" stroke="#10B981" stroke-width="1.5"/>
  <polygon points="300,362 294,362 300,368 306,362" fill="#10B981"/>

  <rect x="55" y="370" width="315" height="36" rx="8" fill="#D1FAE5"/>
  <text x="212" y="393" text-anchor="middle" fill="#047857" font-size="11" font-weight="600" font-family="monospace">run_react() → 4 层 MiddlewareChain</text>

  <!-- Tags -->
  <rect x="55" y="416" width="100" height="28" rx="14" fill="#6EE7B7"/>
  <text x="105" y="435" text-anchor="middle" fill="#065F46" font-size="11" font-weight="600" font-family="system-ui">全量工具</text>
  <rect x="165" y="416" width="100" height="28" rx="14" fill="#6EE7B7"/>
  <text x="215" y="435" text-anchor="middle" fill="#065F46" font-size="11" font-weight="600" font-family="system-ui">Skill 注入</text>
  <rect x="275" y="416" width="95" height="28" rx="14" fill="#6EE7B7"/>
  <text x="322" y="435" text-anchor="middle" fill="#065F46" font-size="11" font-weight="600" font-family="system-ui">沙箱隔离</text>

  <text x="210" y="475" text-anchor="middle" fill="#047857" font-size="12" font-family="system-ui">「从 AgentPool 借出 → 执行 → 归还，干净利落」</text>

  <!-- Mode ② - Multi Agent -->
  <rect x="410" y="255" width="320" height="245" rx="14" fill="#FFFBEB" stroke="#F59E0B" stroke-width="1.5"/>
  <text x="570" y="282" text-anchor="middle" fill="#92400E" font-size="15" font-weight="700" font-family="system-ui">② V2 多Agent (JS Workflow)</text>

  <rect x="435" y="296" width="270" height="44" rx="8" fill="#FDE68A"/>
  <text x="570" y="318" text-anchor="middle" fill="#92400E" font-size="13" font-weight="600" font-family="system-ui">ClaudeCodeWorkflow</text>
  <text x="570" y="333" text-anchor="middle" fill="#B45309" font-size="10" font-family="system-ui">Node.js 运行时 · JSON-RPC IPC</text>

  <line x1="570" y1="340" x2="570" y2="358" stroke="#F59E0B" stroke-width="1.5"/>
  <polygon points="570,362 564,362 570,368 576,362" fill="#F59E0B"/>

  <rect x="435" y="370" width="270" height="36" rx="8" fill="#FEF3C7"/>
  <text x="570" y="393" text-anchor="middle" fill="#B45309" font-size="11" font-weight="600" font-family="monospace">agent() · parallel() · pipeline() · phase()</text>

  <!-- Tags -->
  <rect x="435" y="416" width="85" height="28" rx="14" fill="#FCD34D"/>
  <text x="477" y="435" text-anchor="middle" fill="#92400E" font-size="10" font-weight="600" font-family="system-ui">Schema 验证</text>
  <rect x="528" y="416" width="80" height="28" rx="14" fill="#FCD34D"/>
  <text x="568" y="435" text-anchor="middle" fill="#92400E" font-size="10" font-weight="600" font-family="system-ui">Resume 缓存</text>
  <rect x="616" y="416" width="70" height="28" rx="14" fill="#FCD34D"/>
  <text x="651" y="435" text-anchor="middle" fill="#92400E" font-size="10" font-weight="600" font-family="system-ui">Budget</text>

  <text x="570" y="475" text-anchor="middle" fill="#B45309" font-size="12" font-family="system-ui">「声明式 API 编排多 Agent 协作」</text>
</svg>

<br>

</div>

### 模式①：V2 单Agent

单一 WorkAgent 独立完成一个完整任务。从 `AgentPool` 借出 → 执行 → 归还。

#### 执行链路

```
    AgentPool.acquire()
         │
    ┌────▼─────────────────────────────────────────────────────┐
    │                ReActCore.run_react()                      │
    │                                                          │
    │  ┌──────────────────────────────────────────────────────┐│
    │  │ [Layer 1] ReActDepth  —  深度控制 (max_rounds=10)     ││
    │  ├──────────────────────────────────────────────────────┤│
    │  │ [Layer 2] ReActCore ★ —  LLM → Tool → Observe → 循环 ││
    │  ├──────────────────────────────────────────────────────┤│
    │  │ [Layer 3] Reflection  —  质量评估 · 结果反思          ││
    │  ├──────────────────────────────────────────────────────┤│
    │  │ [Layer 4] KEPA        —  重试 / 失败决策              ││
    │  └──────────────────────────────────────────────────────┘│
    │                    │                                     │
    │              ┌─────▼──────┐                              │
    │              │ LLM Router │                              │
    │              └─────┬──────┘                              │
    │                    │                                     │
    │    ┌───────────────┼───────────────┐                     │
    │    ▼               ▼               ▼                     │
    │ 内置工具 (10)    MCP 工具 (25+)  第三方插件               │
    └──────────────────────────────────────────────────────────┘
         │
         AgentPool.release()
```

### 模式②：V2 多Agent (JS Workflow)

基于 **Node.js 运行时** 的 Claude Code 风格工作流引擎。多个 Agent 通过声明式 API 编排协作。

#### 编排示例

```javascript
// 📄 workflow.js
export const meta = {
  name: "hot_search_analysis",
  description: "搜索多平台热搜并生成对比报告",
  phases: [{ title: "搜索" }, { title: "分析" }]
}

export default async function() {
  phase("搜索")

  // 并行搜索两个平台
  const [baidu, weibo] = await parallel([
    () => agent("搜索百度热搜 TOP 20", { label: "百度热搜" }),
    () => agent("搜索微博热搜 TOP 20", { label: "微博热搜" })
  ])

  phase("分析")
  const report = await agent(`综合对比分析以下数据并生成报告:\n百度: ${baidu}\n微博: ${weibo}`, {
    label: "对比分析",
    schema: { type: "object", properties: { summary: { type: "string" } } }
  })

  return report
}
```

#### 编排 API

| 函数 | 签名 | 语义 |
|------|------|------|
| `agent` | `agent(prompt, opts?)` | 启动一个子 Agent 执行子任务 |
| `parallel` | `parallel([thunks])` | 并行执行 → 屏障等待 → 收集结果 |
| `pipeline` | `pipeline(items, ...stages)` | 流水线，逐阶段传递每个 item |
| `phase` | `phase(title)` | 标记当前阶段（进度显示分组） |
| `log` | `log(msg)` | 输出进度消息 |
| `budget` | `.total / .spent() / .remaining()` | Token 预算追踪硬上限 |

### V2 内置工具 (10 个)

| 工具 | 用途 | 标签 | 沙箱 |
|------|------|------|:----:|
| `web_search` | 多引擎联网搜索 (百度/知乎/微博/抖音) | 🔍 | — |
| `fetch_url` | HTTP GET 抓取网页/API，自动解析热搜 | 🌐 | — |
| `read_file` | 读取文件/目录 (图片/PDF) | 📖 | — |
| `write_file` | 新建写入文件 (报告/脚本/HTML) | ✍️ | — |
| `edit_file` | 精确替换文件某几行 | ✂️ | — |
| `search_files` | 文件名 glob + 内容正则搜索 | 🔎 | — |
| `execute_python` | 沙盒/本地执行 Python | 🐍 | ✅ |
| `execute_shell` | 沙盒/本地执行 Shell 命令 | 💻 | ✅ |
| `git` | Git 版本控制 (status/add/commit/log) | 📦 | — |
| `write_todos` | 多步骤任务清单 | ✅ | — |

### V2 MCP 工具 (25+ 个)

> 自动发现 `mcp/` 目录和 `.mcp.json` 配置，运行时即插即用。支持 5s 超时并行连接。

`Playwright` · `CodeGraph` · `Weather` · `Translator` · `DataAnalysis` · `GUI Automation` · `Text Processing` · `Image Generation` · `Web Scraper` · `Search Engine` · `System Toolbox` · `Game` · `Fun` · `Advanced Automation` · `Sandbox Tools` · `OpenClaw` · 及更多 MCP 标准服务器

<br>

---

## 四、架构对比

| 维度 | V1 队长-队员 | V2 单Agent | V2 多Agent (JS Workflow) |
|------|:------------:|:----------:|:------------------------:|
| **协作模式** | Leader ↔ Worker 上下级分工 | 独立执行 | 平等编排协作 |
| **决策方式** | 队长 ReAct 循环 | ReActCore 中间件链 | 脚本编排 (JS) |
| **并行能力** | `batch_delegate` 批量并行 | 单线程 | `parallel()` 原生并行 |
| **通信协议** | MessageBus 消息传递 | 无 (单一 Agent) | JSON-RPC IPC |
| **记忆系统** | ContextMemory + RAG + STM + 向量库 | temp_memory + RAG | temp_memory (每次重置) |
| **重试机制** | KEPA 反思 (≤3 次) | 中间件 KEPA | 外部脚本控制 |
| **适用场景** | 多步骤复杂任务 | 快速问答 · 单步操作 | 复杂编排 · 多步协作 |
| **技术实现** | 纯 Python | 纯 Python + MCP | Node.js + Python IPC |
| **最大轮次** | 3 (可配) | 10 (可配) | 按需 |
| **Agent 管理** | V1LeaderPool | AgentPool (8 预热) | AgentPool (8 预热) |
| **学习成本** | 📘 中等 | 📗 低 | 📙 较高 (需 JS) |

<br>

---

## 五、功能矩阵

| 能力 | V1 | V2 单Agent | V2 多Agent |
|------|:--:|:----------:|:----------:|
| LLM 多路由 (DeepSeek/GLM) | ✅ | ✅ | ✅ |
| ToolRegistry 35+ 工具 | ✅ | ✅ | ✅ |
| RAG 检索增强 | ✅ | ✅ | — |
| 短期记忆 (STM) | ✅ | ✅ | — |
| 向量记忆 (ChromaDB) | ✅ | ✅ | — |
| 文件写入桌面 | ✅ | ✅ | ✅ |
| WebSocket 实时通信 | ✅ | ✅ | ✅ |
| JS Workflow 编排 | — | — | ✅ |
| Schema 强制验证 | — | — | ✅ |
| Resume 缓存 | — | — | ✅ |
| Budget 追踪 | — | — | ✅ |
| 中间件链扩展 | — | ✅ | — |
| AgentPool 池化 | — | ✅ | ✅ |

> **选型建议**：需要搜索 + 分析 + 写文件多步 → V1；快速问答、单步工具调用 → V2 单Agent；需要编排多 Agent 协作 + Schema 验证 → V2 多Agent JS Workflow

<br>

---

## 六、快速开始

```bash
# 启动
git clone <repo> && cd 小雷版agent
cp .env.example .env       # 填入 DEEPSEEK_API_KEY / ZHIPUAI_API_KEY
python main.py             # 访问 http://127.0.0.1:8001

# 选项
DEV_MODE=true  python main.py    # 热重载开发
AGENT_PORT=8080 python main.py   # 自定义端口
```

<br>

---

## 七、项目结构

```
小雷版agent/
├── main.py                  🚀 FastAPI 入口
├── api/
│   ├── pages.py             🎨 前端页面路由
│   └── routes/
│       ├── chat.py          💬 核心聊天 API (V1 入口)
│       └── chat_ws.py       🔌 WebSocket
├── core/                    ⚙️ 引擎
│   ├── agent_system.py      ⭐ V1 架构 (Leader + Worker)
│   ├── engine/
│   │   ├── llm_backend.py   🧠 LLM 多路由
│   │   └── skill_dispatcher.py  🎯 技能调度
│   ├── multi_agent_v2/      ⭐ V2 架构
│   │   ├── agents/          🤖 WorkAgent · ReActCore · Middleware
│   │   ├── tools/           🛠️ ToolRegistry (35+)
│   │   └── workflow/        📋 JS Workflow 引擎
│   ├── memory/              🗃️ 三层记忆 (STM + Vector + Evolution)
│   ├── search/              🔍 RAG 搜索引擎
│   └── mcp/                 🔌 MCP 客户端
├── mcp/                     🔗 MCP 服务器 (18 台)
├── static/                  🎨 前端
├── config/                  📝 配置
└── plugin/                  🔌 插件
```

<br>

---

<div align="center">
  <sub>
  <b>🦞 小雷版小龙虾 AI Agent</b> · 双架构驱动 · 35+ 工具 · 三层记忆 · 工业级稳定
  </sub>
</div>

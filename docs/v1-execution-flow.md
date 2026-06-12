# V1 架构执行流程图

## 1. 主流程 — 队长 ReAct 循环

```mermaid
graph TB
    Start(["用户任务输入"]) --> Supervise["LeaderAgent.supervise_task()"]

    subgraph react["ReAct 主循环"]
        direction TB
        Round{"round < max_rounds?"}
        Think["_react_think() 队长思考"]
        DoneCheck{"thought.done?"}
        Act["_react_act() 执行行动"]
        Observe["记录 Observation"]
        Publish["publish_progress()"]

        Round -->|"是"| Think
        Think --> DoneCheck
        DoneCheck -->|"是"| Round
        DoneCheck -->|"否"| Act
        Act --> Observe
        Observe --> Publish
        Publish --> Round
    end

    Supervise --> react
    Round -->|"否 / 完成"| Result["返回执行结果"]

    style Start fill:#d3f9d8,stroke:#2f9e44
    style Result fill:#c5f6fa,stroke:#0c8599
    style react fill:#f8f9fa,stroke:#868e96
```

## 2. Thought 阶段 — 队长决策

```mermaid
graph TB
    ThinkStart(["_react_think()"]) --> BuildCtx["构建上下文<br/>history + results + tool_hints"]

    BuildCtx --> TaskType{"任务类型判断"}

    TaskType -->|"天气/气温"| WeatherHint["提示: skill_execute<br/>weather"]
    TaskType -->|"搜索/爬取"| SearchHint["提示: web_search"]
    TaskType -->|"翻译"| TranslateHint["提示: skill_execute<br/>translator"]
    TaskType -->|"写/创建/文件"| WriteHint["提示: write_file"]
    TaskType -->|"执行/代码"| CodeHint["提示: execute_python"]
    TaskType -->|"其他"| NoHint["无特殊提示"]

    WeatherHint --> LLM["LLM 输出 JSON"]
    SearchHint --> LLM
    TranslateHint --> LLM
    WriteHint --> LLM
    CodeHint --> LLM
    NoHint --> LLM

    LLM --> Parse{"解析成功?"}
    Parse -->|"是"| Return["返回 thought"]
    Parse -->|"否"| Fallback["返回 done=True"]

    style ThinkStart fill:#e5dbff,stroke:#5f3dc4
    style LLM fill:#fff4e6,stroke:#e67700
    style Fallback fill:#ffe3e3,stroke:#c92a2a
```

## 3. Action 阶段 — 两种行动类型

```mermaid
graph TB
    ActStart(["_react_act()"]) --> ActionType{"action.type?"}

    ActionType -->|"tool"| ToolName{"tool_name 存在?"}
    ToolName -->|"是"| ExecTool["_execute_tool(tool_name, args)"]
    ToolName -->|"否"| ToolErr["返回 error: 未指定工具"]

    ActionType -->|"delegate"| HasWorker{"有可用 Worker?"}
    HasWorker -->|"是"| SendMsg["发送 AgentMessage<br/>→ worker.process_message()"]
    HasWorker -->|"否"| WorkerErr["返回 error: 无可用 Worker"]

    ActionType -->|"其他"| UnknownErr["返回 error: 未知类型"]

    ExecTool --> ToolResult["返回工具执行结果"]
    SendMsg --> ParseResult["解析 Worker 结果"]
    ParseResult --> WorkerResult["返回 Worker 结果"]

    style ActStart fill:#e5dbff,stroke:#5f3dc4
    style ExecTool fill:#ffe8cc,stroke:#d9480f
    style SendMsg fill:#c5f6fa,stroke:#0c8599
```

## 4. Worker 执行流程 — _handle_message()

```mermaid
graph TB
    MsgIn(["收到 AgentMessage"]) --> RoleConfig["获取角色配置<br/>role + desc + fmt"]

    RoleConfig --> RAG["RAG 检索<br/>_rag_query()"]
    RAG --> GetTools["_get_tools_for_task()"]
    GetTools --> HasTools{"有工具?"}

    HasTools -->|"有"| LLMTools["_llm_with_tools()<br/>LLM + 函数调用"]
    HasTools -->|"无"| LLMJson["_llm_json()<br/>纯 JSON 输出"]

    LLMTools --> ToolCalls{"返回 tool_calls?"}
    ToolCalls -->|"有"| ExecCalls["_execute_tool_calls()<br/>并行执行"]
    ToolCalls -->|"无"| SkipExec["跳过工具执行"]

    ExecCalls --> ProcessResults["_process_tool_results()<br/>汇总结果"]
    SkipExec --> KEPA

    LLMJson --> KEPA["_kepa_reflect()<br/>置信度评估"]
    ProcessResults --> KEPA

    KEPA --> KEPADecision{"KEPA 决策"}
    KEPADecision -->|"continue + >=0.85"| OK["返回成功结果"]
    KEPADecision -->|"retry"| Retry["重试 (最多3次)"]
    KEPADecision -->|"fail"| Fail["返回失败"]

    Retry --> LLMTools

    style MsgIn fill:#d3f9d8,stroke:#2f9e44
    style OK fill:#c5f6fa,stroke:#0c8599
    style Fail fill:#ffe3e3,stroke:#c92a2a
```

## 5. 工具调用格式 — LLM 响应解析

```mermaid
graph TB
    LLMResp(["LLM 响应"]) --> IsDict{"是 dict?"}

    IsDict -->|"是"| DirectReturn["直接返回"]
    IsDict -->|"否"| Clean["清洗文本<br/>strip json/code 标记"]

    Clean --> JsonParse{"JSON 解析成功?"}
    JsonParse -->|"是"| ParsedReturn["返回解析结果"]
    JsonParse -->|"否"| TextExtract["_extract_tool_calls_from_text()<br/>正则提取工具调用"]

    TextExtract --> HasMatch{"匹配到工具?"}
    HasMatch -->|"是"| TextResult["返回 tool_calls"]
    HasMatch -->|"否"| EmptyResult["返回空 dict"]

    style LLMResp fill:#fff4e6,stroke:#e67700
    style DirectReturn fill:#d3f9d8,stroke:#2f9e44
    style TextExtract fill:#ffe8cc,stroke:#d9480f
    style EmptyResult fill:#ffe3e3,stroke:#c92a2a
```

## 6. 端到端数据流

```mermaid
graph LR
    User["用户"] -->|"任务描述"| Leader["队长 LeaderAgent"]
    Leader -->|"ReAct: Thought"| Leader
    Leader -->|"tool: 直接调用"| Tools["工具执行"]
    Leader -->|"delegate: 分配子任务"| Worker1["队员1"]
    Leader -->|"delegate: 分配子任务"| Worker2["队员2"]
    Leader -->|"delegate: 分配子任务"| Worker3["队员3"]

    Worker1 -->|"process_message"| WorkerExec1["工具调用 + KEPA"]
    Worker2 -->|"process_message"| WorkerExec2["工具调用 + KEPA"]
    Worker3 -->|"process_message"| WorkerExec3["工具调用 + KEPA"]

    WorkerExec1 -->|"结果"| Leader
    WorkerExec2 -->|"结果"| Leader
    WorkerExec3 -->|"结果"| Leader

    Tools -->|"结果"| Leader
    Leader -->|"analyze: 分析结果"| Leader
    Leader -->|"完成"| Result["最终结果"]

    style User fill:#d3f9d8,stroke:#2f9e44
    style Leader fill:#e5dbff,stroke:#5f3dc4
    style Worker1 fill:#c5f6fa,stroke:#0c8599
    style Worker2 fill:#c5f6fa,stroke:#0c8599
    style Worker3 fill:#c5f6fa,stroke:#0c8599
    style Result fill:#d3f9d8,stroke:#2f9e44
```

## 7. 关键方法调用栈

```
LeaderAgent.supervise_task()
  ├── _react_think()           # 队长思考 → LLM 决策
  ├── _react_act()             # 执行行动
  │   ├── [tool]     → _execute_tool()          # 直接调用工具
  │   └── [delegate] → worker.process_message()  # 分配给队员
  │       └── _handle_message()
  │           ├── _rag_query()                   # RAG 检索
  │           ├── _get_tools_for_task()           # 获取工具列表
  │           ├── _llm_with_tools() / _llm_json() # LLM 调用
  │           ├── _execute_tool_calls()           # 并行执行工具
  │           ├── _process_tool_results()         # 汇总工具结果
  │           └── _kepa_reflect()                # KEPA 置信度评估
  └── (循环直到 done 或 max_rounds)
```

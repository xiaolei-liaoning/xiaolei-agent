# 对话历史压缩系统 - 流程图

## 📊 系统架构流程图

```mermaid
graph TB
    Start[用户输入] --> Check{对话历史<br/>是否过长?}
    
    Check -->|是| Compress[压缩对话历史]
    Check -->|否| Query[处理用户查询]
    
    Compress --> Determine[确定压缩级别]
    Determine -->|≤10轮| Short[短期摘要]
    Determine -->|≤50轮| Medium[中期摘要]
    Determine -->|>50轮| Long[长期摘要]
    
    Short --> Filter1[过滤最近10轮]
    Medium --> Filter2[过滤最近50轮]
    Long --> Filter3[过滤最近30天]
    
    Filter1 --> Format1[格式化对话文本]
    Filter2 --> Format2[格式化对话文本]
    Filter3 --> Format3[格式化对话文本]
    
    Format1 --> LLM1[LLM生成摘要]
    Format2 --> LLM2[LLM生成摘要]
    Format3 --> LLM3[LLM生成摘要]
    
    LLM1 --> Extract1[提取关键要点]
    LLM2 --> Extract2[提取关键要点]
    LLM3 --> Extract3[提取关键要点]
    
    Extract1 --> Topic1[识别主题]
    Extract2 --> Topic2[识别主题]
    Extract3 --> Topic3[识别主题]
    
    Topic1 --> Store1[存储到向量库]
    Topic2 --> Store2[存储到向量库]
    Topic3 --> Store3[存储到向量库]
    
    Store1 --> Save1[保存到文件]
    Store2 --> Save2[保存到文件]
    Store3 --> Save3[保存到文件]
    
    Save1 --> Cache[更新缓存]
    Save2 --> Cache
    Save3 --> Cache
    
    Cache --> Query
    
    Query --> NeedContext{需要<br/>历史上下文?}
    
    NeedContext -->|是| Search[检索相关上下文]
    NeedContext -->|否| RAG[RAG查询]
    
    Search --> CheckCache{检查缓存}
    CheckCache -->|命中| ReturnCache[返回缓存结果]
    CheckCache -->|未命中| VectorSearch[向量检索]
    
    VectorSearch --> FilterTime[时间范围过滤]
    FilterTime --> Sort[按相似度排序]
    Sort --> ReturnContext[返回上下文]
    
    ReturnCache --> Enhance[增强RAG查询]
    ReturnContext --> Enhance
    
    Enhance --> RAG
    
    RAG --> Generate[生成回答]
    Generate --> End[返回用户]
    
    style Start fill:#e1f5e1
    style End fill:#e1f5e1
    style Compress fill:#fff4e1
    style Search fill:#e1f0ff
    style RAG fill:#f0e1ff
    style LLM1 fill:#ffe1f0
    style LLM2 fill:#ffe1f0
    style LLM3 fill:#ffe1f0
```

---

## 🔄 对话压缩详细流程

```mermaid
sequenceDiagram
    participant User as 用户
    participant System as 系统
    participant Compressor as 压缩器
    participant LLM as LLM
    participant VectorDB as 向量库
    participant File as 文件存储

    User->>System: 输入对话历史
    System->>Compressor: compress_history()
    
    Compressor->>Compressor: 确定压缩级别
    Compressor->>Compressor: 过滤对话轮数
    
    Compressor->>Compressor: 格式化对话文本
    Compressor->>LLM: 生成摘要请求
    LLM->>Compressor: 返回摘要文本
    
    Compressor->>Compressor: 提取关键要点
    Compressor->>Compressor: 识别主题
    
    Compressor->>VectorDB: 存储摘要向量
    Compressor->>File: 保存摘要文件
    
    Compressor->>Compressor: 更新缓存
    Compressor->>System: 返回压缩结果
    System->>User: 显示压缩摘要
```

---

## 🔍 上下文检索详细流程

```mermaid
sequenceDiagram
    participant User as 用户
    participant System as 系统
    participant Compressor as 压缩器
    participant Cache as 缓存
    participant VectorDB as 向量库

    User->>System: 提出查询
    System->>Compressor: get_context(query)
    
    Compressor->>Cache: 检查缓存
    alt 缓存命中
        Cache->>Compressor: 返回缓存结果
        Compressor->>System: 返回上下文
    else 缓存未命中
        Compressor->>VectorDB: 向量检索
        VectorDB->>Compressor: 返回相关记忆
        
        Compressor->>Compressor: 过滤对话类记忆
        Compressor->>Compressor: 时间范围过滤
        Compressor->>Compressor: 按相似度排序
        
        Compressor->>Cache: 更新缓存
        Compressor->>System: 返回上下文
    end
    
    System->>System: 增强RAG查询
    System->>User: 返回增强回答
```

---

## 📊 数据流向图

```mermaid
graph LR
    subgraph 输入层
        A[对话历史] --> B[压缩器]
        C[用户查询] --> B
    end
    
    subgraph 处理层
        B --> D[级别判断]
        D --> E[LLM摘要]
        E --> F[特征提取]
        F --> G[主题识别]
    end
    
    subgraph 存储层
        G --> H[向量库]
        G --> I[文件存储]
        G --> J[缓存]
    end
    
    subgraph 检索层
        K[用户查询] --> L[缓存检查]
        L -->|未命中| M[向量检索]
        M --> N[结果过滤]
        N --> O[排序]
    end
    
    subgraph 输出层
        O --> P[上下文增强]
        P --> Q[RAG查询]
        Q --> R[最终回答]
    end
    
    style A fill:#e1f5e1
    style C fill:#e1f5e1
    style R fill:#e1f5e1
    style H fill:#fff4e1
    style I fill:#fff4e1
    style J fill:#fff4e1
```

---

## 🎯 核心功能流程

### 1. 压缩流程

```mermaid
graph TD
    A[开始压缩] --> B{检查历史长度}
    B -->|≤10轮| C[短期摘要]
    B -->|≤50轮| D[中期摘要]
    B -->|>50轮| E[长期摘要]
    
    C --> F[过滤最近10轮]
    D --> G[过滤最近50轮]
    E --> H[过滤最近30天]
    
    F --> I[格式化文本]
    G --> I
    H --> I
    
    I --> J{LLM可用?}
    J -->|是| K[LLM生成摘要]
    J -->|否| L[备用摘要方案]
    
    K --> M[提取关键要点]
    L --> M
    
    M --> N[识别主题]
    N --> O[存储向量库]
    N --> P[保存文件]
    
    O --> Q[更新缓存]
    P --> Q
    Q --> R[返回结果]
    
    style A fill:#e1f5e1
    style R fill:#e1f5e1
    style K fill:#ffe1f0
```

### 2. 检索流程

```mermaid
graph TD
    A[开始检索] --> B[接收查询]
    B --> C{检查缓存}
    
    C -->|命中| D[返回缓存]
    C -->|未命中| E[向量检索]
    
    E --> F[获取候选结果]
    F --> G[过滤对话类]
    G --> H{有时间范围?}
    
    H -->|是| I[时间过滤]
    H -->|否| J[跳过过滤]
    
    I --> K[相似度排序]
    J --> K
    
    K --> L[限制结果数]
    L --> M[更新缓存]
    M --> N[格式化结果]
    N --> O[返回上下文]
    
    style A fill:#e1f5e1
    style O fill:#e1f5e1
    style D fill:#fff4e1
```

---

## 🗂️ 存储结构图

```mermaid
graph TB
    subgraph 向量库[ChromaDB]
        V1[短期摘要向量]
        V2[中期摘要向量]
        V3[长期摘要向量]
    end
    
    subgraph 文件存储[文件系统]
        F1[summary_user1_short_20260420.json]
        F2[summary_user1_medium_20260420.json]
        F3[summary_user1_long_20260420.json]
    end
    
    subgraph 内存缓存[缓存]
        C1[context_user1_query1]
        C2[context_user1_query2]
    end
    
    V1 --> M[元数据]
    V2 --> M
    V3 --> M
    
    M -->|包含| M1[用户ID]
    M -->|包含| M2[压缩级别]
    M -->|包含| M3[主题]
    M -->|包含| M4[时间戳]
    
    F1 --> S[摘要内容]
    F2 --> S
    F3 --> S
    
    S -->|包含| S1[摘要文本]
    S -->|包含| S2[关键要点]
    S -->|包含| S3[主题列表]
    S -->|包含| S4[原始轮数]
    
    C1 --> R[检索结果]
    C2 --> R
    
    R -->|包含| R1[查询文本]
    R -->|包含| R2[上下文列表]
    R -->|包含| R3[时间戳]
    
    style 向量库 fill:#e1f0ff
    style 文件存储 fill:#fff4e1
    style 内存缓存 fill:#ffe1f0
```

---

## ⚡ 性能优化流程

```mermaid
graph TD
    A[请求到达] --> B{检查缓存}
    
    B -->|命中| C[直接返回<br/>~1ms]
    B -->|未命中| D[向量检索<br/>~100ms]
    
    D --> E{结果数量}
    E -->|足够| F[返回结果]
    E -->|不足| G[扩展检索范围]
    
    G --> D
    
    F --> H[更新缓存]
    H --> I[返回结果<br/>~101ms]
    
    C --> J[定期清理]
    I --> J
    
    J --> K{缓存过期?}
    K -->|是| L[删除缓存]
    K -->|否| M[保留缓存]
    
    L --> N[结束]
    M --> N
    
    style A fill:#e1f5e1
    style C fill:#a8e6cf
    style I fill:#a8e6cf
    style N fill:#e1f5e1
```

---

## 🔄 自动维护流程

```mermaid
graph TD
    A[定时任务触发] --> B{检查摘要数量}
    
    B -->|超过阈值| C[清理旧摘要]
    B -->|正常| D[跳过清理]
    
    C --> E[删除30天前文件]
    E --> F[更新索引]
    
    F --> G{检查向量库}
    G -->|需要清理| H[清理旧向量]
    G -->|正常| I[跳过向量清理]
    
    H --> J[更新统计]
    I --> J
    
    D --> J
    J --> K[记录日志]
    K --> L[等待下次触发]
    
    L --> A
    
    style A fill:#fff4e1
    style L fill:#fff4e1
    style C fill:#ffd3b6
    style H fill:#ffd3b6
```

---

## 📈 压缩效果对比

```mermaid
graph LR
    subgraph 原始对话
        A1[第1-10轮<br/>5000字]
        A2[第11-50轮<br/>20000字]
        A3[第51-100轮<br/>25000字]
    end
    
    subgraph 压缩后
        B1[短期摘要<br/>500字<br/>压缩率90%]
        B2[中期摘要<br/>1000字<br/>压缩率95%]
        B3[长期摘要<br/>800字<br/>压缩率97%]
    end
    
    A1 -->|压缩| B1
    A2 -->|压缩| B2
    A3 -->|压缩| B3
    
    style A1 fill:#ffe1e1
    style A2 fill:#ffe1e1
    style A3 fill:#ffe1e1
    style B1 fill:#a8e6cf
    style B2 fill:#a8e6cf
    style B3 fill:#a8e6cf
```

---

## 🎯 使用场景流程

### 场景1：长时间对话后压缩

```mermaid
sequenceDiagram
    participant U as 用户
    participant S as 系统
    participant C as 压缩器
    
    U->>S: 进行50轮对话
    S->>S: 检测到历史过长
    S->>C: 自动触发压缩
    C->>C: 生成中期摘要
    C->>C: 存储摘要
    C->>S: 压缩完成
    S->>U: 提示对话已压缩
```

### 场景2：查询历史上下文

```mermaid
sequenceDiagram
    participant U as 用户
    participant S as 系统
    participant C as 压缩器
    participant R as RAG
    
    U->>S: "我之前说过什么关于机器学习的？"
    S->>C: 获取相关上下文
    C->>C: 检索历史摘要
    C->>S: 返回相关上下文
    S->>R: 增强RAG查询
    R->>S: 返回增强回答
    S->>U: "您之前讨论过..."
```

### 场景3：定期自动维护

```mermaid
sequenceDiagram
    participant T as 定时任务
    participant C as 压缩器
    participant V as 向量库
    participant F as 文件系统
    
    T->>C: 触发清理任务
    C->>C: 检查旧摘要
    C->>F: 删除30天前文件
    C->>V: 清理旧向量
    C->>C: 更新统计
    C->>T: 清理完成
```

---

## 🚀 集成到RAG系统

```mermaid
graph TB
    A[用户查询] --> B{需要历史上下文?}
    
    B -->|是| C[调用压缩器]
    B -->|否| D[直接RAG查询]
    
    C --> E[检索相关摘要]
    E --> F[构建增强提示]
    
    F --> G[RAG查询]
    D --> G
    
    G --> H[生成回答]
    H --> I[返回用户]
    
    style A fill:#e1f5e1
    style I fill:#e1f5e1
    style C fill:#e1f0ff
    style G fill:#f0e1ff
```

---

**流程图说明：**

1. **系统架构流程图**：展示整个系统的顶层架构和数据流向
2. **对话压缩详细流程**：展示压缩过程的时序交互
3. **上下文检索详细流程**：展示检索过程的时序交互
4. **数据流向图**：展示数据在各层之间的流动
5. **核心功能流程**：详细展示压缩和检索的决策逻辑
6. **存储结构图**：展示数据在不同存储介质中的组织方式
7. **性能优化流程**：展示缓存策略和性能优化机制
8. **自动维护流程**：展示定期清理和维护任务
9. **压缩效果对比**：展示压缩前后的数据量对比
10. **使用场景流程**：展示典型使用场景的交互流程
11. **集成到RAG系统**：展示如何与现有RAG系统集成

所有流程图都使用Mermaid语法，可以在支持Mermaid的Markdown查看器中渲染。
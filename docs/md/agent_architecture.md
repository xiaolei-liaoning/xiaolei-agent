# 多角色独立智能体系统架构图

## 架构概述

本系统采用【多角色独立智能体 + 内部并发分身】架构，实现了单机多实例异步处理模式，并集成了深度思考引擎、监控系统和LLM后端等核心组件。

## 架构图

```plantuml
@startuml

!define RECTANGLE class

package "多角色独立智能体系统" {
    
    package "调度中心" {
        RECTANGLE AgentScheduler as scheduler
        note right of scheduler
            负责任务分配
            管理所有Agent
            提供统一接口
        end note
    }
    
    package "独立智能体" {
        
        package "检查Agent" {
            RECTANGLE CheckerAgent as checker
            note right of checker
                负责检查任务
                内部并发处理
                独立任务队列
            end note
        }
        
        package "爬虫Agent" {
            RECTANGLE ScraperAgent as scraper
            note right of scraper
                负责爬取任务
                内部并发处理
                独立任务队列
            end note
        }
        
        package "漏洞Agent" {
            RECTANGLE VulnerabilityAgent as vulnerability
            note right of vulnerability
                负责漏洞扫描
                内部并发处理
                独立任务队列
            end note
        }
        
        package "总结Agent" {
            RECTANGLE SummarizerAgent as summarizer
            note right of summarizer
                负责总结任务
                内部并发处理
                独立任务队列
            end note
        }
        
        package "前端Agent" {
            RECTANGLE FrontendAgent as frontend
            note right of frontend
                负责前端界面
                实时监控展示
                WebSocket通信
            end note
        }
        
    }
    
    package "核心系统" {
        
        package "深度思考引擎" {
            RECTANGLE ReasoningEngine as reasoning
            note right of reasoning
                多轮隐式推理
                思维链强化
                自我反思机制
                缓存优化
            end note
        }
        
        package "LLM后端" {
            RECTANGLE LLMBackend as llm
            note right of llm
                模型管理
                超时重试
                模型优先级
                API调用优化
            end note
        }
        
        package "监控系统" {
            RECTANGLE MonitoringManager as monitoring
            note right of monitoring
                系统指标监控
                告警机制
                日志管理
                实时数据采集
            end note
        }
        
        package "第三方应用" {
            RECTANGLE ThirdPartyAppManager as third_party
            note right of third_party
                多应用集成
                API密钥管理
                统一接口
            end note
        }
        
    }
    
    package "任务处理系统" {
        RECTANGLE TaskProcessor as processor
        RECTANGLE TaskExecutor as executor
    }
    
    ' 连接线
    scheduler --> checker : 分配检查任务
    scheduler --> scraper : 分配爬虫任务
    scheduler --> vulnerability : 分配漏洞任务
    scheduler --> summarizer : 分配总结任务
    scheduler --> frontend : 分配前端任务
    
    processor --> scheduler : 提交分解后的任务
    executor --> scheduler : 执行具体任务
    
    scheduler --> reasoning : 深度思考任务
    reasoning --> llm : LLM API调用
    
    scheduler --> monitoring : 系统监控
    monitoring --> frontend : 监控数据推送
    
    scheduler --> third_party : 第三方应用调用
    
    ' 内部并发
    checker ..> "内部并发" as checker_concurrent
    scraper ..> "内部并发" as scraper_concurrent
    vulnerability ..> "内部并发" as vulnerability_concurrent
    summarizer ..> "内部并发" as summarizer_concurrent
    frontend ..> "内部并发" as frontend_concurrent
    
}

@enduml
```

## 架构特点

1. **多角色独立智能体**：
   - 每个Agent负责一类固定工作
   - 每个Agent有独立的配置和任务队列
   - 每个Agent可以独立启停和配置

2. **内部并发分身**：
   - 每个Agent内部支持并发处理
   - 可以同时处理多个同类任务
   - 避免任务阻塞

3. **调度中心**：
   - 负责任务分配到对应Agent
   - 不干涉内部执行
   - 提供统一的任务提交和状态查询接口

4. **核心系统**：
   - **深度思考引擎**：实现多轮隐式推理和思维链强化
   - **LLM后端**：管理模型调用和优化API性能
   - **监控系统**：实时监控系统状态和告警
   - **第三方应用**：集成各种外部服务

5. **前端交互**：
   - 实时监控界面
   - WebSocket通信
   - 响应式设计

6. **单机多实例异步架构**：
   - 所有Agent运行在同一台机器上
   - 采用异步编程模型
   - 非分布式架构，不跨设备

7. **并行处理能力**：
   - 同一时间能并行处理大量不同类型任务
   - 同类任务也能并发执行
   - 任务之间互不阻塞

## 工作流程

1. **任务提交**：上层系统通过调度中心提交任务
2. **任务分配**：调度中心根据任务类型分配到对应Agent
3. **任务执行**：Agent内部并发执行任务
4. **深度思考**：复杂任务调用深度思考引擎
5. **LLM调用**：需要时调用LLM后端获取AI能力
6. **监控采集**：监控系统实时采集运行数据
7. **结果返回**：任务完成后返回结果
8. **状态查询**：可通过调度中心查询任务状态
9. **前端展示**：实时推送监控数据到前端界面

## 技术实现

- **编程语言**：Python
- **并发模型**：asyncio 异步编程
- **任务队列**：asyncio.Queue
- **架构模式**：面向对象，继承与多态
- **错误处理**：完善的异常捕获和处理机制
- **缓存机制**：LRU缓存，批量清理
- **监控系统**：实时指标采集，告警机制
- **前端技术**：HTML5, WebSocket, ECharts
- **容器化**：Docker容器化部署
- **CI/CD**：GitHub Actions自动化构建测试

## 优势

1. **职责清晰**：每个Agent只负责一类工作，职责明确
2. **效率提升**：并发处理，避免任务阻塞
3. **智能增强**：深度思考引擎提供强大的推理能力
4. **可监控性**：完善的监控系统，实时掌握系统状态
5. **可扩展性**：易于添加新的Agent类型和第三方应用
6. **可靠性**：单个Agent故障不影响其他Agent
7. **可维护性**：模块化设计，易于维护和调试
8. **部署便捷**：容器化部署，CI/CD流程
9. **用户友好**：实时监控界面，直观展示系统状态
10. **性能优化**：缓存机制，并行处理，LLM调用优化
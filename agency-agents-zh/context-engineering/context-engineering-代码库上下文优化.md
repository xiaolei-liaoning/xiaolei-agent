================================================================================
提示词名称: 代码库上下文优化
描述: 高效加载和管理代码库上下文的策略，在保持 token 限制的同时最大化 AI 的理解能力。
使用场景:
  - 处理大型代码库
  - 优化代码生成的上下文
  - 在保持质量的同时减少 token 使用
  - 智能选择上下文文件
================================================================================

<context_selection_strategy>
优先级层级:

第一层（始终包含）:
- 用户直接提到的文件
- 当前正在编辑的文件
- 主要入口点（index.js、main.py）
- 核心配置文件

第二层（高优先级）:
- 第一层文件导入的文件
- 相关测试文件
- 类型定义/接口
- 目标文件使用的共享工具

第三层（中优先级）:
- 同一目录下的文件
- 类似文件（按名称/用途）
- 最近修改的文件
- 文档文件

第四层（低优先级）:
- 远距离依赖
- 生成的文件
- 第三方代码
- 大型数据文件
</context_selection_strategy>

<token_budget_management>
典型预算分配:
- 系统提示: 2,000-5,000 tokens
- 用户指令: 500-2,000 tokens
- 代码库上下文: 20,000-50,000 tokens
- 输出缓冲: 4,000-8,000 tokens

优化技术:

1. 选择性文件加载:
   - 只加载相关函数，而非整个文件
   - 使用 AST 解析提取特定类/函数
   - 不需要时跳过注释和文档字符串

2. 摘要化:
   - 用结构摘要替代大文件
   - 只显示函数签名而非完整实现
   - 为远距离依赖提供文件级摘要

3. 压缩:
   - 移除空白和格式
   - 在不需要理解格式时进行最小化
   - 在示例中使用缩写变量名

4. 惰性加载:
   - 从最小上下文开始
   - 仅在需要时请求额外文件
   - 迭代式上下文扩展
</token_budget_management>

<file_relevance_scoring>
评分因素:

导入距离（40%）:
- 直接导入: 1.0
- 1 跳距离: 0.7
- 2 跳距离: 0.4
- 3+ 跳距离: 0.2

时效性（20%）:
- 今天修改: 1.0
- 本周: 0.8
- 本月: 0.5
- 更早: 0.3

名称相似度（15%）:
- 精确匹配: 1.0
- 包含关键词: 0.7
- 相关术语: 0.4

目录邻近度（15%）:
- 同一目录: 1.0
- 父/子目录: 0.7
- 兄弟目录: 0.5
- 远距离: 0.2

文件类型（10%）:
- 源代码: 1.0
- 测试: 0.8
- 配置: 0.6
- 文档: 0.4

最终分数: 各因素加权求和
</file_relevance_scoring>

<context_assembly_patterns>
模式 1: 聚焦上下文
```
<target_file>
[被修改文件的完整内容]
</target_file>

<direct_dependencies>
[导入文件中的关键函数/类]
</direct_dependencies>

<type_definitions>
[使用的接口和类型]
</type_definitions>
```

模式 2: 架构上下文
```
<project_structure>
[高级目录树]
</project_structure>

<key_files>
文件: src/services/auth.ts
用途: 认证逻辑
主要导出: login(), logout(), verifyToken()

文件: src/models/User.ts
用途: 用户数据模型
主要导出: User 接口, UserSchema
</key_files>

<target_code>
[需要处理的特定代码]
</target_code>
```

模式 3: 增量上下文
```
<initial_context>
[启动所需的最小上下文]
</initial_context>

[AI 尝试执行任务]

<additional_context>
[根据 AI 需求添加更多文件]
</additional_context>

[AI 带着更多信息继续工作]
```
</context_assembly_patterns>

<smart_filtering>
上下文中应排除:
- node_modules、venv、vendor 目录
- 构建产物（dist、build、.next）
- 锁文件（package-lock.json、yarn.lock）
- 二进制文件（图片、视频、PDF）
- 大型数据文件（CSV、JSON > 100KB）
- 生成的代码（protobuf、GraphQL codegen）
- 压缩后的文件
- 日志文件

选择性包含:
- package.json（仅依赖部分）
- 配置文件（仅相关部分）
- README（仅摘要）
- 测试（与目标代码相关的部分）
</smart_filtering>

<output_format>
```
上下文优化报告
========================

TOKEN 预算:
- 总可用: [tokens]
- 系统提示: [tokens]
- 用户指令: [tokens]
- 代码库上下文: [tokens]
- 输出缓冲: [tokens]

已包含文件:
优先级  文件                          Tokens  原因
第一层    src/components/Button.tsx     450     直接目标
第一层    src/types/props.ts            200     类型定义
第二层    src/utils/classNames.ts       150     导入的工具
第二层    src/components/Button.test.tsx 300    相关测试

已排除文件:
- [file]: [排除原因]

应用的优化:
- [用于适配预算的技术]

上下文质量评分: [0-10]
- 完整性: [分数]
- 相关性: [分数]
- 效率: [分数]
```
</output_format>

================================================================================
提示词名称: 多文件推理框架
描述: 帮助 AI 跨多个文件进行推理的技术，理解复杂的交互、数据流和系统行为。
使用场景:
  - 调试跨多个文件的问题
  - 理解功能实现
  - 跨文件边界重构
  - 追踪数据在系统中的流转
================================================================================

<reasoning_strategies>
1. 依赖链追踪:
   - 从入口点开始
   - 跟随导入/调用
   - 构建执行路径
   - 识别关键决策点

2. 数据流分析:
   - 追踪数据从源到目的地
   - 识别数据转换
   - 映射状态变化
   - 查找数据依赖

3. 调用图构建:
   - 映射跨文件的函数调用
   - 识别调用层次结构
   - 发现循环依赖
   - 检测未使用的代码

4. 接口边界分析:
   - 识别模块边界
   - 理解模块间的契约
   - 查找耦合点
   - 检测抽象泄漏
</reasoning_strategies>

<prompt_structure>
```
<task>
[需要理解的内容描述]
</task>

<entry_point>
文件: [filename]
函数: [function name]
用途: [功能描述]
</entry_point>

<execution_flow>
步骤 1: [entry_point] 在 [file] 中调用 [function]
  - 目的: [why]
  - 传递的数据: [what]

步骤 2: [function] 在 [another_file] 中调用 [another_function]
  - 目的: [why]
  - 数据转换: [how]

步骤 3: [最终步骤]
  - 结果: [what]
</execution_flow>

<key_files>
[流程中每个文件的相关代码]
</key_files>

<question>
[关于多文件交互的具体问题]
</question>
```
</prompt_structure>

<analysis_techniques>
正向追踪（自顶向下）:
- 从用户操作或 API 调用开始
- 向前跟随执行路径
- 追踪数据转换
- 识别最终结果

反向追踪（自底向上）:
- 从观察到的行为或 bug 开始
- 反向追溯找到原因
- 识别所有通向该处的路径
- 找到根本原因

双向追踪:
- 从中间开始（疑似问题处）
- 同时向前和向后追踪
- 理解完整上下文
- 识别修复位置

横切关注点:
- 识别跨文件的模式
- 查找通用工具函数
- 检测重复逻辑
- 建议重构机会
</analysis_techniques>

<output_format>
```
多文件分析报告
========================

范围:
- 入口点: [文件和函数]
- 分析文件数: [count]
- 执行深度: [levels]

执行流程:
1. [file].[function]
   ↓ 调用
2. [file].[function]
   ↓ 调用
3. [file].[function]
   ↓ 返回
4. [result]

数据转换:
输入: [data structure]
  ↓ [file1 中的转换]
中间结果: [data structure]
  ↓ [file2 中的转换]
输出: [data structure]

关键交互:
- [file1] 依赖 [file2] 用于 [purpose]
- [file3] 修改 [file4] 使用的状态
- [file5] 和 [file6] 共享 [resource]

发现:
- [关于多文件行为的洞察]

改进建议:
- [改进建议]
```
</output_format>

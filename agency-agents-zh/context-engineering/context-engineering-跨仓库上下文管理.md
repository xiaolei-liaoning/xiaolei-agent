================================================================================
提示词名称: 跨仓库上下文管理
描述: 在多个相关仓库、微服务或代码库间工作时管理上下文的策略。
使用场景:
  - 微服务架构开发
  - Monorepo 管理
  - 多仓库功能开发
  - 系统级重构
================================================================================

<multi_repo_challenges>
常见问题:
- 上下文分散在不同仓库中
- 共享依赖和契约
- 版本同步
- 跨仓库数据流
- 分布式测试

上下文需求:
- 理解服务边界
- 服务间的 API 契约
- 共享类型和接口
- 配置依赖
- 部署关系
</multi_repo_challenges>

<context_organization>
仓库地图:
```
<system_architecture>
服务: user-service（仓库: user-api）
- 职责: 用户管理、认证
- 暴露: REST API 端口 3001
- 依赖: auth-service、数据库

服务: order-service（仓库: order-api）
- 职责: 订单处理
- 暴露: REST API 端口 3002
- 依赖: user-service、payment-service

服务: payment-service（仓库: payment-api）
- 职责: 支付处理
- 暴露: REST API 端口 3003
- 依赖: 外部支付网关

共享: common-types（仓库: shared-types）
- 提供: TypeScript 接口
- 使用者: 所有服务
</system_architecture>
```

接口契约:
```
<api_contracts>
user-service → order-service:
GET /api/users/:id
响应: { id, name, email, tier }

order-service → payment-service:
POST /api/payments
请求: { orderId, amount, currency }
响应: { transactionId, status }
</api_contracts>
```
</context_organization>

<context_loading_strategy>
聚焦方法:
1. 识别当前任务的主要仓库
2. 从主仓库加载相关文件
3. 从相关仓库加载接口定义
4. 包含 API 契约和共享类型
5. 添加影响交互的配置

示例:
```
<task>在 order-service 中添加订单验证</task>

<primary_context>
仓库: order-api
文件:
- src/services/orderService.ts（当前实现）
- src/validators/orderValidator.ts（现有验证）
- src/types/order.ts（订单类型）
</primary_context>

<related_context>
仓库: shared-types
文件:
- src/User.ts（验证中使用的 User 接口）

仓库: user-api
文件:
- API 契约: GET /api/users/:id（验证用户是否存在）
</related_context>

<configuration>
- 影响验证的环境变量
- 验证规则的功能开关
</configuration>
```
</context_loading_strategy>

<dependency_tracking>
跨仓库依赖:

类型依赖:
```
order-service 从 shared-types 导入:
- User 接口
- Product 接口
- OrderStatus 枚举
```

API 依赖:
```
order-service 调用 user-service:
- GET /api/users/:id（验证用户）
- GET /api/users/:id/tier（检查用户等级）

order-service 调用 payment-service:
- POST /api/payments（处理支付）
```

配置依赖:
```
order-service 需要:
- 从环境变量获取 USER_SERVICE_URL
- 从环境变量获取 PAYMENT_SERVICE_URL
- 共享数据库连接字符串
```
</dependency_tracking>

<change_impact_analysis>
跨仓库影响:

场景: 在 shared-types 中更改 User 接口
```
<impact_analysis>
已更改: shared-types/src/User.ts
- 新增字段: phoneNumber

受影响仓库:
1. user-api
   - 文件: src/models/User.ts（需要更新）
   - 测试: tests/user.test.ts（需要新测试）

2. order-api
   - 文件: src/services/orderService.ts（可能使用新字段）
   - 影响: 低（可选字段）

3. notification-service
   - 文件: src/notifiers/sms.ts（现在可以使用 phoneNumber）
   - 影响: 中（启用了新功能）

需要迁移:
- 在所有服务中更新 shared-types 版本
- 部署顺序: shared-types → user-api → order-api → notification-service
</impact_analysis>
```
</change_impact_analysis>

<output_format>
```
跨仓库上下文报告
========================

任务: [description]

主仓库:
- 名称: [repo-name]
- 加载文件数: [count]
- 上下文 tokens: [count]

相关仓库:
仓库: [name]
- 关系: [依赖于 / 被依赖 / 共享]
- 加载文件: [list]
- 使用接口: [list]

跨仓库依赖:
- 类型导入: [list]
- API 调用: [list]
- 共享配置: [list]

变更影响:
- 受影响仓库: [count]
- 破坏性变更: [是/否]
- 需要迁移: [是/否]

部署顺序:
1. [repo-name]
2. [repo-name]
3. [repo-name]

测试策略:
- 单元测试: [每个仓库]
- 集成测试: [跨仓库]
- 端到端测试: [完整系统]
```
</output_format>

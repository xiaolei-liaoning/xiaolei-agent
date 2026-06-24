================================================================================
提示词名称: 错误上下文增强
描述: 为错误提供丰富上下文的技术，帮助 AI 快速诊断和修复问题。
使用场景:
  - 调试运行时错误
  - 修复编译错误
  - 解决测试失败
  - 排查部署问题
================================================================================

<error_context_structure>
必要的错误信息:
- 错误消息（完整文本）
- 堆栈跟踪（完整）
- 错误类型/代码
- 时间戳
- 环境（开发/预发/生产）

代码上下文:
- 发生错误的文件
- 周围代码（±10 行）
- 包含错误的函数/方法
- 调用栈中的相关函数

执行上下文:
- 触发错误的输入
- 错误发生时的变量值
- 应用状态
- 最近的代码更改

环境上下文:
- 运行时版本
- 依赖版本
- 配置值
- 系统资源
</error_context_structure>

<context_enrichment_techniques>
堆栈跟踪增强:
```
<error>
TypeError: Cannot read property 'name' of undefined
  at getUserName (src/utils/user.ts:45:20)
  at renderProfile (src/components/Profile.tsx:12:15)
  at App (src/App.tsx:28:10)
</error>

<enriched_context>
文件: src/utils/user.ts（第 45 行）
```typescript
export function getUserName(user: User): string {
  // 第 45 行 - 键发生在这里
  return user.name.toUpperCase();
  //     ^^^^ user 是 undefined
}
```

文件: src/components/Profile.tsx（第 12 行）
```typescript
const Profile = ({ userId }: Props) => {
  const user = useUser(userId); // 可能返回 undefined
  // 第 12 行 - 调用 getUserName 时没有空值检查
  const name = getUserName(user);
  return <div>{name}</div>;
}
```

根本原因: 调用 getUserName 时传入了 undefined 的 user
修复: 在访问 user.name 之前添加空值检查
</enriched_context>
```

编译错误增强:
```
<error>
TS2339: Property 'email' does not exist on type 'User'
  at src/components/UserCard.tsx:15:20
</error>

<enriched_context>
当前 User 类型定义:
```typescript
interface User {
  id: string;
  name: string;
  // 缺少 email 属性
}
```

尝试访问 email 的代码:
```typescript
const UserCard = ({ user }: { user: User }) => {
  return <div>{user.email}</div>; // 此处出错
}
```

可能的修复:
1. 在 User 接口中添加 email
2. 使用可选链: user.email?
3. 检查是否使用了错误的类型
</enriched_context>
```

测试失败增强:
```
<error>
Expected: 200
Received: 404
  at tests/api/users.test.ts:25:10
</error>

<enriched_context>
测试代码:
```typescript
test('GET /api/users/:id returns user', async () => {
  const response = await request(app).get('/api/users/123');
  expect(response.status).toBe(200); // 此处失败
});
```

API 路由定义:
```typescript
app.get('/api/user/:id', getUser); // 注意: 是 'user' 而非 'users'
```

根本原因: URL 不匹配 - 路由是 /api/user/:id 但测试调用的是 /api/users/:id
修复: 将路由改为 /api/users/:id 或更新测试
</enriched_context>
```
</error_context_enrichment_techniques>

<automated_context_gathering>
检测到错误时:
1. 捕获完整错误详情
2. 加载发生错误的文件
3. 加载堆栈跟踪中的文件
4. 加载相关测试文件
5. 检查最近的 git 提交
6. 收集相关日志
7. 检查类似的过往错误

上下文优先级:
- 错误直接位置（最高优先级）
- 调用栈文件
- 最近修改的文件
- 相关配置
- 依赖版本
</automated_context_gathering>

<output_format>
```
错误诊断报告
========================

错误摘要:
类型: [error type]
消息: [error message]
位置: [file:line:column]
时间: [when]

堆栈跟踪:
[带文件上下文的完整堆栈跟踪]

根本原因分析:
[错误发生原因的解释]

受影响代码:
[带注释的相关代码段]

建议修复:
```[language]
[修复代码，包含修改前后对比]
```

测试建议:
[如何验证修复是否有效]

预防措施:
[如何防止类似错误]
```
</output_format>

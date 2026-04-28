# Coze SDK 使用指南

## 📦 安装

```bash
# 已配置国内镜像源，直接安装即可
pip install cozepy
```

## 🔑 获取 API Token 和 Bot ID

### 1. 注册 Coze 账号
访问 [https://www.coze.cn/](https://www.coze.cn/) 注册并登录

### 2. 创建 Bot
1. 点击"创建 Bot"
2. 配置 Bot 的名称、描述、人设等
3. 发布 Bot

### 3. 获取 Bot ID
- 在 Bot 详情页可以看到 Bot ID
- 格式类似：`7xxxxxxxxxxxxxxxxx`

### 4. 生成 API Token
1. 点击右上角头像 → "个人设置"
2. 找到 "API Token" 或 "个人访问令牌"
3. 点击"生成新令牌"
4. 复制并保存 Token（只显示一次）

## ⚙️ 配置环境变量

在项目根目录的 `.env` 文件中添加：

```env
# Coze 配置
COZE_API_TOKEN=your_personal_access_token_here
COZE_BOT_ID=your_bot_id_here
COZE_USER_ID=user_123  # 可选，用户标识
```

## 🚀 快速开始

### 方式 1: 使用简单客户端

```python
import asyncio
from test_coze_usage import CozeBotClient

async def main():
    # 创建客户端
    client = CozeBotClient()
    
    # 对话
    response = await client.chat("你好，请介绍一下自己")
    print(f"回复: {response}")
    
    # 关闭
    await client.close()

asyncio.run(main())
```

### 方式 2: 使用 Backend 适配器

```python
import asyncio
from core.coze_backend import CozeBackend

async def main():
    # 创建后端
    backend = CozeBackend()
    
    # 非流式调用
    messages = [{"role": "user", "content": "你好"}]
    response = await backend.chat(messages)
    print(f"回复: {response}")
    
    # 流式调用
    messages = [{"role": "user", "content": "写一首诗"}]
    async for chunk in backend.chat_stream(messages):
        print(chunk, end="", flush=True)
    
    # 查看统计
    stats = backend.get_token_stats()
    print(f"\nToken 统计: {stats}")
    
    await backend.close()

asyncio.run(main())
```

### 方式 3: 直接使用 cozepy

```python
import asyncio
from cozepy import COZE_CN_BASE_URL, CozeAsync
import os

async def main():
    # 初始化客户端
    coze = CozeAsync(
        base_url=COZE_CN_BASE_URL,
        auth_token=os.getenv("COZE_API_TOKEN")
    )
    
    bot_id = os.getenv("COZE_BOT_ID")
    
    # 创建对话
    conversation = await coze.conversations.create()
    
    # 发送消息
    message = await coze.conversations.messages.create(
        conversation_id=conversation.id,
        content="你好",
        role="user"
    )
    
    # 运行 Bot（流式）
    chat = await coze.chat.stream(
        bot_id=bot_id,
        user_id="user_123",
        additional_messages=[message]
    )
    
    # 接收响应
    async for event in chat:
        if event.event == "conversation.message.delta":
            print(event.data.content, end="", flush=True)
    
    await coze.close()

asyncio.run(main())
```

## 📝 运行测试示例

```bash
# 运行基础使用示例
python test_coze_usage.py

# 运行 Backend 适配器示例
python -m core.coze_backend
```

## 🔧 高级用法

### 多 Bot 支持

在 `core/coze_backend.py` 中配置多个 Bot：

```python
SUPPORTED_BOTS = {
    "coze-default": "bot_id_1",
    "coze-assistant": "bot_id_2",
    "coze-coder": "bot_id_3",
}

# 使用时指定 model 参数
backend = CozeBackend()
response = await backend.chat(messages, model="coze-coder")
```

### 错误处理

```python
try:
    response = await client.chat("你好")
except Exception as e:
    print(f"对话失败: {e}")
    # 可以添加重试逻辑
```

### 自定义配置

```python
# 直接传入 token 和 bot_id
client = CozeBotClient(
    token="your_token",
    bot_id="your_bot_id"
)
```

## 📊 API 参考

### CozeBotClient

| 方法 | 说明 | 参数 |
|------|------|------|
| `chat(message, stream=True)` | 与 Bot 对话 | message: 用户消息<br>stream: 是否流式输出 |
| `close()` | 关闭客户端 | - |

### CozeBackend

| 方法 | 说明 | 参数 |
|------|------|------|
| `chat(messages, ...)` | 非流式调用 | messages: 消息列表<br>model: Bot 标识 |
| `chat_stream(messages, ...)` | 流式调用 | 同上 |
| `get_token_stats()` | 获取 Token 统计 | - |
| `close()` | 关闭客户端 | - |

## ❓ 常见问题

### Q1: 如何检查是否安装成功？
```python
python -c "from cozepy import CozeAsync; print('✅ 安装成功')"
```

### Q2: Token 过期怎么办？
在 Coze 平台重新生成新的 Token，并更新 `.env` 文件

### Q3: 支持哪些功能？
- ✅ 文本对话
- ✅ 流式输出
- ✅ 多轮对话
- ✅ 多 Bot 切换
- ⚠️ 文件上传（需要额外配置）
- ⚠️ 工作流调用（需要使用工作流 API）

### Q4: 如何调试？
启用详细日志：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🔗 相关资源

- [Coze 官方文档](https://www.coze.cn/docs)
- [cozepy GitHub](https://github.com/coze-dev/cozepy)
- [Coze API 参考](https://www.coze.cn/open/docs/api)

## 💡 最佳实践

1. **保护 Token**: 不要将 Token 提交到代码仓库
2. **错误处理**: 始终添加 try-except 处理网络错误
3. **流式输出**: 对于长回复，建议使用流式提升用户体验
4. **Token 统计**: 定期查看 Token 使用情况，优化成本
5. **速率限制**: 注意 API 调用频率限制

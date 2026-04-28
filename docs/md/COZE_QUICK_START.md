# Coze SDK 快速入门

## 🎯 3 分钟快速上手

### 第一步：配置环境变量

在项目根目录创建或编辑 `.env` 文件，添加：

```env
COZE_API_TOKEN=你的API_Token
COZE_BOT_ID=你的Bot_ID
```

**如何获取？**
1. 访问 [https://www.coze.cn/](https://www.coze.cn/)
2. 注册并登录
3. 创建 Bot，复制 Bot ID
4. 在个人设置中生成 API Token

### 第二步：运行示例

```bash
# 运行完整示例（包含基础对话、流式对话、多轮对话）
python test_coze_usage.py
```

### 第三步：开始使用

```python
import asyncio
from test_coze_usage import CozeBotClient

async def main():
    client = CozeBotClient()
    response = await client.chat("你好")
    print(response)
    await client.close()

asyncio.run(main())
```

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `test_coze_usage.py` | 完整的使用示例和封装客户端 |
| `core/coze_backend.py` | 与现有 LLM 架构集成的 Backend 适配器 |
| `COZE_USAGE_GUIDE.md` | 详细的使用文档 |

## 🚀 核心功能

- ✅ **简单对话**: 一行代码调用 Bot
- ✅ **流式输出**: 实时显示回复内容
- ✅ **多轮对话**: 支持上下文连续对话
- ✅ **多 Bot 切换**: 通过 model 参数切换不同 Bot
- ✅ **Token 统计**: 自动记录使用情况
- ✅ **错误处理**: 完善的异常处理机制

## 💡 常用场景

### 场景 1: 智能客服
```python
client = CozeBotClient(bot_id="customer_service_bot_id")
response = await client.chat("我的订单状态是什么？")
```

### 场景 2: 代码助手
```python
client = CozeBotClient(bot_id="coding_bot_id")
response = await client.chat("帮我写一个 Python 快速排序")
```

### 场景 3: 内容创作
```python
client = CozeBotClient(bot_id="writer_bot_id")
response = await client.chat("写一篇关于 AI 的文章")
```

## 🔗 下一步

- 📖 查看完整文档: [COZE_USAGE_GUIDE.md](COZE_USAGE_GUIDE.md)
- 🧪 运行更多示例: `python test_coze_usage.py`
- 🔧 集成到项目: 参考 `core/coze_backend.py`

## ❓ 需要帮助？

遇到问题？检查以下几点：
1. ✅ 已安装 cozepy: `pip install cozepy`
2. ✅ .env 文件中配置了正确的 Token 和 Bot ID
3. ✅ Token 未过期且有效
4. ✅ Bot 已发布且可用

更多问题请查看 [COZE_USAGE_GUIDE.md](COZE_USAGE_GUIDE.md) 的常见问题部分。

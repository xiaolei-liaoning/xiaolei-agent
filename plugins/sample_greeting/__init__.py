"""示例 bundled 插件 — 展示 register(ctx) 的用法"""


def register(ctx):
    """PluginManager activate 时调用 — ctx 是核心提供的窄面"""
    def greet(name: str, greeting: str = "你好") -> dict:
        return {"greeting": f"{greeting}, {name}! 来自 sample_greeting 插件"}

    ctx.register_tool(
        name="greet",
        handler=greet,
        schema={
            "name": "greet",
            "description": "Say hello to a person (插件的 greeting 工具)",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "谁的名字"},
                    "greeting": {"type": "string", "description": "一句话开头 (可选)"},
                },
                "required": ["name"],
            },
        },
        toolset="social",
        emoji="👋",
    )

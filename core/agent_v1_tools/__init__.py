# V1 独立工具基础设施 — 已废弃，代码保留作参考
#
# V1→V2: V1 工具系统的 5 个文件（v1_tool_registry.py / v1_mcp_adapter.py /
#   v1_tool_result.py / v1_html_parser.py / __init__.py）提供 V1 独有工具注册表
#   和 MCP 代理。V2 中对应实现在 core/multi_agent_v2/tools/ 下：
#     - tool_registry.py → 替代 v1_tool_registry.py
#     - mcp_client.py    → 替代 v1_mcp_adapter.py
#     - tool_result.py   → 替代 v1_tool_result.py
#
# 保留原因: 参考。V1 的历史测试用例可能依赖这些文件的功能和接口签名。

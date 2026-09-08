"""L1c: Time-based microcompact — clears old results when cache expires.

V1→V2 历史：V1 压缩层 L1c，作为 ContextCompactor pipeline 第四层运行，
负责根据时间间隔清除旧 tool_results，防止长时间会话中上下文膨胀。
当前状态：V2 ContextBudgetManager 保留（use_v1_compaction=True 默认开启），
真实用法：每次 LLM 调用前检查时间间隔（默认 60min），
超过阈值则清理 old tool results，仅保留最近 keep_recent=5 条可清理结果。
enabled 字段仅控制 should_clear() 返回值，clear_old_results()
每次调用时会绕过 should_clear() 直接执行清理路径。
"""
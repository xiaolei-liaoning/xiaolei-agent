"""对话导出 — /export 命令或独立脚本"""

import json
import os
from datetime import datetime


def export_session(session_id: str, chat_history: list, task: str = "",
                   output_dir: str = "~/Desktop") -> str:
    """导出当前会话为 Markdown 文件

    Args:
        session_id: 会话 ID
        chat_history: [{"role": "user"/"assistant", "content": str}]
        task: 当前任务描述
        output_dir: 输出目录

    Returns:
        导出的文件路径
    """
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"xiaolei_dialog_{session_id}_{ts}.md"
    path = os.path.join(output_dir, filename)

    lines = [
        f"# XiaoLei AI Agent — 对话导出",
        f"",
        f"- **会话 ID**: `{session_id}`",
        f"- **任务**: {task or '(无)'}",
        f"- **消息数**: {len(chat_history)}",
        f"- **导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"---",
        f"",
    ]

    for i, msg in enumerate(chat_history):
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            lines.append(f"## 👤 用户")
        elif role == "assistant":
            lines.append(f"## 🤖 Agent")
        else:
            lines.append(f"## ❓ {role}")

        lines.append("")
        lines.append(content)
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


def export_from_store(session_id: str = "",
                      output_dir: str = "~/Desktop") -> str:
    """从 ConversationStore SQLite 导出指定会话

    Args:
        session_id: 会话 ID（空=最新会话）
        output_dir: 输出目录

    Returns:
        导出的文件路径
    """
    from core.multi_agent_v2.agents.conversation_store import ConversationStore

    store = ConversationStore.get_instance()
    conn = store._get_conn()

    if not session_id:
        row = conn.execute(
            "SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            raise ValueError("ConversationStore 中没有会话")
        session_id = row["id"]

    session = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    msgs = conn.execute(
        """SELECT round_num, role, content, tool_call_id, created_at
           FROM conversation_messages
           WHERE session_id = ? ORDER BY round_num, id""",
        (session_id,),
    ).fetchall()

    tools = conn.execute(
        """SELECT round_num, tool_name, success, result, arguments, created_at
           FROM tool_results
           WHERE session_id = ? ORDER BY round_num, id""",
        (session_id,),
    ).fetchall()

    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"xiaolei_store_{session_id[:8]}_{ts}.md")

    lines = [
        f"# XiaoLei Agent — 对话导出 (SQLite)",
        f"",
        f"- **会话 ID**: `{session_id}`",
        f"- **任务**: {session['task_description'] or '(无)'}",
        f"- **消息数**: {len(msgs)} | **工具记录**: {len(tools)}",
        f"- **时间**: {session['created_at']}",
        f"- **导出时间**: {datetime.now().isoformat()}",
        f"",
        f"---",
        f"",
    ]

    for msg in msgs:
        role_icon = {"user": "👤", "assistant": "🤖", "system": "⚙️"}.get(
            msg["role"], "❓"
        )
        content = msg["content"] or ""
        lines.append(f"## {role_icon} {msg['role'].upper()} (轮次 {msg['round_num']})")
        lines.append("")
        lines.append(content[:5000])
        lines.append("")

    if tools:
        lines.append("---")
        lines.append("## 工具执行记录")
        lines.append("")
        for t in tools:
            icon = "✅" if t["success"] else "❌"
            lines.append(
                f"- {icon} **{t['tool_name']}** "
                f"(轮次 {t['round_num']})"
            )
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path

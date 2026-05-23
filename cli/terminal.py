"""终端与 tmux 管理 - 从 cli.py 拆分"""

import os
import shutil
import subprocess
from pathlib import Path


def is_in_tmux() -> bool:
    """检查是否在 tmux 环境中"""
    return os.environ.get("TMUX") is not None


def _get_sandbox_view_script() -> str:
    """生成右侧面板的沙盒查看脚本"""
    return r'''#!/usr/bin/env python3
"""沙盒活动实时查看器 - 右侧面板专用"""
import sys, os, json, time, shutil
from pathlib import Path
view_path = Path(__file__).parent / "logs" / "sandbox_viewer.log"
view_path.parent.mkdir(parents=True, exist_ok=True)
if not view_path.exists():
    view_path.write_text("")
last_size = 0
while True:
    try:
        cols = shutil.get_terminal_size().columns
        rows = shutil.get_terminal_size().lines
        current_size = view_path.stat().st_size
        if current_size > last_size or current_size < last_size:
            print("\033[H\033[J", end="")
            title = " \U0001f6e1️ 沙盒执行活动 "
            pad = max(0, cols - len(title)) // 2
            print("━" * cols)
            print(f"{' ' * pad}{title}{' ' * (cols - pad - len(title))}")
            print("━" * cols)
            with open(view_path, "r") as f:
                lines = f.readlines()
                if not lines:
                    space = (cols - 20) // 2
                    print(f"{' ' * space}  (沙盒空闲)")
                for line in lines[-(rows-5):]:
                    line = line.strip()
                    if line:
                        try:
                            evt = json.loads(line)
                            t = evt.get("type","?")
                            title = evt.get("title","")
                            detail = evt.get("detail","")
                            status = evt.get("status","ok")
                            icon = "✅" if status=="ok" else "❌"
                            if t == "file_read": icon = "\U0001f4c4"
                            display = f"{icon} {title}"
                            if detail:
                                display += f" | {detail[:cols-30]}"
                            print(f"  {display[:cols-2]}")
                        except json.JSONDecodeError:
                            print(f"  {line[:cols-2]}")
            last_size = current_size
        time.sleep(0.5)
    except KeyboardInterrupt:
        break
    except Exception:
        time.sleep(1)
'''


def setup_dual_terminal() -> bool:
    """设置双终端模式（tmux + 沙盒查看器）

    Returns:
        是否成功进入 tmux 会话
    """
    if not shutil.which("tmux"):
        return False

    script_dir = Path(__file__).parent.parent
    log_file = str(script_dir / "logs" / "agent.log")
    (script_dir / "logs").mkdir(exist_ok=True)
    Path(log_file).write_text("", encoding="utf-8")

    # 写入沙盒查看器脚本到临时目录（避免污染项目目录）
    import tempfile
    viewer_script = Path(tempfile.gettempdir()) / "xiaolei_sandbox_view.py"
    viewer_script.write_text(_get_sandbox_view_script(), encoding="utf-8")

    session_name = "xiaolei_agent"

    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True
    )

    if result.returncode == 0:
        subprocess.run(["tmux", "attach-session", "-t", session_name])
        return True

    try:
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "-n", "Agent"])
        subprocess.run(["tmux", "set-option", "-t", session_name, "history-limit", "10000"])
        subprocess.run(["tmux", "set-option", "-t", session_name, "mouse", "on"])

        subprocess.run(["tmux", "split-window", "-h"])
        subprocess.run(["tmux", "resize-pane", "-L", "65"])

        subprocess.run([
            "tmux", "send-keys", "-t", f"{session_name}:Agent.0",
            f"cd '{script_dir}' && python3 cli.py", "C-m"
        ])
        subprocess.run([
            "tmux", "send-keys", "-t", f"{session_name}:Agent.1",
            f"cd '{script_dir}' && python3 {viewer_script}", "C-m"
        ])

        subprocess.run(["tmux", "select-pane", "-t", "0"])
        subprocess.run(["tmux", "attach-session", "-t", session_name])
        return True

    except Exception as e:
        print(f"启动双终端模式失败: {e}")
        return False

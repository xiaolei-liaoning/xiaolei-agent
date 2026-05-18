#!/usr/bin/env python3
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

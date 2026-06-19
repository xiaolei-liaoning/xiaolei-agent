#!/usr/bin/env python3
import subprocess
import sys

print("启动深度思考测试...")
result = subprocess.run(
    [sys.executable, "quick.py"],
    capture_output=True,
    text=True,
    cwd="/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent"
)

print("STDOUT:", result.stdout)
print("STDERR:", result.stderr[-500:] if result.stderr else "")
print("Return code:", result.returncode)

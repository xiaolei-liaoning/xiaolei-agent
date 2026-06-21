#!/bin/bash
# 小雷版小龙虾 AI Agent - 单终端启动脚本

# 设置路径
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

echo "🦞 启动小雷版小龙虾 AI Agent..."
echo "   ✓ 单终端模式"
echo "   ✓ 输入 /help 查看所有命令"
echo "   ✓ 输入 exit 或按 Ctrl+C 退出"
echo ""

cd "$SCRIPT_DIR" && python3 cli.py --single-terminal

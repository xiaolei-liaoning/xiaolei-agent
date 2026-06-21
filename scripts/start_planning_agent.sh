#!/bin/bash
# Planning Agent 快速启动脚本

echo "=========================================="
echo "🚀 Planning Agent 快速启动"
echo "=========================================="
echo ""

# 检查 Python 版本
echo "1️⃣  检查 Python 版本..."
python_version=$(python3 --version 2>&1)
if [ $? -eq 0 ]; then
    echo "   ✅ $python_version"
else
    echo "   ❌ Python3 未安装"
    exit 1
fi
echo ""

# 检查依赖
echo "2️⃣  检查依赖..."
if [ -f "requirements.txt" ]; then
    echo "   📦 安装依赖（这可能需要几分钟）..."
    pip install -r requirements.txt -q
    if [ $? -eq 0 ]; then
        echo "   ✅ 依赖安装完成"
    else
        echo "   ⚠️  依赖安装可能有问题，请检查错误信息"
    fi
else
    echo "   ⚠️  未找到 requirements.txt"
fi
echo ""

# 选择启动模式
echo "3️⃣  选择启动模式:"
echo "   [1] 启动主服务（包含 API 接口）- 推荐"
echo "   [2] 运行测试套件"
echo "   [3] 运行演示脚本"
echo "   [4] 命令行交互模式"
echo ""
read -p "请选择 (1-4): " choice

case $choice in
    1)
        echo ""
        echo "=========================================="
        echo "🌐 启动主服务..."
        echo "=========================================="
        echo ""
        echo "💡 提示:"
        echo "   - API 地址: http://localhost:8001"
        echo "   - 监控界面: http://localhost:8001/monitor"
        echo "   - 按 Ctrl+C 停止服务"
        echo ""
        python main.py
        ;;
    2)
        echo ""
        echo "=========================================="
        echo "🧪 运行测试套件..."
        echo "=========================================="
        echo ""
        python test_planning_agent.py
        ;;
    3)
        echo ""
        echo "=========================================="
        echo "🎬 运行演示脚本..."
        echo "=========================================="
        echo ""
        python demo_planning_agent.py
        ;;
    4)
        echo ""
        echo "=========================================="
        echo "💻 命令行交互模式"
        echo "=========================================="
        echo ""
        echo "输入任务描述（输入 'quit' 退出）:"
        echo ""
        while true; do
            read -p "> " task
            if [ "$task" = "quit" ] || [ "$task" = "exit" ]; then
                echo "再见！👋"
                break
            fi
            if [ -n "$task" ]; then
                python -m planning_agent "$task"
                echo ""
            fi
        done
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "✨ 完成！"
echo "=========================================="

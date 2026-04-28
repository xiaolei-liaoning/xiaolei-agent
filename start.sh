#!/bin/bash

# 小雷版小龙虾Agent系统 - 快速启动脚本
# 用法: ./start.sh [选项]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 正在启动小雷版小龙虾Agent系统...${NC}"
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误: 未找到Python3，请先安装Python 3.7+${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python版本:${NC} $(python3 --version)"
echo ""

# 解析参数
INSTALL_DEPS=false
DEV_MODE=false
RUN_TESTS=false
DEBUG_MODE=false
PROFILE_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --install)
            INSTALL_DEPS=true
            shift
            ;;
        --dev)
            DEV_MODE=true
            shift
            ;;
        --debug)
            DEBUG_MODE=true
            shift
            ;;
        --profile)
            PROFILE_MODE=true
            shift
            ;;
        --test)
            RUN_TESTS=true
            shift
            ;;
        --help)
            echo -e "${CYAN}用法: ./start.sh [选项]${NC}"
            echo ""
            echo "选项:"
            echo "  --install    安装/更新依赖"
            echo "  --dev        开发模式（热重载）"
            echo "  --debug      调试模式（详细日志）"
            echo "  --profile    性能分析模式"
            echo "  --test       运行所有测试"
            echo "  --help       显示此帮助信息"
            echo ""
            echo "示例:"
            echo "  ./start.sh                  # 标准模式"
            echo "  ./start.sh --dev            # 开发模式（推荐）"
            echo "  ./start.sh --debug          # 调试模式"
            echo "  ./start.sh --dev --debug    # 开发+调试模式"
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            exit 1
            ;;
    esac
done

# 安装依赖
if [ "$INSTALL_DEPS" = true ]; then
    echo -e "${YELLOW}📦 正在安装依赖...${NC}"
    if [ ! -f "requirements.txt" ]; then
        echo -e "${RED}❌ 错误: 未找到requirements.txt${NC}"
        exit 1
    fi
    pip3 install -r requirements.txt
    echo -e "${GREEN}✅ 依赖安装完成${NC}"
    echo ""
fi

# 运行测试
if [ "$RUN_TESTS" = true ]; then
    echo -e "${YELLOW}🧪 正在运行测试...${NC}"
    python3 -m pytest tests/ -v --tb=short
    echo ""
fi

# 检查配置文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  警告: 未找到.env配置文件${NC}"
    echo "   请复制 .env.example 为 .env 并配置API密钥"
    echo ""
fi

# 创建日志目录
mkdir -p logs

# 设置环境变量
export PYTHONUNBUFFERED=1

if [ "$DEBUG_MODE" = true ]; then
    export LOG_LEVEL=DEBUG
    echo -e "${CYAN}🔍 调试模式已启用（详细日志）${NC}"
else
    export LOG_LEVEL=INFO
fi

# 启动服务
echo -e "${GREEN}🎯 启动主服务...${NC}"
echo -e "   ${BLUE}访问地址:${NC} http://localhost:8001"
echo -e "   ${BLUE}监控界面:${NC} http://localhost:8001/monitor"
echo -e "   ${BLUE}API文档:${NC} http://localhost:8001/docs"
echo ""

if [ "$DEV_MODE" = true ]; then
    echo -e "${YELLOW}🔧 开发模式已启用（热重载）${NC}"
    if [ "$PROFILE_MODE" = true ]; then
        echo -e "${YELLOW}📊 性能分析模式已启用${NC}"
        python3 dev_mode.py --module main.py --port 8001
    else
        python3 dev_mode.py --module main.py --port 8001
    fi
elif [ "$PROFILE_MODE" = true ]; then
    echo -e "${YELLOW}📊 性能分析模式已启用${NC}"
    python3 -m cProfile -o profile.stats main.py
    echo -e "${GREEN}✅ 性能分析完成，结果保存在 profile.stats${NC}"
    echo "   使用 snakeviz profile.stats 查看可视化报告"
else
    echo "按 Ctrl+C 停止服务"
    echo "=========================================="
    echo ""
    python3 main.py
fi

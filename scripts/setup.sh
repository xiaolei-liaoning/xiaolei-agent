#!/bin/bash
# 小雷版小龙虾 Agent - 环境设置脚本
# 
# 此脚本用于设置开发环境
# 用法:
#   ./scripts/setup.sh          # 常规安装
#   ./scripts/setup.sh --offline  # 离线模式（假设已下载依赖）

set -e  # 错误时退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  小雷版小龙虾 Agent - 环境设置${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 解析命令行参数
OFFLINE_MODE=0
for arg in "$@"; do
    case $arg in
        --offline)
            OFFLINE_MODE=1
            shift
            ;;
    esac
done

# 检查 Python 版本
echo -e "${YELLOW}[1/6] 检查 Python 版本...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3，请先安装 Python 3.8+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
REQUIRED_VERSION="3.8"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}错误: 需要 Python 3.8+，当前版本: $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python 版本: $PYTHON_VERSION${NC}"
echo ""

# 创建虚拟环境
echo -e "${YELLOW}[2/6] 创建虚拟环境...${NC}"
VENV_DIR="$PROJECT_ROOT/.venv"

if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}⚠️  虚拟环境已存在，跳过创建${NC}"
else
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ 虚拟环境创建成功: $VENV_DIR${NC}"
fi

# 激活虚拟环境
echo -e "${YELLOW}[3/6] 激活虚拟环境...${NC}"
source "$VENV_DIR/bin/activate"
echo -e "${GREEN}✓ 虚拟环境已激活${NC}"

# 升级 pip
echo -e "${YELLOW}[4/6] 升级 pip...${NC}"
pip install --upgrade pip
echo -e "${GREEN}✓ pip 已升级${NC}"

# 安装依赖
echo -e "${YELLOW}[5/6] 安装依赖...${NC}"

if [ $OFFLINE_MODE -eq 1 ]; then
    echo -e "${YELLOW}⚠️  离线模式: 假设依赖已在本地缓存${NC}"
    if [ -f "requirements.txt" ]; then
        pip install --no-index --find-links=./wheelhouse -r requirements.txt
    else
        echo -e "${RED}错误: 离线模式需要 requirements.txt${NC}"
        exit 1
    fi
else
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    elif [ -f "pyproject.toml" ]; then
        pip install -e .
    else
        echo -e "${YELLOW}⚠️  未找到 requirements.txt 或 pyproject.toml${NC}"
        # 安装基础依赖
        pip install "uvicorn>=0.20.0" "fastapi>=0.89.0" "pydantic>=1.10.0"
    fi
fi

echo -e "${GREEN}✓ 依赖安装完成${NC}"

# 创建必要的目录
echo -e "${YELLOW}[6/6] 创建必要的目录...${NC}"
mkdir -p "$PROJECT_ROOT/data"
mkdir -p "$PROJECT_ROOT/dashboard"
mkdir -p "$PROJECT_ROOT/docker"
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/skills/core"
mkdir -p "$PROJECT_ROOT/skills/biz"
mkdir -p "$PROJECT_ROOT/tests"
echo -e "${GREEN}✓ 目录创建完成${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  设置完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "下一步:"
echo "  1. 激活虚拟环境: source .venv/bin/activate"
echo "  2. 复制配置: cp config/app_config.json.example config/app_config.json"
echo "  3. 编辑配置: vim config/app_config.json"
echo "  4. 运行测试: pytest -q"
echo "  5. 启动服务: python main.py"
echo ""
echo "提示: 运行 ./scripts/setup.sh --help 查看更多选项"
echo ""

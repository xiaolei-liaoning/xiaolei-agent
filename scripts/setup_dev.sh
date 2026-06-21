#!/bin/bash

# 开发环境一键配置脚本

set -e

echo "🔧 正在配置开发环境..."
echo ""

# 1. 创建虚拟环境（如果不存在）
if [ ! -d ".venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv .venv
    echo "✅ 虚拟环境创建成功"
else
    echo "✅ 虚拟环境已存在"
fi

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 升级pip
echo "⬆️  升级pip..."
pip install --upgrade pip

# 4. 安装依赖
echo "📥 安装项目依赖..."
pip install -r requirements.txt

# 5. 安装开发工具
echo "🛠️  安装开发工具..."
pip install black isort flake8 pytest pre-commit

# 6. 安装pre-commit钩子
echo "🔗 安装Git预提交钩子..."
if [ -d ".git" ]; then
    pre-commit install
    echo "✅ Git预提交钩子安装成功"
else
    echo "⚠️  未检测到Git仓库，跳过pre-commit安装"
fi

# 7. 创建.env文件（如果不存在）
if [ ! -f ".env" ]; then
    echo "📝 创建.env配置文件..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ 已从.env.example复制配置"
    else
        cat > .env << 'ENVEOF'
# API密钥配置
ZHIPU_API_KEY=your_api_key_here
COZE_API_TOKEN=your_coze_token_here
COZE_BOT_ID=your_bot_id_here

# 数据库配置
REDIS_URL=redis://localhost:6379/0

# 其他配置
LOG_LEVEL=INFO
ENVEOF
        echo "✅ 已创建默认.env文件，请修改API密钥"
    fi
fi

echo ""
echo "=========================================="
echo -e "\033[0;32m✅ 开发环境配置完成！\033[0m"
echo ""
echo "下一步："
echo "  1. 编辑 .env 文件，配置API密钥"
echo "  2. 运行 ./start.sh --install 启动服务"
echo "  3. 访问 http://localhost:8001/docs 查看API文档"
echo ""
echo "常用命令："
echo "  ./start.sh              # 启动服务"
echo "  ./start.sh --dev        # 开发模式（热重载）"
echo "  ./start.sh --test       # 运行测试"
echo "  ./start.sh --help       # 查看帮助"
echo "=========================================="

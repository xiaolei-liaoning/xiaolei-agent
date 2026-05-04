#!/bin/bash
# 仓库拆分脚本 - 将项目拆分为公开和私有两部分

set -e

echo "=========================================="
echo "  小雷版小龙虾Agent - 仓库拆分脚本"
echo "=========================================="
echo ""

# 检查git远程
echo "1. 检查当前仓库状态..."
git remote -v
echo ""

# 询问用户GitHub用户名
echo "2. 请输入您的GitHub用户名:"
read -r GITHUB_USER

# 创建公开仓库目录
echo ""
echo "3. 创建公开仓库目录..."
mkdir -p "../xiaolei-agent-docs"
cd "../xiaolei-agent-docs"

# 初始化新仓库
git init
git remote add origin "https://github.com/${GITHUB_USER}/xiaolei-agent-docs.git"

# 创建README
cat > README.md << 'EOF'
# 小雷版小龙虾 Agent - 文档与示例

这是一个开源的AI Agent项目，提供智能对话、多Agent协作、技能市场等功能。

## 主要特性

- 🎯 **意图理解** - 深度三层解析（意图分类→实体提取→约束识别）
- 🤖 **多Agent协作** - 规划师/执行者/校验员协作模式
- 🛒 **技能市场** - 10+内置技能（计算器/翻译/搜索/深度思考等）
- 🧠 **深度思考** - 5阶段反思框架+3种思考深度
- 💾 **记忆系统** - 短期+长期+工作记忆三层结构
- 🔒 **安全沙盒** - 代码执行隔离保护

## 快速开始

### 1. 克隆文档仓库
```bash
git clone https://github.com/${GITHUB_USER}/xiaolei-agent-docs.git
```

### 2. 查看文档
- [00.md](00.md) - 核心技术架构文档
- [QUICK_START.md](QUICK_START.md) - 快速开始指南
- [USER_GUIDE.md](USER_GUIDE.md) - 用户指南

### 3. 查看前端示例
在 `templates/` 目录下有完整的Web UI示例：
- chat.html - 智能对话界面
- coze.html - Coze风格界面
- workflow_editor.html - 工作流编辑器

## 架构预览

```
用户 → 意图理解 → 技能分发 → 任务规划 → 多Agent执行 → 深度思考 → 响应
         ↓            ↓           ↓           ↓            ↓
      关键词匹配   优先级排序   规则+AI     规划/执行    5阶段反思
                                                    ↓
                                              三层记忆系统
```

## 许可证

本项目采用 MIT 许可证。

## 联系

如需完整代码授权，请联系项目作者。
EOF

# 添加公开文件
echo ""
echo "4. 复制公开文件..."

# 复制文档
cp "../../小雷版小龙虾agent/00.md" ./
cp "../../小雷版小龙虾agent/QUICK_START.md" ./
cp "../../小雷版小龙虾agent/USER_GUIDE.md" ./
cp "../../小雷版小龙虾agent/README.md" ./README_full.md

# 复制前端模板
cp -r "../../小雷版小龙虾agent/templates" ./

# 复制API示例
mkdir -p api
cp "../../小雷版小龙虾agent/api/monitor.py" api/
cp "../../小雷版小龙虾agent/api/schedule.py" api/

# 复制环境变量示例
cp "../../小雷版小龙虾agent/.env.example" ./

# 复制CI配置
mkdir -p .github/workflows
cp "../../小雷版小龙虾agent/.github/workflows/ci-cd.yml" .github/workflows/

# 提交公开仓库
echo ""
echo "5. 提交公开仓库..."
git add .
git commit -m "✨ 初始版本：文档与示例

- 核心技术架构文档 (00.md)
- 快速开始指南 (QUICK_START.md)
- 用户指南 (USER_GUIDE.md)
- 前端UI示例 (templates/)
- 简单API示例 (api/)
- 环境变量配置模板 (.env.example)"

echo ""
echo "=========================================="
echo "  公开仓库创建完成！"
echo "=========================================="
echo ""
echo "📁 公开仓库位置: ../xiaolei-agent-docs/"
echo "🌐 推送命令:"
echo "   cd ../xiaolei-agent-docs"
echo "   git push -u origin main"
echo ""
echo "⚠️  接下来请在GitHub上:"
echo "   1. 创建 xiaolei-agent-docs 仓库（公开）"
echo "   2. 创建 xiaolei-agent-core 仓库（私有）"
echo "   3. 手动将 core/ skills/ api/v1.py api/workflow.py main.py 推送到私有仓库"
echo ""

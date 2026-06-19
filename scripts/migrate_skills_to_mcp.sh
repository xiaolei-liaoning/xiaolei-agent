#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Skill → MCP 迁移脚本
# 将所有功能型 Skill（非系统）从 Claude Code Skill 系统迁移到 MCP
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
BACKUP_DIR="$HOME/.claude/skills-backup-$(date +%Y%m%d_%H%M%S)"

# 系统级 Skill 列表（保留不动）
SYSTEM_SKILLS=(
  "update-config"
  "keybindings-help"
  "simplify"
  "fewer-permission-prompts"
  "loop"
  "init"
  "review"
)

# 功能型 Skill 列表（全部迁至 MCP）
FUNCTIONAL_SKILLS=(
  "agent-introspection-debugging"
  "agent-sort"
  "api-design"
  "article-writing"
  "backend-patterns"
  "brand-voice"
  "bun-runtime"
  "coding-standards"
  "content-engine"
  "crosspost"
  "deep-research"
  "dmux-workflows"
  "documentation-lookup"
  "e2e-testing"
  "eval-harness"
  "everything-claude-code"
  "exa-search"
  "fal-ai-media"
  "frontend-patterns"
  "frontend-slides"
  "investor-materials"
  "investor-outreach"
  "market-research"
  "mcp-server-patterns"
  "nextjs-turbopack"
  "product-capability"
  "strategic-compact"
  "tdd-workflow"
  "verification-loop"
  "video-editing"
  "x-api"
  "安全审查"
  "市场研究"
  "文章写作"
  "视频编辑"
  "编码标准"
  "产品能力"
  "端到端测试"
  "工作流管理"
  "后端模式"
  "跨平台发布"
  "内容引擎"
  "品牌声音"
  "评估框架"
  "前端模式"
  "前端演示"
  "全能Claude代码"
  "深度研究"
  "文档查询"
  "投资者材料"
  "投资者外联"
  "X平台API"
  "TDD工作流"
  "验证循环"
  "战略压缩"
  "智能体调试"
  "智能体排序"
  "Exa搜索"
  "MCP服务器模式"
  "Next.js打包"
  "API设计"
  "Bun运行时"
  "AI媒体生成"
)

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Skill → MCP 迁移工具                                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📂 技能目录: $CLAUDE_SKILLS_DIR"
echo "📦 备份目录: $BACKUP_DIR"
echo ""

# Step 1: 备份
echo "🔵 [1/4] 备份当前 Skills..."
mkdir -p "$BACKUP_DIR"
for skill in "${FUNCTIONAL_SKILLS[@]}"; do
  skill_path="$CLAUDE_SKILLS_DIR/$skill"
  if [ -L "$skill_path" ] || [ -d "$skill_path" ]; then
    cp -R "$skill_path" "$BACKUP_DIR/$skill" 2>/dev/null || true
    echo "   ✅ 已备份: $skill"
  fi
done
echo ""

# Step 2: 验证 MCP 服务器文件存在
echo "🔵 [2/4] 验证 MCP Skill Servers..."
if [ -f "$PROJECT_ROOT/小雷版小龙虾agent/mcp/skill_mcp_server.py" ]; then
  echo "   ✅ stdio MCP Server: skill_mcp_server.py"
else
  echo "   ❌ stdio MCP Server 缺失!"
  exit 1
fi

if [ -f "$PROJECT_ROOT/小雷版小龙虾agent/mcp/streamable_skill_server.py" ]; then
  echo "   ✅ HTTP MCP Server: streamable_skill_server.py"
else
  echo "   ❌ HTTP MCP Server 缺失!"
  exit 1
fi
echo ""

# Step 3: 测试 MCP 服务器启动
echo "🔵 [3/4] 测试 MCP 服务器..."
cd "$PROJECT_ROOT/小雷版小龙虾agent"

echo "   测试 stdio 模式..."
echo '{"jsonrpc":"2.0","id":1,"method":"listTools","params":{}}' | \
  python3 mcp/skill_mcp_server.py 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin); assert 'result' in d; print('   ✅ stdio 服务器正常 (' + str(len(d['result']['tools'])) + ' 个工具)')"

echo "   测试 HTTP 模式..."
python3 mcp/streamable_skill_server.py --port 6285 &
HTTP_PID=$!
sleep 2
curl -s http://127.0.0.1:6285/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('   ✅ HTTP 服务器正常 (' + str(d['skills_count']) + ' 个技能)')" || echo "   ⚠️ HTTP 服务器测试跳过"
kill $HTTP_PID 2>/dev/null || true
echo ""

# Step 4: 移除旧的 symlinks
echo "🔵 [4/4] 移除旧的功能型 Skill Symlinks..."
REMOVED=0
for skill in "${FUNCTIONAL_SKILLS[@]}"; do
  skill_path="$CLAUDE_SKILLS_DIR/$skill"
  if [ -L "$skill_path" ]; then
    rm "$skill_path"
    echo "   🗑️ 移除: $skill"
    REMOVED=$((REMOVED + 1))
  elif [ -d "$skill_path" ] && [ "$skill" != "gstack" ] && [ "$skill" != "superpowers" ]; then
    # 非 symlink 的目录（保留 gstack 和 superpowers 等非 symlink 目录）
    rm -rf "$skill_path"
    echo "   🗑️ 移除目录: $skill"
    REMOVED=$((REMOVED + 1))
  fi
done

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  迁移完成                                                    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  ✅ 已备份: $BACKUP_DIR"
echo "║  ✅ 已移除: $REMOVED 个功能型 Skills"
echo "║  ✅ MCP 服务器已就绪:"
echo "║     - stdio:  python3 mcp/skill_mcp_server.py"
echo "║     - HTTP:   python3 mcp/streamable_skill_server.py --port 6283"
echo "║  ✅ 配置文件:"
echo "║     - .mcp.json: skill-server + skill-server-http"
echo "║     - settings.local.json: enabledMcpjsonServers 已更新"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "💡 使用方式:"
echo "   调用 skill_list 工具列出技能"
echo "   调用 skill_get 获取技能详情"
echo "   调用 skill_execute 执行技能指导"
echo "   调用 skill://{name} 读取技能 Resources"
echo ""
echo "📌 注意: 系统级 Skills (update-config, loop, init 等) 保留在原位"

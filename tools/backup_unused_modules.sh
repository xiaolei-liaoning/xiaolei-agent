#!/bin/bash
# 未使用模块备份脚本
# 用于备份即将删除的 6 个文件

BACKUP_DIR="backup_unused_modules_$(date +%Y%m%d_%H%M%S)"
CORE_DIR="/Users/leiyuxuan/Desktop/逝去的白月光/小雷版小龙虾agent/core"

echo "=========================================="
echo "备份未使用模块"
echo "=========================================="
echo ""

# 创建备份目录
mkdir -p "$BACKUP_DIR"
echo "创建备份目录: $BACKUP_DIR"

# 备份文件列表
FILES_TO_BACKUP=(
    "handlers/global_state.py"
    "memory/conversation_compressor.py"
    "multi_agent_v2/api/api_server.py"
    "multi_agent_v2/infrastructure/observability/exception_middleware.py"
    "multi_agent_v2/infrastructure/observability/prometheus_metrics.py"
    "multi_agent_v2/orchestration/collaboration/complex_collaboration.py"
)

echo ""
echo "开始备份文件..."
count=0
for file in "${FILES_TO_BACKUP[@]}"; do
    src="$CORE_DIR/$file"
    if [ -f "$src" ]; then
        mkdir -p "$BACKUP_DIR/$(dirname "$file")"
        cp "$src" "$BACKUP_DIR/$file"
        echo "✅ 备份: $file"
        count=$((count + 1))
    else
        echo "⚠️ 文件不存在: $file"
    fi
done

echo ""
echo "=========================================="
echo "备份完成！共备份 $count 个文件"
echo "备份位置: $(pwd)/$BACKUP_DIR"
echo "=========================================="
echo ""
echo "接下来可以安全删除文件:"
echo "rm -f ${FILES_TO_BACKUP[@]/#/$CORE_DIR/}"
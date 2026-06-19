#!/bin/bash
# 意图识别监控快速操作脚本

set -e

LOG_DIR="logs/intent_monitoring"
TODAY=$(date +%Y%m%d)

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "用法: $0 <command>"
    echo ""
    echo "命令:"
    echo "  status      查看今日监控状态"
    echo "  report      生成并查看日报"
    echo "  low-conf    查看低置信度样例"
    echo "  trend       查看周趋势"
    echo "  clean       清理30天前的旧日志"
    echo "  test        运行测试"
    echo ""
}

check_status() {
    echo -e "${GREEN}📊 今日监控状态${NC}"
    echo "=================================="
    
    if [ ! -f "$LOG_DIR/intent_log_$TODAY.jsonl" ]; then
        echo -e "${YELLOW}⚠️  今日暂无数据${NC}"
        return
    fi
    
    TOTAL=$(wc -l < "$LOG_DIR/intent_log_$TODAY.jsonl")
    LOW_CONF=$(grep -o '"confidence": [0-9]\+\.[0-9]*' "$LOG_DIR/intent_log_$TODAY.jsonl" | \
               awk -F': ' '{if ($2 < 0.3) count++} END {print count+0}')
    
    echo "总请求数: $TOTAL"
    echo "低置信度(<0.3): $LOW_CONF"
    echo "低置信度率: $(echo "scale=2; $LOW_CONF * 100 / $TOTAL" | bc)%"
    echo ""
}

view_report() {
    echo -e "${GREEN}📋 今日日报${NC}"
    echo "=================================="
    
    REPORT_FILE="$LOG_DIR/daily_report_$TODAY.json"
    
    if [ ! -f "$REPORT_FILE" ]; then
        echo -e "${YELLOW}⚠️  日报尚未生成,正在生成...${NC}"
        python -c "
import sys
sys.path.insert(0, '.')
from core.intent_monitor import get_intent_monitor
monitor = get_intent_monitor()
monitor.generate_daily_report()
"
    fi
    
    if [ -f "$REPORT_FILE" ]; then
        cat "$REPORT_FILE" | python -m json.tool
    else
        echo -e "${RED}❌ 日报生成失败${NC}"
    fi
}

view_low_confidence() {
    echo -e "${GREEN}🔍 低置信度样例 (Top 10)${NC}"
    echo "=================================="
    
    if [ ! -f "$LOG_DIR/intent_log_$TODAY.jsonl" ]; then
        echo -e "${YELLOW}⚠️  今日暂无数据${NC}"
        return
    fi
    
    python -c "
import json
from pathlib import Path

log_file = Path('$LOG_DIR/intent_log_$TODAY.jsonl')
records = []
with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        records.append(json.loads(line.strip()))

low_conf = [r for r in records if r['confidence'] < 0.3]
low_conf.sort(key=lambda x: x['confidence'])

if not low_conf:
    print('✅ 今日无低置信度记录')
else:
    print(f'共 {len(low_conf)} 条低置信度记录\n')
    for i, r in enumerate(low_conf[:10], 1):
        print(f'{i}. 输入: {r[\"user_input\"]}')
        print(f'   意图: {r[\"primary_intent\"]} (置信度: {r[\"confidence\"]:.2f})')
        print(f'   时间: {r[\"datetime\"]}')
        print()
"
}

view_trend() {
    echo -e "${GREEN}📈 周趋势分析${NC}"
    echo "=================================="
    
    python -c "
import sys
sys.path.insert(0, '.')
from core.intent_monitor import get_intent_monitor

monitor = get_intent_monitor()
trend = monitor.analyze_weekly_trend(days=7)

if not trend['daily_volumes']:
    print('⚠️  暂无足够数据')
else:
    print('每日请求量:')
    for day in trend['daily_volumes']:
        print(f'  {day[\"date\"]}: {day[\"count\"]}')
    
    print('\n每日低置信度率:')
    for day in trend['daily_low_confidence_rates']:
        rate = day['rate'] * 100
        color = '\033[0;32m' if rate < 10 else '\033[1;33m' if rate < 20 else '\033[0;31m'
        reset = '\033[0m'
        print(f'  {color}{day[\"date\"]}: {rate:.1f}%{reset}')
"
}

clean_old_logs() {
    echo -e "${YELLOW}🧹 清理30天前的旧日志...${NC}"
    
    DELETED=$(find "$LOG_DIR" -name "*.jsonl" -mtime +30 -delete -print | wc -l)
    
    echo -e "${GREEN}✅ 已删除 $DELETED 个旧日志文件${NC}"
}

run_test() {
    echo -e "${GREEN}🧪 运行监控测试...${NC}"
    echo "=================================="
    python core/intent_monitor.py
}

# 主逻辑
case "${1:-status}" in
    status)
        check_status
        ;;
    report)
        view_report
        ;;
    low-conf)
        view_low_confidence
        ;;
    trend)
        view_trend
        ;;
    clean)
        clean_old_logs
        ;;
    test)
        run_test
        ;;
    *)
        usage
        exit 1
        ;;
esac

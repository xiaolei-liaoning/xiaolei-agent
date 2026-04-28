#!/bin/bash
# 小雷版小龙虾 AI Agent - 服务管理脚本
# 用法: ./dev.sh [start|stop|restart|dev]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.server.pid"
LOG_FILE="$SCRIPT_DIR/logs/server.log"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 创建日志目录
mkdir -p "$SCRIPT_DIR/logs"

show_help() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}小雷版小龙虾 AI Agent - 服务管理工具${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "用法: ./dev.sh [命令]"
    echo ""
    echo "命令:"
    echo "  start     启动服务（生产模式）"
    echo "  dev       启动服务（开发模式，带热重载）"
    echo "  stop      停止服务"
    echo "  restart   重启服务"
    echo "  status    查看服务状态"
    echo "  logs      查看实时日志"
    echo "  help      显示帮助信息"
    echo ""
    echo "示例:"
    echo "  ./dev.sh start      # 启动生产服务"
    echo "  ./dev.sh dev        # 启动开发服务（热重载）"
    echo "  ./dev.sh logs       # 查看实时日志"
    echo ""
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

is_running() {
    local pid=$(get_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

start_server() {
    local mode=$1
    local mode_name=""
    
    if is_running; then
        local pid=$(get_pid)
        echo -e "${YELLOW}⚠️  服务已在运行 (PID: $pid)${NC}"
        echo -e "${YELLOW}   如需重启，请先执行: ./dev.sh stop${NC}"
        exit 1
    fi
    
    if [ "$mode" == "dev" ]; then
        mode_name="开发模式"
        export DEV_MODE=true
        echo -e "${BLUE}🚀 启动服务（$mode_name - 带热重载）...${NC}"
    else
        mode_name="生产模式"
        unset DEV_MODE
        echo -e "${BLUE}🚀 启动服务（$mode_name）...${NC}"
    fi
    
    cd "$SCRIPT_DIR"
    nohup python main.py > "$LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$PID_FILE"
    
    # 等待服务启动
    sleep 2
    
    if is_running; then
        echo -e "${GREEN}✅ 服务启动成功 (PID: $pid)${NC}"
        echo -e "${GREEN}   访问地址: http://localhost:8001${NC}"
        echo -e "${GREEN}   工作流编辑器: http://localhost:8001/workflow_editor${NC}"
        echo -e "${GREEN}   Coze 聊天: http://localhost:8001/coze${NC}"
        echo -e "${GREEN}   API 文档: http://localhost:8001/docs${NC}"
        echo ""
        echo -e "${YELLOW}💡 提示:${NC}"
        echo -e "   查看日志: ./dev.sh logs"
        echo -e "   停止服务: ./dev.sh stop"
    else
        echo -e "${RED}❌ 服务启动失败，请查看日志: ${NC}"
        echo -e "${RED}   tail -f $LOG_FILE${NC}"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop_server() {
    if ! is_running; then
        echo -e "${YELLOW}⚠️  服务未运行${NC}"
        rm -f "$PID_FILE"
        return 0
    fi
    
    local pid=$(get_pid)
    echo -e "${BLUE}🛑 停止服务 (PID: $pid)...${NC}"
    
    # 优雅停止
    kill -TERM "$pid" 2>/dev/null || true
    
    # 等待最多 5 秒
    for i in {1..5}; do
        if ! is_running; then
            break
        fi
        sleep 1
    done
    
    # 如果还在运行，强制终止
    if is_running; then
        echo -e "${YELLOW}⚠️  优雅停止超时，强制终止...${NC}"
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
    fi
    
    rm -f "$PID_FILE"
    echo -e "${GREEN}✅ 服务已停止${NC}"
}

show_status() {
    if is_running; then
        local pid=$(get_pid)
        local port=8001
        
        echo -e "${GREEN}✅ 服务正在运行${NC}"
        echo -e "   PID: $pid"
        echo -e "   端口: $port"
        
        # 检查端口占用
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo -e "   状态: ${GREEN}监听中${NC}"
        else
            echo -e "   状态: ${YELLOW}异常（进程存在但端口未监听）${NC}"
        fi
        
        echo ""
        echo -e "   访问地址:"
        echo -e "   - 主页: http://localhost:$port"
        echo -e "   - 工作流编辑器: http://localhost:$port/workflow_editor"
        echo -e "   - Coze 聊天: http://localhost:$port/coze"
        echo -e "   - API 文档: http://localhost:$port/docs"
    else
        echo -e "${YELLOW}⚠️  服务未运行${NC}"
        echo -e "   启动服务: ./dev.sh start"
        echo -e "   开发模式: ./dev.sh dev"
    fi
}

show_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}⚠️  日志文件不存在${NC}"
        echo -e "   请先启动服务: ./dev.sh start"
        exit 1
    fi
    
    echo -e "${BLUE}📋 实时日志（Ctrl+C 退出）...${NC}"
    echo ""
    tail -f "$LOG_FILE"
}

# 主逻辑
case "${1:-help}" in
    start)
        start_server "prod"
        ;;
    dev)
        start_server "dev"
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        sleep 1
        start_server "prod"
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}❌ 未知命令: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac

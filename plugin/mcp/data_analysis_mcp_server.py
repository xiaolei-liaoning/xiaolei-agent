#!/usr/bin/env python3
"""数据分析 MCP 服务器"""

import json
import sys
from typing import List, Dict, Any


class DataAnalysisMCPServer:
    """数据分析 MCP 服务器"""

    def __init__(self):
        self.name = "data-analysis"
        self.description = "数据分析服务（统计、图表、词云）"

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "analyze_csv",
                "description": "分析CSV文件（自动查找最近导出的CSV）",
                "parameters": {
                    "file_path": {"type": "string", "description": "CSV文件路径（可选，不指定则自动查找）", "required": False},
                    "analysis_type": {"type": "string", "description": "分析类型: stats/bar/pie/wordcloud/line", "required": False}
                }
            },
            {
                "name": "descriptive_stats",
                "description": "描述性统计分析",
                "parameters": {
                    "file_path": {"type": "string", "description": "CSV文件路径", "required": False}
                }
            },
            {
                "name": "create_chart",
                "description": "生成图表",
                "parameters": {
                    "chart_type": {"type": "string", "description": "图表类型: bar/pie/line", "required": True},
                    "file_path": {"type": "string", "description": "CSV文件路径", "required": False}
                }
            },
            {
                "name": "create_wordcloud",
                "description": "生成词云",
                "parameters": {
                    "file_path": {"type": "string", "description": "CSV文件路径", "required": False},
                    "text_column": {"type": "string", "description": "文本列名", "required": False}
                }
            },
        ]

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            handler = self._get_handler()
            if name == "analyze_csv":
                result = handler.execute(
                    file_path=args.get("file_path", ""),
                    analysis_type=args.get("analysis_type", "stats")
                )
            elif name == "descriptive_stats":
                result = handler._descriptive_stats(
                    handler._load_csv(args.get("file_path", "")) if args.get("file_path")
                    else handler._load_csv(handler._find_latest_csv())
                )
            elif name == "create_chart":
                chart_type = args.get("chart_type", "bar")
                df = handler._load_csv(args.get("file_path", "")) if args.get("file_path") else handler._load_csv(handler._find_latest_csv())
                if chart_type == "bar":
                    result = handler._create_bar_chart(df)
                elif chart_type == "pie":
                    result = handler._create_pie_chart(df)
                elif chart_type == "line":
                    result = handler._create_line_chart(df)
                else:
                    return {"success": False, "error": f"未知图表类型: {chart_type}"}
            elif name == "create_wordcloud":
                result = handler._create_wordcloud(
                    handler._load_csv(args.get("file_path", "")) if args.get("file_path") else handler._load_csv(handler._find_latest_csv())
                )
            else:
                return {"success": False, "error": f"未知工具: {name}"}

            reply = result.get("reply", str(result))
            return {"success": True, "result": reply}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_handler(self):
        try:
            from mcp._impl.data_analysis.handler import DataAnalysisHandler
            return DataAnalysisHandler()
        except Exception as e:
            raise ImportError(f"无法加载数据分析模块: {e}")


server = DataAnalysisMCPServer()


def handle_request(request: dict) -> dict:
    method = request.get("method", "")
    if method == "list_tools" or method == "tools":
        return {"jsonrpc": "2.0", "result": server.get_tools(), "id": request.get("id")}
    elif method == "call" or method == "callTool":
        tool_name = request.get("params", {}).get("name")
        args = request.get("params", {}).get("arguments", {})
        result = server.call_tool(tool_name, args)
        return {
            "jsonrpc": "2.0",
            "result": {"success": result["success"], "content": [{"text": str(result.get("result", ""))}]},
            "id": request.get("id")
        }
    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": request.get("id")}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}))
            sys.stdout.flush()


if __name__ == "__main__":
    main()

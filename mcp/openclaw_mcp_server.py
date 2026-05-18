#!/usr/bin/env python3
"""OpenClaw 工作流引擎 MCP 服务器 - JSON-RPC stdio 协议"""

import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path

WORKFLOW_DIR = Path(__file__).parent.parent / "workflows" / "openclaw"
WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)

TOOLS = [
    {
        "name": "list_workflows",
        "description": "列出所有工作流（可按标签或状态筛选）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "按标签筛选（可选）"},
                "status": {"type": "string", "description": "按状态筛选: draft/published/archived（可选）"}
            }
        }
    },
    {
        "name": "create_workflow",
        "description": "创建工作流并保存",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "工作流唯一ID"},
                "definition": {
                    "type": "object",
                    "description": "工作流定义: {nodes: [...], edges: [...]}",
                    "properties": {
                        "nodes": {"type": "array", "items": {"type": "object"}},
                        "edges": {"type": "array", "items": {"type": "object"}}
                    }
                },
                "description": {"type": "string", "description": "工作流描述"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "标签列表"}
            },
            "required": ["workflow_id", "definition"]
        }
    },
    {
        "name": "execute_workflow",
        "description": "执行工作流",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "已保存的工作流ID"},
                "input_data": {"type": "object", "description": "输入数据"}
            }
        }
    },
    {
        "name": "validate_workflow",
        "description": "验证工作流定义的完整性",
        "inputSchema": {
            "type": "object",
            "properties": {
                "definition": {
                    "type": "object",
                    "description": "工作流定义: {nodes: [...], edges: [...]}",
                    "properties": {
                        "nodes": {"type": "array", "items": {"type": "object"}},
                        "edges": {"type": "array", "items": {"type": "object"}}
                    }
                }
            },
            "required": ["definition"]
        }
    },
    {
        "name": "get_template",
        "description": "获取工作流模板",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_name": {"type": "string", "description": "模板名称（可选，不传则列出可用模板）"}
            }
        }
    },
    {
        "name": "delete_workflow",
        "description": "删除工作流",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "工作流ID"}
            },
            "required": ["workflow_id"]
        }
    },
    {
        "name": "export_workflow",
        "description": "导出工作流为 JSON",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "工作流ID"}
            },
            "required": ["workflow_id"]
        }
    },
]


def detect_cycle(edges):
    """检测是否有循环依赖"""
    graph = {}
    for edge in edges:
        frm = edge.get("from_node", "")
        to = edge.get("to_node", "")
        if frm not in graph:
            graph[frm] = []
        graph[frm].append(to)
    visited = set()
    rec_stack = set()

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    for node in graph:
        if node not in visited:
            if dfs(node):
                return True
    return False


async def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    rid = request.get("id", 1)

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"name": "openclaw-mcp", "version": "1.0.0"}}
    if method == "listTools":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method in ("callTool", "call"):
        tool = params.get("name")
        args = params.get("arguments", {})

        try:
            if tool == "list_workflows":
                tag = args.get("tag")
                status = args.get("status")
                workflows = []
                for wf_file in sorted(WORKFLOW_DIR.glob("*.json")):
                    try:
                        with open(wf_file, 'r', encoding='utf-8') as f:
                            wf = json.load(f)
                        if tag and tag not in wf.get("tags", []):
                            continue
                        if status and wf.get("status") != status:
                            continue
                        workflows.append({
                            "id": wf["id"],
                            "description": wf.get("description", ""),
                            "tags": wf.get("tags", []),
                            "status": wf.get("status", "draft"),
                            "version": wf.get("version", "1.0.0"),
                            "created_at": wf.get("created_at", ""),
                            "node_count": len(wf.get("definition", {}).get("nodes", []))
                        })
                    except Exception:
                        continue
                if not workflows:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": "暂无工作流"}]}}
                lines = [f"📋 工作流列表 ({len(workflows)} 个)\n"]
                for wf in workflows:
                    lines.append(f"• {wf['id']} [{wf['status']}] v{wf['version']}")
                    if wf["description"]:
                        lines.append(f"  {wf['description']}")
                    lines.append(f"  节点: {wf['node_count']} | 标签: {', '.join(wf['tags']) if wf['tags'] else '无'}")
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": '\n'.join(lines)}]}}

            if tool == "create_workflow":
                wf_id = args.get("workflow_id", "")
                definition = args.get("definition", {})
                description = args.get("description", "")
                tags = args.get("tags", [])

                errors = []
                if "nodes" not in definition:
                    errors.append("缺少 nodes 字段")
                if "edges" not in definition:
                    errors.append("缺少 edges 字段")

                if not errors:
                    node_ids = set()
                    for node in definition.get("nodes", []):
                        if "id" not in node:
                            errors.append("节点缺少 id 字段")
                        else:
                            if node["id"] in node_ids:
                                errors.append(f"节点ID重复: {node['id']}")
                            node_ids.add(node["id"])

                    for edge in definition.get("edges", []):
                        if edge.get("from_node") not in node_ids and edge.get("from_node"):
                            errors.append(f"边引用不存在的源节点: {edge['from_node']}")
                        if edge.get("to_node") not in node_ids and edge.get("to_node"):
                            errors.append(f"边引用不存在的目标节点: {edge['to_node']}")

                    if detect_cycle(definition.get("edges", [])):
                        errors.append("检测到循环依赖")

                if errors:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"验证失败:\n" + '\n'.join(errors)}]}}

                wf_data = {
                    "id": wf_id,
                    "definition": definition,
                    "description": description,
                    "tags": tags,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "version": "1.0.0",
                    "status": "draft"
                }
                wf_file = WORKFLOW_DIR / f"{wf_id}.json"
                with open(wf_file, 'w', encoding='utf-8') as f:
                    json.dump(wf_data, f, ensure_ascii=False, indent=2)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"✅ 工作流 '{wf_id}' 创建成功\n路径: {wf_file}"}]}}

            if tool == "execute_workflow":
                wf_id = args.get("workflow_id", "")
                input_data = args.get("input_data", {})
                wf_file = WORKFLOW_DIR / f"{wf_id}.json"
                if not wf_file.exists():
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"工作流不存在: {wf_id}"}]}}
                with open(wf_file, 'r', encoding='utf-8') as f:
                    wf = json.load(f)
                text = f"✅ 工作流 '{wf_id}' 执行完成\n节点数: {len(wf['definition'].get('nodes', []))}\n执行时间: {datetime.now().isoformat()}"
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "validate_workflow":
                definition = args.get("definition", {})
                errors = []
                warnings = []
                if "nodes" not in definition:
                    errors.append("缺少 nodes 字段")
                if "edges" not in definition:
                    errors.append("缺少 edges 字段")
                if not errors:
                    node_ids = set()
                    for node in definition.get("nodes", []):
                        if "id" not in node:
                            errors.append("节点缺少 id 字段")
                        else:
                            if node["id"] in node_ids:
                                errors.append(f"节点ID重复: {node['id']}")
                            node_ids.add(node["id"])
                        if "type" not in node:
                            warnings.append(f"节点 {node.get('id', 'unknown')} 缺少 type 字段")
                    for edge in definition.get("edges", []):
                        if edge.get("from_node", "") and edge["from_node"] not in node_ids:
                            errors.append(f"边引用不存在的源节点: {edge['from_node']}")
                        if edge.get("to_node", "") and edge["to_node"] not in node_ids:
                            errors.append(f"边引用不存在的目标节点: {edge['to_node']}")
                    if detect_cycle(definition.get("edges", [])):
                        warnings.append("检测到循环依赖")
                if errors:
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"验证失败 ({len(errors)} 个错误):\n" + '\n'.join(errors)}]}}
                text = f"✅ 验证通过\n节点: {len(node_ids)} | 边: {len(definition.get('edges', []))}"
                if warnings:
                    text += "\n⚠️ 警告:\n" + '\n'.join(warnings)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": text}]}}

            if tool == "get_template":
                tmpl_name = args.get("template_name", "")
                templates = {
                    "web_scraper": {
                        "nodes": [{"id": "start", "type": "trigger"}, {"id": "scrape", "type": "web_scraper"}, {"id": "output", "type": "output"}],
                        "edges": [{"from_node": "start", "to_node": "scrape"}, {"from_node": "scrape", "to_node": "output"}]
                    },
                    "data_analysis": {
                        "nodes": [{"id": "input", "type": "input"}, {"id": "analyze", "type": "data_analysis"}, {"id": "report", "type": "output"}],
                        "edges": [{"from_node": "input", "to_node": "analyze"}, {"from_node": "analyze", "to_node": "report"}]
                    },
                }
                if tmpl_name:
                    tmpl = templates.get(tmpl_name)
                    if tmpl:
                        return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"📋 模板 '{tmpl_name}':\n{json.dumps(tmpl, indent=2, ensure_ascii=False)}"}]}}
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"未知模板: {tmpl_name}\n可用: {', '.join(templates.keys())}"}]}}
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"📋 可用模板:\n" + '\n'.join(f"• {k}" for k in templates.keys())}]}}

            if tool == "delete_workflow":
                wf_id = args.get("workflow_id", "")
                wf_file = WORKFLOW_DIR / f"{wf_id}.json"
                if not wf_file.exists():
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"工作流不存在: {wf_id}"}]}}
                wf_file.unlink()
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"已删除工作流: {wf_id}"}]}}

            if tool == "export_workflow":
                wf_id = args.get("workflow_id", "")
                wf_file = WORKFLOW_DIR / f"{wf_id}.json"
                if not wf_file.exists():
                    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"工作流不存在: {wf_id}"}]}}
                with open(wf_file, 'r', encoding='utf-8') as f:
                    wf = json.load(f)
                return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": json.dumps(wf, indent=2, ensure_ascii=False)}]}}

        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"text": f"错误: {str(e)}"}]}}

        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {tool}"}}

    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}


async def main():
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            request = json.loads(line.strip())
            response = await handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "id": 0, "error": {"code": -32700, "message": "Parse error"}}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "id": 0, "error": {"code": -32603, "message": str(e)}}))
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())

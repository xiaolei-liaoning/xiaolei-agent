#!/usr/bin/env python3
"""
Unified MCP Skill Server - stdio mode
将 Claude Code 全局功能型 Skills 迁移为 MCP Resources + Tools

架构：
- 读取 everything-claude-code 所有技能的 SKILL.md
- 每个 Skill 同时作为 MCP Resource (可读指导内容) 和 Tool (可执行调用)
- 遵循 JSON-RPC stdio 协议
- 支持混合模式：标准技能用本地 stdio，复杂技能可 HTTP 转发

Usage:
  python mcp/skill_mcp_server.py

注册到 .mcp.json:
  {
    "mcpServers": {
      "skill-server": {
        "type": "stdio",
        "command": "python3",
        "args": ["mcp/skill_mcp_server.py"]
      }
    }
  }
"""

import os
import re
import sys
import json
import yaml
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────────────────────
SKILLS_BASE = os.path.expanduser(
    "~/Desktop/claude/everything-claude-code-main/.agents/skills"
)
PROJECT_SKILLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")

# 系统级 Skills（保留在 Skill 系统中，不迁移）
SYSTEM_SKILLS = {
    "update-config", "keybindings-help", "simplify",
    "fewer-permission-prompts", "loop", "init", "review",
    "security-review", "GenericAgent"
}

# 功能型 Skill 分类
SKILL_CATEGORIES = {
    "product": {"product-capability", "market-research", "strategic-compact"},
    "frontend": {"frontend-patterns", "frontend-slides", "nextjs-turbopack"},
    "backend": {"backend-patterns", "api-design", "mcp-server-patterns", "bun-runtime"},
    "content": {"article-writing", "content-engine", "crosspost", "brand-voice"},
    "media": {"video-editing", "fal-ai-media"},
    "ai": {"deep-research", "exa-search", "documentation-lookup", "e2e-testing", "eval-harness"},
    "devops": {"tdd-workflow", "verification-loop", "coding-standards", "agent-sort", "everything-claude-code"},
    "investor": {"investor-materials", "investor-outreach"},
    "security": {"security-review"},
    "api-platform": {"x-api", "agent-introspection-debugging", "dmux-workflows"},
    "project": {"gstack", "superpowers"}  # project-specific
}

# ── 技能加载 ──────────────────────────────────────────────────────────

def load_skill_metadata(skill_dir: str) -> Optional[Dict[str, Any]]:
    """从 SKILL.md 加载技能的 frontmatter 元数据"""
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md):
        return None

    name = os.path.basename(skill_dir)

    try:
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    # 解析 frontmatter (---\n...\n---)
    meta = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            body = parts[2].strip()
            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip()

    # 确定分类
    category = "uncategorized"
    for cat, skills in SKILL_CATEGORIES.items():
        if name in skills:
            category = cat
            break

    # 检查是否有 agents 子目录
    has_agents = os.path.isdir(os.path.join(skill_dir, "agents"))

    # 读取子 agent 配置
    agents = []
    if has_agents:
        agents_dir = os.path.join(skill_dir, "agents")
        for agent_file in sorted(os.listdir(agents_dir)):
            if agent_file.endswith(".md"):
                agent_path = os.path.join(agents_dir, agent_file)
                try:
                    with open(agent_path, "r", encoding="utf-8") as f:
                        agents.append({
                            "name": agent_file.replace(".md", ""),
                            "content": f.read()[:500]  # 截断，完整内容走 resource
                        })
                except Exception:
                    pass

    # 决定 MCP 模式
    mcp_mode = "http" if category in ("product", "content", "media", "ai") else "stdio"

    return {
        "name": name,
        "title": meta.get("name", name),
        "description": meta.get("description", ""),
        "version": meta.get("version", "1.0.0"),
        "author": meta.get("author", ""),
        "category": category,
        "has_agents": has_agents,
        "mcp_mode": mcp_mode,
        "agents": agents,
        "body_preview": body[:300] if body else "",
        "body_length": len(body) if body else 0,
        "file_path": skill_md,
    }


def scan_all_skills() -> Dict[str, Dict[str, Any]]:
    """扫描所有技能目录，返回 {name: metadata}"""
    skills = {}

    # 从 everything-claude-code 加载
    if os.path.exists(SKILLS_BASE):
        for entry in sorted(os.listdir(SKILLS_BASE)):
            skill_dir = os.path.join(SKILLS_BASE, entry)
            if os.path.isdir(skill_dir):
                meta = load_skill_metadata(skill_dir)
                if meta and meta["name"] not in SYSTEM_SKILLS:
                    skills[meta["name"]] = meta

    # 从项目本地 skills 加载
    if os.path.exists(PROJECT_SKILLS):
        for entry in sorted(os.listdir(PROJECT_SKILLS)):
            skill_dir = os.path.join(PROJECT_SKILLS, entry)
            if os.path.isdir(skill_dir):
                meta = load_skill_metadata(skill_dir)
                if meta and meta["name"] not in SYSTEM_SKILLS and meta["name"] not in skills:
                    skills[meta["name"]] = meta

    return skills


def get_skill_content(name: str) -> Optional[str]:
    """获取指定技能的完整 SKILL.md 内容"""
    # 尝试 everything-claude-code
    path = os.path.join(SKILLS_BASE, name, "SKILL.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    # 尝试项目本地
    path = os.path.join(PROJECT_SKILLS, name, "SKILL.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    return None


# ── MCP 服务器实现 ────────────────────────────────────────────────────

class SkillMCPServer:
    """Unified MCP Skill Server - 将所有功能型 Skill 暴露为 MCP Resources + Tools"""

    def __init__(self, skills_base: str = SKILLS_BASE):
        self.name = "skill-mcp-server"
        self.version = "2.0.0"
        self.skills_base = skills_base
        self.skills: Dict[str, Dict[str, Any]] = {}
        self._reload_skills()

    def _reload_skills(self):
        """重新加载技能列表"""
        self.skills = scan_all_skills()
        logger.info(f"已加载 {len(self.skills)} 个技能")

    def get_tools(self) -> List[Dict]:
        """返回工具列表（MCP listTools）"""
        return [
            {
                "name": "skill_list",
                "description": "列出所有可用的功能型 Skill，可按分类筛选",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "筛选分类: product, frontend, backend, content, media, ai, devops, investor, security, api-platform, project"
                        }
                    }
                }
            },
            {
                "name": "skill_get",
                "description": "获取指定 Skill 的详细元数据和指导内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill 名称 (如 product-capability, api-design)"
                        }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "skill_search",
                "description": "搜索技能名称和描述中匹配关键词的 Skill",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "skill_execute",
                "description": "执行指定 Skill - 返回完整的指导内容和执行步骤，用作任务执行的上下文",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill 名称"
                        },
                        "task": {
                            "type": "string",
                            "description": "要执行的具体任务描述"
                        },
                        "context": {
                            "type": "string",
                            "description": "额外上下文信息（可选）"
                        }
                    },
                    "required": ["name", "task"]
                }
            },
            {
                "name": "skill_agent_run",
                "description": "运行 Skill 的子 Agent 工作流（仅限有 agents 子目录的 Skill）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill 名称"
                        },
                        "agent": {
                            "type": "string",
                            "description": "子 Agent 名称（不填则返回可用 Agent 列表）"
                        },
                        "input": {
                            "type": "string",
                            "description": "Agent 输入参数"
                        }
                    },
                    "required": ["name"]
                }
            },
        ]

    def get_resources(self) -> List[Dict]:
        """返回资源列表（MCP resources/list）"""
        resources = []
        for name, meta in self.skills.items():
            resources.append({
                "uri": f"skill://{name}",
                "name": meta["title"],
                "description": meta["description"][:100],
                "mimeType": "text/markdown",
            })
        return resources

    def get_categories(self) -> Dict[str, List[str]]:
        """获取按分类分组的技能列表"""
        cats = {}
        for name, meta in self.skills.items():
            cat = meta["category"]
            if cat not in cats:
                cats[cat] = []
            cats[cat].append(name)
        return cats

    async def handle_request(self, request: Dict) -> Dict:
        """处理 JSON-RPC 请求"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id", 1)

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "name": self.name,
                    "version": self.version,
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {},
                    }
                }
            }

        elif method == "listTools":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": self.get_tools()}
            }

        elif method == "listResources":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"resources": self.get_resources()}
            }

        elif method == "readResource":
            uri = params.get("uri", "")
            if uri.startswith("skill://"):
                name = uri.replace("skill://", "")
                content = get_skill_content(name)
                if content:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "contents": [{
                                "uri": uri,
                                "mimeType": "text/markdown",
                                "text": content
                            }]
                        }
                    }
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": f"Skill '{name}' not found"}
                }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": f"Resource '{uri}' not found"}
            }

        elif method == "callTool":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "skill_list":
                category = arguments.get("category")
                if category and category in SKILL_CATEGORIES:
                    skills_in_cat = [self.skills[s] for s in SKILL_CATEGORIES[category] if s in self.skills]
                    result_text = f"# {category} 分类技能 ({len(skills_in_cat)} 个)\n\n"
                else:
                    skills_in_cat = list(self.skills.values())
                    cats = self.get_categories()
                    result_text = f"# 可用技能 ({len(skills_in_cat)} 个)\n\n"
                    for cat, skill_names in cats.items():
                        result_text += f"## {cat}\n"
                        for s in skill_names:
                            meta = self.skills[s]
                            result_text += f"- **{meta['title']}** ({s}): {meta['description'][:80]}...\n"
                        result_text += "\n"

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"text": result_text}]}
                }

            elif tool_name == "skill_get":
                name = arguments.get("name", "")
                meta = self.skills.get(name)
                if not meta:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": f"Skill '{name}' not found"}
                    }

                content = get_skill_content(name)

                result_text = f"""# {meta['title']}

**名称**: {meta['name']}
**分类**: {meta['category']}
**描述**: {meta['description']}
**版本**: {meta['version']}
**作者**: {meta['author']}
**MCP 模式**: {meta['mcp_mode']}
**有子 Agent**: {meta['has_agents']}

## 指导内容
{content if content else '(无内容)'}
"""

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"text": result_text}]}
                }

            elif tool_name == "skill_search":
                query = arguments.get("query", "").lower()
                results = []
                for name, meta in self.skills.items():
                    if query in name.lower() or query in meta["description"].lower() or query in meta["title"].lower():
                        results.append(meta)

                if results:
                    result_text = f"# 搜索结果: '{query}' ({len(results)} 个)\n\n"
                    for meta in results:
                        result_text += f"- **{meta['title']}** (`{meta['name']}`): {meta['description'][:100]}...\n"
                else:
                    result_text = f"未找到匹配 '{query}' 的 Skill"

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"text": result_text}]}
                }

            elif tool_name == "skill_execute":
                name = arguments.get("name", "")
                task = arguments.get("task", "")
                context = arguments.get("context", "")

                meta = self.skills.get(name)
                if not meta:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": f"Skill '{name}' not found"}
                    }

                content = get_skill_content(name)

                result_text = f"""# Skill 执行: {meta['title']}

## 任务
{task}

## Skill 指导
{content if content else '(无内容)'}

## 执行计划
1. 读取 Skill `{name}` 的完整指导内容
2. 根据任务 "{task}" 应用 Skill 规则
3. 按 Skill 定义的工作流执行
4. 生成符合 Skill 规范的输出
"""
                if context:
                    result_text += f"\n## 额外上下文\n{context}\n"

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"text": result_text}]}
                }

            elif tool_name == "skill_agent_run":
                name = arguments.get("name", "")
                agent_name = arguments.get("agent", "")
                agent_input = arguments.get("input", "")

                meta = self.skills.get(name)
                if not meta:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": f"Skill '{name}' not found"}
                    }

                if not meta["has_agents"]:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"text": f"Skill '{name}' 没有子 Agent"}]}
                    }

                if not agent_name:
                    agents_list = "\n".join([f"- {a['name']}" for a in meta["agents"]])
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"text": f"Skill '{name}' 可用子 Agent:\n{agents_list}"}]}
                    }

                # 找到指定 Agent
                agent = None
                for a in meta["agents"]:
                    if a["name"] == agent_name:
                        agent = a
                        break

                if not agent:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": f"Agent '{agent_name}' not found in skill '{name}'"}
                    }

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"text": f"""# Agent 执行: {name} / {agent_name}

## Agent 配置
{agent['content']}

## 输入
{agent_input}

## 执行
请根据 Agent 配置执行指定任务。
"""}]}
                }

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }


# ── 启动入口 ──────────────────────────────────────────────────────────

async def main():
    """运行 MCP Skill Server (stdio 模式)"""
    logger.info(f"🚀 启动 Unified MCP Skill Server v2.0.0")
    logger.info(f"📂 技能目录: {SKILLS_BASE}")

    server = SkillMCPServer()
    logger.info(f"✅ 已加载 {len(server.skills)} 个功能型 Skills")

    # 按分类输出统计
    cats = server.get_categories()
    for cat, skill_names in sorted(cats.items()):
        logger.info(f"   {cat}: {len(skill_names)} skills")

    try:
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            try:
                request = json.loads(line.strip())
                response = await server.handle_request(request)
                print(json.dumps(response))
                sys.stdout.flush()
            except json.JSONDecodeError:
                print(json.dumps({
                    "jsonrpc": "2.0", "id": 0,
                    "error": {"code": -32700, "message": "Parse error"}
                }))
                sys.stdout.flush()
            except Exception as e:
                print(json.dumps({
                    "jsonrpc": "2.0", "id": 0,
                    "error": {"code": -32603, "message": str(e)}
                }))
                sys.stdout.flush()

    except KeyboardInterrupt:
        logger.info("✅ 服务器已停止")
        sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stderr  # 日志输出到 stderr，与 stdout 的 JSON-RPC 分离
    )
    asyncio.run(main())

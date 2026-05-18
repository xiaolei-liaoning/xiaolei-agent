"""plugin/ — 功能级资源统一容器

结构：
  plugin.json            — 插件元数据与组件清单
  skills/                — 本地 Skill（workflow_engine, 人物 等）
  mcp/                   — MCP 服务器（.py + _impl/ 实现）
  api/                   — 功能级 API 路由模块
  config/                — MCP/技能/应用配置

当前为渐进迁移模式：
  - 新位置的文件为新架构主目录
  - 旧位置保留 symlink/import 兼容性
  - plugin_loader.py 统一加载

未来：旧位置的 skills/ mcp/ config/ 目录可删除。
"""
import os
import json
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent


def load_manifest() -> dict:
    """读取 plugin.json 清单"""
    manifest_path = PLUGIN_DIR / "plugin.json"
    if manifest_path.exists():
        with open(manifest_path, 'r') as f:
            return json.load(f)
    return {}

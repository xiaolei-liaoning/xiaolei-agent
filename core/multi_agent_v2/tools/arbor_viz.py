"""ARBOR 假设树可视化工具

生成交互式 HTML 树形图，展示假设树的预测/选择/实施过程。
节点颜色表示状态，箭头颜色匹配子节点状态。
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

_TREE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ARBOR 假设树</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; overflow: hidden; height: 100vh; }
#container { width: 100%; height: 100vh; }
.title-card { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: rgba(15,23,42,0.85); border: 1px solid #334155; border-radius: 12px; padding: 10px 24px; z-index: 100; backdrop-filter: blur(8px); text-align: center; pointer-events: none; }
.title-card h1 { font-size: 18px; font-weight: 600; color: #f1f5f9; letter-spacing: 0.5px; }
.title-card span { font-size: 12px; color: #64748b; margin-left: 8px; }
.legend { position: fixed; bottom: 24px; right: 24px; background: rgba(15,23,42,0.9); border: 1px solid #334155; border-radius: 10px; padding: 12px 16px; z-index: 100; backdrop-filter: blur(8px); font-size: 12px; display: flex; flex-direction: column; gap: 6px; }
.legend-item { display: flex; align-items: center; gap: 8px; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.1); }
.legend-label { color: #94a3b8; font-size: 11px; }
.node { cursor: pointer; transition: opacity 0.2s; }
.node:hover { opacity: 0.85; }
.node rect { stroke-width: 2; transition: all 0.3s; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3)); }
.node rect.implemented { fill: #166534; stroke: #22c55e; }
.node rect.selected { fill: #14532d; stroke: #4ade80; }
.node rect.predicted { fill: #1e3a5f; stroke: #60a5fa; }
.node rect.pruned { fill: #1f2937; stroke: #6b7280; }
.node rect.root { fill: #312e81; stroke: #818cf8; }
.node text { fill: #f1f5f9; font-size: 13px; font-weight: 500; pointer-events: none; }
.node text.sub { fill: #94a3b8; font-size: 10px; font-weight: 400; }
.link { fill: none; stroke-width: 2; transition: all 0.3s; }
.link.implemented { stroke: #22c55e; }
.link.selected { stroke: #4ade80; }
.link.predicted { stroke: #60a5fa; }
.link.pruned { stroke: #6b7280; }
.tooltip { position: fixed; background: rgba(15,23,42,0.95); border: 1px solid #475569; border-radius: 8px; padding: 8px 12px; font-size: 12px; pointer-events: none; z-index: 200; display: none; max-width: 280px; backdrop-filter: blur(8px); }
.tooltip .tt-label { color: #e2e8f0; font-weight: 600; margin-bottom: 4px; }
.tooltip .tt-status { color: #94a3b8; font-size: 11px; }
.tooltip .tt-detail { color: #64748b; font-size: 11px; margin-top: 2px; }
.controls { position: fixed; bottom: 24px; left: 24px; z-index: 100; display: flex; gap: 8px; }
.controls button { background: rgba(30,41,59,0.9); border: 1px solid #475569; color: #e2e8f0; padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 12px; backdrop-filter: blur(8px); transition: all 0.2s; }
.controls button:hover { background: #334155; border-color: #60a5fa; }
</style>
</head>
<body>
<div id="container"></div>
<div class="title-card"><h1>🌳 ARBOR 假设树 <span id="title-sub"></span></h1></div>
<div class="tooltip" id="tooltip"><div class="tt-label" id="tt-label"></div><div class="tt-status" id="tt-status"></div><div class="tt-detail" id="tt-detail"></div></div>
<div class="legend">
<div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div><span class="legend-label">已实施</span></div>
<div class="legend-item"><div class="legend-dot" style="background:#4ade80"></div><span class="legend-label">已选定</span></div>
<div class="legend-item"><div class="legend-dot" style="background:#60a5fa"></div><span class="legend-label">预测中</span></div>
<div class="legend-item"><div class="legend-dot" style="background:#6b7280"></div><span class="legend-label">已剪枝</span></div>
</div>
<div class="controls"><button onclick="zoomIn()">＋ 放大</button><button onclick="zoomOut()">－ 缩小</button><button onclick="resetView()">⟲ 复位</button></div>
<script>
const DATA = {NODES_DATA};

const statusColors = {
  implemented: { node: '#166534', stroke: '#22c55e', link: '#22c55e' },
  selected: { node: '#14532d', stroke: '#4ade80', link: '#4ade80' },
  predicted: { node: '#1e3a5f', stroke: '#60a5fa', link: '#60a5fa' },
  pruned: { node: '#1f2937', stroke: '#6b7280', link: '#6b7280' },
};

document.getElementById('title-sub').textContent = DATA.title || '';

const stratify = d3.stratify()
  .id(d => d.id)
  .parentId(d => d.parent_id)
  (DATA.nodes.filter(n => n.id !== 'root'));

stratify.each(n => {
  const raw = DATA.nodes.find(d => d.id === n.id);
  n.data.status = raw.status || 'predicted';
  n.data.detail = raw.detail || '';
});

const width = window.innerWidth, height = window.innerHeight;
const svg = d3.select('#container').append('svg')
  .attr('width', width).attr('height', height)
  .style('display', 'block');

const g = svg.append('g').attr('transform', `translate(0,40)`);

const treeLayout = d3.tree().nodeSize([200, 100]).separation((a, b) => (a.parent === b.parent ? 1.5 : 2));
const root = treeLayout(stratify);

const minX = d3.min(root.descendants(), d => d.x) || 0;
const maxX = d3.max(root.descendants(), d => d.x) || width;
const treeWidth = maxX - minX;
const offsetX = Math.max(40, (width - treeWidth) / 2 - minX);
const initialScale = Math.min(1, width / (treeWidth + 160));

let zoom = d3.zoom().scaleExtent([0.2, 3]).on('zoom', e => g.attr('transform', e.transform));
svg.call(zoom);

const links = g.append('g').selectAll('.link')
  .data(root.links()).join('path')
  .attr('class', d => `link ${d.target.data.status}`)
  .attr('d', d => {
    const dx = d.target.x - d.source.x, dy = d.target.y - d.source.y;
    const cx = (d.source.x + d.target.x) / 2;
    return `M${d.source.x},${d.source.y} Q${cx},${d.source.y + dy/2} ${d.target.x},${d.target.y}`;
  })
  .attr('stroke', d => statusColors[d.target.data.status]?.link || '#6b7280')
  .attr('stroke-width', 2.5)
  .attr('fill', 'none')
  .attr('marker-end', d => `url(#arrow-${d.target.data.status})`);

const defs = svg.append('defs');
['implemented','selected','predicted','pruned'].forEach(s => {
  const c = statusColors[s]?.link || '#6b7280';
  defs.append('marker').attr('id', `arrow-${s}`).attr('viewBox', '0 -5 10 10')
    .attr('refX', 22).attr('refY', -0.5).attr('markerWidth', 8).attr('markerHeight', 8)
    .attr('orient', 'auto').append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', c);
});

const nodes = g.append('g').selectAll('.node')
  .data(root.descendants()).join('g')
  .attr('class', 'node')
  .attr('transform', d => `translate(${d.x},${d.y})`);

nodes.each(function(d) {
  const node = d3.select(this);
  const status = d.data.status || 'predicted';
  const label = d.data.id;
  const detail = d.data.detail || '';
  const isRoot = d.depth === 0;
  const cls = isRoot ? 'root' : status;

  const lines = [label];
  if (detail) lines.push(...detail.split('\n').slice(0,2));
  const maxW = Math.max(...lines.map(l => l.length)) * 9 + 24;
  const h = lines.length * 20 + 16;

  node.append('rect').attr('class', cls)
    .attr('x', -maxW/2).attr('y', -h/2)
    .attr('width', maxW).attr('height', h)
    .attr('rx', 8).attr('ry', 8);

  node.append('text').attr('text-anchor', 'middle')
    .attr('y', -h/2 + (lines.length === 1 ? 20 : 26))
    .text(label);

  if (detail) {
    node.append('text').attr('class', 'sub')
      .attr('text-anchor', 'middle')
      .attr('y', -h/2 + 44)
      .text(detail.length > 30 ? detail.slice(0, 28) + '…' : detail);
  }

  node.on('mouseover', function(e) {
    const tt = document.getElementById('tooltip');
    document.getElementById('tt-label').textContent = label;
    document.getElementById('tt-status').textContent = `状态: ${status}`;
    document.getElementById('tt-detail').textContent = detail || '';
    tt.style.display = 'block';
    tt.style.left = (e.clientX + 12) + 'px';
    tt.style.top = (e.clientY - 10) + 'px';
  }).on('mousemove', function(e) {
    const tt = document.getElementById('tooltip');
    tt.style.left = (e.clientX + 12) + 'px';
    tt.style.top = (e.clientY - 10) + 'px';
  }).on('mouseout', () => document.getElementById('tooltip').style.display = 'none');
});

svg.call(zoom.transform, d3.zoomIdentity.translate(offsetX, 40).scale(initialScale));

window.zoomIn = () => svg.transition().duration(300).call(zoom.scaleBy, 1.3);
window.zoomOut = () => svg.transition().duration(300).call(zoom.scaleBy, 0.7);
window.resetView = () => svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(offsetX, 40).scale(initialScale));

window.addEventListener('resize', () => {
  svg.attr('width', window.innerWidth).attr('height', window.innerHeight);
});
</script>
</body>
</html>"""


async def handle_arbor_viz(args: dict) -> dict:
    """生成 ARBOR 假设树交互式 HTML 可视化"""
    nodes = args.get("nodes", [])
    title = args.get("title", "")
    output_path = args.get("output_path", "~/Desktop/arbor_tree.html")

    if not nodes:
        return {"ok": False, "error": "需要 nodes 参数", "data": ""}

    node_ids = {n.get("id") for n in nodes}
    for n in nodes:
        pid = n.get("parent_id")
        if pid and pid not in node_ids and pid != "root":
            n["parent_id"] = "root"

    if not any(n.get("id") == "root" for n in nodes):
        nodes.insert(0, {"id": "root", "parent_id": "", "status": "implemented", "detail": "根节点"})

    for n in nodes:
        n.setdefault("status", "predicted")
        n.setdefault("detail", "")

    html = _TREE_TEMPLATE.replace("{NODES_DATA}", json.dumps({
        "nodes": nodes,
        "title": title or f"共 {len(nodes)} 个节点",
    }, ensure_ascii=False))

    path = os.path.expanduser(output_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"ARBOR 假设树已生成: {path} ({len(nodes)} 节点)")
    return {"ok": True, "data": f"✅ ARBOR 假设树已生成: {path} ({len(nodes)} 节点)"}

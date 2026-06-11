# Obsidian Visual Skills Pack

为 Obsidian 用户提供的可视化技能包，支持从文本生成 Canvas、Excalidraw 和 Mermaid 图表。

## 包含的 Skills

### 1. Excalidraw Diagram Generator
生成手绘风格的 Excalidraw 图表。

**触发词：**
- `Excalidraw`、`画图`、`流程图`、`思维导图`、`可视化`
- `标准Excalidraw`、`standard excalidraw`
- `Excalidraw动画`、`动画图`、`animate`

**输出格式：**
- Obsidian 模式：`.md` 文件（默认）
- Standard 模式：`.excalidraw` 文件
- Animated 模式：`.excalidraw` 文件（带动画）

### 2. Mermaid Visualizer
将文本内容转换为专业的 Mermaid 图表。

**支持的图表类型：**
- 流程图 (Process Flow)
- 循环图 (Circular Flow)
- 对比图 (Comparison)
- 思维导图 (Mindmap)
- 时序图 (Sequence)
- 状态图 (State)

**特点：**
- 自动修复语法错误
- 支持 Obsidian 和 GitHub 渲染
- 多种布局和样式选项

### 3. Obsidian Canvas Creator
创建 Obsidian Canvas 画布文件。

**布局类型：**
- MindMap 布局：放射状思维导图
- Freeform 布局：自由格式画布

**特点：**
- 自动计算节点位置
- 支持分组和连接
- 颜色编码系统

## 安装

### OpenCode
Skills 已安装到：`.opencode/skills/obsidian-visual-skills/`

### Claude Code
Skills 已安装到：`.claude/skills/obsidian-visual-skills/`

## 使用方法

在 Claude Code 或支持 Claude Skills 的工具中，使用对应的触发词即可激活相应的 skill。

### 示例

```
用户：帮我画一个软件开发流程图
→ 激活 Mermaid Visualizer skill

用户：创建一个关于太阳系的思维导图
→ 激活 Excalidraw Diagram skill

用户：把这个笔记内容转成 Canvas
→ 激活 Obsidian Canvas Creator skill
```

## 来源

- GitHub: https://github.com/axtonliu/axton-obsidian-visual-skills
- 作者: axtonliu
- 许可证: MIT
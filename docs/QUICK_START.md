# 🚀 快速开始指南 - 小雷版小龙虾 AI Agent v3.3.1

**最后更新**: 2026-04-28

---

## 📋 目录

1. [快速启动](#快速启动)
2. [核心功能](#核心功能)
3. [快捷指令](#快捷指令)
4. [常见问题](#常见问题)

---

## 快速启动

### 方式一：使用管理脚本（推荐）⭐

```bash
# 启动开发服务（带热重载）
./dev.sh dev

# 查看实时日志
./dev.sh logs

# 查看服务状态
./dev.sh status
```

### 方式二：直接启动

```bash
# 生产模式
python main.py

# 开发模式（热重载）
export DEV_MODE=true && python main.py
```

### 访问地址

启动成功后，访问以下地址：

- **Coze 聊天**: http://localhost:8001/coze
- **工作流编辑器**: http://localhost:8001/workflow_editor
- **API 文档**: http://localhost:8001/docs

---

## 核心功能

### 1. 💬 智能聊天

**基本使用**:
1. 访问 http://localhost:8001/coze
2. 在输入框中输入消息
3. 按 Enter 或点击发送按钮

**特色功能**:

#### 消息历史记录 ⭐
- ✅ 自动保存所有聊天记录
- ✅ 点击"恢复历史"按钮恢复之前的对话
- ✅ 支持导出为 JSON 或 TXT 格式

**操作步骤**:
```
1. 发送几条消息
2. 刷新页面或关闭浏览器
3. 重新打开页面
4. 点击"恢复历史"按钮
5. 之前的聊天记录立即恢复
```

#### 文件上传与 OCR 识别 ⭐
- ✅ 拖拽图片到聊天区域
- ✅ 点击回形针图标选择文件
- ✅ 自动识别图片中的文字

**支持的文件类型**:
- 图片: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.gif`
- 文档: `.pdf`, `.txt`, `.doc`, `.docx`

**使用示例**:
```
1. 拖拽一张包含文字的图片到聊天区域
2. 输入："识别这张图片中的文字"
3. 点击发送
4. AI 会返回识别结果
```

### 2. 🎯 快捷指令 ⭐

**使用方法**:
1. 在输入框中输入 `/`
2. 看到指令建议列表
3. 使用上下箭头或鼠标选择
4. 按 Tab 或 Enter 确认
5. 继续输入具体内容

**支持的指令**:

| 指令 | 说明 | 示例 |
|------|------|------|
| `/天气` | 查询天气 | `/天气 北京` |
| `/翻译` | 翻译内容 | `/翻译 Hello World` |
| `/分析` | 分析内容 | `/分析 这段代码` |
| `/思考` | 深度思考 | `/思考 这个问题` |
| `/爬虫` | 抓取数据 | `/爬虫 GitHub` |
| `/自动化` | 自动化任务 | `/自动化 这个流程` |
| `/总结` | 总结内容 | `/总结 这篇文章` |
| `/解释` | 解释概念 | `/解释 什么是AI` |
| `/代码` | 编写代码 | `/代码 Python排序` |
| `/优化` | 优化代码 | `/优化 这段函数` |

**键盘快捷键**:
- `↑/↓` - 上下导航
- `Tab/Enter` - 选择指令
- `ESC` - 关闭提示框

### 3. 🔄 工作流编辑器

**访问**: http://localhost:8001/workflow_editor

**功能**:
- ✅ 拖拽节点到画布
- ✅ 连接节点创建工作流
- ✅ 选择技能工具
- ✅ 导出/导入工作流（JSON格式）
- ✅ 缩放和清空画布

**使用步骤**:
```
1. 从左侧面板拖拽节点到画布
2. 点击节点配置属性
3. 拖动连线连接节点
4. 点击"导出"保存工作流
5. 点击"导入"加载已有工作流
```

---

## 常见问题

### Q1: 如何清除浏览器缓存？

**Chrome/Edge**:
```
1. 按 Ctrl+Shift+R (Windows/Linux) 或 Cmd+Shift+R (Mac)
2. 或打开开发者工具 (F12)
3. 右键刷新按钮，选择"清空缓存并硬性重新加载"
```

**Firefox**:
```
1. 按 Ctrl+F5 (Windows/Linux) 或 Cmd+Shift+R (Mac)
```

### Q2: 消息历史保存在哪里？

消息历史保存在浏览器的 `localStorage` 中：
- **键名**: `coze_message_history`
- **位置**: 浏览器本地存储
- **限制**: 默认最多保存 100 条消息

**手动查看**:
```javascript
// 在浏览器控制台执行
console.log(localStorage.getItem('coze_message_history'));
```

### Q3: 如何修改最大保存消息数？

在浏览器控制台执行：
```javascript
// 加载当前设置
const prefs = JSON.parse(localStorage.getItem('coze_preferences'));

// 修改最大保存数（例如改为 200）
prefs.maxHistoryLength = 200;

// 保存
localStorage.setItem('coze_preferences', JSON.stringify(prefs));

console.log('✅ 已更新最大保存消息数为:', prefs.maxHistoryLength);
```

### Q4: 文件上传失败怎么办？

检查以下几点：
1. **文件大小**: 确保不超过 10MB
2. **文件格式**: 确认是支持的类型（图片、PDF、TXT等）
3. **网络连接**: 确保服务正常运行
4. **浏览器控制台**: 查看详细错误信息

**调试方法**:
```javascript
// 在浏览器控制台查看上传日志
// 应该看到类似这样的输出：
// 📎 检测到 1 个文件被拖拽
// ✅ 文件上传成功: /uploads/image.jpg
```

### Q5: 如何启用热重载？

**方法一**: 使用管理脚本
```bash
./dev.sh dev
```

**方法二**: 设置环境变量
```bash
export DEV_MODE=true
python main.py
```

**效果**:
- 修改代码后自动重启服务
- 无需手动停止和启动
- 重载目录: `api/`, `core/`, `skills/`, `tools/`

### Q6: 服务启动失败怎么办？

**检查端口占用**:
```bash
# 查看 8001 端口是否被占用
lsof -i :8001

# 如果被占用，停止旧进程
kill <PID>
```

**查看详细日志**:
```bash
# 使用管理脚本查看
./dev.sh logs

# 或直接查看日志文件
tail -f logs/server.log
```

**常见错误**:
- `Address already in use`: 端口被占用，需要停止旧进程
- `ModuleNotFoundError`: 缺少依赖，运行 `pip install -r requirements.txt`
- `Database connection failed`: 数据库未启动，检查 MySQL 服务

### Q7: 如何自定义快捷指令？

编辑 `static/js/coze.js` 文件，找到 `QuickCommandAutocomplete.commands` 对象：

```javascript
const QuickCommandAutocomplete = {
    commands: {
        '/天气': '帮我查询今天的天气',
        '/翻译': '请帮我翻译以下内容',
        // 添加你的自定义指令
        '/我的指令': '这是我的自定义指令',
    },
    // ...
};
```

保存后刷新页面即可生效（如果启用了热重载则自动生效）。

---

## 🛠️ 开发工具

### 服务管理脚本 (dev.sh)

```bash
# 启动服务
./dev.sh start      # 生产模式
./dev.sh dev        # 开发模式（热重载）

# 管理服务
./dev.sh stop       # 停止服务
./dev.sh restart    # 重启服务
./dev.sh status     # 查看状态
./dev.sh logs       # 查看实时日志
```

### 测试脚本

```bash
# 运行综合测试
python test_comprehensive.py

# 运行前端功能测试
python test_frontend_fixes.py

# 运行 OCR 功能测试
python test_ocr_full.py
```

---

## 📚 更多资源

- **API 文档**: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
- **优化报告**: [FINAL_OPTIMIZATION_REPORT.md](FINAL_OPTIMIZATION_REPORT.md)
- **问题反馈**: 提交 Issue 或联系开发团队

---

## 🎉 开始体验

现在你已经了解了所有核心功能，开始体验吧！

```bash
# 启动服务
./dev.sh dev

# 打开浏览器
# http://localhost:8001/coze
```

祝你使用愉快！🚀

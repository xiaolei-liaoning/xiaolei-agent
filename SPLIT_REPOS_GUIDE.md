# 📦 仓库拆分说明

## 拆分方案

将项目拆分为两个GitHub仓库：

### 1️⃣ 公开仓库 (xiaolei-agent-docs)
**地址**: `https://github.com/你的用户名/xiaolei-agent-docs`
**权限**: Public（所有人可见）

**包含内容**:
| 文件/目录 | 说明 |
|-----------|------|
| `README.md` | 项目介绍 |
| `00.md` | 核心技术架构文档（7大核心模块+架构图） |
| `QUICK_START.md` | 快速开始指南 |
| `USER_GUIDE.md` | 用户使用指南 |
| `templates/` | 前端UI示例（chat.html, coze.html等） |
| `api/monitor.py` | 监控API示例 |
| `api/schedule.py` | 调度API示例 |
| `.env.example` | 环境变量配置模板 |
| `.github/workflows/ci-cd.yml` | CI配置 |

---

### 2️⃣ 私有仓库 (xiaolei-agent-core)
**地址**: `https://github.com/你的用户名/xiaolei-agent-core`
**权限**: Private（仅自己可见）

**包含内容**:
| 文件/目录 | 说明 |
|-----------|------|
| `core/` | 核心业务逻辑（handlers, bfs_processor, multi_agent等） |
| `skills/` | 全部技能模块（10+技能） |
| `api/v1.py` | 核心API路由 |
| `api/workflow.py` | 工作流API |
| `main.py` | 项目入口 |
| `requirements.txt` | Python依赖 |
| 其他核心Python文件 | |

---

## 🔧 手动操作步骤

### 第一步：创建GitHub仓库

1. 登录 GitHub: https://github.com

2. 创建**公开仓库** `xiaolei-agent-docs`
   - 点击右上角 `+` → `New repository`
   - 名称: `xiaolei-agent-docs`
   - 选择: **Public**
   - 不勾选 "Initialize this repository with a README"

3. 创建**私有仓库** `xiaolei-agent-core`
   - 点击右上角 `+` → `New repository`
   - 名称: `xiaolei-agent-core`
   - 选择: **Private**
   - 不勾选 "Initialize this repository with a README"

---

### 第二步：设置公开仓库

```bash
# 1. 克隆当前仓库
git clone https://github.com/xiaolei-liaoning/xiaolei-agent.git
cd xiaolei-agent

# 2. 创建公开版本（排除核心代码）
git checkout --orphan public-docs

# 3. 移除核心代码（只保留文档）
git rm -rf core/
git rm -rf skills/           # 保留 skills/marketplace/ 和 skills/人物/
git rm api/v1.py
git rm api/workflow.py
git rm main.py
git rm requirements.txt

# 4. 添加文档和示例
git add README.md 00.md QUICK_START.md USER_GUIDE.md
git add templates/
git add api/monitor.py api/schedule.py
git add .env.example
git add .github/workflows/ci-cd.yml

# 5. 提交
git commit -m "✨ 文档与示例初始版本"

# 6. 推送到公开仓库
git remote set-url origin https://github.com/你的用户名/xiaolei-agent-docs.git
git push -u origin public-docs:main
```

---

### 第三步：设置私有仓库

```bash
# 在另一个目录操作
cd ..
git clone https://github.com/xiaolei-liaoning/xiaolei-agent.git xiaolei-agent-core
cd xiaolei-agent-core

# 推送到私有仓库
git remote set-url origin https://github.com/你的用户名/xiaolei-agent-core.git
git push -u origin main
```

---

## ⚠️ 注意事项

1. **先备份仓库** - 操作前先备份当前仓库
2. **GitHub免费账户限制** - 免费账户只能有有限个私有仓库（Pro账户无限制）
3. **原仓库处理** - 可以选择删除原仓库，或保留为私有版本
4. **敏感信息检查** - 确保私有仓库中没有 `.env` 文件等敏感信息

---

## 📊 拆分后的项目结构

```
┌─────────────────────────────────────────────────────────┐
│  GitHub: xiaolei-liaoning/xiaolei-agent                │
│  ↓ 拆分后                                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📄 公开仓库: xiaolei-agent-docs                        │
│  ├── README.md (项目介绍)                              │
│  ├── 00.md (架构文档)                                  │
│  ├── QUICK_START.md                                    │
│  ├── USER_GUIDE.md                                     │
│  ├── templates/ (UI示例)                               │
│  └── .github/workflows/                                │
│                                                         │
│  🔒 私有仓库: xiaolei-agent-core                        │
│  ├── core/ (核心逻辑)                                  │
│  ├── skills/ (技能市场)                                │
│  ├── api/v1.py, workflow.py                           │
│  ├── main.py                                           │
│  └── requirements.txt                                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## ✅ 验证拆分成功

1. 打开 `https://github.com/你的用户名/xiaolei-agent-docs`
   - 应该只能看到文档和前端示例
   - 不应该看到 `core/` 和 `skills/` 目录

2. 登录GitHub后访问 `https://github.com/你的用户名/xiaolei-agent-core`
   - 应该能看到全部代码

---

## 🚀 快速重新同步

如果日后需要更新，可以分别推送：

```bash
# 更新公开仓库
cd xiaolei-agent-docs
git pull origin main  # 从原仓库拉取更新
git push origin main

# 更新私有仓库
cd xiaolei-agent-core
git pull origin main
git push origin main
```

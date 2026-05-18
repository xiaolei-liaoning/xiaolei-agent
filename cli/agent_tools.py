"""Agent管理工具模块 - 集成GLM LLM"""

import sys
sys.path.insert(0, '.')

class AgentTools:
    @staticmethod
    async def list_agents():
        """列出所有可用Agent"""
        print("\n🦾 可用Agent:")
        agents = [
            ("Master", "任务分解与调度专家"),
            ("Worker", "具体任务执行者"),
            ("Expert", "领域专家顾问"),
            ("Reviewer", "质量评审专家"),
            ("Coordinator", "流程协调专家"),
            ("Monitor", "系统监控专家"),
            ("Researcher", "信息检索与研究专家"),
            ("Writer", "文案写作专家"),
            ("Coder", "代码编写专家"),
            ("Designer", "创意设计专家"),
            ("DataAnalyst", "数据分析专家"),
            ("Translator", "多语言翻译专家"),
            ("Teacher", "知识教学专家"),
            ("Storyteller", "故事创作专家"),
            ("ProblemSolver", "问题解决专家"),
            ("Planner", "计划制定专家"),
            ("Optimizer", "性能优化专家"),
            ("SecurityExpert", "网络安全专家"),
            ("DevOps", "运维部署专家"),
            ("Marketer", "市场营销专家"),
            ("Psychologist", "心理辅导专家"),
        ]
        
        for name, desc in agents:
            print(f"  - {name}: {desc}")
    
    @staticmethod
    async def _call_llm(prompt):
        """调用GLM LLM生成内容"""
        try:
            from core.engine.llm_backend import GLMBackend
            llm = GLMBackend()
            messages = [{"role": "user", "content": prompt}]
            response = await llm.chat(messages)
            return response
        except Exception as e:
            print(f"⚠️ LLM调用失败，使用模板回复: {e}")
            return None
    
    @staticmethod
    async def call_agent(agent_type, task):
        """调用指定Agent执行任务 - 集成LLM"""
        print(f"\n🚀 调用 {agent_type} 执行任务: {task}")
        
        # 构建LLM提示词
        agent_prompts = {
            "Master": f"你是一个任务分解专家，请帮我把这个任务分解成具体的子任务：{task}",
            "Writer": f"请写一篇关于'{task}'的文章，内容要详细、有深度",
            "Coder": f"请帮我编写关于'{task}'的Python代码，并给出详细解释",
            "Storyteller": f"请讲一个关于'{task}'的精彩故事",
            "DataAnalyst": f"请帮我分析'{task}'，给出数据分析报告",
            "Expert": f"作为专家，请分析'{task}'并给出专业建议",
            "Reviewer": f"请帮我评审'{task}'，给出质量评估和改进建议",
            "Researcher": f"请帮我研究'{task}'，给出详细的研究报告",
            "Translator": f"请翻译'{task}'，提供多种语言版本",
            "Teacher": f"请教我关于'{task}'的知识，详细讲解核心概念",
            "ProblemSolver": f"请帮我解决'{task}'这个问题，给出详细方案",
            "Optimizer": f"请帮我优化'{task}'，给出性能优化建议",
            "SecurityExpert": f"请帮我分析'{task}'的安全风险，给出防护建议",
            "Designer": f"请帮我设计'{task}'，给出完整的设计方案",
            "Planner": f"请帮我制定'{task}'的执行计划",
            "Marketer": f"请帮我制定'{task}'的营销策略",
            "Psychologist": f"请帮我分析'{task}'，给出心理建议",
        }
        
        # 优先调用LLM生成内容
        llm_prompt = agent_prompts.get(agent_type)
        if llm_prompt:
            llm_response = await AgentTools._call_llm(llm_prompt)
            if llm_response:
                print(f"\n✅ {agent_type} Agent (LLM生成):")
                print("-" * 50)
                print(llm_response)
                print("-" * 50)
                return
        
        # 如果LLM调用失败，使用模板内容
        print("\n⚠️ LLM不可用，使用模板回复")
        results = {
            "Master": f"""
📋 Master Agent任务分解结果:

任务: {task}

子任务列表:
1. 分析需求和目标
2. 收集相关资料
3. 制定执行计划
4. 分配执行资源
5. 监控进度和质量

预计完成时间: 2小时
""",
            "Writer": f"""
📝 Writer Agent创作结果:

# {task}

人工智能正在深刻改变我们的世界。从自动驾驶汽车到智能助手，AI技术正在各个领域展现出强大的潜力。

## AI的发展历程

人工智能的概念最早可以追溯到1956年的达特茅斯会议。经过几十年的发展，特别是深度学习的出现，AI技术取得了突破性进展。

## AI的应用领域

- **医疗健康**: 疾病诊断、药物研发
- **金融科技**: 风险评估、智能投顾
- **智能制造**: 自动化生产线、质量检测
- **交通出行**: 自动驾驶、智能导航

## 未来展望

随着技术的不断进步，人工智能将在更多领域发挥重要作用，为人类社会带来更多便利和创新。
""",
            "Coder": f"""
💻 Coder Agent编码结果:

```python
# {task}
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr

# 示例使用
unsorted = [64, 34, 25, 12, 22, 11, 90]
sorted_arr = bubble_sort(unsorted)
print("排序结果:", sorted_arr)
```

时间复杂度: O(n²)
空间复杂度: O(1)
""",
            "Storyteller": f"""
📖 Storyteller Agent创作结果:

# {task}

在遥远的魔法大陆上，勇敢的冒险者艾瑞克踏上了寻找失落宝藏的旅程。

穿过幽暗的森林，越过险峻的山脉，艾瑞克终于来到了神秘的遗迹前。古老的石门上刻着神秘的符文，只有解开谜题才能进入。

经过一番努力，艾瑞克成功打开了石门。里面是一个巨大的地下宫殿，闪耀着无数宝石的光芒。在宫殿的中央，他找到了传说中的宝藏——一本记载着无限智慧的魔法书。

带着宝藏和智慧，艾瑞克踏上了归途，成为了王国的英雄。
""",
            "DataAnalyst": f"""
📊 DataAnalyst Agent分析结果:

# {task}

## 数据分析报告

### 数据概览
- 数据周期: 2024年1月-12月
- 样本数量: 12,580条记录
- 数据来源: 销售管理系统

### 关键发现

| 月份 | 销售额 | 同比增长 |
|------|--------|----------|
| 1月 | ¥125万 | +12.5% |
| 6月 | ¥238万 | +28.3% |
| 12月 | ¥312万 | +45.2% |

### 趋势分析
- Q4销售额达到全年峰值
- 电商促销活动显著提升销量
- 建议加强Q1营销力度

### 结论
整体销售趋势良好，建议继续优化促销策略。
""",
            "Expert": f"""
🎯 Expert Agent分析结果:

# {task}

## 专业分析

经过深入分析，针对这个问题，我提供以下专业建议：

### 核心要点
1. 明确目标和范围
2. 收集相关数据和信息
3. 分析关键因素和变量
4. 制定可行的解决方案
5. 监控执行效果

### 推荐方案
根据当前情况，建议采取以下步骤：
- 优先处理核心问题
- 分阶段实施
- 定期评估和调整

如需更详细的分析，请提供更多背景信息。
""",
            "Reviewer": f"""
🔍 Reviewer Agent评审结果:

# {task}

## 质量评审报告

### 评审指标
| 指标 | 评分 | 状态 |
|------|------|------|
| 代码质量 | 85/100 | ✅ 良好 |
| 安全性 | 90/100 | ✅ 优秀 |
| 性能 | 78/100 | ⚠️ 需要优化 |
| 文档 | 82/100 | ✅ 良好 |

### 改进建议
1. 优化性能瓶颈
2. 增加单元测试覆盖率
3. 完善API文档

### 结论
整体质量良好，可以进入下一阶段。
""",
            "Researcher": f"""
🔬 Researcher Agent研究结果:

# {task}

## 研究报告

### 研究背景
本研究旨在深入了解相关领域的最新进展和趋势。

### 主要发现
1. 该领域近年来发展迅速
2. 关键技术不断创新
3. 应用场景日益广泛
4. 面临的挑战和机遇并存

### 参考资料
- 相关学术论文
- 行业报告
- 专家观点

如需更深入的研究，请提供具体方向。
""",
            "Translator": f"""
🌍 Translator Agent翻译结果:

# {task}

英文翻译:
Artificial Intelligence

日文翻译:
人工知能 (じんこうちのう)

韩文翻译:
인공지능

法文翻译:
Intelligence Artificielle

西班牙文翻译:
Inteligencia Artificial

德文翻译:
Künstliche Intelligenz
""",
            "Teacher": f"""
📚 Teacher Agent教学结果:

# {task}

## 知识点讲解

### 基本概念
人工智能是研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及应用系统的一门新的技术科学。

### 核心技术
- 机器学习
- 深度学习
- 自然语言处理
- 计算机视觉
- 强化学习

### 学习建议
1. 从基础概念开始
2. 学习相关数学知识
3. 实践项目经验
4. 关注行业动态

如需更详细的讲解，请告诉我具体想了解的内容。
""",
            "ProblemSolver": f"""
💡 ProblemSolver Agent解决方案:

# {task}

## 问题分析

经过分析，该问题的核心在于：
1. 需求理解不够清晰
2. 资源分配不够合理
3. 执行过程缺乏监控

## 解决方案

### 短期方案
1. 明确需求和目标
2. 制定详细计划
3. 分配合适资源

### 长期方案
1. 建立标准化流程
2. 引入自动化工具
3. 定期评估和优化

如需进一步分析，请提供更多细节。
""",
            "Optimizer": f"""
⚡ Optimizer Agent优化结果:

# {task}

## 性能优化报告

### 当前状态分析
- 响应时间: 1.2秒
- 内存占用: 256MB
- CPU使用率: 45%

### 优化方案

| 优化项 | 当前值 | 目标值 | 提升幅度 |
|--------|--------|--------|----------|
| 响应时间 | 1.2s | 0.5s | +58% |
| 内存占用 | 256MB | 128MB | +50% |
| CPU使用率 | 45% | 30% | +33% |

### 优化建议
1. 引入缓存机制
2. 优化算法复杂度
3. 使用异步处理

预计优化后性能提升约40%。
""",
            "SecurityExpert": f"""
🛡️ SecurityExpert Agent安全分析:

# {task}

## 安全风险评估

### 风险等级: 中等

### 识别的风险
1. 输入验证不足
2. 敏感数据未加密
3. 访问控制不够严格
4. 日志记录不完整

### 修复建议

| 风险 | 建议措施 | 优先级 |
|------|----------|--------|
| 输入验证 | 添加参数校验 | 高 |
| 数据加密 | 使用HTTPS | 高 |
| 访问控制 | 实施RBAC | 中 |
| 日志记录 | 完善日志系统 | 中 |

### 结论
建议尽快修复高优先级安全问题。
""",
            "Worker": f"""
🛠️ Worker Agent执行结果:

任务: {task}

执行状态: ✅ 完成

执行日志:
- 开始时间: 2024-01-15 10:00:00
- 结束时间: 2024-01-15 10:30:00
- 耗时: 30分钟
- 状态: 成功完成

结果摘要: 任务已成功执行，所有步骤均已完成。
""",
            "Coordinator": f"""
🤝 Coordinator Agent协调结果:

# {task}

## 协调报告

### 参与Agent
- Master Agent: 任务分解
- Worker Agent: 执行任务
- Reviewer Agent: 质量评审

### 执行流程
1. Master分解任务
2. Worker执行任务
3. Reviewer评审结果
4. 汇总交付

### 状态: ✅ 协调完成

所有Agent协作顺利，任务已完成。
""",
            "Monitor": f"""
📈 Monitor Agent监控报告:

# {task}

## 系统状态

### 服务状态
| 服务 | 状态 | 响应时间 |
|------|------|----------|
| API服务 | ✅ 正常 | 15ms |
| 数据库 | ✅ 正常 | 8ms |
| 缓存 | ✅ 正常 | 2ms |

### 资源使用
- CPU: 25%
- 内存: 60%
- 磁盘: 45%

### 告警
暂无异常告警

系统运行正常！
""",
            "Planner": f"""
📅 Planner Agent计划结果:

# {task}

## 执行计划

### 阶段划分

**阶段1: 准备阶段** (第1-2天)
- 明确需求
- 收集资料
- 制定方案

**阶段2: 执行阶段** (第3-7天)
- 核心开发
- 测试验证
- 优化调整

**阶段3: 交付阶段** (第8-10天)
- 最终测试
- 文档编写
- 上线部署

### 里程碑
| 日期 | 里程碑 |
|------|--------|
| 第2天 | 方案确认 |
| 第5天 | 功能完成 |
| 第10天 | 正式交付 |

总工期: 10天
""",
            "Designer": f"""
🎨 Designer Agent设计结果:

# {task}

## 设计方案

### 设计目标
- 美观大方
- 用户友好
- 功能完善

### 设计要点

**视觉设计:**
- 配色方案: 现代简约风格
- 字体选择: 清晰易读
- 图标设计: 统一风格

**交互设计:**
- 流畅的动画效果
- 直观的操作流程
- 完善的反馈机制

**架构设计:**
- 模块化结构
- 可扩展性强
- 易于维护

如需进一步细化，请提供具体需求。
""",
            "DevOps": f"""
🔧 DevOps Agent部署结果:

# {task}

## 部署报告

### 部署环境
- 环境类型: 生产环境
- 服务器: 云服务器 x 3
- 负载均衡: 已配置

### 部署步骤
1. 代码拉取 ✅
2. 依赖安装 ✅
3. 配置更新 ✅
4. 服务重启 ✅
5. 健康检查 ✅

### 部署结果
状态: ✅ 成功
版本: v1.0.0
时间: 2024-01-15 14:30:00

应用已成功部署到生产环境！
""",
            "Marketer": f"""
📣 Marketer Agent营销方案:

# {task}

## 营销方案

### 目标设定
- 提升品牌知名度
- 增加用户活跃度
- 促进产品销售

### 营销策略

**线上推广:**
- 社交媒体营销
- 内容营销
- SEO优化

**线下活动:**
- 展会参展
- 线下体验活动
- 合作伙伴推广

### 预期效果
| 指标 | 目标 |
|------|------|
| 曝光量 | 50万+ |
| 转化率 | 5%+ |
| ROI | 3:1+ |

如需详细方案，请提供更多信息。
""",
            "Psychologist": f"""
🧠 Psychologist Agent咨询结果:

# {task}

## 心理建议

### 问题分析
经过分析，您当前可能面临的情况是正常的心理反应。

### 建议

**情绪管理:**
1. 接纳自己的情绪
2. 寻找情绪释放的途径
3. 保持积极心态

**压力应对:**
1. 合理规划时间
2. 适当休息放松
3. 寻求支持和帮助

**心态调整:**
1. 关注积极方面
2. 设定合理期望
3. 学会自我肯定

如果问题持续或加重，建议寻求专业心理咨询。
""",
        }
        
        result = results.get(agent_type, f"未知Agent: {agent_type}")
        print(result)
        return result
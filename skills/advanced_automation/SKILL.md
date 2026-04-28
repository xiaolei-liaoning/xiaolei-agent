# Advanced Automation - 全链路自动化

## 📋 功能描述
Open Claw风格全链路自动化工作流，一句话完成复杂任务链。
- **智能编排**：自动识别意图并串联多个Skill
- **工作流引擎**：支持XML定义和AI生成
- **报告生成**：自动生成Markdown报告到桌面
- **定时任务**：支持cron表达式调度
- **邮件发送**：SMTP协议支持附件
- **PDF生成**：reportlab库生成PDF文档

## 🔑 触发关键词
- **中文**：工作流、自动执行、全链路、爬取并分析、生成报告、定时任务、发送邮件
- **英文**：workflow, automate, pipeline, schedule, send email

## ⚙️ 支持功能
| 功能 | 说明 | 示例 |
|------|------|------|
| execute_workflow | 执行工作流 | 爬取+分析+报告 |
| send_email | 发送邮件 | SMTP带附件 |
| generate_pdf | 生成PDF | reportlab库 |
| schedule_task | 定时任务 | cron表达式 |
| create_smart_workflow | AI生成工作流 | 自然语言描述 |

## 💡 使用示例
```python
# 全链路自动化
用户: "爬取微博热搜并分析趋势，生成报告到桌面"
→ 自动执行:
  1. 爬虫：抓取微博热搜Top10
  2. 分析：统计热词分布、生成柱状图
  3. 报告：生成Markdown文档
  4. 保存：~/Desktop/微博热搜分析_20260419.md
  5. 预览：自动用Mac预览打开

# 定时任务
用户: "每天早上9点爬取微博热搜"
→ advanced_automation.execute(action='schedule_task', 
    cron='0 9 * * *', 
    workflow_id='wf_weibo_daily')

# 发送邮件
用户: "发送报告给test@example.com"
→ advanced_automation.execute(action='send_email',
    to='test@example.com',
    subject='每日热点报告',
    body='<h1>今日热点</h1>',
    attachments=['report.pdf'])
```

## 📦 依赖
- workflow_engine (工作流引擎)
- APScheduler (定时任务)
- smtplib (邮件发送)
- reportlab (PDF生成)

## 🎯 性能指标
- 工作流创建: ~5ms
- 工作流执行: <1s (简单节点)
- 完整链路: ~8s (爬虫+分析+报告)
- 邮件发送: 1-3s
- PDF生成: 0.5-2s

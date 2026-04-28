# GUI Automation - 桌面自动化

## 📋 功能描述
macOS桌面应用自动化控制，支持21+种操作。
- **应用管理**：打开/退出应用、窗口切换
- **输入操作**：点击文字、输入文本、快捷键
- **系统控制**：截图、OCR识别、音量调节、亮度调节、通知
- **剪贴板**：读取/设置剪贴板内容

## 🔑 触发关键词
- **中文**：打开、点击、发送、微信、邮件、自动化、截图、通知
- **英文**：open, click, send, screenshot, notification, automate

## ⚙️ 支持操作
| 操作 | 说明 | 示例 |
|------|------|------|
| open_app | 打开应用 | WeChat, QQ, Safari |
| open_url | 打开网址 | https://example.com |
| type_text | 输入文本 | 自动打字 |
| click_text | 点击文字 | 点击“发送”按钮 |
| hotkey | 快捷键 | command+C, command+V |
| screenshot | 截屏 | 保存到桌面 |
| ocr_screenshot | OCR截图 | 截屏并识别文字 |
| notification | 发送通知 | 系统提醒 |
| wait | 等待 | 延时2秒 |
| volume_adjust | 调节音量 | 增大/减小 |
| quit_app | 退出应用 | 关闭微信 |
| set_clipboard | 设置剪贴板 | 复制文本 |
| get_clipboard | 读取剪贴板 | 粘贴内容 |

## 💡 使用示例
```python
# 打开应用
用户: "打开微信"
→ gui_automation.execute(action='open_app', app='WeChat')

# 发送消息
用户: "给豆包发消息：你好"
→ 自动执行: 打开微信 → 搜索豆包 → 输入消息 → 发送

# 截图
用户: "截屏"
→ gui_automation.execute(action='screenshot')

# 系统通知
用户: "提醒我喝水"
→ gui_automation.execute(action='notification', title='提醒', message='该喝水了！')
```

## 📦 依赖
- pyobjc (macOS API)
- PyAutoGUI (GUI自动化)
- pyperclip (剪贴板操作)

## 🎯 性能指标
- 应用启动: 1-3s
- 点击操作: <500ms
- 截图: <200ms
- 成功率: 90% (依赖UI稳定性)
# 计算器技能

## 技能信息

| 属性 | 值 |
|------|------|
| **名称** | 计算器 |
| **版本** | 1.0.0 |
| **分类** | 工具 / 数学计算 |
| **描述** | 提供基础数学计算功能,支持加减乘除 |
| **作者** | 小雷版小龙虾团队 |
| **创建时间** | 2026-04-28 |

## 功能特性

### ✅ 核心功能
- **基础运算**: 支持加减乘除四则运算
- **表达式计算**: 支持复杂数学表达式
- **历史记录**: 保存计算历史(可选)

## 支持的操作

| 操作 | 描述 | 必需参数 | 可选参数 |
|------|------|----------|----------|
| `calculate` | 执行计算 | expression | - |
| `history` | 查看历史 | - | - |
| `clear` | 清空历史 | - | - |

## 使用示例

```python
from skills.calculator.handler import get_calculator_handler

handler = get_calculator_handler()

# 基础计算
result = handler.execute('calculate', expression='2 + 3 * 4')
print(result['result'])  # 输出: 14

# 复杂表达式
result = handler.execute('calculate', expression='(10 + 5) / 3')
print(result['result'])  # 输出: 5.0
```

## 安全说明

- 仅允许数字和基本运算符(+,-,*,/,(),.)
- 禁止执行任意Python代码
- 表达式长度限制: 最多100字符

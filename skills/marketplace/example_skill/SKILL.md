# 天气查询技能

## Description
查询指定城市的实时天气信息，包括温度、湿度、风向等详细数据。

## Version
1.0.0

## Author
小雷版小龙虾团队

## Email
support@xiaolei.com

## Category
utility

## Tags
weather, forecast, temperature, utility

## Keywords
天气, 温度, 预报, 气象, climate

## Dependencies
{}

## Usage

```python
from skills.marketplace.example_skill.handler import handler

# 查询北京天气
result = await handler.execute(city="北京")
print(result)

# 查询上海天气
result = await handler.execute(city="上海")
print(result)
```

## Examples

### Example 1: 基本用法
```python
result = await handler.execute(city="北京")
# 返回: {"success": True, "result": "北京今天的天气是晴朗，温度25°C", ...}
```

### Example 2: 错误处理
```python
result = await handler.execute(city="未知城市")
# 返回: {"success": False, "error": "未找到城市 '未知城市' 的天气信息", ...}
```

## API Response Format

成功响应:
```json
{
  "success": true,
  "result": "北京今天的天气是晴朗，温度25°C",
  "data": {
    "city": "北京",
    "temperature": "25°C",
    "condition": "晴朗",
    "humidity": "45%",
    "wind": "北风 3级"
  }
}
```

失败响应:
```json
{
  "success": false,
  "error": "未找到城市 'XXX' 的天气信息",
  "suggestion": "支持的城市: 北京、上海、广州"
}
```

## Changelog

### 1.0.0
- Initial release
- 支持北京、上海、广州三个城市的天气查询
- 提供详细的天气信息（温度、湿度、风向）

## Future Plans
- 集成真实天气API（如和风天气、OpenWeatherMap）
- 支持更多城市
- 添加未来7天天气预报
- 支持恶劣天气预警

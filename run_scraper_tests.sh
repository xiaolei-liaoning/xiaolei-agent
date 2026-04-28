#!/bin/bash

# 运行爬虫功能测试

echo "开始测试爬虫功能..."
echo "="
echo ""

# 确保虚拟环境已激活
if [ -d "venv" ]; then
    echo "激活虚拟环境..."
    source venv/bin/activate
fi

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

# 运行pytest测试
echo "运行爬虫功能测试..."
pytest tests/test_web_scraper.py -v

# 检查测试结果
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 所有爬虫功能测试通过！"
else
    echo ""
    echo "❌ 部分测试失败，请检查错误信息。"
fi

echo ""
echo "="
echo "测试完成。"
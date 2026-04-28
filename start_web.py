#!/usr/bin/env python
"""启动FastAPI Web服务器

运行AI任务分解系统的Web界面
"""

import os
import sys
import subprocess
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


def check_dependencies():
    """检查必要的依赖"""
    required_packages = [
        'fastapi',
        'uvicorn',
        'jinja2',
        'pydantic'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ 缺少必要的依赖包: {', '.join(missing_packages)}")
        print("请运行以下命令安装依赖:")
        print("pip install -r requirements.txt")
        return False
    
    return True


def main():
    """主函数"""
    print("="*60)
    print("🚀 启动AI任务分解系统Web服务器")
    print("="*60)
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 检查必要文件
    web_server = Path(__file__).parent / "web_server.py"
    if not web_server.exists():
        print(f"❌ 找不到web_server.py文件: {web_server}")
        sys.exit(1)
    
    templates_dir = Path(__file__).parent / "templates"
    if not templates_dir.exists():
        print(f"❌ 找不到templates目录: {templates_dir}")
        sys.exit(1)
    
    index_html = templates_dir / "index.html"
    if not index_html.exists():
        print(f"❌ 找不到index.html文件: {index_html}")
        sys.exit(1)
    
    print("✅ 所有依赖检查通过")
    print(f"📁 工作目录: {Path(__file__).parent}")
    print(f"🌐 服务器地址: http://localhost:8000")
    print(f"📖 API文档: http://localhost:8000/docs")
    print("="*60)
    print()
    
    # 启动服务器
    try:
        import uvicorn
        from web_server import app
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            reload=False  # 生产环境建议关闭热重载
        )
    except KeyboardInterrupt:
        print("\n\n👋 服务器已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
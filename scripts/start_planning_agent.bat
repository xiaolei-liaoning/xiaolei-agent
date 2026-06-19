@echo off
chcp 65001 >nul
REM Planning Agent 快速启动脚本 (Windows)

echo ==========================================
echo 🚀 Planning Agent 快速启动
echo ==========================================
echo.

REM 检查 Python 版本
echo 1️⃣  检查 Python 版本...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('python --version') do echo    ✅ %%i
) else (
    echo    ❌ Python 未安装
    pause
    exit /b 1
)
echo.

REM 检查依赖
echo 2️⃣  检查依赖...
if exist requirements.txt (
    echo    📦 安装依赖（这可能需要几分钟）...
    pip install -r requirements.txt -q
    if %errorlevel% equ 0 (
        echo    ✅ 依赖安装完成
    ) else (
        echo    ⚠️  依赖安装可能有问题，请检查错误信息
    )
) else (
    echo    ⚠️  未找到 requirements.txt
)
echo.

REM 选择启动模式
echo 3️⃣  选择启动模式:
echo    [1] 启动主服务（包含 API 接口）- 推荐
echo    [2] 运行测试套件
echo    [3] 运行演示脚本
echo    [4] 命令行交互模式
echo.
set /p choice="请选择 (1-4): "

if "%choice%"=="1" (
    echo.
    echo ==========================================
    echo 🌐 启动主服务...
    echo ==========================================
    echo.
    echo 💡 提示:
    echo    - API 地址: http://localhost:8001
    echo    - 监控界面: http://localhost:8001/monitor
    echo    - 按 Ctrl+C 停止服务
    echo.
    python main.py
) else if "%choice%"=="2" (
    echo.
    echo ==========================================
    echo 🧪 运行测试套件...
    echo ==========================================
    echo.
    python test_planning_agent.py
) else if "%choice%"=="3" (
    echo.
    echo ==========================================
    echo 🎬 运行演示脚本...
    echo ==========================================
    echo.
    python demo_planning_agent.py
) else if "%choice%"=="4" (
    echo.
    echo ==========================================
    echo 💻 命令行交互模式
    echo ==========================================
    echo.
    echo 输入任务描述（输入 'quit' 退出）:
    echo.
    :loop
    set /p task="^> "
    if "%task%"=="quit" goto end
    if "%task%"=="exit" goto end
    if not "%task%"=="" (
        python -m planning_agent %task%
        echo.
    )
    goto loop
    :end
    echo 再见！👋
) else (
    echo ❌ 无效选择
    pause
    exit /b 1
)

echo.
echo ==========================================
echo ✨ 完成！
echo ==========================================
pause

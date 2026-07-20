@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   桌面文件整理器
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10 或更高版本
    echo 下载: https://www.python.org/downloads/
    echo 安装时勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

python -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装 PyQt6 ...
    python -m pip install PyQt6
    if errorlevel 1 (
        echo [错误] PyQt6 安装失败
        pause
        exit /b 1
    )
)

echo 正在启动...
python desktop_organizer_v51.py
set EXITCODE=%errorlevel%
if %EXITCODE% neq 0 (
    echo.
    echo [错误] 程序异常退出，退出码: %EXITCODE%
    if exist "启动错误.log" (
        echo.
        echo ===== 启动错误.log =====
        type "启动错误.log"
    ) else (
        echo 未找到 启动错误.log，请先运行 诊断环境.bat
    )
    echo.
    pause
) else (
    echo 程序已正常关闭。
)

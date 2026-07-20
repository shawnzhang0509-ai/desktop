@echo off
chcp 65001 >nul
cd /d "%~dp0"

set LOG=%~dp0诊断结果.txt
echo ======================================== > "%LOG%"
echo 桌面整理器 - 环境诊断 >> "%LOG%"
echo 时间: %date% %time% >> "%LOG%"
echo 目录: %CD% >> "%LOG%"
echo ======================================== >> "%LOG%"
echo. >> "%LOG%"

echo [1] 检查 Python... >> "%LOG%"
where python >> "%LOG%" 2>&1
if errorlevel 1 (
    echo 结果: 未找到 python 命令 >> "%LOG%"
    echo. >> "%LOG%"
    echo 解决办法: 安装 Python 并勾选 Add to PATH >> "%LOG%"
    goto SHOW
)

echo [2] Python 版本... >> "%LOG%"
python --version >> "%LOG%" 2>&1
python -c "import sys; print('路径:', sys.executable)" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo [3] 检查 PyQt6... >> "%LOG%"
python -c "import PyQt6; from PyQt6.QtWidgets import QApplication; print('PyQt6 正常')" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo 结果: PyQt6 未安装，正在安装... >> "%LOG%"
    python -m pip install PyQt6 >> "%LOG%" 2>&1
)
echo. >> "%LOG%"

echo [4] 检查 dist 目录 exe... >> "%LOG%"
if exist "dist\desktop_organizer_v51\desktop_organizer_v51.exe" (
    if exist "dist\desktop_organizer_v51\_internal" (
        echo dist exe 完整（含 _internal） >> "%LOG%"
    ) else (
        echo 警告: dist 里 exe 缺少 _internal 文件夹 >> "%LOG%"
    )
) else (
    echo 未找到 dist\desktop_organizer_v51\desktop_organizer_v51.exe >> "%LOG%"
)
echo. >> "%LOG%"

echo [5] 尝试运行 desktop_organizer_v51.py ... >> "%LOG%"
python desktop_organizer_v51.py >> "%LOG%" 2>&1
echo 退出码: %errorlevel% >> "%LOG%"
echo. >> "%LOG%"

if exist "启动错误.log" (
    echo [6] 启动错误.log 内容: >> "%LOG%"
    type "启动错误.log" >> "%LOG%"
) else (
    echo [6] 未生成 启动错误.log（可能 Python 根本没运行起来） >> "%LOG%"
)

:SHOW
echo.
type "%LOG%"
echo.
echo 诊断结果已保存到: %LOG%
echo.
pause

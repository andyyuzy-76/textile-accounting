@echo off
chcp 65001 >nul
echo ========================================
echo 家纺记账系统 Flet 版打包工具
echo ========================================
echo.

echo [1/3] 检查依赖...
python -c "import flet" 2>nul
if errorlevel 1 (
    echo 错误: 未安装 Flet
    echo 请运行: pip install flet
    pause
    exit /b 1
)

echo [2/3] 使用 Flet 打包...
flet pack accounting_flet.py --name "家纺记账系统-苹果风格" --add-data "receipt_printer.py;."

if errorlevel 1 (
    echo.
    echo 打包失败！
    pause
    exit /b 1
)

echo.
echo [3/3] 打包完成！
echo 可执行文件位置: dist\家纺记账系统-苹果风格.exe
echo.
pause

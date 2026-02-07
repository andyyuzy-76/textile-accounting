@echo off
chcp 65001 >nul
echo ===========================================
echo   家纺记账系统 - 打包工具
echo ===========================================
echo.
echo 正在安装 PyInstaller...
echo.
pip install pyinstaller -q
echo.
echo ===========================================
echo   开始打包...
echo ===========================================
echo.
cd /d %~dp0

echo 正在清理旧文件...
if exist "dist" rmdir /s /q dist 2>nul
if exist "build" rmdir /s /q build 2>nul
del /q *.spec 2>nul

echo.
echo 正在打包，请稍候...
echo.

pyinstaller --onefile ^
    --name "家纺记账系统" ^
    --icon "icon.ico" ^
    --add-data "使用说明-GUI.md;." ^
    --windowed ^
    --clean ^
    accounting_gui.py

echo.
if exist "dist\家纺记账系统.exe" (
    echo ===========================================
    echo   ✅ 打包成功！
    echo ===========================================
    echo.
    echo 可执行文件位置:
    echo   %~dp0dist\家纺记账系统.exe
    echo.
    echo 可以将整个 dist 文件夹拷贝到其他电脑运行！
    echo.
) else (
    echo ===========================================
    echo   ❌ 打包失败
    echo ===========================================
    echo.
    echo 请检查错误信息，或手动运行:
    echo   pyinstaller --onefile --name "家纺记账系统" --windowed accounting_gui.py
    echo.
)

pause

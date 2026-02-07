@echo off
chcp 65001 >nul
echo 启动家纺记账系统（图形界面版）...
cd /d %USERPROFILE%\.accounting-tool
pythonw accounting_gui.py
if errorlevel 1 (
    echo 启动失败，尝试使用 python 命令...
    python accounting_gui.py
)

@echo off
chcp 65001 >nul
echo 启动家纺记账系统（Flet 主线版）...
cd /d %USERPROFILE%\.accounting-tool
pythonw accounting_flet.py
if errorlevel 1 (
    echo 启动失败，尝试使用 python 命令...
    python accounting_flet.py
)

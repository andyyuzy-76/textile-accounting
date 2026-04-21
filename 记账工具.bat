@echo off
chcp 65001 >nul
echo 启动家纺记账工具（Flet 主线版）...
cd /d %USERPROFILE%\.accounting-tool
python accounting_flet.py
pause

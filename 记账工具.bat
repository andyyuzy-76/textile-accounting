@echo off
chcp 65001 >nul
echo 启动家纺记账工具...
cd /d %USERPROFILE%\.accounting-tool
python accounting.py
pause

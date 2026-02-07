@echo off
chcp 936 >nul
echo ===========================================
echo   An Zhuang Excel Dao Ru Yi Lai
echo ===========================================
echo.
echo Zheng Zai An Zhuang openpyxl...
echo.
python -m pip install openpyxl
echo.
if %errorlevel% == 0 (
    echo [OK] An Zhuang Cheng Gong!
    echo.
    echo Xian Zai Ke Yi Dao Ru Excel Wen Jian Le
    echo Shi Yong Fang Fa: Dian Ji "Dao Ru Excel" An Niu
) else (
    echo [FAIL] An Zhuang Shi Bai
    echo.
    echo Qing Shou Dong Yun Xing Yi Xia Ming Ling:
    echo pip install openpyxl
)
echo.
pause

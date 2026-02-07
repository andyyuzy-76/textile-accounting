#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安装Excel支持
"""

import subprocess
import sys

print("=" * 50)
print("  安装 Excel 导入依赖")
print("=" * 50)
print()
print("正在安装 openpyxl...")
print()

try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "openpyxl"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    if result.returncode == 0:
        print()
        print("✅ 安装成功！")
        print()
        print("现在可以导入 Excel 文件了")
        print('使用方法：点击"📥 导入Excel"按钮')
    else:
        print()
        print("❌ 安装失败")
        print()
        print("请手动运行以下命令：")
        print("pip install openpyxl")
        
except Exception as e:
    print(f"错误: {e}")
    print()
    print("请手动运行以下命令：")
    print("pip install openpyxl")

print()
input("按回车键继续...")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：将旧的 accounting.py 调用转发到 Flet 主线。"""

from accounting_flet import main
import flet as ft


if __name__ == "__main__":
    ft.run(main)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
家纺四件套记账系统 - Flet 苹果风格版本
功能：图形化界面实时记账
作者：AI Assistant
日期：2026-02-21
"""

import flet as ft
import json
import os
import csv
import threading
import time
import ctypes
from datetime import datetime
from typing import List, Dict, Optional

# 导入打印模块
try:
    from receipt_printer import ReceiptPrinter

    PRINT_AVAILABLE = True
except ImportError:
    ReceiptPrinter = None  # type: ignore
    PRINT_AVAILABLE = False
class AppleColors:
    TEXT_PRIMARY = "#0f172a"
    TEXT_SECONDARY = "#6b7280"
    TEXT_TERTIARY = "#9ca3af"
    BG_SECONDARY = "#f8fafc"
    BG_TERTIARY = "#ffffff"
    BORDER = "#e6eef8"
    PRIMARY = "#0b84ff"
    SUCCESS = "#16a34a"
    DANGER = "#dc2626"
    INFO = "#0ea5e9"
    WARNING = "#f59e0b"
    DIVIDER = "#e6eef8"
    SHADOW = "#00000022"
    HOVER_BG = "#f1f5f9"


VERSION = "1.14.0"


class AccountingApp:
    def __init__(self, page: ft.Page):
        self.page = page
        home_dir = os.path.expanduser("~")
        self.data_dir = os.path.join(home_dir, ".accounting-tool")
        self.data_file = os.path.join(self.data_dir, "records.json")
        os.makedirs(self.data_dir, exist_ok=True)
        self.records = self.load_records()
        self.item_rows = []
        self.receipt_printer = ReceiptPrinter() if PRINT_AVAILABLE and ReceiptPrinter else None
        
        # 设置全局键盘事件：Ctrl+Enter 提交记录
        def on_keyboard(e):
            if e.key == "Enter" and e.ctrl:
                self.add_record()
        
        page.on_keyboard_event = on_keyboard
        
        try:
            self.build_ui()
        except Exception as e:
            print(f"[ERROR] build_ui failed: {e}")
            import traceback
            traceback.print_exc()

    def load_records(self) -> List[Dict]:
        """加载历史记录"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_records(self):
        """保存记录"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    def load_printer_settings(self):
        """加载打印机设置"""
        if not PRINT_AVAILABLE or not self.receipt_printer:
            return

        settings_file = os.path.join(self.data_dir, "printer_settings.json")
        default_settings = {
            "shop_name": "家纺四件套",
            "shop_address": "",
            "shop_phone": "",
            "footer_text": "谢谢惠顾，欢迎下次光临！",
            "printer_name": "",
            "auto_print": False,
            "paper_width": 58,
            "compact_mode": True,
        }

        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    loaded_settings = json.load(f)
                    default_settings.update(loaded_settings)
            except:
                pass

        # 应用到打印机
        self.receipt_printer.set_shop_info(
            name=default_settings["shop_name"],
            address=default_settings["shop_address"],
            phone=default_settings["shop_phone"],
        )
        self.receipt_printer.footer_text = default_settings["footer_text"]
        self.receipt_printer.receipt_width = (
            32 if default_settings["paper_width"] == 58 else 48
        )

    def print_receipt(self, record):
        """打印小票"""
        if not PRINT_AVAILABLE or not self.receipt_printer:
            self.show_error("打印模块未安装")
            return

        try:
            import tempfile
            import subprocess

            # 生成小票内容
            receipt_text = self.receipt_printer.format_receipt(record, compact=True)

            # 保存到临时文件
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", delete=False
            ) as f:
                f.write(receipt_text)
                temp_file = f.name

            # 使用记事本打印
            subprocess.Popen(["notepad", "/p", temp_file])

            self.show_success("小票已发送到打印机")
        except Exception as e:
            self.show_error(f"打印失败: {str(e)}")

    def export_csv(self):
        """导出CSV"""
        try:
            from datetime import datetime

            # 生成文件名
            filename = f"records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join(os.path.expanduser("~"), "Desktop", filename)

            # 写入CSV
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "日期", "类型", "数量", "总金额", "备注"])

                for record in self.records:
                    record_type = "退货" if record.get("type") == "return" else "销售"
                    writer.writerow(
                        [
                            record["id"],
                            record["date"],
                            record_type,
                            record["quantity"],
                            record["total_amount"],
                            record.get("note", ""),
                        ]
                    )

            self.show_success(f"导出成功！\n文件保存在桌面：\n{filename}")
        except Exception as e:
            self.show_error(f"导出失败: {str(e)}")

    def import_csv(self):
        """导入CSV"""

        def on_file_result(e: ft.FilePickerResultEvent):
            if not e.files:
                return

            try:
                filepath = e.files[0].path
                imported_count = 0

                with open(filepath, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)

                    # 获取当前最大ID
                    max_id = max([r["id"] for r in self.records], default=0)

                    for row in reader:
                        # 跳过表头或空行
                        if not row.get("日期"):
                            continue

                        # 解析数据
                        record_type = "return" if row.get("类型") == "退货" else "sale"
                        quantity = int(row.get("数量", 0))
                        total_amount = float(row.get("总金额", 0))

                        # 计算平均单价
                        avg_price = (
                            abs(total_amount) / abs(quantity) if quantity != 0 else 0
                        )

                        # 创建记录
                        max_id += 1
                        record = {
                            "id": max_id,
                            "date": row.get("日期", ""),
                            "quantity": quantity,
                            "unit_price": avg_price,
                            "total_amount": total_amount,
                            "note": row.get("备注", ""),
                            "type": record_type,
                            "items": [
                                {"quantity": abs(quantity), "unit_price": avg_price}
                            ],
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }

                        self.records.append(record)
                        imported_count += 1

                if imported_count > 0:
                    self.save_records()
                    self.refresh_display()
                    self.show_success(f"成功导入 {imported_count} 条记录")
                else:
                    self.show_error("未找到有效记录")

            except Exception as ex:
                self.show_error(f"导入失败: {str(ex)}")

        # 创建文件选择器
        file_picker = ft.FilePicker(on_result=on_file_result)
        self.page.overlay.append(file_picker)
        self.page.update()

        # 打开文件选择对话框
        file_picker.pick_files(
            allowed_extensions=["csv"],
            dialog_title="选择CSV文件",
        )

    def build_ui(self):
        """构建主界面"""
        # 顶部标题栏
        header = self.create_header()

        # 主内容区（卡片式布局）
        content = self.create_content()

        # 添加到页面
        self.page.add(
            ft.Column(
                controls=[header, content],
                spacing=0,
                expand=True,
            )
        )

    def create_header(self):
        """创建顶部标题栏"""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        "🏠 家纺记账",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=AppleColors.TEXT_PRIMARY,
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.UPLOAD_FILE,
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="导入CSV",
                        on_click=lambda _: self.import_csv(),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD,
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="导出CSV",
                        on_click=lambda _: self.export_csv(),
                    ),
                    ft.Text(
                        f"v{VERSION}",
                        size=14,
                        color=AppleColors.TEXT_TERTIARY,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding(left=30, right=30, top=20, bottom=20),
            bgcolor=AppleColors.BG_SECONDARY,
            border=ft.Border(bottom=ft.BorderSide(1, AppleColors.DIVIDER)),
        )

    def create_content(self):
        """创建主内容区"""
        # 左侧：录入区 + 统计卡片
        left_panel = self.create_input_panel()

        # 右侧：记录列表
        right_panel = self.create_records_panel()

        return ft.Container(
            content=ft.Row(
                controls=[left_panel, right_panel],
                spacing=20,
                expand=True,
            ),
            padding=20,
            expand=True,
        )

    def create_input_panel(self):
        """创建录入面板"""
        # 日期选择
        self.date_field = ft.TextField(
            label="日期",
            value=datetime.now().strftime("%Y-%m-%d"),
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
            border_color=AppleColors.BORDER,
            focused_border_color=AppleColors.PRIMARY,
            text_size=15,
            height=50,
        )

        today_btn = ft.TextButton(
            "今天",
            on_click=lambda _: self.set_today(),
            style=ft.ButtonStyle(
                color=AppleColors.PRIMARY,
            ),
        )

        date_row = ft.Row(
            controls=[
                ft.Container(self.date_field, expand=True),
                today_btn,
            ],
            spacing=10,
        )

        # 类型选择
        self.record_type = ft.RadioGroup(
            content=ft.Row(
                controls=[
                    ft.Radio(
                        value="sale", label="销售", fill_color=AppleColors.SUCCESS
                    ),
                    ft.Radio(
                        value="return", label="退货", fill_color=AppleColors.DANGER
                    ),
                ],
                spacing=30,
            ),
            value="sale",
        )

        type_section = ft.Column(
            controls=[
                ft.Text(
                    "类型",
                    size=15,
                    weight=ft.FontWeight.W_500,
                    color=AppleColors.TEXT_PRIMARY,
                ),
                self.record_type,
            ],
            spacing=8,
        )

        # 商品明细区域
        self.items_container = ft.Column(spacing=10)
        self.add_item_row()  # 添加第一行

        add_item_btn = ft.TextButton(
            "+ 添加商品",
            on_click=lambda _: self.add_item_row(),
            style=ft.ButtonStyle(color=AppleColors.PRIMARY),
        )

        items_section = ft.Column(
            controls=[
                ft.Text(
                    "商品明细",
                    size=15,
                    weight=ft.FontWeight.W_500,
                    color=AppleColors.TEXT_PRIMARY,
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            # 表头
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        "数量",
                                        size=13,
                                        color=AppleColors.TEXT_SECONDARY,
                                        width=80,
                                    ),
                                    ft.Text(
                                        "单价",
                                        size=13,
                                        color=AppleColors.TEXT_SECONDARY,
                                        width=80,
                                    ),
                                    ft.Text(
                                        "小计",
                                        size=13,
                                        color=AppleColors.TEXT_SECONDARY,
                                        width=100,
                                    ),
                                ],
                                spacing=10,
                            ),
                            self.items_container,
                            add_item_btn,
                        ],
                        spacing=10,
                    ),
                    padding=15,
                    bgcolor=AppleColors.BG_SECONDARY,
                    border_radius=10,
                    border=ft.Border.all(1, AppleColors.BORDER),
                ),
            ],
            spacing=8,
        )

        # 汇总信息
        self.summary_qty = ft.Text("0套", size=16, weight=ft.FontWeight.W_500)
        self.summary_total = ft.Text(
            "¥0.00", size=20, weight=ft.FontWeight.BOLD, color=AppleColors.PRIMARY
        )

        summary_section = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text("汇总", size=15, color=AppleColors.TEXT_SECONDARY),
                    self.summary_qty,
                    ft.Container(expand=True),
                    self.summary_total,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=15,
            bgcolor=AppleColors.BG_TERTIARY,
            border_radius=10,
        )

        # 备注
        self.note_field = ft.TextField(
            label="备注",
            multiline=True,
            min_lines=2,
            max_lines=3,
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
            border_color=AppleColors.BORDER,
            focused_border_color=AppleColors.PRIMARY,
            text_size=15,
        )

        # 操作按钮
        add_btn = ft.FilledButton(
            "✅ 添加记录",
            on_click=lambda _: self.add_record(),
            style=ft.ButtonStyle(
                bgcolor=AppleColors.PRIMARY,
                color=AppleColors.BG_SECONDARY,
                padding=ft.Padding(left=30, right=30, top=15, bottom=15),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            height=50,
        )

        clear_btn = ft.TextButton(
            "清空表单",
            on_click=lambda _: self.clear_form(),
            style=ft.ButtonStyle(color=AppleColors.TEXT_SECONDARY),
        )

        # 今日统计卡片
        self.stats_text = ft.Text(
            "加载中...",
            size=14,
            color=AppleColors.TEXT_PRIMARY,
        )

        stats_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        "📊 今日统计",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color=AppleColors.TEXT_PRIMARY,
                    ),
                    ft.Divider(height=1, color=AppleColors.DIVIDER),
                    self.stats_text,
                ],
                spacing=10,
            ),
            padding=15,
            bgcolor=AppleColors.BG_SECONDARY,
            border_radius=15,
            border=ft.border.all(1, AppleColors.BORDER),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color=AppleColors.SHADOW,
                offset=ft.Offset(0, 2),
            ),
        )

        # 组装左侧面板
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text(
                                    "📝 新记录",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=AppleColors.TEXT_PRIMARY,
                                ),
                                ft.Divider(height=1, color=AppleColors.DIVIDER),
                                date_row,
                                type_section,
                                items_section,
                                summary_section,
                                self.note_field,
                                add_btn,
                                clear_btn,
                            ],
                            spacing=15,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        padding=20,
                        bgcolor=AppleColors.BG_SECONDARY,
                        border_radius=15,
                        border=ft.Border.all(1, AppleColors.BORDER),
                        shadow=ft.BoxShadow(
                            spread_radius=0,
                            blur_radius=10,
                            color=AppleColors.SHADOW,
                            offset=ft.Offset(0, 2),
                        ),
                        expand=True,
                    ),
                    stats_card,
                ],
                spacing=15,
                expand=True,
            ),
            width=450,
            expand=True,
        )

    def create_records_panel(self):
        """创建记录列表面板"""
        # 筛选按钮
        filter_buttons = ft.Row(
            controls=[
                ft.Text(
                    "📋 记录列表",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=AppleColors.TEXT_PRIMARY,
                ),
                ft.Container(expand=True),
                ft.TextButton(
                    "今天",
                    on_click=lambda _: self.show_today_records(),
                    style=ft.ButtonStyle(color=AppleColors.PRIMARY),
                ),
                ft.TextButton(
                    "本月",
                    on_click=lambda _: self.show_month_records(),
                    style=ft.ButtonStyle(color=AppleColors.TEXT_SECONDARY),
                ),
                ft.TextButton(
                    "本年",
                    on_click=lambda _: self.show_year_records(),
                    style=ft.ButtonStyle(color=AppleColors.TEXT_SECONDARY),
                ),
                ft.TextButton(
                    "全部",
                    on_click=lambda _: self.show_all_records(),
                    style=ft.ButtonStyle(color=AppleColors.TEXT_SECONDARY),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        
        # 记录列表
        self.records_list = ft.Column(
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

        # 合计显示
        self.total_label = ft.Text(
            "¥0.00",
            size=24,
            weight=ft.FontWeight.BOLD,
            color=AppleColors.PRIMARY,
        )

        total_row = ft.Row(
            controls=[
                ft.Text(
                    "💰 合计:",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=AppleColors.TEXT_PRIMARY,
                ),
                ft.Container(expand=True),
                self.total_label,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # 组装右侧面板
        return ft.Container(
            content=ft.Column(
                controls=[
                    filter_buttons,
                    ft.Divider(height=1, color=AppleColors.DIVIDER),
                    ft.Container(
                        content=self.records_list,
                        expand=True,
                    ),
                    ft.Divider(height=1, color=AppleColors.DIVIDER),
                    total_row,
                ],
                spacing=15,
            ),
            padding=20,
            bgcolor=AppleColors.BG_SECONDARY,
            border_radius=15,
            border=ft.border.all(1, AppleColors.BORDER),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color=AppleColors.SHADOW,
                offset=ft.Offset(0, 2),
            ),
            expand=True,
        )

    def add_item_row(self):
        """添加商品行"""
        qty_field = ft.TextField(
            hint_text="数量",
            width=80,
            height=40,
            border_radius=8,
            text_size=14,
            bgcolor=AppleColors.BG_TERTIARY,
            border_color=AppleColors.BORDER,
            focused_border_color=AppleColors.PRIMARY,
            on_change=lambda _: self.update_summary(),
        )

        price_field = ft.TextField(
            hint_text="单价",
            width=80,
            height=40,
            border_radius=8,
            text_size=14,
            bgcolor=AppleColors.BG_TERTIARY,
            border_color=AppleColors.BORDER,
            focused_border_color=AppleColors.PRIMARY,
            on_change=lambda _: self.update_summary(),
        )

        subtotal_text = ft.Text(
            "¥0.00", size=14, color=AppleColors.TEXT_SECONDARY, width=100
        )

        def delete_row():
            if len(self.item_rows) > 1:
                self.items_container.controls.remove(row_container)
                self.item_rows.remove(row_data)
                self.update_summary()
                self.page.update()

        delete_btn = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=16,
            icon_color=AppleColors.TEXT_TERTIARY,
            on_click=lambda _: delete_row(),
        )

        # 当在数量输入框按回车时，移动焦点到本行的单价输入框
        async def _qty_on_submit(e, pf=price_field):
            try:
                await pf.focus()
            except Exception as ex:
                print(f"[warn] qty on_submit focus failed: {ex}")

        qty_field.on_submit = _qty_on_submit

        # 在单价输入框按回车时，添加新的一行
        async def _price_on_submit(e):
            try:
                # 添加新行
                self.add_item_row()
                # 焦点移动到新行的数量输入框
                if self.item_rows:
                    new_qty_field = self.item_rows[-1]['qty_field']
                    await new_qty_field.focus()
            except Exception as ex:
                print(f"[warn] price on_submit failed: {ex}")

        price_field.on_submit = _price_on_submit

        row_container = ft.Row(
            controls=[qty_field, price_field, subtotal_text, delete_btn],
            spacing=10,
        )

        row_data = {
            "qty_field": qty_field,
            "price_field": price_field,
            "subtotal_text": subtotal_text,
            "container": row_container,
        }

        self.item_rows.append(row_data)
        self.items_container.controls.append(row_container)
        self.page.update()

    def update_summary(self):
        """更新汇总信息"""
        total_qty = 0
        total_amount = 0.0

        for row in self.item_rows:
            try:
                qty = int(row["qty_field"].value or 0)
                price = float(row["price_field"].value or 0)
                subtotal = qty * price
                row["subtotal_text"].value = f"¥{subtotal:.2f}"
                total_qty += qty
                total_amount += subtotal
            except:
                row["subtotal_text"].value = "¥0.00"

        self.summary_qty.value = f"{total_qty}套"
        self.summary_total.value = f"¥{total_amount:.2f}"
        self.page.update()


    def set_today(self):
        """设置日期为今天"""
        self.date_field.value = datetime.now().strftime("%Y-%m-%d")
        self.page.update()

    def clear_form(self):
        """清空表单"""
        # 清空所有商品行（保留第一行）
        while len(self.item_rows) > 1:
            row = self.item_rows.pop()
            self.items_container.controls.remove(row["container"])

        # 清空第一行数据
        if self.item_rows:
            self.item_rows[0]["qty_field"].value = ""
            self.item_rows[0]["price_field"].value = ""
            self.item_rows[0]["subtotal_text"].value = "¥0.00"

        # 清空备注
        self.note_field.value = ""

        # 更新汇总
        self.update_summary()
        self.page.update()

    def add_record(self):
        """添加记录"""
        try:
            date = self.date_field.value.strip()
            note = self.note_field.value.strip() if self.note_field.value else ""
            record_type = self.record_type.value

            if not date:
                self.show_error("请输入日期！")
                return

            # 收集商品数据
            items = []
            total_quantity = 0
            total_amount = 0.0

            for row in self.item_rows:
                qty_str = row["qty_field"].value
                price_str = row["price_field"].value

                if qty_str and price_str:
                    try:
                        qty = int(qty_str)
                        price = float(price_str)
                        if qty > 0 and price > 0:
                            items.append({"quantity": qty, "unit_price": price})
                            total_quantity += qty
                            total_amount += qty * price
                    except ValueError:
                        pass

            if not items:
                self.show_error("请至少添加一个有效的商品行！")
                return

            # 处理退货
            if record_type == "return":
                total_quantity = -total_quantity
                total_amount = -total_amount
                if note:
                    note = f"[退货] {note}"
                else:
                    note = "[退货]"
                for item in items:
                    item["quantity"] = -item["quantity"]

            # 计算平均单价
            avg_price = (
                abs(total_amount) / abs(total_quantity) if total_quantity != 0 else 0
            )

            # 创建记录
            record = {
                "id": len(self.records) + 1,
                "date": date,
                "quantity": total_quantity,
                "unit_price": avg_price,
                "total_amount": total_amount,
                "note": note,
                "type": record_type,
                "items": items,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            self.records.append(record)
            self.save_records()

            # 刷新显示
            self.refresh_display()
            self.clear_form()

            # 显示成功提示
            type_label = "退货" if record_type == "return" else "销售"
            self.show_success(
                f"✅ {type_label}记录添加成功！\n金额: ¥{abs(total_amount):.2f}"
            )

        except Exception as e:
            self.show_error(f"添加失败: {str(e)}")

    def refresh_display(self):
        """刷新显示"""
        self.show_today_records()
        self.update_stats()

    def show_today_records(self):
        """显示今日记录"""
        today = datetime.now().strftime("%Y-%m-%d")
        filtered = [r for r in self.records if r["date"] == today]
        self.display_records(filtered)

    def show_month_records(self):
        """显示本月记录"""
        this_month = datetime.now().strftime("%Y-%m")
        filtered = [r for r in self.records if r["date"].startswith(this_month)]
        self.display_records(filtered)

    def show_year_records(self):
        """显示本年记录"""
        this_year = datetime.now().strftime("%Y")
        filtered = [r for r in self.records if r["date"].startswith(this_year)]
        self.display_records(filtered)

    def show_all_records(self):
        """显示所有记录"""
        self.display_records(self.records)

    def display_records(self, records):
        """显示记录列表"""
        print(f"[DEBUG] display_records called with {len(records)} records")
        self.records_list.controls.clear()

        # 按日期排序（降序）
        sorted_records = sorted(records, key=lambda x: x["date"], reverse=True)

        total = 0.0
        for record in sorted_records:
            is_return = record.get("type") == "return" or record["quantity"] < 0

            # 创建记录卡片
            card = self.create_record_card(record, is_return)
            self.records_list.controls.append(card)

            total += record["total_amount"]

        # 更新合计
        if abs(total) < 0.01:
            self.total_label.value = "¥0.00"
            self.total_label.color = AppleColors.TEXT_PRIMARY
        elif total < 0:
            self.total_label.value = f"-¥{abs(total):.2f}"
            self.total_label.color = AppleColors.DANGER
        else:
            self.total_label.value = f"¥{total:.2f}"
            self.total_label.color = AppleColors.SUCCESS

        self.page.update()

    def create_record_card(self, record, is_return):
        """创建记录卡片"""
        print(f"[DEBUG] create_record_card for record {record.get('id')}")
        # 格式化明细 - 每个明细单独显示，退货用红色
        items = record.get("items", [])
        detail_controls = []
        if items:
            for item in items:
                qty = item.get("quantity", 0)
                price = item.get("unit_price", 0)
                is_item_return = qty < 0
                text = f"{abs(qty)}套@¥{price:.0f}"
                detail_controls.append(
                    ft.Text(
                        text,
                        size=13,
                        color=AppleColors.DANGER if is_item_return else AppleColors.TEXT_PRIMARY,
                    )
                )
        else:
            qty = record["quantity"]
            price = record.get("unit_price", 0)
            is_item_return = qty < 0
            detail_controls.append(
                ft.Text(
                    f"{abs(qty)}套@¥{price:.0f}",
                    size=13,
                    color=AppleColors.DANGER if is_item_return else AppleColors.TEXT_PRIMARY,
                )
            )

        # 颜色
        type_color = AppleColors.DANGER if is_return else AppleColors.SUCCESS
        type_text = "退货" if is_return else "销售"

        amount_text = (
            f"-¥{abs(record['total_amount']):.2f}"
            if is_return
            else f"¥{record['total_amount']:.2f}"
        )

        # 操作按钮
        def on_print_click(e):
            print(f"[DEBUG] print clicked for record {record.get('id')}")
            self.print_receipt(record)
        
        print_btn = ft.IconButton(
            icon=ft.Icons.PRINT,
            icon_size=18,
            icon_color=AppleColors.INFO,
            tooltip="打印小票",
            on_click=on_print_click,
        )

        def on_menu_click(e):
            try:
                print(f"[DEBUG] menu button clicked for record {record.get('id')}")
                self.show_record_menu(record)
            except Exception as ex:
                print(f"[ERROR] on_menu_click: {ex}")
        
        menu_btn = ft.IconButton(
            icon=ft.Icons.MORE_HORIZ,
            icon_size=18,
            icon_color=AppleColors.TEXT_SECONDARY,
            tooltip="更多操作",
            on_click=on_menu_click,
        )

        def on_edit_click(e):
            try:
                print(f"[DEBUG] edit clicked for record {record.get('id')}")
                self.edit_record(record)
            except Exception as ex:
                print(f"[ERROR] on_edit_click: {ex}")
        
        edit_btn = ft.IconButton(
            icon=ft.Icons.EDIT,
            icon_size=18,
            icon_color=AppleColors.TEXT_SECONDARY,
            tooltip="编辑",
            on_click=on_edit_click,
        )

        def on_delete_click(e):
            print(f"[DEBUG] delete clicked for record {record.get('id')}")
            self.delete_record(record)
        
        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE,
            icon_size=18,
            icon_color=AppleColors.DANGER,
            tooltip="删除",
            on_click=on_delete_click,
        )

        card_content = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Container(
                                        content=ft.Text(
                                            type_text,
                                            size=12,
                                            color=AppleColors.BG_SECONDARY,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        bgcolor=type_color,
                                        padding=ft.padding.symmetric(
                                            horizontal=8, vertical=2
                                        ),
                                        border_radius=5,
                                    ),
                                    ft.Text(
                                        record["date"],
                                        size=14,
                                        color=AppleColors.TEXT_SECONDARY,
                                    ),
                                ],
                                spacing=10,
                            ),
                            ft.Row(
                                controls=detail_controls,
                                spacing=5,
                                wrap=True,
                            ),
                            ft.Text(
                                record.get("note", ""),
                                size=12,
                                color=AppleColors.TEXT_TERTIARY,
                            )
                            if record.get("note")
                            else ft.Container(),
                        ],
                        spacing=5,
                        expand=True,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                amount_text,
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=type_color,
                            ),
                            ft.Row(
                                [menu_btn, print_btn, edit_btn, delete_btn],
                                spacing=4,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        spacing=5,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=15,
            bgcolor="#fef2f2" if is_return else AppleColors.BG_TERTIARY,
            border_radius=10,
            border=ft.border.all(1, AppleColors.DANGER if is_return else AppleColors.BORDER),
            on_hover=lambda e: self.on_card_hover(e, record),
        )
        
        return card_content

    def show_record_menu(self, record):
        """显示记录操作菜单"""
        try:
            print(f"[DEBUG] show_record_menu called for record {record.get('id')}")
            
            def on_action(e):
                action = e.control.data
                self.page.pop_dialog()
                
                if action == "detail":
                    self.show_record_detail(record)
                elif action == "edit":
                    self.edit_record(record)
                elif action == "add_sale":
                    self.quick_add_sale(record)
                elif action == "return":
                    self.quick_return(record)
                elif action == "print":
                    self.print_receipt(record)
                elif action == "delete":
                    self.delete_record(record)
            
            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"记录 #{record['id']} 操作", weight=ft.FontWeight.BOLD),
                content=ft.Column(
                    controls=[
                        ft.TextButton("📋 销售明细", data="detail", on_click=on_action,
                                      style=ft.ButtonStyle(color=AppleColors.PRIMARY)),
                        ft.Divider(),
                        ft.TextButton("编辑", data="edit", on_click=on_action,
                                      style=ft.ButtonStyle(color=AppleColors.PRIMARY)),
                        ft.TextButton("添加销售", data="add_sale", on_click=on_action,
                                      style=ft.ButtonStyle(color=AppleColors.SUCCESS)),
                        ft.TextButton("退货", data="return", on_click=on_action,
                                      style=ft.ButtonStyle(color=AppleColors.WARNING)),
                        ft.TextButton("打印小票", data="print", on_click=on_action,
                                      style=ft.ButtonStyle(color=AppleColors.INFO)),
                        ft.Divider(),
                        ft.TextButton("删除", data="delete", on_click=on_action,
                                      style=ft.ButtonStyle(color=AppleColors.DANGER)),
                    ],
                    tight=True,
                    spacing=5,
                ),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.show_dialog(dlg)
        except Exception as ex:
            print(f"[ERROR] show_record_menu: {ex}")
            import traceback
            traceback.print_exc()

    def show_record_detail(self, record):
        """显示记录销售明细"""
        try:
            items = record.get("items", [])
            is_return = record.get("type") == "return" or record.get("quantity", 0) < 0
            print(f"[DEBUG] show_record_detail: type={record.get('type')}, quantity={record.get('quantity')}, is_return={is_return}")
            
            # 表头
            header = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text("数量", size=14, weight=ft.FontWeight.BOLD, 
                                color=AppleColors.TEXT_SECONDARY, width=80),
                        ft.Text("单价", size=14, weight=ft.FontWeight.BOLD,
                                color=AppleColors.TEXT_SECONDARY, width=100),
                        ft.Text("小计", size=14, weight=ft.FontWeight.BOLD,
                                color=AppleColors.TEXT_SECONDARY, width=100),
                    ],
                ),
                bgcolor=AppleColors.BG_TERTIARY,
                padding=ft.padding.only(left=10, right=10, top=8, bottom=8),
                border_radius=5,
            )
            
            # 明细行
            detail_rows = [header]
            for item in items:
                qty = item.get("quantity", 0)
                price = item.get("unit_price", 0)
                # 根据每个商品的qty正负判断是否是退货
                item_is_return = qty < 0
                
                if item_is_return:
                    qty_display = f"-{abs(qty)}套"
                    subtotal = abs(qty) * price
                    subtotal_display = f"-¥{subtotal:.0f}"
                    row_bgcolor = "#fef2f2"  # 淡红色背景
                    text_color = AppleColors.DANGER
                else:
                    qty_display = f"{qty}套"
                    subtotal = qty * price
                    subtotal_display = f"¥{subtotal:.0f}"
                    row_bgcolor = AppleColors.BG_TERTIARY
                    text_color = AppleColors.TEXT_PRIMARY
                
                detail_rows.append(
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Text(qty_display, size=14, 
                                        color=text_color,
                                        width=80),
                                ft.Text(f"¥{price:.0f}", size=14,
                                        color=AppleColors.TEXT_PRIMARY, width=100),
                                ft.Text(subtotal_display, size=14,
                                        color=text_color, 
                                        width=100,
                                        weight=ft.FontWeight.W_500),
                            ],
                        ),
                        padding=ft.padding.only(left=10, right=10, top=6, bottom=6),
                        bgcolor=row_bgcolor,
                        border_radius=5,
                    )
                )
            
            # 汇总行
            total_qty = abs(record.get("quantity", 0))
            total_amount = abs(record.get("total_amount", 0))
            
            # 退货显示负数
            if is_return:
                qty_text = f"合计: -{total_qty}套"
                amount_text = f"-¥{total_amount:.0f}"
            else:
                qty_text = f"合计: {total_qty}套"
                amount_text = f"¥{total_amount:.0f}"
            
            summary_row = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text(qty_text, size=14, 
                                weight=ft.FontWeight.BOLD,
                                color=AppleColors.DANGER if is_return else AppleColors.TEXT_PRIMARY),
                        ft.Container(expand=True),
                        ft.Text(amount_text, size=16,
                                weight=ft.FontWeight.BOLD,
                                color=AppleColors.DANGER if is_return else AppleColors.SUCCESS),
                    ],
                ),
                bgcolor="#fef2f2" if is_return else AppleColors.BG_SECONDARY,
                padding=ft.padding.only(left=10, right=10, top=10, bottom=10),
                border_radius=5,
            )
            detail_rows.append(summary_row)
            
            # 记录信息
            record_info = ft.Column(
                controls=[
                    ft.Row([
                        ft.Text(f"📅 日期: {record.get('date', '-')}", size=13, 
                                color=AppleColors.TEXT_SECONDARY),
                        ft.Container(expand=True),
                        ft.Text(f"{'🔄 退货' if is_return else '✅ 销售'}", size=13,
                                color=AppleColors.DANGER if is_return else AppleColors.SUCCESS,
                                weight=ft.FontWeight.BOLD),
                    ]),
                    ft.Text(f"🆔 记录号: #{record.get('id', '-')}", size=12,
                            color=AppleColors.TEXT_TERTIARY),
                    ft.Text(f"⏰ 创建时间: {record.get('created_at', '-')}", size=12,
                            color=AppleColors.TEXT_TERTIARY),
                ],
                spacing=5,
            )
            
            # 备注
            note = record.get("note", "")
            if note:
                note_control = ft.Container(
                    content=ft.Column([
                        ft.Text("📝 备注:", size=12, color=AppleColors.TEXT_SECONDARY),
                        ft.Text(note, size=13, color=AppleColors.TEXT_PRIMARY),
                    ], spacing=3),
                    bgcolor=AppleColors.BG_TERTIARY,
                    padding=10,
                    border_radius=5,
                )
            else:
                note_control = ft.Container()
            
            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("📋 销售明细", weight=ft.FontWeight.BOLD),
                content=ft.Column(
                    controls=[
                        record_info,
                        ft.Divider(),
                        ft.Column(detail_rows, spacing=2),
                        ft.Divider(),
                        note_control,
                    ],
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                    width=350,
                    height=400,
                ),
                actions=[
                    ft.TextButton("关闭", on_click=lambda e: self.page.pop_dialog()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.show_dialog(dlg)
        except Exception as ex:
            print(f"[ERROR] show_record_detail: {ex}")
            import traceback
            traceback.print_exc()

    def on_card_hover(self, e, record):
        """卡片悬停效果"""
        is_return = record.get("type") == "return" or record.get("quantity", 0) < 0
        if e.data == "true":
            e.control.bgcolor = AppleColors.HOVER_BG
        else:
            # 恢复原来的背景色：退货是淡红色，销售是白色
            e.control.bgcolor = "#fef2f2" if is_return else AppleColors.BG_TERTIARY
        self.page.update()

    def update_stats(self):
        """更新今日统计"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_records = [r for r in self.records if r["date"] == today]

        sale_records = [
            r for r in today_records if r.get("type") != "return" and r["quantity"] > 0
        ]
        return_records = [
            r for r in today_records if r.get("type") == "return" or r["quantity"] < 0
        ]

        sale_qty = sum(r["quantity"] for r in sale_records)
        sale_amount = sum(r["total_amount"] for r in sale_records)

        return_qty = sum(abs(r["quantity"]) for r in return_records)
        return_amount = sum(abs(r["total_amount"]) for r in return_records)

        net_qty = sale_qty - return_qty
        net_amount = sale_amount - return_amount

        self.stats_text.value = f"""📅 {today}
━━━━━━━━━━━━━━
✅ 销售: {sale_qty}套 ¥{sale_amount:.0f}
🔄 退货: {return_qty}套 ¥{return_amount:.0f}
━━━━━━━━━━━━━━
📦 净额: {net_qty}套 ¥{net_amount:.0f}"""

        self.page.update()

    def edit_record(self, record):
        """编辑记录"""

        def save_changes(e):
            new_note = note_field.value.strip()
            record["note"] = new_note
            self.save_records()
            self.refresh_display()
            self.page.pop_dialog()
            self.show_success("记录已更新")

        note_field = ft.TextField(
            label="备注",
            value=record.get("note", ""),
            multiline=True,
            min_lines=3,
            max_lines=5,
            border_radius=10,
            bgcolor=AppleColors.BG_TERTIARY,
        )

        dlg = ft.AlertDialog(
            title=ft.Text(f"编辑记录 #{record['id']}", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            f"日期: {record['date']}",
                            size=14,
                            color=AppleColors.TEXT_SECONDARY,
                        ),
                        ft.Text(
                            f"金额: ¥{abs(record['total_amount']):.2f}",
                            size=14,
                            color=AppleColors.TEXT_SECONDARY,
                        ),
                        ft.Divider(height=10),
                        note_field,
                    ],
                    spacing=10,
                    tight=True,
                ),
                width=400,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(
                    "保存",
                    on_click=save_changes,
                    style=ft.ButtonStyle(
                        bgcolor=AppleColors.PRIMARY, color=AppleColors.BG_SECONDARY
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def delete_record(self, record):
        """删除记录"""

        def confirm_delete(e):
            self.records = [r for r in self.records if r["id"] != record["id"]]
            self.save_records()
            self.refresh_display()
            self.page.pop_dialog()
            self.show_success("记录已删除")

        dlg = ft.AlertDialog(
            title=ft.Text(
                "确认删除", color=AppleColors.DANGER, weight=ft.FontWeight.BOLD
            ),
            content=ft.Text(
                f"确定要删除这条记录吗？\n\n日期: {record['date']}\n金额: ¥{abs(record['total_amount']):.2f}",
                size=14,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(
                    "删除",
                    on_click=confirm_delete,
                    style=ft.ButtonStyle(
                        bgcolor=AppleColors.DANGER, color=AppleColors.BG_SECONDARY
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def quick_add_sale(self, record):
        """往原有记录添加商品明细 - 多行模式"""
        print(f"[DEBUG] quick_add_sale called for record {record.get('id')}")
        
        dlg_item_rows = []  # 弹窗内的商品行
        dlg_items_container = ft.Column(spacing=10)
        dlg_summary_qty = ft.Text("0套", size=14, weight=ft.FontWeight.W_500)
        dlg_summary_total = ft.Text("¥0.00", size=16, weight=ft.FontWeight.BOLD, color=AppleColors.PRIMARY)
        
        def update_dlg_summary():
            total_qty = 0
            total_amount = 0.0
            for row in dlg_item_rows:
                try:
                    qty = int(row["qty_field"].value or 0)
                    price = float(row["price_field"].value or 0)
                    subtotal = qty * price
                    row["subtotal_text"].value = f"¥{subtotal:.2f}"
                    total_qty += qty
                    total_amount += subtotal
                except:
                    row["subtotal_text"].value = "¥0.00"
            dlg_summary_qty.value = f"{total_qty}套"
            dlg_summary_total.value = f"¥{total_amount:.2f}"
            self.page.update()
        
        def add_dlg_item_row(focus_first=False):
            idx = len(dlg_item_rows)
            
            qty_field = ft.TextField(
                hint_text="数量",
                width=70,
                height=40,
                border_radius=8,
                text_size=14,
                bgcolor=AppleColors.BG_TERTIARY,
                border_color=AppleColors.BORDER,
                focused_border_color=AppleColors.PRIMARY,
            )
            
            price_field = ft.TextField(
                hint_text="单价",
                width=70,
                height=40,
                border_radius=8,
                text_size=14,
                bgcolor=AppleColors.BG_TERTIARY,
                border_color=AppleColors.BORDER,
                focused_border_color=AppleColors.PRIMARY,
            )
            
            subtotal_text = ft.Text("¥0.00", size=14, color=AppleColors.TEXT_SECONDARY, width=80)
            
            def delete_row():
                if len(dlg_item_rows) > 1:
                    dlg_items_container.controls.remove(row_container)
                    dlg_item_rows.remove(row_data)
                    update_dlg_summary()
            
            delete_btn = ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_size=16,
                icon_color=AppleColors.TEXT_TERTIARY,
                on_click=lambda _: delete_row(),
            )
            
            # 数量回车跳到单价 (async)
            async def on_qty_submit(e, pf=price_field):
                try:
                    await pf.focus()
                except Exception as ex:
                    print(f"[warn] qty focus failed: {ex}")
            qty_field.on_submit = on_qty_submit
            
            # 单价回车添加新行 (async)
            async def on_price_submit(e):
                try:
                    add_dlg_item_row(focus_first=True)
                    if dlg_item_rows:
                        await dlg_item_rows[-1]["qty_field"].focus()
                except Exception as ex:
                    print(f"[warn] price submit failed: {ex}")
            price_field.on_submit = on_price_submit
            
            # 输入变化时更新汇总
            qty_field.on_change = lambda e: update_dlg_summary()
            price_field.on_change = lambda e: update_dlg_summary()
            
            row_container = ft.Row(
                controls=[qty_field, price_field, subtotal_text, delete_btn],
                spacing=10,
            )
            
            row_data = {
                "qty_field": qty_field,
                "price_field": price_field,
                "subtotal_text": subtotal_text,
                "container": row_container,
            }
            
            dlg_item_rows.append(row_data)
            dlg_items_container.controls.append(row_container)
            self.page.update()
            
            if focus_first:
                qty_field.focus()
        
        def do_add_all(e):
            try:
                items_to_add = []
                total_qty = 0
                total_amount = 0.0
                
                for row in dlg_item_rows:
                    qty_str = row["qty_field"].value
                    price_str = row["price_field"].value
                    
                    if qty_str and price_str:
                        qty = int(qty_str)
                        price = float(price_str)
                        if qty > 0 and price > 0:
                            items_to_add.append({"quantity": qty, "unit_price": price})
                            total_qty += qty
                            total_amount += qty * price
                
                if not items_to_add:
                    self.show_error("请至少添加一个有效的商品行")
                    return
                
                self.page.pop_dialog()
                
                # 往原有记录添加商品明细
                if "items" not in record:
                    record["items"] = []
                record["items"].extend(items_to_add)
                
                # 重新计算总计
                all_total_qty = sum(item.get("quantity", 0) for item in record["items"])
                all_total_amount = sum(item.get("quantity", 0) * item.get("unit_price", 0) for item in record["items"])
                record["quantity"] = all_total_qty
                record["total_amount"] = all_total_amount
                if all_total_qty > 0:
                    record["unit_price"] = all_total_amount / all_total_qty
                
                self.save_records()
                self.refresh_display()
                self.show_success(f"已添加 {total_qty}套，共 ¥{total_amount:.2f}")
                
            except ValueError:
                self.show_error("请输入有效的数量和单价")
        
        dlg_content = ft.Column(
            controls=[
                ft.Text(f"记录 #{record['id']} - 当前: {record.get('quantity', 0)}套", 
                        size=13, color=AppleColors.TEXT_SECONDARY),
                ft.Divider(height=5),
                # 表头
                ft.Row(
                    controls=[
                        ft.Text("数量", size=12, color=AppleColors.TEXT_SECONDARY, width=70),
                        ft.Text("单价", size=12, color=AppleColors.TEXT_SECONDARY, width=70),
                        ft.Text("小计", size=12, color=AppleColors.TEXT_SECONDARY, width=80),
                    ],
                    spacing=10,
                ),
                dlg_items_container,
                ft.TextButton("+ 添加商品", on_click=lambda e: add_dlg_item_row(focus_first=True),
                             style=ft.ButtonStyle(color=AppleColors.PRIMARY)),
                ft.Divider(height=5),
                # 汇总
                ft.Row(
                    controls=[
                        ft.Text("汇总:", size=14, color=AppleColors.TEXT_SECONDARY),
                        dlg_summary_qty,
                        ft.Container(expand=True),
                        dlg_summary_total,
                    ],
                ),
            ],
            tight=True,
            spacing=8,
            width=320,
        )
        
        # 添加第一行
        add_dlg_item_row(focus_first=False)
        
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("添加商品明细", color=AppleColors.SUCCESS),
            content=dlg_content,
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("确认添加", on_click=do_add_all,
                               style=ft.ButtonStyle(bgcolor=AppleColors.SUCCESS, 
                                                    color=AppleColors.BG_SECONDARY)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        # 保存原来的键盘事件
        original_keyboard_handler = self.page.on_keyboard_event
        
        # 弹窗关闭时恢复原来的键盘事件
        def restore_keyboard():
            self.page.on_keyboard_event = original_keyboard_handler
        
        # 包装确认函数，先恢复键盘再执行
        def do_add_all_with_restore(e):
            restore_keyboard()
            do_add_all(e)
        
        # 设置弹窗专用的键盘事件
        def on_dlg_keyboard(e):
            if e.key == "Enter" and e.ctrl:
                do_add_all_with_restore(e)
        
        self.page.on_keyboard_event = on_dlg_keyboard
        
        # 更新按钮事件
        dlg.actions[0].on_click = lambda e: (restore_keyboard(), self.page.pop_dialog())
        dlg.actions[1].on_click = do_add_all_with_restore
        
        self.page.show_dialog(dlg)
        
        # 弹窗打开后聚焦到第一个输入框
        if dlg_item_rows:
            dlg_item_rows[0]["qty_field"].focus()

    def quick_return(self, record):
        """往原有记录添加退货明细 - 多行模式"""
        print(f"[DEBUG] quick_return called for record {record.get('id')}")
        
        dlg_item_rows = []  # 弹窗内的商品行
        dlg_items_container = ft.Column(spacing=10)
        dlg_summary_qty = ft.Text("0套", size=14, weight=ft.FontWeight.W_500)
        dlg_summary_total = ft.Text("-¥0.00", size=16, weight=ft.FontWeight.BOLD, color=AppleColors.DANGER)
        
        def update_dlg_summary():
            total_qty = 0
            total_amount = 0.0
            for row in dlg_item_rows:
                try:
                    qty = int(row["qty_field"].value or 0)
                    price = float(row["price_field"].value or 0)
                    subtotal = qty * price
                    row["subtotal_text"].value = f"-¥{subtotal:.2f}"
                    total_qty += qty
                    total_amount += subtotal
                except:
                    row["subtotal_text"].value = "-¥0.00"
            dlg_summary_qty.value = f"{total_qty}套"
            dlg_summary_total.value = f"-¥{total_amount:.2f}"
            self.page.update()
        
        def add_dlg_item_row(focus_first=False):
            idx = len(dlg_item_rows)
            
            qty_field = ft.TextField(
                hint_text="数量",
                width=70,
                height=40,
                border_radius=8,
                text_size=14,
                bgcolor=AppleColors.BG_TERTIARY,
                border_color=AppleColors.BORDER,
                focused_border_color=AppleColors.WARNING,
            )
            
            price_field = ft.TextField(
                hint_text="单价",
                width=70,
                height=40,
                border_radius=8,
                text_size=14,
                bgcolor=AppleColors.BG_TERTIARY,
                border_color=AppleColors.BORDER,
                focused_border_color=AppleColors.WARNING,
            )
            
            subtotal_text = ft.Text("-¥0.00", size=14, color=AppleColors.DANGER, width=80)
            
            def delete_row():
                if len(dlg_item_rows) > 1:
                    dlg_items_container.controls.remove(row_container)
                    dlg_item_rows.remove(row_data)
                    update_dlg_summary()
            
            delete_btn = ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_size=16,
                icon_color=AppleColors.TEXT_TERTIARY,
                on_click=lambda _: delete_row(),
            )
            
            # 数量回车跳到单价 (async)
            async def on_qty_submit(e, pf=price_field):
                try:
                    await pf.focus()
                except Exception as ex:
                    print(f"[warn] qty focus failed: {ex}")
            qty_field.on_submit = on_qty_submit
            
            # 单价回车添加新行 (async)
            async def on_price_submit(e):
                try:
                    add_dlg_item_row(focus_first=True)
                    if dlg_item_rows:
                        await dlg_item_rows[-1]["qty_field"].focus()
                except Exception as ex:
                    print(f"[warn] price submit failed: {ex}")
            price_field.on_submit = on_price_submit
            
            # 输入变化时更新汇总
            qty_field.on_change = lambda e: update_dlg_summary()
            price_field.on_change = lambda e: update_dlg_summary()
            
            row_container = ft.Row(
                controls=[qty_field, price_field, subtotal_text, delete_btn],
                spacing=10,
            )
            
            row_data = {
                "qty_field": qty_field,
                "price_field": price_field,
                "subtotal_text": subtotal_text,
                "container": row_container,
            }
            
            dlg_item_rows.append(row_data)
            dlg_items_container.controls.append(row_container)
            self.page.update()
            
            if focus_first:
                qty_field.focus()
        
        def do_return_all(e):
            try:
                items_to_add = []
                total_qty = 0
                total_amount = 0.0
                
                for row in dlg_item_rows:
                    qty_str = row["qty_field"].value
                    price_str = row["price_field"].value
                    
                    if qty_str and price_str:
                        qty = int(qty_str)
                        price = float(price_str)
                        if qty > 0 and price > 0:
                            items_to_add.append({"quantity": -qty, "unit_price": price})  # 负数表示退货
                            total_qty += qty
                            total_amount += qty * price
                
                if not items_to_add:
                    self.show_error("请至少添加一个有效的退货行")
                    return
                
                self.page.pop_dialog()
                
                # 往原有记录添加退货明细（负数）
                if "items" not in record:
                    record["items"] = []
                record["items"].extend(items_to_add)
                
                # 重新计算总计
                all_total_qty = sum(item.get("quantity", 0) for item in record["items"])
                all_total_amount = sum(item.get("quantity", 0) * item.get("unit_price", 0) for item in record["items"])
                record["quantity"] = all_total_qty
                record["total_amount"] = all_total_amount
                if all_total_qty != 0:
                    record["unit_price"] = abs(all_total_amount / all_total_qty)
                
                self.save_records()
                self.refresh_display()
                self.show_success(f"已添加退货 {total_qty}套，共 -¥{total_amount:.2f}")
                
            except ValueError:
                self.show_error("请输入有效的数量和单价")
        
        dlg_content = ft.Column(
            controls=[
                ft.Text(f"记录 #{record['id']} - 当前: {record.get('quantity', 0)}套, ¥{record.get('total_amount', 0):.2f}",
                        size=13, color=AppleColors.TEXT_SECONDARY),
                ft.Divider(height=5),
                # 表头
                ft.Row(
                    controls=[
                        ft.Text("数量", size=12, color=AppleColors.TEXT_SECONDARY, width=70),
                        ft.Text("单价", size=12, color=AppleColors.TEXT_SECONDARY, width=70),
                        ft.Text("小计", size=12, color=AppleColors.TEXT_SECONDARY, width=80),
                    ],
                    spacing=10,
                ),
                dlg_items_container,
                ft.TextButton("+ 添加退货", on_click=lambda e: add_dlg_item_row(focus_first=True),
                             style=ft.ButtonStyle(color=AppleColors.WARNING)),
                ft.Divider(height=5),
                # 汇总
                ft.Row(
                    controls=[
                        ft.Text("汇总:", size=14, color=AppleColors.TEXT_SECONDARY),
                        dlg_summary_qty,
                        ft.Container(expand=True),
                        dlg_summary_total,
                    ],
                ),
            ],
            tight=True,
            spacing=8,
            width=320,
        )
        
        # 添加第一行
        add_dlg_item_row(focus_first=False)
        
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("添加退货明细", color=AppleColors.WARNING),
            content=dlg_content,
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("确认退货", on_click=do_return_all,
                               style=ft.ButtonStyle(bgcolor=AppleColors.WARNING, 
                                                    color=AppleColors.BG_SECONDARY)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        # 保存原来的键盘事件
        original_keyboard_handler = self.page.on_keyboard_event
        
        # 弹窗关闭时恢复原来的键盘事件
        def restore_keyboard():
            self.page.on_keyboard_event = original_keyboard_handler
        
        # 包装退货函数，先恢复键盘再执行
        def do_return_all_with_restore(e):
            restore_keyboard()
            do_return_all(e)
        
        # 设置弹窗专用的键盘事件
        def on_dlg_keyboard(e):
            if e.key == "Enter" and e.ctrl:
                do_return_all_with_restore(e)
        
        self.page.on_keyboard_event = on_dlg_keyboard
        
        # 更新按钮事件
        dlg.actions[0].on_click = lambda e: (restore_keyboard(), self.page.pop_dialog())
        dlg.actions[1].on_click = do_return_all_with_restore
        
        self.page.show_dialog(dlg)
        
        # 弹窗打开后聚焦到第一个输入框
        if dlg_item_rows:
            dlg_item_rows[0]["qty_field"].focus()

    def show_success(self, message):
        """显示成功提示"""
        print(f"[DEBUG] show_success: {message}")
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=AppleColors.SUCCESS,
            duration=2000,
        )
        self.page.snack_bar = snack
        snack.open = True
        self.page.update()

    def show_error(self, message):
        """显示错误提示"""
        print(f"[DEBUG] show_error: {message}")
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=AppleColors.DANGER,
            duration=3000,
        )
        self.page.snack_bar = snack
        snack.open = True
        self.page.update()


def main(page: ft.Page):
    # Set window size and title
    page.title = "家纺记账系统"
    page.window.width = 1400
    page.window.height = 900
    
    try:
        page.window.maximized = True
    except Exception:
        pass
    
    # Initialize app
    try:
        app = AccountingApp(page)
    except Exception as e:
        print(f"[ERROR] AccountingApp init failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    try:
        app.refresh_display()
    except Exception as e:
        print(f"[ERROR] refresh_display failed: {e}")
        import traceback
        traceback.print_exc()
    
    
    try:
        page.update()
    except Exception as e:
        print(f"[ERROR] page.update failed: {e}")


if __name__ == "__main__":
    ft.run(main)

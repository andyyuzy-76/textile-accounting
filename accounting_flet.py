#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
家纺四件套记账系统 - Flet 苹果风格版本
功能：图形化界面实时记账
作者：AI Assistant
日期：2026-02-21
"""

import asyncio
import flet as ft
import json
import os
import csv
import threading
import time
import ctypes
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from app_core.paths import get_data_dir, get_records_file
from app_core.services.importers import import_csv_records
from app_core.services.printer_settings import PrinterSettingsStore
from app_core.services.records import RecordService
from app_core.storage import JsonStore
from auto_updater import check_for_updates as check_updates_fn
from auto_updater import perform_update as perform_update_fn

# 导入打印模块
try:
    from receipt_printer import (
        ReceiptPrinter as ReceiptPrinterClass,
        get_printer_list as get_printer_list_fn,
    )
except ImportError:
    ReceiptPrinterClass = None
    get_printer_list_fn = None

PRINT_AVAILABLE = ReceiptPrinterClass is not None


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


VERSION = "1.15.8"


class AccountingApp:
    def get_record_kind(self, record: dict[str, Any]) -> str:
        """统一获取记录类型"""
        record_type = str(record.get("type", ""))
        if record_type in {"sale", "return", "mixed"}:
            return record_type
        if int(record.get("quantity", 0)) < 0:
            return "return"
        return "sale"

    def get_record_visuals(self, record: dict[str, Any]) -> tuple[str, str, str, str]:
        """返回记录展示样式：文本、颜色、背景、边框"""
        kind = self.get_record_kind(record)
        if kind == "return":
            return ("退货", AppleColors.DANGER, "#fef2f2", AppleColors.DANGER)
        if kind == "mixed":
            return ("混合", AppleColors.INFO, "#eff6ff", AppleColors.INFO)
        return (
            "销售",
            AppleColors.SUCCESS,
            AppleColors.BG_TERTIARY,
            AppleColors.BORDER,
        )

    def get_customer_names(self) -> list[str]:
        """获取客户列表"""
        customers = self.printer_settings.get("customers", [])
        return [str(name).strip() for name in customers if str(name).strip()]

    def build_customer_options(self, selected: str = "") -> list[ft.dropdown.Option]:
        """构建客户下拉选项"""
        names = self.get_customer_names()
        if selected and selected not in names:
            names.append(selected)
        options = [ft.dropdown.Option("", "未选择")]
        options.extend(ft.dropdown.Option(name, name) for name in names)
        return options

    def refresh_customer_dropdown(self):
        """刷新主表单客户下拉"""
        current_value = (
            self.customer_field.value if hasattr(self.customer_field, "value") else ""
        )
        self.customer_field.options = self.build_customer_options(
            str(current_value or "")
        )
        self.page.update()

    def __init__(self, page: ft.Page):
        self.page = page
        self.data_dir = str(get_data_dir())
        self.data_file = str(get_records_file())
        os.makedirs(self.data_dir, exist_ok=True)
        self.record_service = RecordService(JsonStore(Path(self.data_file)))
        self.printer_settings_store = PrinterSettingsStore(
            Path(self.data_dir) / "printer_settings.json"
        )
        self.date_field = ft.TextField()
        self.items_container = ft.Column()
        self.summary_qty = ft.Text()
        self.summary_total = ft.Text()
        self.customer_field = ft.Dropdown(options=[ft.dropdown.Option("", "未选择")])
        self.note_field = ft.TextField()
        self.stats_text = ft.Text()
        self.records_list = ft.Column()
        self.filter_date_field = ft.TextField()
        self.records_scope_text = ft.Text()
        self.total_label = ft.Text()
        self.record_filter_buttons: dict[str, ft.TextButton] = {}
        self.printer_settings: dict[str, Any] = self.printer_settings_store.load()
        self.records = self.load_records()
        self._sorted_records_cache: list[dict[str, Any]] = []
        self._records_by_date: dict[str, list[dict[str, Any]]] = {}
        self._records_by_month: dict[str, list[dict[str, Any]]] = {}
        self._records_by_year: dict[str, list[dict[str, Any]]] = {}
        self._record_indexes_ready = False
        self._record_indexes_dirty = True
        self.item_rows: list[dict[str, Any]] = []
        self._ctrl_enter_submit_pending = False
        self.receipt_printer = (
            ReceiptPrinterClass() if PRINT_AVAILABLE and ReceiptPrinterClass else None
        )
        self.load_printer_settings()

        # 设置全局键盘事件：Ctrl+Enter 提交记录
        page.on_keyboard_event = self.handle_main_form_keyboard

        try:
            self.build_ui()
        except Exception as e:
            print(f"[ERROR] build_ui failed: {e}")
            import traceback

            traceback.print_exc()

        try:
            self.page.run_task(self.prewarm_record_indexes)
        except Exception:
            pass

    def load_records(self) -> list[dict[str, Any]]:
        """加载历史记录"""
        self.records = self.record_service.reload()
        self.mark_record_indexes_dirty()
        return self.records

    def save_records(self):
        """保存记录"""
        self.records = self.record_service.replace_records(self.records)
        self.mark_record_indexes_dirty()

    def load_printer_settings(self):
        """加载打印机设置"""
        self.printer_settings = self.printer_settings_store.load()
        if not PRINT_AVAILABLE or not self.receipt_printer:
            return
        self.printer_settings_store.apply_to_printer(
            self.receipt_printer, self.printer_settings
        )

    def save_printer_settings(self, settings: dict[str, Any]):
        """保存打印机设置"""
        self.printer_settings = self.printer_settings_store.save(settings)
        if PRINT_AVAILABLE and self.receipt_printer:
            self.printer_settings_store.apply_to_printer(
                self.receipt_printer, self.printer_settings
            )
        self.refresh_customer_dropdown()

    def handle_main_form_keyboard(self, e):
        """处理主界面的全局键盘事件"""
        if e.key == "Enter" and e.ctrl:
            self._ctrl_enter_submit_pending = True
            self.add_record()

    def mark_record_indexes_dirty(self):
        """标记记录索引需要重建"""
        self._record_indexes_dirty = True
        self._record_indexes_ready = False

    def build_record_indexes(self):
        """构建按日期/月/年的记录索引，并缓存排序结果"""
        sorted_records = sorted(
            self.records,
            key=self.get_record_sort_key,
            reverse=True,
        )

        records_by_date: dict[str, list[dict[str, Any]]] = {}
        records_by_month: dict[str, list[dict[str, Any]]] = {}
        records_by_year: dict[str, list[dict[str, Any]]] = {}

        for record in sorted_records:
            date_text = self.get_record_date_text(record)
            month_text = date_text[:7]
            year_text = date_text[:4]

            if date_text:
                records_by_date.setdefault(date_text, []).append(record)
            if len(month_text) == 7:
                records_by_month.setdefault(month_text, []).append(record)
            if len(year_text) == 4:
                records_by_year.setdefault(year_text, []).append(record)

        self._sorted_records_cache = sorted_records
        self._records_by_date = records_by_date
        self._records_by_month = records_by_month
        self._records_by_year = records_by_year
        self._record_indexes_dirty = False
        self._record_indexes_ready = True

    async def prewarm_record_indexes(self):
        """后台预热记录索引，避免首次筛选时阻塞"""
        await asyncio.sleep(0)
        await asyncio.to_thread(self.build_record_indexes)

    def ensure_record_indexes_ready(self):
        """确保记录索引已就绪，必要时同步构建"""
        if getattr(self, "_record_indexes_ready", False) and not getattr(
            self, "_record_indexes_dirty", True
        ):
            return
        self.build_record_indexes()

    def should_skip_price_submit_after_ctrl_enter(self) -> bool:
        """避免 Ctrl+Enter 提交后，价格输入框的回车事件再次补空行"""
        if not getattr(self, "_ctrl_enter_submit_pending", False):
            return False

        self._ctrl_enter_submit_pending = False

        item_rows = getattr(self, "item_rows", [])
        if not item_rows:
            return True

        for row in item_rows:
            if str(row["qty_field"].value or "").strip():
                return False
            if str(row["price_field"].value or "").strip():
                return False
            if str(row["type_field"].value or "sale").strip() != "sale":
                return False

        if str(getattr(self.customer_field, "value", "") or "").strip():
            return False
        if str(getattr(self.note_field, "value", "") or "").strip():
            return False

        return True

    def maybe_auto_print(self, record: dict[str, Any]):
        """在启用时自动打印小票"""
        if self.printer_settings.get("auto_print"):
            self.print_receipt(record)

    def get_receipt_preview_text(self, settings: dict[str, Any]) -> str:
        """生成小票预览文本"""
        if not PRINT_AVAILABLE or not ReceiptPrinterClass:
            return "打印模块未安装，无法预览。"

        preview_printer = ReceiptPrinterClass()
        self.printer_settings_store.apply_to_printer(preview_printer, settings)
        preview_printer.footer_text = settings.get(
            "footer_text", preview_printer.footer_text
        )

        test_record = {
            "id": 8888,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "quantity": 2,
            "unit_price": 280.0,
            "total_amount": 560.0,
            "note": "测试预览",
            "type": "sale",
            "items": [{"quantity": 2, "unit_price": 280.0}],
        }
        compact = bool(settings.get("compact_mode", True))
        return preview_printer.format_receipt(test_record, compact=compact)

    def show_printer_settings(self):
        """显示打印设置弹窗"""
        if not PRINT_AVAILABLE or not self.receipt_printer:
            self.show_error("打印模块未安装")
            return

        current = dict(self.printer_settings)
        printers = ["使用系统默认打印机"]
        if get_printer_list_fn:
            try:
                printers.extend(get_printer_list_fn())
            except Exception:
                pass

        printer_dropdown = ft.Dropdown(
            label="打印机",
            value=current.get("printer_name", "") or "使用系统默认打印机",
            options=[ft.dropdown.Option(name) for name in printers],
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
        )
        paper_width_dropdown = ft.Dropdown(
            label="纸张宽度",
            value=str(current.get("paper_width", 58)),
            options=[
                ft.dropdown.Option("58"),
                ft.dropdown.Option("76"),
                ft.dropdown.Option("80"),
            ],
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
        )
        auto_print_checkbox = ft.Checkbox(
            label="销售/退货后自动打印小票",
            value=bool(current.get("auto_print", False)),
        )
        compact_mode_checkbox = ft.Checkbox(
            label="紧凑模式（一张纸打印）",
            value=bool(current.get("compact_mode", True)),
        )
        shop_name_field = ft.TextField(
            label="店铺名称",
            value=str(current.get("shop_name", "家纺四件套")),
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
        )
        shop_address_field = ft.TextField(
            label="店铺地址",
            value=str(current.get("shop_address", "")),
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
        )
        shop_phone_field = ft.TextField(
            label="联系电话",
            value=str(current.get("shop_phone", "")),
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
        )
        footer_field = ft.TextField(
            label="底部文字",
            value=str(current.get("footer_text", "谢谢惠顾，欢迎下次光临！")),
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
        )
        preview_text = ft.TextField(
            value=self.get_receipt_preview_text(current),
            multiline=True,
            min_lines=12,
            max_lines=12,
            read_only=True,
            border_radius=10,
            bgcolor=AppleColors.BG_TERTIARY,
            text_size=12,
        )

        def collect_settings() -> dict[str, Any]:
            printer_name = printer_dropdown.value or "使用系统默认打印机"
            return {
                "shop_name": shop_name_field.value or "家纺四件套",
                "shop_address": shop_address_field.value or "",
                "shop_phone": shop_phone_field.value or "",
                "footer_text": footer_field.value or "谢谢惠顾，欢迎下次光临！",
                "printer_name": ""
                if printer_name == "使用系统默认打印机"
                else printer_name,
                "paper_width": int(paper_width_dropdown.value or "58"),
                "auto_print": bool(auto_print_checkbox.value),
                "compact_mode": bool(compact_mode_checkbox.value),
            }

        def update_preview(_=None):
            preview_text.value = self.get_receipt_preview_text(collect_settings())
            self.page.update()

        def save_settings(_):
            self.save_printer_settings(collect_settings())
            self.page.pop_dialog()
            self.show_success("打印设置已保存")

        dialog_actions: list[ft.Control] = [
            ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
            ft.TextButton("更新预览", on_click=update_preview),
            ft.FilledButton("保存", on_click=save_settings),
        ]

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("🖨️ 打印设置", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    scroll=ft.ScrollMode.AUTO,
                    spacing=12,
                    controls=[
                        printer_dropdown,
                        paper_width_dropdown,
                        auto_print_checkbox,
                        compact_mode_checkbox,
                        shop_name_field,
                        shop_address_field,
                        shop_phone_field,
                        footer_field,
                        ft.Text("预览", size=14, weight=ft.FontWeight.W_500),
                        preview_text,
                    ],
                ),
            ),
            actions=dialog_actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def print_receipt(self, record):
        """打印小票"""
        if not PRINT_AVAILABLE or not self.receipt_printer:
            self.show_error("打印模块未安装")
            return

        try:
            compact = bool(self.printer_settings.get("compact_mode", True))
            printer_name = self.printer_settings.get("printer_name", "") or None
            receipt_text = self.receipt_printer.format_receipt(
                record,
                compact=compact,
                return_records=self.get_return_records(record),
            )
            result = self.receipt_printer.print_to_windows_printer(
                receipt_text,
                printer_name,
            )
            if result.get("success"):
                self.show_success(str(result.get("message", "小票已发送到打印机")))
            else:
                self.show_error(str(result.get("message", "打印失败")))
        except Exception as e:
            self.show_error(f"打印失败: {str(e)}")

    def get_return_records(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        """获取关联的退货记录"""
        record_id = record.get("id")
        if record.get("type") == "return" or record.get("quantity", 0) < 0:
            return []
        return [
            current
            for current in self.records
            if (current.get("type") == "return" or current.get("quantity", 0) < 0)
            and current.get("original_record_id") == record_id
        ]

    def save_receipt_as_text(self, record: dict[str, Any]):
        """保存小票为文本文件"""
        if not PRINT_AVAILABLE or not self.receipt_printer:
            self.show_error("打印模块未安装")
            return
        receipt_printer = self.receipt_printer

        file_picker = ft.FilePicker()
        self.page.overlay.append(file_picker)

        async def save_receipt_file():
            try:
                suggested_name = (
                    f"小票_{record.get('id', '0000')}_{record.get('date', '')}.txt"
                )
                path = await file_picker.save_file(
                    file_name=suggested_name,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["txt"],
                )
                if not path:
                    return

                compact = bool(self.printer_settings.get("compact_mode", True))
                receipt_text = receipt_printer.format_receipt(
                    record,
                    compact=compact,
                    return_records=self.get_return_records(record),
                )
                Path(path).write_text(receipt_text, encoding="utf-8")
                self.show_success(f"小票已保存到:\n{path}")
            except Exception as ex:
                self.show_error(f"保存失败: {str(ex)}")

        self.page.run_task(save_receipt_file)

    def show_receipt_preview(self, record: dict[str, Any]):
        """显示小票预览"""
        if not PRINT_AVAILABLE or not self.receipt_printer:
            self.show_error("打印模块未安装")
            return
        receipt_printer = self.receipt_printer

        compact = bool(self.printer_settings.get("compact_mode", True))
        receipt_text = receipt_printer.format_receipt(
            record,
            compact=compact,
            return_records=self.get_return_records(record),
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("🧾 小票预览", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=460,
                content=ft.Column(
                    spacing=10,
                    controls=[
                        ft.TextField(
                            value=receipt_text,
                            multiline=True,
                            min_lines=20,
                            max_lines=20,
                            read_only=True,
                            border_radius=10,
                            bgcolor=AppleColors.BG_TERTIARY,
                            text_size=12,
                        )
                    ],
                ),
            ),
            actions=[
                ft.TextButton("关闭", on_click=lambda e: self.page.pop_dialog()),
                ft.TextButton(
                    "保存",
                    on_click=lambda e: self.save_receipt_as_text(record),
                ),
                ft.FilledButton(
                    "打印",
                    on_click=lambda e: self.print_receipt(record),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def import_excel(self):
        """导入 Excel"""
        file_picker = ft.FilePicker()
        self.page.overlay.append(file_picker)

        async def pick_excel_file():
            try:
                files = await file_picker.pick_files(
                    allowed_extensions=["xlsx", "xls"],
                    dialog_title="选择 Excel 文件",
                )
                if not files:
                    return
                filepath = files[0].path
                if not filepath:
                    self.show_error("所选文件没有可用路径")
                    return

                from import_excel import import_from_excel

                result = import_from_excel(filepath)
                if not result.get("success"):
                    self.show_error(
                        str(result.get("error") or result.get("message") or "导入失败")
                    )
                    return

                imported_records = result.get("records", [])
                starting_id = max([r["id"] for r in self.records], default=0) + 1
                for index, imported in enumerate(imported_records, start=starting_id):
                    imported["id"] = index

                if imported_records:
                    self.records.extend(imported_records)
                    self.save_records()
                    self.refresh_display()
                    self.show_success(f"成功导入 {len(imported_records)} 条 Excel 记录")
                else:
                    self.show_error("未找到有效 Excel 记录")
            except Exception as ex:
                self.show_error(f"Excel 导入失败: {str(ex)}")

        self.page.run_task(pick_excel_file)

    def check_for_updates(self):
        """检查更新"""
        update_status = ft.Text("⏳ 正在检查更新...", color=AppleColors.TEXT_SECONDARY)
        update_progress = ft.ProgressBar(
            value=0.0,
            visible=False,
            color=AppleColors.PRIMARY,
            bgcolor=AppleColors.BORDER,
            bar_height=8,
            border_radius=999,
            width=420,
        )
        update_hint = ft.Text(
            "",
            size=12,
            color=AppleColors.TEXT_TERTIARY,
        )
        run_update_button = ft.FilledButton(
            "执行更新",
            visible=False,
        )
        close_button = ft.TextButton("关闭")

        def get_update_progress_value(message: str, current: float) -> float:
            stage_progress = [
                ("准备", 0.08),
                ("下载", 0.35),
                ("校验", 0.62),
                ("应用", 0.84),
                ("重启", 1.0),
            ]
            for keyword, progress in stage_progress:
                if keyword in message:
                    return progress
            return current

        def set_update_progress(message: str):
            current_value = float(update_progress.value or 0.0)
            update_status.value = message
            update_progress.visible = True
            update_progress.value = get_update_progress_value(message, current_value)
            update_hint.value = "更新期间请勿关闭程序，完成后会自动重启。"
            run_update_button.disabled = True
            run_update_button.content = "更新中..."
            close_button.disabled = True
            self.page.update()

        def close_dialog(_=None):
            self.page.pop_dialog()

        async def perform_update_task():
            set_update_progress("⏳ 正在准备更新...")
            loop = asyncio.get_running_loop()

            def progress_callback(message: str):
                loop.call_soon_threadsafe(set_update_progress, message)

            success, update_message = await asyncio.to_thread(
                perform_update_fn,
                progress_callback,
            )
            if success:
                self.show_success(update_message)
            else:
                run_update_button.disabled = False
                run_update_button.content = "执行更新"
                close_button.disabled = False
                self.show_error(update_message)

        run_update_button.on_click = lambda e: self.page.run_task(perform_update_task)
        dialog_actions: list[ft.Control] = [
            close_button,
            run_update_button,
        ]
        close_button.on_click = close_dialog

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("🔍 检查更新", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    controls=[update_status, update_progress, update_hint],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=dialog_actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

        async def run_update_check():
            try:
                has_update, remote, current, message = check_updates_fn(silent=False)
                if has_update:
                    update_status.value = f"发现新版本 v{remote}\n当前版本: v{current}\n\n{message or '有可用更新。'}"
                    run_update_button.visible = True
                elif message and remote and remote != current:
                    update_status.value = message
                    run_update_button.visible = False
                else:
                    update_status.value = f"✅ 已是最新版本 v{current}"
                    run_update_button.visible = False
                self.page.update()
            except Exception as ex:
                update_status.value = f"❌ 检查更新失败: {str(ex)}"
                run_update_button.visible = False
                self.page.update()

        self.page.run_task(run_update_check)

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
                writer.writerow(
                    ["ID", "日期", "类型", "客户", "数量", "总金额", "备注"]
                )

                for record in self.records:
                    kind = self.get_record_kind(record)
                    record_type = {
                        "sale": "销售",
                        "return": "退货",
                        "mixed": "混合",
                    }.get(kind, "销售")
                    writer.writerow(
                        [
                            record["id"],
                            record["date"],
                            record_type,
                            record.get("customer", ""),
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

        file_picker = ft.FilePicker()
        self.page.overlay.append(file_picker)

        async def pick_csv_file():
            try:
                files = await file_picker.pick_files(
                    allowed_extensions=["csv"],
                    dialog_title="选择CSV文件",
                )
                if not files:
                    return

                filepath = files[0].path
                if not filepath:
                    self.show_error("所选文件没有可用路径")
                    return

                starting_id = max([r["id"] for r in self.records], default=0) + 1
                imported_records = import_csv_records(filepath, starting_id=starting_id)

                if imported_records:
                    self.records.extend(imported_records)
                    self.save_records()
                    self.refresh_display()
                    self.show_success(f"成功导入 {len(imported_records)} 条记录")
                else:
                    self.show_error("未找到有效记录")
            except Exception as ex:
                self.show_error(f"导入失败: {str(ex)}")

        self.page.run_task(pick_csv_file)

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
                        icon=cast(ft.IconData, ft.Icons.UPLOAD_FILE),
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="导入CSV",
                        on_click=lambda _: self.import_csv(),
                    ),
                    ft.IconButton(
                        icon=cast(ft.IconData, ft.Icons.TABLE_VIEW),
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="导入Excel",
                        on_click=lambda _: self.import_excel(),
                    ),
                    ft.IconButton(
                        icon=cast(ft.IconData, ft.Icons.DOWNLOAD),
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="导出CSV",
                        on_click=lambda _: self.export_csv(),
                    ),
                    ft.IconButton(
                        icon=cast(ft.IconData, ft.Icons.PRINT),
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="打印设置",
                        on_click=lambda _: self.show_printer_settings(),
                    ),
                    ft.IconButton(
                        icon=cast(ft.IconData, ft.Icons.SYSTEM_UPDATE),
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="检查更新",
                        on_click=lambda _: self.check_for_updates(),
                    ),
                    ft.IconButton(
                        icon=cast(ft.IconData, ft.Icons.BAR_CHART),
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="月度统计",
                        on_click=lambda _: self.show_monthly_stats(),
                    ),
                    ft.IconButton(
                        icon=cast(ft.IconData, ft.Icons.SETTINGS),
                        icon_color=AppleColors.TEXT_SECONDARY,
                        tooltip="系统设置",
                        on_click=lambda _: self.show_settings(),
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

        type_hint = ft.Container(
            content=ft.Text(
                "每一行都可以单独选择“销售 / 退货”，一张新记录可同时填写销售和退货。",
                size=13,
                color=AppleColors.TEXT_SECONDARY,
            ),
            padding=12,
            bgcolor=AppleColors.BG_TERTIARY,
            border_radius=10,
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
                                        "类型",
                                        size=13,
                                        color=AppleColors.TEXT_SECONDARY,
                                        width=110,
                                    ),
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
                            type_hint,
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

        self.customer_field = ft.Dropdown(
            label="客户",
            hint_text="选择客户",
            options=self.build_customer_options(),
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
            border_color=AppleColors.BORDER,
            focused_border_color=AppleColors.PRIMARY,
            height=50,
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
                                ft.Container(
                                    content=ft.Column(
                                        controls=[
                                            ft.Text(
                                                "📝 新记录",
                                                size=18,
                                                weight=ft.FontWeight.BOLD,
                                                color=AppleColors.TEXT_PRIMARY,
                                            ),
                                            ft.Divider(
                                                height=1,
                                                color=AppleColors.DIVIDER,
                                            ),
                                            date_row,
                                            items_section,
                                            summary_section,
                                            self.customer_field,
                                            self.note_field,
                                        ],
                                        spacing=15,
                                        scroll=ft.ScrollMode.AUTO,
                                    ),
                                    expand=True,
                                ),
                                ft.Divider(height=1, color=AppleColors.DIVIDER),
                                ft.Row(
                                    controls=[add_btn, clear_btn],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                            ],
                            spacing=15,
                            expand=True,
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
        self.filter_date_field = ft.TextField(
            hint_text="YYYY-MM-DD",
            width=140,
            height=38,
            border_radius=10,
            bgcolor=AppleColors.BG_TERTIARY,
            border_color=AppleColors.BORDER,
            focused_border_color=AppleColors.PRIMARY,
            text_size=14,
        )

        date_filter_controls: list[ft.Control] = [
            self.filter_date_field,
            ft.TextButton(
                "查询",
                on_click=lambda _: self.show_selected_date_records(),
                style=ft.ButtonStyle(color=AppleColors.PRIMARY),
            ),
            ft.TextButton(
                "填今天",
                on_click=lambda _: self.fill_today_filter_date(),
                style=ft.ButtonStyle(color=AppleColors.TEXT_SECONDARY),
            ),
        ]

        self.records_scope_text = ft.Text(
            "当前：今天",
            size=13,
            color=AppleColors.TEXT_SECONDARY,
        )

        self.record_filter_buttons = {
            "today": ft.TextButton(
                "今天",
                on_click=lambda _: self.show_today_records(),
                style=self.build_record_filter_button_style(active=True),
            ),
            "month": ft.TextButton(
                "本月",
                on_click=lambda _: self.show_month_records(),
                style=self.build_record_filter_button_style(active=False),
            ),
            "year": ft.TextButton(
                "本年",
                on_click=lambda _: self.show_year_records(),
                style=self.build_record_filter_button_style(active=False),
            ),
            "all": ft.TextButton(
                "全部",
                on_click=lambda _: self.show_all_records(),
                style=self.build_record_filter_button_style(active=False),
            ),
        }

        # 筛选按钮
        filter_buttons = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text(
                            "📋 记录列表",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=AppleColors.TEXT_PRIMARY,
                        ),
                        self.records_scope_text,
                    ],
                    spacing=4,
                ),
                ft.Container(expand=True),
                self.record_filter_buttons["today"],
                self.record_filter_buttons["month"],
                self.record_filter_buttons["year"],
                self.record_filter_buttons["all"],
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        date_filter_row = ft.Row(
            controls=date_filter_controls,
            spacing=8,
            alignment=ft.MainAxisAlignment.START,
        )

        # 记录列表
        self.records_list = ft.ListView(
            spacing=10,
            expand=True,
            auto_scroll=False,
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
                    date_filter_row,
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
        type_field = ft.Dropdown(
            width=110,
            height=40,
            value="sale",
            border_radius=8,
            bgcolor=AppleColors.BG_TERTIARY,
            border_color=AppleColors.BORDER,
            focused_border_color=AppleColors.PRIMARY,
            options=[
                ft.dropdown.Option("sale", "销售"),
                ft.dropdown.Option("return", "退货"),
            ],
            on_select=lambda _: self.update_summary(),
        )

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
                if self.should_skip_price_submit_after_ctrl_enter():
                    return
                # 添加新行
                self.add_item_row()
                # 焦点移动到新行的数量输入框
                if self.item_rows:
                    new_qty_field = self.item_rows[-1]["qty_field"]
                    await new_qty_field.focus()
            except Exception as ex:
                print(f"[warn] price on_submit failed: {ex}")

        price_field.on_submit = _price_on_submit

        row_container = ft.Row(
            controls=[type_field, qty_field, price_field, subtotal_text, delete_btn],
            spacing=10,
        )

        row_data = {
            "type_field": type_field,
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
        sale_qty = 0
        sale_amount = 0.0
        return_qty = 0
        return_amount = 0.0

        for row in self.item_rows:
            try:
                row_type = row["type_field"].value or "sale"
                qty = int(row["qty_field"].value or 0)
                price = float(row["price_field"].value or 0)
                subtotal = qty * price
                if row_type == "return":
                    row["subtotal_text"].value = f"-¥{subtotal:.2f}"
                    row["subtotal_text"].color = AppleColors.DANGER
                    return_qty += qty
                    return_amount += subtotal
                else:
                    row["subtotal_text"].value = f"¥{subtotal:.2f}"
                    row["subtotal_text"].color = AppleColors.TEXT_SECONDARY
                    sale_qty += qty
                    sale_amount += subtotal
            except:
                row["subtotal_text"].value = "¥0.00"
                row["subtotal_text"].color = AppleColors.TEXT_SECONDARY

        net_qty = sale_qty - return_qty
        net_amount = sale_amount - return_amount
        self.summary_qty.value = f"售 {sale_qty}套 / 退 {return_qty}套 / 净 {net_qty}套"
        if net_amount < 0:
            self.summary_total.value = f"-¥{abs(net_amount):.2f}"
            self.summary_total.color = AppleColors.DANGER
        else:
            self.summary_total.value = f"¥{net_amount:.2f}"
            self.summary_total.color = AppleColors.PRIMARY
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
            self.item_rows[0]["type_field"].value = "sale"
            self.item_rows[0]["qty_field"].value = ""
            self.item_rows[0]["price_field"].value = ""
            self.item_rows[0]["subtotal_text"].value = "¥0.00"
            self.item_rows[0]["subtotal_text"].color = AppleColors.TEXT_SECONDARY

        # 清空备注
        self.customer_field.value = ""
        self.note_field.value = ""

        # 更新汇总
        self.update_summary()
        self.page.update()

    def add_record(self):
        """添加记录"""
        try:
            date = self.date_field.value.strip()
            customer = (
                self.customer_field.value.strip() if self.customer_field.value else ""
            )
            note = self.note_field.value.strip() if self.note_field.value else ""

            if not date:
                self.show_error("请输入日期！")
                return

            items = []
            for row in self.item_rows:
                qty_str = row["qty_field"].value
                price_str = row["price_field"].value
                row_type = row["type_field"].value or "sale"

                if qty_str and price_str:
                    try:
                        qty = int(qty_str)
                        price = float(price_str)
                        if qty > 0 and price > 0:
                            items.append(
                                {
                                    "quantity": qty,
                                    "unit_price": price,
                                    "record_type": row_type,
                                }
                            )
                    except ValueError:
                        pass

            if not items:
                self.show_error("请至少添加一个有效的商品行！")
                return

            record = self.record_service.add_record(
                date=date,
                items=items,
                customer=customer,
                note=note,
                record_type="mixed",
            )
            self.records = self.record_service.list_records()
            self.mark_record_indexes_dirty()

            self.refresh_display()
            self.clear_form()
            self.maybe_auto_print(record)

            type_map = {"sale": "销售", "return": "退货", "mixed": "混合"}
            type_label = type_map.get(self.get_record_kind(record), "销售")
            self.show_success(
                f"✅ {type_label}记录添加成功！\n金额: ¥{abs(record['total_amount']):.2f}"
            )

        except Exception as e:
            self.show_error(f"添加失败: {str(e)}")

    def refresh_display(self):
        """刷新显示"""
        self.show_today_records()
        self.update_stats()

    def build_record_filter_button_style(self, active: bool) -> ft.ButtonStyle:
        """构建记录筛选按钮样式"""
        return ft.ButtonStyle(
            color=AppleColors.PRIMARY if active else AppleColors.TEXT_SECONDARY,
            bgcolor="#e8f2ff" if active else None,
            shape=ft.RoundedRectangleBorder(radius=999),
            padding=ft.Padding(left=14, right=14, top=8, bottom=8),
        )

    def update_records_scope(self, scope_key: str, detail: str, count: int):
        """更新当前记录筛选范围的可视反馈"""
        scope_labels = {
            "today": "今天",
            "date": "指定日期",
            "month": "本月",
            "year": "本年",
            "all": "全部",
        }
        scope_label = scope_labels.get(scope_key, "记录")
        detail_suffix = f" ({detail})" if detail else ""
        count_suffix = f" · {count} 条"

        if hasattr(self, "records_scope_text") and self.records_scope_text:
            self.records_scope_text.value = (
                f"当前：{scope_label}{detail_suffix}{count_suffix}"
            )

        for key, button in getattr(self, "record_filter_buttons", {}).items():
            button.style = self.build_record_filter_button_style(key == scope_key)

    def get_record_date_text(self, record: dict[str, Any]) -> str:
        """统一读取记录日期，避免数据格式差异影响筛选"""
        return str(record.get("date", "")).strip()

    def get_record_created_at_text(self, record: dict[str, Any]) -> str:
        """统一读取记录创建时间，用于同日记录排序"""
        return str(record.get("created_at", "")).strip()

    def get_record_created_time_display(self, record: dict[str, Any]) -> str:
        """提取记录创建时间的时分，供列表展示"""
        created_at = self.get_record_created_at_text(record).replace("T", " ")
        if not created_at:
            return ""

        if " " in created_at:
            time_part = created_at.split(" ", 1)[1].strip()
        else:
            time_part = created_at.strip()

        if len(time_part) >= 5 and time_part[2] == ":":
            return time_part[:5]
        return ""

    def get_record_sort_key(self, record: dict[str, Any]) -> tuple[str, str, int]:
        """统一记录排序：日期倒序，再按创建时间和记录ID倒序"""
        try:
            record_id = int(record.get("id", 0))
        except (TypeError, ValueError):
            record_id = 0

        return (
            self.get_record_date_text(record),
            self.get_record_created_at_text(record),
            record_id,
        )

    def show_records_for_scope(
        self,
        scope_key: str,
        detail: str,
        records: list[dict[str, Any]],
        empty_message: str,
        presorted: bool = False,
    ):
        """按指定范围展示记录，并同步界面反馈"""
        self.update_records_scope(scope_key, detail, len(records))
        try:
            self.display_records(records, empty_message, presorted)
        except TypeError:
            try:
                self.display_records(records, empty_message)
            except TypeError:
                self.display_records(records)

    def show_today_records(self):
        """显示今日记录"""
        today = datetime.now().strftime("%Y-%m-%d")
        filtered = [r for r in self.records if self.get_record_date_text(r) == today]
        self.show_records_for_scope("today", today, filtered, f"{today} 暂无记录")

    def fill_today_filter_date(self):
        """将筛选日期填充为今天"""
        self.filter_date_field.value = datetime.now().strftime("%Y-%m-%d")
        self.page.update()

    def show_selected_date_records(self):
        """按指定日期显示记录"""
        selected_date = str(self.filter_date_field.value or "").strip()
        if not selected_date:
            self.show_error("请输入要查询的日期，格式如 2026-04-21")
            return
        try:
            datetime.strptime(selected_date, "%Y-%m-%d")
        except ValueError:
            self.show_error("日期格式错误，请使用 YYYY-MM-DD")
            return

        self.ensure_record_indexes_ready()
        filtered = list(self._records_by_date.get(selected_date, []))
        self.show_records_for_scope(
            "date",
            selected_date,
            filtered,
            f"{selected_date} 暂无记录",
            presorted=True,
        )

    def show_month_records(self):
        """显示本月记录"""
        this_month = datetime.now().strftime("%Y-%m")
        self.ensure_record_indexes_ready()
        filtered = list(self._records_by_month.get(this_month, []))
        self.show_records_for_scope(
            "month",
            this_month,
            filtered,
            f"{this_month} 暂无记录",
            presorted=True,
        )

    def show_year_records(self):
        """显示本年记录"""
        this_year = datetime.now().strftime("%Y")
        self.ensure_record_indexes_ready()
        filtered = list(self._records_by_year.get(this_year, []))
        self.show_records_for_scope(
            "year",
            this_year,
            filtered,
            f"{this_year} 暂无记录",
            presorted=True,
        )

    def show_all_records(self):
        """显示所有记录"""
        self.ensure_record_indexes_ready()
        self.show_records_for_scope(
            "all",
            "",
            list(self._sorted_records_cache),
            "当前没有任何记录",
            presorted=True,
        )

    def display_records(
        self,
        records,
        empty_message: str = "暂无记录",
        presorted: bool = False,
    ):
        """显示记录列表"""
        self.records_list.controls.clear()

        if presorted:
            sorted_records = list(records)
        else:
            # 按日期排序（降序）
            sorted_records = sorted(
                records,
                key=self.get_record_sort_key,
                reverse=True,
            )

        total = 0.0
        if not sorted_records:
            empty_controls = [
                ft.Text(
                    "暂无记录",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=AppleColors.TEXT_PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                )
            ]
            if empty_message and empty_message != "暂无记录":
                empty_controls.append(
                    ft.Text(
                        empty_message,
                        size=13,
                        color=AppleColors.TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER,
                    )
                )

            self.records_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=empty_controls,
                        spacing=6,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(left=20, right=20, top=32, bottom=32),
                    bgcolor=AppleColors.BG_TERTIARY,
                    border_radius=14,
                    border=ft.Border.all(1, AppleColors.BORDER),
                )
            )

        for record in sorted_records:
            # 创建记录卡片
            card = self.create_record_card(record)
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

    def create_record_card(self, record):
        """创建记录卡片"""
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
                        color=AppleColors.DANGER
                        if is_item_return
                        else AppleColors.TEXT_PRIMARY,
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
                    color=AppleColors.DANGER
                    if is_item_return
                    else AppleColors.TEXT_PRIMARY,
                )
            )

        customer_text = str(record.get("customer", "")).strip()

        type_text, type_color, card_bgcolor, card_border_color = (
            self.get_record_visuals(record)
        )
        created_time_text = self.get_record_created_time_display(record)
        total_amount = float(record.get("total_amount", 0))
        amount_text = (
            f"-¥{abs(total_amount):.2f}" if total_amount < 0 else f"¥{total_amount:.2f}"
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
                                    ft.Text(
                                        created_time_text,
                                        size=13,
                                        color=AppleColors.TEXT_TERTIARY,
                                    )
                                    if created_time_text
                                    else ft.Container(),
                                ],
                                spacing=10,
                            ),
                            ft.Row(
                                controls=detail_controls,
                                spacing=5,
                                wrap=True,
                            ),
                            ft.Text(
                                f"客户：{customer_text}",
                                size=12,
                                color=AppleColors.INFO,
                                weight=ft.FontWeight.W_500,
                            )
                            if customer_text
                            else ft.Container(),
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
            bgcolor=card_bgcolor,
            border_radius=10,
            border=ft.border.all(1, card_border_color),
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
                    self.show_receipt_preview(record)
                elif action == "delete":
                    self.delete_record(record)

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"记录 #{record['id']} 操作", weight=ft.FontWeight.BOLD),
                content=ft.Column(
                    controls=[
                        ft.TextButton(
                            "📋 销售明细",
                            data="detail",
                            on_click=on_action,
                            style=ft.ButtonStyle(color=AppleColors.PRIMARY),
                        ),
                        ft.Divider(),
                        ft.TextButton(
                            "编辑",
                            data="edit",
                            on_click=on_action,
                            style=ft.ButtonStyle(color=AppleColors.PRIMARY),
                        ),
                        ft.TextButton(
                            "添加销售",
                            data="add_sale",
                            on_click=on_action,
                            style=ft.ButtonStyle(color=AppleColors.SUCCESS),
                        ),
                        ft.TextButton(
                            "退货",
                            data="return",
                            on_click=on_action,
                            style=ft.ButtonStyle(color=AppleColors.WARNING),
                        ),
                        ft.TextButton(
                            "打印小票",
                            data="print",
                            on_click=on_action,
                            style=ft.ButtonStyle(color=AppleColors.INFO),
                        ),
                        ft.Divider(),
                        ft.TextButton(
                            "删除",
                            data="delete",
                            on_click=on_action,
                            style=ft.ButtonStyle(color=AppleColors.DANGER),
                        ),
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
            record_kind = self.get_record_kind(record)
            print(
                f"[DEBUG] show_record_detail: type={record.get('type')}, quantity={record.get('quantity')}, kind={record_kind}"
            )

            # 表头
            header = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text(
                            "数量",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=AppleColors.TEXT_SECONDARY,
                            width=80,
                        ),
                        ft.Text(
                            "单价",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=AppleColors.TEXT_SECONDARY,
                            width=100,
                        ),
                        ft.Text(
                            "小计",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=AppleColors.TEXT_SECONDARY,
                            width=100,
                        ),
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
                                ft.Text(
                                    qty_display, size=14, color=text_color, width=80
                                ),
                                ft.Text(
                                    f"¥{price:.0f}",
                                    size=14,
                                    color=AppleColors.TEXT_PRIMARY,
                                    width=100,
                                ),
                                ft.Text(
                                    subtotal_display,
                                    size=14,
                                    color=text_color,
                                    width=100,
                                    weight=ft.FontWeight.W_500,
                                ),
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

            if record_kind == "return":
                qty_text = f"合计: -{total_qty}套"
                amount_text = f"-¥{total_amount:.0f}"
            elif record_kind == "mixed":
                qty_text = f"净合计: {record.get('quantity', 0)}套"
                amount_text = (
                    f"-¥{total_amount:.0f}"
                    if float(record.get("total_amount", 0)) < 0
                    else f"¥{float(record.get('total_amount', 0)):.0f}"
                )
            else:
                qty_text = f"合计: {total_qty}套"
                amount_text = f"¥{total_amount:.0f}"

            summary_row = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text(
                            qty_text,
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=AppleColors.DANGER
                            if record_kind == "return"
                            else (
                                AppleColors.INFO
                                if record_kind == "mixed"
                                else AppleColors.TEXT_PRIMARY
                            ),
                        ),
                        ft.Container(expand=True),
                        ft.Text(
                            amount_text,
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=AppleColors.DANGER
                            if float(record.get("total_amount", 0)) < 0
                            else (
                                AppleColors.INFO
                                if record_kind == "mixed"
                                else AppleColors.SUCCESS
                            ),
                        ),
                    ],
                ),
                bgcolor="#fef2f2"
                if record_kind == "return"
                else (
                    "#eff6ff" if record_kind == "mixed" else AppleColors.BG_SECONDARY
                ),
                padding=ft.padding.only(left=10, right=10, top=10, bottom=10),
                border_radius=5,
            )
            detail_rows.append(summary_row)

            # 记录信息
            record_info = ft.Column(
                controls=[
                    ft.Row(
                        [
                            ft.Text(
                                f"📅 日期: {record.get('date', '-')}",
                                size=13,
                                color=AppleColors.TEXT_SECONDARY,
                            ),
                            ft.Container(expand=True),
                            ft.Text(
                                f"{'🔄 退货' if record_kind == 'return' else ('🔀 混合' if record_kind == 'mixed' else '✅ 销售')}",
                                size=13,
                                color=AppleColors.DANGER
                                if record_kind == "return"
                                else (
                                    AppleColors.INFO
                                    if record_kind == "mixed"
                                    else AppleColors.SUCCESS
                                ),
                                weight=ft.FontWeight.BOLD,
                            ),
                        ]
                    ),
                    ft.Text(
                        f"🆔 记录号: #{record.get('id', '-')}",
                        size=12,
                        color=AppleColors.TEXT_TERTIARY,
                    ),
                    ft.Text(
                        f"⏰ 创建时间: {record.get('created_at', '-')}",
                        size=12,
                        color=AppleColors.TEXT_TERTIARY,
                    ),
                ],
                spacing=5,
            )

            # 备注
            note = record.get("note", "")
            if note:
                note_control = ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "📝 备注:", size=12, color=AppleColors.TEXT_SECONDARY
                            ),
                            ft.Text(note, size=13, color=AppleColors.TEXT_PRIMARY),
                        ],
                        spacing=3,
                    ),
                    bgcolor=AppleColors.BG_TERTIARY,
                    padding=10,
                    border_radius=5,
                )
            else:
                note_control = ft.Container()

            detail_controls: list[ft.Control] = [
                record_info,
                ft.Divider(),
                ft.Column(controls=list(detail_rows), spacing=2),
                ft.Divider(),
                note_control,
            ]

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("📋 销售明细", weight=ft.FontWeight.BOLD),
                content=ft.Column(
                    controls=detail_controls,
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
        _, _, card_bgcolor, _ = self.get_record_visuals(record)
        if e.data == "true":
            e.control.bgcolor = AppleColors.HOVER_BG
        else:
            e.control.bgcolor = card_bgcolor
        self.page.update()

    def update_stats(self):
        """更新今日统计"""
        today = datetime.now().strftime("%Y-%m-%d")
        summary = self.record_service.summarize_by_date(today)

        sale_qty = summary["sale_quantity"]
        sale_amount = summary["sale_amount"]
        return_qty = summary["return_quantity"]
        return_amount = summary["return_amount"]
        net_qty = summary["net_quantity"]
        net_amount = summary["net_amount"]

        self.stats_text.value = f"""📅 {today}
━━━━━━━━━━━━━━
✅ 销售: {sale_qty}套 ¥{sale_amount:.0f}
🔄 退货: {return_qty}套 ¥{return_amount:.0f}
━━━━━━━━━━━━━━
📦 净额: {net_qty}套 ¥{net_amount:.0f}"""

        self.page.update()

    def show_monthly_stats(self):
        """显示月度统计"""
        month_field = ft.TextField(
            label="月份",
            value=datetime.now().strftime("%Y-%m"),
            hint_text="YYYY-MM",
            border_radius=10,
            bgcolor=AppleColors.BG_SECONDARY,
        )
        result_field = ft.TextField(
            multiline=True,
            min_lines=14,
            max_lines=14,
            read_only=True,
            border_radius=10,
            bgcolor=AppleColors.BG_TERTIARY,
            text_size=12,
        )

        def build_monthly_stats(month_value: str):
            month_records = [
                record
                for record in self.records
                if str(record.get("date", "")).startswith(month_value)
            ]
            if not month_records:
                return f"{month_value} 没有记录"

            sale_records = [
                record
                for record in month_records
                if record.get("type") != "return" and record.get("quantity", 0) > 0
            ]
            return_records = [
                record
                for record in month_records
                if record.get("type") == "return" or record.get("quantity", 0) < 0
            ]
            sale_qty = sum(int(record.get("quantity", 0)) for record in sale_records)
            sale_amount = sum(
                float(record.get("total_amount", 0)) for record in sale_records
            )
            return_qty = sum(
                abs(int(record.get("quantity", 0))) for record in return_records
            )
            return_amount = sum(
                abs(float(record.get("total_amount", 0))) for record in return_records
            )
            net_qty = sale_qty - return_qty
            net_amount = sale_amount - return_amount
            avg_price = sale_amount / sale_qty if sale_qty else 0.0

            daily_stats: dict[str, dict[str, float]] = {}
            for record in month_records:
                date = str(record.get("date", ""))
                daily_stats.setdefault(
                    date,
                    {
                        "qty": 0.0,
                        "amount": 0.0,
                        "return_qty": 0.0,
                        "return_amount": 0.0,
                    },
                )
                if record.get("type") == "return" or int(record.get("quantity", 0)) < 0:
                    daily_stats[date]["return_qty"] += abs(
                        int(record.get("quantity", 0))
                    )
                    daily_stats[date]["return_amount"] += abs(
                        float(record.get("total_amount", 0))
                    )
                else:
                    daily_stats[date]["qty"] += int(record.get("quantity", 0))
                    daily_stats[date]["amount"] += float(record.get("total_amount", 0))

            lines = [
                f"📊 {month_value} 月度统计",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                f"✅ 销售: {sale_qty}套 ¥{sale_amount:.2f}",
                f"🔄 退货: {return_qty}套 ¥{return_amount:.2f}",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                f"📦 净数量: {net_qty} 套",
                f"💵 净金额: ¥{net_amount:.2f}",
                f"💰 平均单价: ¥{avg_price:.2f}",
                f"📝 记录数: {len(month_records)} 条",
                f"📅 有记录天数: {len(daily_stats)} 天",
                "",
                "📈 每日明细:",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
            ]
            for date in sorted(daily_stats.keys()):
                stats = daily_stats[date]
                parts = []
                if stats["qty"] > 0:
                    parts.append(f"售{int(stats['qty'])}套¥{stats['amount']:.0f}")
                if stats["return_qty"] > 0:
                    parts.append(
                        f"退{int(stats['return_qty'])}套¥{stats['return_amount']:.0f}"
                    )
                lines.append(f"{date}: {' | '.join(parts)}")
            return "\n".join(lines)

        def refresh_stats(_: ft.ControlEvent | None = None):
            result_field.value = build_monthly_stats(month_field.value.strip())
            self.page.update()

        result_field.value = build_monthly_stats(month_field.value.strip())
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("📊 月度统计", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    spacing=12,
                    controls=[month_field, result_field],
                ),
            ),
            actions=[
                ft.TextButton("关闭", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("确认查看", on_click=refresh_stats),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def show_settings(self):
        """显示系统设置"""
        info_text = ft.Text(
            f"当前版本: v{VERSION}\n数据文件: {self.data_file}\n记录总数: {len(self.records)} 条",
            color=AppleColors.TEXT_SECONDARY,
        )
        customers_field = ft.TextField(
            label="客户列表（每行一个）",
            value="\n".join(self.get_customer_names()),
            multiline=True,
            min_lines=6,
            max_lines=10,
            border_radius=10,
            bgcolor=AppleColors.BG_TERTIARY,
        )

        def open_data_dir(_=None):
            try:
                os.startfile(self.data_dir)
            except Exception as ex:
                self.show_error(f"打开数据目录失败: {str(ex)}")

        def save_settings(_=None):
            customer_names = [
                line.strip()
                for line in str(customers_field.value or "").splitlines()
                if line.strip()
            ]
            self.save_printer_settings({"customers": customer_names})
            self.page.pop_dialog()
            self.show_success("系统设置已保存")

        settings_controls: list[ft.Control] = [
            info_text,
            customers_field,
            ft.FilledButton("📁 打开数据目录", on_click=open_data_dir),
        ]
        settings_actions: list[ft.Control] = [
            ft.TextButton("关闭", on_click=lambda e: self.page.pop_dialog()),
            ft.TextButton("检查更新", on_click=lambda e: self.check_for_updates()),
            ft.FilledButton("保存客户列表", on_click=save_settings),
        ]

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("⚙️ 系统设置", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=460,
                content=ft.Column(
                    spacing=12,
                    controls=settings_controls,
                ),
            ),
            actions=settings_actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def edit_record(self, record):
        """编辑记录"""
        dlg_item_rows: list[dict[str, Any]] = []
        dlg_items_container = ft.Column(spacing=10)
        note_field = ft.TextField(
            label="备注",
            value=record.get("note", ""),
            multiline=True,
            min_lines=2,
            max_lines=4,
            border_radius=10,
            bgcolor=AppleColors.BG_TERTIARY,
        )
        customer_field = ft.Dropdown(
            label="客户",
            value=record.get("customer", ""),
            options=self.build_customer_options(str(record.get("customer", ""))),
            border_radius=10,
            bgcolor=AppleColors.BG_TERTIARY,
        )
        summary_qty = ft.Text(size=14, weight=ft.FontWeight.W_500)
        summary_total = ft.Text(size=16, weight=ft.FontWeight.BOLD)

        def update_dialog_summary():
            sale_qty = 0
            sale_amount = 0.0
            return_qty = 0
            return_amount = 0.0
            for row in dlg_item_rows:
                try:
                    row_type = row["type_field"].value or "sale"
                    qty = int(row["qty_field"].value or 0)
                    price = float(row["price_field"].value or 0)
                    subtotal = qty * price
                    if row_type == "return":
                        row["subtotal_text"].value = f"-¥{subtotal:.2f}"
                        row["subtotal_text"].color = AppleColors.DANGER
                        return_qty += qty
                        return_amount += subtotal
                    else:
                        row["subtotal_text"].value = f"¥{subtotal:.2f}"
                        row["subtotal_text"].color = AppleColors.TEXT_SECONDARY
                        sale_qty += qty
                        sale_amount += subtotal
                except Exception:
                    row["subtotal_text"].value = "¥0.00"
                    row["subtotal_text"].color = AppleColors.TEXT_SECONDARY
            net_qty = sale_qty - return_qty
            net_amount = sale_amount - return_amount
            summary_qty.value = f"售 {sale_qty}套 / 退 {return_qty}套 / 净 {net_qty}套"
            if net_amount < 0:
                summary_total.value = f"-¥{abs(net_amount):.2f}"
                summary_total.color = AppleColors.DANGER
            else:
                summary_total.value = f"¥{net_amount:.2f}"
                summary_total.color = AppleColors.PRIMARY
            self.page.update()

        def add_edit_row(qty: int = 0, price: float = 0.0, row_type: str = "sale"):
            type_field = ft.Dropdown(
                width=110,
                height=40,
                value=row_type,
                border_radius=8,
                bgcolor=AppleColors.BG_TERTIARY,
                border_color=AppleColors.BORDER,
                focused_border_color=AppleColors.PRIMARY,
                options=[
                    ft.dropdown.Option("sale", "销售"),
                    ft.dropdown.Option("return", "退货"),
                ],
                on_select=lambda _: update_dialog_summary(),
            )
            qty_field = ft.TextField(
                hint_text="数量",
                width=70,
                value=str(qty) if qty else "",
                border_radius=8,
                bgcolor=AppleColors.BG_TERTIARY,
            )
            price_field = ft.TextField(
                hint_text="单价",
                width=90,
                value=f"{price:.2f}" if price else "",
                border_radius=8,
                bgcolor=AppleColors.BG_TERTIARY,
            )
            subtotal_text = ft.Text("¥0.00", width=90)

            def delete_row(_=None):
                if len(dlg_item_rows) > 1:
                    dlg_items_container.controls.remove(row_container)
                    dlg_item_rows.remove(row_data)
                    update_dialog_summary()

            row_controls: list[ft.Control] = [
                type_field,
                qty_field,
                price_field,
                subtotal_text,
                ft.IconButton(
                    icon=ft.Icons.DELETE,
                    icon_color=AppleColors.DANGER,
                    on_click=delete_row,
                ),
            ]

            row_container = ft.Row(
                controls=row_controls,
                spacing=10,
            )
            row_data = {
                "type_field": type_field,
                "qty_field": qty_field,
                "price_field": price_field,
                "subtotal_text": subtotal_text,
                "container": row_container,
            }
            qty_field.on_change = lambda e: update_dialog_summary()
            price_field.on_change = lambda e: update_dialog_summary()
            dlg_item_rows.append(row_data)
            dlg_items_container.controls.append(row_container)
            update_dialog_summary()

        initial_items = record.get("items", []) or [
            {
                "quantity": abs(int(record.get("quantity", 0))),
                "unit_price": float(record.get("unit_price", 0)),
            }
        ]
        for item in initial_items:
            add_edit_row(
                abs(int(item.get("quantity", 0))),
                float(item.get("unit_price", 0)),
                "return" if int(item.get("quantity", 0)) < 0 else "sale",
            )

        def save_changes(_=None):
            try:
                items = []
                for row in dlg_item_rows:
                    qty = int(row["qty_field"].value or 0)
                    price = float(row["price_field"].value or 0)
                    row_type = row["type_field"].value or "sale"
                    if qty > 0 and price > 0:
                        items.append(
                            {
                                "quantity": qty,
                                "unit_price": price,
                                "record_type": row_type,
                            }
                        )
                if not items:
                    self.show_error("请至少保留一个有效商品")
                    return

                self.record_service.update_record(
                    record["id"],
                    items=items,
                    customer=str(customer_field.value or "").strip(),
                    note=note_field.value.strip(),
                )
                self.records = self.record_service.list_records()
                self.mark_record_indexes_dirty()
                self.refresh_display()
                self.page.pop_dialog()
                self.show_success("记录已更新")
            except Exception as ex:
                self.show_error(f"更新失败: {str(ex)}")

        edit_actions: list[ft.Control] = [
            ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
            ft.FilledButton("保存", on_click=save_changes),
        ]

        dlg = ft.AlertDialog(
            title=ft.Text(f"编辑记录 #{record['id']}", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=430,
                content=ft.Column(
                    spacing=10,
                    controls=[
                        ft.Text(
                            f"日期: {record['date']}", color=AppleColors.TEXT_SECONDARY
                        ),
                        dlg_items_container,
                        ft.TextButton("+ 添加商品", on_click=lambda e: add_edit_row()),
                        ft.Row(
                            controls=[
                                summary_qty,
                                ft.Container(expand=True),
                                summary_total,
                            ]
                        ),
                        customer_field,
                        note_field,
                    ],
                ),
            ),
            actions=edit_actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def delete_record(self, record):
        """删除记录"""

        def confirm_delete(e):
            self.record_service.delete_record(record["id"])
            self.records = self.record_service.list_records()
            self.mark_record_indexes_dirty()
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
        dlg_summary_total = ft.Text(
            "¥0.00", size=16, weight=ft.FontWeight.BOLD, color=AppleColors.PRIMARY
        )

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

            subtotal_text = ft.Text(
                "¥0.00", size=14, color=AppleColors.TEXT_SECONDARY, width=80
            )

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

                async def focus_qty_field():
                    await qty_field.focus()

                self.page.run_task(focus_qty_field)

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

                self.record_service.append_items(
                    record["id"],
                    items_to_add,
                    record_type="sale",
                )
                self.records = self.record_service.list_records()
                self.mark_record_indexes_dirty()
                updated_record = next(
                    r for r in self.records if r.get("id") == record.get("id")
                )
                self.refresh_display()
                self.maybe_auto_print(updated_record)
                self.show_success(f"已添加 {total_qty}套，共 ¥{total_amount:.2f}")

            except ValueError:
                self.show_error("请输入有效的数量和单价")

        dlg_content = ft.Column(
            controls=[
                ft.Text(
                    f"记录 #{record['id']} - 当前: {record.get('quantity', 0)}套",
                    size=13,
                    color=AppleColors.TEXT_SECONDARY,
                ),
                ft.Divider(height=5),
                # 表头
                ft.Row(
                    controls=[
                        ft.Text(
                            "数量", size=12, color=AppleColors.TEXT_SECONDARY, width=70
                        ),
                        ft.Text(
                            "单价", size=12, color=AppleColors.TEXT_SECONDARY, width=70
                        ),
                        ft.Text(
                            "小计", size=12, color=AppleColors.TEXT_SECONDARY, width=80
                        ),
                    ],
                    spacing=10,
                ),
                dlg_items_container,
                ft.TextButton(
                    "+ 添加商品",
                    on_click=lambda e: add_dlg_item_row(focus_first=True),
                    style=ft.ButtonStyle(color=AppleColors.PRIMARY),
                ),
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

        cancel_button = ft.TextButton("取消")
        confirm_button = ft.FilledButton(
            "确认添加",
            style=ft.ButtonStyle(
                bgcolor=AppleColors.SUCCESS,
                color=AppleColors.BG_SECONDARY,
            ),
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("添加商品明细", color=AppleColors.SUCCESS),
            content=dlg_content,
            actions=[cancel_button, confirm_button],
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
        cancel_button.on_click = lambda e: (restore_keyboard(), self.page.pop_dialog())
        confirm_button.on_click = do_add_all_with_restore

        self.page.show_dialog(dlg)

        # 弹窗打开后聚焦到第一个输入框
        if dlg_item_rows:

            async def focus_first_add_row():
                await dlg_item_rows[0]["qty_field"].focus()

            self.page.run_task(focus_first_add_row)

    def quick_return(self, record):
        """往原有记录添加退货明细 - 多行模式"""
        print(f"[DEBUG] quick_return called for record {record.get('id')}")

        if record.get("type") == "return" or int(record.get("quantity", 0)) < 0:
            self.show_error("该记录已经是退货记录，无法再退货")
            return

        dlg_item_rows = []  # 弹窗内的商品行
        dlg_items_container = ft.Column(spacing=10)
        dlg_summary_qty = ft.Text("0套", size=14, weight=ft.FontWeight.W_500)
        dlg_summary_total = ft.Text(
            "-¥0.00", size=16, weight=ft.FontWeight.BOLD, color=AppleColors.DANGER
        )

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

            subtotal_text = ft.Text(
                "-¥0.00", size=14, color=AppleColors.DANGER, width=80
            )

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

                async def focus_qty_field():
                    await qty_field.focus()

                self.page.run_task(focus_qty_field)

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
                            items_to_add.append({"quantity": qty, "unit_price": price})
                            total_qty += qty
                            total_amount += qty * price

                if not items_to_add:
                    self.show_error("请至少添加一个有效的退货行")
                    return

                self.page.pop_dialog()

                return_record = self.record_service.create_linked_return(
                    original_record_id=record["id"],
                    items=items_to_add,
                )
                self.records = self.record_service.list_records()
                self.mark_record_indexes_dirty()
                self.refresh_display()
                self.maybe_auto_print(return_record)
                self.show_success(f"已添加退货 {total_qty}套，共 -¥{total_amount:.2f}")

            except ValueError:
                self.show_error("请输入有效的数量和单价")

        dlg_content = ft.Column(
            controls=[
                ft.Text(
                    f"记录 #{record['id']} - 当前: {record.get('quantity', 0)}套, ¥{record.get('total_amount', 0):.2f}",
                    size=13,
                    color=AppleColors.TEXT_SECONDARY,
                ),
                ft.Divider(height=5),
                # 表头
                ft.Row(
                    controls=[
                        ft.Text(
                            "数量", size=12, color=AppleColors.TEXT_SECONDARY, width=70
                        ),
                        ft.Text(
                            "单价", size=12, color=AppleColors.TEXT_SECONDARY, width=70
                        ),
                        ft.Text(
                            "小计", size=12, color=AppleColors.TEXT_SECONDARY, width=80
                        ),
                    ],
                    spacing=10,
                ),
                dlg_items_container,
                ft.TextButton(
                    "+ 添加退货",
                    on_click=lambda e: add_dlg_item_row(focus_first=True),
                    style=ft.ButtonStyle(color=AppleColors.WARNING),
                ),
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

        cancel_button = ft.TextButton("取消")
        confirm_button = ft.FilledButton(
            "确认退货",
            style=ft.ButtonStyle(
                bgcolor=AppleColors.WARNING,
                color=AppleColors.BG_SECONDARY,
            ),
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("添加退货明细", color=AppleColors.WARNING),
            content=dlg_content,
            actions=[cancel_button, confirm_button],
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
        cancel_button.on_click = lambda e: (restore_keyboard(), self.page.pop_dialog())
        confirm_button.on_click = do_return_all_with_restore

        self.page.show_dialog(dlg)

        # 弹窗打开后聚焦到第一个输入框
        if dlg_item_rows:

            async def focus_first_return_row():
                await dlg_item_rows[0]["qty_field"].focus()

            self.page.run_task(focus_first_return_row)

    def show_success(self, message):
        """显示成功提示"""
        print(f"[DEBUG] show_success: {message}")
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=AppleColors.SUCCESS,
            duration=2000,
        )
        self.page.overlay.append(snack)
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
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()


def configure_page(page: ft.Page):
    page.title = "家纺记账系统"
    page.window.width = 1400
    page.window.height = 900

    try:
        page.window.maximized = True
    except Exception:
        pass


def create_app(page: ft.Page) -> AccountingApp:
    return AccountingApp(page)


def main(page: ft.Page):
    configure_page(page)

    try:
        app = create_app(page)
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

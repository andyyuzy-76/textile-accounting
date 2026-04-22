import asyncio
import accounting_flet
from datetime import datetime
from typing import Any, cast


def _control_label(control):
    if hasattr(control, "text"):
        return control.text
    if hasattr(control, "content"):
        if isinstance(control.content, str):
            return control.content
        if hasattr(control.content, "value"):
            return control.content.value
    if hasattr(control, "value"):
        return control.value
    return None


def test_maybe_auto_print_respects_setting():
    app = object.__new__(accounting_flet.AccountingApp)
    calls: list[dict[str, object]] = []
    app.printer_settings = {"auto_print": True}
    app.print_receipt = lambda record: calls.append(record)

    record = {"id": 1}
    accounting_flet.AccountingApp.maybe_auto_print(app, record)

    assert calls == [record]


def test_maybe_auto_print_skips_when_disabled():
    app = object.__new__(accounting_flet.AccountingApp)
    calls: list[dict[str, object]] = []
    app.printer_settings = {"auto_print": False}
    app.print_receipt = lambda record: calls.append(record)

    accounting_flet.AccountingApp.maybe_auto_print(app, {"id": 1})

    assert calls == []


def test_get_receipt_preview_text_uses_settings(monkeypatch):
    class DummyPrinter:
        def __init__(self):
            self.footer_text = ""
            self.applied_settings: dict[str, object] | None = None

        def format_receipt(self, record, compact=True):
            assert self.applied_settings is not None
            return f"compact={compact};shop={self.applied_settings['shop_name']};footer={self.footer_text};id={record['id']}"

    class DummyStore:
        def apply_to_printer(self, printer, settings):
            printer.applied_settings = settings

    monkeypatch.setattr(accounting_flet, "PRINT_AVAILABLE", True)
    monkeypatch.setattr(accounting_flet, "ReceiptPrinterClass", DummyPrinter)

    app = object.__new__(accounting_flet.AccountingApp)
    app.printer_settings_store = cast(
        accounting_flet.PrinterSettingsStore,
        cast(object, DummyStore()),
    )

    preview = accounting_flet.AccountingApp.get_receipt_preview_text(
        app,
        {
            "shop_name": "测试店",
            "footer_text": "欢迎再来",
            "compact_mode": False,
        },
    )

    assert "compact=False" in preview
    assert "shop=测试店" in preview
    assert "footer=欢迎再来" in preview
    assert "id=8888" in preview


def test_get_return_records_filters_related_return_records():
    app = object.__new__(accounting_flet.AccountingApp)
    app.records = [
        {"id": 1, "type": "sale", "quantity": 3},
        {"id": 2, "type": "return", "quantity": -1, "original_record_id": 1},
        {"id": 3, "type": "return", "quantity": -1, "original_record_id": 99},
    ]

    result = accounting_flet.AccountingApp.get_return_records(
        app, {"id": 1, "type": "sale", "quantity": 3}
    )

    assert result == [app.records[1]]


def test_check_for_updates_shows_update_button_when_update_available(monkeypatch):
    class DummyPage:
        def __init__(self):
            self.dialog = None
            self.updated = False

        def show_dialog(self, dlg):
            self.dialog = dlg

        def pop_dialog(self):
            self.dialog = None

        def run_task(self, fn):
            import asyncio

            asyncio.run(fn())

        def update(self):
            self.updated = True

    monkeypatch.setattr(
        accounting_flet,
        "check_updates_fn",
        lambda silent=False: (True, "9.9.9", "1.0.0", "新版本说明"),
    )
    monkeypatch.setattr(
        accounting_flet, "perform_update_fn", lambda: (True, "更新成功")
    )

    app = object.__new__(accounting_flet.AccountingApp)
    page = DummyPage()
    app.page = cast(accounting_flet.ft.Page, cast(object, page))
    app.show_success = lambda message: None
    app.show_error = lambda message: None

    accounting_flet.AccountingApp.check_for_updates(app)

    assert page.dialog is not None
    assert page.dialog.actions[1].visible is True
    assert "9.9.9" in page.dialog.content.content.controls[0].value


def test_check_for_updates_shows_pending_release_message_without_update_button(
    monkeypatch,
):
    class DummyPage:
        def __init__(self):
            self.dialog = None
            self.updated = False

        def show_dialog(self, dlg):
            self.dialog = dlg

        def pop_dialog(self):
            self.dialog = None

        def run_task(self, fn):
            import asyncio

            asyncio.run(fn())

        def update(self):
            self.updated = True

    monkeypatch.setattr(
        accounting_flet,
        "check_updates_fn",
        lambda silent=False: (
            False,
            "1.15.2",
            "1.15.1",
            "检测到新版本 v1.15.2，但更新包尚未发布，请稍后再试。",
        ),
    )

    app = object.__new__(accounting_flet.AccountingApp)
    page = DummyPage()
    app.page = cast(accounting_flet.ft.Page, cast(object, page))
    app.show_success = lambda message: None
    app.show_error = lambda message: None

    accounting_flet.AccountingApp.check_for_updates(app)

    assert page.dialog is not None
    assert page.dialog.actions[1].visible is False
    assert "尚未发布" in page.dialog.content.content.controls[0].value


def test_check_for_updates_shows_progress_feedback_during_update(monkeypatch):
    class DummyPage:
        def __init__(self):
            self.dialog = None
            self.updated = False

        def show_dialog(self, dlg):
            self.dialog = dlg

        def pop_dialog(self):
            self.dialog = None

        def run_task(self, fn):
            import asyncio

            asyncio.run(fn())

        def update(self):
            self.updated = True

    monkeypatch.setattr(
        accounting_flet,
        "check_updates_fn",
        lambda silent=False: (True, "1.15.5", "1.15.4", "新版本说明"),
    )

    progress_messages = []

    def fake_perform_update(callback=None):
        assert callback is not None
        callback("正在下载软件更新包...")
        callback("正在校验更新包...")
        callback("正在应用更新...")
        callback("正在重启程序...")
        progress_messages.append("done")
        return True, "更新成功"

    monkeypatch.setattr(accounting_flet, "perform_update_fn", fake_perform_update)

    app = object.__new__(accounting_flet.AccountingApp)
    page = DummyPage()
    app.page = cast(accounting_flet.ft.Page, cast(object, page))
    success_messages: list[str] = []
    error_messages: list[str] = []
    app.show_success = success_messages.append
    app.show_error = error_messages.append

    accounting_flet.AccountingApp.check_for_updates(app)

    assert page.dialog is not None
    run_update_button = page.dialog.actions[1]
    assert run_update_button.visible is True

    run_update_button.on_click(None)

    dialog_column = page.dialog.content.content
    update_status = dialog_column.controls[0]
    update_progress = dialog_column.controls[1]
    update_hint = dialog_column.controls[2]

    assert progress_messages == ["done"]
    assert success_messages == ["更新成功"]
    assert error_messages == []
    assert "正在重启程序..." in update_status.value
    assert update_progress.visible is True
    assert update_progress.value == 1.0
    assert "请勿关闭程序" in update_hint.value


def test_show_receipt_preview_opens_dialog(monkeypatch):
    class DummyPrinter:
        def format_receipt(self, record, compact=True, return_records=None):
            return f"receipt-{record['id']}-{compact}"

    class DummyPage:
        def __init__(self):
            self.dialog = None

        def show_dialog(self, dlg):
            self.dialog = dlg

        def pop_dialog(self):
            self.dialog = None

    app = object.__new__(accounting_flet.AccountingApp)
    page = DummyPage()
    app.page = cast(accounting_flet.ft.Page, cast(object, page))
    app.receipt_printer = cast(Any, DummyPrinter())
    app.printer_settings = {"compact_mode": True}
    app.get_return_records = lambda record: []
    app.show_error = lambda message: None

    monkeypatch.setattr(accounting_flet, "PRINT_AVAILABLE", True)

    accounting_flet.AccountingApp.show_receipt_preview(app, {"id": 12})

    assert page.dialog is not None
    preview_field = page.dialog.content.content.controls[0]
    assert preview_field.value == "receipt-12-True"


def test_get_record_kind_and_visuals_support_mixed_records():
    app = object.__new__(accounting_flet.AccountingApp)

    kind = accounting_flet.AccountingApp.get_record_kind(
        app,
        {"type": "mixed", "quantity": 2, "total_amount": 200.0},
    )
    visuals = accounting_flet.AccountingApp.get_record_visuals(
        app,
        {"type": "mixed", "quantity": 2, "total_amount": 200.0},
    )

    assert kind == "mixed"
    assert visuals[0] == "混合"


def test_get_record_visuals_keeps_customer_outside_type_judgement():
    app = object.__new__(accounting_flet.AccountingApp)

    kind = accounting_flet.AccountingApp.get_record_kind(
        app,
        {"type": "sale", "customer": "张女士", "quantity": 2},
    )

    assert kind == "sale"


def test_build_customer_options_uses_saved_customer_list():
    app = object.__new__(accounting_flet.AccountingApp)
    app.printer_settings = {"customers": ["张女士", "李老板"]}

    options = accounting_flet.AccountingApp.build_customer_options(app)

    assert [option.key for option in options] == ["", "张女士", "李老板"]


def test_show_selected_date_records_filters_exact_date():
    app = object.__new__(accounting_flet.AccountingApp)
    app.records = [
        {"date": "2026-04-21", "id": 1},
        {"date": "2026-04-22", "id": 2},
    ]
    app.filter_date_field = cast(
        accounting_flet.ft.TextField,
        cast(object, type("Field", (), {"value": "2026-04-21"})()),
    )

    captured = {}
    app.display_records = lambda records: captured.setdefault("records", records)
    app.show_error = lambda message: captured.setdefault("error", message)

    accounting_flet.AccountingApp.show_selected_date_records(app)

    assert captured["records"] == [{"date": "2026-04-21", "id": 1}]


def test_show_month_records_updates_scope_text_and_filters_current_month(
    monkeypatch,
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 22)

    monkeypatch.setattr(accounting_flet, "datetime", FixedDateTime)

    app = object.__new__(accounting_flet.AccountingApp)
    app.records = [
        {"date": "2026-04-21", "id": 1},
        {"date": "2026-04-01", "id": 2},
        {"date": "2026-03-31", "id": 3},
    ]
    app.records_scope_text = cast(
        accounting_flet.ft.Text,
        cast(object, type("Label", (), {"value": ""})()),
    )

    captured = {}
    app.display_records = lambda records, empty_message=None: captured.setdefault(
        "records", records
    )

    accounting_flet.AccountingApp.show_month_records(app)

    assert captured["records"] == [
        {"date": "2026-04-21", "id": 1},
        {"date": "2026-04-01", "id": 2},
    ]
    assert "本月" in app.records_scope_text.value
    assert "2 条" in app.records_scope_text.value


def test_show_year_records_updates_scope_text_and_filters_current_year(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 22)

    monkeypatch.setattr(accounting_flet, "datetime", FixedDateTime)

    app = object.__new__(accounting_flet.AccountingApp)
    app.records = [
        {"date": "2026-04-21", "id": 1},
        {"date": "2026-01-15", "id": 2},
        {"date": "2025-12-31", "id": 3},
    ]
    app.records_scope_text = cast(
        accounting_flet.ft.Text,
        cast(object, type("Label", (), {"value": ""})()),
    )

    captured = {}
    app.display_records = lambda records, empty_message=None: captured.setdefault(
        "records", records
    )

    accounting_flet.AccountingApp.show_year_records(app)

    assert captured["records"] == [
        {"date": "2026-04-21", "id": 1},
        {"date": "2026-01-15", "id": 2},
    ]
    assert "本年" in app.records_scope_text.value
    assert "2 条" in app.records_scope_text.value


def test_display_records_shows_empty_state_when_no_records():
    class DummyPage:
        def __init__(self):
            self.updated = False

        def update(self):
            self.updated = True

    app = object.__new__(accounting_flet.AccountingApp)
    app.page = cast(accounting_flet.ft.Page, cast(object, DummyPage()))
    app.records_list = accounting_flet.ft.Column()
    app.total_label = accounting_flet.ft.Text()

    accounting_flet.AccountingApp.display_records(app, [], "2026-04 没有记录")

    assert len(app.records_list.controls) == 1
    assert app.total_label.value == "¥0.00"
    assert cast(Any, app.page).updated is True


def test_display_records_puts_newer_same_day_records_on_top():
    class DummyPage:
        def __init__(self):
            self.updated = False

        def update(self):
            self.updated = True

    app = object.__new__(accounting_flet.AccountingApp)
    app.page = cast(accounting_flet.ft.Page, cast(object, DummyPage()))
    app.records_list = accounting_flet.ft.Column()
    app.total_label = accounting_flet.ft.Text()
    app.create_record_card = lambda record: accounting_flet.ft.Text(str(record["id"]))

    accounting_flet.AccountingApp.display_records(
        app,
        [
            {
                "id": 1,
                "date": "2026-04-22",
                "created_at": "2026-04-22 10:00:00",
                "total_amount": 100.0,
            },
            {
                "id": 2,
                "date": "2026-04-22",
                "created_at": "2026-04-22 10:00:01",
                "total_amount": 200.0,
            },
            {
                "id": 3,
                "date": "2026-04-22",
                "created_at": "2026-04-22 10:00:01",
                "total_amount": 300.0,
            },
            {
                "id": 4,
                "date": "2026-04-21",
                "created_at": "2026-04-21 23:59:59",
                "total_amount": 400.0,
            },
        ],
    )

    assert [control.value for control in app.records_list.controls] == [
        "3",
        "2",
        "1",
        "4",
    ]


def test_ctrl_enter_submit_does_not_leave_extra_blank_item_row():
    class DummyPage:
        def __init__(self):
            self.updated = False

        def update(self):
            self.updated = True

    class DummyRecordService:
        def add_record(self, **kwargs):
            return {
                "id": 99,
                "date": "2026-04-22",
                "total_amount": 100.0,
                "type": "sale",
            }

        def list_records(self):
            return []

    app = object.__new__(accounting_flet.AccountingApp)
    app.page = cast(accounting_flet.ft.Page, cast(object, DummyPage()))
    app.item_rows = []
    app.items_container = accounting_flet.ft.Column()
    app.summary_qty = accounting_flet.ft.Text()
    app.summary_total = accounting_flet.ft.Text()
    app.customer_field = accounting_flet.ft.Dropdown(options=[])
    app.note_field = accounting_flet.ft.TextField()
    app.date_field = accounting_flet.ft.TextField(value="2026-04-22")
    app.record_service = cast(Any, DummyRecordService())
    app.records = []
    app.printer_settings = {"auto_print": False}
    app.show_success = lambda message: None
    app.show_error = lambda message: None
    app.refresh_display = lambda: None
    app.maybe_auto_print = lambda record: None

    accounting_flet.AccountingApp.add_item_row(app)
    app.item_rows[0]["qty_field"].value = "1"
    app.item_rows[0]["price_field"].value = "100"

    accounting_flet.AccountingApp.handle_main_form_keyboard(
        app,
        cast(
            Any,
            type("KeyboardEvent", (), {"key": "Enter", "ctrl": True})(),
        ),
    )
    asyncio.run(app.item_rows[0]["price_field"].on_submit(None))

    assert len(app.item_rows) == 1


def test_create_input_panel_keeps_actions_outside_scrollable_form():
    class DummyPage:
        def __init__(self):
            self.updated = False

        def update(self):
            self.updated = True

    app = object.__new__(accounting_flet.AccountingApp)
    app.page = cast(accounting_flet.ft.Page, cast(object, DummyPage()))
    app.printer_settings = {"customers": []}
    app.item_rows = []
    app.add_item_row = lambda: None

    panel = accounting_flet.AccountingApp.create_input_panel(app)

    card_container = panel.content.controls[0]
    card_content = card_container.content
    scroll_section = card_content.controls[0]
    action_bar = card_content.controls[-1]

    assert isinstance(scroll_section, accounting_flet.ft.Container)
    assert isinstance(scroll_section.content, accounting_flet.ft.Column)
    assert scroll_section.content.scroll == accounting_flet.ft.ScrollMode.AUTO
    assert isinstance(action_bar, accounting_flet.ft.Row)
    assert [_control_label(control) for control in action_bar.controls] == [
        "✅ 添加记录",
        "清空表单",
    ]

    scroll_texts = [
        _control_label(control)
        for control in scroll_section.content.controls
        if _control_label(control)
    ]
    assert "✅ 添加记录" not in scroll_texts


def test_create_records_panel_uses_list_view_for_long_record_lists():
    class DummyPage:
        def __init__(self):
            self.updated = False

        def update(self):
            self.updated = True

    app = object.__new__(accounting_flet.AccountingApp)
    app.page = cast(accounting_flet.ft.Page, cast(object, DummyPage()))

    panel = accounting_flet.AccountingApp.create_records_panel(app)

    assert isinstance(app.records_list, accounting_flet.ft.ListView)
    assert panel.content.controls[3].content is app.records_list

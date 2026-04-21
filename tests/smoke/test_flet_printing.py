import accounting_flet
from typing import Any, cast


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
    assert "9.9.9" in page.dialog.content.content.value


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

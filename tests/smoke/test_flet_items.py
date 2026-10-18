import pytest

import accounting_flet as ui
from app_core.services.records import RecordService
from app_core.storage import JsonStore


class DummyPage:
    def update(self):
        pass

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.dialog = None


@pytest.fixture
def app(tmp_path):
    app = object.__new__(ui.AccountingApp)
    app.page = DummyPage()
    app.item_rows = []
    app.items_container = ui.ft.Column()
    app.summary_qty = ui.ft.Text()
    app.summary_total = ui.ft.Text()
    app.customer_field = ui.ft.Dropdown()
    app.note_field = ui.ft.TextField()
    app.date_field = ui.ft.TextField(value="2026-10-18")
    app.printer_settings = {"auto_print": False, "customers": []}
    app.record_service = RecordService(JsonStore(tmp_path / "records.json"))
    app.refresh_display = lambda: None
    app.show_success = lambda message: None
    app.show_error = pytest.fail
    return app


def test_item_type_click_toggles_and_saves_mixed_rows_then_resets(app):
    for qty, price in [(2, 100), (1, 50)]:
        app.add_item_row()
        app.item_rows[-1]["qty_field"].value = str(qty)
        app.item_rows[-1]["price_field"].value = str(price)
    first, second = app.item_rows
    button = first["type_field"]
    assert isinstance(button, ui.ft.OutlinedButton)
    assert (button.data, button.content) == ("sale", "销售")

    for kind, label, subtotal, total in [
        ("return", "退货", "-¥200.00", "-¥150.00"),
        ("sale", "销售", "¥200.00", "¥250.00"),
        ("return", "退货", "-¥200.00", "-¥150.00"),
    ]:
        button.on_click(None)
        assert (button.data, button.content) == (kind, label)
        assert first["subtotal_text"].value == subtotal
        assert app.summary_total.value == total
        assert second["type_field"].data == "sale"

    app.add_record()
    saved = app.record_service.list_records()[0]
    assert saved["type"] == "mixed"
    assert saved["total_amount"] == -150
    assert [item["quantity"] for item in saved["items"]] == [-2, 1]
    assert len(app.item_rows) == 1
    assert (button.data, button.content) == ("sale", "销售")
    assert app.summary_total.value == "¥0.00"
    button.on_click(None)
    assert (button.data, button.content) == ("return", "退货")
    app._ctrl_enter_submit_pending = True
    assert app.should_skip_price_submit_after_ctrl_enter() is False
    app.clear_form()
    app._ctrl_enter_submit_pending = True
    assert app.should_skip_price_submit_after_ctrl_enter() is True


@pytest.mark.parametrize("initial_type", ["sale", "return"])
def test_edit_item_type_keeps_initial_value_and_saves_toggled_type(app, initial_type):
    record = app.record_service.add_record(
        date="2026-10-18",
        items=[{"quantity": 2, "unit_price": 100}],
        record_type=initial_type,
    )
    app.edit_record(record)
    dialog = app.page.dialog
    controls = dialog.content.content.controls
    button = controls[1].controls[0].controls[0]
    assert isinstance(button, ui.ft.OutlinedButton)
    assert button.data == initial_type

    button.on_click(None)
    is_return = initial_type == "sale"
    assert button.content == ("退货" if is_return else "销售")
    assert controls[3].controls[-1].value == ("-¥200.00" if is_return else "¥200.00")
    dialog.actions[1].on_click(None)
    saved = app.record_service.list_records()[0]
    assert saved["type"] == ("return" if is_return else "sale")
    assert saved["quantity"] == (-2 if is_return else 2)
    assert saved["total_amount"] == (-200 if is_return else 200)

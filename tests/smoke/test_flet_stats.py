import pytest

import accounting_flet as ui
from app_core.services.records import RecordService
from app_core.storage import JsonStore


class DummyPage:
    def update(self):
        pass

    def show_dialog(self, dialog):
        self.dialog = dialog


@pytest.fixture
def app(tmp_path):
    instance = object.__new__(ui.AccountingApp)
    instance.page = DummyPage()
    instance.record_service = RecordService(JsonStore(tmp_path / "records.json"))
    return instance


def show_report(app, month):
    app.records = app.record_service.list_records()
    app.show_monthly_stats()
    dialog = app.page.dialog
    month_field, result_field = dialog.content.content.controls
    month_field.value = month
    dialog.actions[1].on_click(None)
    return result_field.value


@pytest.mark.parametrize(
    ("sale_qty", "sale_price", "return_qty", "return_price"),
    [
        (3, 100, 1, 80),
        (1, 80, 3, 100),
        (2, 100, 2, 100),
        (2, 100, 2, 50),
    ],
    ids=["net-sale", "net-return", "zero-net", "zero-quantity-different-prices"],
)
def test_monthly_report_splits_mixed_items(
    app, sale_qty, sale_price, return_qty, return_price
):
    app.record_service.add_record(
        date="2026-04-21",
        items=[
            {"quantity": sale_qty, "unit_price": sale_price, "record_type": "sale"},
            {"quantity": return_qty, "unit_price": return_price, "record_type": "return"},
        ],
        record_type="mixed",
    )

    report = show_report(app, "2026-04")
    sale_amount = sale_qty * sale_price
    return_amount = return_qty * return_price

    assert f"✅ 销售: {sale_qty}套 ¥{sale_amount:.2f}" in report
    assert f"🔄 退货: {return_qty}套 ¥{return_amount:.2f}" in report
    assert f"📦 净数量: {sale_qty - return_qty} 套" in report
    assert f"💵 净金额: ¥{sale_amount - return_amount:.2f}" in report
    assert f"💰 平均单价: ¥{sale_price:.2f}" in report
    assert "📝 记录数: 1 条" in report
    assert "📅 有记录天数: 1 天" in report
    assert (
        f"2026-04-21: 售{sale_qty}套¥{sale_amount:.0f} | "
        f"退{return_qty}套¥{return_amount:.0f}"
    ) in report


def test_monthly_report_aggregates_days_and_legacy_records(app):
    app.record_service.replace_records(
        [
            {"id": 1, "date": "2026-04-22", "quantity": 2, "total_amount": 120.0},
            {"id": 2, "date": "2026-04-21", "quantity": -1, "total_amount": -80.0},
            {"id": 3, "date": "2026-04-22", "quantity": 1, "total_amount": 60.0},
            {"id": 4, "date": "2026-05-01", "quantity": 10, "total_amount": 1000.0},
            {"id": 5, "date": "2025-04-21", "quantity": 10, "total_amount": 1000.0},
        ]
    )

    report = show_report(app, "2026-04")

    assert "✅ 销售: 3套 ¥180.00" in report
    assert "🔄 退货: 1套 ¥80.00" in report
    assert "📦 净数量: 2 套" in report
    assert "💵 净金额: ¥100.00" in report
    assert "💰 平均单价: ¥60.00" in report
    assert "📝 记录数: 3 条" in report
    assert "📅 有记录天数: 2 天" in report
    assert "2026-04-21: 退1套¥80" in report
    assert "2026-04-22: 售3套¥180" in report
    assert report.index("2026-04-21:") < report.index("2026-04-22:")
    assert "2026-05-01" not in report
    assert "2025-04-21" not in report


def test_monthly_report_with_only_returns_has_zero_average(app):
    app.record_service.add_record(
        date="2026-04-21",
        items=[{"quantity": 2, "unit_price": 80}],
        record_type="return",
    )

    report = show_report(app, "2026-04")

    assert "✅ 销售: 0套 ¥0.00" in report
    assert "🔄 退货: 2套 ¥160.00" in report
    assert "💵 净金额: ¥-160.00" in report
    assert "💰 平均单价: ¥0.00" in report


def test_monthly_report_can_switch_to_empty_month(app):
    app.record_service.add_record(
        date="2026-04-21", items=[{"quantity": 1, "unit_price": 100}]
    )
    assert "销售: 1套" in show_report(app, "2026-04")
    dialog = app.page.dialog
    month_field, result_field = dialog.content.content.controls

    month_field.value = "2026-05"
    dialog.actions[1].on_click(None)

    assert result_field.value == "2026-05 没有记录"

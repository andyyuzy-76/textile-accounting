from app_core.services.records import RecordService
from app_core.storage import JsonStore


def test_add_sale_record_computes_total_and_persists(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))

    result = service.add_record(
        date="2026-04-21",
        items=[{"quantity": 2, "unit_price": 99.0}],
        note="A",
    )

    assert result["total_amount"] == 198.0
    assert service.list_records()[0]["note"] == "A"


def test_return_record_normalizes_negative_values(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))

    result = service.add_record(
        date="2026-04-21",
        items=[{"quantity": 1, "unit_price": 100.0}],
        note="客户退货",
        record_type="return",
    )

    assert result["quantity"] == -1
    assert result["total_amount"] == -100.0
    assert result["note"].startswith("[退货]")


def test_summary_uses_filtered_records(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    service.add_record(date="2026-04-21", items=[{"quantity": 1, "unit_price": 100.0}], note="A")
    service.add_record(date="2026-04-22", items=[{"quantity": 2, "unit_price": 50.0}], note="B")

    summary = service.summarize_by_date("2026-04-21")

    assert summary["sale_quantity"] == 1
    assert summary["sale_amount"] == 100.0
    assert summary["net_amount"] == 100.0


def test_update_note_and_delete_record(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    record = service.add_record(date="2026-04-21", items=[{"quantity": 1, "unit_price": 88.0}], note="旧备注")

    updated = service.update_note(record["id"], "新备注")

    assert updated["note"] == "新备注"
    assert service.delete_record(record["id"]) is True
    assert service.list_records() == []

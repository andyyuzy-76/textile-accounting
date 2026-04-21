from app_core.services.records import RecordService
from app_core.storage import JsonStore


def test_add_sale_record_computes_total_and_persists(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))

    result = service.add_record(
        date="2026-04-21",
        items=[{"quantity": 2, "unit_price": 99.0}],
        customer="张女士",
        note="A",
    )

    assert result["total_amount"] == 198.0
    assert result["customer"] == "张女士"
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
    service.add_record(
        date="2026-04-21", items=[{"quantity": 1, "unit_price": 100.0}], note="A"
    )
    service.add_record(
        date="2026-04-22", items=[{"quantity": 2, "unit_price": 50.0}], note="B"
    )

    summary = service.summarize_by_date("2026-04-21")

    assert summary["sale_quantity"] == 1
    assert summary["sale_amount"] == 100.0
    assert summary["net_amount"] == 100.0


def test_update_note_and_delete_record(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    record = service.add_record(
        date="2026-04-21", items=[{"quantity": 1, "unit_price": 88.0}], note="旧备注"
    )

    updated = service.update_note(record["id"], "新备注")

    assert updated["note"] == "新备注"
    assert service.delete_record(record["id"]) is True
    assert service.list_records() == []


def test_append_items_updates_sale_record_totals(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    record = service.add_record(
        date="2026-04-21",
        items=[{"quantity": 1, "unit_price": 88.0}],
        note="首单",
    )

    updated = service.append_items(
        record["id"],
        [{"quantity": 2, "unit_price": 50.0}],
        record_type="sale",
    )

    assert updated["quantity"] == 3
    assert updated["total_amount"] == 188.0
    assert updated["unit_price"] == 188.0 / 3
    assert len(updated["items"]) == 2


def test_append_items_updates_return_totals_without_changing_record_identity(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    record = service.add_record(
        date="2026-04-21",
        items=[{"quantity": 3, "unit_price": 100.0}],
        note="首单",
    )

    updated = service.append_items(
        record["id"],
        [{"quantity": 1, "unit_price": 100.0}],
        record_type="return",
    )

    assert updated["id"] == record["id"]
    assert updated["type"] == "sale"
    assert updated["quantity"] == 2
    assert updated["total_amount"] == 200.0
    assert updated["unit_price"] == 100.0
    assert updated["items"][-1]["quantity"] == -1


def test_update_record_recalculates_totals_and_note(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    record = service.add_record(
        date="2026-04-21",
        items=[{"quantity": 1, "unit_price": 80.0}],
        note="旧备注",
    )

    updated = service.update_record(
        record["id"],
        items=[
            {"quantity": 2, "unit_price": 50.0},
            {"quantity": 1, "unit_price": 120.0},
        ],
        customer="李女士",
        note="新备注",
    )

    assert updated["quantity"] == 3
    assert updated["total_amount"] == 220.0
    assert updated["unit_price"] == 220.0 / 3
    assert updated["customer"] == "李女士"
    assert updated["note"] == "新备注"


def test_create_linked_return_creates_separate_return_record(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    sale = service.add_record(
        date="2026-04-21",
        items=[{"quantity": 3, "unit_price": 100.0}],
        note="原销售",
    )

    created = service.create_linked_return(
        original_record_id=sale["id"],
        items=[{"quantity": 1, "unit_price": 100.0}],
    )

    assert created["type"] == "return"
    assert created["quantity"] == -1
    assert created["total_amount"] == -100.0
    assert created["original_record_id"] == sale["id"]
    assert "原记录#" in created["note"]


def test_create_linked_return_rejects_excess_quantity(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    sale = service.add_record(
        date="2026-04-21",
        items=[{"quantity": 1, "unit_price": 100.0}],
        note="原销售",
    )

    try:
        service.create_linked_return(
            original_record_id=sale["id"],
            items=[{"quantity": 2, "unit_price": 100.0}],
        )
    except ValueError as exc:
        assert "exceeds" in str(exc)
    else:
        raise AssertionError("Expected ValueError for excessive return quantity")


def test_add_record_supports_mixed_sale_and_return_items(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))

    result = service.add_record(
        date="2026-04-21",
        items=[
            {"quantity": 3, "unit_price": 100.0, "record_type": "sale"},
            {"quantity": 1, "unit_price": 100.0, "record_type": "return"},
        ],
        note="混合单",
        record_type="mixed",
    )

    assert result["type"] == "mixed"
    assert result["quantity"] == 2
    assert result["total_amount"] == 200.0
    assert [item["quantity"] for item in result["items"]] == [3, -1]


def test_summary_counts_mixed_record_sale_and_return_separately(tmp_path):
    service = RecordService(JsonStore(tmp_path / "records.json"))
    service.add_record(
        date="2026-04-21",
        items=[
            {"quantity": 3, "unit_price": 100.0, "record_type": "sale"},
            {"quantity": 1, "unit_price": 100.0, "record_type": "return"},
        ],
        note="混合单",
        record_type="mixed",
    )

    summary = service.summarize_by_date("2026-04-21")

    assert summary["sale_quantity"] == 3
    assert summary["sale_amount"] == 300.0
    assert summary["return_quantity"] == 1
    assert summary["return_amount"] == 100.0
    assert summary["net_quantity"] == 2
    assert summary["net_amount"] == 200.0

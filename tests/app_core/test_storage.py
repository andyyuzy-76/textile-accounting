from app_core.storage import JsonStore


def test_json_store_returns_empty_list_for_missing_file(tmp_path):
    store = JsonStore(tmp_path / "records.json")
    assert store.load_list() == []


def test_json_store_round_trips_records(tmp_path):
    store = JsonStore(tmp_path / "records.json")
    records = [{"id": 1, "date": "2026-04-21", "quantity": 2, "unit_price": 100.0, "total_amount": 200.0}]
    store.save_list(records)
    assert store.load_list() == records

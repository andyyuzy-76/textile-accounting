from app_core.storage import JsonStore
from pathlib import Path

import pytest


def test_json_store_returns_empty_list_for_missing_file(tmp_path):
    store = JsonStore(tmp_path / "records.json")
    assert store.load_list() == []


def test_json_store_round_trips_records(tmp_path):
    store = JsonStore(tmp_path / "records.json")
    records = [{"id": 1, "date": "2026-04-21", "quantity": 2, "unit_price": 100.0, "total_amount": 200.0}]
    store.save_list(records)
    assert store.load_list() == records


def test_save_callback_runs_only_after_successful_write(tmp_path, monkeypatch):
    calls = []
    store = JsonStore(tmp_path / "records.json", on_save=lambda: calls.append(store.load_list()))
    store.save_list([{"id": 1}])
    assert calls == [[{"id": 1}]]

    def fail_replace(*args):
        raise OSError("simulated write failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        store.save_list([{"id": 2}])
    assert calls == [[{"id": 1}]]

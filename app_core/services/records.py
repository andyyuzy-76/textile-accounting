from __future__ import annotations

from datetime import datetime
from typing import Any

from app_core.storage import JsonStore


class RecordService:
    def __init__(self, store: JsonStore):
        self.store = store
        self._records = self.store.load_list()

    def reload(self) -> list[dict[str, Any]]:
        self._records = self.store.load_list()
        return self.list_records()

    def list_records(self) -> list[dict[str, Any]]:
        return list(self._records)

    def replace_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._records = list(records)
        self.store.save_list(self._records)
        return self.list_records()

    def add_record(
        self,
        *,
        date: str,
        items: list[dict[str, Any]],
        note: str = "",
        record_type: str = "sale",
    ) -> dict[str, Any]:
        datetime.strptime(date, "%Y-%m-%d")
        normalized_items = self._normalize_items(items, record_type)
        if not normalized_items:
            raise ValueError("items must not be empty")

        total_quantity = sum(int(item["quantity"]) for item in normalized_items)
        total_amount = sum(float(item["quantity"]) * float(item["unit_price"]) for item in normalized_items)
        average_price = abs(total_amount) / abs(total_quantity) if total_quantity else 0.0

        normalized_note = note.strip()
        if record_type == "return":
            normalized_note = f"[退货] {normalized_note}".strip() if normalized_note else "[退货]"

        record = {
            "id": max((int(record.get("id", 0)) for record in self._records), default=0) + 1,
            "date": date,
            "quantity": total_quantity,
            "unit_price": average_price,
            "total_amount": total_amount,
            "note": normalized_note,
            "type": record_type,
            "items": normalized_items,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._records.append(record)
        self.store.save_list(self._records)
        return record

    def update_note(self, record_id: int, note: str) -> dict[str, Any]:
        for record in self._records:
            if int(record.get("id", 0)) == record_id:
                record["note"] = note
                self.store.save_list(self._records)
                return record
        raise KeyError(f"record {record_id} not found")

    def delete_record(self, record_id: int) -> bool:
        original_length = len(self._records)
        self._records = [record for record in self._records if int(record.get("id", 0)) != record_id]
        if len(self._records) == original_length:
            return False
        self.store.save_list(self._records)
        return True

    def summarize_by_date(self, date: str) -> dict[str, Any]:
        selected = [record for record in self._records if record.get("date") == date]
        sale_records = [record for record in selected if record.get("type") != "return" and record.get("quantity", 0) > 0]
        return_records = [record for record in selected if record.get("type") == "return" or record.get("quantity", 0) < 0]

        sale_quantity = sum(int(record.get("quantity", 0)) for record in sale_records)
        sale_amount = sum(float(record.get("total_amount", 0)) for record in sale_records)
        return_quantity = sum(abs(int(record.get("quantity", 0))) for record in return_records)
        return_amount = sum(abs(float(record.get("total_amount", 0))) for record in return_records)

        return {
            "sale_quantity": sale_quantity,
            "sale_amount": sale_amount,
            "return_quantity": return_quantity,
            "return_amount": return_amount,
            "net_quantity": sale_quantity - return_quantity,
            "net_amount": sale_amount - return_amount,
        }

    def _normalize_items(self, items: list[dict[str, Any]], record_type: str) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in items:
            quantity = int(item["quantity"])
            unit_price = float(item["unit_price"])
            if quantity <= 0 or unit_price <= 0:
                continue
            normalized_quantity = -quantity if record_type == "return" else quantity
            normalized.append({"quantity": normalized_quantity, "unit_price": unit_price})
        return normalized

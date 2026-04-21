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
        customer: str = "",
        note: str = "",
        record_type: str = "sale",
    ) -> dict[str, Any]:
        datetime.strptime(date, "%Y-%m-%d")
        normalized_items = self._normalize_items(items, record_type)
        if not normalized_items:
            raise ValueError("items must not be empty")

        total_quantity = sum(int(item["quantity"]) for item in normalized_items)
        total_amount = sum(
            float(item["quantity"]) * float(item["unit_price"])
            for item in normalized_items
        )
        average_price = (
            abs(total_amount) / abs(total_quantity) if total_quantity else 0.0
        )

        effective_type = self._derive_record_type(normalized_items, record_type)

        normalized_note = note.strip()
        if effective_type == "return":
            normalized_note = (
                f"[退货] {normalized_note}".strip() if normalized_note else "[退货]"
            )

        record = {
            "id": max((int(record.get("id", 0)) for record in self._records), default=0)
            + 1,
            "date": date,
            "customer": customer.strip(),
            "quantity": total_quantity,
            "unit_price": average_price,
            "total_amount": total_amount,
            "note": normalized_note,
            "type": effective_type,
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

    def update_record(
        self,
        record_id: int,
        *,
        items: list[dict[str, Any]],
        customer: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        for record in self._records:
            if int(record.get("id", 0)) != record_id:
                continue

            record_type = str(record.get("type", "sale"))
            normalized_items = self._normalize_items(items, record_type)
            if not normalized_items:
                raise ValueError("items must not be empty")

            total_quantity = sum(int(item["quantity"]) for item in normalized_items)
            total_amount = sum(
                float(item["quantity"]) * float(item["unit_price"])
                for item in normalized_items
            )

            effective_type = self._derive_record_type(normalized_items, record_type)
            record["items"] = normalized_items
            record["customer"] = customer.strip()
            record["quantity"] = total_quantity
            record["total_amount"] = total_amount
            record["unit_price"] = (
                abs(total_amount / total_quantity) if total_quantity else 0.0
            )
            record["type"] = effective_type
            record["note"] = note.strip()
            self.store.save_list(self._records)
            return record

        raise KeyError(f"record {record_id} not found")

    def delete_record(self, record_id: int) -> bool:
        original_length = len(self._records)
        self._records = [
            record for record in self._records if int(record.get("id", 0)) != record_id
        ]
        if len(self._records) == original_length:
            return False
        self.store.save_list(self._records)
        return True

    def append_items(
        self,
        record_id: int,
        items: list[dict[str, Any]],
        *,
        record_type: str = "sale",
    ) -> dict[str, Any]:
        normalized_items = self._normalize_items(items, record_type)
        if not normalized_items:
            raise ValueError("items must not be empty")

        for record in self._records:
            if int(record.get("id", 0)) != record_id:
                continue

            existing_items = list(record.get("items", []))
            existing_items.extend(normalized_items)
            total_quantity = sum(
                int(item.get("quantity", 0)) for item in existing_items
            )
            total_amount = sum(
                float(item.get("quantity", 0)) * float(item.get("unit_price", 0))
                for item in existing_items
            )

            record["items"] = existing_items
            record["quantity"] = total_quantity
            record["total_amount"] = total_amount
            record["unit_price"] = (
                abs(total_amount / total_quantity) if total_quantity else 0.0
            )
            self.store.save_list(self._records)
            return record

        raise KeyError(f"record {record_id} not found")

    def create_linked_return(
        self,
        *,
        original_record_id: int,
        items: list[dict[str, Any]],
        note: str = "",
        date: str | None = None,
    ) -> dict[str, Any]:
        original_record = next(
            (
                record
                for record in self._records
                if int(record.get("id", 0)) == original_record_id
            ),
            None,
        )
        if original_record is None:
            raise KeyError(f"record {original_record_id} not found")
        if (
            original_record.get("type") == "return"
            or int(original_record.get("quantity", 0)) < 0
        ):
            raise ValueError("cannot create linked return from return record")

        normalized_items = self._normalize_items(items, "return")
        if not normalized_items:
            raise ValueError("items must not be empty")

        requested_return_qty = sum(
            abs(int(item["quantity"])) for item in normalized_items
        )
        original_qty = abs(int(original_record.get("quantity", 0)))
        if requested_return_qty > original_qty:
            raise ValueError("return quantity exceeds original record quantity")

        total_amount = sum(
            float(item["quantity"]) * float(item["unit_price"])
            for item in normalized_items
        )
        total_quantity = sum(int(item["quantity"]) for item in normalized_items)
        average_price = abs(total_amount / total_quantity) if total_quantity else 0.0
        base_note = note.strip() or str(original_record.get("note", "")).strip()
        normalized_note = f"[退货] 原记录#{original_record_id} {base_note}".strip()

        record = {
            "id": max((int(record.get("id", 0)) for record in self._records), default=0)
            + 1,
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "quantity": total_quantity,
            "unit_price": average_price,
            "total_amount": total_amount,
            "note": normalized_note,
            "type": "return",
            "items": normalized_items,
            "original_record_id": original_record_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._records.append(record)
        self.store.save_list(self._records)
        return record

    def summarize_by_date(self, date: str) -> dict[str, Any]:
        selected = [record for record in self._records if record.get("date") == date]
        sale_quantity = 0
        sale_amount = 0.0
        return_quantity = 0
        return_amount = 0.0

        for record in selected:
            items = record.get("items") or []
            if items:
                for item in items:
                    quantity = int(item.get("quantity", 0))
                    amount = quantity * float(item.get("unit_price", 0))
                    if quantity < 0:
                        return_quantity += abs(quantity)
                        return_amount += abs(amount)
                    else:
                        sale_quantity += quantity
                        sale_amount += amount
                continue

            quantity = int(record.get("quantity", 0))
            amount = float(record.get("total_amount", 0))
            if record.get("type") == "return" or quantity < 0:
                return_quantity += abs(quantity)
                return_amount += abs(amount)
            else:
                sale_quantity += quantity
                sale_amount += amount

        return {
            "sale_quantity": sale_quantity,
            "sale_amount": sale_amount,
            "return_quantity": return_quantity,
            "return_amount": return_amount,
            "net_quantity": sale_quantity - return_quantity,
            "net_amount": sale_amount - return_amount,
        }

    def _normalize_items(
        self, items: list[dict[str, Any]], record_type: str
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in items:
            quantity = int(item["quantity"])
            unit_price = float(item["unit_price"])
            if quantity <= 0 or unit_price <= 0:
                continue
            item_type = str(item.get("record_type", record_type or "sale"))
            normalized_quantity = -quantity if item_type == "return" else quantity
            normalized.append(
                {"quantity": normalized_quantity, "unit_price": unit_price}
            )
        return normalized

    def _derive_record_type(
        self, normalized_items: list[dict[str, Any]], fallback_type: str
    ) -> str:
        has_sale = any(int(item.get("quantity", 0)) > 0 for item in normalized_items)
        has_return = any(int(item.get("quantity", 0)) < 0 for item in normalized_items)
        if has_sale and has_return:
            return "mixed"
        if has_return:
            return "return"
        if has_sale:
            return "sale"
        return fallback_type or "sale"

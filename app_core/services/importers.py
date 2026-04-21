from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%Y年%m月%d日",
    "%Y.%m.%d",
    "%d.%m.%Y",
]

DATE_KEYWORDS = ["日期", "date", "时间", "time"]
QUANTITY_KEYWORDS = ["数量", "quantity", "套数", "件数", "套", "qty"]
PRICE_KEYWORDS = ["单价", "price", "unit", "价格", "unit_price", "单价(元)"]
NOTE_KEYWORDS = ["备注", "note", "说明", "描述", "notes", "客户"]
TYPE_KEYWORDS = ["类型", "type"]
TOTAL_KEYWORDS = ["总金额", "total", "金额", "总价", "合计", "total_amount"]


def parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()
    if not text:
        return None

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    try:
        excel_date = int(float(text))
    except ValueError:
        return None

    if 1 <= excel_date <= 50000:
        parsed = datetime(1899, 12, 30) + timedelta(days=excel_date)
        return parsed.strftime("%Y-%m-%d")
    return None


def parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("¥", "").replace("元", "").replace(",", "").replace(" ", "").strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def detect_columns(headers: Sequence[str]) -> dict[str, int]:
    lowered = [str(header).lower().strip() for header in headers]
    mapping: dict[str, int] = {}
    for idx, header in enumerate(lowered):
        if "date" not in mapping and any(keyword in header for keyword in DATE_KEYWORDS):
            mapping["date"] = idx
        if "quantity" not in mapping and any(keyword in header for keyword in QUANTITY_KEYWORDS):
            mapping["quantity"] = idx
        if "unit_price" not in mapping and any(keyword in header for keyword in PRICE_KEYWORDS):
            mapping["unit_price"] = idx
        if "note" not in mapping and any(keyword in header for keyword in NOTE_KEYWORDS):
            mapping["note"] = idx
    return mapping


def detect_named_columns(columns: Sequence[Any]) -> dict[str, str]:
    names = [str(column) for column in columns]
    index_mapping = detect_columns(names)
    return {key: names[index] for key, index in index_mapping.items()}


def normalize_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    data = {str(key).strip().lower(): value for key, value in row.items() if key is not None}

    def pick(keywords: Sequence[str]) -> Any:
        for key, value in data.items():
            if any(keyword in key for keyword in keywords):
                return value
        return None

    date = parse_date(pick(DATE_KEYWORDS))
    quantity = parse_number(pick(QUANTITY_KEYWORDS))
    unit_price = parse_number(pick(PRICE_KEYWORDS))
    total_amount = parse_number(pick(TOTAL_KEYWORDS))
    note_value = pick(NOTE_KEYWORDS)
    note = str(note_value).strip() if note_value not in (None, "") else ""
    type_value = pick(TYPE_KEYWORDS)
    record_type = "return" if str(type_value).strip() in {"退货", "return"} else "sale"

    if quantity == 0 and total_amount == 0:
        return None
    if unit_price == 0 and quantity != 0 and total_amount != 0:
        unit_price = abs(total_amount) / abs(quantity)
    if not date or quantity == 0 or unit_price == 0:
        return None

    if quantity < 0 or total_amount < 0:
        record_type = "return"

    return {
        "date": date,
        "quantity": int(abs(quantity)),
        "unit_price": float(unit_price),
        "note": note,
        "record_type": record_type,
    }


def build_record(*, record_id: int, date: str, quantity: int, unit_price: float, note: str = "", record_type: str = "sale") -> dict[str, Any]:
    signed_quantity = -quantity if record_type == "return" else quantity
    signed_total = signed_quantity * unit_price
    normalized_note = note.strip()
    if record_type == "return":
        normalized_note = f"[退货] {normalized_note}".strip() if normalized_note else "[退货]"
    return {
        "id": record_id,
        "date": date,
        "quantity": signed_quantity,
        "unit_price": float(unit_price),
        "total_amount": signed_total,
        "note": normalized_note,
        "type": record_type,
        "items": [{"quantity": signed_quantity, "unit_price": float(unit_price)}],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def import_csv_records(file_path: str | Path, starting_id: int = 1) -> list[dict[str, Any]]:
    path = Path(file_path)
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                records: list[dict[str, Any]] = []
                next_id = starting_id
                for row in reader:
                    normalized = normalize_row(row)
                    if not normalized:
                        continue
                    records.append(
                        build_record(
                            record_id=next_id,
                            date=normalized["date"],
                            quantity=normalized["quantity"],
                            unit_price=normalized["unit_price"],
                            note=normalized["note"],
                            record_type=normalized["record_type"],
                        )
                    )
                    next_id += 1
                return records
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return []

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app_core.storage import JsonStore

DEFAULT_PRINTER_SETTINGS: dict[str, Any] = {
    "shop_name": "家纺四件套",
    "shop_address": "",
    "shop_phone": "",
    "footer_text": "谢谢惠顾，欢迎下次光临！",
    "printer_name": "",
    "auto_print": False,
    "paper_width": 58,
    "compact_mode": True,
}


class PrinterSettingsStore:
    def __init__(self, file_path: Path):
        self.store = JsonStore(file_path)

    def load(self) -> dict[str, Any]:
        loaded = self._load_dict()
        settings = dict(DEFAULT_PRINTER_SETTINGS)
        settings.update(loaded)
        return settings

    def save(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = self.load()
        merged.update(settings)
        self.store.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.store.file_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged

    def apply_to_printer(self, printer: Any, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        current = settings or self.load()
        printer.set_shop_info(
            name=current["shop_name"],
            address=current["shop_address"],
            phone=current["shop_phone"],
        )
        printer.footer_text = current["footer_text"]
        width = int(current.get("paper_width", 58))
        printer.receipt_width = 32 if width == 58 else (44 if width == 76 else 48)
        return current

    def _load_dict(self) -> dict[str, Any]:
        path = self.store.file_path
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

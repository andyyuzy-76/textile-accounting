from __future__ import annotations

from pathlib import Path


def get_data_dir(home: Path | None = None) -> Path:
    base = home or Path.home()
    return base / ".accounting-tool"


def ensure_data_dir(home: Path | None = None) -> Path:
    data_dir = get_data_dir(home)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_records_file(home: Path | None = None) -> Path:
    return ensure_data_dir(home) / "records.json"

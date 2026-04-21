from pathlib import Path

import pandas as pd

import import_excel


def test_import_from_excel_auto_confirm_returns_error_when_required_columns_missing(
    monkeypatch, tmp_path
):
    excel_file = tmp_path / "records.xlsx"
    excel_file.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        import_excel.pd, "read_excel", lambda _path: pd.DataFrame({"备注": ["A"]})
    )

    result = import_excel.import_from_excel(str(excel_file), auto_confirm=True)

    assert result["success"] is False
    assert "无法自动识别必需列" in result["error"]


def test_import_from_excel_auto_confirm_builds_records_without_input(
    monkeypatch, tmp_path
):
    excel_file = tmp_path / "records.xlsx"
    excel_file.write_text("placeholder", encoding="utf-8")

    dataframe = pd.DataFrame(
        {
            "日期": ["2026-04-21"],
            "数量": [2],
            "单价": [100],
            "备注": ["客户A"],
        }
    )
    monkeypatch.setattr(import_excel.pd, "read_excel", lambda _path: dataframe)

    result = import_excel.import_from_excel(str(excel_file), auto_confirm=True)

    assert result["success"] is True
    assert result["imported"] == 1
    assert result["records"][0]["date"] == "2026-04-21"
    assert result["records"][0]["quantity"] == 2
    assert result["records"][0]["unit_price"] == 100.0

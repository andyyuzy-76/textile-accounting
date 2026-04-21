from app_core.services.importers import import_csv_records, normalize_row


def test_normalize_row_parses_currency_and_date():
    row = {
        "日期": "2026/04/21",
        "数量": "2",
        "单价": "¥100",
        "客户": "客户A",
        "备注": "备注1",
    }
    normalized = normalize_row(row)
    assert normalized is not None
    assert normalized["date"] == "2026-04-21"
    assert normalized["quantity"] == 2
    assert normalized["unit_price"] == 100.0
    assert normalized["customer"] == "客户A"
    assert normalized["note"] == "备注1"
    assert normalized["record_type"] == "sale"


def test_import_csv_records_supports_exported_total_amount_format(tmp_path):
    csv_file = tmp_path / "records.csv"
    csv_file.write_text(
        "日期,类型,数量,总金额,备注\n2026-04-21,退货,-1,-88,客户退货\n",
        encoding="utf-8-sig",
    )

    records = import_csv_records(csv_file, starting_id=10)

    assert len(records) == 1
    assert records[0]["id"] == 10
    assert records[0]["type"] == "return"
    assert records[0]["quantity"] == -1
    assert records[0]["total_amount"] == -88.0


def test_import_csv_records_does_not_duplicate_return_prefix(tmp_path):
    csv_file = tmp_path / "records.csv"
    csv_file.write_text(
        "日期,类型,数量,总金额,备注\n2026-04-21,退货,-1,-88,[退货] 客户退货\n",
        encoding="utf-8-sig",
    )

    records = import_csv_records(csv_file, starting_id=1)

    assert records[0]["note"] == "[退货] 客户退货"

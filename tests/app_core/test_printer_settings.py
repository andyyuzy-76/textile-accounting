from app_core.services.printer_settings import PrinterSettingsStore


class DummyPrinter:
    def __init__(self):
        self.shop_name = None
        self.shop_address = None
        self.shop_phone = None
        self.footer_text = None
        self.receipt_width = None

    def set_shop_info(self, name: str = "", address: str = "", phone: str = ""):
        self.shop_name = name
        self.shop_address = address
        self.shop_phone = phone


def test_printer_settings_store_returns_defaults_when_missing(tmp_path):
    store = PrinterSettingsStore(tmp_path / "printer_settings.json")
    settings = store.load()
    assert settings["paper_width"] == 58
    assert settings["auto_print"] is False
    assert settings["customers"] == []


def test_printer_settings_store_saves_and_applies_to_printer(tmp_path):
    store = PrinterSettingsStore(tmp_path / "printer_settings.json")
    printer = DummyPrinter()

    settings = store.save({"shop_name": "A店", "paper_width": 76})
    store.apply_to_printer(printer, settings)

    assert printer.shop_name == "A店"
    assert printer.receipt_width == 44


def test_printer_settings_store_persists_customer_list(tmp_path):
    store = PrinterSettingsStore(tmp_path / "printer_settings.json")

    store.save({"customers": ["张女士", "李老板"]})
    settings = store.load()

    assert settings["customers"] == ["张女士", "李老板"]

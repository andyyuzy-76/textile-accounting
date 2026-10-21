import json
from pathlib import Path

import accounting_flet


class DummyWindow:
    def __init__(self):
        self.width = None
        self.height = None
        self.maximized = False


class DummyPage:
    def __init__(self):
        self.title = None
        self.window = DummyWindow()
        self.updated = False

    def update(self):
        self.updated = True


def test_ui_version_matches_release_manifest():
    manifest_path = Path(accounting_flet.__file__).with_name("version.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert accounting_flet.VERSION == manifest["version"]


def test_configure_page_sets_window_defaults():
    page = DummyPage()

    accounting_flet.configure_page(page)

    assert page.title == "家纺记账系统"
    assert page.window.width == 1400
    assert page.window.height == 900


def test_main_initializes_app_and_refreshes(monkeypatch):
    page = DummyPage()
    calls = {"refresh": False}

    class DummyApp:
        def __init__(self, incoming_page):
            assert incoming_page is page

        def refresh_display(self):
            calls["refresh"] = True

    monkeypatch.setattr(accounting_flet, "AccountingApp", DummyApp)

    accounting_flet.main(page)

    assert calls["refresh"] is True
    assert page.updated is True

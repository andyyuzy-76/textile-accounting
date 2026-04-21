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

import io
import json

import auto_updater


def test_is_frozen_app_reflects_runtime_flag(monkeypatch):
    monkeypatch.setattr(auto_updater.sys, "frozen", True, raising=False)

    assert auto_updater.is_frozen_app() is True


def test_get_release_asset_download_url_returns_matching_asset(monkeypatch):
    payload = {
        "assets": [
            {
                "name": "家纺记账系统-苹果风格.exe",
                "browser_download_url": "https://example.com/app.exe",
            }
        ]
    }

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(
        auto_updater.urllib.request, "urlopen", lambda *args, **kwargs: DummyResponse()
    )

    result = auto_updater.get_release_asset_download_url("家纺记账系统-苹果风格.exe")

    assert result == "https://example.com/app.exe"

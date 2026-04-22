import io
import json
import hashlib

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


def test_get_release_asset_info_returns_matching_asset_metadata(monkeypatch):
    payload = {
        "assets": [
            {
                "name": "TextileAccounting_v1.15.2.exe",
                "browser_download_url": "https://example.com/app.exe",
                "size": 1234,
                "digest": "sha256:abcd",
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

    result = auto_updater.get_release_asset_info("TextileAccounting_v1.15.2.exe")

    assert result["browser_download_url"] == "https://example.com/app.exe"
    assert result["size"] == 1234
    assert result["digest"] == "sha256:abcd"


def test_verify_downloaded_file_checks_size_and_sha256(tmp_path):
    file_path = tmp_path / "app.exe"
    content = b"hello-update"
    file_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    success, message = auto_updater.verify_downloaded_file(
        str(file_path),
        expected_size=len(content),
        expected_digest=f"sha256:{digest}",
    )

    assert success is True
    assert message == ""


def test_verify_downloaded_file_rejects_wrong_size(tmp_path):
    file_path = tmp_path / "app.exe"
    file_path.write_bytes(b"hello-update")

    success, message = auto_updater.verify_downloaded_file(
        str(file_path),
        expected_size=1,
    )

    assert success is False
    assert "大小校验失败" in message


def test_check_for_updates_hides_exe_update_until_release_asset_exists(monkeypatch):
    monkeypatch.setattr(auto_updater, "is_frozen_app", lambda: True)
    monkeypatch.setattr(
        auto_updater,
        "get_current_version",
        lambda: "1.15.1",
    )
    monkeypatch.setattr(
        auto_updater,
        "get_remote_manifest",
        lambda: {
            "version": "1.15.2",
            "message": "有新版本",
            "exe_asset_name": "TextileAccounting_v1.15.2.exe",
        },
    )
    monkeypatch.setattr(auto_updater, "get_release_asset_info", lambda asset_name: None)

    has_update, remote, current, message = auto_updater.check_for_updates(silent=False)

    assert has_update is False
    assert remote == "1.15.2"
    assert current == "1.15.1"
    assert "尚未发布" in message

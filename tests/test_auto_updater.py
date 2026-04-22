import io
import json
import hashlib
from pathlib import Path

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


def test_perform_binary_update_resets_pyinstaller_environment_before_restart(
    monkeypatch, tmp_path
):
    temp_dir = tmp_path / "update-temp"
    temp_dir.mkdir()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        auto_updater,
        "get_remote_manifest",
        lambda: {"exe_asset_name": "TextileAccounting_v1.15.4.exe"},
    )
    monkeypatch.setattr(
        auto_updater,
        "get_release_asset_info",
        lambda asset_name: {
            "browser_download_url": "https://example.com/TextileAccounting_v1.15.4.exe",
            "size": 3,
            "digest": None,
        },
    )
    monkeypatch.setattr(auto_updater.tempfile, "mkdtemp", lambda: str(temp_dir))
    monkeypatch.setattr(
        auto_updater,
        "download_url",
        lambda url, dest_path: Path(dest_path).write_bytes(b"exe") or True,
    )

    def fake_popen(args, creationflags=0):
        captured["args"] = args
        captured["creationflags"] = creationflags
        return None

    monkeypatch.setattr(auto_updater.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(auto_updater.sys, "executable", str(tmp_path / "app.exe"))

    class ExitCalled(Exception):
        pass

    def fake_exit(code):
        raise ExitCalled(code)

    monkeypatch.setattr(auto_updater.os, "_exit", fake_exit)

    try:
        auto_updater.perform_binary_update()
    except ExitCalled:
        pass

    script_path = temp_dir / "apply_update.bat"
    assert script_path.exists()
    script = script_path.read_text(encoding="utf-8")
    assert "set PYINSTALLER_RESET_ENVIRONMENT=1" in script


def test_perform_binary_update_reports_progress_stages(monkeypatch, tmp_path):
    temp_dir = tmp_path / "update-temp"
    temp_dir.mkdir()
    messages: list[str] = []

    monkeypatch.setattr(
        auto_updater,
        "get_remote_manifest",
        lambda: {"exe_asset_name": "TextileAccounting_v1.15.5.exe"},
    )
    monkeypatch.setattr(
        auto_updater,
        "get_release_asset_info",
        lambda asset_name: {
            "browser_download_url": "https://example.com/TextileAccounting_v1.15.5.exe",
            "size": 3,
            "digest": None,
        },
    )
    monkeypatch.setattr(auto_updater.tempfile, "mkdtemp", lambda: str(temp_dir))
    monkeypatch.setattr(
        auto_updater,
        "download_url",
        lambda url, dest_path: Path(dest_path).write_bytes(b"exe") or True,
    )
    monkeypatch.setattr(
        auto_updater,
        "verify_downloaded_file",
        lambda *args, **kwargs: (True, ""),
    )
    monkeypatch.setattr(
        auto_updater.subprocess,
        "Popen",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(auto_updater.sys, "executable", str(tmp_path / "app.exe"))

    class ExitCalled(Exception):
        pass

    monkeypatch.setattr(auto_updater.os, "_exit", lambda code: (_ for _ in ()).throw(ExitCalled(code)))

    try:
        auto_updater.perform_binary_update(messages.append)
    except ExitCalled:
        pass

    assert messages == [
        "正在下载软件更新包...",
        "正在校验更新包...",
        "正在应用更新...",
        "正在重启程序...",
    ]

import io
import json
import hashlib
from pathlib import Path

import pytest

import auto_updater


def test_get_current_version_uses_local_manifest_for_source(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(auto_updater, "is_frozen_app", lambda: False)
    (tmp_path / "version.json").write_text('{"version": "1.15.9"}', encoding="utf-8")
    assert auto_updater.get_current_version() == "1.15.9"


def test_get_current_version_uses_bundled_manifest_for_exe(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "version.json").write_text('{"version": "1.15.9"}', encoding="utf-8")
    (tmp_path / "version.json").write_text('{"version": "1.15.8"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(auto_updater, "is_frozen_app", lambda: True)
    monkeypatch.setattr(auto_updater, "__file__", str(bundle / "auto_updater.py"))
    assert auto_updater.get_current_version() == "1.15.9"


def test_source_update_downloads_cloud_backup_module(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(auto_updater, "is_frozen_app", lambda: False)
    downloaded = []

    def download(filename, destination):
        downloaded.append(filename)
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# updated", encoding="utf-8")
        return True

    monkeypatch.setattr(auto_updater, "download_file", download)
    success, _ = auto_updater.perform_update()
    assert success
    assert "app_core/services/cloud_backup.py" in downloaded
    assert (tmp_path / "app_core/services/cloud_backup.py").read_text(encoding="utf-8") == "# updated"


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


@pytest.fixture
def binary_update(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = tmp_path / "家纺 & 账本.exe"
    target.write_bytes(b"old")
    captured = {"target": target, "data_dir": data_dir}
    monkeypatch.setattr(auto_updater, "ensure_data_dir", lambda: data_dir)
    monkeypatch.setattr(auto_updater.sys, "executable", str(target))
    monkeypatch.setattr(auto_updater, "get_remote_manifest", lambda: {
        "exe_asset_name": "TextileAccounting_v1.15.11.exe",
    })
    monkeypatch.setattr(auto_updater, "get_release_asset_info", lambda name: {
        "browser_download_url": "https://example.com/app.exe",
        "size": 3,
        "digest": "sha256:" + hashlib.sha256(b"exe").hexdigest(),
    })
    monkeypatch.setattr(auto_updater, "download_url", lambda url, path: Path(path).write_bytes(b"exe"))

    class Helper:
        def poll(self):
            return None

    def popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        config = Path(kwargs["cwd"]) / "update.json"
        captured["job_dir"] = config.parent
        (config.parent / "ready").touch()
        return Helper()

    def exit_process(code):
        pytest.fail("更新助手就绪后应由界面正常关闭，不能强制退出进程")

    monkeypatch.setattr(auto_updater.subprocess, "Popen", popen)
    monkeypatch.setattr(auto_updater.os, "_exit", exit_process)
    return captured


def test_binary_update_preserves_target_and_retains_download_before_handoff(binary_update):
    success, message = auto_updater.perform_binary_update()
    assert success is True
    assert "重启" in message
    job_dir = binary_update["job_dir"]
    config = json.loads((job_dir / "update.json").read_text(encoding="utf-8"))
    assert Path(config["target"]) == binary_update["target"]
    assert binary_update["target"].read_bytes() == b"old"
    assert Path(config["staged"]).parent == binary_update["target"].parent
    assert Path(config["staged"]).read_bytes() == b"exe"
    assert job_dir.parent == binary_update["data_dir"] / "update"
    assert (job_dir / "TextileAccounting_v1.15.11.exe").read_bytes() == b"exe"
    script = (job_dir / "apply_update.ps1").read_text(encoding="utf-8-sig")
    assert "$env:PYINSTALLER_RESET_ENVIRONMENT = '1'" in script
    assert binary_update["kwargs"]["creationflags"] == auto_updater.subprocess.CREATE_NO_WINDOW


def test_perform_binary_update_reports_progress_stages(binary_update):
    messages = []
    success, _ = auto_updater.perform_binary_update(messages.append)
    assert success is True
    assert "保存位置：" in messages[0]
    assert messages[1:] == ["正在校验更新包...", "正在应用更新...", "正在重启程序..."]


@pytest.mark.parametrize("name", ["../outside.exe", "..\\outside.exe", "app.bat", None])
def test_binary_update_rejects_invalid_filename(binary_update, monkeypatch, name):
    monkeypatch.setattr(auto_updater, "get_remote_manifest", lambda: {"exe_asset_name": name})
    success, message = auto_updater.perform_binary_update()
    assert success is False
    assert "文件名无效" in message
    assert binary_update["target"].read_bytes() == b"old"


def test_binary_update_rejects_bad_download_without_exiting(binary_update, monkeypatch):
    monkeypatch.setattr(auto_updater, "download_url", lambda url, path: Path(path).write_bytes(b"bad-data"))
    success, message = auto_updater.perform_binary_update()
    assert success is False
    assert "大小校验失败" in message
    assert binary_update["target"].read_bytes() == b"old"
    assert not list(binary_update["data_dir"].rglob("*.exe"))


@pytest.mark.parametrize("failure", ["permission", "helper"])
def test_binary_update_preflight_failure_keeps_app_and_download(binary_update, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise PermissionError("access denied")

    if failure == "permission":
        monkeypatch.setattr(auto_updater.tempfile, "mkstemp", fail)
    else:
        monkeypatch.setattr(auto_updater.subprocess, "Popen", fail)
    success, message = auto_updater.perform_binary_update()
    assert success is False
    assert "当前程序可继续使用" in message
    assert "更新包和日志目录" in message
    assert binary_update["target"].read_bytes() == b"old"
    assert not list(binary_update["target"].parent.glob(".textile-update-*.exe"))
    assert len(list(binary_update["data_dir"].rglob("*.exe"))) == 1
    assert len(list(binary_update["data_dir"].rglob("update.log"))) == 1


def test_binary_update_does_not_exit_until_helper_is_ready(binary_update, monkeypatch):
    class FailedHelper:
        def poll(self):
            return 1

    monkeypatch.setattr(auto_updater.subprocess, "Popen", lambda *args, **kwargs: FailedHelper())
    success, message = auto_updater.perform_binary_update()
    assert success is False
    assert "更新助手未能启动" in message
    assert binary_update["target"].read_bytes() == b"old"

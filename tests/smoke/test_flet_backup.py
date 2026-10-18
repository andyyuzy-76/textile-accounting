import asyncio
import os
from types import SimpleNamespace

import pytest

import accounting_flet as ui
from app_core.services.cloud_backup import CloudBackupError
from app_core.services import cloud_backup as cloud


class DummyPage:
    def __init__(self):
        self.dialogs = []
        self.tasks = []

    def update(self):
        pass

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop()

    def run_task(self, handler, *args):
        self.tasks.append((handler, args))

    def run_pending(self):
        handler, args = self.tasks.pop(0)
        asyncio.run(handler(*args))


@pytest.fixture
def app(tmp_path, monkeypatch):
    if os.name != "nt":
        monkeypatch.setattr(cloud, "protect_password", lambda value, **kwargs: value)
    instance = object.__new__(ui.AccountingApp)
    instance.page = DummyPage()
    instance.cloud_backup = ui.CloudBackupService(tmp_path)
    instance.cloud_backup_button = ui.ft.IconButton()
    instance._backup_generation = 0
    instance.data_file = str(tmp_path / "records.json")
    return instance


def dialog_controls(app):
    dialog = app.page.dialogs[-1]
    controls = dialog.content.content.controls
    return SimpleNamespace(url=controls[1], username=controls[2], password=controls[3], auto=controls[4],
                           test=controls[5].controls[0], upload=controls[5].controls[1],
                           status=controls[7], history=controls[10].controls[0],
                           refresh=controls[10].controls[1], restore=controls[11],
                           save=dialog.actions[1])


def configure(fields):
    fields.url.value = "https://example.com/dav"
    fields.username.value = " backup-user "
    fields.password.value = "test-app-password"


def test_dialog_upload_history_and_cancel_restore(app, monkeypatch):
    monkeypatch.setattr(app.cloud_backup, "backup", lambda: "backup-name")
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: ["backup-name"])
    monkeypatch.setattr(app.cloud_backup, "download", lambda name: {"records": [{"id": 1}]})
    monkeypatch.setattr(app.cloud_backup, "restore", lambda data: pytest.fail("cancel must not restore"))
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    assert controls.password.password is True
    assert controls.restore.disabled is True
    controls.upload.on_click(None)
    app.page.run_pending()
    assert "备份成功" in controls.status.value
    controls.refresh.on_click(None)
    app.page.run_pending()
    assert controls.history.value == "backup-name"
    assert controls.restore.disabled is False
    assert controls.url.value == "https://example.com/dav/"
    assert controls.username.value == "backup-user"
    controls.restore.on_click(None)
    app.page.run_pending()
    assert len(app.page.dialogs) == 2
    assert app._cloud_backup_busy is True
    app.page.dialogs[-1].actions[0].on_click(None)
    assert len(app.page.dialogs) == 1
    assert app._cloud_backup_busy is False


def test_confirm_restore_reloads_records_and_printer_settings(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: ["backup-name"])
    monkeypatch.setattr(app.cloud_backup, "download", lambda name: {"records": []})
    monkeypatch.setattr(app.cloud_backup, "restore", lambda data: calls.append("restore") or "safety-dir")
    app.load_records = lambda: calls.append("records")
    app.load_printer_settings = lambda: calls.append("settings")
    app.refresh_customer_dropdown = lambda: calls.append("customers")
    app.refresh_display = lambda: calls.append("display")
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    controls.refresh.on_click(None)
    app.page.run_pending()
    controls.restore.on_click(None)
    app.page.run_pending()
    asyncio.run(app.page.dialogs[-1].actions[1].on_click(None))
    assert calls == ["restore", "records", "settings", "customers", "display"]
    assert "safety-dir" in controls.status.value
    assert app._cloud_backup_busy is False


def test_changed_destination_requires_refresh_before_restore(app, monkeypatch):
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: ["backup-name"])
    monkeypatch.setattr(app.cloud_backup, "download", lambda name: pytest.fail("stale destination"))
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    controls.refresh.on_click(None)
    app.page.run_pending()
    controls.url.value = "https://other.example/dav/"
    controls.restore.on_click(None)
    app.page.run_pending()
    assert "请先刷新" in controls.status.value
    assert len(app.page.dialogs) == 1


def test_upload_failure_is_visible_and_unlocks_controls(app, monkeypatch):
    def fail():
        raise CloudBackupError("云端存储空间不足。")

    monkeypatch.setattr(app.cloud_backup, "backup", fail)
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    controls.upload.on_click(None)
    app.page.run_pending()
    assert "空间不足" in controls.status.value
    assert controls.status.color == ui.AppleColors.DANGER
    assert controls.upload.disabled is False
    assert app.cloud_backup_button.icon_color == ui.AppleColors.WARNING


def test_auto_backup_runs_latest_save_only_and_reports_failure(app, monkeypatch):
    monkeypatch.setattr(app.cloud_backup.settings, "load", lambda: {"auto_backup": True})
    calls = []
    monkeypatch.setattr(app.cloud_backup, "backup", lambda **kwargs: calls.append(kwargs) or "name")
    async def no_sleep(seconds):
        pass
    monkeypatch.setattr(ui.asyncio, "sleep", no_sleep)
    app.cloud_backup.data_dir.joinpath("records.json").write_text("[]", encoding="utf-8")
    app.schedule_cloud_backup()
    app.schedule_cloud_backup()
    app.page.run_pending()
    assert calls == []
    app.page.run_pending()
    assert calls == [{"force": False}]

    def fail(**kwargs):
        raise CloudBackupError("无法连接云端")
    monkeypatch.setattr(app.cloud_backup, "backup", fail)
    app.schedule_cloud_backup()
    app.page.run_pending()
    assert "自动备份失败" in app.cloud_backup_button.tooltip
    assert app.cloud_backup_button.icon_color == ui.AppleColors.WARNING
    monkeypatch.setattr(app.cloud_backup.settings, "load", lambda: {"auto_backup": False})
    app.schedule_cloud_backup()
    assert app.page.tasks == []


def test_print_and_customer_settings_also_schedule_backup(app):
    calls = []
    app.printer_settings_store = SimpleNamespace(save=lambda settings: settings)
    app.receipt_printer = None
    app.refresh_customer_dropdown = lambda: None
    app.schedule_cloud_backup = lambda: calls.append("backup")
    app.save_printer_settings({"customers": ["测试客户"]})
    assert calls == ["backup"]


def test_keyboard_submit_is_blocked_during_restore(app):
    app._cloud_backup_busy = True
    app.add_record = lambda: pytest.fail("must not modify data while restoring")
    app.handle_main_form_keyboard(SimpleNamespace(key="Enter", ctrl=True))


def test_unreadable_saved_password_is_visible_at_startup(app, monkeypatch):
    monkeypatch.setattr(app.cloud_backup.settings, "load", lambda: {"auto_backup": False, "error": "请重新填写应用密码"})
    app.schedule_cloud_backup()
    assert "重新填写" in app.cloud_backup_button.tooltip
    assert app.cloud_backup_button.icon_color == ui.AppleColors.WARNING
    assert app.page.tasks == []

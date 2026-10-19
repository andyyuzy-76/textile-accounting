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
    return SimpleNamespace(url=controls[1], username=controls[2], password=controls[3],
                           ledger=controls[4], device=controls[5], auto=controls[6], number=controls[7],
                           test=controls[8].controls[0], upload=controls[8].controls[1],
                           status=controls[10], history=controls[13].controls[0],
                           refresh=controls[13].controls[1], details=controls[14], restore=controls[15],
                           save=dialog.actions[1])


def configure(fields):
    fields.url.value = "https://example.com/dav"
    fields.username.value = " backup-user "
    fields.password.value = "test-app-password"


def test_dialog_upload_history_and_cancel_restore(app, monkeypatch):
    monkeypatch.setattr(app.cloud_backup, "backup", lambda: "backup-name")
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: [{"name": "backup-name"}])
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
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: [{"name": "backup-name"}])
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
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: [{"name": "backup-name"}])
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


def test_invalid_account_reports_account_error_in_the_dialog(app):
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    identity = app.cloud_backup.identity()
    controls.username.value = "backup\nuser"
    controls.save.on_click(None)
    assert "NAS / WebDAV 账号" in controls.status.value
    assert controls.status.color == ui.AppleColors.DANGER
    controls.upload.on_click(None)
    app.page.run_pending()
    assert "NAS / WebDAV 账号" in controls.status.value
    assert controls.upload.disabled is False
    assert app.cloud_backup.identity() == identity


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


def test_identity_names_are_saved_and_ids_stay_stable(app):
    app.show_cloud_backup()
    controls = dialog_controls(app)
    identity = app.cloud_backup.identity()
    controls.ledger.value = " 门店账本 "
    controls.device.value = " 前台电脑 "
    controls.save.on_click(None)
    assert app.cloud_backup.identity() == {**identity, "ledger_name": "门店账本", "device_name": "前台电脑"}
    assert controls.ledger.value == "门店账本"
    assert controls.device.value == "前台电脑"
    assert identity["ledger_id"] in controls.number.value
    controls.ledger.value = " "
    controls.save.on_click(None)
    assert controls.status.color == ui.AppleColors.DANGER


def test_history_and_confirmation_show_source_from_verified_backup(app, monkeypatch):
    source = {**app.cloud_backup.identity(), "ledger_id": "1" * 32, "device_id": "2" * 32,
              "ledger_name": "门店账本", "device_name": "前台电脑", "webdav_account": "store-user"}
    name = "backup-20261018T120000000000Z-12345678.json"
    info = {"name": name, "backup_identity": source, "record_count": 1200}
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: [info, {"name": "old-backup"}])
    verified_source = {**source, "ledger_name": "已校验账本", "device_name": "已校验电脑"}
    monkeypatch.setattr(app.cloud_backup, "download", lambda name: {"records": [], "backup_identity": verified_source})
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    controls.refresh.on_click(None)
    app.page.run_pending()
    assert "门店账本" in controls.history.options[0].text
    assert "前台电脑" in controls.history.options[0].text
    assert "1200 条" in controls.details.value
    assert source["ledger_id"] in controls.details.value
    assert "store-user" in controls.details.value
    controls.history.value = "old-backup"
    controls.history.on_select(None)
    assert "未记录来源" in controls.details.value
    controls.history.value = name
    controls.history.on_select(None)
    controls.restore.on_click(None)
    app.page.run_pending()
    confirmation = app.page.dialogs[-1].content.value
    assert app.page.dialogs[-1].scrollable is True
    assert "已校验账本" in confirmation
    assert "已校验电脑" in confirmation
    assert "store-user" in confirmation
    assert "0 条账目" in confirmation
    assert "1200" not in confirmation
    assert "沿用备份中的账本编号" in confirmation


def test_legacy_confirmation_explains_unknown_origin(app, monkeypatch):
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: [{"name": "backup-name"}])
    monkeypatch.setattr(app.cloud_backup, "download", lambda name: {"records": []})
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    controls.refresh.on_click(None)
    app.page.run_pending()
    controls.restore.on_click(None)
    app.page.run_pending()
    confirmation = app.page.dialogs[-1].content.value
    assert "未记录账本归属" in confirmation
    assert "使用当前账本名称和编号" in confirmation


def test_changed_identity_requires_refresh_before_restore(app, monkeypatch):
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: [{"name": "backup-name"}])
    monkeypatch.setattr(app.cloud_backup, "download", lambda name: pytest.fail("changed identity"))
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    controls.refresh.on_click(None)
    app.page.run_pending()
    controls.ledger.value = "另一账本"
    controls.restore.on_click(None)
    app.page.run_pending()
    assert "请先刷新" in controls.status.value
    assert len(app.page.dialogs) == 1


def test_corrupt_local_identity_before_restore_is_reported(app, monkeypatch):
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: [{"name": "backup-name"}])
    monkeypatch.setattr(app.cloud_backup, "download", lambda name: pytest.fail("identity must be checked first"))
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    controls.refresh.on_click(None)
    app.page.run_pending()
    app.cloud_backup.data_dir.joinpath("backup_identity.json").write_bytes(b"broken identity")
    controls.restore.on_click(None)
    app.page.run_pending()
    assert "账本身份无法读取" in controls.status.value
    assert controls.status.color == ui.AppleColors.DANGER
    assert len(app.page.dialogs) == 1


def test_restore_updates_ledger_fields_and_preserves_this_computer(app, monkeypatch):
    original = app.cloud_backup.save_identity("本地账本", "新电脑")
    source = {**original, "ledger_id": "1" * 32, "device_id": "2" * 32,
              "ledger_name": "原账本", "device_name": "旧电脑", "webdav_account": "old-user"}
    info = {"name": "backup-name", "backup_identity": source, "record_count": 0}
    monkeypatch.setattr(app.cloud_backup, "list_backups", lambda: [info])
    monkeypatch.setattr(app.cloud_backup, "download", lambda name: {"records": [], "printer_settings": {}, "backup_identity": source})
    for method in ("load_records", "load_printer_settings", "refresh_customer_dropdown", "refresh_display"):
        monkeypatch.setattr(app, method, lambda: None)
    app.show_cloud_backup()
    controls = dialog_controls(app)
    configure(controls)
    controls.refresh.on_click(None)
    app.page.run_pending()
    login = app.cloud_backup.settings.load()
    controls.restore.on_click(None)
    app.page.run_pending()
    asyncio.run(app.page.dialogs[-1].actions[1].on_click(None))
    assert controls.ledger.value == "原账本"
    assert controls.device.value == "新电脑"
    assert source["ledger_id"] in controls.number.value
    assert app.cloud_backup.identity()["device_id"] == original["device_id"]
    assert app.cloud_backup.settings.load() == login

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from app_core.services import cloud_backup as cloud
from app_core.services import local_backup as local


DATA = {
    "records": [{"id": 1, "date": "2026-10-18", "quantity": 2,
                 "unit_price": 120.5, "total_amount": 241.0, "customer": "测试客户",
                 "type": "sale", "items": [{"quantity": 2, "unit_price": 120.5}]}],
    "printer_settings": {"customers": ["测试客户"], "paper_width": 58, "auto_print": False},
}


@pytest.fixture
def service(tmp_path):
    target = tmp_path / "backup-out"
    instance = local.LocalBackupService(tmp_path / "data")
    instance.settings.save({"directory": str(target), "auto_backup": True, "keep": local.DEFAULT_KEEP})
    cloud.atomic_write(instance.data_dir / "records.json", cloud.json_bytes(DATA["records"]))
    cloud.atomic_write(instance.data_dir / "printer_settings.json", cloud.json_bytes(DATA["printer_settings"]))
    return instance


def test_backup_writes_verified_file_meta_and_state(service):
    name = service.backup()
    target = Path(service.settings.load()["directory"])
    assert cloud.BACKUP_NAME.fullmatch(name)
    assert (target / name).exists()
    assert (target / (name + ".meta.json")).exists()
    payload = json.loads((target / name).read_text(encoding="utf-8"))
    assert payload["app"] == "textile-accounting"
    assert payload["sha256"] == hashlib.sha256(cloud.json_bytes(payload["data"])).hexdigest()
    assert payload["data"]["backup_identity"]["ledger_id"] == service.identity()["ledger_id"]
    assert "webdav_account" not in payload["data"]["backup_identity"]
    state = service.state()
    assert state["name"] == name
    assert state["last_backup"]
    assert state["directory"] == str(target)


def test_unchanged_data_is_skipped_unless_forced(service):
    assert service.backup(force=False) is not None
    assert service.backup(force=False) is None
    assert service.backup() is not None
    assert len(service.list_backups()) == 2


def test_changed_directory_forces_a_new_backup(service, tmp_path):
    assert service.backup(force=False) is not None
    service.settings.save({"directory": str(tmp_path / "second"), "auto_backup": True,
                           "keep": local.DEFAULT_KEEP})
    assert service.backup(force=False) is not None
    assert len(service.list_backups()) == 1


def test_history_reads_meta_and_flags_damaged_index(service):
    first = service.backup()
    target = Path(service.settings.load()["directory"])
    (target / (first + ".meta.json")).write_text("{broken", encoding="utf-8")
    cloud.atomic_write(service.data_dir / "records.json",
                       cloud.json_bytes([{**DATA["records"][0], "id": 2}]))
    second = service.backup()
    infos = {info["name"]: info for info in service.list_backups()}
    assert infos[second]["record_count"] == 1
    assert infos[second]["backup_identity"]["ledger_name"]
    assert infos[first]["metadata_error"] is True


def test_download_verifies_checksum_and_rejects_tampering(service):
    name = service.backup()
    target = Path(service.settings.load()["directory"])
    assert service.download(name)["records"][0]["id"] == 1
    payload = json.loads((target / name).read_text(encoding="utf-8"))
    payload["data"]["records"][0]["quantity"] = 99
    (target / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(cloud.CloudBackupError, match="校验"):
        service.download(name)


@pytest.mark.parametrize("name", ["../records.json", "backup.json", "backup-2026T1-x.json", ""])
def test_download_rejects_unsafe_names(service, name):
    with pytest.raises(cloud.CloudBackupError, match="文件名无效"):
        service.download(name)


def test_missing_directory_or_file_reports_clear_errors(service, tmp_path):
    name = service.backup()
    target = Path(service.settings.load()["directory"])
    (target / name).unlink()
    with pytest.raises(cloud.CloudBackupError, match="不存在"):
        service.download(name)
    shutil.rmtree(target)
    with pytest.raises(cloud.CloudBackupError, match="备份目录不存在"):
        service.list_backups()


def test_prune_keeps_only_the_newest_backups(service):
    service.settings.save({"directory": service.settings.load()["directory"], "auto_backup": True,
                           "keep": local.MIN_KEEP})
    for index in range(local.MIN_KEEP + 3):
        cloud.atomic_write(service.data_dir / "records.json",
                           cloud.json_bytes([{**DATA["records"][0], "id": index}]))
        service.backup()
    target = Path(service.settings.load()["directory"])
    names = service.list_backups()
    assert len(names) == local.MIN_KEEP
    assert len([path for path in target.iterdir() if path.name.endswith(".meta.json")]) == local.MIN_KEEP
    assert len([path for path in target.iterdir() if path.name.startswith("backup-")]) == local.MIN_KEEP * 2


def test_restore_replaces_data_and_keeps_this_computer(service):
    name = service.backup()
    data = service.download(name)
    original = service.identity()
    cloud.atomic_write(service.data_dir / "records.json", cloud.json_bytes([]))
    safety = service.restore(data)
    assert safety.exists()
    assert json.loads((service.data_dir / "records.json").read_text(encoding="utf-8"))[0]["id"] == 1
    assert service.identity()["device_id"] == original["device_id"]


@pytest.mark.parametrize("value", ["", "  ", "relative\\path", "C:\\"])
def test_invalid_directories_are_rejected(tmp_path, value):
    with pytest.raises(cloud.CloudBackupError):
        local.parse_directory(value, tmp_path)


def test_data_directory_cannot_be_the_backup_target(tmp_path):
    with pytest.raises(cloud.CloudBackupError, match="程序数据目录"):
        local.parse_directory(str(tmp_path), tmp_path)
    with pytest.raises(cloud.CloudBackupError, match="程序数据目录"):
        local.parse_directory(str(tmp_path / "backups"), tmp_path)


def test_keep_bounds_are_enforced(tmp_path):
    for value in (0, local.MIN_KEEP - 1, local.MAX_KEEP + 1, "abc", True):
        with pytest.raises(cloud.CloudBackupError):
            local.parse_keep(value)
    assert local.parse_keep(local.MIN_KEEP) == local.MIN_KEEP


def test_settings_round_trip_and_corruption_disables_auto_backup(tmp_path):
    store = local.LocalBackupSettingsStore(tmp_path / "data")
    assert store.load()["auto_backup"] is True
    assert store.load()["directory"] == str(local.default_directory())
    saved = store.save({"directory": str(tmp_path / "out"), "auto_backup": False, "keep": 20})
    assert saved == {"directory": str((tmp_path / "out").resolve()), "auto_backup": False, "keep": 20}
    assert store.load() == saved
    store.path.write_text('{"directory": 3}', encoding="utf-8")
    broken = store.load()
    assert broken["auto_backup"] is False
    assert "无法读取" in broken["error"]


def test_backup_refuses_when_settings_are_unreadable(service):
    service.settings.path.write_text("{broken", encoding="utf-8")
    with pytest.raises(cloud.CloudBackupError, match="无法读取"):
        service.backup()


@pytest.mark.skipif(os.name != "nt", reason="Windows 路径")
def test_drive_root_is_rejected(tmp_path):
    with pytest.raises(cloud.CloudBackupError, match="磁盘根目录"):
        local.parse_directory("D:\\", tmp_path)

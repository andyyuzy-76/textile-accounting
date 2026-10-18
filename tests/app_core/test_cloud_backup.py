import base64
import copy
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import pytest

from app_core.services import cloud_backup as cloud


DATA = {
    "records": [{"id": 1, "date": "2026-10-18", "quantity": 2,
                 "unit_price": 120.5, "total_amount": 241.0, "customer": "测试客户",
                 "type": "sale", "items": [{"quantity": 2, "unit_price": 120.5}]}],
    "printer_settings": {"customers": ["测试客户"], "paper_width": 58, "auto_print": False},
}


@pytest.fixture
def dav():
    state = SimpleNamespace(files={}, requests=[], fail_method=None, fail_status=401,
                            corrupt_get=False, xml=None, extra_hrefs=[])
    authorization = "Basic " + base64.b64encode(b"backup-user:test-app-password").decode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_body(self, status, content=b""):
            self.send_response(status)
            if 300 <= status < 400:
                self.send_header("Location", "https://must-not-follow.invalid/")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def handle_request(self):
            state.requests.append((self.command, self.path, dict(self.headers)))
            content = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.headers.get("Authorization") != authorization:
                return self.send_body(401)
            if self.command == state.fail_method:
                return self.send_body(state.fail_status)
            name = self.path.rsplit("/", 1)[-1]
            if self.command == "MKCOL":
                return self.send_body(405)
            if self.command == "PUT":
                if name in state.files and self.headers.get("If-None-Match") == "*":
                    return self.send_body(412)
                state.files[name] = content
                return self.send_body(201)
            if self.command == "GET":
                body = b"corrupted" if state.corrupt_get else state.files.get(name, b"")
                return self.send_body(200 if name in state.files else 404, body)
            if self.command == "PROPFIND":
                if state.xml is not None:
                    return self.send_body(207, state.xml)
                def entry(href, collection=False):
                    kind = "<d:collection/>" if collection else ""
                    return (f"<d:response><d:href>{escape(href)}</d:href><d:propstat>"
                            f"<d:prop><d:resourcetype>{kind}</d:resourcetype></d:prop>"
                            "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>")
                directory = "/dav/textile-accounting/"
                entries = entry(directory, True)
                if self.headers.get("Depth") != "0":
                    entries += "".join(entry(directory + name) for name in state.files)
                    entries += "".join(entry(href) for href in state.extra_hrefs)
                body = f'<d:multistatus xmlns:d="DAV:">{entries}</d:multistatus>'.encode()
                return self.send_body(207, body)
            self.send_body(405)

        do_MKCOL = do_PROPFIND = do_PUT = do_GET = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}/dav/"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def service(tmp_path, dav, monkeypatch):
    if os.name != "nt":
        def protect(value, *, decrypt=False):
            return value[10:] if decrypt else b"protected:" + value
        monkeypatch.setattr(cloud, "protect_password", protect)
    instance = cloud.CloudBackupService(tmp_path)
    instance.settings.save({"url": dav.url, "username": "backup-user",
                            "password": "test-app-password", "auto_backup": True})
    cloud.atomic_write(tmp_path / "records.json", cloud.json_bytes(DATA["records"]))
    cloud.atomic_write(tmp_path / "printer_settings.json", cloud.json_bytes(DATA["printer_settings"]))
    return instance


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_windows_password_protection():
    secret = "测试应用密码".encode()
    encrypted = cloud.protect_password(secret)
    assert secret not in encrypted
    assert cloud.protect_password(encrypted, decrypt=True) == secret
    with pytest.raises(cloud.CloudBackupError):
        cloud.protect_password(b"invalid", decrypt=True)


def test_settings_round_trip_and_corrupt_password_disables_auto_backup(service):
    settings = service.settings.load()
    assert settings["password"] == "test-app-password"
    raw = service.settings.path.read_text(encoding="utf-8")
    assert "test-app-password" not in raw
    saved = json.loads(raw)
    saved["protected_password"] = "invalid!"
    service.settings.path.write_text(json.dumps(saved), encoding="utf-8")
    assert service.settings.load()["auto_backup"] is False
    assert "error" in service.settings.load()


@pytest.mark.parametrize("url", ["http://example.com/dav", "https://user:secret@example.com/",
                                  "https://example.com/?key=secret", "https://example.com/#x",
                                  "https://example.com:bad/", "https://example.com:/",
                                  "https://bad host/", "https://example.com/\nsecret"])
def test_rejects_unsafe_urls(url):
    with pytest.raises(cloud.CloudBackupError):
        cloud.normalize_url(url)


def test_normalizes_unicode_directory():
    assert cloud.normalize_url(" https://example.com/备份 ") == "https://example.com/%E5%A4%87%E4%BB%BD/"
    assert cloud.normalize_url("https://EXAMPLE.COM/dav") == "https://example.com/dav/"


def test_backup_versions_deduplication_and_restore(service, dav):
    first = service.backup()
    assert cloud.BACKUP_NAME.fullmatch(first)
    downloaded = service.download(first)
    assert {key: downloaded[key] for key in DATA} == DATA
    assert downloaded["backup_identity"] == {**service.identity(), "webdav_account": "backup-user"}
    count = len(dav.requests)
    assert service.backup(force=False) is None
    assert len(dav.requests) == count
    second = service.backup()
    assert second != first
    assert [info["name"] for info in service.list_backups()] == sorted([first, second], reverse=True)
    for method, _, headers in dav.requests:
        if method == "PUT":
            assert headers["If-None-Match"] == "*"
    assert "password" not in json.loads(dav.files[first])["data"]
    changed = copy.deepcopy(DATA)
    changed["records"][0]["note"] = "修改后"
    cloud.atomic_write(service.data_dir / "records.json", cloud.json_bytes(changed["records"]))
    third = service.backup(force=False)
    assert third not in (None, first, second)
    safety_dir = service.restore(service.download(first))
    assert service.read_local_data() == DATA
    assert json.loads((safety_dir / "records.json").read_bytes()) == changed["records"]
    assert (safety_dir / "printer_settings.json").is_file()
    assert service.settings.load()["password"] == "test-app-password"


@pytest.mark.parametrize("failure", ["upload", "verify"])
def test_failed_backup_does_not_record_success(service, dav, failure):
    if failure == "upload":
        dav.fail_method, dav.fail_status = "PUT", 507
    else:
        dav.corrupt_get = True
    with pytest.raises(cloud.CloudBackupError):
        service.backup()
    assert service.state() == {}
    assert service.read_local_data() == DATA


@pytest.mark.parametrize("status", [401, 403, 302])
def test_cloud_errors_are_clean_and_redirects_not_followed(service, dav, status):
    dav.fail_method, dav.fail_status = "MKCOL", status
    with pytest.raises(cloud.CloudBackupError) as caught:
        service.backup()
    assert "test-app-password" not in str(caught.value)
    assert len(dav.requests) == 1
    assert service.state() == {}


def test_corrupt_local_data_stops_before_upload(service, dav):
    (service.data_dir / "records.json").write_text("broken", encoding="utf-8")
    with pytest.raises(cloud.CloudBackupError):
        service.backup()
    assert not dav.requests


def test_invalid_download_and_filename_do_not_touch_local_data(service, dav):
    name = service.backup()
    envelope = json.loads(dav.files[name])
    envelope["data"]["records"][0]["total_amount"] = 1
    dav.files[name] = cloud.json_bytes(envelope)
    with pytest.raises(cloud.CloudBackupError):
        service.download(name)
    count = len(dav.requests)
    with pytest.raises(cloud.CloudBackupError):
        service.download("../records.json")
    assert len(dav.requests) == count
    assert service.read_local_data() == DATA
    assert not (service.data_dir / "backups").exists()


def test_directory_listing_rejects_foreign_hrefs_and_invalid_xml(service, dav):
    name = service.backup()
    foreign = "backup-20260101T120000000000Z-12345678.json"
    dav.extra_hrefs = [f"https://other.invalid/dav/textile-accounting/{foreign}",
                       f"/other/{foreign}", f"/dav/textile-accounting/sub/{foreign}"]
    assert [info["name"] for info in service.list_backups()] == [name]
    dav.xml = b'<!DOCTYPE x [<!ENTITY x "bad">]><d:multistatus xmlns:d="DAV:"/>'
    with pytest.raises(cloud.CloudBackupError):
        service.list_backups()
    dav.xml = b'<d:multistatus xmlns:d="DAV:"/>'
    with pytest.raises(cloud.CloudBackupError):
        service.list_backups()


@pytest.mark.parametrize("record", [{"id": True}, {"quantity": "2"}, {"unit_price": float("nan")},
                                      {"date": "2026-02-30"}, {"items": [{}]}])
def test_invalid_record_cannot_be_restored(service, record):
    invalid = copy.deepcopy(DATA)
    invalid["records"][0].update(record)
    with pytest.raises(cloud.CloudBackupError):
        service.restore(invalid)
    assert service.read_local_data() == DATA
    assert not (service.data_dir / "backups").exists()


@pytest.mark.parametrize("printer_exists", [True, False])
def test_restore_write_failure_rolls_back_exact_original_files(service, monkeypatch, printer_exists):
    records_path = service.data_dir / "records.json"
    printer_path = service.data_dir / "printer_settings.json"
    original_records = b"original corrupt file, preserved byte for byte"
    records_path.write_bytes(original_records)
    original_printer = printer_path.read_bytes() if printer_exists else None
    if not printer_exists:
        printer_path.unlink()
    write = cloud.atomic_write
    failed = False

    def fail_once(path, content):
        nonlocal failed
        if path == printer_path and not failed:
            failed = True
            raise OSError("simulated disk failure")
        write(path, content)

    monkeypatch.setattr(cloud, "atomic_write", fail_once)
    with pytest.raises(cloud.CloudBackupError, match="已还原"):
        service.restore(DATA)
    assert records_path.read_bytes() == original_records
    assert (printer_path.read_bytes() if printer_path.exists() else None) == original_printer
    assert next((service.data_dir / "backups").glob("*/records.json")).read_bytes() == original_records


def test_response_size_limit(service, dav):
    name = service.backup()
    client = cloud.WebDAVClient(service.settings.load())
    with pytest.raises(cloud.CloudBackupError, match="过大"):
        client.request("GET", name, limit=10)
    assert urlsplit(client.directory).hostname == "127.0.0.1"


def test_identity_is_stable_and_renaming_triggers_backup(service, dav):
    original = service.identity()
    assert cloud.CloudBackupService(service.data_dir).identity() == original
    first = service.backup()
    changed = service.save_identity(" 门店账本 ", " 前台电脑 ")
    assert changed == {**original, "ledger_name": "门店账本", "device_name": "前台电脑"}
    second = service.backup(force=False)
    assert second not in (None, first)
    assert service.backup(force=False) is None
    assert service.download(second)["backup_identity"]["ledger_id"] == original["ledger_id"]


@pytest.mark.parametrize("ledger,device", [("", "电脑"), ("账本", "  "), ("账本\n其他", "电脑"), ("账" * 81, "电脑")])
def test_identity_names_are_validated(service, ledger, device):
    original = service.identity()
    with pytest.raises(cloud.CloudBackupError):
        service.save_identity(ledger, device)
    assert service.identity() == original


def test_corrupt_local_identity_is_preserved_and_stops_upload(service, dav):
    path = service.data_dir / "backup_identity.json"
    path.write_bytes(b"broken identity")
    with pytest.raises(cloud.CloudBackupError, match="账本身份"):
        service.backup()
    assert not dav.requests
    assert path.read_bytes() == b"broken identity"


def test_identity_fields_remain_accessible_while_backup_is_busy(service):
    with ThreadPoolExecutor(max_workers=1) as pool:
        with service._lock:
            identity = pool.submit(service.save_identity, "门店账本", "前台电脑").result(timeout=2)
    assert identity["ledger_name"] == "门店账本"
    assert service.identity() == identity


def test_history_reads_small_summaries_and_marks_damaged_index(service, dav):
    service.save_identity("门店账本", "前台电脑")
    name = service.backup()
    dav.requests.clear()
    info, = service.list_backups()
    assert info["record_count"] == 1
    assert info["backup_identity"]["ledger_name"] == "门店账本"
    assert info["backup_identity"]["device_name"] == "前台电脑"
    assert all(method != "GET" or path.endswith(".meta.json") for method, path, _ in dav.requests)
    dav.files[name + ".meta.json"] = b"damaged index"
    assert service.list_backups() == [{"name": name, "metadata_error": True}]
    assert service.download(name)["backup_identity"]["ledger_name"] == "门店账本"


def test_restore_on_another_computer_keeps_device_and_login(service, dav, tmp_path):
    service.save_identity("门店账本", "旧电脑")
    name = service.backup()
    origin = service.identity()
    other = cloud.CloudBackupService(tmp_path / "other-computer")
    other.save_identity("新账本", "新电脑")
    local = other.identity()
    other.settings.save({"url": "https://other.example/dav/", "username": "another-user",
                         "password": "different-password", "auto_backup": False})
    login = other.settings.load()
    safety = other.restore(service.download(name))
    assert other.identity() == {**local, "ledger_id": origin["ledger_id"], "ledger_name": origin["ledger_name"]}
    assert other.settings.load() == login
    assert other.read_local_data() == DATA
    assert json.loads((safety / "backup_identity.json").read_bytes()) == local


def test_legacy_backup_can_be_identified_as_unknown_and_restored(service, dav):
    name = "backup-20260101T120000000000Z-12345678.json"
    dav.files[name] = cloud.json_bytes({"app": "textile-accounting", "version": 1,
                                       "created_at": "2026-01-01T12:00:00+00:00", "data": DATA,
                                       "sha256": cloud.hashlib.sha256(cloud.json_bytes(DATA)).hexdigest()})
    identity = service.save_identity("保留名称", "本机")
    assert service.list_backups() == [{"name": name}]
    assert service.download(name) == DATA
    service.restore(service.download(name))
    assert service.read_local_data() == DATA
    assert service.identity() == identity


@pytest.mark.parametrize("key,value", [("ledger_id", "../another"), ("device_name", []), ("ledger_name", ""),
                                      ("webdav_account", "user\nother")])
def test_invalid_source_metadata_is_rejected_before_restore(service, dav, key, value):
    name = service.backup()
    payload = json.loads(dav.files[name])
    payload["data"]["backup_identity"][key] = value
    payload["sha256"] = cloud.hashlib.sha256(cloud.json_bytes(payload["data"])).hexdigest()
    dav.files[name] = cloud.json_bytes(payload)
    identity = service.identity()
    with pytest.raises(cloud.CloudBackupError):
        service.download(name)
    with pytest.raises(cloud.CloudBackupError):
        service.restore(payload["data"])
    assert service.identity() == identity
    assert service.read_local_data() == DATA
    assert not (service.data_dir / "backups").exists()


def test_failed_identity_restore_rolls_back_data_and_identity(service, monkeypatch):
    identity_path = service.data_dir / "backup_identity.json"
    original = service.identity()
    changed = copy.deepcopy(DATA)
    changed["records"][0]["note"] = "云端内容"
    changed["backup_identity"] = {**original, "ledger_id": "1" * 32, "ledger_name": "云端账本"}
    original_bytes = identity_path.read_bytes()
    write = cloud.atomic_write
    failed = False

    def fail_once(path, content):
        nonlocal failed
        if path == identity_path and not failed:
            failed = True
            raise OSError("simulated identity write failure")
        write(path, content)

    monkeypatch.setattr(cloud, "atomic_write", fail_once)
    with pytest.raises(cloud.CloudBackupError, match="已还原"):
        service.restore(changed)
    assert service.read_local_data() == DATA
    assert identity_path.read_bytes() == original_bytes
    assert next((service.data_dir / "backups").glob("*/backup_identity.json")).read_bytes() == original_bytes


def test_failed_index_upload_keeps_backup_but_does_not_mark_success(service, dav, monkeypatch):
    request = cloud.WebDAVClient.request

    def fail_index(self, method, name="", **kwargs):
        if method == "PUT" and name.endswith(".meta.json"):
            raise cloud.CloudBackupError("来源索引上传失败")
        return request(self, method, name, **kwargs)

    monkeypatch.setattr(cloud.WebDAVClient, "request", fail_index)
    with pytest.raises(cloud.CloudBackupError):
        service.backup()
    assert service.state() == {}
    name, = dav.files
    assert service.download(name)["records"] == DATA["records"]
    assert service.list_backups() == [{"name": name}]

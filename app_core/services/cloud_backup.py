from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import math
import os
import re
import socket
import tempfile
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


class CloudBackupError(Exception):
    pass


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")


def protect_password(value: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise CloudBackupError("当前系统暂不支持安全保存应用密码，请在 Windows 上配置。")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise CloudBackupError("应用密码加密或解密失败，请重新填写应用密码。")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(result.data)


def normalize_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (parsed.scheme != "https" and not local_http) or not parsed.hostname:
            raise ValueError
        if parsed.netloc.endswith(":") or port == 0 or any(char.isspace() for char in parsed.netloc):
            raise ValueError
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ValueError
        if any(ord(char) < 32 or char == "\\" for char in value):
            raise ValueError
    except ValueError:
        raise CloudBackupError("请填写有效的 HTTPS WebDAV 地址，账号和密码请填写在对应输入框。") from None
    path = quote(parsed.path.rstrip("/") + "/", safe="/%:@")
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), path, "", ""))


class CloudBackupSettingsStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "cloud_backup.json"

    def load(self) -> dict[str, Any]:
        settings = {"url": "", "username": "", "password": "", "auto_backup": False}
        if not self.path.exists():
            return settings
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict) or any(not isinstance(saved[key], str) for key in ("url", "username")):
                raise ValueError
            if type(saved["auto_backup"]) is not bool:
                raise ValueError
            settings.update({key: saved[key] for key in ("url", "username", "auto_backup")})
            if saved.get("protected_password"):
                encrypted = base64.b64decode(saved["protected_password"], validate=True)
                settings["password"] = protect_password(encrypted, decrypt=True).decode("utf-8")
            if settings["auto_backup"] and not all(settings[key] for key in ("url", "username", "password")):
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError, CloudBackupError):
            settings["auto_backup"] = False
            settings["error"] = "云端备份配置无法读取，请重新填写并保存。"
        return settings

    def save(self, settings: dict[str, Any]) -> dict[str, Any]:
        url = str(settings.get("url", "")).strip()
        username = str(settings.get("username", "")).strip()
        password = str(settings.get("password", ""))
        automatic = bool(settings.get("auto_backup", False))
        if url:
            url = normalize_url(url)
        if ":" in username:
            raise CloudBackupError("WebDAV 账号不能包含冒号。")
        if automatic and not all((url, username, password)):
            raise CloudBackupError("开启自动备份前，请填写 WebDAV 地址、账号和应用密码。")
        saved = {"url": url, "username": username, "auto_backup": automatic,
                 "protected_password": base64.b64encode(protect_password(password.encode("utf-8"))).decode("ascii") if password else ""}
        atomic_write(self.path, json_bytes(saved))
        return {"url": url, "username": username, "password": password, "auto_backup": automatic}


BACKUP_NAME = re.compile(r"backup-\d{8}T\d{12}Z-[0-9a-f]{8}\.json\Z")
MAX_BACKUP_BYTES = 50 * 1024 * 1024


def validate_backup_identity(value: Any) -> None:
    try:
        for key in ("ledger_id", "device_id"):
            if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{32}", value[key]):
                raise ValueError
        for key in ("ledger_name", "device_name"):
            name = value[key]
            if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(char) < 32 for char in name):
                raise ValueError
        if "webdav_account" in value and (not isinstance(value["webdav_account"], str) or
                                          len(value["webdav_account"]) > 255 or
                                          any(ord(char) < 32 for char in value["webdav_account"])):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise CloudBackupError("账本或来源电脑信息无效，请检查名称和编号。") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Credentials must never follow a server redirect.
        return None


class WebDAVClient:
    def __init__(self, settings: dict[str, Any]):
        self.directory = normalize_url(settings.get("url", "")) + "textile-accounting/"
        username = str(settings.get("username", ""))
        password = str(settings.get("password", ""))
        if not username or not password or ":" in username:
            raise CloudBackupError("请填写有效的账号和 WebDAV 应用密码。")
        self.authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        self.opener = build_opener(NoRedirect())

    def request(self, method: str, name: str = "", *, content: bytes | None = None,
                headers: dict[str, str] | None = None, accepted: tuple[int, ...] = (200,),
                limit: int = MAX_BACKUP_BYTES) -> bytes:
        if name and not BACKUP_NAME.fullmatch(name.removesuffix(".meta.json")):
            raise CloudBackupError("备份文件名无效。")
        request = Request(self.directory + name, data=content, method=method,
                          headers={"Authorization": self.authorization, **(headers or {})})
        try:
            with self.opener.open(request, timeout=30) as response:
                if response.status not in accepted:
                    raise CloudBackupError("云端返回了非预期的响应，请检查 WebDAV 地址。")
                result = response.read(limit + 1)
                if len(result) > limit:
                    raise CloudBackupError("云端文件过大，已停止读取。")
                return result
        except HTTPError as error:
            code = error.code
            error.close()
            if code in accepted:
                return b""
            messages = {401: "云端认证失败，请检查账号和应用密码。", 403: "没有云端目录的读写权限。",
                        404: "云端目录或备份不存在，请检查 WebDAV 地址。", 409: "WebDAV 上级目录不存在，请填写已有目录地址。",
                        412: "同名备份已存在，请重新备份。", 429: "云端请求过于频繁，请稍后重试。",
                        507: "云端存储空间不足。"}
            if 300 <= code < 400:
                raise CloudBackupError("WebDAV 地址发生重定向，请填写服务商提供的最终 HTTPS 地址。") from None
            raise CloudBackupError(messages.get(code, f"云端请求失败（HTTP {code}）。")) from None
        except (OSError, HTTPException):
            raise CloudBackupError("无法连接云端，请检查网络、HTTPS 证书和 WebDAV 地址。") from None

    def ensure_directory(self) -> None:
        self.request("MKCOL", accepted=(201, 405))
        self.list_backups(depth="0")

    def list_backups(self, depth: str = "1") -> list[str]:
        content = b'<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
        body = self.request("PROPFIND", content=content,
                            headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
                            accepted=(207,), limit=2 * 1024 * 1024)
        try:
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise ValueError
            root = ET.fromstring(body)
            if root.tag != "{DAV:}multistatus":
                raise ValueError
        except (ET.ParseError, ValueError):
            raise CloudBackupError("云端没有返回有效的 WebDAV 目录信息。") from None
        names = set()
        directory = urlsplit(self.directory)
        found_directory = False
        for response in root.findall("{DAV:}response"):
            href = response.findtext("{DAV:}href", "")
            target = urlsplit(urljoin(self.directory, href))
            if (target.scheme, target.netloc.lower()) != (directory.scheme, directory.netloc):
                continue
            successful = [prop.find("{DAV:}prop") for prop in response.findall("{DAV:}propstat")
                          if " 200 " in prop.findtext("{DAV:}status", "")]
            path = unquote(target.path)
            parent = unquote(directory.path)
            if path.rstrip("/") == parent.rstrip("/"):
                found_directory = any(prop is not None and prop.find("{DAV:}resourcetype/{DAV:}collection") is not None for prop in successful)
            elif path.startswith(parent):
                name = path[len(parent):]
                if successful and BACKUP_NAME.fullmatch(name):
                    names.add(name)
        if not found_directory:
            raise CloudBackupError("云端备份目录不可读取，请检查地址和目录权限。")
        return sorted(names, reverse=True)


def validate_data(data: Any) -> None:
    try:
        records = data["records"]
        settings = data["printer_settings"]
        if not isinstance(records, list) or not isinstance(settings, dict):
            raise ValueError
        identifiers = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError
            identifier = record["id"]
            if type(identifier) is not int or identifier < 0 or identifier in identifiers:
                raise ValueError
            identifiers.add(identifier)
            datetime.strptime(record["date"], "%Y-%m-%d")
            if type(record["quantity"]) is not int:
                raise ValueError
            for key in ("unit_price", "total_amount"):
                if type(record[key]) not in (int, float) or not math.isfinite(record[key]):
                    raise ValueError
            for key in ("note", "customer", "created_at"):
                if key in record and not isinstance(record[key], str):
                    raise ValueError
            if "type" in record and record["type"] not in {"sale", "return", "mixed"}:
                raise ValueError
            if "original_record_id" in record and type(record["original_record_id"]) is not int:
                raise ValueError
            if "items" in record:
                if not isinstance(record["items"], list):
                    raise ValueError
                for item in record["items"]:
                    if not isinstance(item, dict) or type(item["quantity"]) is not int or type(item["unit_price"]) not in (int, float) or not math.isfinite(item["unit_price"]):
                        raise ValueError
        for key in ("shop_name", "shop_address", "shop_phone", "footer_text", "printer_name"):
            if key in settings and not isinstance(settings[key], str):
                raise ValueError
        for key in ("auto_print", "compact_mode"):
            if key in settings and type(settings[key]) is not bool:
                raise ValueError
        if "paper_width" in settings and settings["paper_width"] not in (58, 76, 80):
            raise ValueError
        if "customers" in settings and (not isinstance(settings["customers"], list) or any(not isinstance(name, str) for name in settings["customers"])):
            raise ValueError
        if "backup_identity" in data:
            validate_backup_identity(data["backup_identity"])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise CloudBackupError("备份中的账目或设置格式无效，未修改本地数据。") from None


class CloudBackupService:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.settings = CloudBackupSettingsStore(data_dir)
        self._lock = threading.Lock()
        self._identity_lock = threading.RLock()

    def identity(self) -> dict[str, str]:
        with self._identity_lock:
            path = self.data_dir / "backup_identity.json"
            try:
                if path.exists():
                    value = json.loads(path.read_text(encoding="utf-8"))
                    validate_backup_identity(value)
                else:
                    value = {"ledger_id": uuid4().hex, "ledger_name": "我的账本",
                             "device_id": uuid4().hex, "device_name": socket.gethostname() or "本机"}
                    validate_backup_identity(value)
                    atomic_write(path, json_bytes(value))
            except (OSError, ValueError, CloudBackupError):
                raise CloudBackupError("本地账本身份无法读取或保存，已停止操作；请保留 backup_identity.json 后检查文件。") from None
            return {key: value[key] for key in ("ledger_id", "ledger_name", "device_id", "device_name")}

    def save_identity(self, ledger_name: str, device_name: str) -> dict[str, str]:
        with self._identity_lock:
            value = {**self.identity(), "ledger_name": ledger_name.strip(), "device_name": device_name.strip()}
            validate_backup_identity(value)
            atomic_write(self.data_dir / "backup_identity.json", json_bytes(value))
            return value

    def state(self) -> dict[str, Any]:
        try:
            value = json.loads((self.data_dir / "cloud_backup_state.json").read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def read_local_data(self) -> dict[str, Any]:
        try:
            records = json.loads((self.data_dir / "records.json").read_text(encoding="utf-8"))
            settings_path = self.data_dir / "printer_settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
        except (OSError, ValueError):
            raise CloudBackupError("本地账目或打印设置无法读取，已停止备份。") from None
        data = {"records": records, "printer_settings": settings}
        validate_data(data)
        return data

    def backup(self, *, force: bool = True) -> str | None:
        with self._lock:
            settings = self.settings.load()
            client = WebDAVClient(settings)
            data = self.read_local_data()
            data["backup_identity"] = {**self.identity(), "webdav_account": settings["username"]}
            validate_backup_identity(data["backup_identity"])
            digest = hashlib.sha256(json_bytes(data)).hexdigest()
            target = hashlib.sha256((client.directory + settings["username"]).encode("utf-8")).hexdigest()
            previous = self.state()
            if not force and previous.get("digest") == digest and previous.get("target") == target:
                return None
            now = datetime.now(timezone.utc)
            payload = json_bytes({"app": "textile-accounting", "version": 1, "created_at": now.isoformat(),
                                  "data": data, "sha256": digest})
            if len(payload) > MAX_BACKUP_BYTES:
                raise CloudBackupError("本地数据超过 50 MB，无法使用当前备份功能。")
            name = f"backup-{now.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}.json"
            summary = json_bytes({"backup": name, "backup_identity": data["backup_identity"],
                                  "record_count": len(data["records"])})
            client.ensure_directory()
            # 历史列表读取小型来源索引，避免下载每份完整账本。
            for remote_name, content in ((name, payload), (name + ".meta.json", summary)):
                client.request("PUT", remote_name, content=content,
                               headers={"Content-Type": "application/json; charset=utf-8", "If-None-Match": "*"},
                               accepted=(201, 204))
                if client.request("GET", remote_name) != content:
                    raise CloudBackupError("云端备份或来源索引校验失败，请重新备份。")
            atomic_write(self.data_dir / "cloud_backup_state.json", json_bytes({
                "last_backup": now.astimezone().strftime("%Y-%m-%d %H:%M:%S"), "name": name,
                "digest": digest, "target": target}))
            return name

    def list_backups(self) -> list[dict[str, Any]]:
        client = WebDAVClient(self.settings.load())
        client.ensure_directory()
        backups = []
        for name in client.list_backups():
            info: dict[str, Any] = {"name": name}
            body = client.request("GET", name + ".meta.json", accepted=(200, 404), limit=16 * 1024)
            if body:
                try:
                    summary = json.loads(body)
                    if summary["backup"] != name or type(summary["record_count"]) is not int or summary["record_count"] < 0:
                        raise ValueError
                    validate_backup_identity(summary["backup_identity"])
                    info.update({key: summary[key] for key in ("backup_identity", "record_count")})
                except (ValueError, KeyError, TypeError, CloudBackupError):
                    info["metadata_error"] = True
            backups.append(info)
        return backups

    def download(self, name: str) -> dict[str, Any]:
        body = WebDAVClient(self.settings.load()).request("GET", name)
        try:
            value = json.loads(body)
            if value["app"] != "textile-accounting" or type(value["version"]) is not int or value["version"] != 1:
                raise ValueError
            data = value["data"]
            if hashlib.sha256(json_bytes(data)).hexdigest() != value["sha256"]:
                raise ValueError
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise CloudBackupError("云端备份格式或校验不通过，未修改本地数据。") from None
        validate_data(data)
        return data

    def restore(self, data: dict[str, Any]) -> Path:
        validate_data(data)
        with self._lock:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
            safety_dir = self.data_dir / "backups" / ("before-restore-" + timestamp)
            safety_dir.mkdir(parents=True)
            originals = {}
            for name in ("records.json", "printer_settings.json", "backup_identity.json"):
                path = self.data_dir / name
                originals[name] = path.read_bytes() if path.exists() else None
                if originals[name] is not None:
                    atomic_write(safety_dir / name, originals[name])
            try:
                identity = self.identity()
                if "backup_identity" in data:
                    identity.update({key: data["backup_identity"][key] for key in ("ledger_id", "ledger_name")})
                atomic_write(self.data_dir / "records.json", json_bytes(data["records"]))
                atomic_write(self.data_dir / "printer_settings.json", json_bytes(data["printer_settings"]))
                atomic_write(self.data_dir / "backup_identity.json", json_bytes(identity))
            except OSError:
                try:
                    for name, content in originals.items():
                        if content is None:
                            (self.data_dir / name).unlink(missing_ok=True)
                        else:
                            atomic_write(self.data_dir / name, content)
                except OSError:
                    raise CloudBackupError(f"恢复写入失败，本地回滚未完成；原文件副本位于：{safety_dir}") from None
                raise CloudBackupError("恢复写入失败，已还原本地原始文件。") from None
            return safety_dir

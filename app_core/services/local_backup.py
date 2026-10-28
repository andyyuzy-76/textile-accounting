"""本地目录备份。

沿用 ``cloud_backup`` 的账本身份、数据校验与恢复流程，只把「备份存放位置」
从 WebDAV 网盘换成本机（或移动硬盘、同步盘）上的普通文件夹。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app_core.services.cloud_backup import (
    BACKUP_NAME,
    MAX_BACKUP_BYTES,
    CloudBackupError,
    CloudBackupService,
    atomic_write,
    json_bytes,
    validate_backup_identity,
    validate_data,
)

DEFAULT_KEEP = 30
MIN_KEEP = 5
MAX_KEEP = 200


def default_directory() -> Path:
    """默认备份目录：用户主目录下的独立文件夹。"""
    return Path.home() / "家纺记账备份"


def parse_directory(value: Any, data_dir: Path) -> Path:
    """校验用户填写的备份目录，返回规范化后的绝对路径（不创建目录）。"""
    text = str(value or "").strip().strip('"').strip()
    if not text:
        raise CloudBackupError("请先选择本地备份目录。")
    if any(ord(char) < 32 for char in text):
        raise CloudBackupError("备份目录路径包含换行等控制字符，请重新选择。")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise CloudBackupError("请填写完整的目录路径，例如 D:\\家纺记账备份。")
    try:
        resolved = path.resolve()
    except OSError:
        raise CloudBackupError("备份目录路径无法解析，请重新选择。") from None
    if resolved == Path(resolved.anchor):
        raise CloudBackupError("不能直接备份到磁盘根目录，请选择或新建一个专用文件夹。")
    data_root = data_dir.resolve()
    if resolved == data_root or data_root in resolved.parents:
        raise CloudBackupError("备份目录不能放在程序数据目录内，请换一个文件夹（建议另一个磁盘或同步盘）。")
    return resolved


def ensure_directory(path: Path) -> None:
    """创建目录并做一次写入探测，确保备份不会中途失败。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise CloudBackupError("备份目录无法创建，请检查路径、磁盘和文件夹权限。") from None
    if not path.is_dir():
        raise CloudBackupError("所选路径不是文件夹，请重新选择备份目录。")
    probe = None
    try:
        descriptor, probe = tempfile.mkstemp(dir=path, prefix=".write-test.")
        os.close(descriptor)
    except OSError:
        raise CloudBackupError("备份目录不可写入，请检查文件夹权限或换一个目录。") from None
    finally:
        if probe:
            Path(probe).unlink(missing_ok=True)


def parse_keep(value: Any) -> int:
    if type(value) is bool:
        raise CloudBackupError("保留份数应为整数。")
    try:
        keep = int(value)
    except (TypeError, ValueError):
        raise CloudBackupError("保留份数应为整数。") from None
    if not MIN_KEEP <= keep <= MAX_KEEP:
        raise CloudBackupError(f"保留份数应在 {MIN_KEEP}–{MAX_KEEP} 之间。")
    return keep


class LocalBackupSettingsStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "local_backup.json"

    def load(self) -> dict[str, Any]:
        settings: dict[str, Any] = {"directory": str(default_directory()), "auto_backup": True,
                                    "keep": DEFAULT_KEEP}
        if not self.path.exists():
            return settings
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise ValueError
            directory = saved["directory"]
            automatic = saved["auto_backup"]
            if not isinstance(directory, str) or not directory.strip() or type(automatic) is not bool:
                raise ValueError
            settings.update({"directory": directory, "auto_backup": automatic,
                             "keep": parse_keep(saved.get("keep", DEFAULT_KEEP))})
        except (OSError, ValueError, KeyError, TypeError, CloudBackupError):
            settings["auto_backup"] = False
            settings["error"] = "本地备份配置无法读取，请重新选择备份目录并保存。"
        return settings

    def save(self, settings: dict[str, Any]) -> dict[str, Any]:
        directory = parse_directory(settings.get("directory"), self.data_dir)
        automatic = bool(settings.get("auto_backup", False))
        keep = parse_keep(settings.get("keep", DEFAULT_KEEP))
        ensure_directory(directory)
        saved = {"directory": str(directory), "auto_backup": automatic, "keep": keep}
        atomic_write(self.path, json_bytes(saved))
        return dict(saved)


class LocalBackupService(CloudBackupService):
    """把备份写到本地文件夹；身份、校验与恢复逻辑复用云端实现。"""

    STATE_NAME = "local_backup_state.json"

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self.settings = LocalBackupSettingsStore(data_dir)

    def state(self) -> dict[str, Any]:
        try:
            value = json.loads((self.data_dir / self.STATE_NAME).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def directory(self) -> Path:
        return parse_directory(self.settings.load().get("directory"), self.data_dir)

    @staticmethod
    def _write_verified(path: Path, content: bytes) -> None:
        try:
            atomic_write(path, content)
            stored = path.read_bytes()
        except OSError:
            raise CloudBackupError("备份文件写入或读取失败，请检查磁盘空间和文件夹权限。") from None
        if stored != content:
            raise CloudBackupError("备份文件写入后校验不一致，请检查磁盘是否正常。")

    @staticmethod
    def _prune(directory: Path, keep: int, keep_name: str) -> None:
        """只清理本程序生成的备份文件，失败不影响本次备份结果。"""
        try:
            names = sorted((path.name for path in directory.iterdir()
                            if path.is_file() and BACKUP_NAME.fullmatch(path.name)), reverse=True)
        except OSError:
            return
        for name in names[keep:]:
            if name == keep_name:
                continue
            for target in (directory / name, directory / (name + ".meta.json")):
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass

    def backup(self, *, force: bool = True) -> str | None:
        with self._lock:
            settings = self.settings.load()
            if settings.get("error"):
                raise CloudBackupError(settings["error"])
            directory = parse_directory(settings.get("directory"), self.data_dir)
            data = self.read_local_data()
            data["backup_identity"] = self.identity()
            validate_backup_identity(data["backup_identity"])
            digest = hashlib.sha256(json_bytes(data)).hexdigest()
            target = hashlib.sha256(str(directory).encode("utf-8")).hexdigest()
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
            ensure_directory(directory)
            self._write_verified(directory / name, payload)
            self._write_verified(directory / (name + ".meta.json"), summary)
            self._prune(directory, parse_keep(settings.get("keep", DEFAULT_KEEP)), name)
            atomic_write(self.data_dir / self.STATE_NAME, json_bytes({
                "last_backup": now.astimezone().strftime("%Y-%m-%d %H:%M:%S"), "name": name,
                "digest": digest, "target": target, "directory": str(directory)}))
            return name

    def list_backups(self) -> list[dict[str, Any]]:
        directory = self.directory()
        if not directory.is_dir():
            raise CloudBackupError("备份目录不存在，请重新选择备份目录后保存。")
        try:
            names = sorted((path.name for path in directory.iterdir()
                            if path.is_file() and BACKUP_NAME.fullmatch(path.name)), reverse=True)
        except OSError:
            raise CloudBackupError("备份目录无法读取，请检查文件夹权限。") from None
        backups = []
        for name in names:
            info: dict[str, Any] = {"name": name}
            meta = directory / (name + ".meta.json")
            try:
                if meta.exists():
                    summary = json.loads(meta.read_text(encoding="utf-8"))
                    if summary["backup"] != name or type(summary["record_count"]) is not int or summary["record_count"] < 0:
                        raise ValueError
                    validate_backup_identity(summary["backup_identity"])
                    info.update({key: summary[key] for key in ("backup_identity", "record_count")})
            except (OSError, ValueError, KeyError, TypeError, CloudBackupError):
                info["metadata_error"] = True
            backups.append(info)
        return backups

    def download(self, name: str) -> dict[str, Any]:
        if not BACKUP_NAME.fullmatch(name):
            raise CloudBackupError("备份文件名无效。")
        path = self.directory() / name
        try:
            if path.stat().st_size > MAX_BACKUP_BYTES:
                raise CloudBackupError("备份文件过大，已停止读取。")
            body = path.read_bytes()
        except FileNotFoundError:
            raise CloudBackupError("备份文件不存在，可能已被移动或删除。") from None
        except OSError:
            raise CloudBackupError("备份文件无法读取，请检查磁盘和文件夹权限。") from None
        try:
            value = json.loads(body)
            if value["app"] != "textile-accounting" or type(value["version"]) is not int or value["version"] != 1:
                raise ValueError
            data = value["data"]
            if hashlib.sha256(json_bytes(data)).hexdigest() != value["sha256"]:
                raise ValueError
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise CloudBackupError("本地备份格式或校验不通过，未修改本地数据。") from None
        validate_data(data)
        return data

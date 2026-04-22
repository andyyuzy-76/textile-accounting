"""
自动更新模块
从GitHub仓库检查并下载最新版本
"""

import os
import json
import hashlib
import urllib.request
import urllib.error
import tempfile
import shutil
import subprocess
import sys
from datetime import datetime

# GitHub仓库信息
GITHUB_REPO = "andyyuzy-76/textile-accounting"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/version.json"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"
GITHUB_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# 本地版本文件路径
LOCAL_VERSION_FILE = "version.json"


def is_frozen_app():
    """是否运行于打包 exe 环境"""
    return bool(getattr(sys, "frozen", False))


def get_current_version():
    """获取当前版本号"""
    try:
        if os.path.exists(LOCAL_VERSION_FILE):
            with open(LOCAL_VERSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version", "1.0.0")
    except:
        pass
    return "1.0.0"


def get_remote_version():
    """获取远程最新版本号"""
    try:
        url = f"{GITHUB_RAW_URL}/version.json?t={datetime.now().timestamp()}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TextileAccounting/1.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("version", "1.0.0"), data.get("message", "")
    except Exception as e:
        print(f"检查更新失败: {e}")
        return None, None


def get_remote_manifest():
    """获取远程版本清单"""
    try:
        url = f"{GITHUB_RAW_URL}/version.json?t={datetime.now().timestamp()}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TextileAccounting/1.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def get_release_asset_download_url(asset_name: str):
    """获取最新 release 中指定资产的下载地址"""
    asset = get_release_asset_info(asset_name)
    if asset:
        return asset.get("browser_download_url")
    return None


def get_release_asset_info(asset_name: str):
    """获取最新 release 中指定资产的元信息"""
    try:
        req = urllib.request.Request(
            GITHUB_RELEASE_API_URL,
            headers={
                "User-Agent": "TextileAccounting/1.0",
                "Accept": "application/vnd.github+json",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        for asset in data.get("assets", []):
            if asset.get("name") == asset_name:
                return asset
        return None
    except Exception as e:
        print(f"获取 release 资产失败: {e}")
        return None


def verify_downloaded_file(
    file_path: str,
    *,
    expected_size: int | None = None,
    expected_digest: str | None = None,
):
    """校验下载文件大小和摘要"""
    if not os.path.exists(file_path):
        return False, "更新包不存在"

    if expected_size is not None:
        actual_size = os.path.getsize(file_path)
        if actual_size != expected_size:
            return (
                False,
                f"更新包大小校验失败（期望 {expected_size} 字节，实际 {actual_size} 字节）",
            )

    if expected_digest:
        algorithm, sep, digest_value = expected_digest.partition(":")
        if not sep or algorithm.lower() != "sha256" or not digest_value:
            return False, f"不支持的摘要格式: {expected_digest}"

        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        actual_digest = hasher.hexdigest()
        if actual_digest.lower() != digest_value.lower():
            return False, "更新包摘要校验失败，请重新尝试下载"

    return True, ""


def download_url(url, dest_path):
    """下载任意 URL 到目标文件"""
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TextileAccounting/1.0",
                "Cache-Control": "no-cache",
                "Accept": "application/octet-stream",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            with open(dest_path, "wb") as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"下载 {url} 失败: {e}")
        return False


def perform_binary_update(callback=None):
    """打包版 exe 自更新"""
    manifest = get_remote_manifest()
    if not manifest:
        return False, "无法获取远程版本信息"

    asset_name = manifest.get("exe_asset_name", "家纺记账系统-苹果风格.exe")
    asset_info = get_release_asset_info(asset_name)
    if not asset_info:
        return False, f"未找到发布资产: {asset_name}"
    asset_url = asset_info.get("browser_download_url")
    expected_size = asset_info.get("size")
    expected_digest = asset_info.get("digest")

    current_exe = sys.executable
    if not current_exe.lower().endswith(".exe"):
        return False, "当前不是 exe 运行环境"

    app_dir = os.path.dirname(current_exe)
    temp_dir = tempfile.mkdtemp()
    downloaded_exe = os.path.join(temp_dir, asset_name)
    updater_bat = os.path.join(temp_dir, "apply_update.bat")

    if callback:
        callback("正在下载软件更新包...")
    if not download_url(asset_url, downloaded_exe):
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, "下载更新包失败"

    if callback:
        callback("正在校验更新包...")
    verified, verify_message = verify_downloaded_file(
        downloaded_exe,
        expected_size=expected_size,
        expected_digest=expected_digest,
    )
    if not verified:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, verify_message

    script = f"""@echo off
chcp 65001 >nul
set EXE_PATH={current_exe}
set NEW_EXE={downloaded_exe}
ping 127.0.0.1 -n 3 >nul
copy /y "%NEW_EXE%" "%EXE_PATH%" >nul
if errorlevel 1 exit /b 1
set PYINSTALLER_RESET_ENVIRONMENT=1
start "" "%EXE_PATH%"
"""
    if callback:
        callback("正在应用更新...")
    with open(updater_bat, "w", encoding="utf-8") as f:
        f.write(script)

    if callback:
        callback("正在重启程序...")
    subprocess.Popen(
        ["cmd", "/c", updater_bat], creationflags=subprocess.CREATE_NO_WINDOW
    )
    os._exit(0)


def compare_versions(v1, v2):
    """比较版本号，返回True表示v2更新"""
    try:
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]

        # 补齐版本号长度
        while len(parts1) < 3:
            parts1.append(0)
        while len(parts2) < 3:
            parts2.append(0)

        for i in range(3):
            if parts2[i] > parts1[i]:
                return True
            elif parts2[i] < parts1[i]:
                return False
        return False
    except:
        return False


def download_file(filename, dest_path):
    """从GitHub下载文件"""
    url = f"{GITHUB_RAW_URL}/{filename}"
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TextileAccounting/1.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(dest_path, "wb") as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"下载 {filename} 失败: {e}")
        return False


def perform_update(callback=None):
    """执行更新操作"""
    if is_frozen_app():
        return perform_binary_update(callback)

    backup_dir = None
    temp_dir = None

    try:
        if callback:
            callback("正在下载更新...")

        # 需要更新的文件列表
        files_to_update = [
            "accounting.py",
            "accounting_flet.py",
            "auto_updater.py",
            "version.json",
            "build_flet.bat",
            "receipt_printer.py",
            "import_excel.py",
            "app_core/__init__.py",
            "app_core/paths.py",
            "app_core/storage.py",
            "app_core/services/__init__.py",
            "app_core/services/records.py",
            "app_core/services/importers.py",
            "app_core/services/printer_settings.py",
        ]

        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        backup_dir = tempfile.mkdtemp()

        # 下载所有文件
        for filename in files_to_update:
            if callback:
                callback(f"下载 {filename}...")
            dest_path = os.path.join(temp_dir, filename)
            if not download_file(filename, dest_path):
                if filename != "auto_updater.py":  # auto_updater.py 可能不存在旧版本
                    return False, f"下载 {filename} 失败"

        if callback:
            callback("正在应用更新...")

        # 备份当前文件
        for filename in files_to_update:
            if os.path.exists(filename):
                os.makedirs(
                    os.path.dirname(os.path.join(backup_dir, filename)), exist_ok=True
                )
                shutil.copy2(filename, os.path.join(backup_dir, filename))

        # 替换文件
        for filename in files_to_update:
            src = os.path.join(temp_dir, filename)
            if os.path.exists(src):
                os.makedirs(
                    os.path.dirname(filename), exist_ok=True
                ) if os.path.dirname(filename) else None
                shutil.copy2(src, filename)

        # 清理临时文件
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        if backup_dir and os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)

        return True, "更新成功！"

    except Exception as e:
        # 恢复备份
        if backup_dir and os.path.exists(backup_dir):
            for filename in [
                "accounting.py",
                "accounting_flet.py",
                "auto_updater.py",
                "version.json",
                "build_flet.bat",
                "receipt_printer.py",
                "import_excel.py",
                "app_core/__init__.py",
                "app_core/paths.py",
                "app_core/storage.py",
                "app_core/services/__init__.py",
                "app_core/services/records.py",
                "app_core/services/importers.py",
                "app_core/services/printer_settings.py",
            ]:
                backup_file = os.path.join(backup_dir, filename)
                if os.path.exists(backup_file):
                    os.makedirs(
                        os.path.dirname(filename), exist_ok=True
                    ) if os.path.dirname(filename) else None
                    shutil.copy2(backup_file, filename)
        # 清理
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        if backup_dir and os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        return False, f"更新出错: {e}"


def check_for_updates(silent=True):
    """检查是否有更新"""
    current = get_current_version()
    manifest = get_remote_manifest()

    if manifest is None:
        if not silent:
            return False, "无法连接到服务器", current, ""
        return False, None, current, ""

    remote = manifest.get("version", "1.0.0")
    message = manifest.get("message", "")

    has_update = compare_versions(current, remote)

    if has_update and is_frozen_app():
        asset_name = manifest.get("exe_asset_name", "家纺记账系统-苹果风格.exe")
        asset_info = get_release_asset_info(asset_name)
        if not asset_info:
            return (
                False,
                remote,
                current,
                f"检测到新版本 v{remote}，但更新包尚未发布，请稍后再试。",
            )

    return has_update, remote, current, message or ""


if __name__ == "__main__":
    # 测试更新检查
    has_update, remote, current, message = check_for_updates(silent=False)
    print(f"当前版本: {current}")
    print(f"最新版本: {remote}")
    print(f"有更新: {has_update}")
    if message:
        print(f"更新说明: {message}")

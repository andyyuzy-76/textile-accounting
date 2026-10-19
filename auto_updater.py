"""
自动更新模块
从GitHub仓库检查并下载最新版本
"""

import os
import json
import hashlib
import base64
from contextlib import suppress
import urllib.request
import urllib.error
import tempfile
import shutil
import subprocess
import sys
import time
from datetime import datetime

from app_core.paths import ensure_data_dir

# GitHub仓库信息
GITHUB_REPO = "andyyuzy-76/textile-accounting"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/version.json"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"
GITHUB_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# 本地版本文件路径
LOCAL_VERSION_FILE = "version.json"

BINARY_UPDATE_SCRIPT = r'''param([string]$ConfigPath)
$ErrorActionPreference = 'Stop'
$env:PSModulePath = [System.IO.Path]::Combine($PSHOME, 'Modules')
$jobDir = [System.IO.Path]::GetDirectoryName($ConfigPath)
$logPath = Join-Path $jobDir 'update.log'
$replaced = $false
function Write-Log([string]$message) {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) $message" -Encoding UTF8 -ErrorAction SilentlyContinue
}
try {
    $job = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ((Get-FileHash -LiteralPath $job.staged -Algorithm SHA256).Hash -ne $job.sha256) {
        throw '待安装文件校验失败，原程序未更改。'
    }
    Write-Log "等待程序退出：$($job.target)"
    [System.IO.File]::WriteAllText((Join-Path $jobDir 'ready'), 'ready')
    $owner = Get-Process -Id $job.owner_pid -ErrorAction SilentlyContinue
    if ($owner) { $owner | Wait-Process -Timeout 60 -ErrorAction Stop }
    $deadline = (Get-Date).AddSeconds(60)
    while ($true) {
        try {
            [System.IO.File]::Replace($job.staged, $job.target, $job.backup)
            $replaced = $true
            break
        } catch [System.IO.IOException] {
            if ((Get-Date) -ge $deadline) { throw }
            Start-Sleep -Milliseconds 500
        }
    }
    if ((Get-FileHash -LiteralPath $job.target -Algorithm SHA256).Hash -ne $job.sha256) {
        throw '替换后文件校验失败。'
    }
    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $job.target
    $start.WorkingDirectory = [System.IO.Path]::GetDirectoryName($job.target)
    $start.UseShellExecute = $false
    $app = [System.Diagnostics.Process]::Start($start)
    # shortcut: 仅检测三秒内的启动失败，需要确认界面就绪时再增加握手。
    if ($app.WaitForExit(3000) -and $app.ExitCode -ne 0) {
        throw "新版启动失败，退出码：$($app.ExitCode)"
    }
    Write-Log "更新完成，已启动：$($job.target)"
    Remove-Item -LiteralPath $job.backup -Force -ErrorAction SilentlyContinue
} catch {
    $message = "更新失败：$($_.Exception.Message)"
    if ($replaced) {
        try {
            [System.IO.File]::Replace($job.backup, $job.target, [NullString]::Value)
            $message += "`n已恢复旧程序。"
        } catch {
            $message += "`n自动回退失败：$($_.Exception.Message)`n旧程序保留在：$($job.backup)"
        }
    }
    $message += "`n更新包目录：$jobDir`n日志：$logPath"
    Write-Log $message
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($message, '家纺记账更新失败') | Out-Null
    exit 1
}
'''


def is_frozen_app():
    """是否运行于打包 exe 环境"""
    return bool(getattr(sys, "frozen", False))


def get_current_version():
    """获取当前版本号"""
    version_file = (
        os.path.join(os.path.dirname(__file__), LOCAL_VERSION_FILE)
        if is_frozen_app()
        else LOCAL_VERSION_FILE
    )
    try:
        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
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
    if (
        not isinstance(asset_name, str)
        or os.path.basename(asset_name) != asset_name
        or not asset_name.lower().endswith(".exe")
    ):
        return False, "更新包文件名无效"
    asset_info = get_release_asset_info(asset_name)
    if not asset_info:
        return False, f"未找到发布资产: {asset_name}"
    asset_url = asset_info.get("browser_download_url")
    expected_size = asset_info.get("size")
    expected_digest = asset_info.get("digest")

    current_exe = os.path.abspath(sys.executable)
    if not current_exe.lower().endswith(".exe"):
        return False, "当前不是 exe 运行环境"

    job_dir = None
    staged_exe = None
    helper = None
    try:
        update_dir = ensure_data_dir() / "update"
        update_dir.mkdir(exist_ok=True)
        job_dir = tempfile.mkdtemp(prefix="pending-", dir=update_dir)
        downloaded_exe = os.path.join(job_dir, asset_name)
        if callback:
            callback(f"正在下载软件更新包...\n保存位置：{downloaded_exe}")
        if not download_url(asset_url, downloaded_exe):
            raise OSError("下载更新包失败")
        if callback:
            callback("正在校验更新包...")
        verified, verify_message = verify_downloaded_file(
            downloaded_exe, expected_size=expected_size, expected_digest=expected_digest
        )
        if not verified:
            os.remove(downloaded_exe)
            raise OSError(verify_message)

        if callback:
            callback("正在应用更新...")
        # 同目录暂存后原子替换，避免中途失败留下半个 exe。
        fd, staged_exe = tempfile.mkstemp(
            prefix=".textile-update-", suffix=".exe", dir=os.path.dirname(current_exe)
        )
        os.close(fd)
        shutil.copyfile(downloaded_exe, staged_exe)
        with open(downloaded_exe, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        config_path = os.path.join(job_dir, "update.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({
                "target": current_exe,
                "staged": staged_exe,
                "backup": staged_exe + ".old",
                "owner_pid": os.getpid(),
                "sha256": digest,
            }, f, ensure_ascii=False)
        script_path = os.path.join(job_dir, "apply_update.ps1")
        with open(script_path, "w", encoding="utf-8-sig") as f:
            f.write(BINARY_UPDATE_SCRIPT)
        # -File 会把路径中的方括号当作通配符；按字面读取脚本并传入路径。
        command = "& ([scriptblock]::Create([IO.File]::ReadAllText('{}'))) -ConfigPath '{}'".format(
            script_path.replace("'", "''"), config_path.replace("'", "''")
        )
        encoded_command = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        powershell = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
        )
        # 外部更新助手不能继承打包程序的 DLL 搜索目录。
        dll_dir = getattr(sys, "_MEIPASS", None)
        if dll_dir:
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            with open(os.path.join(job_dir, "launcher.log"), "ab") as log:
                helper = subprocess.Popen(
                    [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-EncodedCommand", encoded_command],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=log, stderr=subprocess.STDOUT, cwd=job_dir,
                )
        finally:
            if dll_dir:
                ctypes.windll.kernel32.SetDllDirectoryW(dll_dir)
        deadline = time.monotonic() + 10
        while not os.path.exists(os.path.join(job_dir, "ready")):
            if helper.poll() is not None or time.monotonic() >= deadline:
                raise OSError("更新助手未能启动，请查看 launcher.log 和 update.log")
            time.sleep(0.1)
    except Exception as ex:
        if helper is not None and helper.poll() is None:
            with suppress(OSError, subprocess.TimeoutExpired):
                helper.terminate()
                helper.wait(timeout=5)
        if staged_exe and os.path.exists(staged_exe):
            with suppress(OSError):
                os.remove(staged_exe)
        message = f"更新未应用，当前程序可继续使用：{ex}"
        if job_dir:
            message += f"\n更新包和日志目录：{job_dir}"
            with suppress(OSError):
                with open(os.path.join(job_dir, "update.log"), "a", encoding="utf-8") as log:
                    log.write(message + "\n")
        return False, message
    if callback:
        callback("正在重启程序...")
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
            "app_core/services/cloud_backup.py",
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
                "app_core/services/cloud_backup.py",
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

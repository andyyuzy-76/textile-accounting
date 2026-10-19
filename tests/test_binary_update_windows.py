import ctypes
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from auto_updater import BINARY_UPDATE_SCRIPT


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows executable updater")
POWERSHELL = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) /
                 "System32/WindowsPowerShell/v1.0/powershell.exe")


@pytest.fixture(scope="module")
def probe_exe(tmp_path_factory):
    folder = tmp_path_factory.mktemp("update-probe")
    builder = folder / "build.ps1"
    builder.write_text('''param([string]$OutputPath)
$ErrorActionPreference = 'Stop'
Add-Type -OutputAssembly $OutputPath -OutputType WindowsApplication -TypeDefinition @'
using System;
using System.IO;
public class Probe {
    public static int Main() {
        File.WriteAllText("restarted.txt", Environment.GetEnvironmentVariable("PYINSTALLER_RESET_ENVIRONMENT"));
        return Environment.GetEnvironmentVariable("TEXTILE_PROBE_FAIL") == "1" ? 7 : 0;
    }
}
'@
''', encoding="utf-8-sig")
    exe = folder / "probe.exe"
    subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(builder), "-OutputPath", str(exe)],
                   check=True, capture_output=True, timeout=30,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    return exe


@pytest.fixture
def update_job(tmp_path, probe_exe):
    folder = tmp_path / "中文 账本 %!&'[]"
    folder.mkdir()
    target = folder / "家纺记账 %!&'[].exe"
    target.write_bytes(b"old-program")
    staged = folder / "staged.exe"
    staged.write_bytes(probe_exe.read_bytes())
    config = folder / "update.json"
    job = {
        "target": str(target), "staged": str(staged),
        "backup": str(folder / "old.exe"), "owner_pid": 2147483647,
        "sha256": hashlib.sha256(staged.read_bytes()).hexdigest(),
    }
    config.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    script = folder / "apply_update.ps1"
    # Expected failures must not open a modal dialog in the test runner.
    script.write_text(BINARY_UPDATE_SCRIPT.replace(
        "[System.Windows.Forms.MessageBox]::Show($message, '家纺记账更新失败') | Out-Null",
        "Write-Output $message",
    ), encoding="utf-8-sig")
    command = "& ([scriptblock]::Create([IO.File]::ReadAllText('{}'))) -ConfigPath '{}'".format(
        str(script).replace("'", "''"), str(config).replace("'", "''")
    )
    args = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", base64.b64encode(command.encode("utf-16-le")).decode("ascii")]
    return folder, target, job, script, args


def test_update_replaces_same_path_and_restarts_with_reset_environment(update_job, probe_exe):
    folder, target, job, script, args = update_job
    result = subprocess.run(args, capture_output=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_bytes() == probe_exe.read_bytes()
    assert (folder / "restarted.txt").read_text(encoding="utf-8-sig") == "1"
    assert not Path(job["backup"]).exists()
    assert "更新完成" in (folder / "update.log").read_text(encoding="utf-8-sig")


def test_update_retries_exclusive_file_lock_before_replacing(update_job, probe_exe):
    folder, target, job, script, args = update_job
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(target), 0x80000000, 0, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    helper = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 10
        while not (folder / "ready").exists() and helper.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert (folder / "ready").exists()
        time.sleep(3)
        assert helper.poll() is None
    finally:
        kernel.CloseHandle(handle)
        stdout, stderr = helper.communicate(timeout=20)
    assert helper.returncode == 0, stdout + stderr
    assert target.read_bytes() == probe_exe.read_bytes()
    assert (folder / "restarted.txt").exists()


def test_update_rolls_back_when_new_process_fails(update_job, monkeypatch):
    folder, target, job, script, args = update_job
    monkeypatch.setenv("TEXTILE_PROBE_FAIL", "1")
    result = subprocess.run(args, capture_output=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 1, result.stdout + result.stderr
    assert target.read_bytes() == b"old-program"
    assert "已恢复旧程序" in (folder / "update.log").read_text(encoding="utf-8-sig")


def test_update_rejects_changed_staged_file_before_replacing(update_job):
    folder, target, job, script, args = update_job
    Path(job["staged"]).write_bytes(b"corrupted")
    result = subprocess.run(args, capture_output=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 1, result.stdout + result.stderr
    assert target.read_bytes() == b"old-program"
    assert "校验失败" in (folder / "update.log").read_text(encoding="utf-8-sig")

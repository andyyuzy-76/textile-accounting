"""Verify the release bundle and launch it with an isolated, empty user profile."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.utils.win32.versioninfo import read_version_info_from_executable
import win32gui


def verify_bundle(executable: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert executable.name == manifest["exe_asset_name"]
    with executable.open("rb") as stream:
        assert stream.read(2) == b"MZ", "Not a Windows executable"

    archive = CArchiveReader(str(executable))
    names = {name.replace("\\", "/"): name for name in archive.toc}
    bundled_manifest = json.loads(archive.extract(names["version.json"]).decode("utf-8"))
    assert bundled_manifest == manifest, "Bundled manifest does not match this release"
    assert "flet_desktop/app/flet/flet.exe" in names, "Missing Flet desktop client"
    assert any(name.endswith("/flutter_windows.dll") for name in names)
    assert any(name.endswith("/icons.json") for name in names)
    assert any(name.endswith("win32print.pyd") for name in names)

    pyz_name = next(name for name in archive.toc if name.endswith(".pyz"))
    modules = archive.open_embedded_archive(pyz_name).toc
    for module in (
        "app_core.services.records",
        "app_core.services.cloud_backup",
        "auto_updater",
        "flet_desktop",
        "import_excel",
        "openpyxl",
        "pandas",
        "receipt_printer",
    ):
        assert module in modules, f"Missing bundled module: {module}"

    version_info = read_version_info_from_executable(str(executable))
    parts = tuple(int(part) for part in manifest["version"].split("."))
    assert version_info.ffi.fileVersionMS == (parts[0] << 16) | parts[1]
    assert version_info.ffi.fileVersionLS == parts[2] << 16
    print(f"Bundle and Windows version metadata verified: {manifest['version']}", flush=True)


def smoke_launch(executable: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="textile-release-smoke-") as folder:
        profile = Path(folder)
        env = os.environ.copy()
        env.update({"USERPROFILE": folder, "HOME": folder})
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        process = subprocess.Popen([str(executable)], cwd=folder, env=env)
        try:
            deadline = time.monotonic() + 60
            found = []
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Client exited before showing its window: {process.returncode}")

                def inspect_window(handle, _):
                    if win32gui.IsWindowVisible(handle) and win32gui.GetWindowText(handle) == "家纺记账系统":
                        found.append(handle)

                win32gui.EnumWindows(inspect_window, None)
                if found:
                    # Ensure the new window is not immediately followed by a crash.
                    time.sleep(3)
                    assert process.poll() is None, "Client crashed after showing its window"
                    assert any(win32gui.IsWindow(handle) for handle in found)
                    assert (profile / ".accounting-tool").is_dir()
                    print("Client startup window verified with an isolated user profile", flush=True)
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Client did not show its startup window within 60 seconds")
        finally:
            if process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    timeout=15,
                )
                process.wait(timeout=15)


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("Run the release bundle checks on Windows")
    executable = Path(sys.argv[1]).resolve()
    manifest_path = Path(sys.argv[2]).resolve()
    verify_bundle(executable, manifest_path)
    smoke_launch(executable)

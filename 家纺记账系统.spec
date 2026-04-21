# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['accounting_flet.py'],
    pathex=[],
    binaries=[],
    datas=[('receipt_printer.py', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='家纺记账系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\ADMINI~1\\AppData\\Local\\Temp\\84feb3e7-1312-45f3-b1a4-639a848dfce0',
)

# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['accounting_flet.py'],
    pathex=[],
    binaries=[],
    datas=[('receipt_printer.py', '.'), ('version.json', '.')],
    hiddenimports=['import_excel', 'openpyxl', 'win32print'],
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
    name='TextileAccounting_v1.15.16',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:/Users/ADMINI~1/AppData/Local/Temp/9ea91c11-0ab8-4199-9a3f-041871a40881',
)

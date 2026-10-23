# -*- mode: python ; coding: utf-8 -*-
# Build the Windows GUI:  pyinstaller gui.spec
# Configs are copied next to the exe at runtime by the user (configs/*.json).

a = Analysis(
    ['run_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('configs', 'configs')],
    hiddenimports=['undetected_chromedriver', 'PIL._tkinter_finder'],
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
    name='WebScraperPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX-packed exes trigger many antivirus false positives
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
)

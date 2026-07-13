# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

ROOT = Path(SPECPATH).parent
APP_VERSION = os.environ.get('APP_VERSION') or (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
VERSION_FILE = ROOT / '.build' / 'VERSION'
VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
VERSION_FILE.write_text(APP_VERSION + '\n', encoding='utf-8')
UPDATE_REPO = os.environ.get('APP_UPDATE_REPO') or os.environ.get('GITHUB_REPOSITORY') or ''
UPDATE_REPO_FILE = ROOT / '.build' / 'UPDATE_REPO'
UPDATE_REPO_FILE.write_text(UPDATE_REPO.strip() + '\n', encoding='utf-8')

a = Analysis(
    [str(ROOT / 'apps/gui_vpn_win.py')],
    pathex=[str(ROOT / 'src')],
    binaries=[
        (str(ROOT / 'runtime/windows-arm64/sing-box.exe'), '.'),
        (str(ROOT / 'runtime/windows-arm64/libcronet.dll'), '.'),
    ],
    datas=[
        (str(ROOT / 'assets/vpn_icon.ico'), '.'),
        (str(ROOT / 'assets/windows_icon_16.png'), 'assets'),
        (str(ROOT / 'assets/windows_icon_20.png'), 'assets'),
        (str(ROOT / 'assets/windows_icon_24.png'), 'assets'),
        (str(ROOT / 'assets/windows_icon_32.png'), 'assets'),
        (str(ROOT / 'assets/windows_icon_40.png'), 'assets'),
        (str(ROOT / 'assets/windows_icon_48.png'), 'assets'),
        (str(ROOT / 'assets/windows_icon_64.png'), 'assets'),
        (str(ROOT / 'assets/windows_icon_128.png'), 'assets'),
        (str(ROOT / 'assets/windows_icon_256.png'), 'assets'),
        (str(ROOT / 'assets/workvpn_icon_imagegen_source.png'), 'assets'),
        (str(ROOT / 'assets/workvpn_icon_tile_source.png'), 'assets'),
        (str(ROOT / 'assets/ui_token.png'), 'assets'),
        (str(ROOT / 'assets/ui_token_light.png'), 'assets'),
        (str(ROOT / 'assets/ui_log.png'), 'assets'),
        (str(ROOT / 'assets/ui_log_light.png'), 'assets'),
        (str(ROOT / 'assets/ui_exit.png'), 'assets'),
        (str(ROOT / 'assets/ui_save.png'), 'assets'),
        (str(ROOT / 'assets/ui_cancel.png'), 'assets'),
        (str(ROOT / 'assets/ui_power.png'), 'assets'),
        (str(ROOT / 'assets/vpn_shield.png'), 'assets'),
        (str(ROOT / 'assets/tray_icon_red.png'), 'assets'),
        (str(ROOT / 'assets/tray_icon_green.png'), 'assets'),
        (str(ROOT / 'assets/tray_icon_orange.png'), 'assets'),
        (str(ROOT / 'assets/power_button_disconnected.png'), 'assets'),
        (str(ROOT / 'assets/power_button_busy.png'), 'assets'),
        (str(ROOT / 'assets/power_button_connected.png'), 'assets'),
        (str(ROOT / 'assets/ui_theme_sun.png'), 'assets'),
        (str(ROOT / 'assets/ui_theme_moon.png'), 'assets'),
        (str(ROOT / 'runtime/windows-arm64/LICENSE'), '.'),
        (str(VERSION_FILE), '.'),
        (str(UPDATE_REPO_FILE), '.'),
    ],
    hiddenimports=['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
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
    name='WorkVPN',
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
    icon=str(ROOT / 'assets/vpn_icon.ico'),
    uac_admin=False,
)

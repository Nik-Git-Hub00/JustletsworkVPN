# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / 'apps/gui_vpn_win.py')],
    pathex=[str(ROOT / 'src')],
    binaries=[
        (str(ROOT / 'runtime/windows-arm64/sing-box.exe'), '.'),
        (str(ROOT / 'runtime/windows-arm64/libcronet.dll'), '.'),
    ],
    datas=[
        (str(ROOT / 'assets/vpn_icon.ico'), '.'),
        (str(ROOT / 'assets/workvpn_icon_imagegen_source.png'), 'assets'),
        (str(ROOT / 'assets/workvpn_icon_tile_source.png'), 'assets'),
        (str(ROOT / 'assets/ui_token.png'), 'assets'),
        (str(ROOT / 'assets/ui_log.png'), 'assets'),
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
        (str(ROOT / 'runtime/windows-arm64/LICENSE'), '.'),
    ],
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
    uac_admin=True,
)

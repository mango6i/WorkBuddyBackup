# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('WorkBuddyBackup.ico', '.'), ('WorkBuddyBackup_icon.png', '.')]
binaries = []
hiddenimports = []


a = Analysis(
    ['WorkBuddy一键备份.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebChannel', 'PyQt6.QtQuick', 'PyQt6.QtQml', 'PyQt6.Qt3DCore', 'PyQt6.QtCharts', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets', 'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets', 'PyQt6.QtDesigner', 'PyQt6.QtTest', 'PyQt6.QtPositioning', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort', 'PyQt6.QtBluetooth', 'PyQt6.QtNfc', 'PyQt6.QtRemoteObjects', 'PyQt6.QtTextToSpeech', 'PyQt6.QtWebSockets', 'PyQt6.QtNetworkAuth', 'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'PyQt6.QtVulkan', 'PyQt6.QtSpatialAudio', 'PyQt6.QtScxml', 'PyQt6.QtStateMachine', 'PyQt6.QtSql', 'PyQt6.QtHelp', 'PyQt6.QtUiTools', 'PyQt6.QtXml'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

splash = Splash(
    'splash.png',
    binaries=a.binaries,
    datas=a.datas,
    always_on_top=False,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name='WorkBuddyBackup',
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
    icon='WorkBuddyBackup.ico',
    splash=splash,
)

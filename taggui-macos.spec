# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS application bundle.

Build it with:

    venv/bin/python -m PyInstaller taggui-macos.spec

The bundle is written to `dist/TagGUI.app`. The icon is the `.icns` file
built by `build_icon.py`.
"""

datas = [('clip-vit-base-patch32', 'clip-vit-base-patch32'),
         ('images/icon.icns', 'images')]
hiddenimports = []

block_cipher = None


a = Analysis(
    ['taggui/run_gui.py'],
    pathex=['taggui'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TagGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['images/icon.icns'],
    contents_directory='_TagGUI',
)

app = BUNDLE(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TagGUI.app',
    icon='images/icon.icns',
    bundle_identifier='com.taggui.taggui',
    version='1.0.0',
    info_plist={
        'CFBundleName': 'TagGUI',
        'CFBundleDisplayName': 'TagGUI',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.graphics-design',
    },
)

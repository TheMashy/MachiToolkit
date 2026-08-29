# -*- mode: python ; coding: utf-8 -*-
#
# Recette de compilation unique, partagee par Compiler.bat et par le
# workflow GitHub : les deux produisent exactement le meme exe.
#
#     pyinstaller --noconfirm --clean GuirlandeAmbiante.spec
#
# Les chemins sont relatifs a ce fichier (SPECPATH), jamais absolus :
# un chemin en dur ne compilerait que sur la machine qui l'a ecrit.

import os

from PyInstaller.utils.hooks import collect_all

RACINE = os.path.abspath(SPECPATH)

datas = []
binaries = []
hiddenimports = ['win32gui', 'win32process', 'win32api', 'win32event',
                 'winerror', 'pystray._win32', 'PIL._tkinter_finder']

# winrt n'existe que sur Windows et son nom de paquet a bouge selon les
# versions de bleak : son absence ne doit pas casser la compilation.
for paquet in ('bleak', 'winrt', 'mss', 'soundcard'):
    try:
        d, b, h = collect_all(paquet)
    except Exception as e:
        print("spec : %s ignore (%s)" % (paquet, e))
        continue
    datas += d
    binaries += b
    hiddenimports += h

icone = os.path.join(RACINE, 'icone.ico')

a = Analysis(
    [os.path.join(RACINE, 'guirlande_ambiante.py')],
    pathex=[RACINE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='GuirlandeAmbiante',
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
    icon=([icone] if os.path.exists(icone) else None),
)

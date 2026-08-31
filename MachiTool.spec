# -*- mode: python ; coding: utf-8 -*-
#
# Recette de compilation unique, partagee par Compiler.bat et par le
# workflow GitHub : les deux produisent exactement le meme exe.
#
#     pyinstaller --noconfirm --clean MachiTool.spec
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
# cffi et son extension C portent la capture audio de soundcard ; sans
# elles, l'import echoue dans l'exe alors qu'il passe en mode script.
hiddenimports += ['cffi', '_cffi_backend']

for paquet in ('bleak', 'winrt', 'mss', 'soundcard', 'cffi', 'numpy'):
    try:
        d, b, h = collect_all(paquet)
    except Exception as e:
        print("spec : %s ignore (%s)" % (paquet, e))
        continue
    datas += d
    binaries += b
    hiddenimports += h

icone = os.path.join(RACINE, 'icone.ico')

# L'icone sert deux fois : gravee dans le .exe par le parametre icon
# ci-dessous, et embarquee comme donnee pour que la fenetre puisse la
# poser a l'execution. Sans cette seconde copie, Tk affiche sa plume.
if os.path.exists(icone):
    datas += [(icone, '.')]

a = Analysis(
    [os.path.join(RACINE, 'machi_tool.py')],
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
    name='MachiTool',
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

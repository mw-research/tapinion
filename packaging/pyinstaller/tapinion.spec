# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for the one-file desktop app (Windows .exe, macOS .app, Linux binary).
#   pyinstaller --noconfirm packaging/pyinstaller/tapinion.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent.parent
PKG = ROOT / "tapinion"

datas = [
    (str(PKG / "templates"), "tapinion/templates"),
    (str(PKG / "static"), "tapinion/static"),
    (str(PKG / "locales"), "tapinion/locales"),
]
hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("tapinion")
    + ["fpdf", "qrcode.image.svg", "multipart", "python_multipart", "itsdangerous"]
)

a = Analysis(
    [str(Path(SPECPATH) / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hidden,
    excludes=["pytest", "IPython", "numpy", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = str(Path(SPECPATH) / "tapinion.ico")

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Tapinion",
    console=False,
    icon=icon,
    upx=False,
    runtime_tmpdir=None,
)

if sys.platform == "darwin":
    app = BUNDLE(exe, name="Tapinion.app", icon=None, bundle_identifier="org.tapinion.desktop")

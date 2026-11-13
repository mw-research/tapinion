# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for the desktop app. Produces a program folder (dist/Tapinion/), which the
# installers package: Inno Setup (Windows), a .app in a .dmg (macOS), an AppImage (Linux).
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Tapinion",
    console=False,
    icon=str(Path(SPECPATH) / "tapinion.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Tapinion", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Tapinion.app",
        icon=str(Path(SPECPATH) / "tapinion.icns") if (Path(SPECPATH) / "tapinion.icns").is_file() else None,
        bundle_identifier="io.github.mwresearch.tapinion",
        info_plist={
            "CFBundleDisplayName": "Tapinion",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "NSLocalNetworkUsageDescription": "Tablets in your network connect to Tapinion.",
        },
    )

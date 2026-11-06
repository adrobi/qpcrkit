# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the qpcrkit one-file executable (Windows exe, Linux ELF).

Build:  pyinstaller qpcrkit.spec --noconfirm
"""

import sys

a = Analysis(
    ["qpcr_cli.py"],
    pathex=[],
    binaries=[],
    datas=[("ui/icons/app/qpcrkit.png", "ui/icons/app"), ("ui/icons/*.svg", "ui/icons"), ("examples/demo_project.qpcrkit.json", "examples")],
    # The GUI is imported lazily by qpcr_cli, so PyInstaller cannot see it on its own.
    hiddenimports=[
        "i18n",
        "translations_en",
        "ui.main_window",
        "ui.errors",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.backends.backend_svg",
        "matplotlib.backends.backend_pdf",
    ],
    hookspath=[],
    excludes=["tkinter", "matplotlib.backends.backend_tkagg", "numpy.tests", "scipy.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="qpcrkit",
    debug=False,
    strip=False,
    upx=False,
    # console=False only matters on Windows/macOS; a Linux ELF keeps stdout.
    console=False,
    # .ico is a Windows/macOS-only option; PyInstaller does not use it on Linux.
    icon="ui/icons/app/qpcrkit.ico" if sys.platform == "win32" else None,
)

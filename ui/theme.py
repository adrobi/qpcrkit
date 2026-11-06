"""Light and dark themes: every color of the interface comes from these tokens."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

LIGHT = {
    "bg": "#f7f9f9",
    "panel": "#ffffff",
    "card": "#ffffff",
    "text": "#12201f",
    "dim": "#5b6b69",
    "grid": "#dfe6e5",
    "border": "#cfd9d7",
    "hover": "#eaf1f0",
    "header_bg": "#eef3f2",
    "well_empty": "#f7f9f9",
    "well_border": "#cfd9d7",
    "selection": "#0f766e",
    "pipet_active": "#d97706",
    "qc_ok": "#dcfce7",
    "qc_warn": "#fef3c7",
    "qc_err": "#fee2e2",
    "warn": "#b45309",
    "accent": "#0f766e",
    "accent_soft": "#d5efeb",
    "on_accent": "#ffffff",
}

DARK = {
    "bg": "#0f1716",
    "panel": "#162120",
    "card": "#1b2827",
    "text": "#e6efed",
    "dim": "#93a5a2",
    "grid": "#2b3a38",
    "border": "#34443f",
    "hover": "#22302e",
    "header_bg": "#1b2827",
    "well_empty": "#162120",
    "well_border": "#34443f",
    "selection": "#2dd4bf",
    "pipet_active": "#fbbf24",
    "qc_ok": "#14532d",
    "qc_warn": "#713f12",
    "qc_err": "#7f1d1d",
    "warn": "#fbbf24",
    "accent": "#2dd4bf",
    "accent_soft": "#123f3a",
    "on_accent": "#06211e",
}


def theme(name: str) -> dict:
    return DARK if name == "dark" else LIGHT


def resource_dir() -> Path:
    """``ui/`` next to this module, or ``sys._MEIPASS/ui`` in a PyInstaller bundle (see qpcrkit.spec)."""
    frozen = getattr(sys, "_MEIPASS", None)
    return Path(frozen) / "ui" if frozen else Path(__file__).resolve().parent


def demo_path() -> Path:
    """The demo project: next to ``ui/`` in the sources and in a bundle alike (see qpcrkit.spec)."""
    return resource_dir().parent / "examples" / "demo_project.qpcrkit.json"


def resolve_dark(mode: str, system_dark: bool) -> bool:
    return system_dark if mode == "auto" else mode == "dark"


def system_is_dark() -> bool:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def tinted_icon(name: str, color: str) -> str:
    """Path of ``ui/icons/<name>.svg`` drawn in ``color``, for QSS ``url()``; "" if it cannot be written."""
    folder = Path(tempfile.gettempdir()) / "qpcrkit_icons"
    target = folder / f"{name}_{color.lstrip('#')}.svg"
    try:
        folder.mkdir(exist_ok=True)
        if not target.exists():
            svg = (resource_dir() / "icons" / f"{name}.svg").read_text(encoding="utf-8")
            target.write_text(svg.replace("currentColor", color), encoding="utf-8")
    except OSError:
        return ""
    return target.as_posix()


def icon(name: str, color: str):
    """A line icon for buttons; empty if there is no such icon."""
    from PySide6.QtGui import QIcon

    if not (resource_dir() / "icons" / f"{name}.svg").exists():
        return QIcon()
    return QIcon(tinted_icon(name, color))


def _image(name: str, color: str) -> str:
    path = tinted_icon(name, color)
    return f"image: url({path});" if path else ""


def _controls_qss(t: dict) -> str:
    """Check marks and arrows: a stylesheet on these controls removes the platform's own."""
    return (
        f"QCheckBox::indicator, QTableView::indicator, QTreeView::indicator {{ width: 13px; height: 13px;"
        f" border: 1px solid {t['dim']}; border-radius: 3px; background-color: {t['bg']}; }}"
        f"QCheckBox::indicator:checked, QTableView::indicator:checked, QTreeView::indicator:checked {{"
        f" background-color: {t['accent']}; border-color: {t['accent']}; {_image('check', t['on_accent'])} }}"
        f"QComboBox::drop-down {{ border: none; width: 18px; }}"
        f"QComboBox::down-arrow {{ width: 10px; height: 10px; {_image('chevron-down', t['dim'])} }}"
        f"QSpinBox, QDoubleSpinBox {{ padding-right: 18px; }}"
        f"QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border;"
        f" subcontrol-position: top right; width: 16px; border: none; }}"
        f"QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border;"
        f" subcontrol-position: bottom right; width: 16px; border: none; }}"
        f"QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ width: 9px; height: 9px; {_image('chevron-up', t['dim'])} }}"
        f"QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ width: 9px; height: 9px; {_image('chevron-down', t['dim'])} }}"
    )


def app_qss(dark: bool) -> str:
    """The application stylesheet; a stylesheet replaces platform drawing, so every control is covered."""
    t = DARK if dark else LIGHT
    return f"""
QWidget {{ background-color: {t['bg']}; color: {t['text']}; font-size: 13px; }}
QLabel, QCheckBox, QRadioButton {{ background-color: transparent; }}
QLabel#dim {{ color: {t['dim']}; }}
QMenuBar, QMenu, QToolBar, QStatusBar {{ background-color: {t['panel']}; border: none; }}
QMenuBar {{ border-bottom: 1px solid {t['border']}; }}
QMenu {{ border: 1px solid {t['border']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 6px; }}
QMenuBar::item:selected, QMenu::item:selected {{ background-color: {t['accent_soft']}; color: {t['accent']}; }}
QToolTip {{ background-color: {t['card']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 3px; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
  background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 4px 6px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QPushButton:disabled {{ color: {t['dim']}; background-color: {t['bg']}; }}
QComboBox QAbstractItemView {{ background-color: {t['card']}; border: 1px solid {t['border']}; selection-background-color: {t['accent_soft']}; selection-color: {t['accent']}; }}
QTableView, QTableWidget, QTreeView, QTreeWidget, QListView {{
  background-color: {t['card']}; alternate-background-color: {t['bg']}; gridline-color: {t['grid']};
  border: 1px solid {t['border']}; border-radius: 10px; selection-background-color: {t['accent_soft']}; selection-color: {t['text']};
}}
QHeaderView::section {{ background-color: {t['header_bg']}; color: {t['dim']}; border: none; border-bottom: 1px solid {t['border']}; padding: 5px 6px; }}
QPushButton, QToolButton {{ background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 5px 12px; }}
QPushButton:hover, QToolButton:hover {{ background-color: {t['hover']}; }}
QPushButton#primaryBtn {{ background-color: {t['accent']}; color: {t['on_accent']}; border-color: {t['accent']}; font-weight: 600; }}
QPushButton#primaryBtn:hover {{ background-color: {t['accent']}; border-color: {t['text']}; }}
QGroupBox {{ border: 1px solid {t['border']}; border-radius: 10px; margin-top: 10px; padding-top: 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: 10px; }}
QTabBar::tab {{ background-color: transparent; color: {t['dim']}; padding: 6px 14px; }}
QTabBar::tab:selected {{ color: {t['accent']}; font-weight: 600; border-bottom: 2px solid {t['accent']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background-color: {t['border']}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background-color: {t['dim']}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; height: 0; width: 0; }}
QSplitter::handle {{ background-color: {t['bg']}; }}
#navRail, #topBar {{ background-color: {t['panel']}; }}
#navRail {{ border-right: 1px solid {t['border']}; }}
#topBar {{ border-bottom: 1px solid {t['border']}; }}
#navRail QTreeView, #navRail QTreeWidget {{ background-color: {t['panel']}; border: none; }}
#navButton {{ background-color: transparent; border: none; border-radius: 8px; padding: 7px 10px; text-align: left; color: {t['text']}; }}
#navButton:hover {{ background-color: {t['hover']}; }}
#navButton:checked {{ background-color: {t['accent_soft']}; color: {t['accent']}; font-weight: 600; }}
#projectName {{ font-size: 15px; font-weight: 600; background-color: transparent; }}
#chip {{ background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 4px 10px; }}
#chip:hover {{ background-color: {t['hover']}; }}
#chip[missing="true"] {{ border: 1px solid {t['warn']}; color: {t['warn']}; }}
#chip::menu-indicator {{ image: none; width: 0; }}
#hintBar {{ background-color: {t['accent_soft']}; border-radius: 8px; }}
#hintBar QLabel {{ color: {t['accent']}; font-weight: 600; }}
#startCard {{ background-color: {t['panel']}; border: 1px dashed {t['border']}; border-radius: 10px; }}
""" + _controls_qss(t)


def mpl_style(dark: bool) -> dict:
    """matplotlib rcParams for on-screen figures in the current theme."""
    t = DARK if dark else LIGHT
    return {
        "figure.facecolor": t["bg"],
        "axes.facecolor": t["bg"],
        "savefig.facecolor": t["bg"],
        "axes.edgecolor": t["dim"],
        "axes.labelcolor": t["text"],
        "axes.titlecolor": t["text"],
        "text.color": t["text"],
        "xtick.color": t["dim"],
        "ytick.color": t["dim"],
        "grid.color": t["grid"],
    }


def app_icon():
    from PySide6.QtGui import QIcon

    return QIcon(str(resource_dir() / "icons" / "app" / "qpcrkit.png"))

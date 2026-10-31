"""Light and dark themes shared across all qpcrkit widgets (same palette as platekit)."""

from __future__ import annotations

import sys
from pathlib import Path

LIGHT = {
    "bg": "#ffffff",
    "panel": "#f8fafc",
    "card": "#f1f5f9",
    "text": "#0f172a",
    "dim": "#64748b",
    "grid": "#cbd5e1",
    "header_bg": "#e2e8f0",
    "well_empty": "#f8fafc",
    "well_border": "#cbd5e1",
    "selection": "#2563eb",
    "pipet_active": "#f59e0b",
    "qc_ok": "#dcfce7",
    "qc_warn": "#fef3c7",
    "qc_err": "#fee2e2",
    "accent": "#2563eb",
}

DARK = {
    "bg": "#18181b",
    "panel": "#202024",
    "card": "#27272a",
    "text": "#e4e4e7",
    "dim": "#a1a1aa",
    "grid": "#3f3f46",
    "header_bg": "#27272a",
    "well_empty": "#1f1f23",
    "well_border": "#3f3f46",
    "selection": "#60a5fa",
    "pipet_active": "#fbbf24",
    "qc_ok": "#14532d",
    "qc_warn": "#713f12",
    "qc_err": "#7f1d1d",
    "accent": "#60a5fa",
}


def theme(name: str) -> dict:
    return DARK if name == "dark" else LIGHT


def _checkbox_qss(t: dict) -> str:
    # The platform style draws no frame for an unchecked box on these backgrounds.
    return (
        f"QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid {t['dim']};"
        f" border-radius: 3px; background-color: {t['bg']}; }}"
        f"QCheckBox::indicator:checked {{ background-color: {t['accent']}; border-color: {t['accent']}; }}"
    )


def app_qss(dark: bool) -> str:
    """Explicit application stylesheet for consistent dark/light appearance."""
    if dark:
        return (
            "QWidget { background-color: #202024; color: #e4e4e7; font-size: 12px; }"
            "QMenuBar, QMenu, QToolBar { background-color: #27272a; border-bottom: 1px solid #3f3f46; }"
            "QMenu::item:selected { background-color: #3b82f6; color: #ffffff; }"
            "QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QTableWidget {"
            "  background-color: #18181b; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 4px; padding: 3px;"
            "}"
            "QHeaderView::section { background-color: #27272a; color: #e4e4e7; border: 1px solid #3f3f46; padding: 4px; }"
            "QPushButton {"
            "  background-color: #27272a; color: #e4e4e7; border: 1px solid #52525b; border-radius: 4px; padding: 5px 10px;"
            "}"
            "QPushButton:hover { background-color: #3f3f46; }"
            "QPushButton#primaryBtn { background-color: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; font-weight: bold; }"
            "QPushButton#primaryBtn:hover { background-color: #3b82f6; }"
            "QGroupBox { border: 1px solid #3f3f46; border-radius: 5px; margin-top: 8px; padding-top: 10px; font-weight: bold; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
            "QTabWidget::pane { border: 1px solid #3f3f46; }"
            "QTabBar::tab { background-color: #27272a; color: #a1a1aa; padding: 6px 14px; border: 1px solid #3f3f46; }"
            "QTabBar::tab:selected { background-color: #18181b; color: #ffffff; font-weight: bold; }"
            + _checkbox_qss(DARK)
        )
    return (
        "QWidget { background-color: #f8fafc; color: #0f172a; font-size: 12px; }"
        "QMenuBar, QMenu, QToolBar { background-color: #e2e8f0; border-bottom: 1px solid #cbd5e1; }"
        "QMenu::item:selected { background-color: #2563eb; color: #ffffff; }"
        "QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QTableWidget {"
        "  background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px;"
        "}"
        "QHeaderView::section { background-color: #e2e8f0; color: #0f172a; border: 1px solid #cbd5e1; padding: 4px; }"
        "QPushButton {"
        "  background-color: #ffffff; color: #0f172a; border: 1px solid #94a3b8; border-radius: 4px; padding: 5px 10px;"
        "}"
        "QPushButton:hover { background-color: #e2e8f0; }"
        "QPushButton#primaryBtn { background-color: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; font-weight: bold; }"
        "QPushButton#primaryBtn:hover { background-color: #1d4ed8; }"
        "QGroupBox { border: 1px solid #cbd5e1; border-radius: 5px; margin-top: 8px; padding-top: 10px; font-weight: bold; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        "QTabWidget::pane { border: 1px solid #cbd5e1; }"
        "QTabBar::tab { background-color: #e2e8f0; color: #475569; padding: 6px 14px; border: 1px solid #cbd5e1; }"
        "QTabBar::tab:selected { background-color: #ffffff; color: #0f172a; font-weight: bold; }"
        + _checkbox_qss(LIGHT)
    )


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
    }


def resource_dir() -> Path:
    """``ui/`` next to this module, or ``sys._MEIPASS/ui`` in a PyInstaller bundle (see qpcrkit.spec)."""
    frozen = getattr(sys, "_MEIPASS", None)
    return Path(frozen) / "ui" if frozen else Path(__file__).resolve().parent


def app_icon():
    from PySide6.QtGui import QIcon

    return QIcon(str(resource_dir() / "icons" / "app" / "qpcrkit.png"))

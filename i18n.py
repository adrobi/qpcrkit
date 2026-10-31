"""Lightweight dictionary-based i18n (RU base table here, EN in translations_en)."""

# Same mechanism as platekit/ab1kit: tr(key, **kw), language from the OS.

from __future__ import annotations

import ctypes
import locale
import os
import sys

from translations_en import EN

RU: dict[str, str] = {
    # QC flags (codes from qpcr_core; params documented in qpcr_core/flags.py)
    "qc.rep_sd_high": "Разброс технических реплик SD = {sd:.2f} больше порога {limit:.2f}",
    "qc.outlier_suggested": "Реплика с Cq {cq:.2f} далеко от медианы {median:.2f} — предлагается исключить",
    "qc.partial_undetermined": "Часть технических реплик без Cq (Undetermined)",
    "qc.ntc_contamination": "Контроль без матрицы (NTC) дал Cq {cq:.2f} — возможна контаминация",
    "qc.late_amplification": "Поздняя амплификация: Cq {cq:.2f}",
    "qc.irc_missing": "На планшете нет межпланшетных калибраторов — поправка не применена",
    "qc.no_irc": "Несколько планшетов без межпланшетных калибраторов — Cq между ними не выравниваются",
    "qc.std_levels_few": "Меньше 3 уровней стандартов ({levels}) — кривая не построена",
    "qc.efficiency_out_of_range": "Эффективность {eff:.1%} вне диапазона 90–110 %",
    "qc.r2_low": "R² стандартной кривой {r2:.3f} ниже 0,98",
    "qc.extrapolated": "Количество {quantity:.3g} вне диапазона стандартов (экстраполяция)",
    "qc.no_control": "Не выбрана контрольная группа или образец-калибратор",
    "qc.no_reference_targets": "Не выбраны референсные гены",
    "qc.no_reference_for_sample": "Нет Cq ни одного референсного гена для образца",
    "qc.no_cq": "Нет Cq ни в одной реплике",
    "qc.no_calibrator_cq": "В контрольной группе нет Cq для этой мишени",
    "qc.too_few_bio_reps": "В группе «{group}» меньше 2 биологических реплик — тесты не выполняются",
    # Export sheets
    "sheet.raw": "Исходные данные",
    "sheet.qc": "QC",
    "sheet.std": "Стандартные кривые",
    "sheet.abs": "Абсолютная оценка",
    "sheet.rel": "Относительная экспрессия",
    "sheet.stats": "Статистика",
    "sheet.params": "Параметры анализа",
}


def detect_system_language() -> str:
    """Detect OS UI language on Windows, Linux or macOS; fall back to 'en' if undetermined."""
    # 1. Check standard POSIX / environment variables
    for env_var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        val = os.environ.get(env_var, "").strip()
        if not val or val.upper() in ("C", "C.UTF-8", "POSIX"):
            continue
        first_token = val.split(":")[0].strip().lower()
        if first_token.startswith(("ru", "russian")):
            return "ru"
        if len(first_token) >= 2 and first_token[:2].isalpha():
            return "en"

    # 2. Check Windows Win32 UI language if running on Windows
    if sys.platform == "win32":
        try:
            windll = getattr(ctypes, "windll", None)
            if windll is not None:
                lang_id = int(windll.kernel32.GetUserDefaultUILanguage())
                # Primary language 0x19 is Russian (LANG_RUSSIAN)
                if (lang_id & 0x3FF) == 0x19:
                    return "ru"
                win_loc = locale.windows_locale.get(lang_id, "").lower()
                if win_loc.startswith("ru"):
                    return "ru"
                if win_loc:
                    return "en"
        except Exception:
            pass

    # 3. Check Python locale
    try:
        loc_name, _ = locale.getlocale()
        if loc_name:
            low = loc_name.lower()
            if low.startswith(("ru", "russian")):
                return "ru"
            if low not in ("c", "posix"):
                return "en"
    except Exception:
        pass

    return "en"


_lang: str = detect_system_language()


def set_language(lang: str | None) -> None:
    global _lang
    if not lang or lang == "auto":
        _lang = detect_system_language()
    elif lang in ("ru", "en"):
        _lang = lang
    else:
        _lang = "en"


def language() -> str:
    return _lang


def tr(key: str, **kwargs) -> str:
    table = RU if _lang == "ru" else EN
    text = table.get(key) or EN.get(key) or key
    return text.format(**kwargs) if kwargs else text


def current_language() -> str:
    return _lang

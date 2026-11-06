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
    "qc.efficiency_out_of_range": "Эффективность {eff:.1%} вне диапазона {min:.0%}–{max:.0%}",
    "qc.r2_low": "R² стандартной кривой {r2:.3f} ниже {min:.3g}",
    "qc.wells_without_sample": "Лунок без образца: {count}. Они не участвуют в расчёте, задайте образцы",
    "qc.nrt_amplified": "Контроль без ОТ дал Cq {cq:.2f}: разница с образцом меньше {delta:g} циклов, возможна примесь гДНК",
    "qc.extrapolated": "Количество {quantity:.3g} вне диапазона стандартов (экстраполяция)",
    "qc.no_control": "Не выбрана контрольная группа или образец-калибратор",
    "qc.no_reference_targets": "Не выбраны референсные гены",
    "qc.no_reference_for_sample": "Нет Cq ни одного референсного гена для образца",
    "qc.no_cq": "Нет Cq ни в одной реплике",
    "qc.no_calibrator_cq": "В контрольной группе нет Cq для этой мишени",
    "qc.too_few_bio_reps": "В группе «{group}» меньше 2 биологических реплик — тесты не выполняются",
    "qc.irc_partial": "Калибраторы этой мишени есть не на всех планшетах — использованы общие калибраторы",
    "qc.irc_no_common": "Нет калибратора, общего для всех планшетов — Cq между планшетами не выровнены",
    "qc.std_no_quantity": "Стандарт без количества — не используется в кривой",
    "qc.efficiency_unusable": "Эффективность по кривой {eff:.1%} недостоверна (кривая повреждена?) — использована ручная или 100 %",
    "qc.efficiency_curves_unusable": "По кривым не удалось оценить эффективность — использовано 100 %",
    "qc.efficiency_from_subtracted": "Эффективность оценена по кривым с уже вычтенным фоном: оценка менее надёжна",
    "qc.curve_unusable": "Кривых, которые нельзя обработать: {count}. Для них нет своего Cq",
    "qc.mixed_cq_sources": "В проекте на этой мишени смешаны Cq прибора и рассчитанные по кривым: у них разный порог",
    "qc.no_curve_for_calculated": "Выбран Cq по кривым, но у {count} реакций нет кривой — они остались без Cq",
    "qc.thresholds_differ_no_irc": "На планшетах разные пороги, а калибраторов нет — Cq между планшетами несравнимы",
    "qc.melt_multiple_peaks": "На кривой плавления несколько значимых пиков ({count}): возможен второй продукт",
    "qc.melt_tm_shift": "Tm {tm:.1f} °C отличается от медианы мишени {median:.1f} °C",
    "qc.ntc_melt_product": "В контроле без матрицы (NTC) пик плавления {tm:.1f} °C, как у продукта: возможна контаминация",
    "qc.ntc_melt_other": "В контроле без матрицы (NTC) пик плавления {tm:.1f} °C не совпадает с продуктом: вероятно, димеры праймеров",
    "qc.cq_source_disagree": "Cq прибора и рассчитанный по кривой расходятся на {delta:+.2f} цикла сверх обычного сдвига (порог {limit:.2f})",
    "qc.early_cq": "Очень ранний Cq {cq:.2f}, меньше {min:g}: фон оценён ненадёжно, стоит разбавить образец",
    "qc.no_amplification_with_cq": "Прибор указал Cq у {count} реакций, но кривая не растёт",
    "qc.partial_reference": "Нет Cq части референсных генов — нормировка по оставшимся",
    "qc.samples_without_group": "Образцов без группы: {count} — они не входят в относительную экспрессию",
    # Export sheets
    "sheet.raw": "Исходные данные",
    "sheet.qc": "QC",
    "sheet.std": "Стандартные кривые",
    "sheet.abs": "Абсолютная оценка",
    "sheet.rel": "Относительная экспрессия",
    "sheet.curves": "Кривые",
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

RU.update({"act.rename_target": "Переименовать мишень на планшете…", "ui.rename_from": "Мишень на этом планшете:", "ui.rename_to": "Новое имя:"})
RU.update({"ui.bad_quantity": "Количество должно быть положительным числом"})
RU.update(
    {
        "ui.col.cq_calc": "Cq по кривой",
        "ui.col.tm": "Tm",
        "ui.save_figure": "Сохранить рисунок…",
        "ui.filter_figure": "Рисунки (*.svg *.png *.pdf)",
        "ui.excluded_on_curve": "исключена на стандартной кривой",
        "ui.excluded_note": "Реплика {coord} ({target}) исключена. Отменить: Ctrl+Z",
    }
)
RU.update(
    {
        "ui.cq_source": "Источник Cq",
        "ui.cq_source.instrument": "Cq прибора",
        "ui.cq_source.calculated": "Cq по кривым",
        "ui.eff.curves": "по кривым амплификации",
        "ui.eff.from_curves": "по кривым: {eff:.0%}",
        "ui.set.nrt_min_delta": "Контроль без ОТ: разница с образцом, циклов",
        "ui.set.tm_shift_max": "Сдвиг Tm от медианы, °C",
        "ui.set.early_cq": "Ранний Cq, меньше",
        "ui.set.cq_disagree_max": "Расхождение с Cq прибора, циклов",
    }
)
RU.update(
    {
        "start.title": "Перетащите файлы прибора сюда",
        "start.note": "Несколько файлов или папку: CFX, QuantStudio, Rotor-Gene, RDML, CSV",
        "ui.role_keep": "Роль: без изменений",
        "start.add": "Выбрать файлы…",
        "start.open": "Открыть проект…",
        "start.demo": "Демо-данные",
    }
)
RU.update(
    {
        "ui.curves.auto": "Авто",
        "ui.curves.auto_tip": "Сбросить ручной порог",
    }
)
RU.update(
    {
        "ui.curves.amp": "Амплификация",
        "ui.curves.log": "Амплификация, логарифм",
        "ui.curves.melt": "Плавление",
        "ui.curves.all": "Все мишени",
        "ui.curves.none": "В этом запуске нет таких кривых",
        "ui.curves.cycle": "Цикл",
        "ui.curves.signal": "Сигнал без фона",
        "ui.curves.temperature": "Температура, °C",
        "ui.curves.dfdt": "-dF/dT",
    }
)
RU.update(
    {
        "ui.select_wells": "Выделите лунки на планшете",
        "ui.mixed": "несколько значений",
    }
)
RU.update(
    {
        "ui.analysis_settings": "Настройки анализа",
        "ui.qc_count": "Ошибок: {errors}, предупреждений: {warnings}",
        "ui.chip.reference": "Референс: {value}",
        "ui.chip.control": "Контроль: {value}",
        "ui.chip.not_set": "не выбран",
        "ui.chip.no_targets": "Мишеней пока нет",
        "ui.chip.no_groups": "Сначала задайте группы образцов",
    }
)
RU.update(
    {
        "hint.no_target": "Лунок без мишени: {count}. Выделите их и задайте мишень",
        "hint.no_sample": "Лунок без образца: {count}. Выделите их и задайте образец",
        "hint.no_reference": "Выберите референсный ген",
        "hint.no_groups": "Образцов без группы: {count}. Задайте группы",
        "hint.no_control": "Выберите контрольную группу",
    }
)
RU.update(
    {
        "cli.unknown_format": "Формат файла не распознан: {path}. Откройте его в qpcrkit через мастер импорта CSV.",
        "cli.inspect": "Формат: {fmt}\nЛунок: {wells}\nРеакций: {reactions}\nМишеней: {targets}\nОбразцов: {samples}\nПропущено строк: {skipped}",
        "cli.summary": "Ошибок: {error}, предупреждений: {warning}, информационных: {info}",
        "cli.saved": "Сохранено: {path}",
    }
)

RU.update(
    {
        "ui.col.run": "Запуск", "ui.col.well": "Лунка", "ui.col.sample": "Образец", "ui.col.group": "Группа",
        "ui.col.target": "Мишень", "ui.col.role": "Роль", "ui.col.cq": "Cq", "ui.col.quantity": "Количество",
        "ui.col.excluded": "Исключена",
        "ui.filter": "Фильтр…",
        "ui.paste_hint": "Ctrl+V: вставить из Excel столбцы «образец — группа — биол. реплика»",
        "ui.role.unknown": "образец", "ui.role.ntc": "NTC", "ui.role.nrt": "контроль без ОТ", "ui.role.std": "стандарт", "ui.role.irc": "калибратор (IRC)",
        "ui.role.pos": "полож. контроль",
    }
)

RU.update(
    {
        "ui.no_curves": "Нет стандартных кривых: отметьте лунки стандартов и задайте количества",
        "ui.no_groups": "Нет данных для экспрессии: выберите референсные гены, контрольную группу и задайте группы образцов",
        "ui.no_flags": "Замечаний нет",
        "ui.target": "Мишень", "ui.curve": "Кривая", "ui.error_bar": "Погрешность", "ui.log2": "log2",
        "ui.error.sd": "SD", "ui.error.sem": "SEM", "ui.error.ci95": "95 % ДИ",
        "ui.col.slope": "Наклон", "ui.col.intercept": "Пересечение", "ui.col.r2": "R²", "ui.col.efficiency": "Эффективность",
        "ui.col.lowest": "Наименьший детектируемый стандарт", "ui.col.n": "n", "ui.col.fold": "Кратность",
        "ui.col.group_b": "Против", "ui.col.test": "Тест", "ui.col.p": "p", "ui.col.p_adj": "p (BH)",
        "ui.col.severity": "Уровень", "ui.col.where": "Где", "ui.col.message": "Сообщение",
        "ui.severity.error": "ошибка", "ui.severity.warning": "предупреждение", "ui.severity.info": "инфо",
        "ui.pooled": "все запуски",
    }
)

RU.update(
    {
        "ui.runs": "Запуски", "ui.targets": "Мишени", "ui.groups": "Группы",
        "ui.add_run": "Добавить запуск…", "ui.import_layout": "Импорт разметки…",
        "ui.wells_n": "{n} лунок",
        "ui.references": "Референсные гены", "ui.control_group": "Контрольная группа",
        "ui.efficiency": "Эффективность", "ui.eff.stdcurve": "по стандартам", "ui.eff.manual": "вручную", "ui.eff.ideal": "100 %",
        "ui.test": "Пост-хок тест", "ui.test.dunnett": "Даннет (против контроля)", "ui.test.tukey": "Тьюки (все пары)",
        "ui.thresholds": "Пороги QC",
        "ui.set.rep_sd_max": "SD реплик, макс.", "ui.set.ntc_cq_min": "Cq NTC, мин.", "ui.set.late_cq": "Поздний Cq",
        "ui.set.eff_min": "Эффективность, мин.", "ui.set.eff_max": "Эффективность, макс.", "ui.set.r2_min": "R², мин.",
        "ui.pool_std_runs": "Объединять стандарты всех запусков",
        "ui.none": "—",
        "ui.wizard.title": "Импорт таблицы", "ui.wizard.header_row": "Строка заголовка",
        "ui.wizard.preset": "Пресет", "ui.wizard.save_preset": "Сохранить как пресет:",
        "ui.wizard.required": "Укажите колонки лунки, мишени и Cq",
        "ui.field.well": "Лунка", "ui.field.target": "Мишень", "ui.field.cq": "Cq", "ui.field.sample": "Образец",
        "ui.field.role": "Роль", "ui.field.quantity": "Количество", "ui.field.group": "Группа",
    }
)

RU.update(
    {
        "menu.file": "Файл", "menu.edit": "Правка", "menu.view": "Вид", "menu.help": "Справка",
        "act.new": "Новый проект", "act.open": "Открыть…", "act.recent": "Последние", "act.save": "Сохранить",
        "act.save_as": "Сохранить как…", "act.add_run": "Добавить запуск…", "act.import_layout": "Импорт разметки…",
        "act.export_xlsx": "Экспорт в Excel…", "act.export_csv": "Экспорт в CSV…", "act.export_html": "HTML-отчёт…",
        "act.export_figures": "Рисунки (SVG)…", "act.exit": "Выход", "act.undo": "Отменить", "act.redo": "Повторить",
        "act.theme_auto": "Тема как в системе", "act.theme_light": "Светлая тема", "act.theme_dark": "Тёмная тема", "act.lang_ru": "Русский", "act.lang_en": "English", "act.about": "О программе",
        "tab.plate": "Планшет", "tab.data": "Данные", "tab.std": "Стандарты", "tab.expr": "Экспрессия", "tab.qc": "QC",
        "ui.untitled": "без имени",
        "ui.analysis_failed": "Расчёт не выполнен: {error}",
        "ui.status": "Запусков: {runs} · ошибок: {errors} · предупреждений: {warnings}",
        "ui.unsaved_title": "Несохранённые изменения", "ui.unsaved_text": "Сохранить изменения в проекте?",
        "ui.color_by": "Цвет:", "ui.color.target": "по мишени", "ui.color.role": "по роли",
        "ui.selection": "Выделено: {n}", "ui.apply": "Применить", "ui.exclude": "Исключить", "ui.include": "Вернуть",
        "ui.imported": "Импортировано {imported} из {total}; пропущено {skipped}",
        "ui.about_text": "qpcrkit {version}\nАнализ данных qPCR. Лицензия MIT.",
        "ui.filter_project": "Проект qpcrkit (*.qpcrkit.json)",
        "ui.filter_tables": "Экспорт прибора (*.csv *.txt *.xlsx *.rdml)",
        "ui.unsupported_file": "Этот файл программы прибора прочитать нельзя: {name}. Экспортируйте из неё RDML или таблицы CSV.",
        "ui.filter_layout": "Разметка (*.platekit.json *.csv *.txt)",
        "ui.export_failed": "Не удалось сохранить файл: {error}",
        "ui.import_failed": "Не удалось прочитать файл: {error}",
        "ui.crash_text": "Непредвиденная ошибка: {error}\nПроект можно сохранить и продолжить работу. Пожалуйста, отправьте отчёт разработчику.",
        "ui.copy_report": "Скопировать отчёт",
        "ui.btn.save": "Сохранить", "ui.btn.discard": "Не сохранять", "ui.btn.cancel": "Отмена",
        "ui.series": "Серия…", "ui.series_prefix": "Начало имени образца", "ui.series_replicates": "Реплик на образец",
        "ui.group_needs_sample": "Группа задаётся образцам: сначала назовите образцы этих лунок",
        "ui.map_pasted": "Из схемы планшета заполнено лунок: {n}",
        "ui.suggest_text": "В файле указаны референсные гены: {refs}; образец-калибратор: {calibrator}. Использовать их?",
        "act.paste_map": "Вставить схему планшета",
        "cli.file_error": "Не удалось обработать файл: {error}",
        "cli.bad_choice": "Нет такого значения: {name}. Есть: {options}",
        "ui.no_run": "Нет запусков: добавьте экспорт прибора (Файл → Добавить запуск)",
    }
)

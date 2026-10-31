"""Results export: styled xlsx, flat CSV, self-contained HTML report."""

from __future__ import annotations

import csv
import dataclasses
import html
import io
import os
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

import qpcr_core
from i18n import tr

from .figures import expression_figure, std_curve_figure
from .flags import flag_text
from .models import Project
from .pipeline import Results

_HEADER_FILL = PatternFill("solid", fgColor="1E293B")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_SEVERITY_FILL = {
    "error": PatternFill("solid", fgColor="FEE2E2"),
    "warning": PatternFill("solid", fgColor="FEF3C7"),
    "info": PatternFill("solid", fgColor="F1F5F9"),
}
CSV_COLUMNS = ["sample", "group", "target", "mean_cq", "delta_cq", "rq", "log2_rq"]


def _sheet(wb: Workbook, key: str, header: list[str], rows: list[list]):
    ws = wb.create_sheet(tr(key))
    ws.append(header)
    for row in rows:
        ws.append(row)
    for cell in ws[1]:
        cell.fill, cell.font = _HEADER_FILL, _HEADER_FONT
    ws.freeze_panes = "A2"
    for i, title in enumerate(header, start=1):
        width = max([len(str(title))] + [len(str(r[i - 1])) for r in rows if i - 1 < len(r) and r[i - 1] is not None])
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 8), 50)
    return ws


def _flag_rows(results: Results) -> list[list]:
    return [
        [f.severity, f.code, f.run_id or "", ", ".join(f.coords), f.target or "", f.sample or "", flag_text(f)]
        for f in results.flags
    ]


def export_xlsx(project: Project, results: Results, path: str | os.PathLike) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    groups = {n: s.group for n, s in project.samples.items()}

    raw = [
        [run.id, well.coord, well.sample or "", groups.get(well.sample or "", ""), rxn.target, rxn.fluor, rxn.role,
         rxn.cq, results.calibration.get((run.id, rxn.target), 0.0), rxn.quantity, "yes" if rxn.excluded else "", rxn.exclude_reason]
        for run, well, rxn in project.iter_reactions()
    ]
    _sheet(wb, "sheet.raw", ["Run", "Well", "Sample", "Group", "Target", "Fluor", "Role", "Cq", "Calibration factor", "Quantity", "Excluded", "Reason"], raw)

    ws = _sheet(wb, "sheet.qc", ["Severity", "Code", "Run", "Wells", "Target", "Sample", "Message"], _flag_rows(results))
    for row in ws.iter_rows(min_row=2):
        fill = _SEVERITY_FILL.get(row[0].value)
        if fill:
            for cell in row:
                cell.fill = fill

    std = [
        [t, run or "pooled", c.slope, c.intercept, c.r2, c.efficiency, c.n_levels, c.n_points, c.min_q, c.max_q, c.lowest_detected]
        for (run, t), c in results.std_curves.items()
    ]
    _sheet(wb, "sheet.std", ["Target", "Run", "Slope", "Intercept", "R²", "Efficiency", "Levels", "Points", "Min quantity", "Max quantity", "Lowest detected standard"], std)

    absq = [[q.run_id, q.sample, groups.get(q.sample, ""), q.target, q.mean_cq, q.quantity, "yes" if q.extrapolated else ""] for q in results.quantities]
    _sheet(wb, "sheet.abs", ["Run", "Sample", "Group", "Target", "Mean Cq", "Quantity", "Extrapolated"], absq)

    rel = [[r.sample, r.group, r.target, r.mean_cq, r.delta_cq, r.rq, r.log2_rq] for r in results.rqs]
    _sheet(wb, "sheet.rel", ["Sample", "Group", "Target", "Mean Cq", "ΔCq", "RQ", "log2 RQ"], rel)

    st = [[g.target, g.group, "", g.n, g.fold, g.mean_log2, g.sd_log2, g.sem_log2, g.ci95_log2, None, None, None] for g in results.groups]
    st += [[c.target, c.group_a, c.group_b, None, None, None, None, None, None, c.test, c.statistic, c.p, c.p_adj] for c in results.comparisons]
    _sheet(wb, "sheet.stats", ["Target", "Group", "vs group", "n", "Fold change", "Mean log2", "SD log2", "SEM log2", "95% CI log2", "Test", "Statistic", "p", "p adj (BH)"], st)

    s = project.settings
    params: list[list] = [["qpcrkit version", qpcr_core.__version__]]
    params += [["Run", f"{r.id}: {r.source_file or r.name} ({r.instrument})"] for r in project.runs]
    params += [["Reference gene", n] for n, t in project.targets.items() if t.kind == "reference"]
    params += [
        ["Efficiency", f"{n}: {results.efficiencies.get(n, 1.0):.4f} ({t.efficiency_mode})"]
        for n, t in project.targets.items()
    ]
    params += [[f.name, getattr(s, f.name)] for f in dataclasses.fields(s)]
    params += [["Excluded", f"{run.id} {well.coord} {rxn.target}", rxn.exclude_reason]
               for run, well, rxn in project.iter_reactions() if rxn.excluded]
    _sheet(wb, "sheet.params", ["Parameter", "Value", "Note"], params)
    wb.save(path)


def export_csv(results: Results, path: str | os.PathLike) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for r in results.rqs:
            w.writerow([r.sample, r.group, r.target, r.mean_cq, r.delta_cq, r.rq, r.log2_rq])


def _svg(fig) -> str:
    buf = io.StringIO()
    fig.set_size_inches(160 / 25.4, 100 / 25.4)
    fig.savefig(buf, format="svg")
    text = buf.getvalue()
    return text[text.index("<svg"):]


def _table(header: list[str], rows: list[list]) -> str:
    def fmt(v) -> str:
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.4g}"
        return html.escape(str(v))

    head = "".join(f"<th>{html.escape(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


_CSS = """
@page { size: A4; margin: 15mm; }
body { font-family: system-ui, sans-serif; font-size: 11px; color: #0f172a; max-width: 180mm; margin: auto; }
h1 { font-size: 18px; } h2 { font-size: 14px; border-bottom: 1px solid #cbd5e1; margin-top: 18px; }
table { border-collapse: collapse; margin: 6px 0; } th, td { border: 1px solid #cbd5e1; padding: 2px 6px; text-align: left; }
th { background: #1e293b; color: #fff; } .error { background: #fee2e2; } .warning { background: #fef3c7; }
svg { max-width: 100%; height: auto; }
"""


def export_html(project: Project, results: Results, path: str | os.PathLike) -> None:
    parts = [f"<h1>qpcrkit {html.escape(qpcr_core.__version__)}</h1>"]
    serious = [f for f in results.flags if f.severity in ("error", "warning")]
    if serious:
        items = "".join(
            f'<li class="{f.severity}">{html.escape(" ".join(x for x in (f.run_id, ", ".join(f.coords), f.target, f.sample) if x))}: '
            f"{html.escape(flag_text(f))}</li>"
            for f in serious
        )
        parts.append(f"<h2>{html.escape(tr('sheet.qc'))}</h2><ul>{items}</ul>")

    parts.append(f"<h2>{html.escape(tr('sheet.rel'))}</h2>")
    for target in sorted({g.target for g in results.groups}):
        parts.append(_svg(expression_figure(results, target, error=project.settings.error_bar)))
    parts.append(_table(
        ["Target", "Group", "n", "Fold change", "SD log2", "SEM log2", "95% CI log2"],
        [[g.target, g.group, g.n, g.fold, g.sd_log2, g.sem_log2, g.ci95_log2] for g in results.groups],
    ))
    if results.comparisons:
        parts.append(f"<h2>{html.escape(tr('sheet.stats'))}</h2>")
        parts.append(_table(
            ["Target", "Group A", "Group B", "Test", "Statistic", "p", "p adj (BH)"],
            [[c.target, c.group_a, c.group_b, c.test, c.statistic, c.p, c.p_adj] for c in results.comparisons],
        ))
    if results.std_curves:
        parts.append(f"<h2>{html.escape(tr('sheet.std'))}</h2>")
        for curve in results.std_curves.values():
            parts.append(_svg(std_curve_figure(curve)))

    doc = (
        '<!doctype html><html><head><meta charset="utf-8"><title>qpcrkit report</title>'
        f"<style>{_CSS}</style></head><body>{''.join(parts)}</body></html>"
    )
    Path(path).write_text(doc, encoding="utf-8")

"""qpcrkit command line: inspect / new / analyze, without Qt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from i18n import tr


def _inspect(args: argparse.Namespace) -> int:
    from qpcr_core.importers.base import UnknownFormatError, UnsupportedFileError
    from qpcr_core.importers.detect import import_file

    try:
        rep = import_file(args.file, "R1")
    except (UnknownFormatError, UnsupportedFileError):
        print(tr("cli.unknown_format", path=args.file), file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(tr("cli.file_error", error=exc), file=sys.stderr)
        return 2
    rxns = [r for w in rep.run.wells.values() for r in w.reactions]
    print(
        tr(
            "cli.inspect",
            fmt=rep.run.instrument,
            wells=len(rep.run.wells),
            reactions=len(rxns),
            targets=len({r.target for r in rxns}),
            samples=len(rep.samples),
            skipped=len(rep.skipped),
        )
    )
    for line, reason in rep.skipped:
        print(f"  #{line}: {reason}")
    return 0


def _new(args: argparse.Namespace) -> int:
    from qpcr_core.importers.base import UnknownFormatError, UnsupportedFileError, add_report
    from qpcr_core.importers.detect import import_files
    from qpcr_core.importers.platekit import apply_layout, read_instrument_layout, read_platekit_json
    from qpcr_core.models import Project
    from qpcr_core.sessions import save_project

    project = Project()
    try:
        for report in import_files(args.files):
            add_report(project, report)
            for note in report.notes:
                print(f"  {note}")
        if args.layout:
            reader = read_platekit_json if args.layout.endswith(".json") else read_instrument_layout
            layout = reader(args.layout)
            for run in project.runs:
                apply_layout(project, run.id, layout)
    except (UnknownFormatError, UnsupportedFileError) as exc:
        print(tr("cli.unknown_format", path=exc), file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(tr("cli.file_error", error=exc), file=sys.stderr)
        return 2
    unknown = [n for n in args.ref if n not in project.targets]
    if unknown:
        print(tr("cli.bad_choice", name=", ".join(unknown), options=", ".join(sorted(project.targets))), file=sys.stderr)
        return 2
    groups = sorted({s.group for s in project.samples.values() if s.group})
    if args.control and args.control not in groups:
        print(tr("cli.bad_choice", name=args.control, options=", ".join(groups) or "—"), file=sys.stderr)
        return 2
    for name in args.ref:
        project.targets[name].kind = "reference"
    if args.control:
        project.settings.control_group = args.control
    try:
        save_project(project, args.output)
    except OSError as exc:
        print(tr("cli.file_error", error=exc), file=sys.stderr)
        return 2
    print(tr("cli.saved", path=args.output))
    return 0


def _analyze(args: argparse.Namespace) -> int:
    from qpcr_core.flags import flag_text
    from qpcr_core.pipeline import analyze
    from qpcr_core.sessions import SessionError, load_project

    try:
        project = load_project(args.project)
    except SessionError as exc:
        print(exc, file=sys.stderr)
        return 2
    res = analyze(project)
    counts = {s: len(res.flags_by_severity(s)) for s in ("error", "warning", "info")}
    print(tr("cli.summary", **counts))
    for f in res.flags:
        if f.severity != "info":
            where = " ".join(x for x in (f.run_id, ",".join(f.coords), f.target, f.sample) if x)
            print(f"  [{f.severity}] {where}: {flag_text(f)}")

    outputs: list[str] = []
    try:
        if args.output:
            from qpcr_core import export

            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            export.export_xlsx(project, res, args.output)
            outputs.append(args.output)
        if args.csv:
            from qpcr_core.export import export_csv

            Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
            export_csv(res, args.csv)
            outputs.append(args.csv)
        if args.html:
            from qpcr_core.export import export_html

            Path(args.html).parent.mkdir(parents=True, exist_ok=True)
            export_html(project, res, args.html)
            outputs.append(args.html)
        if args.figures:
            from qpcr_core.figures import expression_figure, safe_name, save_figure, std_curve_figure

            out = Path(args.figures)
            out.mkdir(parents=True, exist_ok=True)
            for target in sorted({g.target for g in res.groups}):
                fig = expression_figure(res, target, error=project.settings.error_bar)
                save_figure(fig, out / f"expression_{safe_name(target)}.svg")
            for (run_id, target), curve in res.std_curves.items():
                save_figure(std_curve_figure(curve), out / f"stdcurve_{safe_name(target)}_{run_id or 'pooled'}.svg")
            outputs.append(str(out))
    except OSError as exc:
        print(tr("cli.file_error", error=exc), file=sys.stderr)
        return 2
    for path in outputs:
        print(tr("cli.saved", path=path))
    return 1 if args.strict and counts["error"] else 0


def _gui(args: argparse.Namespace) -> int:
    from ui.main_window import run

    return run(Path(args.project) if args.project else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpcrkit", description="qPCR analysis (headless)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("gui", help="open the desktop application (default without a command)")
    p.add_argument("project", nargs="?")
    p.set_defaults(func=_gui)

    p = sub.add_parser("inspect", help="detect the format of an instrument export and summarize it")
    p.add_argument("file")
    p.set_defaults(func=_inspect)

    p = sub.add_parser("new", help="create a project from instrument exports")
    p.add_argument("files", nargs="+", help="instrument exports or folders")
    p.add_argument("--layout", help=".platekit.json or an instrument plate layout CSV")
    p.add_argument("--ref", action="append", default=[], help="reference gene (repeatable)")
    p.add_argument("--control", help="control group name")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=_new)

    p = sub.add_parser("analyze", help="analyze a project and export results")
    p.add_argument("project")
    p.add_argument("-o", "--output", help="results .xlsx")
    p.add_argument("--csv")
    p.add_argument("--html")
    p.add_argument("--figures", help="directory for SVG figures")
    p.add_argument("--strict", action="store_true", help="exit 1 if there are QC errors")
    p.set_defaults(func=_analyze)

    args = parser.parse_args(argv)
    if args.command is None:
        args.project = None
        return _gui(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

import subprocess
import sys
from pathlib import Path

import pytest

from qpcr_cli import main
from qpcr_core.pipeline import analyze
from qpcr_core.sessions import load_project, save_project

ROOT = Path(__file__).resolve().parent.parent
RUN1, RUN2 = ROOT / "examples" / "demo_run1.csv", ROOT / "examples" / "demo_run2.csv"


@pytest.fixture
def project_file(tmp_path):
    path = tmp_path / "exp.qpcrkit.json"
    assert main(["new", str(RUN1), str(RUN2), "--ref", "GAPDH", "--control", "Ctrl", "-o", str(path)]) == 0
    return path


def test_inspect(capsys):
    assert main(["inspect", str(RUN1)]) == 0
    assert "cfx" in capsys.readouterr().out


def test_inspect_unknown_format(tmp_path, capsys):
    p = tmp_path / "g.csv"
    p.write_text("Pos,Gene,Ct\nA1,IL6,20\n", encoding="utf-8")
    assert main(["inspect", str(p)]) == 2
    assert capsys.readouterr().err


def test_new(project_file):
    p = load_project(project_file)
    assert [r.id for r in p.runs] == ["R1", "R2"]
    assert p.targets["GAPDH"].kind == "reference"
    assert p.settings.control_group == "Ctrl"
    assert p.samples["LPS-1"].group == "LPS"


def test_analyze_outputs(project_file, tmp_path):
    out = tmp_path / "out"
    args = ["analyze", str(project_file), "-o", str(out / "r.xlsx"), "--csv", str(out / "r.csv"),
            "--html", str(out / "r.html"), "--figures", str(out / "figs")]
    assert main(args) == 0
    for name in ("r.xlsx", "r.csv", "r.html"):
        assert (out / name).stat().st_size > 0
    assert list((out / "figs").glob("*.svg"))


def test_demo_fold_change(project_file):
    res = analyze(load_project(project_file))
    lps = next(g for g in res.groups if (g.target, g.group) == ("IL6", "LPS"))
    assert 6 <= lps.fold <= 10


def test_strict(project_file):
    p = load_project(project_file)
    ntc = next(r for _, _, r in p.iter_reactions() if r.role == "ntc")
    ntc.cq = 30.0
    save_project(p, project_file)
    assert main(["analyze", str(project_file)]) == 0
    assert main(["analyze", str(project_file), "--strict"]) == 1


def test_no_qt_imported():
    code = f"import sys, qpcr_cli; qpcr_cli.main(['inspect', r'{RUN1}']); print('PySide6' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=ROOT)
    assert out.stdout.strip().splitlines()[-1] == "False"


def test_gui_launch(monkeypatch):
    calls = []
    monkeypatch.setattr("ui.main_window.run", lambda project=None: calls.append(project) or 0)
    assert main([]) == 0
    assert main(["gui"]) == 0
    assert main(["gui", "x.qpcrkit.json"]) == 0
    assert calls == [None, None, Path("x.qpcrkit.json")]


def test_new_accepts_a_folder(tmp_path):
    src = ROOT / "tests" / "data" / "real"
    folder = tmp_path / "plate"
    folder.mkdir()
    for p in src.glob("2016-09-04 gapdh*"):
        (folder / p.name).write_bytes(p.read_bytes())
    out = tmp_path / "x.qpcrkit.json"
    assert main(["new", str(folder), "-o", str(out)]) == 0
    r = load_project(out).runs[0].wells["A1"].reactions[0]
    assert r.amplification is not None


def test_missing_file_is_a_message(tmp_path, capsys):
    missing = tmp_path / "none.csv"
    assert main(["inspect", str(missing)]) == 2
    assert main(["new", str(missing), "-o", str(tmp_path / "x.json")]) == 2
    assert main(["analyze", str(missing)]) == 2
    assert "none.csv" in capsys.readouterr().err


def test_unknown_ref_and_control_are_errors(tmp_path, capsys):
    out = tmp_path / "x.qpcrkit.json"
    assert main(["new", str(RUN1), "--ref", "NOPE", "-o", str(out)]) == 2
    err = capsys.readouterr().err
    assert "NOPE" in err and "GAPDH" in err
    assert main(["new", str(RUN1), "--control", "NOPE", "-o", str(out)]) == 2
    err = capsys.readouterr().err
    assert "NOPE" in err and "Ctrl" in err
    assert not out.exists()


def test_locked_output_is_a_message(project_file, tmp_path, monkeypatch, capsys):
    def locked(*a, **k):
        raise PermissionError("file is open in Excel")

    monkeypatch.setattr("qpcr_core.export.export_xlsx", locked)
    assert main(["analyze", str(project_file), "-o", str(tmp_path / "r.xlsx")]) == 2
    assert "Excel" in capsys.readouterr().err


def test_figure_names_are_safe(project_file, tmp_path):
    from qpcr_core.figures import safe_name

    assert safe_name("a/b:c") == "a_b_c"
    assert safe_name("IL-6") == "IL-6"
    assert safe_name("ген 1") == "ген_1"


def test_changelog_section(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("changelog_section", ROOT / "scripts" / "changelog_section.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text = "# Changelog\n\n## [1.1.0] — 2026-12-01\n\n### Added\n- New\n\n## [1.0.0] — 2026-11-01\n\n- Old\n"
    assert mod.section(text, "1.1.0") == "### Added\n- New"
    assert mod.section(text, "v1.0.0") == "- Old"
    assert mod.section(text, "9.9.9") == ""


def test_control_may_come_from_the_layout(tmp_path):
    src = ROOT / "tests" / "data" / "real" / "cfx_maestro_example01.csv"
    layout = ROOT / "tests" / "data" / "plan.platekit.json"
    out = tmp_path / "x.qpcrkit.json"
    assert main(["new", str(src), "--layout", str(layout), "--control", "Ctrl", "-o", str(out)]) == 0


def test_missing_layout_is_a_message(tmp_path, capsys):
    assert main(["new", str(RUN1), "--layout", str(tmp_path / "no.csv"), "-o", str(tmp_path / "x.json")]) == 2
    assert "no.csv" in capsys.readouterr().err


def test_changelog_script_fails_on_unknown_version():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "changelog_section.py"), "v9.9.9"], capture_output=True, text=True)
    assert out.returncode == 1 and "9.9.9" in out.stderr

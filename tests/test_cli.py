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

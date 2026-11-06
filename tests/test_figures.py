import subprocess
import sys

import pytest

from qpcr_core.figures import expression_figure, save_figure, significance_stars, std_curve_figure
from qpcr_core.pipeline import analyze
from tests.test_pipeline import demo_project


@pytest.fixture(scope="module")
def results():
    return analyze(demo_project())


def test_stars():
    assert significance_stars(0.0004) == "***"
    assert significance_stars(0.004) == "**"
    assert significance_stars(0.03) == "*"
    assert significance_stars(0.2) == ""
    assert significance_stars(None) == ""
    assert significance_stars(float("nan")) == ""


def test_std_curve_figure(results):
    fig = std_curve_figure(results.std_curves[(None, "IL6")])
    assert len(fig.axes) == 1
    texts = [t.get_text() for t in fig.axes[0].texts] + [fig.axes[0].get_title()]
    assert any("R²" in t for t in texts)


def test_expression_figure_bars(results):
    fig = expression_figure(results, "IL6")
    assert len(fig.axes[0].patches) == 3


def test_expression_log2(results):
    fig = expression_figure(results, "IL6", error="ci95", log2=True)
    assert "log2" in fig.axes[0].get_ylabel()


@pytest.mark.parametrize("suffix,magic", [(".svg", b"<?xml"), (".pdf", b"%PDF"), (".png", b"\x89PNG")])
def test_save_formats(results, tmp_path, suffix, magic):
    path = tmp_path / f"f{suffix}"
    save_figure(expression_figure(results, "IL6"), path)
    assert path.read_bytes().startswith(magic)


def test_save_unknown_suffix(results, tmp_path):
    with pytest.raises(ValueError):
        save_figure(expression_figure(results, "IL6"), tmp_path / "f.bmp")


def test_no_pyplot():
    code = "import qpcr_core.figures, sys; print('matplotlib.pyplot' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# --- curves ---


def _curve_project():
    from qpcr_core.models import Project, Reaction, Run, Well
    from tests.curve_factory import logistic, melt

    wells = {}
    for i, c in enumerate((20, 22, 24, 26)):
        rxn = Reaction(target="T", fluor="FAM", amplification=logistic(c, seed=i, noise=0.002), melt=melt(tm=84.0))
        wells[f"A{i + 1}"] = Well(f"A{i + 1}", f"s{i}", [rxn])
    wells["B1"] = Well("B1", "x", [Reaction(target="U", fluor="HEX", amplification=logistic(25))])
    wells["B2"] = Well("B2", "x", [Reaction(target="T", fluor="FAM", cq=22.0)])
    p = Project(runs=[Run(id="R1", name="R1", wells=wells)])
    p.ensure_targets_and_samples()
    return p


def _lines(fig) -> int:
    return sum(len(c.get_segments()) for c in fig.axes[0].collections)


def test_amplification_figure_draws_one_line_per_curve():
    from qpcr_core.figures import amplification_figure
    from qpcr_core.pipeline import analyze

    p = _curve_project()
    res = analyze(p)
    assert _lines(amplification_figure(p, res, "R1")) == 5
    assert _lines(amplification_figure(p, res, "R1", target="T")) == 4


def test_amplification_figure_shows_thresholds():
    from qpcr_core.figures import amplification_figure
    from qpcr_core.pipeline import analyze

    p = _curve_project()
    res = analyze(p)
    assert len(amplification_figure(p, res, "R1", target="T").axes[0].lines) == 1
    assert len(amplification_figure(p, res, "R1", target="T", threshold=False).axes[0].lines) == 0


def test_amplification_figure_on_a_log_axis_with_non_positive_values():
    import io

    from qpcr_core.figures import amplification_figure
    from qpcr_core.pipeline import analyze

    p = _curve_project()
    fig = amplification_figure(p, analyze(p), "R1", log=True)
    assert fig.axes[0].get_yscale() == "log"
    fig.savefig(io.BytesIO(), format="svg")


def test_melt_figure():
    from qpcr_core.curves import melt_derivative
    from qpcr_core.figures import melt_figure
    from qpcr_core.pipeline import analyze
    from tests.curve_factory import melt

    p = _curve_project()
    p.runs[0].wells["B2"].reactions[0].melt_derivative = melt_derivative(melt(tm=80.0))  # ready, drawn as it is
    fig = melt_figure(p, analyze(p), "R1")
    assert _lines(fig) == 5
    tops = [round(s[s[:, 1].argmax(), 0]) for s in fig.axes[0].collections[0].get_segments()]
    assert sorted(tops) == [80, 84, 84, 84, 84]

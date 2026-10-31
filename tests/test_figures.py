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

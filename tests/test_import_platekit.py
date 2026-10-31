from pathlib import Path

from qpcr_core.importers.platekit import LayoutWell, apply_layout, read_instrument_layout, read_platekit_json
from tests.factories import make_project

DATA = Path(__file__).parent / "data"


def _project():
    return make_project(
        [
            ("R1", "A1", None, "GAPDH", "unknown", 20.0, None),
            ("R1", "A1", None, "IL6", "unknown", 25.0, None),
            ("R1", "A2", None, "GAPDH", "unknown", 30.0, None),
            ("R1", "A2", None, "IL6", "unknown", 18.0, None),
            ("R1", "A3", None, "IL6", "unknown", 22.0, None),
        ]
    )


def test_read_platekit_json():
    lay = read_platekit_json(DATA / "plan.platekit.json")
    assert lay["A1"] == LayoutWell("A1", sample="c1", group="Ctrl", role="unknown")
    assert lay["A2"].target == "IL6" and lay["A2"].quantity == 1000.0 and lay["A2"].role == "std"
    assert lay["A3"].role == "pos"
    assert "A4" not in lay


def test_apply_layout():
    p = _project()
    changed = apply_layout(p, "R1", read_platekit_json(DATA / "plan.platekit.json"))
    wells = p.runs[0].wells
    assert changed == 3
    assert wells["A1"].sample == "c1" and p.samples["c1"].group == "Ctrl"
    assert [r.role for r in wells["A1"].reactions] == ["unknown", "unknown"]
    gapdh, il6 = wells["A2"].reactions
    assert (il6.role, il6.quantity) == ("std", 1000.0)
    assert (gapdh.role, gapdh.quantity) == ("unknown", None)
    assert "H12" not in wells


def test_read_instrument_layout_cfx(tmp_path):
    p = tmp_path / "layout.csv"
    p.write_text(
        "Well,Fluor,Target,Content,Sample,Biological Set Name,Starting Quantity\n"
        "A01,SYBR,GAPDH,Unkn,c1,Ctrl,\n"
        "A02,SYBR,IL6,Std,std-a,,1000\n",
        encoding="utf-8",
    )
    lay = read_instrument_layout(p)
    assert lay["A1"] == LayoutWell("A1", sample="c1", target="GAPDH", role="unknown", group="Ctrl")
    assert lay["A2"] == LayoutWell("A2", sample="std-a", target="IL6", role="std", quantity=1000.0)

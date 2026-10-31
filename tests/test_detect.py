from pathlib import Path

import pytest

from qpcr_core.importers.base import UnknownFormatError
from qpcr_core.importers.detect import detect_format, import_file
from qpcr_core.importers.generic_csv import ColumnMapping
from qpcr_core.importers.textio import read_rows

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize(
    "name,fmt",
    [("cfx_basic.csv", "cfx"), ("qs_results.txt", "quantstudio"), ("qs7500_384_numeric.txt", "quantstudio"), ("rotorgene_quant.csv", "rotorgene")],
)
def test_detect_known(name, fmt):
    assert detect_format(read_rows(DATA / name)) == fmt


def test_generic_needs_mapping(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("Pos,Gene,Ct\nA1,IL6,20\n", encoding="utf-8")
    assert detect_format(read_rows(p)) is None
    with pytest.raises(UnknownFormatError):
        import_file(p, "R1")
    rep = import_file(p, "R1", ColumnMapping(well="Pos", target="Gene", cq="Ct"))
    assert rep.run.wells["A1"].reactions[0].cq == 20.0


def test_import_file_sets_run_id():
    rep = import_file(DATA / "cfx_basic.csv", "R7")
    assert rep.run.id == "R7"
    assert rep.run.source_file == "cfx_basic.csv"

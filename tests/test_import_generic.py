import pytest

from qpcr_core.importers.generic_csv import ColumnMapping, parse
from qpcr_core.importers.textio import read_rows


def _file(tmp_path):
    p = tmp_path / "g.csv"
    p.write_bytes("Pos;Gene;Ct;Name;Kind;Grp\nA1;IL6;20,5;S1;ntc;\nA2;IL6;21,25;S2;;LPS\n".encode("cp1251"))
    return p


def test_parse_with_mapping(tmp_path):
    m = ColumnMapping(well="Pos", target="Gene", cq="Ct", sample="Name", role="Kind", group="Grp")
    rep = parse(read_rows(_file(tmp_path)), m, "g.csv", "R1")
    assert rep.run.wells["A2"].reactions[0].cq == 21.25
    assert rep.run.wells["A1"].reactions[0].role == "ntc"
    assert rep.run.wells["A2"].reactions[0].role == "unknown"
    assert rep.samples["S2"].group == "LPS"
    assert rep.run.instrument == "generic"


def test_missing_column_named(tmp_path):
    m = ColumnMapping(well="Pos", target="Gene", cq="Cq")
    with pytest.raises(ValueError, match="Cq"):
        parse(read_rows(_file(tmp_path)), m, "g.csv", "R1")


def test_mapping_round_trip():
    m = ColumnMapping(well="W", target="T", cq="C", quantity="Q", header_row=2)
    assert ColumnMapping.from_dict(m.to_dict()) == m


def test_quantity_column_style():
    rows = [["W", "G", "C", "K", "Q"], ["A1", "IL6", "20", "Std", "1,250.0"], ["A2", "IL6", "21", "Std", "2,500.0"]]
    rep = parse(rows, ColumnMapping(well="W", target="G", cq="C", role="K", quantity="Q"), "g", "R1")
    assert rep.run.wells["A2"].reactions[0].quantity == 2500.0

import openpyxl
import pytest

from qpcr_core.importers.textio import parse_cq, parse_number, read_rows


def test_utf8_bom_comma(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("﻿Well,Cq\nA1,20.5\n".encode("utf-8"))
    assert read_rows(p) == [["Well", "Cq"], ["A1", "20.5"]]


def test_utf16_tab(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Well\tCq\nA1\t20.5\n", encoding="utf-16")
    assert read_rows(p) == [["Well", "Cq"], ["A1", "20.5"]]


def test_cp1251_semicolon_decimal_comma(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("Лунка;Образец;Cq\nA1;Контроль 1;20,5\nA2; Контроль 2 ;21,0\n".encode("cp1251"))
    rows = read_rows(p)
    assert rows[1] == ["A1", "Контроль 1", "20,5"]
    assert rows[2][1] == "Контроль 2"
    assert parse_cq(rows[1][2]) == 20.5


def test_preamble_does_not_confuse_delimiter(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("Experiment: demo, run 1\n\nWell,Target,Cq\nA1,IL6,20.1\nA2,IL6,20.2\n", encoding="utf-8")
    rows = read_rows(p)
    assert ["Well", "Target", "Cq"] in rows


def _xlsx(path, sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.save(path)


def test_xlsx_prefers_results_sheet(tmp_path):
    p = tmp_path / "a.xlsx"
    _xlsx(p, [("Info", [["x"]]), ("Results", [["Well", "CT"], ["A1", 20.123456789], ["A2", None]])])
    assert read_rows(p) == [["Well", "CT"], ["A1", "20.123456789"], ["A2", ""]]


def test_xlsx_first_sheet_without_results(tmp_path):
    p = tmp_path / "a.xlsx"
    _xlsx(p, [("0", [["Well", "Cq"], ["A1", 21]]), ("Other", [["y"]])])
    assert read_rows(p) == [["Well", "Cq"], ["A1", "21"]]


def test_parse_number():
    assert parse_number("1,5e3") == 1500.0
    assert parse_number(" 2.5 ") == 2.5
    assert parse_number("") is None
    assert parse_number("abc") is None


@pytest.mark.parametrize("s", ["Undetermined", "N/A", "NaN", "No Ct", "—", "-", "", "undetermined"])
def test_parse_cq_missing(s):
    assert parse_cq(s) is None


def test_parse_cq_value():
    assert parse_cq("23,45") == 23.45

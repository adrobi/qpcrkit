import pytest

from qpcr_core.models import coord_from_index, format_coord, parse_coord
from tests.factories import make_project


def test_parse_coord():
    assert parse_coord("B12") == (1, 11)
    assert parse_coord("b012") == (1, 11)


def test_parse_coord_rejects_garbage():
    with pytest.raises(ValueError):
        parse_coord("Z99")


def test_format_coord():
    assert format_coord(15, 23) == "P24"


def test_coord_from_index():
    assert coord_from_index(25, 384) == "B1"
    assert coord_from_index(13, 96) == "B1"
    assert coord_from_index(7, 72) == "7"


def test_make_project_groups_reactions_per_well():
    p = make_project(
        [
            ("R1", "A1", "s1", "GAPDH", "unknown", 20.0, None),
            ("R1", "A1", "s1", "IL6", "unknown", 25.0, None),
        ],
        refs=("GAPDH",),
    )
    assert len(p.runs[0].wells) == 1
    assert len(p.runs[0].wells["A1"].reactions) == 2
    assert p.targets["GAPDH"].kind == "reference"
    assert p.targets["IL6"].kind == "target"
    assert len(list(p.iter_reactions())) == 2

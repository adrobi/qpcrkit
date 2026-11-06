"""The one thing the user should do next."""

from qpcr_core.hints import next_hint
from qpcr_core.models import Project, Reaction, Run, Well
from tests.factories import make_project

ROWS = [
    ("R1", "A1", "s1", "GAPDH", "unknown", 20.0, None),
    ("R1", "A2", "s2", "GAPDH", "unknown", 21.0, None),
    ("R1", "B1", "s1", "IL6", "unknown", 25.0, None),
    ("R1", "B2", "s2", "IL6", "unknown", 24.0, None),
]
GROUPS = {"s1": "Ctrl", "s2": "LPS"}


def _complete(**extra):
    kw = {"groups": GROUPS, "refs": ("GAPDH",), "control_group": "Ctrl"}
    kw.update(extra)
    return make_project(ROWS, **kw)


def _key(project):
    hint = next_hint(project)
    return hint.key if hint else None


def test_nothing_to_say_on_an_empty_project():
    assert next_hint(Project()) is None


def test_nothing_to_say_when_everything_is_set():
    assert next_hint(_complete()) is None


def test_wells_without_target_come_first():
    run = Run(id="R", name="R", wells={c: Well(c, None, [Reaction(target="SYBR", fluor="SYBR")]) for c in ("A1", "A2")})
    hint = next_hint(Project(runs=[run]))
    assert hint.key == "hint.no_target"
    assert hint.params == {"count": 2}
    assert hint.page == "plate"


def test_wells_without_sample_count_each_well_once():
    rows = [("R1", "A1", None, "T", "unknown", 20.0, None), ("R1", "A1", None, "U", "unknown", 20.0, None)]
    rows += [("R1", "A2", None, "T", "unknown", None, None), ("R1", "A3", None, "T", "ntc", None, None)]
    hint = next_hint(make_project(rows))
    assert hint.key == "hint.no_sample"
    assert hint.params == {"count": 2}


def test_excluded_wells_need_no_sample():
    p = make_project(ROWS + [("R1", "A3", None, "GAPDH", "unknown", 20.0, None)], groups=GROUPS, refs=("GAPDH",), control_group="Ctrl")
    p.runs[0].wells["A3"].reactions[0].excluded = True
    assert next_hint(p) is None


def test_then_the_reference():
    assert _key(_complete(refs=())) == "hint.no_reference"


def test_then_samples_without_group():
    hint = next_hint(_complete(groups={"s1": "Ctrl"}))
    assert hint.key == "hint.no_groups"
    assert hint.params == {"count": 1}


def test_a_calibrator_sample_needs_no_group():
    rows = ROWS + [("R1", "H1", "IRC", "GAPDH", "irc", 20.0, None), ("R1", "H2", None, "GAPDH", "std", 20.0, 100.0)]
    p = make_project(rows, groups=GROUPS, refs=("GAPDH",), control_group="Ctrl")
    assert next_hint(p) is None


def test_then_the_control():
    assert _key(_complete(control_group="")) == "hint.no_control"


def test_a_calibrator_sample_replaces_the_control():
    assert next_hint(_complete(control_group="", calibrator_sample="s1")) is None


def test_hints_have_texts():
    from i18n import tr

    for key, params in (
        ("hint.no_target", {"count": 2}),
        ("hint.no_sample", {"count": 2}),
        ("hint.no_reference", {}),
        ("hint.no_groups", {"count": 1}),
        ("hint.no_control", {}),
    ):
        assert tr(key, **params) != key

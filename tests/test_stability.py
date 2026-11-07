"""Stability of reference genes: geNorm and NormFinder."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from qpcr_core import stability as st

GENES = ["A", "B", "C", "D"]


def _by_definition_m(x: np.ndarray) -> np.ndarray:
    """M straight from Vandesompele 2002: mean SD of the log2 ratios with every other gene."""
    k = x.shape[1]
    out = []
    for j in range(k):
        sds = [np.std(x[:, j] - x[:, i], ddof=1) for i in range(k) if i != j]
        out.append(np.mean(sds))
    return np.array(out)


def _data(seed=1, n=6, k=4, spread=(0.1, 0.2, 0.4, 0.8)):
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 1, n)[:, None]  # the amount of material differs between samples
    return base + np.column_stack([rng.normal(0, s, n) for s in spread[:k]])


# --- log2 quantities ---


def test_log2_quantities_with_ideal_efficiency():
    mean_cq = {("s1", "A"): 20.0, ("s2", "A"): 22.0, ("s3", "A"): 21.0, ("s1", "B"): 25.0, ("s2", "B"): 25.5, ("s3", "B"): 26.0}
    x, kept, excluded = st.log2_quantities(mean_cq, {"A": 1.0, "B": 1.0}, ["s1", "s2", "s3"], ["A", "B"])
    assert kept == ("s1", "s2", "s3") and excluded == ()
    assert x[:, 0] == pytest.approx([0.0, -2.0, -1.0])
    assert x[:, 1] == pytest.approx([0.0, -0.5, -1.0])


def test_log2_quantities_use_the_efficiency():
    mean_cq = {("s1", "A"): 20.0, ("s2", "A"): 22.0}
    x, _, _ = st.log2_quantities(mean_cq, {"A": 0.9}, ["s1", "s2"], ["A"])
    assert x[1, 0] == pytest.approx(-2.0 * math.log2(1.9))


def test_samples_without_a_cq_are_excluded():
    mean_cq = {("s1", "A"): 20.0, ("s2", "A"): None, ("s3", "A"): 21.0, ("s1", "B"): 25.0, ("s2", "B"): 25.0, ("s3", "B"): 26.0}
    x, kept, excluded = st.log2_quantities(mean_cq, {}, ["s1", "s2", "s3", "s4"], ["A", "B"])
    assert kept == ("s1", "s3") and excluded == ("s2", "s4")
    assert x.shape == (2, 2)
    assert x[:, 0] == pytest.approx([0.0, -1.0])  # the minimum is taken over the kept samples


# --- geNorm M ---


def test_m_matches_the_definition():
    x = _data()
    assert st.genorm_m(x) == pytest.approx(_by_definition_m(x), abs=1e-12)


def test_m_does_not_depend_on_the_scale_of_a_gene():
    x = _data()
    y = x.copy()
    y[:, 2] += 7.3  # another primer pair, another absolute level
    assert st.genorm_m(y) == pytest.approx(st.genorm_m(x), abs=1e-12)


def test_genes_in_perfect_agreement_have_m_zero():
    base = np.array([0.0, 1.0, -0.5, 2.0])
    x = np.column_stack([base, base + 3.0])
    assert st.genorm_m(x) == pytest.approx([0.0, 0.0])
    assert not np.isnan(st.genorm_m(x)).any()


def test_a_constant_gene_is_fine():
    x = np.column_stack([np.zeros(5), _data(n=5)[:, :2]])
    assert np.isfinite(st.genorm_m(x)).all()


@pytest.mark.parametrize("shape", [(5, 1), (2, 3)])
def test_too_little_data(shape):
    with pytest.raises(ValueError):
        st.genorm_m(np.zeros(shape))


# --- stepwise exclusion ---


def test_stepwise_exclusion():
    x = _data()
    ranking, steps = st.genorm_ranking(x, GENES)
    remaining = list(GENES)
    expected_removed = []
    for _ in range(len(GENES) - 2):
        cols = [GENES.index(g) for g in remaining]
        m = _by_definition_m(x[:, cols])
        assert dict(steps)[tuple(remaining)] == pytest.approx(m.mean())
        worst = remaining[int(np.argmax(m))]
        expected_removed.append(worst)
        remaining.remove(worst)
    assert ranking == tuple(sorted(remaining)) + tuple(reversed(expected_removed))
    assert [s[0] for s in steps][0] == tuple(GENES) and len(steps[-1][0]) == 2
    assert ranking[-1] == "D"  # the noisiest gene goes first


def test_ties_are_broken_by_name():
    base = np.array([0.0, 1.0, -0.5, 2.0])
    noise = np.array([0.3, -0.3, 0.3, -0.3])
    x = np.column_stack([base, base, base + noise, base - noise])
    ranking, _ = st.genorm_ranking(x, ["A", "B", "C", "D"])
    assert ranking[-1] == "D"  # C and D are equally bad; the later name goes first


# --- pairwise variation and the advice ---


def test_pairwise_variation():
    x = _data()
    ranking, _ = st.genorm_ranking(x, GENES)
    v = st.pairwise_v(x, GENES, ranking)
    assert set(v) == {2, 3}
    for n in (2, 3):
        cols_n = [GENES.index(g) for g in ranking[:n]]
        cols_n1 = [GENES.index(g) for g in ranking[: n + 1]]
        expected = np.std(x[:, cols_n].mean(axis=1) - x[:, cols_n1].mean(axis=1), ddof=1)
        assert v[n] == pytest.approx(expected)


def test_no_pairwise_variation_with_two_genes():
    x = _data(k=2)
    assert st.pairwise_v(x, ["A", "B"], ("A", "B")) == {}


@pytest.mark.parametrize(
    "v,expected,found",
    [
        ({2: 0.10, 3: 0.05}, ("A", "B"), True),
        ({2: 0.20, 3: 0.12}, ("A", "B", "C"), True),
        ({2: 0.20, 3: 0.18}, ("A", "B", "C", "D"), False),
        ({}, ("A", "B"), True),
    ],
)
def test_recommend(v, expected, found):
    ranking = ("A", "B", "C", "D")[: 2 if not v else 4]
    assert st.recommend(ranking, v) == (expected, found)


# --- NormFinder ---


def _groups(n1=4, n2=4):
    return ["G1"] * n1 + ["G2"] * n2


def _nf_data(seed=3, n1=4, n2=4, shift=None, spread=(0.1, 0.15, 0.2, 0.25)):
    rng = np.random.default_rng(seed)
    n = n1 + n2
    base = rng.normal(0, 1, n)[:, None]
    x = base + np.column_stack([rng.normal(0, s, n) for s in spread])
    if shift is not None:
        gene, amount = shift
        x[n1:, gene] += amount
    return x


def test_differences_sum_to_zero_over_groups_with_unequal_sizes():
    x = _nf_data(n1=3, n2=5)
    r = st.normfinder(x, _groups(3, 5))
    assert r.groups_used == 2
    assert r.d.shape == (2, 4)
    # before shrinkage d sums to zero per gene; shrinkage multiplies each by a positive factor of one sign
    assert np.all(np.sign(r.d[0]) == -np.sign(r.d[1])) or np.allclose(r.d, 0)


def test_a_gene_shifted_in_one_group_ranks_last():
    x = _nf_data(shift=(0, 1.0))
    r = st.normfinder(x, _groups())
    assert int(np.argmax(r.rho)) == 0
    m = st.genorm_m(x)
    rank_rho = int(np.argsort(np.argsort(r.rho))[0])
    rank_m = int(np.argsort(np.argsort(m))[0])
    assert rank_rho == 3 and rank_rho >= rank_m


def test_without_groups_rho_is_the_corrected_sd():
    x = _nf_data()
    r = st.normfinder(x, [""] * x.shape[0])
    k = x.shape[1]
    resid = x - x.mean(axis=0) - x.mean(axis=1, keepdims=True) + x.mean()
    a = (resid**2).sum(axis=0) / (x.shape[0] - 1)
    sigma2 = np.maximum((a - a.sum() / (k * (k - 1))) / (1 - 2 / k), 0)
    assert r.groups_used == 0 and "no_groups" in r.notes
    assert r.rho == pytest.approx(np.sqrt(sigma2))
    assert r.v[0] == pytest.approx(sigma2)


def test_less_material_in_one_group_changes_nothing():
    x = _nf_data()
    y = x.copy()
    y[4:, :] -= 2.0  # every gene lower in G2: just less RNA
    assert st.normfinder(y, _groups()).rho == pytest.approx(st.normfinder(x, _groups()).rho)


def test_genes_in_perfect_agreement():
    base = np.array([0.0, 1.0, -0.5, 2.0, 0.3, 1.1])
    x = np.column_stack([base, base + 1, base + 2])
    for groups in (["G1"] * 3 + ["G2"] * 3, [""] * 6):
        r = st.normfinder(x, groups)
        assert r.rho == pytest.approx([0, 0, 0]) and np.isfinite(r.rho).all()


def test_a_group_of_one_sample_is_left_out():
    x = _nf_data(n1=4, n2=4)
    x = np.vstack([x, x[:1] + 0.1])
    groups = _groups() + ["G3"]
    r = st.normfinder(x, groups)
    assert r.groups_used == 2 and "small_groups" in r.notes


def test_samples_without_a_group_among_grouped_ones():
    x = _nf_data()
    groups = _groups()
    groups[0] = ""
    r = st.normfinder(x, groups)
    assert r.groups_used == 2 and "ungrouped_samples" in r.notes


def test_all_groups_of_one_sample_fall_back_to_no_groups():
    x = _nf_data(n1=4, n2=0)
    r = st.normfinder(x, ["a", "b", "c", "d"])
    assert r.groups_used == 0 and "no_groups" in r.notes and np.isfinite(r.rho).all()


def test_too_few_genes():
    with pytest.raises(ValueError):
        st.normfinder(_nf_data()[:, :2], _groups())


def test_best_pair_compensates():
    """Two genes shifted in opposite directions are worse alone but good together."""
    x = _nf_data(spread=(0.05, 0.05, 0.3, 0.3))
    x[4:, 0] += 0.6
    x[4:, 1] -= 0.6
    r = st.normfinder(x, _groups())
    pair, rho = st.normfinder_best_pair(r, GENES)
    assert set(pair) == {"A", "B"}
    assert rho < min(r.rho[0], r.rho[1])


def test_best_pair_without_groups():
    x = _nf_data(spread=(0.05, 0.08, 0.3, 0.4))
    r = st.normfinder(x, [""] * 8)
    pair, rho = st.normfinder_best_pair(r, GENES)
    assert set(pair) == {"A", "B"}
    assert rho == pytest.approx(math.sqrt((r.v[0][0] + r.v[0][1]) / 4))


def test_pairs_are_all_considered():
    x = _nf_data()
    r = st.normfinder(x, _groups())
    pair, rho = st.normfinder_best_pair(r, GENES)
    best = min(
        (np.mean(np.abs((r.d[:, a] + r.d[:, b]) / 2) + np.sqrt((r.v[:, a] + r.v[:, b]) / 4)), (GENES[a], GENES[b]))
        for a, b in itertools.combinations(range(4), 2)
    )
    assert rho == pytest.approx(best[0]) and pair == best[1]


# --- inside the project and the analysis ---

from qpcr_core.editing import EditHistory, rename_target_in_run, set_stability_candidate, set_target  # noqa: E402
from qpcr_core.pipeline import analyze  # noqa: E402
from qpcr_core.sessions import load_project, save_project  # noqa: E402
from tests.factories import make_project  # noqa: E402
from tests.test_pipeline import demo_project  # noqa: E402


def _three_refs(shift_lps=0.0, refs=("R1", "R2", "R3"), samples_per_group=4, drop=None, fourth=False):
    """Ctrl and LPS, three references and one target; R3 may move with the treatment."""
    rng = np.random.default_rng(7)
    rows, groups = [], {}
    for g_index, group in enumerate(("Ctrl", "LPS")):
        for i in range(samples_per_group):
            sample = f"{group}-{i}"
            groups[sample] = group
            amount = rng.normal(0, 0.8)  # how much RNA went into this sample
            levels = {"R1": 20.0, "R2": 22.0, "R3": 24.0, "T": 27.0 - 2.0 * g_index}
            if fourth:
                levels["R4"] = 23.0  # one more stable gene, so that V can fall below 0.15
            for gene, level in levels.items():
                cq = level - amount + rng.normal(0, 0.08)
                if gene == "R3" and group == "LPS":
                    cq += shift_lps
                if drop == (sample, gene):
                    cq = None
                for rep in range(2):
                    rows.append(("R1", f"{sample}-{gene}-{rep}", sample, gene, "unknown", cq, None))
    return make_project(rows, groups=groups, refs=refs, control_group="Ctrl")


def test_candidates_default_to_the_references():
    p = _three_refs()
    assert st.stability_candidates(p) == ["R1", "R2", "R3"]


def test_without_references_every_target_is_a_candidate():
    p = _three_refs(refs=())
    assert st.stability_candidates(p) == ["R1", "R2", "R3", "T"]


def test_explicit_choice_wins():
    p = _three_refs()
    set_stability_candidate(p, "T", True)
    set_stability_candidate(p, "R1", False)
    assert st.stability_candidates(p) == ["R2", "R3", "T"]
    set_stability_candidate(p, "R1", None)
    assert st.stability_candidates(p) == ["R1", "R2", "R3", "T"]


def test_results_have_the_ranking():
    res = analyze(_three_refs(shift_lps=3.0))
    s = res.stability
    assert s.candidates[-1] == "R3"
    assert set(s.genorm_m) == {"R1", "R2", "R3"}
    assert s.pairwise_v and 2 in s.pairwise_v
    assert set(s.normfinder_rho) == {"R1", "R2", "R3"} and s.groups_used == 2
    assert s.best_pair is not None
    assert len(s.samples) == 8 and s.excluded_samples == ()


def test_an_unstable_reference_is_flagged():
    res = analyze(_three_refs(shift_lps=3.0))
    flags = [f for f in res.flags if f.code == "reference_unstable"]
    assert [f.target for f in flags] == ["R3"]
    assert flags[0].params["m"] > 1.0 and flags[0].params["limit"] == 1.0
    assert flags[0].severity == "warning"


def test_stable_references_raise_nothing():
    res = analyze(_three_refs())
    assert not [f for f in res.flags if f.code in ("reference_unstable", "single_reference")]


def test_the_limit_is_a_setting():
    p = _three_refs(shift_lps=1.0)
    m = analyze(p).stability.genorm_m["R3"]
    p.settings.genorm_m_max = m + 0.1
    assert not [f for f in analyze(p).flags if f.code == "reference_unstable"]
    p.settings.genorm_m_max = m - 0.1
    assert [f for f in analyze(p).flags if f.code == "reference_unstable"]


def test_one_reference_gets_the_miqe_note():
    res = analyze(demo_project())
    flag = next(f for f in res.flags if f.code == "single_reference")
    assert flag.severity == "info"
    assert res.stability.genorm_m == {} and "few_candidates" in res.stability.notes


def test_samples_without_a_cq_are_counted():
    res = analyze(_three_refs(drop=("LPS-1", "R2")))
    flag = next(f for f in res.flags if f.code == "stability_samples_excluded")
    assert flag.params["count"] == 1 and res.stability.excluded_samples == ("LPS-1",)


def test_two_candidates_give_genorm_only():
    p = _three_refs(refs=("R1", "R2"))
    s = analyze(p).stability
    assert set(s.genorm_m) == {"R1", "R2"} and s.pairwise_v == {}
    assert s.normfinder_rho == {} and s.best_pair is None
    assert s.recommended == ("R1", "R2")


def test_two_references_and_two_samples_do_not_fail():
    p = _three_refs(refs=("R1", "R2"), samples_per_group=1)
    res = analyze(p)
    assert not [f for f in res.flags if f.code == "reference_unstable"]
    assert "few_samples" in res.stability.notes


def test_rq_does_not_change():
    before = {(r.sample, r.target): r.rq for r in analyze(_three_refs(shift_lps=3.0)).rqs}
    p = _three_refs(shift_lps=3.0)
    set_stability_candidate(p, "T", True)
    assert {(r.sample, r.target): r.rq for r in analyze(p).rqs} == before


def test_candidate_choice_is_saved(tmp_path):
    p = _three_refs()
    set_stability_candidate(p, "T", True)
    path = tmp_path / "p.qpcrkit.json"
    save_project(p, path)
    q = load_project(path)
    assert q.targets["T"].stability_candidate is True and q.targets["R1"].stability_candidate is None


def test_rename_carries_the_choice():
    p = _three_refs()
    set_stability_candidate(p, "R3", False)
    rename_target_in_run(p, "R1", "R3", "HPRT1")
    assert p.targets["HPRT1"].stability_candidate is False and "R3" not in p.targets


def test_rename_into_an_existing_target_keeps_its_choice():
    p = _three_refs()
    set_stability_candidate(p, "R2", True)
    set_stability_candidate(p, "R3", False)
    rename_target_in_run(p, "R1", "R3", "R2")
    assert p.targets["R2"].stability_candidate is True


def test_a_target_gone_from_every_well_takes_its_choice_along():
    p = _three_refs()
    set_stability_candidate(p, "T", True)
    coords = [w.coord for w in p.runs[0].wells.values() if w.reactions[0].target == "T"]
    set_target(p, "R1", coords, "IL6")
    assert "T" not in p.targets and p.targets["IL6"].stability_candidate is None


def test_choice_can_be_undone():
    p = _three_refs()
    history = EditHistory()
    history.record(p)
    set_stability_candidate(p, "T", True)
    assert history.undo(p).targets["T"].stability_candidate is None


# --- figures and export ---


def _stab_results(shift=3.0, refs=("R1", "R2", "R3")):
    p = _three_refs(shift_lps=shift, refs=refs)
    return p, analyze(p)


def test_genorm_figure():
    from qpcr_core.figures import genorm_figure

    _, res = _stab_results()
    s = res.stability
    fig = genorm_figure(s)
    steps_axis, v_axis = fig.axes
    assert len(steps_axis.lines[0].get_xdata()) == len(s.genorm_steps)
    assert len(v_axis.patches) == len(s.pairwise_v)
    assert any(list(line.get_ydata()) == [0.15, 0.15] for line in v_axis.lines)


def test_genorm_figure_without_v_has_one_axis():
    from qpcr_core.figures import genorm_figure

    _, res = _stab_results(refs=("R1", "R2"))
    assert len(genorm_figure(res.stability).axes) == 1


def test_normfinder_figure_best_on_top():
    from qpcr_core.figures import normfinder_figure

    _, res = _stab_results()
    s = res.stability
    ax = normfinder_figure(s).axes[0]
    assert len(ax.patches) == 3
    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert labels[-1] == min(s.normfinder_rho, key=s.normfinder_rho.get)  # barh draws the last label on top


def test_stability_figures_follow_the_style():
    from matplotlib.colors import to_hex

    from qpcr_core.figures import genorm_figure

    _, res = _stab_results()
    style = {"text.color": "#e6efed"}
    assert to_hex(genorm_figure(res.stability, style=style).axes[0].lines[0].get_color()) == "#e6efed"


def test_stability_sheet(tmp_path):
    import openpyxl

    from i18n import tr
    from qpcr_core.export import export_xlsx

    p, res = _stab_results()
    path = tmp_path / "s.xlsx"
    export_xlsx(p, res, path)
    rows = list(openpyxl.load_workbook(path)[tr("sheet.stability")].iter_rows(values_only=True))
    blocks = {r[0] for r in rows[1:]}
    assert {"geNorm", "geNorm steps", "V", "NormFinder", "Recommended", "Best pair"} <= blocks
    m = {r[1]: r[2] for r in rows if r[0] == "geNorm"}
    assert m["R3"] == pytest.approx(res.stability.genorm_m["R3"])


def test_no_stability_sheet_without_a_ranking(tmp_path):
    import openpyxl

    from i18n import tr
    from qpcr_core.export import export_xlsx

    p = demo_project()
    path = tmp_path / "s.xlsx"
    export_xlsx(p, analyze(p), path)
    assert tr("sheet.stability") not in openpyxl.load_workbook(path).sheetnames


def test_stability_in_the_html_report(tmp_path):
    from i18n import tr
    from qpcr_core.export import export_html

    p, res = _stab_results()
    path = tmp_path / "s.html"
    export_html(p, res, path)
    text = path.read_text(encoding="utf-8")
    section = text[text.index(tr("sheet.stability")):]
    assert section.count("<svg") >= 2 and "R3" in section


def test_cli_saves_the_stability_figures(tmp_path):
    from qpcr_cli import main

    p, _ = _stab_results()
    project = tmp_path / "p.qpcrkit.json"
    save_project(p, project)
    out = tmp_path / "figs"
    assert main(["analyze", str(project), "--figures", str(out)]) == 0
    assert (out / "stability_genorm.svg").exists() and (out / "stability_normfinder.svg").exists()


def test_two_candidates_save_genorm_only(tmp_path):
    from qpcr_cli import main

    p, _ = _stab_results(refs=("R1", "R2"))
    project = tmp_path / "p.qpcrkit.json"
    save_project(p, project)
    out = tmp_path / "figs"
    assert main(["analyze", str(project), "--figures", str(out)]) == 0
    assert (out / "stability_genorm.svg").exists() and not (out / "stability_normfinder.svg").exists()

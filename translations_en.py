"""English translation table."""

from __future__ import annotations

EN: dict[str, str] = {
    "qc.rep_sd_high": "Technical replicate SD = {sd:.2f} exceeds {limit:.2f}",
    "qc.outlier_suggested": "Replicate Cq {cq:.2f} is far from the median {median:.2f} — consider excluding it",
    "qc.partial_undetermined": "Some technical replicates have no Cq (Undetermined)",
    "qc.ntc_contamination": "No-template control gave Cq {cq:.2f} — possible contamination",
    "qc.late_amplification": "Late amplification: Cq {cq:.2f}",
    "qc.irc_missing": "No inter-run calibrators on this plate — no correction applied",
    "qc.no_irc": "Several plates without inter-run calibrators — Cq values are not aligned between them",
    "qc.std_levels_few": "Fewer than 3 standard levels ({levels}) — no curve fitted",
    "qc.efficiency_out_of_range": "Efficiency {eff:.1%} is outside 90–110 %",
    "qc.r2_low": "Standard curve R² {r2:.3f} is below 0.98",
    "qc.extrapolated": "Quantity {quantity:.3g} is outside the standard range (extrapolated)",
    "qc.no_control": "No control group or calibrator sample selected",
    "qc.no_reference_targets": "No reference genes selected",
    "qc.no_reference_for_sample": "No Cq for any reference gene in this sample",
    "qc.no_cq": "No Cq in any replicate",
    "qc.no_calibrator_cq": "The control group has no Cq for this target",
    "qc.too_few_bio_reps": "Group “{group}” has fewer than 2 biological replicates — no tests run",
    "qc.irc_partial": "This target's calibrators are not on every plate — common calibrators used instead",
    "qc.irc_no_common": "No calibrator is shared by all plates — Cq values are not aligned between plates",
    "qc.std_no_quantity": "Standard without quantity — not used in the curve",
    "qc.efficiency_unusable": "Curve efficiency {eff:.1%} is implausible (broken curve?) — manual or 100 % used",
    "qc.partial_reference": "Some reference genes have no Cq — normalized to the remaining ones",
    "qc.samples_without_group": "{count} sample(s) without a group — left out of relative expression",
    "sheet.raw": "Raw data",
    "sheet.qc": "QC",
    "sheet.std": "Standard curves",
    "sheet.abs": "Absolute quantification",
    "sheet.rel": "Relative expression",
    "sheet.stats": "Statistics",
    "sheet.params": "Analysis parameters",
}

EN.update(
    {
        "cli.unknown_format": "Unrecognized file format: {path}. Open it in qpcrkit with the CSV import wizard.",
        "cli.inspect": "Format: {fmt}\nWells: {wells}\nReactions: {reactions}\nTargets: {targets}\nSamples: {samples}\nSkipped rows: {skipped}",
        "cli.summary": "Errors: {error}, warnings: {warning}, info: {info}",
        "cli.saved": "Saved: {path}",
    }
)

EN.update(
    {
        "ui.col.run": "Run", "ui.col.well": "Well", "ui.col.sample": "Sample", "ui.col.group": "Group",
        "ui.col.target": "Target", "ui.col.role": "Role", "ui.col.cq": "Cq", "ui.col.quantity": "Quantity",
        "ui.col.excluded": "Excluded",
        "ui.filter": "Filter…",
        "ui.paste_hint": "Ctrl+V: paste sample — group — biological replicate columns from Excel",
        "ui.role.unknown": "sample", "ui.role.ntc": "NTC", "ui.role.std": "standard", "ui.role.irc": "calibrator (IRC)",
        "ui.role.pos": "positive control",
    }
)

EN.update(
    {
        "ui.no_curves": "No standard curves: mark standard wells and set their quantities",
        "ui.no_groups": "No expression data: choose reference genes, a control group and sample groups",
        "ui.no_flags": "No issues",
        "ui.target": "Target", "ui.curve": "Curve", "ui.error_bar": "Error bars", "ui.log2": "log2",
        "ui.error.sd": "SD", "ui.error.sem": "SEM", "ui.error.ci95": "95% CI",
        "ui.col.slope": "Slope", "ui.col.intercept": "Intercept", "ui.col.r2": "R²", "ui.col.efficiency": "Efficiency",
        "ui.col.lowest": "Lowest detected standard", "ui.col.n": "n", "ui.col.fold": "Fold change",
        "ui.col.group_b": "Versus", "ui.col.test": "Test", "ui.col.p": "p", "ui.col.p_adj": "p (BH)",
        "ui.col.severity": "Level", "ui.col.where": "Where", "ui.col.message": "Message",
        "ui.severity.error": "error", "ui.severity.warning": "warning", "ui.severity.info": "info",
        "ui.pooled": "all runs",
    }
)

EN.update(
    {
        "ui.runs": "Runs", "ui.targets": "Targets", "ui.groups": "Groups",
        "ui.add_run": "Add run…", "ui.import_layout": "Import layout…",
        "ui.wells_n": "{n} wells",
        "ui.references": "Reference genes", "ui.control_group": "Control group",
        "ui.efficiency": "Efficiency", "ui.eff.stdcurve": "from curve", "ui.eff.manual": "manual", "ui.eff.ideal": "100 %",
        "ui.test": "Post-hoc test", "ui.test.dunnett": "Dunnett (vs control)", "ui.test.tukey": "Tukey (all pairs)",
        "ui.thresholds": "QC thresholds",
        "ui.set.rep_sd_max": "Replicate SD, max", "ui.set.ntc_cq_min": "NTC Cq, min", "ui.set.late_cq": "Late Cq",
        "ui.set.eff_min": "Efficiency, min", "ui.set.eff_max": "Efficiency, max", "ui.set.r2_min": "R², min",
        "ui.pool_std_runs": "Pool standards across runs",
        "ui.none": "—",
        "ui.wizard.title": "Import table", "ui.wizard.header_row": "Header row",
        "ui.wizard.preset": "Preset", "ui.wizard.save_preset": "Save as preset:",
        "ui.wizard.required": "Choose the well, target and Cq columns",
        "ui.field.well": "Well", "ui.field.target": "Target", "ui.field.cq": "Cq", "ui.field.sample": "Sample",
        "ui.field.role": "Role", "ui.field.quantity": "Quantity", "ui.field.group": "Group",
    }
)

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
    "qc.efficiency_out_of_range": "Efficiency {eff:.1%} is outside {min:.0%}–{max:.0%}",
    "qc.r2_low": "Standard curve R² {r2:.3f} is below {min:.3g}",
    "qc.wells_without_sample": "{count} well(s) without a sample are left out of the analysis. Name them",
    "qc.nrt_amplified": "No-RT control gave Cq {cq:.2f}, less than {delta:g} cycles from the sample: possible genomic DNA",
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
    "qc.efficiency_curves_unusable": "Efficiency could not be estimated from the curves — 100 % used",
    "qc.efficiency_from_subtracted": "Efficiency comes from curves with the background already removed: less reliable",
    "qc.curve_unusable": "Curves that cannot be processed: {count}. They have no Cq of their own",
    "qc.mixed_cq_sources": "This target mixes instrument Cq with Cq calculated from curves: their thresholds differ",
    "qc.no_curve_for_calculated": "Cq from curves is selected, but {count} reactions have no curve and stay without Cq",
    "qc.thresholds_differ_no_irc": "Plates use different thresholds and there are no calibrators — Cq cannot be compared between plates",
    "qc.melt_multiple_peaks": "The melt curve has several significant peaks ({count}): possibly a second product",
    "qc.melt_tm_shift": "Tm {tm:.1f} °C differs from the target's median {median:.1f} °C",
    "qc.ntc_melt_product": "The no-template control has a melt peak at {tm:.1f} °C, same as the product: possible contamination",
    "qc.ntc_melt_other": "The no-template control has a melt peak at {tm:.1f} °C, away from the product: probably primer dimers",
    "qc.cq_source_disagree": "Instrument Cq and Cq from the curve differ by {delta:+.2f} cycles beyond the usual shift (limit {limit:.2f})",
    "qc.early_cq": "Very early Cq {cq:.2f}, below {min:g}: the background is unreliable, consider diluting the sample",
    "qc.no_amplification_with_cq": "The instrument gave a Cq for {count} reactions, but the curve does not grow",
    "qc.partial_reference": "Some reference genes have no Cq — normalized to the remaining ones",
    "qc.samples_without_group": "{count} sample(s) without a group — left out of relative expression",
    "sheet.raw": "Raw data",
    "sheet.qc": "QC",
    "sheet.std": "Standard curves",
    "sheet.abs": "Absolute quantification",
    "sheet.rel": "Relative expression",
    "sheet.curves": "Curves",
    "sheet.stats": "Statistics",
    "sheet.params": "Analysis parameters",
}

EN.update(
    {
        "tab.stab": "Stability",
        "stab.title": "Stability of reference genes",
        "stab.candidates": "Reference candidates",
        "stab.candidate": "{name} ({n} samples)",
        "stab.apply": "Make them the references",
        "stab.rank": "Rank",
        "stab.advice": "{n} references are recommended: {genes} (V = {v:.2f})",
        "stab.advice_two": "With two candidates, take both: {genes}",
        "stab.advice_all": "V does not fall below 0.15: take all {n} candidates: {genes}",
        "stab.best_pair": "Best NormFinder pair: {a} and {b} (ρ = {rho:.3f})",
        "ui.set.genorm_m_max": "geNorm M of references, max",
        "ui.set.genorm_m_max_tip": "Hellemans et al. 2007: 0.5 for homogeneous samples (cell lines), 1.0 for heterogeneous ones (tissues)",
    }
)
EN.update(
    {
        "sheet.stability": "Stability",
        "stab.note.few_candidates": "At least two candidates are needed",
        "stab.note.few_candidates_normfinder": "NormFinder needs at least three candidates",
        "stab.note.few_samples": "At least three samples with a Cq of every candidate are needed",
        "stab.note.no_groups": "No groups or too small ones: NormFinder took only the spread within a group",
        "stab.note.small_groups": "Groups of one sample are left out of NormFinder",
        "stab.note.ungrouped_samples": "Samples without a group are left out of NormFinder",
        "stab.note.v_never_below": "V never falls below 0.15: take all candidates",
    }
)
EN.update(
    {
        "qc.reference_unstable": "The reference gene is not stable in this experiment: M = {m:.2f}, limit {limit:.2f}",
        "qc.single_reference": "One reference gene: MIQE recommends at least two, so that their stability can be checked",
        "qc.stability_samples_excluded": "Samples without a Cq of a reference candidate: {count}. They are left out of the stability ranking",
    }
)
EN.update({"act.rename_target": "Rename a target on this plate…", "ui.rename_from": "Target on this plate:", "ui.rename_to": "New name:"})
EN.update({"ui.bad_quantity": "The quantity must be a positive number"})
EN.update(
    {
        "ui.col.cq_calc": "Cq from curve",
        "ui.col.tm": "Tm",
        "ui.save_figure": "Save figure…",
        "ui.filter_figure": "Figures (*.svg *.png *.pdf)",
        "ui.excluded_on_curve": "excluded on the standard curve",
        "ui.excluded_note": "Replicate {coord} ({target}) excluded. Undo: Ctrl+Z",
    }
)
EN.update(
    {
        "ui.cq_source": "Cq source",
        "ui.cq_source.instrument": "Instrument Cq",
        "ui.cq_source.calculated": "Cq from curves",
        "ui.eff.curves": "from amplification curves",
        "ui.eff.from_curves": "from curves: {eff:.0%}",
        "ui.set.nrt_min_delta": "No-RT control: cycles from the sample",
        "ui.set.tm_shift_max": "Tm shift from the median, °C",
        "ui.set.early_cq": "Early Cq, below",
        "ui.set.cq_disagree_max": "Disagreement with instrument Cq, cycles",
    }
)
EN.update(
    {
        "start.title": "Drop instrument files here",
        "start.note": "Several files or a folder: CFX, QuantStudio, Rotor-Gene, RDML, CSV",
        "ui.role_keep": "Role: unchanged",
        "start.add": "Choose files…",
        "start.open": "Open project…",
        "start.demo": "Demo data",
    }
)
EN.update(
    {
        "ui.curves.auto": "Auto",
        "ui.curves.auto_tip": "Reset the manual threshold",
    }
)
EN.update(
    {
        "ui.curves.amp": "Amplification",
        "ui.curves.log": "Amplification, log",
        "ui.curves.melt": "Melt",
        "ui.curves.all": "All targets",
        "ui.curves.none": "This run has no such curves",
        "ui.curves.cycle": "Cycle",
        "ui.curves.signal": "Signal, background removed",
        "ui.curves.temperature": "Temperature, °C",
        "ui.curves.dfdt": "-dF/dT",
    }
)
EN.update(
    {
        "ui.select_wells": "Select wells on the plate",
        "ui.mixed": "several values",
    }
)
EN.update(
    {
        "ui.analysis_settings": "Analysis settings",
        "ui.qc_count": "Errors: {errors}, warnings: {warnings}",
        "ui.chip.reference": "Reference: {value}",
        "ui.chip.control": "Control: {value}",
        "ui.chip.not_set": "not set",
        "ui.chip.no_targets": "No targets yet",
        "ui.chip.no_groups": "Set sample groups first",
    }
)
EN.update(
    {
        "hint.no_target": "{count} wells have no target. Select them and set the target",
        "hint.no_sample": "{count} wells have no sample. Select them and set the sample",
        "hint.no_reference": "Choose a reference gene",
        "hint.no_groups": "{count} samples have no group. Set the groups",
        "hint.no_control": "Choose the control group",
    }
)
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
        "ui.role.unknown": "sample", "ui.role.ntc": "NTC", "ui.role.nrt": "no-RT control", "ui.role.std": "standard", "ui.role.irc": "calibrator (IRC)",
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
        "ui.efficiency": "Efficiency", "ui.eff.stdcurve": "from standards", "ui.eff.manual": "manual", "ui.eff.ideal": "100 %",
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

EN.update(
    {
        "menu.file": "File", "menu.edit": "Edit", "menu.view": "View", "menu.help": "Help",
        "act.new": "New project", "act.open": "Open…", "act.recent": "Recent", "act.save": "Save",
        "act.save_as": "Save as…", "act.add_run": "Add run…", "act.import_layout": "Import layout…",
        "act.export_xlsx": "Export to Excel…", "act.export_csv": "Export to CSV…", "act.export_html": "HTML report…",
        "act.export_figures": "Figures (SVG)…", "act.exit": "Exit", "act.undo": "Undo", "act.redo": "Redo",
        "act.theme_auto": "Theme as in system", "act.theme_light": "Light theme", "act.theme_dark": "Dark theme", "act.lang_ru": "Русский", "act.lang_en": "English", "act.about": "About",
        "tab.plate": "Plate", "tab.data": "Data", "tab.std": "Standards", "tab.expr": "Expression", "tab.qc": "QC",
        "ui.untitled": "untitled",
        "ui.analysis_failed": "Analysis failed: {error}",
        "ui.status": "Runs: {runs} · errors: {errors} · warnings: {warnings}",
        "ui.unsaved_title": "Unsaved changes", "ui.unsaved_text": "Save changes to the project?",
        "ui.color_by": "Colour:", "ui.color.target": "by target", "ui.color.role": "by role",
        "ui.selection": "Selected: {n}", "ui.apply": "Apply", "ui.exclude": "Exclude", "ui.include": "Include",
        "ui.imported": "Imported {imported} of {total}; skipped {skipped}",
        "ui.about_text": "qpcrkit {version}\nqPCR data analysis. MIT licence.",
        "ui.filter_project": "qpcrkit project (*.qpcrkit.json)",
        "ui.filter_tables": "Instrument export (*.csv *.txt *.xlsx *.rdml)",
        "ui.unsupported_file": "This instrument project file cannot be read: {name}. Export RDML or CSV tables from the instrument software.",
        "ui.filter_layout": "Plate layout (*.platekit.json *.csv *.txt)",
        "ui.export_failed": "Could not save the file: {error}",
        "ui.import_failed": "Could not read the file: {error}",
        "ui.crash_text": "Unexpected error: {error}\nYou can save the project and keep working. Please send the report to the developer.",
        "ui.copy_report": "Copy report",
        "ui.btn.save": "Save", "ui.btn.discard": "Don't save", "ui.btn.cancel": "Cancel",
        "ui.series": "Series…", "ui.series_prefix": "Sample name start", "ui.series_replicates": "Replicates per sample",
        "ui.group_needs_sample": "Groups belong to samples: name the samples of these wells first",
        "ui.map_pasted": "Wells filled from the plate map: {n}",
        "ui.suggest_text": "The file names reference genes: {refs}; calibrator sample: {calibrator}. Use them?",
        "act.paste_map": "Paste plate map",
        "cli.file_error": "Could not process the file: {error}",
        "cli.bad_choice": "No such value: {name}. Available: {options}",
        "ui.no_run": "No runs yet: add an instrument export (File → Add run)",
    }
)

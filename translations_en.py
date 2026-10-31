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
    "sheet.raw": "Raw data",
    "sheet.qc": "QC",
    "sheet.std": "Standard curves",
    "sheet.abs": "Absolute quantification",
    "sheet.rel": "Relative expression",
    "sheet.stats": "Statistics",
    "sheet.params": "Analysis parameters",
}

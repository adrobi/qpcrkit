# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.2.0] — 2026-11-07

### Added
- Stability of reference genes: geNorm M with stepwise exclusion and pairwise variation V, NormFinder ρ with sample groups and the best pair of genes. Checked against NormqPCR and ctrlGene on their published data sets.
- A Stability page: candidate genes with check boxes, the advice on how many references to take and which, a button that makes them the references; geNorm and NormFinder figures.
- QC: a warning when a chosen reference is not stable in the experiment (geNorm M above a limit set in the analysis settings), a note for a single reference, a note for samples left out of the ranking.
- A Stability sheet in the workbook, a section in the HTML report, the stability figures in exported figures and `qpcrkit analyze --figures`.
- A warning when a well has two reactions with the same target and dye; only the first is used.

### Changed
- When the analysis fails, the result pages say so instead of showing the previous results.

### Fixed
- A target name starting with "_" no longer disappears from the legend of curve figures.
- The curve graph keeps its saved picture when its size does not change.

## [1.1.0] — 2026-11-07

### Added
- A new workspace: navigation with the runs on the left, reference and control chips on top, a hint line that says what is missing next, a start screen with drag and drop and a demo project.
- Curve analysis: baseline, Cq at a common threshold, per-well efficiency in a window of linearity, melt peaks and Tm, compared with instrument results on real files. The instrument's Cq stays the default; Cq and efficiency from curves are an explicit choice.
- The curve graph beside the plate and linked with it, a threshold line that can be dragged, per-run manual thresholds with an Auto button.
- New QC from curves: several melt peaks, Tm shift, a product or dimers in the NTC, disagreement with the instrument's Cq, very early Cq, Cq without amplification, mixed Cq sources, thresholds that differ without calibrators.
- Exclude a standard by clicking its point; save the expression figure from its page; curve columns in the data table, a Curves sheet in the workbook, curve figures in the HTML report and in the exported figures; `qpcrkit analyze --cq-source`.
- QuantStudio Design & Analysis workbooks; RDML 1.0 and 1.1; several CFX files or a whole folder as one run.
- Amplification and melt curves are imported and stored in the project.
- Assign targets to wells, rename a target on a plate, name samples in series, paste a plate map from a spreadsheet.
- No-RT control role (`nrt`) with its own check.
- Reference genes and calibrator named by the file are offered after import.

### Changed
- A calm theme with a teal accent and line icons; analysis settings moved to a dialog, reference and control to the top bar.
- Project files are smaller: curves of a run share one axis.
- The theme follows the system by default; light and dark can still be chosen.
- Wells without a sample are no longer treated as replicates of each other.

### Fixed
- Checked boxes show a tick; lists and spin boxes show their arrows.
- Numbers are read by column: `1,250.000` and `100,000,000` no longer lose standard quantities, and a Russian dilution series keeps its decimals.
- Binary instrument files give a clear message.
- QC messages show the thresholds from the settings.
- Command line: a missing file, a locked xlsx or an unknown `--ref`/`--control` give a message instead of a traceback.
- Target names cannot break figure file names; the standards tab keeps the selected curve.
- A wrong quantity is refused instead of breaking the standard curve.

## [1.0.0] — 2026-11-01

### Added
- Headless core `qpcr_core`: import of Bio-Rad CFX, QuantStudio/7500,
  Rotor-Gene Q and any CSV with a column mapping; plate layouts from platekit.
- Replicate/NTC QC with outlier suggestions, inter-run calibration (IRC),
  standard curves with efficiency and absolute quantification.
- Relative expression (generalized Pfaffl; ΔΔCt at 100 % efficiency) with
  several reference genes; group statistics on log2 scale (Welch, ANOVA,
  Dunnett, Tukey, Benjamini–Hochberg).
- Figures (SVG/PDF/PNG), xlsx/CSV/HTML export, sessions `*.qpcrkit.json`.
- CLI `qpcrkit inspect | new | analyze` and demo data in `examples/`.
- Desktop application (`qpcrkit` / `qpcrkit gui`): project tree, plate view with
  selection and exclusion, editable data table with paste from Excel, standard
  curves, relative expression with statistics, QC list that jumps to the well,
  analysis settings, CSV import wizard with presets, undo/redo, automatic
  recalculation, light/dark theme, Russian/English, error dialog with a copyable
  report.
- Application icon; Qt's own dialog buttons follow the interface language.
- Windows and Linux builds published by GitHub Actions on a version tag.

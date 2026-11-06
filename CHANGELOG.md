# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- QuantStudio Design & Analysis workbooks; RDML 1.0 and 1.1; several CFX files or a whole folder as one run.
- Amplification and melt curves are imported and stored in the project.
- Assign targets to wells, rename a target on a plate, name samples in series, paste a plate map from a spreadsheet.
- No-RT control role (`nrt`) with its own check.
- Reference genes and calibrator named by the file are offered after import.

### Changed
- The theme follows the system by default; light and dark can still be chosen.
- Wells without a sample are no longer treated as replicates of each other.

### Fixed
- Checked boxes show a tick; lists and spin boxes show their arrows.
- Numbers are read by column: `1,250.000` and `100,000,000` no longer lose standard quantities, and a Russian dilution series keeps its decimals.
- Binary instrument files give a clear message.
- QC messages show the thresholds from the settings.
- Command line: a missing file, a locked xlsx or an unknown `--ref`/`--control` give a message instead of a traceback.
- Target names cannot break figure file names; the standards tab keeps the selected curve.

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

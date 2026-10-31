# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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

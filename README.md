# <img src="ui/icons/app/qpcrkit.png" width="48" align="center"> qpcrkit

English | [Русский](README.ru.md)

Open-source desktop tool for **qPCR data analysis**: import Cq tables from the
instrument, check replicates and controls, fit standard curves, calculate
relative expression (ΔΔCt / Pfaffl) with statistics, and export tables and
publication-ready figures. Offline, free, English/Russian interface — a
replacement for the ΔΔCt spreadsheet most labs keep in Excel.

Part of a small family of lab tools: [platekit](https://github.com/adrobi/platekit)
plans the plate, qpcrkit analyses the run, [ab1kit](https://github.com/adrobi/ab1kit)
handles Sanger reads.

![expression](docs/screenshots/expression.png)
![plate, dark theme](docs/screenshots/plate-dark.png)

## Features

**Import**
- Bio-Rad CFX Maestro, Applied Biosystems QuantStudio / 7500, Qiagen Rotor-Gene Q
  exports (CSV, TXT, XLSX), detected automatically.
- Any other table through a column-mapping wizard with reusable presets.
- Plate layouts from platekit (`.platekit.json` or its instrument layout CSVs).
- Several plates in one experiment, aligned with inter-run calibrators (IRC).

**Analysis**
- QC: technical replicate spread, suggested outliers (never removed silently),
  NTC contamination, late amplification; every issue links to its well.
- Standard curves: slope, R², efficiency, lowest detected standard, absolute
  quantification with extrapolation warnings.
- Relative expression with any number of reference genes (geometric mean) and
  per-target efficiency — from the curve, entered manually or 100 % (classic ΔΔCt).
- Statistics on the log2 scale: SD / SEM / 95 % CI, Welch t-test, one-way ANOVA
  with Dunnett or Tukey, Benjamini–Hochberg across targets.

**Results**
- Fold-change charts with replicate points and significance stars; standard
  curve plots. SVG / PDF / PNG 300 dpi.
- Excel workbook (raw data, QC, curves, quantities, expression, statistics and
  every analysis parameter for MIQE-style reporting), CSV, printable HTML report.
- Projects are plain JSON (`*.qpcrkit.json`): raw data, annotations and
  exclusions are stored, results are always recalculated.

**Desktop**
- Plate view with drag selection, data table with paste-from-Excel, undo/redo,
  automatic recalculation, light and dark themes.
- Command line for batch work: `qpcrkit inspect | new | analyze`.

## Download

Ready-made builds are on the [Releases](https://github.com/adrobi/qpcrkit/releases)
page: `qpcrkit-windows-x64.exe` (no installation needed) and
`qpcrkit-linux-x86_64.tar.gz`.

## Run from source

```bash
git clone https://github.com/adrobi/qpcrkit.git
cd qpcrkit
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
qpcrkit                       # opens the desktop application
```

Python 3.11–3.13. Dependencies: PySide6, numpy, scipy, matplotlib, openpyxl.

## Quick start

1. **File → Add run…** and choose the instrument export (try `examples/demo_run1.csv`
   and `examples/demo_run2.csv`).
2. Check sample groups on the **Data** tab (paste a *sample — group* table from
   Excel with Ctrl+V) or import the layout from platekit.
3. On the right, tick the reference gene(s) and choose the control group.
4. Look at **QC**, **Standards** and **Expression**; export with **File → Export**.

The same from the command line:

```bash
qpcrkit new examples/demo_run1.csv examples/demo_run2.csv --ref GAPDH --control Ctrl -o demo.qpcrkit.json
qpcrkit analyze demo.qpcrkit.json -o results.xlsx --html report.html --figures figures/
```

## How the numbers are calculated

- Calibrated Cq = Cq − CF(run); CF is the mean deviation of the run's IRCs from
  their mean over runs (qbase, Hellemans et al. 2007).
- RQ = (1+E<sub>target</sub>)<sup>ΔCq</sup> / geomean over references of
  (1+E<sub>ref</sub>)<sup>ΔCq</sup>, ΔCq = Cq(control) − Cq(sample) (Pfaffl 2001).
- Group statistics and tests use log2(RQ) of biological replicates.

## Development

```bash
pytest -q
```

Tests cover the calculations against reference values, every importer, the CLI
and the GUI (offscreen). Releases are built by GitHub Actions on a `v*` tag.

## License

MIT © Aleksey Drobin ([@adrobi](https://github.com/adrobi))

# LaTeX manuscript package

Deliverable for "13. LATEX VERSION" of the paper request. This is a complete, internally
consistent LaTeX conversion of `paper/02_manuscript.md`, ready to open in Overleaf.

## A. `main.tex`

The full manuscript: title, abstract, all 9 sections with subsections, equations (InstanceNorm
mechanism, FiLM modulation, the linear-mixture PFT architecture, and all 5 evaluation metrics),
4 tables (via `\input`), 10 figures (via `\includegraphics` — all now generated, see part D
below), captions, labels, and cross-references throughout (`\Cref`/`\ref` for
sections/tables/figures/equations, `\cite`/`\citep`/`\citet` for the bibliography). Verified
before delivery (see "Verification" below).

## B. Suggested project folder structure

```
paper/latex/
├── main.tex
├── references.bib
├── README.md                       <- this file
├── figures/                        <- all 10 files generated (see D); regenerate via
│                                       Code/build_paper_latex_figures.py
│   ├── study_overview.pdf
│   ├── prediction_examples.pdf
│   ├── baseline_comparison.pdf
│   ├── loyo_r2_distributions.pdf
│   ├── loyo_year_difficulty.pdf
│   ├── spatial_transfer.pdf
│   ├── predictor_importance.pdf
│   ├── adaptation_results.pdf
│   ├── pft_shuffle_control.pdf
│   └── leakage_diagnostic.pdf
└── tables/
    ├── tab_dataset.tex             <- Table 1 (dataset & setup)
    ├── tab_main_comparison.tex     <- Table 2 (zero-shot vs. 8 baselines)
    ├── tab_loyo.tex                <- Table 3 (LOYO-CV, 330 folds)
    └── tab_adaptation.tex          <- Table 4 (adaptation methods + PFT shuffle control)
```

Upload this entire `paper/latex/` directory to Overleaf as a project (or `git clone` the
containing repository and point Overleaf's GitHub sync at this subdirectory).

## C. `references.bib`

Two tiers, clearly marked in the file itself:
- **Verified**: `ansari2024chronos` and `ansari2025chronos2` are copied verbatim from the
  `amazon-science/chronos-forecasting` repository's own README (this repo's parent project) —
  no fields invented.
- **PEFT-method papers** (LoRA, DoRA, VeRA, IA3, BitFit, FiLM) and three literature-review
  citations found by the project's own PFT-v2 research log: arXiv IDs and venues are confirmed
  from the project's source reports; author lists/exact titles are supplied from general
  knowledge of these well-known papers and marked `VERIFY before submission` — confirm against
  the actual paper before using.
- **Placeholder stubs** (`lai_forecasting_TODO`, `aelstm_TODO`, `ts_forecasting_survey_TODO`,
  `tsfm_review_TODO`, `earth_system_fm_TODO`): no fabricated fields at all — these sections of
  the literature review were never performed in this project and must be researched before
  submission, not filled in from memory.

## D. Figures — generation status

All 10 figure files now exist under `figures/`, built by
[`Code/build_paper_latex_figures.py`](../../Code/build_paper_latex_figures.py) (run from the
repository's `Code/` directory; requires `matplotlib`, `pandas`, `scipy`, `Pillow`, `geopandas`
(for `study_overview.pdf`'s real CONUS state-boundary basemap, drawn from the Natural Earth
shapefiles already bundled with `cartopy` — no network access needed). Re-run that
script any time an underlying result CSV changes, to regenerate every figure from scratch.

| File | How it was built | New plotting, or reused? |
|---|---|---|
| `study_overview.pdf` | New schematic, redesigned from an earlier abstract draft (v1: a dashed-rectangle "illustrative" map, plain labeled boxes, flat grey list). v2 uses a real CONUS basemap (state polygons from the Natural Earth shapefiles bundled with `cartopy`, via `geopandas` — an actual map, not a placeholder), an illustrative seasonal-LAI curve driving the task-formulation panel, and a pill/numbered-badge pipeline for the experiment tree. No data plotted beyond the 5 study-pixel coordinates already in Table 1 — diagram only. | **New** |
| `prediction_examples.pdf` | 3-panel figure (one per core pixel), trimmed to Observed / Zero-shot Chronos-2 / AELSTM / RF, from `outputs/final_comparison/all_methods_vs_raw_obs.csv`. | **New** (built from existing CSV) |
| `baseline_comparison.pdf` | Rebuilt from the authoritative `outputs/fair_comparison_vs_raw_observations.csv` and `fair_comparison_rank_consistency.csv` — **not** the naive, smoothed-target `outputs/all_models_r2_bars.png` the project's own README warns against. | **New** (redesigned, per Deliverable G) |
| `loyo_r2_distributions.pdf` | Direct PNG→PDF repackage of `outputs/loyo_cv/comparison/loyo_r2_distributions.png`. | Reused |
| `loyo_year_difficulty.pdf` | Direct PNG→PDF repackage of `outputs/loyo_cv/comparison/loyo_year_difficulty_heatmap.png`. | Reused |
| `spatial_transfer.pdf` | Direct PNG→PDF repackage of `outputs/spatial_transfer/evergreen_to_evergreen_west/spatial_transfer_r2_drop_combined.png`. | Reused |
| `predictor_importance.pdf` | Direct PNG→PDF repackage of `outputs/predictor_ablation/comparison/predictor_importance_by_pixel.png`. | Reused |
| `adaptation_results.pdf` | Direct PNG→PDF repackage of `outputs/advanced_finetuning/r2_by_pixel_all_methods.png`. | Reused |
| `pft_shuffle_control.pdf` | New 2-panel figure (per-pixel ΔR² scatter vs. PFT entropy, and a 4-condition mean-R² bar chart) built from `outputs/pft_v2/per_pixel_final_comparison.csv` and `real_vs_shuffled_ttest.csv` — did not exist as a standalone plot anywhere in the project before. | **New** (built from existing CSVs) |
| `leakage_diagnostic.pdf` | Direct PNG→PDF repackage of `outputs/leakage_diagnostic_2012/evergreen/leakage_cross_project_r2_comparison.png`. | Reused |

"Reused" figures are exact repackages of already-existing, already-verified project figures (no
new data, no new claims) — the PNG raster is embedded in a PDF container so `\includegraphics`
resolves cleanly; they are not redrawn as vector graphics. "New" figures are built entirely from
already-saved, already-verified result CSVs — no new experiments were run to produce any of them.

## Verification performed before delivery

- Brace balance: 454 open / 454 close.
- Every `\begin{...}`/`\end{...}` environment pair matches (abstract, align×2, description,
  document, enumerate, equation×2, figure×8, itemize, subfigure×4).
- Every `\Cref`/`\ref` target has a corresponding `\label` (checked programmatically; zero
  missing).
- Every `\cite`/`\citep`/`\citet` key exists in `references.bib` (checked programmatically; zero
  missing) and every bib entry is cited at least once in the text.
- Every `\input{tables/...}` path resolves to an existing file.
- Every `\includegraphics` filename matches the naming scheme in this README's folder structure
  and the D table above — no orphaned or inconsistently-named figure references.
- No Markdown syntax (`**bold**`, `##` headers, `[text](url)` links) remains anywhere in
  `main.tex`.
- All four tables' numbers were cross-checked against the underlying result CSVs during the
  audit that produced `paper/02_manuscript.md` and `paper/03_tables.tex` (see
  `paper/04_figures_missing_verification.md`, Deliverable I) — this LaTeX version transcribes
  those same verified numbers, not new ones.

## What will NOT compile cleanly yet

All 10 figures now exist, so `main.tex` should compile end-to-end in Overleaf as-is. The one
remaining gap is bibliographic: `references.bib`'s five placeholder stubs (`lai_forecasting_TODO`,
`aelstm_TODO`, `ts_forecasting_survey_TODO`, `tsfm_review_TODO`, `earth_system_fm_TODO`) have no
real entry yet and will render as a "?" citation until a genuine literature search fills them in —
by design, since this project never performed that search and the request explicitly prohibits
inventing bibliographic details. The PEFT-method entries marked `VERIFY before submission` will
compile and render correctly as-is; that flag means "confirm the author list/title before
submitting," not "this will fail to compile."

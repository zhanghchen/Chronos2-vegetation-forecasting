# LaTeX manuscript package

Deliverable for "13. LATEX VERSION" of the paper request. This is a complete, internally
consistent LaTeX conversion of `paper/02_manuscript.md`, ready to open in Overleaf.

## A. `main.tex`

The full manuscript: title, abstract, all 9 sections with subsections, equations (InstanceNorm
mechanism, FiLM modulation, the linear-mixture PFT architecture, and all 5 evaluation metrics),
4 tables (via `\input`), 9 figure placeholders (via `\includegraphics`, all currently missing —
see part D below), captions, labels, and cross-references throughout (`\Cref`/`\ref` for
sections/tables/figures/equations, `\cite`/`\citep`/`\citet` for the bibliography). Verified
before delivery (see "Verification" below).

## B. Suggested project folder structure

```
paper/latex/
├── main.tex
├── references.bib
├── README.md                       <- this file
├── figures/                        <- EMPTY: all 10 files below must be generated (see D)
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

## D. Figures still needing generation or redesign

None of the 10 figure files exist yet. Status and source, per the project's own figure plan
(`paper/04_figures_missing_verification.md`, Deliverable G):

| File | Status |
|---|---|
| `study_overview.pdf` | **New figure, does not exist anywhere in the project.** Schematic only — no new data needed. |
| `prediction_examples.pdf` | Reuse + trim `outputs/final_comparison/<pixel>/all_methods_vs_raw_obs.png` (currently shows all 10 methods; trim to zero-shot + AELSTM + 1 baseline for a 3-panel main-text figure). |
| `baseline_comparison.pdf` | **Redesign required.** The existing `outputs/all_models_r2_bars.png` uses the naive, smoothed-target comparison the project's own README explicitly warns against — must be rebuilt from `outputs/fair_comparison_vs_raw_observations.csv`. |
| `loyo_r2_distributions.pdf` | Reuse `outputs/loyo_cv/comparison/loyo_r2_distributions.png` (convert/export to PDF). |
| `loyo_year_difficulty.pdf` | Reuse `outputs/loyo_cv/comparison/loyo_year_difficulty_heatmap.png`. |
| `spatial_transfer.pdf` | Reuse `outputs/spatial_transfer/evergreen_to_evergreen_west/spatial_transfer_r2_drop_combined.png`. |
| `predictor_importance.pdf` | Reuse `outputs/predictor_ablation/comparison/predictor_importance_by_pixel.png`. |
| `adaptation_results.pdf` | Reuse `outputs/advanced_finetuning/r2_by_pixel_all_methods.png`. |
| `pft_shuffle_control.pdf` | **New figure, does not exist as a standalone plot.** Build from `outputs/pft_v2/mixed_vs_pure_final.png`'s underlying data (`per_pixel_final_comparison.csv`) as a real-vs-shuffled per-pixel ΔR² scatter. |
| `leakage_diagnostic.pdf` | Reuse `outputs/leakage_diagnostic_2012/evergreen/leakage_cross_project_r2_comparison.png`. |

All "reuse" entries need only a format conversion (PNG → vector PDF ideally, or at minimum a
high-resolution PNG renamed/placed under `figures/`) — no new experiments. The two flagged
**bold** entries need new plotting work from already-existing CSVs, not new experiments either.

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

By design, per the request: `main.tex` will fail to find the 10 files under `figures/` until they
are generated (part D) and will show a "?" for every citation and an empty bibliography until
`references.bib`'s placeholder entries are filled in with a real literature search (part C). Every
other aspect of the document (structure, tables, equations, cross-references) is complete and
self-consistent now.

# LOYO-CV Robustness Update Deck

*Generated: 2026-09-23 · Updated: 2026-09-23 (added a transparent
performance-selected-subset comparison slide, slide 8) · Updated:
2026-09-24 (added slides 12-13: Prof. Wang's follow-up on whether LOYO-CV
R² actually captures inter-annual variability)*

14-slide follow-up deck for Prof. Wang, addressing the feedback that a
single test year (2022) is not sufficient evidence of robustness. Two
sections:

1. **Post-meeting supplement**: the CDS-vs-cloud ERA5 visual comparison
   (reused from the earlier deck, unmodified).
2. **Leave-One-Year-Out Cross-Validation (LOYO-CV)** for both prior
   experiments — the 70-pixel CONUS pool and the 68-pixel global
   (non-CONUS) pool — each re-evaluated across 11 independent held-out
   years (2012–2022), zero-shot Chronos-2 only.

No new Chronos-2 settings were introduced: this reuses the project's own
already-published LOYO-CV protocol (`Code/loyo_cv_chronos2.py`,
`reports/LOYO_CV_FINDINGS.md`) for the CONUS pool, run for the first time
on all 70 pixels (originally only the 3 core pixels), and replicates the
identical protocol (same fixed 12-year window, same 11 held-out years,
same metrics) for the global pool via a new script, since that pool lives
in a separate ERA5/MODIS pipeline.

## Files

- `LOYO_CV_Robustness_Update.pptx` — the deck (14 slides).
- `build_deck.py` — editable slide source. Re-run with
  `/home/deh25003/miniconda3/bin/python3 build_deck.py` to regenerate.
- `figures/` — all embedded figures, copied from their source locations
  (see below); nothing here is unique to this folder.

## Where the underlying LOYO-CV work lives (not in this folder)

- `Code/loyo_cv_chronos2.py` — the LOYO-CV runner, run unmodified with
  `--sites <70 CONUS pixel names> --modes zero_shot`. Resumable: already
  skipped the 3 core pixels' zero-shot folds, which were computed in the
  original 3-pixel LOYO-CV study.
- `experiments/global_era5_chronos/scripts/run_loyo_cv_global.py` — new
  script replicating the identical protocol for the global pool (reuses
  `run_era5_chronos.build_merged_df` for the full 2000-2022 merged
  LAI+ERA5 series per pixel, then applies the same fixed-12-year-window
  fold logic). Does NOT compute ACC (anomaly correlation vs. day-of-year
  climatology, which the CONUS runner does) — omitted since building a
  reliable climatology from MODIS's already-sparse, irregular record is a
  separate methodological question not addressed in this pass.
- `Code/build_loyo_cv_summary_all_pools.py` — aggregates both pools' raw
  per-fold CSVs into per-pixel summaries, the headline "average variance"
  statistic, and the comparison figures. Outputs to
  `outputs/loyo_cv_pools_summary/`.
- Raw results: `outputs/loyo_cv/<site>/fold_<year>_metrics.csv` (CONUS),
  `experiments/global_era5_chronos/outputs/loyo_cv/<pixel>/fold_<year>_metrics.csv`
  (global).

## The "average variance" statistic, precisely defined

For each pixel: compute R² for each of its 11 LOYO folds, then take the
**variance** of those 11 values (sample variance, `pandas .std()**2`).
"Average variance" = the mean of that per-pixel variance across all
pixels in the pool. Because variance is dominated by extreme values, this
number is heavily influenced by a handful of outlier pixels (e.g.
`evergreen`'s already-diagnosed 2012 drought fold, R²=−7.64 that year) —
the deck also reports the **median** variance (robust to outliers) so
both the "average pixel" and "worst-case tail" pictures are visible, per
this project's standing practice of not letting one aggregate number
hide the story.

| Pool | Folds | Mean R² | Average variance | Median variance |
|---|---|---|---|---|
| CONUS (70 pixels) | 770 | 0.749 | 0.170 | 0.005 |
| Global (68 pixels) | 748 | 0.348 | 0.106 | 0.030 |

## Slide 8: exploratory performance-selected subset (explicitly not the result)

Slide 8 answers a specific, narrower question — "how much does performance
improve in a best-case subset?" — with a transparently-labeled, explicitly
exploratory comparison: the full 68-pixel pool (the primary, reported
result throughout this project) side by side with the top 20 of those 68
pixels **ranked by their own mean LOYO-CV R²** (threshold: mean R² ≥
0.594). Because the subset is selected by the outcome metric itself, its
statistics (mean R²=0.690, median variance=0.016) are conditional on that
selection and are explicitly labeled on the slide as NOT representative of
the full pool's typical performance — the full-pool row (mean R²=0.348)
remains the number reported everywhere else in this project
(`ERA5_GLOBAL70_REPORT.md`, the rest of this deck, the GitHub-committed
raw results). Built by `Code/build_global_top20_subgroup.py`.

## Slides 12-13: does LOYO-CV actually capture inter-annual variability?

Prof. Wang's follow-up: the per-fold R² reported above (and throughout the
original LOYO-CV study) is computed **across time within one held-out
year** — since both the actual and predicted LAI follow the same strong
8-day seasonal cycle, that R² mostly reflects "did the model get the
seasonal shape right," not "did it capture real year-to-year differences."
Her requested fix: fix the **calendar position** (e.g. the 1st 8-day
composite of the year) and compute R² **across the 11 held-out years** at
that position — this removes the shared seasonal cycle and isolates
genuine inter-annual variability.

Implementation (per pixel, matching her description exactly — not pooled
across pixels, which would conflate genuine temporal variance with
between-pixel spatial differences like forest vs. grassland baseline LAI):
for each of the ~46 composite positions in the year, and each pixel
separately, compute R² using only that pixel's own held-out-year values at
that position (pixels need ≥8 of the 11 years present), then average
across pixels to get one typical value per position.

**Result**: with only ≤11 points per pixel-position, R² itself is
unstable — a well-known small-sample failure mode where a single biased
point can drive R² arbitrarily negative — and its mean turns negative for
both pools (CONUS mean of per-position mean R²=-0.344, Global=-0.431).
Pearson r, bounded in [-1, 1] and far less sensitive to this failure mode,
gives a coherent, physically sensible answer instead: a modest positive
inter-annual correlation (CONUS r≈0.29, Global r≈0.18) that **declines
over the forecast horizon** — highest (r≈0.4-0.5) at early composite
positions (short lead time) and falling toward 0-0.2 by the far end of the
45-step horizon, consistent with forecast skill degrading over lead time
rather than a pool-specific issue. Slide 12 presents the R²-vs-Pearson-r
comparison table; slide 13 shows the full Pearson-r-by-composite-position
sequence plot for both pools.

Built by three new scripts (all purely additive — read the existing
LOYO-CV fold logic unmodified, write to new output directories, never
touch the original `outputs/loyo_cv/` fold-metric CSVs):

- `Code/loyo_cv_capture_predictions.py` — re-runs the same 770 CONUS LOYO
  folds as `Code/loyo_cv_chronos2.py` (reusing its fold-construction
  functions unmodified) but additionally saves per-timestep
  `(date, ground_truth, prediction, composite_index)` arrays, which the
  original script doesn't persist. Writes to
  `outputs/loyo_cv_predictions/<site>/fold_<year>_predictions.csv`.
- `experiments/global_era5_chronos/scripts/loyo_cv_capture_predictions_global.py`
  — the same, for the 748 global folds, reusing
  `run_loyo_cv_global.py`'s fold logic unmodified. Writes to
  `experiments/global_era5_chronos/outputs/loyo_cv_predictions/`.
- `Code/build_loyo_composite_position_r2.py` — computes both the primary
  per-pixel-then-averaged R²/Pearson-r-by-composite-position analysis and
  a secondary pooled-across-pixels reference (explicitly documented as
  conflating spatial and temporal variance, kept only for comparison).
  Outputs to `outputs/loyo_cv_pools_summary/` (`loyo_*_r2_by_position_per_pixel*.csv`,
  `loyo_r2_by_position_per_pixel_summary.csv`, and the sequence-plot
  figures used on slides 12-13).

## Known simplifications (disclosed)

- The global pool's LOYO-CV does not compute ACC (anomaly correlation
  coefficient), unlike the CONUS runner — see above.
- A handful of global-pool folds have quite short context (as low as
  the pool's usual MODIS-gap-driven range) — `n_context` is saved per
  fold in the raw CSVs for anyone who wants to filter further.

# LOYO-CV Robustness Update Deck

*Generated: 2026-09-23*

11-slide follow-up deck for Prof. Wang, addressing the feedback that a
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

- `LOYO_CV_Robustness_Update.pptx` — the deck (11 slides).
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

## Known simplifications (disclosed)

- The global pool's LOYO-CV does not compute ACC (anomaly correlation
  coefficient), unlike the CONUS runner — see above.
- A handful of global-pool folds have quite short context (as low as
  the pool's usual MODIS-gap-driven range) — `n_context` is saved per
  fold in the raw CSVs for anyone who wants to filter further.

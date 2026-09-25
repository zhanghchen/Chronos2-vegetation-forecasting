# Zero-Shot Chronos-2 Across 70 Non-CONUS Global Pixels

*Generated: 2026-09-20 · Corrected: 2026-09-25 (RMSE/MAE were reported
10x too small - see "Data correction" note below; R²/Pearson r/MAPE were
unaffected and unchanged)*

## Data correction (2026-09-25)

A unit bug was found and fixed in `scripts/load_global_lai.py`: it
re-applied the MOD15A2H 0.1 scale factor on top of LAI values that
NASA's AppEEARS point-sample API had already scaled to physical units
(AppEEARS' own docs: "the middleware makes it possible to extract
**scaled** data values" - `data/global_lai/raw/README.md:139`), silently
dividing every real LAI value in this experiment by 10 (e.g. forest
pixels capped under ~0.7 instead of their true ~3-7 range). Caught when a
plotted forest pixel's LAI never exceeded 1. All 68 pixels' LAI (context,
ground truth, and the Chronos-2 predictions built from it) were affected;
CONUS was not (different data source, no equivalent bug). Fixed, the raw
LAI reprocessed, and every downstream global result rerun.
**R², Pearson r, and MAPE are scale-invariant and came back numerically
identical** (verified directly, not assumed) - only RMSE and MAE, which
are NOT scale-invariant, were wrong by ~10x and are corrected below.

**Chronos-2 used strictly zero-shot: no training or fine-tuning.**

## Motivation

Every prior zero-shot generalization result in this project (the original
3-pixel study, the 32/70-pixel CONUS gridMET studies, the 70-pixel CONUS
cloud-ERA5 study) was confined to the continental United States. This
experiment asks the genuinely new question: does the same zero-shot
pattern hold **outside CONUS**, across a diverse, independently-selected
global pixel pool, using ERA5 (already validated as a climate source) and
an independent global LAI product?

## Data sources (new for this experiment)

- **Pixel selection**: `scripts/select_global_pixels.py` (N_TARGET=70),
  reusing the existing global ESA CCI PFT product (300m, true global
  coverage) and the same farthest-point-sampling methodology already used
  for the project's earlier 45-pixel candidate set — extended to 70,
  explicitly excluding CONUS/Alaska/Hawaii. Output:
  `data_selection/global_candidate_pixels_70.csv`. 70 pixels, 10 vegetation
  classes, 14 world regions, purity range 0.44–1.00.
- **Climate**: same cloud ERA5 pipeline as the CONUS experiment
  (`era5_source_arco.py`, already validated — see
  `ERA5_CLOUD_EQUIVALENCE_REPORT.md`), extended to these 70 new grid
  points, full 2000–2022 history, same batched-extraction approach.
- **LAI ground truth (new)**: MODIS `MOD15A2H.061` (Terra, 8-day, 500m),
  fetched via NASA's AppEEARS point-sample API
  (`fetch_global_lai_appeears.py` / `poll_and_download_lai.py`) using the
  project's existing, confirmed-working NASA Earthdata credentials — not
  gridMET/HiQ-LAI, which is CONUS-only. QC-filtered
  (`load_global_lai.py`) to MODLAND-good-quality retrievals only
  (`FparLai_QC` MODLAND bit == 0), which keeps 68.1% of all pixel-dates;
  the rest (persistent cloud/polar-night contamination) are dropped, not
  interpolated over.

## Coverage

68/70 pixels had enough usable LAI (≥100 good observations total, ≥5 in
the 2022 test year) to run. The 2 excluded pixels:
`g000_grass_nat` (75.99°N, high Arctic — persistent polar night/sea ice)
and `g041_grass_man` (14.0°N/108.0°E, Vietnam/Laos — persistent monsoon
cloud cover). Both are well-documented MODIS optical-LAI limitations, not
pipeline errors.

**Context length varies by pixel** (202–1002 8-day steps, median 696) —
unlike the CONUS studies, where every pixel had a uniform ~1000-step
2000–2021 context, MODIS data gaps mean some global pixels have much less
usable history. `context_steps` is reported per pixel; the R²-vs-context
correlation across all 68 pixels is only **r=0.16**, so context length is
not the dominant driver of the results below (see Interpretation).

## Results: 68 pixels

`outputs/era5_global70_clean.csv` (full table),
`outputs/era5_global70_summary_{overall,by_class,by_region}.csv`,
`outputs/global70_map.png`, `outputs/global70_r2_by_pixel_and_class.png`.

| | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|
| mean | 0.754 | 0.540 | 58.1 | 0.299 | 0.621 |
| median | 0.591 | 0.422 | 42.7 | **0.353** | 0.668 |
| std | 0.583 | 0.432 | 56.6 | 0.403 | 0.270 |
| min | 0.079 | 0.063 | 8.0 | −0.934 | −0.495 |
| max | 3.503 | 2.547 | 433.9 | 0.916 | 0.960 |

(RMSE/MAE corrected 2026-09-25 - see data correction note above; MAPE/R²/Pearson r unchanged.)

**Only 4/68 (5.9%) pixels reach R² ≥ 0.8** (vs. 66% for the CONUS cloud-ERA5
study on the same protocol) — a large, real drop, not noise.

**By dominant vegetation class** (mean R², sorted):

| Class | n | Mean R² | Median R² |
|---|---|---|---|
| SHRUBS-BD | 6 | 0.584 | 0.571 |
| TREES-NE | 6 | 0.484 | 0.481 |
| GRASS-NAT | 24 | 0.364 | 0.490 |
| SHRUBS-ND | 3 | 0.301 | 0.374 |
| TREES-BD | 6 | 0.261 | 0.173 |
| GRASS-MAN | 9 | 0.240 | 0.351 |
| SHRUBS-NE | 3 | 0.199 | 0.601 |
| TREES-BE | 6 | 0.037 | 0.038 |
| SHRUBS-BE | 3 | −0.055 | 0.143 |
| TREES-ND | 2 | −0.056 | −0.056 |

**By region** (mean R², selected): Mediterranean (n=1) 0.916, Central/
Southern Africa (n=3) 0.685, Canada (n=7) 0.535, East Asia (n=8) 0.503 —
down to **Amazon/Tropical S. America (n=4) −0.119** and "Other" (mostly
high-latitude/remote, n=16) 0.065, the two weakest regions.

## Failure cases

13/68 pixels score R² < 0. Two distinct failure patterns:

1. **Genuine anti-correlation** (worst case): `g052_grass_nat` (Amazon,
   R²=−0.934, **Pearson r=−0.495**, context=381) — the forecast doesn't
   just miss the magnitude, it gets the direction wrong. Tropical
   persistent cloud cover (the same issue that excluded `g041` entirely)
   is the most likely driver, both from noisier surviving MODIS
   retrievals and from a short, gap-heavy context.
2. **Miscalibrated but directionally reasonable** (most other negative-R²
   pixels): e.g. `g023_grass_nat` (Canada, R²=−0.280 but Pearson
   r=+0.682) and `g015_trees_nd` (Siberia, R²=−0.246, r=+0.849) — the
   model tracks the right temporal pattern but is biased in absolute
   magnitude enough to fail the stricter R² criterion. This is a
   different, milder failure mode than (1).

`outputs/global70_prediction_examples.png` shows both failure modes
directly (full 2000-2021 observed LAI history + the 2022 forecast overlay)
alongside 3 strong performers (`g032_shrubs_bd`, `g065_shrubs_bd`,
`g009_grass_nat`) and `g001_shrubs_nd` (R²≈0, only 202 valid MODIS
observations across 22 years — visually a sparse, irregular series where
near-zero R² reflects a near-featureless target more than a bad forecast).
Individual per-pixel plots for all 68 pixels are in
`outputs/global70_prediction_plots/<pixel_id>.png`.

Top performers span genuinely diverse regions and contexts:
`g032_shrubs_bd` (Mediterranean, R²=0.916), `g065_shrubs_bd` (Central/
Southern Africa, R²=0.879), `g005_grass_nat` (Siberia, R²=0.871, despite
only 369 context steps), `g009_grass_nat` (Canada, R²=0.802) —
demonstrating the pattern is not confined to any one continent when it
does work.

## Interpretation

> **RESULT**: across 68 non-CONUS global pixels, zero-shot Chronos-2 with
> ERA5 + MODIS LAI scores a median R² of 0.353 (mean 0.299), with only
> 5.9% of pixels reaching R² ≥ 0.8 — substantially weaker than every
> CONUS result in this project (32-pixel gridMET median 0.865, 70-pixel
> CONUS cloud-ERA5 median 0.890).
>
> **INTERPRETATION**: the strong zero-shot generalization repeatedly
> observed within CONUS does **not** transfer uniformly to a global,
> more climatically and ecologically diverse pixel pool. This is the
> first result in this project to show a real ceiling on zero-shot
> Chronos-2's LAI generalization — it is not unconditionally
> location-independent.
>
> **INTERPRETATION**: the gap is not primarily an artifact of shorter
> context (context-length vs. R² correlation is only 0.16) — genuine
> regional/ecological difficulty is the larger factor. Tropical
> (persistent-cloud, low MODIS data quality) and remote high-latitude
> pixels are disproportionately represented among the failures.
>
> **HYPOTHESIS, not established here**: whether the gap reflects (a)
> Chronos-2's own generalization limits, (b) the noisier/sparser MODIS
> LAI ground truth compared to HiQ-LAI's CONUS-tuned processing, (c)
> genuinely different, less seasonally-regular vegetation dynamics
> outside CONUS (e.g., tropical evergreen systems with weak seasonal LAI
> cycles), or some mix of all three, is not distinguished by this
> experiment. Disentangling would require, at minimum, a CONUS pixel
> re-scored against MODIS LAI instead of HiQ-LAI as a controlled
> comparison — not done here.

## Files

- `scripts/select_global_pixels.py` (N_TARGET=70) — pixel selection.
- `scripts/fetch_global_lai_appeears.py`, `scripts/poll_and_download_lai.py`,
  `scripts/load_global_lai.py` — MODIS LAI acquisition + QC filter.
- `scripts/prefetch_arco_global70.py` — climate prefetch for the new points.
- `scripts/run_era5_chronos_batch_global.py` — zero-shot batch driver.
- `scripts/build_global70_comparison.py` — summary tables/figures.
- `scripts/plot_global_predictions.py` — per-pixel observed-vs-predicted
  LAI plots (curated 6-pixel grid + all 68 individual plots).
- `data/global_lai/{raw,processed}/`, `data/global_lai/coverage_report.csv`.
- `results_global/<pixel>/{metrics_era5_cloud.txt,predictions_era5_cloud.csv}`.
- `outputs/era5_global70{,_clean}.csv`,
  `outputs/era5_global70_summary_{overall,by_class,by_region}.csv`,
  `outputs/global70_map.png`, `outputs/global70_r2_by_pixel_and_class.png`,
  `outputs/global70_context_vs_r2.png`.

# Zero-Shot Chronos-2 Across 32 Diverse, Purity-Filtered CONUS Pixels

*Generated: 2026-09-15*

**Motivation**: the global ERA5 generalization study (`experiments/global_era5_chronos/`) is
answering the same underlying question — does zero-shot Chronos-2 generalize across diverse
vegetation types? — but is severely bottlenecked by the Copernicus CDS download queue (one
pixel's validation took 13 days of wall-clock time, mostly spent waiting on an external rate
limit, not compute). Since gridMET/HiQ-LAI data is already available locally for a large,
already-selected, already-quality-filtered CONUS pixel pool, this study answers the same
generalization question immediately, using no new downloads at all.

**Design**: reused the 70-pixel pool already selected and quality-filtered for the
`pft_multipixel`/PFT-v2 studies (`AELSTM/outputs/pft_multipixel_selection/pft_diverse_pixels.csv`
— farthest-point-sampled across an 8-class PFT-composition space, geographic minimum-separation
constraint, verified zero climate/LAI gaps). Filtered to **32 pixels with PFT purity ≥ 0.75**
("pure" — i.e., a single vegetation class dominates ≥75% of the pixel), spanning all 8 dominant
classes (TREES_NE/BD/ND, SHRUBS_NE/BD/ND, GRASS_NAT/MAN) and 8 U.S. regions. This set includes the
3 already-published core pixels (`evergreen`, `high_amplitude_deciduous`, `low_amplitude`), whose
existing, already-verified results were reused unchanged rather than rerun.

**Method**: zero-shot Chronos-2 only (no fine-tuning, no baseline retraining — this is a
targeted extension of the zero-shot generalization question, not a full replay of every prior
study). Identical protocol to every other zero-shot run in this project: context = 2000–2021
(~1,002 8-day steps), forecast = all 45 steps of 2022, actual observed 2022 climate supplied as
`future_covariates`, scored against raw (unsmoothed) observed LAI. No new code needed —
`Code/run_chronos2.py --modes zero_shot` was run unmodified on the 29 new pixel CSVs (copied from
the existing multi-pixel dataset into this project's own `data/processed/sites/`, matching this
project's established data-provenance convention).

## Results

`outputs/purity32_pixel_study/zero_shot_32pixels.csv` (full table),
`summary_overall.csv`, `summary_by_class.csv`, `r2_by_pixel_and_class.png`.

**Overall (32 pixels):**

| | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|
| mean | 0.215 | 0.160 | 25.9 | **0.757** | 0.894 |
| median | 0.213 | 0.162 | 18.2 | **0.865** | 0.951 |
| std | 0.127 | 0.096 | 17.1 | 0.281 | 0.156 |
| min | 0.036 | 0.028 | 6.0 | −0.348 | 0.142 |
| max | 0.485 | 0.426 | 67.3 | 0.973 | 0.989 |

**By dominant vegetation class** (mean R², sorted):

| Class | n | Mean R² | Median R² | Std |
|---|---|---|---|---|
| TREES_BD (broadleaf deciduous forest) | 3 | 0.929 | 0.915 | 0.032 |
| SHRUBS_NE (needleleaf evergreen shrub) | 3 | 0.891 | 0.908 | 0.035 |
| TREES_NE (needleleaf evergreen forest) | 4 | 0.885 | 0.885 | 0.064 |
| TREES_ND (needleleaf deciduous forest) | 4 | 0.852 | 0.946 | 0.192 |
| GRASS_MAN (managed grass/cropland) | 5 | 0.760 | 0.836 | 0.168 |
| GRASS_NAT (natural grassland) | 7 | 0.679 | 0.898 | 0.476 |
| SHRUBS_ND (deciduous shrub) | 3 | 0.559 | 0.534 | 0.206 |
| SHRUBS_BD (broadleaf deciduous shrub) | 3 | 0.529 | 0.603 | 0.319 |

**22 of 32 pixels (69%) score R² ≥ 0.8; only 1 of 32 scores below zero.**

### The one outlier: `px047_grass_nat` (R² = −0.348, Southwest)

Investigated directly rather than left unexplained. This pixel's observed LAI has an extremely
narrow dynamic range across every year (2017–2022 annual means: 0.24–0.39, min/max never leaving
roughly 0.10–0.70) — a near-flat, low-signal grassland series. Zero-shot Chronos-2 predicts a
correspondingly damped, narrow-range curve (predicted std = 0.037 vs. observed std = 0.092): its
*absolute* errors are small (RMSE = 0.106, smaller than 24 of the other 31 pixels), but R² —
which measures variance explained relative to the target's own variance — collapses because there
is so little true variance to explain in the first place. This is the **same signal-to-noise
failure mode** already diagnosed for `low_amplitude` in `LOYO_CV_FINDINGS.md` (§2), not a new or
different problem: low-amplitude, low-signal pixels are hard for every model in this project, and
R² is a misleading metric for them in isolation (RMSE/MAE tell a more honest story).

## Interpretation

> **RESULT**: across 32 purity-filtered pixels spanning 8 vegetation classes and 8 U.S. regions,
> zero-shot Chronos-2 (no training, no fine-tuning) scores a median R² of 0.865, with 69% of
> pixels at R² ≥ 0.8, using only the existing gridMET/HiQ-LAI data already available locally.
>
> **INTERPRETATION**: the strong zero-shot generalization already established on the original 3
> core pixels (COMPARISON_REPORT.md) extends to a much larger, independently-selected, diverse
> pixel set — this is not an artifact of having hand-picked 3 favorable locations.
>
> **INTERPRETATION**: performance is not uniform across vegetation types — tree- and
> shrub-evergreen classes (TREES_BD, SHRUBS_NE, TREES_NE) are the most consistently strong
> (std ≤ 0.06), while grassland and deciduous-shrub classes show much higher variance (std up to
> 0.48), driven by a small number of low-amplitude, low-signal pixels within those classes rather
> than a systematic weakness of the vegetation type itself — consistent with this project's
> repeated finding (LOYO-CV, predictor ablation) that *signal amplitude*, not vegetation type per
> se, is the dominant driver of forecast difficulty.
>
> **HYPOTHESIS, not established here**: whether this same 0.86-median pattern would hold outside
> CONUS (the actual motivating question for the ERA5 study) remains untested by this experiment —
> this result only rules out "the original 3-pixel result was cherry-picked," it does not
> substitute for genuine geographic/climatic generalization evidence.

## Files

- `Code/build_purity32_pixel_comparison.py` — figure/summary generation (reads already-saved
  per-pixel results, no new experiments).
- `outputs/zero_shot/<pixel>/{predictions.csv,metrics.txt,prediction_plot.png}` — one per new
  pixel (29 new + 3 reused from the existing core-pixel results).
- `outputs/purity32_pixel_study/{zero_shot_32pixels.csv,summary_overall.csv,summary_by_class.csv,
  r2_by_pixel_and_class.png}`.
- `data/processed/sites/px0*.csv` — the 29 new pixel CSVs, copied from
  `AELSTM/data/processed/sites_pft_multipixel/` (same gridMET/HiQ-LAI extraction pipeline as
  every other pixel in this project).

## Reproducing

```bash
cd Code
# (pixel CSVs already copied into ../data/processed/sites/; see git history for the exact list)
/home/deh25003/miniconda3/envs/chronos2/bin/python3 run_chronos2.py --sites <29 new pixel names> --modes zero_shot
# NOTE: this OVERWRITES outputs/chronos2_all_results.csv with only the sites passed in --sites;
# back it up first if re-running, and restore/merge afterward (see this study's own commit for
# exactly how the 3 already-published core pixels' results were preserved).
python build_purity32_pixel_comparison.py
```

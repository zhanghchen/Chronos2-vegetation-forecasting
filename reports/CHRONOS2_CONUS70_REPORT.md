# Zero-Shot Chronos-2 Across All 70 Diverse CONUS Pixels

*Generated: 2026-09-15* · *Updated: 2026-09-15 (extended from an initial 32-pixel, purity≥0.75
subset to the full 70-pixel pool)*

**Motivation**: the global ERA5 generalization study (`experiments/global_era5_chronos/`) is
answering the same underlying question — does zero-shot Chronos-2 generalize across diverse
vegetation types? — but is severely bottlenecked by the Copernicus CDS download queue (one
pixel's validation took 13 days of wall-clock time, mostly spent waiting on an external rate
limit, not compute). Since gridMET/HiQ-LAI data is already available locally for a large,
already-selected, already-quality-filtered CONUS pixel pool, this study answers the same
generalization question immediately, using no new downloads at all.

**Design**: reused the full 70-pixel pool already selected and quality-filtered for the
`pft_multipixel`/PFT-v2 studies (`AELSTM/outputs/pft_multipixel_selection/pft_diverse_pixels.csv`
— farthest-point-sampled across an 8-class PFT-composition space, geographic minimum-separation
constraint, verified zero climate/LAI gaps), spanning all 8 dominant vegetation classes
(TREES_NE/BD/ND, SHRUBS_NE/BD/ND, GRASS_NAT/MAN), PFT purity 0.46–1.00, and 9 U.S. regions. Of the
70, **4 pixels already had established, already-published results** and were reused unchanged
rather than rerun: the 3 core pixels (`evergreen`, `high_amplitude_deciduous`, `low_amplitude`,
from `outputs/fair_comparison_vs_raw_observations.csv`) and `mixed_forest_grass` (from the PFT
ablation study's zero-shot baseline, `outputs/pft_ablation/mixed_forest_grass/baseline/metrics.txt`
— its own copy of this pixel's CSV predates and differs slightly from the multi-pixel dataset's
copy, so the already-published number was kept rather than silently changed). The remaining **66
pixels were run fresh** in two batches (an initial 29-pixel, purity≥0.75 "pure" subset, then the
remaining 37 to complete the full pool).

**Method**: zero-shot Chronos-2 only (no fine-tuning, no baseline retraining — this is a
targeted extension of the zero-shot generalization question, not a full replay of every prior
study). Identical protocol to every other zero-shot run in this project: context = 2000–2021
(~1,002 8-day steps), forecast = all 45 steps of 2022, actual observed 2022 climate supplied as
`future_covariates`, scored against raw (unsmoothed) observed LAI. No new code needed —
`Code/run_chronos2.py --modes zero_shot` was run unmodified on each batch of new pixel CSVs
(copied from the existing multi-pixel dataset into this project's own `data/processed/sites/`,
matching this project's established data-provenance convention).

## Results: all 70 pixels

`outputs/purity32_pixel_study/zero_shot_70pixels.csv` (full table), `summary_overall_70pixels.csv`,
`summary_by_class_70pixels.csv`, `summary_by_region_70pixels.csv`, `r2_by_pixel_and_class_70.png`.

**Overall (70 pixels):**

| | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|
| mean | 0.205 | 0.151 | 39.6 | **0.765** | 0.903 |
| median | 0.180 | 0.139 | 21.3 | **0.904** | 0.956 |
| std | 0.121 | 0.088 | 103.2 | 0.303 | 0.132 |
| min | 0.036 | 0.028 | 6.0 | −0.724 | 0.142 |
| max | 0.620 | 0.467 | 877.2† | 0.987 | 0.994 |

† one pixel (`px069_trees_bd`) has an extreme MAPE despite R²=0.928 and Pearson r=0.967 — MAPE is
divided by observed LAI, and a handful of near-zero-LAI rows there inflate the percentage error
without reflecting a real forecasting problem; not investigated further since R²/RMSE/Pearson r
all agree the forecast is good.

**By dominant vegetation class** (mean R², sorted, all 70):

| Class | n | Mean R² | Median R² | Std |
|---|---|---|---|---|
| TREES_BD (broadleaf deciduous forest) | 7 | 0.938 | 0.933 | 0.024 |
| TREES_NE (needleleaf evergreen forest) | 6 | 0.905 | 0.920 | 0.064 |
| TREES_ND (needleleaf deciduous forest) | 6 | 0.879 | 0.946 | 0.155 |
| SHRUBS_NE (needleleaf evergreen shrub) | 7 | 0.857 | 0.875 | 0.057 |
| GRASS_MAN (managed grass/cropland) | 12 | 0.808 | 0.900 | 0.177 |
| GRASS_NAT (natural grassland) | 19 | 0.675 | 0.910 | 0.474 |
| SHRUBS_BD (broadleaf deciduous shrub) | 7 | 0.621 | 0.709 | 0.294 |
| SHRUBS_ND (deciduous shrub) | 6 | 0.576 | 0.560 | 0.230 |

**By region** (mean R², sorted, all 70):

| Region | n | Mean R² | Median R² |
|---|---|---|---|
| Midwest | 10 | 0.953 | 0.955 |
| Northeast | 4 | 0.946 | 0.943 |
| Northern Rockies / Great Basin | 4 | 0.920 | 0.918 |
| Pacific Northwest | 12 | 0.797 | 0.851 |
| California | 4 | 0.771 | 0.814 |
| Southeast | 6 | 0.738 | 0.834 |
| Great Plains | 21 | 0.708 | 0.898 |
| Other | 6 | 0.634 | 0.595 |
| Southwest | 3 | 0.280 | 0.297 |

**48 of 70 pixels (69%) score R² ≥ 0.8; only 2 of 70 score below zero — both `GRASS_NAT`.**

### The two negative-R² pixels: `px047_grass_nat` and `px045_grass_nat` (both Southwest/Other)

Investigated directly rather than left unexplained (consistent with this project's practice for
every prior outlier — LOYO-CV's `evergreen`/2012 and `low_amplitude`/2018, the PFT studies'
BitFit failure, etc.). `px047_grass_nat`'s observed LAI has an extremely narrow dynamic range
across every year (2017–2022 annual means: 0.24–0.39, min/max never leaving roughly 0.10–0.70) — a
near-flat, low-signal grassland series. Zero-shot Chronos-2 predicts a correspondingly damped,
narrow-range curve (predicted std = 0.037 vs. observed std = 0.092): its *absolute* errors are
small (RMSE = 0.106, better than half the other 69 pixels), but R² — which measures variance
explained relative to the target's own variance — collapses because there is so little true
variance to explain in the first place. `px045_grass_nat` (R² = −0.724, RMSE = 0.112, similarly
small in absolute terms) shows the same pattern. This is the **same signal-to-noise failure mode**
already diagnosed for `low_amplitude` in `LOYO_CV_FINDINGS.md` (§2), not a new or different
problem: low-amplitude, low-signal grassland pixels are hard for every model in this project, and
R² is a misleading metric for them in isolation — RMSE/MAE tell a more honest story, and both
remain small here.

## The 32-pixel "pure" subset (PFT purity ≥ 0.75), for reference

The full 70-pixel pool includes many genuinely mixed-composition pixels (purity as low as 0.46),
which is a harder and different question (can Chronos-2 forecast a pixel whose vegetation
composition is ambiguous?) than the original "does it generalize across clearly-one-type
pixels?" question. The 32-pixel subset with purity ≥ 0.75 isolates the latter:

| | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|
| mean | 0.215 | 0.160 | 25.9 | 0.757 | 0.894 |
| median | 0.213 | 0.162 | 18.2 | **0.865** | 0.951 |

`outputs/purity32_pixel_study/zero_shot_32pixels.csv`, `summary_overall.csv`,
`summary_by_class.csv`, `r2_by_pixel_and_class.png`. The median R² is meaningfully higher for the
purity-filtered subset (0.865 vs. 0.904 — actually the *full* 70-pixel median is slightly
*higher*; see Interpretation below for why this is not the naive result one might expect) than for
mixed-composition pixels specifically, though the difference is driven by a small number of very
low-purity, low-signal pixels rather than a smooth purity-performance gradient.

## Interpretation

> **RESULT**: across all 70 pixels spanning 8 vegetation classes and 9 U.S. regions, zero-shot
> Chronos-2 (no training, no fine-tuning) scores a median R² of 0.904 (mean 0.765), with 69% of
> pixels at R² ≥ 0.8, using only the existing gridMET/HiQ-LAI data already available locally.
>
> **INTERPRETATION**: the strong zero-shot generalization already established on the original 3
> core pixels (`COMPARISON_REPORT.md`) extends to a much larger, independently-selected, diverse
> pixel set — this is not an artifact of having hand-picked 3 favorable locations. Extending from
> 32 to the full 70 pixels did not meaningfully change this conclusion, which is itself informative:
> the pattern is not sensitive to exactly which diverse subset is examined.
>
> **INTERPRETATION**: the full 70-pixel median (0.904) being slightly *higher* than the
> purity-filtered 32-pixel median (0.865) is a reminder not to over-read small differences between
> overlapping, unequally-sized samples — it does not mean "mixed pixels forecast better than pure
> ones." Both the best and worst pixels in the entire pool (`px033_trees_ne`, R²=0.987; the two
> negative-R² grassland pixels) are all comfortably within the purity≥0.75 subset, so purity alone
> does not predict where the extremes fall.
>
> **INTERPRETATION**: performance is not uniform across vegetation types — tree- and
> shrub-evergreen classes (TREES_BD, TREES_NE, SHRUBS_NE) are the most consistently strong
> (std ≤ 0.065), while grassland and deciduous-shrub classes show much higher variance (std up to
> 0.47), driven by a small number of low-amplitude, low-signal pixels within those classes rather
> than a systematic weakness of the vegetation type itself — consistent with this project's
> repeated finding (LOYO-CV, predictor ablation) that *signal amplitude*, not vegetation type per
> se, is the dominant driver of forecast difficulty.
>
> **INTERPRETATION**: the regional breakdown (Southwest mean R²=0.28, n=3) is suggestive but
> should not be over-generalized — n=3 is too small to distinguish "the Southwest is genuinely
> harder" from "this project's 3 Southwest pixels happen to include a disproportionate share of
> low-signal grassland."
>
> **HYPOTHESIS, not established here**: whether this same ~0.9-median pattern would hold outside
> CONUS (the actual motivating question for the ERA5 study) remains untested by this experiment —
> this result only rules out "the original 3-pixel result was cherry-picked," it does not
> substitute for genuine geographic/climatic generalization evidence.

## Files

- `Code/build_purity32_pixel_comparison.py` — figure/summary generation for both the 32- and
  70-pixel tables (reads already-saved per-pixel results, no new experiments).
- `outputs/zero_shot/<pixel>/{predictions.csv,metrics.txt,prediction_plot.png}` — one per newly-run
  pixel (66 new; 4 reused from existing results elsewhere in the project).
- `outputs/purity32_pixel_study/` — `zero_shot_32pixels.csv`, `zero_shot_70pixels.csv`,
  `summary_overall{,_70pixels}.csv`, `summary_by_class{,_70pixels}.csv`,
  `summary_by_region_70pixels.csv`, `r2_by_pixel_and_class{,_70}.png`.
- `data/processed/sites/px0*.csv` — the 66 new pixel CSVs, copied from
  `AELSTM/data/processed/sites_pft_multipixel/` (same gridMET/HiQ-LAI extraction pipeline as
  every other pixel in this project).

## Reproducing

```bash
cd Code
# (pixel CSVs already copied into ../data/processed/sites/; see git history for the exact list)
/home/deh25003/miniconda3/envs/chronos2/bin/python3 run_chronos2.py --sites <new pixel names> --modes zero_shot
# NOTE: this OVERWRITES outputs/chronos2_all_results.csv with only the sites passed in --sites;
# back it up first if re-running, and restore/merge afterward (see this study's own commits for
# exactly how the already-published pixels' results were preserved).
python build_purity32_pixel_comparison.py
```

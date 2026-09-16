# Zero-Shot Chronos-2 Across 70 CONUS Pixels: Cloud ERA5 vs. gridMET

*Generated: 2026-09-15*

**Chronos-2 used strictly zero-shot: no training or fine-tuning, no change to
any existing Chronos-2 setting.**

## Setup

- **Data source**: Google ARCO-ERA5 (cloud), validated against CDS ERA5 for
  the evergreen pixel/2021-2022 period before use — see
  `ERA5_CLOUD_EQUIVALENCE_REPORT.md`.
- **Pixel set**: the same 70-pixel, 8-vegetation-class, 9-region CONUS pool
  already used for the gridMET CONUS-70 study
  (`reports/CHRONOS2_CONUS70_REPORT.md`) — reused unchanged, no new sampling.
- **Context**: 2000-2021 (~1,002 8-day LAI composites; a few pixels have
  997 where a small number of composites lacked full climate coverage at the
  series edges), forecast = all steps of 2022, observed 2022 climate as
  `future_covariates`, scored against raw observed LAI — **identical
  protocol and context length to the gridMET study**, fixing the original
  ERA5 validation's shorter 2020-2021-only context.
- **Runtime**: cloud prefetch (one-time, whole pool) ≈ 2 hours; the 70
  zero-shot Chronos-2 forecasts themselves took 23 seconds total once data
  was cached.

All 70 pixels succeeded; 0 failures.

## Results: 70 pixels, cloud ERA5

`outputs/era5_cloud_70pixels_clean.csv` (full table),
`era5_cloud_summary_{overall,by_class,by_region}.csv`,
`era5_cloud_r2_by_pixel_and_class.png`.

| | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|
| mean | 0.214 | 0.157 | 38.7 | 0.716 | 0.897 |
| median | 0.194 | 0.143 | 22.3 | **0.890** | 0.957 |
| std | 0.122 | 0.088 | 91.0 | 0.366 | 0.135 |
| min | 0.043 | 0.033 | 7.1 | −0.667 | 0.163 |
| max | 0.655 | 0.489 | 774.4 | 0.987 | 0.994 |

**By dominant vegetation class** (mean R², sorted):

| Class | n | Mean R² | Median R² | Std |
|---|---|---|---|---|
| TREES_BD | 7 | 0.939 | 0.939 | 0.022 |
| TREES_NE | 6 | 0.901 | 0.908 | 0.066 |
| TREES_ND | 6 | 0.860 | 0.929 | 0.180 |
| SHRUBS_NE | 7 | 0.842 | 0.843 | 0.044 |
| GRASS_MAN | 12 | 0.809 | 0.903 | 0.168 |
| GRASS_NAT | 19 | 0.643 | 0.904 | 0.489 |
| SHRUBS_BD | 7 | 0.471 | 0.519 | 0.462 |
| SHRUBS_ND | 6 | 0.313 | 0.406 | 0.394 |

64/70 pixels (91%) score Pearson r ≥ 0.8; **6/70 (9%) score R² < 0**, all in
GRASS_NAT/SHRUBS_ND/SHRUBS_BD.

## Deliverable: comparison against gridMET (same 70 pixels, matched context)

`outputs/era5_cloud_vs_gridmet_matched.csv`, `era5_cloud_vs_gridmet_scatter.png`.

| | ERA5 (cloud) | gridMET |
|---|---|---|
| Mean R² | 0.716 | 0.766 |
| Median R² | 0.890 | 0.905 |
| n pixels with R² < 0 | 6 | 2 |

Per-pixel R² between the two sources correlates strongly (Pearson
r = 0.886 across the 70 pixels) — pixels that are hard for one source tend
to be hard for the other. ERA5 scores a *higher* R² than gridMET on 31/70
pixels (44%) and lower on 39/70 (56%).

**The 4 largest ERA5-worse-than-gridMET drops** are all in already-marginal
SHRUBS_ND/SHRUBS_BD/GRASS_NAT pixels where gridMET itself was only
moderately confident (R² 0.26-0.53): `px035_shrubs_nd` (0.534→−0.128),
`px049_grass_nat` (0.437→−0168), `px059_shrubs_bd` (0.265→−0.295),
`px009_shrubs_nd` (0.367→−0.182). None of these were negative under
gridMET; ERA5 pushed all four into negative-R² territory.

**The largest ERA5-better-than-gridMET case** is `px045_grass_nat`, one of
the two pixels the gridMET study itself diagnosed as a low-signal,
near-flat grassland series (`CHRONOS2_CONUS70_REPORT.md`'s own outlier
section) — both sources score negative R² here, ERA5 less negative
(−0.263 vs. −0.724).

## Failures / outliers (deliverable 8)

No pixel failed to run. Six score R² < 0, all newly negative except the two
already-diagnosed low-signal grassland pixels:

| site | class | region | RMSE | R² (ERA5) | R² (gridMET) |
|---|---|---|---|---|---|
| px047_grass_nat | GRASS_NAT | Southwest | 0.118 | −0.667 | −0.348 |
| px059_shrubs_bd | SHRUBS_BD | Great Plains | 0.149 | −0.295 | 0.265 |
| px045_grass_nat | GRASS_NAT | Great Plains | 0.096 | −0.263 | −0.724 |
| px009_shrubs_nd | SHRUBS_ND | Other | 0.294 | −0.182 | 0.367 |
| px049_grass_nat | GRASS_NAT | Great Plains | 0.163 | −0.168 | 0.437 |
| px035_shrubs_nd | SHRUBS_ND | Other | 0.265 | −0.128 | 0.534 |

`px047_grass_nat`/`px045_grass_nat` reproduce the already-known
signal-to-noise failure mode (near-flat LAI, small absolute errors but
R² collapses because there is little true variance to explain — same
diagnosis as `LOYO_CV_FINDINGS.md`). The other four are **new** failures
specific to the cloud-ERA5 covariates: their LAI series are not flat
(std 0.31-0.49), their absolute RMSE is moderate (0.15-0.29), and gridMET
scores them positively — the most plausible explanation, consistent with
the equivalence report's diagnosed precipitation/wind discrepancy, is that
noisier ERA5-derived covariates on these already-marginal pixels degraded
an already-fragile forecast rather than a wholesale pipeline problem
(64/70 pixels, including the majority of tree/shrub-evergreen classes,
are unaffected and score Pearson r ≥ 0.8).

## Interpretation

> **RESULT**: across the same 70 pixels and the same 22-year context used
> for the gridMET study, zero-shot Chronos-2 with cloud-ERA5 covariates
> scores a median R² of 0.890 (mean 0.716), versus gridMET's median 0.905
> (mean 0.766) on the identical pixels/context. Per-pixel R² correlates
> strongly between the two sources (r=0.886).
>
> **INTERPRETATION**: the strong zero-shot generalization already
> established with gridMET (median R²=0.904, `CHRONOS2_CONUS70_REPORT.md`)
> is **not specific to gridMET** — an independent reanalysis product
> (ERA5) produces a comparably strong result (median R²=0.890) under an
> identical protocol. This is the first evidence in this project that the
> zero-shot pattern generalizes across *meteorological data sources*, not
> just across pixels within one source.
>
> **INTERPRETATION**: gridMET and cloud-ERA5 are not interchangeable at the
> level of individual marginal pixels — cloud-ERA5 has a longer negative-R²
> tail (6 vs. 2 of 70) concentrated in already-difficult SHRUBS_ND/
> SHRUBS_BD/GRASS_NAT pixels, consistent with (not proof of) the
> equivalence report's diagnosed precipitation/wind noise in the ERA5-cloud
> covariates. **Do not read this as "ERA5 is worse than gridMET" in
> general**: ERA5 outperforms gridMET on 31/70 pixels, including the
> single worst pixel in the whole pool, and the two medians differ by only
> 0.015 — the honest reading is comparable central-tendency performance
> with a somewhat heavier tail of poor pixels for ERA5, not a systematic
> quality gap.
>
> **HYPOTHESIS, not established here**: whether the four newly-negative
> pixels are specifically attributable to the precipitation/wind
> discrepancy diagnosed in the equivalence report (rather than, e.g.,
> ordinary zero-shot sensitivity to any alternate covariate realization)
> is not tested directly — doing so would require re-running those four
> pixels with a precipitation/wind-only source swap, which was out of
> scope for this study.

## Files

See `experiments/global_era5_chronos/README.md` for the complete
reproducible pipeline (dataset, variables, units, transformations,
aggregation, access date, environment setup).

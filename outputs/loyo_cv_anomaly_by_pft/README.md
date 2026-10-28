# LAI-Anomaly LOYO-CV, Broken Down by Vegetation Class

*Generated: 2026-10-27*

Prof. Wang's feedback on the pooled CONUS/Global boxplot (one box per pool,
770/748 folds pooled across all vegetation types): pooling everything
together hides which vegetation types Chronos-2 is actually good at
forecasting LAI anomaly for. This reruns the same fold-level results
(`outputs/loyo_cv_anomaly/all_folds_anomaly.csv`, `experiments/global_era5_chronos/outputs/loyo_cv_anomaly/all_folds_anomaly.csv`
— no new Chronos-2 calls, same 770/748 folds as before) grouped by each
site's dominant vegetation class instead, using the authoritative per-pixel
ESA-CCI PFT classification already used elsewhere in this project
(`data/processed/pft_diverse_pixels.csv` for CONUS,
`experiments/global_era5_chronos/data_selection/global_candidate_pixels_70.csv`
for Global) — not the informal class suffix in the site name.

Script: `Code/loyo_cv_anomaly_by_pft.py`. Outputs:
`loyo_anomaly_by_pft_boxplots.png/.pdf` (4-panel: Pearson r and R², CONUS
and Global, each broken out by class) and 4 summary CSVs
(`{conus,global}_by_pft_{pearson_r,r2}.csv`).

## Finding

A consistent pattern shows up **independently in both pools** (not an
artifact of one site or one region):

**Shrubs and grasses forecast better than trees**, in Pearson r:

| Class family | CONUS median r | Global median r |
|---|---|---|
| Shrubs (BD/ND/NE/BE) | 0.38 – 0.55 | 0.17 – 0.27 |
| Grass (NAT/MAN) | 0.24 – 0.32 | 0.17 – 0.21 |
| Trees (BD/ND/NE/BE) | 0.17 – 0.23 | 0.02 – 0.17 |

The ordering (shrubs > grass > trees) holds in both pools even though the
absolute numbers differ between them. A plausible read: trees have slower,
more inertia-dominated canopy dynamics (deep rooting, leaf longevity) where
the *anomaly* signal is smaller relative to noise, while shrubs/grass
respond faster to the same interannual drivers Chronos-2 can pick up from
context — this is a hypothesis prompted by the pattern, not something this
analysis tests directly.

**R² tells a flatter, noisier story** — all classes hover near or below
zero with large negative outliers (worst: CONUS Shrubs_NE site, -4.1), the
same R²-instability-vs-Pearson-r-robustness pattern already documented
elsewhere in this project. The class ranking is far less clean in R² than
in Pearson r; lead with Pearson r when presenting this.

## Caution: several classes have very few sites

Read these with their `n_sites`, not just `n_folds` — a class with 2-3
sites is essentially a 2-3 point estimate repeated across 11 years, not an
independent 22-33 fold sample:

- Global: `TREES_ND` (2 sites, 22 folds), `SHRUBS_ND`/`SHRUBS_NE`/`SHRUBS_BE`
  (3 sites each, 33 folds each).
- CONUS: smallest classes still have 6+ sites, so less of a concern there.

The shrubs > grass > trees ordering is visible within CONUS alone (where
the smallest class still has 6 sites), which is reassuring, but the Global
numbers for the 2-3-site classes should be presented as suggestive, not
definitive.

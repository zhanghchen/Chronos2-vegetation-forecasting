# Progress Report: Vegetation-Class LAI Breakdown + GPP Data Fix + GPP vs. LAI Zero-Shot Comparison

*Generated: 2026-10-28*

Three things, in the order Prof. Wang asked about them: (1) the fix to last
week's pooled LAI-anomaly boxplot, (2) why the GPP data was reported as
"only available from 2021" and what the actual problem was, (3) the first
GPP vs. LAI zero-shot comparison now that real GPP data is in hand.

---

## 1. Improvement to last week's result: LAI anomaly broken down by vegetation class

Last week's "Part 1 Aggregate" slide showed one pooled boxplot per region
(CONUS: 770 folds, Global: 748 folds) — every vegetation type mixed
together. Prof. Wang's feedback: that hides which vegetation types
Chronos-2 is actually good at.

Reran the same already-computed fold-level results (no new model calls),
grouped by each site's dominant vegetation class instead, using the
project's existing ESA-CCI-derived PFT classification (not the informal
site-name suffix). Script: `Code/loyo_cv_anomaly_by_pft.py`. Figure:
`outputs/loyo_cv_anomaly_by_pft/loyo_anomaly_by_pft_boxplots.png`.

**Finding, consistent independently in both CONUS and Global pools:**

| Class family | CONUS median Pearson r | Global median Pearson r |
|---|---|---|
| Shrubs | 0.38 – 0.55 | 0.17 – 0.27 |
| Grass | 0.24 – 0.32 | 0.17 – 0.21 |
| Trees | 0.17 – 0.23 | 0.02 – 0.17 |

**Shrubs and grasses forecast noticeably better than trees** in both
pools. Plausible mechanism (a hypothesis prompted by the pattern, not
independently tested here): trees have slower, inertia-dominated canopy
dynamics, so the year-to-year *anomaly* signal is small relative to noise;
shrubs/grass respond faster to the same interannual weather drivers
Chronos-2 sees in context. R² is noisier than Pearson r across classes —
same R²-instability pattern already documented in this project, so Pearson
r is the metric to lead with. Caveat: a few Global classes have only 2-3
sites (`TREES_ND`, `SHRUBS_ND/NE/BE`) and should be read as suggestive, not
definitive — CONUS classes all have 6+ sites.

---

## 2. Why the GPP data was reported as "only 2021-2022 available"

This was **not a request error** — the original script's date range was
correctly specified (`startDate: 01-01-2000`) — and it was **not an actual
limitation of MODIS GPP data itself**. It was the wrong product.

**Root cause, confirmed directly against AppEEARS' own product catalog**
(`GET /api/product`, not inferred from behavior):

| Product requested originally | `MOD17A2H.061` | `TemporalExtentStart: 2021-01-01` |
|---|---|---|
| Product that should have been requested | `MOD17A2HGF.061` ("GF" = gap-filled) | `TemporalExtentStart: 2000-01-01`, same layers (`Gpp_500m`, `Psn_QC_500m`), same scale factor |

`MOD17A2H.061` is a genuinely newer MODIS collection that LP DAAC only
started serving from 2021 onward — requesting more history from it was
never going to work, regardless of how the request was written.
`MOD17A2HGF.061` is the full-record, gap-filled companion product and
covers the full 2000-2022 range needed. This matches the full-record
product on the catalog page Prof. Wang linked
(`lpcloud-mod17a2h-006` — the older-numbered equivalent of today's full-record
GF product).

Resubmitted under `MOD17A2HGF.061` (`Code/fetch_conus_gpp_appeears.py`,
updated with this fix documented in its header) — confirmed the new
downloads cover 2000-2022 in full before using the data.

**Data sanity check performed before trusting it** (same type of check that
caught a 10x LAI scale-factor bug earlier in this project): good-QC
`Gpp_500m` values for forest/grass sites come out in the 0-0.1 kg C/m²/8-day
range, which looked suspiciously low at first glance. Summed to an annual
total per site (e.g. `px005_trees_bd`, a broadleaf-deciduous forest
pixel: ~0.9-1.0 kg C/m²/year across 2015-2018), this lines up with
published typical annual GPP for temperate forest/grassland — confirming
the scale factor is correct, not a repeat of the earlier LAI bug.

---

## 3. First GPP vs. LAI zero-shot comparison (no physics guidance yet)

Per the plan agreed with Prof. Wang: data first, zero-shot baseline second,
physics-guided fine-tuning on GPP last (not started yet).

**Protocol**: identical LOYO-CV anomaly-forecasting setup already used for
LAI (`Code/loyo_cv_gpp_anomaly_chronos2.py`, same 12-year rolling window,
same no-leakage climatology, same weather covariates) — only the target
column changes (GPP instead of LAI). This makes the comparison apples-to-
apples: same sites, same folds, same model, same protocol.

**AppEEARS download strategy note**: the full 70-site request sat in
AppEEARS' processing queue for several hours with no progress signal (the
queue appears congested independent of request size — even an 8-point
test request took comparably long), so three requests of increasing size
(8/20/70 sites) were submitted in parallel as a hedge. The 8-site and
20-site requests have completed; the 70-site request is still processing
in the background and this report will be updated with the full-sample
result once it lands.

**Result on the 20 sites downloaded so far** (20 sites × 11 LOYO years =
220 folds; sites chosen as the top 2-3 most PFT-pure sites per vegetation
class plus the 4 original project validation sites, so all 8 CONUS
vegetation classes are represented):

| | mean R² | median R² | mean Pearson r | median Pearson r |
|---|---|---|---|---|
| LAI anomaly (same 20 sites) | -0.172 | -0.054 | 0.286 | 0.267 |
| **GPP anomaly (same 20 sites)** | **0.030** | **0.045** | **0.358** | **0.380** |

**GPP is forecast noticeably better than LAI, zero-shot, on both metrics.**
By vegetation class:

| Class | LAI mean r | GPP mean r | n folds |
|---|---|---|---|
| Grass (managed) | 0.121 | 0.348 | 22 |
| Grass (natural) | 0.265 | 0.360 | 33 |
| Shrubs (BD) | 0.450 | 0.569 | 22 |
| Shrubs (ND) | 0.423 | 0.426 | 22 |
| Shrubs (NE) | 0.518 | 0.560 | 22 |
| Trees (BD) | 0.186 | 0.251 | 44 |
| Trees (ND) | 0.233 | 0.293 | 22 |
| Trees (NE) | 0.229 | 0.226 | 33 |

GPP wins in 7 of 8 classes; trees (needleleaf evergreen) is essentially
tied. Grasses show the largest relative gain.

**Interpretation (hypothesis, not yet tested directly)**: this is
consistent with Prof. Wang's expectation that GPP is the more weather-
coupled, more directly forecastable target — GPP responds to the same
short-term weather drivers Chronos-2 sees in its covariates more directly
than LAI, which is a slower-integrating structural/canopy variable. This
zero-shot result doesn't yet test whether physics-guided fine-tuning helps
GPP more than LAI (that's the next planned step) — it only establishes
that the *baseline* gap between the two targets is real and goes in the
expected direction, which is itself informative before spending effort on
the fine-tuning comparison.

## Next steps

1. Confirm this result holds at the full 70-site scale once that download
   finishes (currently still processing on AppEEARS' side).
2. Physics-guided fine-tuning on GPP, using the existing phenology
   equation and `Code/physics_guided_chronos2_finetune_phenology.py`'s
   machinery (already supports GPP as `--target-col`) — deliberately not
   started yet, per the agreed order of work.

## Files

- `Code/loyo_cv_anomaly_by_pft.py` — vegetation-class breakdown (item 1).
- `Code/fetch_conus_gpp_appeears.py`, `Code/poll_and_download_conus_gpp.py`,
  `Code/fetch_conus_gpp20_appeears.py`, `Code/fetch_conus_gpp8_appeears.py`
  — corrected GPP download scripts (item 2), 70/20/8-site variants.
- `Code/build_conus_gpp_sites.py` — QC filter + merge with weather
  covariates, `--pool {8,20,70}`.
- `Code/loyo_cv_gpp_anomaly_chronos2.py` — the zero-shot GPP experiment
  (item 3).
- `outputs/loyo_cv_gpp_anomaly/all_folds_gpp_anomaly.csv` — raw results.

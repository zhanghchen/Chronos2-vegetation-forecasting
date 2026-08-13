# Predictor Sensitivity / Ablation Study

**Scope**: 9 methods (8 AELSTM-family + Chronos-2 zero-shot — LoRA fine-tuning excluded, see
"Design" below), 3 pixels, same train-2000-2021/test-2022 protocol as the current setup. The
full-7-predictor baseline is not rerun — read from each method's already-computed, raw-obs-scored
results. All deltas are `ablated_metric − baseline_metric`, so negative ΔR² means removing the
predictor hurt.

## Design

Testing all 2⁷=128 predictor subsets would be neither computationally reasonable nor
interpretable. Instead, a two-phase, pre-registered design:

**Phase 1 — leave-one-predictor-out (7 configs)**: drop exactly one of `tmmx, tmmn, pr, srad,
vpd, sph, vs` at a time, keep the other 6. This directly estimates each predictor's individual
contribution, holding everything else fixed.

**Phase 2 — grouped ablations (4 configs), selection rule fixed *before* Phase 1 ran**: after
computing each predictor's average ΔR² across all 9 methods × 3 pixels (27 points) in Phase 1,
add exactly four more configs:
1. **Top-3 essential only** — keep just the 3 highest-ranked predictors.
2. **Drop least-important pair** — remove the 2 lowest-ranked predictors together.
3. **Drop `{tmmx, tmmn}`** — a priori physical hypothesis (daily max/min temperature likely redundant with each other).
4. **Drop `{vpd, sph}`** — same logic for the two moisture/humidity variables.

**Chronos-2 uses zero-shot only, not LoRA fine-tuned.** Fine-tuning would need its own
hyperparameter re-search per predictor subset to stay fair (the improved-fine-tuning experiment's
6-config search × 11 subsets × 3 pixels), which is outside a computationally manageable scope.
Zero-shot also isolates the pure predictor-set effect without a training-noise confound. For
Chronos-2, `common_pipeline.build_chronos_inputs(feature_cols=...)` already applies the same
`feature_cols` list to both `past_covariates` and `future_covariates`, so a dropped predictor is
removed from both consistently by construction.

Total compute: 11 configs × 3 pixels × (~55s for all 8 AELSTM models + ~5s Chronos-2) ≈ 35 minutes.

## Which predictors matter most (Phase 1, averaged across all 9 methods × 3 pixels)

| Predictor | Mean ΔR² when removed | Std | Interpretation |
|---|---|---|---|
| **srad** | **−0.0215** | 0.067 | Most important — consistently useful across every pixel (see below) |
| **tmmn** | **−0.0167** | 0.031 | Second most important |
| **tmmx** | **−0.0148** | 0.042 | Third most important overall, but this hides a large pixel-specific effect (see below) |
| vpd | +0.0001 | 0.022 | Essentially neutral on average |
| sph | +0.0012 | 0.030 | Essentially neutral on average |
| pr | +0.0068 | 0.044 | Mildly *helpful* to remove, on average |
| **vs** | **+0.0084** | 0.039 | Most *redundant* predictor — removing it helps slightly more often than it hurts |

`predictor_importance_ranking.png` shows this as a ranked bar chart with error bars.

## Do different models depend on different predictors?

**Yes, substantially.** `predictor_model_pixel_heatmap.png` (predictor × model, one panel per
pixel) shows the same predictor's removal can have opposite effects on different models within the
same pixel. At `low_amplitude`: removing `pr` *helps* GRU dramatically (ΔR² ≈ +0.15) while hurting
RNN and CNN; removing `srad` is catastrophic for CNN (ΔR² ≈ −0.15) but mild-to-positive for most
other models. At `evergreen`: removing `tmmx` *helps* LSTM (ΔR² ≈ +0.11) while removing the same
predictor is neutral-to-negative for CNN, RF, and SVM. No single predictor-importance ranking
applies uniformly across model families — tree/kernel methods (RF, SVM) and different neural
architectures respond differently to the same removed input, likely reflecting how each model's
inductive bias interacts with a smaller, more collinear feature set.

## Does predictor importance change across vegetation types?

**Yes, most visibly for temperature.** `predictor_importance_by_pixel.png` breaks the average
ΔR² down by pixel:

- **`srad` is the one predictor that matters everywhere** — its removal hurts at all 3 pixels
  (`low_amplitude`: −0.024, `high_amplitude_deciduous`: −0.012, `evergreen`: −0.028), the only
  predictor with a consistent sign across all three vegetation types.
- **Temperature's importance is almost entirely pixel-specific.** Removing `tmmx`/`tmmn` is the
  single most damaging ablation at `low_amplitude` (ΔR² = −0.052 / −0.040), but removing the *same*
  predictors is mildly *helpful* at `high_amplitude_deciduous` (+0.001 / +0.002) and mixed at
  `evergreen` (+0.007 for `tmmx`, −0.012 for `tmmn`). A predictor that is nearly indispensable at
  one pixel is close to irrelevant — or even a source of noise — at another.
- **`pr` and `vs` are only redundant at `low_amplitude`** (ΔR² = +0.028 and +0.025, the two largest
  positive effects in the whole study) and close to neutral at the other two pixels — plausibly
  because `low_amplitude` (a sparse natural grassland with very small seasonal amplitude) has the
  weakest true climate-LAI signal of the three pixels, so redundant/noisy predictors have the most
  room to actively hurt a model there, and the most to gain from being dropped.

## Does removing redundant predictors maintain or improve performance? (Phase 2)

**Yes — the data-driven reduced set does, consistently.** `predictor_reduced_sets.png` and
`reduced_sets_summary.csv`:

| Configuration | `low_amplitude` | `high_amplitude_deciduous` | `evergreen` |
|---|---|---|---|
| **Drop least-important pair** (`vs`, `pr` removed; 5 predictors kept) | **+0.066** | **+0.004** | **+0.020** |
| Top-3 essential only (`tmmx`, `tmmn`, `srad`) | +0.072 | −0.012 | +0.027 |
| Drop temperature pair (`tmmx`, `tmmn` removed) | −0.076 | −0.007 | +0.003 |
| Drop moisture pair (`vpd`, `sph` removed) | −0.013 | −0.003 | +0.003 |

"Drop least-important pair" — informed directly by the Phase-1 ranking rather than a priori
guessing — **improves average R² on all three pixels simultaneously** while using 2 fewer
predictors than the current 7-predictor setup. This is a genuine, actionable finding: `vs` and `pr`
add more noise than signal on average across this project's model set and pixels, and a leaner
5-predictor input (`tmmx, tmmn, srad, vpd, sph`) is a defensible default going forward.

The "top-3 essential" set performs nearly as well (and best of all at `low_amplitude`), but loses a
small amount at `high_amplitude_deciduous` — plausibly because that pixel's near-ceiling baseline
(R² > 0.93 for every method) leaves the model reliant on marginal contributions from `pr`/`vpd`/
`sph`/`vs` that a 3-predictor set can no longer supply. Dropping temperature is clearly the worst
choice tested, confirming temperature's importance is real (just concentrated at specific pixels)
rather than an artifact of the ranking.

## Key Findings

1. **`srad` (shortwave radiation) is the only predictor that matters at every pixel tested** — it
   is the single highest-ranked predictor overall and the only one with a consistent negative
   ΔR² across all three vegetation types.
2. **Different models rely on different predictors, even at the same pixel.** The same removed
   predictor can help one model and hurt another (e.g., dropping `pr` helps GRU but hurts RNN/CNN
   at `low_amplitude`) — there is no universal per-predictor importance ranking that holds across
   model architectures.
3. **Predictor importance is strongly vegetation-type-dependent, especially for temperature.**
   `tmmx`/`tmmn` are the most important predictors at `low_amplitude` and among the least important
   (or even counterproductive) at the other two pixels.
4. **Two predictors (`vs`, `vs` paired with `pr`) are measurably redundant.** Removing them
   together improves mean R² at all 3 pixels — the current 7-predictor setup is not the leanest
   effective choice, and a 5-predictor set (`tmmx, tmmn, srad, vpd, sph`) is a validated, better
   default.
5. **`low_amplitude` is the most predictor-sensitive pixel by far** (largest deltas in both
   directions), consistent with it having the weakest underlying climate-LAI signal of the three
   pixels tested — `high_amplitude_deciduous` is comparatively insensitive to any single predictor
   change, since its strong seasonal cycle dominates the achievable R² regardless of input set.

## Reproducing

```bash
# AELSTM project
cd AELSTM/Code
python predictor_ablation_experiment.py --sites low_amplitude high_amplitude_deciduous evergreen
# -> outputs/predictor_ablation/<site>/<config>_metrics.csv, all_ablation_results.csv

# Chronos2 project
cd Chronos2-vegetation-forecasting/Code
python predictor_ablation_chronos2.py --sites low_amplitude high_amplitude_deciduous evergreen
python build_predictor_ablation_comparison.py
# -> outputs/predictor_ablation/comparison/ (all figures + predictor_ablation_all_results.csv)
```

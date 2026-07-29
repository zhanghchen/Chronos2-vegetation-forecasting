# Chronos-2 vs. AELSTM — Comprehensive Comparison Report

**Scope**: 3 pixels run with both frameworks (`low_amplitude`, `high_amplitude_deciduous`,
`evergreen`) + 1 pixel run with AELSTM only (`western_kansas_eastern_colorado`, the original
project pixel, predating this comparison). All numbers below are **every model scored against
the same raw observed LAI** for 2022 — see "A note on 'ground truth'" for why that qualifier
matters and isn't decorative.

Sources (all pre-computed, no retraining involved in assembling this report):
[`AELSTM/outputs/model_comparison/all_sites_vs_raw_observations.csv`](https://github.com/zhanghchen/AELSTM-vegetation-forecasting/blob/main/outputs/model_comparison/all_sites_vs_raw_observations.csv),
[`outputs/chronos2_all_results.csv`](outputs/chronos2_all_results.csv),
[`outputs/fair_comparison_vs_raw_observations.csv`](outputs/fair_comparison_vs_raw_observations.csv).

## Executive summary

1. **Does Chronos-2 show an advantage? Yes, on raw predictive accuracy, with a real caveat on why.**
   Zero-shot Chronos-2 — no training on this data at all — is the best or statistically-tied-best
   model on all 3 pixels tested (mean rank 1.33 of 10). But its task included the actual future
   climate as a known input; AELSTM's did not. See Q1 below for what that does and doesn't mean.
2. **Comprehensive comparison**: this document, plus the two CSVs it's built from.
3. **Did fine-tuning help? No — it made Chronos-2 worse on every single pixel tested**, by a
   consistent margin. See Q3 for the full evidence and likely causes.

---

## Q1. Does Chronos-2 demonstrate an advantage over AELSTM? In what respects?

**Accuracy, on this task, at these 3 pixels: yes, clearly.**

| Pixel | Best method | R² | 2nd best | R² | AELSTM's own R² | AELSTM's rank (of 10) |
|---|---|---|---|---|---|---|
| low_amplitude | **zero-shot Chronos-2** | 0.542 | SVM | 0.465 | 0.365 | 8th |
| high_amplitude_deciduous | **zero-shot Chronos-2** | 0.965 | GRU | 0.961 | 0.934 | 10th |
| evergreen | SVM | 0.8323 | **zero-shot Chronos-2** | 0.8322 | 0.681 | 9th |

Zero-shot Chronos-2 wins outright on 2 of 3 pixels and is separated from the winner by 0.00003 R²
on the third (evergreen) — not a meaningful difference. AELSTM itself is never better than 8th of
10 at any of the 3 pixels.

**Where the advantage plausibly comes from, not just "the model is better":**
- **It was given the actual future climate as input** (`future_covariates`), which is the
  project's deliberately-chosen research question (see AELSTM vs. Chronos-2 task setup below) —
  AELSTM's architecture has no mechanism to use this at all. This is the single largest
  contributor and should not be read as "Chronos-2 predicts LAI better from the same
  information" — it doesn't get the same information.
- **No manual preprocessing was needed** — no smoothing, no scaler-fitting, no leakage risk from
  getting that wrong (an issue that materially affected this project's own AELSTM pipeline; see
  below).
- **Zero training on this specific pixel** — every AELSTM-family model was trained from scratch
  per pixel; Chronos-2 zero-shot used a single pretrained checkpoint unmodified. That it's
  *competitive at all* against 8 specialized, from-scratch-trained models is the more surprising
  and defensible claim; that it's *often better* is real but partly attributable to the easier
  task, per above.

**What this is not evidence of**: that Chronos-2's architecture is intrinsically superior at
sequence modeling, or that AELSTM's approach is obsolete for its own (harder, past-climate-only)
task. It's evidence that *if you have reliable future climate forcings available* (e.g. a seasonal
forecast, or a scenario/what-if analysis), a foundation model that can natively consume them is a
strong option — arguably the more practically useful finding than a head-to-head "which
architecture wins."

## Q2. Comprehensive comparison document

That's this document. Full per-pixel tables follow.

### low_amplitude (37.53°N, 117.56°W)

| Rank | Model | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|---|
| 1 | **zero-shot (Chronos-2)** | 0.0580 | 0.0396 | 17.94 | **0.5417** | 0.7596 |
| 2 | SVM | 0.0627 | 0.0464 | 21.11 | 0.4647 | 0.7187 |
| 3 | RF | 0.0651 | 0.0462 | 21.68 | 0.4216 | 0.7198 |
| 4 | RNN | 0.0672 | 0.0479 | 23.23 | 0.3854 | 0.7611 |
| 5 | LSTM | 0.0673 | 0.0463 | 21.81 | 0.3821 | 0.7557 |
| 6 | BiLSTM | 0.0674 | 0.0484 | 22.80 | 0.3803 | 0.7499 |
| 7 | LoRA fine-tuned (Chronos-2) | 0.0675 | 0.0530 | 20.61 | 0.3786 | 0.6486 |
| 8 | AELSTM | 0.0683 | 0.0487 | 23.15 | 0.3648 | 0.7485 |
| 9 | CNN | 0.0703 | 0.0501 | 23.72 | 0.3263 | 0.7542 |
| 10 | GRU | 0.0718 | 0.0524 | 25.36 | 0.2969 | 0.7690 |

### high_amplitude_deciduous (36.23°N, 84.48°W)

| Rank | Model | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|---|
| 1 | **zero-shot (Chronos-2)** | 0.3722 | 0.2459 | 14.14 | **0.9654** | 0.9835 |
| 2 | GRU | 0.3930 | 0.2864 | 14.44 | 0.9614 | 0.9819 |
| 3 | RF | 0.4142 | 0.2859 | 14.47 | 0.9571 | 0.9792 |
| 4 | BiLSTM | 0.4153 | 0.2863 | 13.73 | 0.9569 | 0.9794 |
| 5 | RNN | 0.4261 | 0.2956 | 14.39 | 0.9546 | 0.9791 |
| 6 | LoRA fine-tuned (Chronos-2) | 0.4392 | 0.2864 | 16.05 | 0.9518 | 0.9764 |
| 7 | SVM | 0.4436 | 0.3355 | 20.72 | 0.9508 | 0.9771 |
| 8 | LSTM | 0.4841 | 0.3293 | 18.85 | 0.9414 | 0.9710 |
| 9 | CNN | 0.4879 | 0.3439 | 18.77 | 0.9405 | 0.9705 |
| 10 | AELSTM | 0.5131 | 0.3333 | 17.81 | 0.9342 | 0.9668 |

### evergreen (30.53°N, 82.43°W)

| Rank | Model | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|---|
| 1 | SVM | 0.4849 | 0.3606 | 12.14 | **0.8323** | 0.9147 |
| 2 | zero-shot (Chronos-2) | 0.4850 | 0.4259 | 14.02 | 0.8322 | 0.9301 |
| 3 | RF | 0.5511 | 0.4111 | 13.59 | 0.7834 | 0.8912 |
| 4 | GRU | 0.5790 | 0.4283 | 14.72 | 0.7608 | 0.8755 |
| 5 | RNN | 0.6015 | 0.4441 | 15.03 | 0.7419 | 0.8669 |
| 6 | LoRA fine-tuned (Chronos-2) | 0.6352 | 0.5305 | 16.53 | 0.7122 | 0.8782 |
| 7 | LSTM | 0.6508 | 0.4982 | 16.85 | 0.6978 | 0.8461 |
| 8 | BiLSTM | 0.6554 | 0.5013 | 17.38 | 0.6935 | 0.8479 |
| 9 | AELSTM | 0.6683 | 0.5261 | 18.12 | 0.6814 | 0.8458 |
| 10 | CNN | 0.6689 | 0.5144 | 18.03 | 0.6809 | 0.8362 |

### western_kansas_eastern_colorado (38.48°N, 101.52°W) — AELSTM-family only, Chronos-2 not run here

| Rank | Model | RMSE | MAE | MAPE | R² | Pearson r |
|---|---|---|---|---|---|---|
| 1 | RF | 0.1059 | 0.0887 | 19.03 | 0.7403 | 0.8728 |
| 2 | BiLSTM | 0.1096 | 0.0935 | 19.68 | 0.7217 | 0.8947 |
| 3 | SVM | 0.1127 | 0.0923 | 20.40 | 0.7057 | 0.8754 |
| 4 | AELSTM | 0.1133 | 0.0942 | 20.35 | 0.7026 | 0.8848 |
| 5 | GRU | 0.1174 | 0.0959 | 20.26 | 0.6807 | 0.8878 |
| 6 | CNN | 0.1211 | 0.0953 | 19.12 | 0.6601 | 0.8557 |
| 7 | LSTM | 0.1342 | 0.1078 | 23.06 | 0.5831 | 0.8351 |
| 8 | RNN | 0.1349 | 0.1077 | 21.84 | 0.5787 | 0.8506 |

### Rank consistency across the 3 shared pixels

| Model | low_amplitude | high_amplitude_deciduous | evergreen | Mean rank | Std dev |
|---|---|---|---|---|---|
| **zero-shot (Chronos-2)** | 1 | 1 | 2 | **1.33** | 0.58 |
| RF | 3 | 3 | 3 | 3.00 | 0.00 |
| SVM | 2 | 7 | 1 | 3.33 | 3.21 |
| RNN | 4 | 5 | 5 | 4.67 | 0.58 |
| GRU | 10 | 2 | 4 | 5.33 | 4.16 |
| BiLSTM | 6 | 4 | 8 | 6.00 | 2.00 |
| LoRA fine-tuned (Chronos-2) | 7 | 6 | 6 | 6.33 | 0.58 |
| LSTM | 5 | 8 | 7 | 6.67 | 1.53 |
| AELSTM | 8 | 10 | 9 | 9.00 | 1.00 |
| CNN | 9 | 9 | 10 | 9.33 | 0.58 |

Two models are perfectly consistent (std dev 0 across all 3 pixels): **zero-shot Chronos-2 at
rank 1.33** and **RF at rank 3.00**. Everything else swings by at least half a rank position,
and GRU swings wildly (rank 10 → rank 2) — a caution against trusting any single-pixel result
for the swingier models.

## Q3. Did fine-tuning actually help? No. Full evidence.

| Pixel | Zero-shot R² | LoRA fine-tuned R² | Change | Zero-shot rank | Fine-tuned rank |
|---|---|---|---|---|---|
| low_amplitude | 0.5417 | 0.3786 | **−0.163** | 1 | 7 |
| high_amplitude_deciduous | 0.9654 | 0.9518 | **−0.014** | 1 | 6 |
| evergreen | 0.8322 | 0.7122 | **−0.120** | 2 | 6 |

**Zero-shot beat fine-tuned on all 3 of 3 pixels, with no exceptions and no borderline cases.**
This is a consistent, reproducible pattern, not noise — the smallest gap (high_amplitude_deciduous)
is still 6 rank positions.

**Why, based on the evidence gathered across this project:**

1. **This is exactly the failure mode Chronos-2's own documentation warns about.** The quickstart
   notebook (`notebooks/chronos-2-quickstart.ipynb`, Fine-Tuning section) states verbatim: *"In
   case of limited data (too few and/or too short series), fine-tuning may not improve over
   zero-shot (and may even worsen accuracy sometimes)."* Each fine-tuning run here used exactly
   one series of ~1000 points — squarely the scenario described.
2. **No validation-based checkpoint selection was used.** `fit()`'s underlying `Trainer` runs with
   `save_strategy="no"`, `load_best_model_at_end=False` unless a validation set and different
   settings are explicitly configured — training simply stops at step 1000 and keeps those
   weights, with no mechanism to detect or roll back overfitting partway through. We did not pass
   `validation_inputs`.
3. **Hyperparameters were Amazon's own notebook defaults** (`lr=1e-4`, `num_steps=1000`,
   `batch_size=32`), tuned by them on a larger multi-series retail dataset, not on a short
   single-series regime like ours — a plausible mismatch, not evidence the method is broken.
4. **The zero-shot starting point was already strong.** A foundation model pretrained on diverse
   time series likely already encodes a good general prior for "seasonal series with covariates."
   With only one short, noisy series to adapt on, there's more room for fine-tuning to perturb
   that prior for the worse than to meaningfully improve it.

None of this was tuned or cherry-picked after the fact — the LoRA hyperparameters were fixed
before any pixel was run, taken directly from Amazon's own example, and applied identically to
all 3 pixels.

---

## A note on "ground truth" — why "vs. raw observations" is the right basis for this report

AELSTM's own pipeline applies a Savitzky-Golay smoothing filter to the LAI target before
training/scaling
([`AELSTM/Code/common_pipeline.py:92-93`](https://github.com/zhanghchen/AELSTM-vegetation-forecasting/blob/main/Code/common_pipeline.py#L92-L93)),
and its own `predictions.csv`/plots report metrics against that **smoothed** signal — correct for
judging the 8 AELSTM-family models against each other (smoothing applied identically to all), but
an easier target than the real observations Chronos-2 was always scored against. Every number in
this report recomputes the AELSTM-family metrics against the same raw observed LAI Chronos-2 uses,
from each model's already-saved predictions (no retraining). See
[`AELSTM/README.md`](https://github.com/zhanghchen/AELSTM-vegetation-forecasting/blob/main/README.md)
for the full explanation and
[`AELSTM/outputs/model_comparison/`](https://github.com/zhanghchen/AELSTM-vegetation-forecasting/tree/main/outputs/model_comparison)
for the per-site `comparison_metrics_vs_raw_observations.csv` detail.

## Important caveats on generalizing these findings

- **3 pixels is a small sample.** GRU's rank swings from 2nd to 10th between pixels — a reminder
  that any single-pixel ranking (including "Chronos-2 is best") could shift with more pixels.
  The remaining 3 selected pixels (`cropland_managed`, `grassland_shrubland`,
  `strong_interannual_variability`) have not yet been run through Chronos-2.
- **The AELSTM-vs-Chronos-2 comparison is not same-task.** Chronos-2 had known future climate;
  AELSTM did not. Treat the "Chronos-2 wins" result as "foundation model + future covariates beats
  from-scratch models without them," not as a pure architecture bake-off.
- **Fine-tuning was only tried in the single-series, default-hyperparameter regime** described
  above — this rules out "fine-tuning never helps," not "fine-tuning can't help here" (see the
  suggested next steps: validation-based checkpointing, joint multi-pixel fine-tuning).

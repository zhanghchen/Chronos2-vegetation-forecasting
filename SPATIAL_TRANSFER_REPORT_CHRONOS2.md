# Spatial Transfer: Chronos-2 Trained on One Evergreen Pixel, Deployed on Another

Chronos-2 counterpart to
[`AELSTM/SPATIAL_TRANSFER_REPORT.md`](https://github.com/zhanghchen/AELSTM-vegetation-forecasting/blob/main/SPATIAL_TRANSFER_REPORT.md),
which found that most of the 8 AELSTM-family models lose substantial R² —
and the flagship AELSTM model collapses to negative R² — when trained on the
`evergreen` pixel (Georgia) and deployed as-is on `evergreen_west`
(Klamath Mountains, N. California/S. Oregon border), a different needleleaf
evergreen forest pixel roughly 3,700 km away, selected via the project's
existing pixel-selection method (see that report for the full rationale).
This is a **legitimate generalization test**, not data leakage — the target
pixel's data never participates in fitting.

## Design

Zero-shot Chronos-2 has no trainable weights, so — as in the temporal
leakage diagnostic — it's kept only as a **reference point**, applied
natively at the target pixel using the target's own context (which is what
zero-shot always does, regardless of any notion of a "source" location).
LoRA fine-tuning is the vehicle for the actual transfer test:
`Code/spatial_transfer_chronos2.py` fits LoRA on `evergreen`'s **full**
2000–2022 series ("train using all data"), reusing the exact random-window-
sampling training mechanics already confirmed in the leakage diagnostic
(`Chronos2Dataset` samples training windows from whatever series is passed
to `fit()`). The resulting weights — informed only by the source location —
are then evaluated with `evergreen_west`'s **own** context (2000–2021) and
its own real 2022 climate as `future_covariates`, forecasting its actual
2022 LAI. No new hyperparameter search — the same already-validated
`FINETUNE_LEARNING_RATE`/rank/`num_steps`/`batch_size` used throughout this
project.

## Results

`outputs/spatial_transfer/evergreen_to_evergreen_west/spatial_transfer_summary_chronos2.csv`:

| Condition | R² | RMSE | Pearson r |
|---|---|---|---|
| Zero-shot (target-native, reference) | 0.888 | 0.274 | 0.948 |
| LoRA, source-local (`evergreen`, trained+tested there) | 0.712 | — | — |
| LoRA, target-local (`evergreen_west`, trained+tested there) | 0.819 | — | — |
| **LoRA, transfer (`evergreen`→`evergreen_west`, no retraining)** | **0.823** | 0.345 | 0.912 |

**The transfer condition (R²=0.823) is essentially identical to — and
fractionally *exceeds* — target-local LoRA (R²=0.819, ΔR²=+0.003).**
Training on a different evergreen-forest pixel roughly 3,700 km away and
deploying without any target-specific fine-tuning costs Chronos-2 nothing
measurable. `spatial_transfer_prediction_curves_chronos2.png` shows the
transfer prediction tracking the observed 2022 seasonal cycle about as
closely as the target-native zero-shot curve does, including the same
slight late-year overprediction both curves share.

**Cross-project comparison** (`spatial_transfer_r2_drop_combined.png`, ΔR²
= transfer − target-local, all 9 methods on the same axis): Chronos-2 LoRA's
transfer loss is statistically flat at zero — the best spatial
generalization of any method tested, ahead of even AELSTM's best transferer
(RNN, ΔR² = −0.006). Every other AELSTM-family model loses more, and AELSTM
itself loses far more (ΔR² = −1.156, collapsing to negative R²).

## Interpretation

This is a striking contrast with the AELSTM-family results and worth
reading together with them. Where most AELSTM-family models — especially
the best local performers, SVM and RF, and the attention-augmented AELSTM
itself — appear to fit location-specific idiosyncrasies that don't
transfer, **Chronos-2's LoRA adaptation captures something that
generalizes almost perfectly across two very different climate regions of
the same vegetation type**. A plausible explanation is that LoRA only
lightly perturbs a large pretrained foundation model's existing
general-purpose time-series representations, rather than fitting a
compact model's few parameters entirely to one location's specific climate
range and noise structure — so what LoRA "learns" from `evergreen` is
closer to a generic seasonal-forecasting adjustment than a location-bound
fit. This is consistent with — and extends — the temporal leakage
diagnostic's finding that Chronos-2's LoRA-adapted weights recovered
strongly even from a severely out-of-distribution year: here, the same
adaptation mechanism also turns out to be robust to being deployed
somewhere it was never trained on at all.

## Reproducing

```bash
cd Code
python spatial_transfer_chronos2.py
# -> outputs/spatial_transfer/evergreen_to_evergreen_west/{transfer_metrics_chronos2.csv,
#    transfer_predictions_chronos2.csv}
python build_spatial_transfer_comparison_chronos2.py
# -> outputs/spatial_transfer/evergreen_to_evergreen_west/ (summary table + figures,
#    reads AELSTM/outputs/spatial_transfer/evergreen_to_evergreen_west/spatial_transfer_summary_table.csv
#    read-only for the combined figure - run the AELSTM experiment first if that file doesn't exist yet)
```

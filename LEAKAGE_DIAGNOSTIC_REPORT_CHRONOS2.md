# Leakage Diagnostic: Chronos-2 on Evergreen/2012 (Prof. Wang's follow-up, part 2)

> **⚠️ This is NOT a valid evaluation protocol.** The "leakage" condition
> below deliberately fine-tunes Chronos-2 on data that includes the year it
> is then evaluated on. This is textbook data leakage and the resulting
> scores are **not** a measure of real forecasting skill. It exists purely
> as a diagnostic to understand *why* Chronos-2 fails so badly on the
> evergreen/2012 LOYO-CV fold — nothing here should be read as, or
> substituted for, a real evaluation result. `Code/loyo_cv_chronos2.py`
> remains the project's only valid evaluation of that fold.

This is the Chronos-2 counterpart to
[`AELSTM/LEAKAGE_DIAGNOSTIC_REPORT.md`](https://github.com/zhanghchen/AELSTM-vegetation-forecasting/blob/main/LEAKAGE_DIAGNOSTIC_REPORT.md),
which ran the same diagnostic on the 8 AELSTM-family models and found that
seeing 2012 during fitting recovers most, but not all, of the lost
performance (mean R² +5.17, mean RMSE −46%) — evidence that the LOYO-CV
failure is mainly distribution shift, with a smaller model-dependent
residual gap. Prof. Wang asked for the same test on Chronos-2.

## 1. Why the AELSTM design doesn't transfer directly, and what does

Zero-shot Chronos-2 has **no trainable weights** — it's pure inference over
a frozen pretrained model. "Has it already seen 2012 during training" has no
operationalization for it: the only literal analogue would require its
forecast context to include 2012 while also forecasting 2012, which is
circular for a covariate-conditioned forecaster. Zero-shot is therefore kept
only as a **reference point** (a fresh prediction curve, no leakage variant).

LoRA fine-tuning is the only mode with trainable weights, so it's the
vehicle for this diagnostic. Two things were confirmed by reading the source
directly before writing any code (`chronos/chronos2/dataset.py` and
`chronos/chronos2/pipeline.py`), per the same practice used for
`Code/finetune_lora_improved.py`:

- **`Chronos2Dataset` in TRAIN mode samples a *random* context/target split
  point from the whole series passed to `fit()`, every step**
  (`slice_idx = np.random.randint(min_past, full_length - prediction_length
  + 1)`), not one fixed split. So whatever series is handed to `fit()` *is*
  the pool every training step's target window can be drawn from — if that
  series is extended to include 2012, a meaningful fraction of the ~1000
  training steps' target windows will land on or overlap 2012, directly
  exposing the gradient to 2012's actual LAI response.
- **`pipeline.fit()` fine-tunes a *copy* of the model and returns a new
  pipeline** (confirmed in its docstring: *"Fine-tune a copy of the current
  Chronos-2 model... and return a new pipeline"*) — calling it twice from
  the same base `pipeline` object never compounds adapters across
  conditions, so both the original and leakage LoRA runs start from
  identical pretrained weights.

## 2. Design

Three conditions, same evaluation forecast call throughout (context =
2000–2011, `future_covariates` = 2012's real observed climate, forecasting
all of 2012) — the only thing that ever changes is what data participated in
fitting:

| Condition | Training data | Trainable weights? |
|---|---|---|
| `zero_shot` | none (pure inference) | no — reference point only |
| `finetuned_lora_original` | 2000–2011 (2012 unseen) | LoRA, fit on pre-2012 only |
| `finetuned_lora_leakage` | 2000–2012 (2012 included) | LoRA, fit with 2012 in the training pool |

`finetuned_lora_original` is an exact reproduction of
`loyo_cv_chronos2.py`'s existing `finetuned_lora`/fold_2012 condition (rerun
fresh here only because that script never saved prediction curves).
`finetuned_lora_leakage` uses `run_chronos2.finetune_pipeline()`'s exact
training call, just built from the window extended through the end of 2012
instead of stopping before it (`Code/leakage_diagnostic_2012_chronos2.py:leakage_train_input()`).

**No new hyperparameter search** — both fine-tuned conditions reuse
`common_pipeline.py`'s existing, already-used `FINETUNE_LEARNING_RATE=1e-4`,
default LoRA rank/alpha, `FINETUNE_NUM_STEPS=1000`, `FINETUNE_BATCH_SIZE=32`,
exactly as `run_chronos2.finetune_pipeline()` already runs them elsewhere in
this project. This keeps the comparison clean (the only experimental
variable is "did 2012 participate in fitting") and avoids the compute cost
of a fresh search, per the explicit instruction to reuse the validated setup.

## 3 & 4. Results

`outputs/leakage_diagnostic_2012/evergreen/leakage_summary_table_chronos2.csv`:

| Condition | RMSE | MAE | R² | Pearson r | ACC |
|---|---|---|---|---|---|
| Zero-shot (reference) | 1.695 | 1.432 | −7.64 | 0.111 | −0.559 |
| LoRA, 2012 unseen | 1.758 | 1.474 | −8.29 | 0.134 | −0.626 |
| **LoRA, 2012 seen in training** | **0.705** | **0.607** | **−0.50** | **0.650** | **0.879** |

**RMSE drops 59.9% and R² improves by +7.79** once 2012 participates in LoRA
fitting — Pearson r nearly sextuples (0.13→0.65) and ACC flips from strongly
negative to strongly positive (−0.63→0.88), meaning the leaked model's
year-to-year anomaly pattern now tracks the observed anomaly, not just the
absolute level. The zero-shot and original-LoRA numbers both reproduce the
existing LOYO-CV finding closely (established values: zero_shot R²=−7.64,
finetuned_lora R²=−8.52; this fresh rerun got −7.64 and −8.29 respectively —
the small original-LoRA difference is expected run-to-run noise from
`Chronos2Dataset`'s unseeded random window sampling during training, far
smaller than the leakage effect).

**Prediction curves** (`leakage_prediction_curves_chronos2.png`) show why:
zero-shot and original-LoRA both predict a "normal" seasonal cycle peaking
near LAI≈5.4–5.6, while observed 2012 LAI stays suppressed around 2.5–3.5 —
a large, sustained overprediction all year. The leaked curve pulls down
substantially and tracks the observed drop-and-partial-recovery shape far
more closely, though a real residual gap remains through the summer months
(leaked prediction peaks near 4.4 in July vs. observed ≈3.0).
**Residuals** (`leakage_residuals_chronos2.png`) confirm the same: the
leaked condition's residuals shrink dramatically but don't fully collapse to
zero, especially April–August.

## 5. Comparison with the 8-model AELSTM leakage diagnostic

`leakage_cross_project_r2_comparison.png` puts Chronos-2 LoRA alongside all
8 AELSTM-family models on the same axes:

- **Chronos-2's original-condition failure (R²=−8.29) is the single worst
  score of all 9 methods compared this way** — even worse than RF (−7.42),
  the worst AELSTM model. This matches the already-established LOYO-CV
  finding that Chronos-2 (both variants) ranked 9th/10th at this specific
  fold.
- **Its leakage recovery (ΔR²=+7.79) is the second-largest of all 9**,
  behind only RF (+8.01), and lands its final leaked R² (−0.50) squarely in
  the middle of the AELSTM pack — statistically indistinguishable from
  BiLSTM (−0.55), GRU (−0.63), and SVM (−0.67).
- Like 7 of the 8 AELSTM models, Chronos-2's leaked R² **stays negative** —
  giving it direct access to 2012 does not make it a good in-sample fit,
  only a much less catastrophic one.

**This strengthens the same conclusion the AELSTM diagnostic reached, and
extends it to Chronos-2 specifically.** The pattern — dramatic, consistent
recovery across every architecture tested (RF, 6 neural sequence models, and
now a large pretrained transformer forecaster), but incomplete recovery
almost everywhere — is exactly the signature of a shared external cause (the
2012 drought itself being unlike anything in 2000–2011) rather than an
architecture-specific limitation. Chronos-2 being the single worst performer
in the original condition and one of the strongest recoverers under leakage
argues against "Chronos-2 specifically cannot represent this response":
given the data, it does about as well as the AELSTM-family's stronger
recurrent models (BiLSTM, GRU) — its original failure looks like a
generalization/distribution-shift problem, not a Chronos-2-specific
architectural one.

## Reproducing

```bash
cd Code
python leakage_diagnostic_2012_chronos2.py
# -> outputs/leakage_diagnostic_2012/evergreen/{leakage_diagnostic_metrics.csv,
#    leakage_diagnostic_predictions.csv}
python build_leakage_comparison_chronos2.py
# -> outputs/leakage_diagnostic_2012/evergreen/{leakage_summary_table_chronos2.csv,
#    leakage_prediction_curves_chronos2.png, leakage_residuals_chronos2.png,
#    leakage_cross_project_r2_comparison.png}
# (reads AELSTM/outputs/leakage_diagnostic_2012/evergreen/leakage_summary_table.csv
# read-only for the cross-project figure - run the AELSTM diagnostic first if
# that file doesn't exist yet)
```

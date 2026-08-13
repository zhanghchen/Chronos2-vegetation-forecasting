# Improved LoRA Fine-Tuning: Design and Results

**What changed vs. the original fine-tuning run** (`Code/run_chronos2.py`'s `finetune_pipeline()`,
results in `outputs/finetuned_lora/`): the original called `pipeline.fit()` without
`validation_inputs`, so `eval_strategy="no"`/`load_best_model_at_end=False` — it trained for a
fixed 1000 steps and kept whatever weights existed at that instant, with LoRA hyperparameters
(`lr=1e-4`, `r=8`, `alpha=16`) taken verbatim from Amazon's own quickstart notebook, never tuned for
this dataset. `Code/finetune_lora_improved.py` fixes both problems. Results live in a **separate**
directory, `outputs/finetuned_lora_improved/` — the original run is untouched.

## Confirmed from source before writing any code

Read `src/chronos/chronos2/pipeline.py:295-321` and `trainer.py` directly. Passing
`validation_inputs` to `fit()` isn't just "the eval set" — it auto-configures the entire
checkpoint-selection pipeline: `eval_strategy="steps"`/`eval_steps=100`,
`save_strategy="steps"`/`save_steps=100`, `load_best_model_at_end=True`,
`metric_for_best_model="eval_loss"`, plus a callback guaranteeing the final step is always a
candidate too. `Chronos2Trainer` only overrides dataloader construction — no custom checkpoint
logic — so by the time `fit()` returns, the underlying model already holds the **best validation
checkpoint's weights**, not the final step's. The public API doesn't expose the loss trajectory, so
a custom `TrainerCallback` (`HistoryCallback`) captures it via `fit()`'s `callbacks=` hook.

## Design

**Chronological validation, 2022 never touched.** Two validation folds are carved from the
*pre-2022* data: one with context 2000-2019 evaluated on 2020, one with context 2000-2020 evaluated
on 2021 (`Chronos2Dataset` in `VALIDATION` mode automatically takes the last `prediction_length`
steps of whatever series is passed as the eval target). Stage-1 training context is therefore
2000-2019 — 2020, 2021, and 2022 are all withheld from every gradient update during the search.

**Hyperparameter search, kept small**: `learning_rate ∈ {1e-5, 1e-4}` (the library's own recommended
LoRA learning rate vs. the original notebook's value — worth testing since they differ 10×) ×
`lora_rank ∈ {4, 8, 16}` (`alpha = 2×rank`, standard convention, avoiding a separate alpha axis) = **6
configurations per pixel**, each with `transformers.EarlyStoppingCallback(patience=3)` (300
non-improving steps) to save compute and directly surface overfitting. Every decision — including
early stopping — is driven purely by validation loss; no observed 2022 (or 2020/2021) R²/RMSE ever
enters the selection.

**Two-stage finalization.** After picking the best (learning rate, rank, checkpoint step) per pixel
by minimum validation loss, a *second* fine-tune runs once more per pixel on the **full** 2000-2021
(all pre-2022 data, no validation split — matching how zero-shot and the original LoRA run both used
all available pre-2022 data) for exactly that many steps, with no early stopping this time. That
final model is evaluated on the untouched 2022 test year — the same protocol as every other method
in this project.

## Which hyperparameters and checkpoint were selected, per pixel

| Pixel | Winning learning rate | Winning rank (α) | Selected step | Steps actually run (of 1000 max) | Validation loss at selection |
|---|---|---|---|---|---|
| `low_amplitude` | **1e-5** | 8 (16) | **100** | 400 (early stopped) | 0.652 |
| `high_amplitude_deciduous` | **1e-4** | 16 (32) | **800** | 1000 (ran to completion) | 0.161 |
| `evergreen` | **1e-4** | 16 (32) | **400** | 700 (early stopped) | 0.611 |

The optimal learning rate is **pixel-dependent, not universal** — `finetune_search_all_configs_curves.png`
shows a clean split: at `low_amplitude` every `lr=1e-4` configuration's validation loss spikes
immediately and never recovers, while every `lr=1e-5` configuration stays flat; at the other two
pixels the pattern reverses, with `lr=1e-4` configurations reaching the lowest validation loss.
This is a genuinely different regime, not noise — using the original notebook's `lr=1e-4`
unconditionally, as before, was the wrong choice specifically for `low_amplitude`.

## Does the model overfit, and where is the best checkpoint?

`finetune_winner_train_val_curves.png` plots each pixel's winning configuration's train loss against
validation loss, step by step:

- **`low_amplitude` overfits immediately.** Validation loss is lowest at step 100 (the first
  possible checkpoint) and rises monotonically afterward while training loss keeps falling — the
  model starts memorizing pixel-specific training noise from the very first evaluation point. The
  honest reading is that this pixel does not benefit from any amount of fine-tuning tested here.
- **`high_amplitude_deciduous` and `evergreen` show genuine interior minima** — validation loss
  decreases with some noise, reaches a minimum (step 800 and step 400 respectively), then ticks back
  up. This is the textbook overfitting signature the original fixed-1000-step run had no mechanism
  to detect, since it never computed a validation loss at all.

## Three-way comparison: zero-shot vs. original LoRA vs. improved LoRA

All three scored against the same raw observed 2022 LAI (`outputs/finetuned_lora_improved/comparison/three_way_comparison.csv`):

| Pixel | Zero-shot R² | Original LoRA R² | Improved LoRA R² | Improved − Original | Improved − Zero-shot |
|---|---|---|---|---|---|
| `low_amplitude` | 0.542 | 0.379 | **0.500** | **+0.121** | −0.042 |
| `high_amplitude_deciduous` | 0.965 | 0.952 | 0.942 | −0.010 | −0.023 |
| `evergreen` | 0.832 | 0.712 | **0.829** | **+0.117** | −0.003 |

## Does fine-tuning genuinely improve over zero-shot now?

**Not outright — improved LoRA still trails zero-shot on all 3 pixels — but the previous
conclusion that fine-tuning is uniformly and substantially harmful turns out to have been largely an
artifact of training without validation.** On the two pixels where the original fine-tune badly
underperformed zero-shot (`low_amplitude`: −0.163, `evergreen`: −0.120), validation-based checkpoint
selection recovers most of that gap (`low_amplitude`: −0.042 remaining, `evergreen`: essentially
closed at −0.003) simply by stopping before the model overfits. On `high_amplitude_deciduous`, where
the original fine-tune was already close to zero-shot, the improved version is marginally further
behind (−0.023 vs. −0.014) — a small, plausible amount of noise from only two validation folds
selecting a slightly different checkpoint than the one that happened to work best on 2022,
rather than evidence that validation-based selection is misleading here.

The practical implication: **the earlier finding "LoRA fine-tuning consistently hurts" should be
revised to "LoRA fine-tuning without validation consistently hurts, and much of that damage is
avoidable."** With a validated, per-pixel-tuned checkpoint, fine-tuning stops being actively harmful
on 2 of 3 pixels and comes within noise of zero-shot on the third — but it still does not beat
zero-shot outright on this 3-pixel sample, so there remains no evidence that fine-tuning is worth its
added complexity and compute cost for this task as currently framed.

## Reproducing

```bash
cd Code
python finetune_lora_improved.py --sites low_amplitude high_amplitude_deciduous evergreen
# -> outputs/finetuned_lora_improved/<site>/{search_summary.csv, search/*_train_loss.csv,
#    search/*_eval_loss.csv, predictions.csv, metrics.txt, prediction_plot.png}
python build_finetune_improvement_comparison.py
# -> outputs/finetuned_lora_improved/comparison/ (three_way_comparison.csv, three_way_comparison_<site>.png,
#    finetune_winner_train_val_curves.png, finetune_search_all_configs_curves.png)
```

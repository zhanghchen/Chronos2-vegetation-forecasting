# Advanced Chronos-2 Fine-Tuning: Can Better PEFT Methods Beat Zero-Shot?

**Question**: our earlier work showed standard LoRA fine-tuning (with and without validation-based
checkpoint selection) did not consistently beat Chronos-2 zero-shot. Does a broader, more recent set
of parameter-efficient fine-tuning (PEFT) methods change that conclusion, under our small
single-pixel vegetation LAI dataset?

**Answer, upfront: no.** Across 6 new methods, 3 pixels, and a fair, equal-sized hyperparameter
search per method, **zero-shot remains the best method overall** (mean R²=0.780 vs. the best new
method's 0.769), and **only one method/pixel combination beats zero-shot at all** (DoRA on
`evergreen`, +0.0026 — small and likely within noise). Full detail, including *why*, below.

## 1. Literature review

Searched ICLR/ICML/NeurIPS 2022–2025 plus TSFM/PEFT-specific venues, cross-checked against our
**actual installed Chronos-2 source** (`chronos/chronos2/pipeline.py`, `trainer.py`) and installed
`peft==0.17.1` — every compatibility claim below was verified against real code, not assumed.

| Method | Paper | Core idea | Trained params | Chronos-2 compatibility (verified) |
|---|---|---|---|---|
| DoRA | [Liu et al., ICML'24 Oral](https://arxiv.org/abs/2402.09353) | Decompose weight into magnitude+direction; LoRA-update direction only | LoRA A/B + magnitude vector | Public `fit()` API, `use_dora=True` flag — zero custom code |
| VeRA | [Kopiczko et al., ICLR'24](https://arxiv.org/abs/2310.11454) | One frozen shared random low-rank pair across all layers; learn only small scaling vectors | 2 vectors/layer | `peft.get_peft_model()` bypass (see §2) |
| IA3 | [Liu et al., NeurIPS'22](https://arxiv.org/abs/2205.05638) | Learned per-channel multiplicative rescaling of K/V/FFN activations | 3 vectors/targeted layer | Bypass |
| LN-Tuning | Used on Chronos in [Beyond LoRA (2409.11302)](https://arxiv.org/html/2409.11302v1) | Unfreeze only normalization affine params | Norm scale vectors only | Bypass |
| BitFit | [Zaken et al., ACL'22](https://arxiv.org/abs/2106.10199) | Unfreeze only bias terms | Bias terms only | Trivial (no library) — **architecturally near-degenerate on Chronos-2**, see §3 |
| Partial (last block) | Classical | Full-weight unfreeze of only the last transformer block | Full block weights | Trivial |

**Excluded after investigation** (not just listed): **AdaLoRA** (importance-based rank pruning needs
more gradient signal than our tiny per-pixel datasets provide, and is LoRA-shaped — would reduce
method diversity given DoRA is included); **FourierFT** (mechanically overlaps with VeRA — both are
"shared, structured, low-dimensional ΔW parameterizations" — chose VeRA for its more direct Chronos
precedent); **Prompt/Prefix tuning** (`peft`'s implementations assume a causal/seq2seq-LM
`get_input_embeddings()` interface that `Chronos2Model`, a custom patch-transformer, doesn't
implement — a real compatibility risk, not a quality judgment); **PETSA** (ICML'25 test-time
adaptation — adapts per test window with no fixed trained checkpoint, breaking comparability with our
fixed train/val/test protocol); **TimesFM in-context fine-tuning** (ICML'25 — architecture-specific to
TimesFM).

**Directly relevant prior evidence**, independent of our own results: [**Foundation Models and
Fine-Tuning** (2607.23146)](https://arxiv.org/html/2607.23146v1), evaluating **Chronos-2 itself**,
found zero-shot beats every fine-tuning strategy on *small* datasets, and full fine-tuning is
"unreliable... consistently degrading performance." [**Beyond LoRA**
(2409.11302)](https://arxiv.org/html/2409.11302v1) evaluated BitFit/LN-Tuning/VeRA/FourierFT **on
Chronos** for a small, scarce-data healthcare task and found lighter methods can match or beat LoRA
there. Both point the same direction our own results confirm below.

## 2. Implementation: how 5 of 6 methods were made to work with Chronos-2

Chronos-2's public `pipeline.fit(finetune_mode="lora", lora_config=...)` hard-types
`finetune_mode: Literal["full","lora"]` and only accepts a `LoraConfig` — but reading the source
(`pipeline.py:176-220`) confirms the actual mechanism is just `peft.get_peft_model(model,
lora_config)`, followed by `Chronos2Trainer`, a `transformers.Trainer` subclass whose *only* override
is dataloader construction (`trainer.py`) — **no LoRA-specific logic anywhere**. `Code/advanced_finetuning_core.py`
replicates `fit()`'s internals exactly (dataset construction, `TrainingArguments`, validation wiring,
the final-step-eval callback, tf32 save/restore, returning a new pipeline) but substitutes the
hardcoded LoRA step with a pluggable dispatcher — so any `peft.PeftConfig` subclass works, and results
stay directly comparable to the existing public-API-based runs. DoRA alone needed no bypass (`use_dora=True`
is just a `LoraConfig` flag).

**Architecture facts used, confirmed by direct inspection of the loaded model** (not assumed):
Chronos-2 is a **T5-style encoder**, 12 blocks (`encoder.block.0-11`), each with
`self_attention.{q,k,v,o}` and `mlp.{wi,wo}` (768-dim), plus a per-sublayer `layer_norm` and a final
`encoder.final_layer_norm`. **Attention and FFN linear layers have `bias=False`** — only the
input/output patch-embedding MLPs have bias terms (6 tensors, **8,352 params = 0.007% of the 119.5M-param
model**). This is why classic BitFit — designed for BERT-style architectures where every linear layer
has a bias — is **architecturally near-degenerate here**: it can only touch the patch embedding,
never the transformer body that actually processes the climate covariates. Reported honestly as a
near-zero-capacity control below, not hidden. Normalization params total 28,416 (37 norm modules ×
768), confirmed exactly by the smoke test's trainable-parameter count for LN-Tuning.

## 3. Experimental protocol

Identical to `finetune_lora_improved.py`'s already-validated design: chronological validation folds
(context 2000–2019→2020, context 2000–2020→2021), `EarlyStoppingCallback(patience=3)`, final refit on
full 2000–2021 at the winning config, evaluated once on real 2022 test data — **test data never
touches hyperparameter selection**. Same 3 pixels, same covariates. Every method starts from the
identical pretrained weights (`build_fresh_model()`). **Equal-sized 4-config search per method per
pixel** (no method got more tuning effort):

| Method | Grid |
|---|---|
| DoRA | lr∈{1e-5,1e-4} × rank∈{8,16} |
| VeRA | lr∈{1e-4,1e-3} × rank∈{256,1024} |
| IA3 / LN-Tuning / BitFit | lr∈{1e-4,1e-3,1e-2,1e-1} |
| Partial (last block) | lr∈{1e-6,1e-5,1e-4,1e-3} |

72 search runs + 18 final refits = 90 fine-tuning runs total, completed in **~85 minutes** on a single
A100 (recorded per-run: trainable params, wall-clock time, peak GPU memory, full train+eval loss
curves). Baselines (zero-shot, original LoRA, improved LoRA) were **not rerun** — read directly from
their existing saved results.

## 4. Final ranking table

`outputs/advanced_finetuning/final_ranking_table.csv`, sorted by mean R² across the 3 pixels:

| Method | Paper | Trainable Params | Val. Strategy | Mean R² | Mean RMSE | Mean MAE | Mean Pearson r | Train Time (s) | vs. Zero-shot | vs. Orig. LoRA | Pixels beating ZS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Zero-shot** | Ansari et al. 2025 | — | none | **0.780** | 0.305 | 0.237 | 0.891 | — | — | +0.099 | — |
| IA3 | NeurIPS'22 | 73,728 | chronological val, early stop | 0.769 | 0.330 | 0.254 | 0.885 | 41.6 | −0.011 | +0.088 | 0/3 |
| Partial (last block) | classical | 13,093,536 | same | 0.766 | 0.321 | 0.255 | 0.885 | 10.0 | −0.014 | +0.085 | 0/3 |
| DoRA | ICML'24 | 1,280,976 | same | 0.761 | 0.334 | 0.255 | 0.884 | 68.9 | −0.019 | +0.080 | **1/3** |
| LN-Tuning | Beyond-LoRA precedent | 28,416 | same | 0.760 | 0.324 | 0.252 | 0.880 | 12.8 | −0.020 | +0.079 | 0/3 |
| Improved LoRA | ICLR'22 + val. selection | — | same | 0.757 | 0.344 | 0.260 | 0.882 | — | −0.023 | +0.076 | 0/3 |
| VeRA | ICLR'24 | 98,896 | same | 0.755 | 0.326 | 0.262 | 0.884 | 16.7 | −0.025 | +0.074 | 0/3 |
| BitFit | ACL'22 | 8,352 | same | 0.683 | 0.402 | 0.310 | 0.861 | 20.5 | −0.097 | +0.002 | 0/3 |
| Original LoRA | ICLR'22, fixed step | 1,280,976 | none (fixed 1000 steps) | 0.681 | 0.381 | 0.290 | 0.834 | — | −0.099 | — | 0/3 |

Every fine-tuning method (old and new) has negative mean R² relative to zero-shot. IA3 and the
last-block-only baseline are the closest — both within ~0.01–0.02 of zero-shot on average, ahead of
improved LoRA — but neither ever actually crosses it on any pixel. **DoRA is the only method/pixel
combination to beat zero-shot at all** (evergreen, +0.0026).

`r2_by_pixel_all_methods.png` (bar chart, all 9 methods × 3 pixels vs. the zero-shot line) and
`params_vs_r2.png` (log trainable-params vs. R², colored by method, shaped by pixel) visualize this.

## 5. Failure-mode analysis

**Is performance correlated with trainable parameter count?** Weakly, and the *direction* depends on
the pixel: `evergreen` r=+0.59, `low_amplitude` r=+0.45 (more capacity mildly helps where zero-shot
has more room to improve), but `high_amplitude_deciduous` r=**−0.24** (more capacity mildly *hurts*
where zero-shot is already near-ceiling, R²=0.965). Overall pooled correlation is only +0.10 —
**parameter count is a weak, inconsistent predictor; which pixel matters far more than how much
capacity a method has.**

**Does performance depend strongly on pixel type?** Yes, dramatically — every method's R² spans
roughly 0.5 (`low_amplitude`) to 0.96 (`high_amplitude_deciduous`), a much larger range than the
spread *between methods* at any fixed pixel. This echoes the LOYO-CV and spatial-transfer studies'
recurring finding throughout this project: pixel identity dominates method choice.

**Does validation loss reliably predict test performance?** **Not always — BitFit is the clearest
counter-example we found.** On `evergreen`, BitFit's selected configuration achieved the *lowest*
validation loss of any of the 24 configurations tested across all 6 methods (eval_loss=0.562, beating
even DoRA's winning 0.615) — yet its test R² (0.587) was the *worst* result of the entire experiment.
`validation_curves_bitfit_vs_dora_evergreen.png` shows both methods' train/val curves have a normal,
unremarkable interior minimum (no dramatic train/val divergence, i.e. this is **not classic
overfitting**) — the failure only shows up in the held-out test year.

**Does the method distort the pretrained seasonal pattern?** Checked directly by comparing predicted
curves and their correlation with the zero-shot curve (`prediction_curves_evergreen.png`): BitFit's
predictions still correlate 0.96 with zero-shot's (DoRA: 0.99) — the *shape* is largely preserved, not
badly distorted. What actually happened is more specific: BitFit's mean bias (−0.39) is *worse* than
zero-shot's own (−0.21), and visually its spring green-up is more delayed than either zero-shot or
DoRA. **BitFit's single global adjustment — the only lever available to a method with no capacity in
the attention/FFN layers that process the climate covariates — moved in a direction that helped the
2020/2021 validation folds but not 2022.** This is a genuine, informative failure mode distinct from
overfitting: a low-capacity method's one available adjustment can be validation-optimal and
test-harmful simultaneously, because it has no way to represent anything more nuanced than a single
global shift.

**Are there methods that preserve zero-shot performance better even if they don't improve it?** Yes:
**IA3 (−0.011 mean) and Partial-last-block (−0.014 mean)** are the safest choices tested — both stay
close to zero-shot on average across all 3 pixels without the catastrophic single-pixel failure BitFit
shows. LN-Tuning (−0.020) is a close third. These three, notably, are also the three with the least
train/test volatility (lowest std of the delta-vs-zero-shot across pixels among the new methods).

**Methods that truly improve generalization vs. those that only fit train/val better vs. those that
mainly reduce fine-tuning's damage**: no method in this study clearly demonstrates *true* generalization
improvement (a consistent, multi-pixel win over zero-shot) — DoRA's single-pixel win is small and
unreplicated elsewhere. IA3, LN-Tuning, and Partial-last-block are best classified as **damage
reduction**: they recover most of what naive/original LoRA loses relative to zero-shot (compare their
~−0.01 to −0.02 deltas against original LoRA's −0.099) without ever converting that into a genuine
improvement. BitFit is the clearest example of a method that can look good on validation while not
translating into anything useful on test — neither improving generalization nor safely preserving it.

## 6. Answering the central question

**"Can a more advanced fine-tuning strategy consistently outperform Chronos-2 zero-shot for
vegetation LAI forecasting under limited-data conditions?" — No.** Across 6 methods spanning a wide
range of mechanisms (additive low-rank, multiplicative rescaling, bias-only, normalization-only,
shared-random-projection, and full-weight partial fine-tuning) and capacities (8K to 13M trainable
parameters), and using a fair, validation-only hyperparameter selection protocol, **not one method
consistently beat zero-shot across the 3 representative pixels**, and only a single method/pixel
combination beat it at all (DoRA on `evergreen`, by a margin small enough to plausibly be noise). This
directly corroborates independent literature evidence ([2607.23146](https://arxiv.org/html/2607.23146v1))
that Chronos-2 fine-tuning specifically struggles to beat zero-shot on small datasets, and extends our
own project's earlier LoRA-specific finding to a much broader set of adaptation mechanisms: **the
result is not specific to LoRA's particular update mechanism — it appears to be a property of
fine-tuning Chronos-2 at all on a dataset this small**, at least for single-pixel, single-target
univariate vegetation forecasting. The practical implication for this project: **zero-shot Chronos-2
remains the recommended default**; if fine-tuning must be used for some other reason (e.g. adapting
to a structurally different domain), IA3 or a last-block-only partial fine-tune are the safest choices
found here, since they lose the least relative to zero-shot and show no catastrophic single-pixel
failure.

## Deliverables

- Literature table: this report, §1.
- Implementation: `Code/advanced_finetuning_core.py` (generalized fit wrapper, all 6 methods).
- Experiment script: `Code/advanced_finetuning_experiment.py` (resumable; skips already-completed method/pixel pairs).
- Comparison/analysis: `Code/build_advanced_finetuning_comparison.py`.
- Raw results: `outputs/advanced_finetuning/advanced_finetuning_all_results.csv`, per-method
  `search_summary.csv` + per-config train/eval loss CSVs + `predictions.csv`/`metrics.txt`.
- Validation-loss curves: `outputs/advanced_finetuning/validation_curves_bitfit_vs_dora_evergreen.png`
  (plus every method/pixel's raw loss CSVs under `outputs/advanced_finetuning/<method>/<site>/search/`).
- Test prediction plots: `outputs/advanced_finetuning/prediction_curves_{evergreen,low_amplitude,high_amplitude_deciduous}.png`.
- Final comparison figures: `r2_by_pixel_all_methods.png`, `params_vs_r2.png`.
- This report.

All new output under `outputs/advanced_finetuning/` — `zero_shot/`, `finetuned_lora/`, and
`finetuned_lora_improved/` were read-only throughout and are unmodified.

## Reproducing

```bash
cd Code
python advanced_finetuning_experiment.py
# -> outputs/advanced_finetuning/<method>/<site>/{search_summary.csv, search/*.csv, predictions.csv, metrics.txt}
# resumable: rerun skips any method/pixel pair already in advanced_finetuning_all_results.csv

python build_advanced_finetuning_comparison.py
# -> outputs/advanced_finetuning/{final_ranking_table.csv, r2_by_pixel_all_methods.png,
#    params_vs_r2.png, validation_curves_bitfit_vs_dora_evergreen.png,
#    prediction_curves_<site>.png}
```

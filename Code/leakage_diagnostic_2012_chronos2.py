# Diagnostic-only experiment (NOT a valid evaluation protocol - deliberate
# data leakage), the Chronos-2 counterpart to
# ../AELSTM/Code/leakage_diagnostic_2012.py and
# ../AELSTM/LEAKAGE_DIAGNOSTIC_REPORT.md. Asks the same question for
# Chronos-2: is the evergreen/2012 LOYO-CV failure (zero_shot R2=-7.64,
# finetuned_lora R2=-8.52 - see LOYO_CV_FINDINGS.md) caused mainly by 2012
# being an unseen drought year, or by a representational limitation of
# Chronos-2 itself?
#
# Zero-shot Chronos-2 has no trainable weights - it's pure inference over a
# frozen pretrained model - so there is no meaningful way to make it "see"
# 2012 during training; it is included below only as a reference point (its
# already-established LOYO score plus a fresh prediction curve), never as a
# leakage condition. LoRA fine-tuning is the only mode with trainable
# weights, so it is the vehicle for this diagnostic, exactly as flagged as
# the natural next step in AELSTM/LEAKAGE_DIAGNOSTIC_REPORT.md.
#
# Design (mirrors the AELSTM diagnostic's logic, adapted to how Chronos-2
# LoRA fine-tuning actually samples training windows - confirmed by reading
# chronos/chronos2/dataset.py:Chronos2Dataset._construct_slice directly
# before writing this script, and chronos/chronos2/pipeline.py:fit(), which
# is documented and confirmed to "fine-tune a COPY of the current model and
# return a new pipeline" - so calling it twice from the same base `pipeline`
# object below never compounds adapters across conditions):
#
# In TRAIN mode, Chronos2Dataset samples a *random* context/target split
# point from the whole series passed to `pipeline.fit()` on every step
# (`slice_idx = np.random.randint(min_past, full_length - prediction_length
# + 1)`), not a single fixed split - so whatever series is handed to fit()
# *is* the pool every training step's target window can be drawn from.
#   ORIGINAL : fit() is given the 2000-2011 series only (exactly
#              run_chronos2.finetune_pipeline()'s existing convention, and
#              exactly what loyo_cv_chronos2.py already used for the
#              finetuned_lora/2012 LOYO fold) - 2012 can never appear as a
#              sampled target window, since it isn't part of the series at
#              all. Evaluated with context=2000-2011, future_covariates=
#              2012's real climate, forecasting all of 2012.
#   LEAKAGE  : fit() is given the 2000-2012 series (2012's actual LAI and
#              climate now part of the pool Chronos2Dataset samples random
#              training windows from) - over 1000 training steps x 32
#              samples/step, a meaningful fraction of sampled target windows
#              land on or overlap 2012 (with min_past=prediction_length=46
#              and a ~598-step series, slice_idx ranges over ~506 positions,
#              so about 1/11 of samples have >0 overlap with 2012, and the
#              gradient directly touches 2012's actual LAI response many
#              times over the course of training). Evaluated with the exact
#              SAME forecast call as ORIGINAL (context=2000-2011,
#              future_covariates=2012's real climate) - the only difference
#              between the two conditions is what the LoRA weights were fit
#              on, never what is in the evaluation context itself.
#
# Hyperparameters are NOT re-searched: both finetuned conditions reuse
# run_chronos2.finetune_pipeline()'s exact convention (lr=1e-4, LoRA
# rank=8/alpha=16 [the library's default], num_steps=1000, batch_size=32 -
# common_pipeline.py's existing FINETUNE_* constants), per the explicit
# instruction to avoid an unnecessary hyperparameter search and reuse the
# previously validated setup as much as possible. This also keeps the
# comparison clean: the only experimental variable is "did 2012 participate
# in fitting," never "were the hyperparameters different."
import time
from pathlib import Path

import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2
import loyo_cv_chronos2 as loyo

SITE = "evergreen"
LEAK_YEAR = 2012
WINDOW_YEARS = 12
WINDOW_START = LEAK_YEAR - WINDOW_YEARS  # 2000

OUTPUT_DIR = cp.OUTPUTS_ROOT / "leakage_diagnostic_2012" / SITE
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def leakage_train_input(df):
    """Same construction as run_chronos2.finetune_pipeline()'s train_input,
    but built from the window extended through the end of 2012 instead of
    stopping before it - the only thing that differs from the ORIGINAL
    condition's fine-tuning call."""
    years = df["date"].dt.year
    window_df = df[(years >= WINDOW_START) & (years <= LEAK_YEAR)]
    return {
        "target": window_df[cp.TARGET_COL].to_numpy(dtype="float32"),
        "past_covariates": {c: window_df[c].to_numpy(dtype="float32") for c in cp.FEATURE_COLS},
        "future_covariates": {c: None for c in cp.FEATURE_COLS},
    }


def run():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)
    df = cp.load_site_df(SITE)

    # Evaluation forecast call used by ALL THREE conditions below: identical
    # to loyo_cv_chronos2.py's fold_2012 condition (context=2000-2011,
    # future_covariates=2012's actual climate, forecasting all of 2012).
    input_dict, prediction_length, future_dates, ground_truth = loyo.build_chronos_inputs_loyo(
        df, LEAK_YEAR, WINDOW_START
    )
    years = df["date"].dt.year
    train_df_clim = df[(years >= WINDOW_START) & (years < LEAK_YEAR)]
    climatology = loyo.circular_doy_climatology(train_df_clim, future_dates)

    rows, pred_rows = [], []

    def score_and_save(condition, pred, elapsed):
        m = cp.compute_metrics(ground_truth, pred)
        m["ACC"] = loyo.compute_acc(ground_truth, pred, climatology)
        m.update(condition=condition, site=SITE, leak_year=LEAK_YEAR, elapsed_sec=round(elapsed, 1))
        rows.append(m)
        pred_rows.append(pd.DataFrame({
            "date": pd.to_datetime(future_dates), "observed": ground_truth, "prediction": pred,
            "residual": pred - ground_truth, "condition": condition,
        }))
        print(f"[{condition}] RMSE={m['RMSE']:.4f} R2={m['R2']:.4f} Pearson_r={m['Pearson_r']:.4f} "
              f"ACC={m['ACC']:.4f} ({elapsed:.1f}s)")

    # zero_shot: reference point only (fresh rerun for a prediction curve;
    # no training happens, so there is no leakage variant for this mode).
    t0 = time.time()
    pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    score_and_save("zero_shot", pred, time.time() - t0)

    # ORIGINAL finetuned_lora: LoRA fit on 2000-2011 only (2012 unseen).
    t0 = time.time()
    finetuned_original = rc2.finetune_pipeline(pipeline, input_dict, prediction_length,
                                                f"{SITE}_leakage_diag_original")
    pred = rc2.predict_with_pipeline(finetuned_original, input_dict, prediction_length)
    score_and_save("finetuned_lora_original", pred, time.time() - t0)

    # LEAKAGE finetuned_lora: LoRA fit on 2000-2012 (2012 seen), evaluated
    # with the exact same forecast call as above.
    train_input_leak = leakage_train_input(df)
    t0 = time.time()
    finetuned_leak = pipeline.fit(
        inputs=[train_input_leak],
        prediction_length=prediction_length,
        finetune_mode="lora",
        output_dir=cp.OUTPUTS_ROOT / "finetune_checkpoints" / f"{SITE}_leakage_diag_leakage",
        learning_rate=cp.FINETUNE_LEARNING_RATE,
        num_steps=cp.FINETUNE_NUM_STEPS,
        batch_size=cp.FINETUNE_BATCH_SIZE,
        logging_steps=100,
    )
    pred = rc2.predict_with_pipeline(finetuned_leak, input_dict, prediction_length)
    score_and_save("finetuned_lora_leakage", pred, time.time() - t0)

    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(OUTPUT_DIR / "leakage_diagnostic_metrics.csv", index=False)
    preds_df = pd.concat(pred_rows, ignore_index=True)
    preds_df.to_csv(OUTPUT_DIR / "leakage_diagnostic_predictions.csv", index=False)
    print(f"\nSaved -> {OUTPUT_DIR}")


if __name__ == "__main__":
    run()

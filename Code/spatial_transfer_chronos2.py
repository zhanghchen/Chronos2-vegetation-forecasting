# Chronos-2 counterpart to ../AELSTM/Code/spatial_transfer_experiment.py:
# Prof. Wang's follow-up "train the model using all data, then apply the
# trained model to another area (but similar plant type)?" This is a
# LEGITIMATE generalization test, not data leakage - the target pixel's data
# never participates in fitting, only in evaluation.
#
# SOURCE = "evergreen" (30.53N, 82.43W, Georgia). TARGET = "evergreen_west"
# (41.40N, 123.68W, N. California/S. Oregon border) - both needleleaf
# evergreen forest, selected via preprocessing/select_representative_pixels.py's
# existing method restricted to candidates >5 degrees from the source pixel
# (see AELSTM/Code/spatial_transfer_experiment.py's header for the full
# selection rationale).
#
# Zero-shot Chronos-2 has no trainable weights, so - exactly as in the
# temporal leakage diagnostic (leakage_diagnostic_2012_chronos2.py) - it is
# kept only as a reference point (applied natively at the target pixel,
# using the target's own context, which is what zero-shot always does
# regardless of any "source" pixel). LoRA fine-tuning is the only mode with
# trainable weights, so it is the vehicle for the actual transfer test:
# fit() is given SOURCE's full 2000-2022 series (same random-window-sampling
# mechanics as the leakage diagnostic - confirmed from
# chronos/chronos2/dataset.py before writing that script), producing
# LoRA-adapted weights informed only by the source location. Those weights
# are then evaluated with TARGET's own context (2000-2021) and TARGET's own
# real 2022 climate as future_covariates, forecasting TARGET's actual 2022
# LAI - so the model's weights come entirely from the source location, but
# every input at inference time is the target's own.
import time
from pathlib import Path

import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2

SOURCE_SITE = "evergreen"
TARGET_SITE = "evergreen_west"
TEST_YEAR = 2022

OUTPUT_DIR = cp.OUTPUTS_ROOT / "spatial_transfer" / f"{SOURCE_SITE}_to_{TARGET_SITE}"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def source_full_train_input(df_source):
    """All of source's 2000-2022 data as the fit() pool - 'train using all
    data.' Mirrors leakage_diagnostic_2012_chronos2.py's leakage_train_input,
    just using the full series instead of stopping at a leak year."""
    return {
        "target": df_source[cp.TARGET_COL].to_numpy(dtype="float32"),
        "past_covariates": {c: df_source[c].to_numpy(dtype="float32") for c in cp.FEATURE_COLS},
        "future_covariates": {c: None for c in cp.FEATURE_COLS},
    }


def run():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = rc2.get_pipeline(device)

    df_source = cp.load_site_df(SOURCE_SITE)
    df_target = cp.load_site_df(TARGET_SITE)

    # Evaluation forecast call: TARGET's own context/covariates throughout -
    # identical in form to every other single-split experiment in this
    # project (build_chronos_inputs), just with the model weights coming
    # from a different fit() call.
    input_dict, prediction_length, future_dates, ground_truth = cp.build_chronos_inputs(df_target)
    print(f"Target ({TARGET_SITE}) eval: context={len(input_dict['target'])} steps, "
          f"prediction_length={prediction_length}")

    rows, pred_rows = [], []

    def score_and_save(condition, pred, elapsed):
        m = cp.compute_metrics(ground_truth, pred)
        m.update(condition=condition, source=SOURCE_SITE, target=TARGET_SITE, elapsed_sec=round(elapsed, 1))
        rows.append(m)
        pred_rows.append(pd.DataFrame({
            "date": pd.to_datetime(future_dates), "observed": ground_truth, "prediction": pred,
            "residual": pred - ground_truth, "condition": condition,
        }))
        print(f"[{condition}] RMSE={m['RMSE']:.4f} R2={m['R2']:.4f} Pearson_r={m['Pearson_r']:.4f} "
              f"({elapsed:.1f}s)")

    # zero_shot: reference only, applied natively at target (no source
    # involved at all - included for context, not as a transfer condition).
    t0 = time.time()
    pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    score_and_save("zero_shot_target_native", pred, time.time() - t0)

    # TRANSFER: LoRA fit on SOURCE's full 2000-2022 data, evaluated on
    # TARGET's own context/covariates.
    train_input_source = source_full_train_input(df_source)
    t0 = time.time()
    finetuned_source = pipeline.fit(
        inputs=[train_input_source],
        prediction_length=prediction_length,
        finetune_mode="lora",
        output_dir=cp.OUTPUTS_ROOT / "finetune_checkpoints" / f"{SOURCE_SITE}_to_{TARGET_SITE}_transfer",
        learning_rate=cp.FINETUNE_LEARNING_RATE,
        num_steps=cp.FINETUNE_NUM_STEPS,
        batch_size=cp.FINETUNE_BATCH_SIZE,
        logging_steps=100,
    )
    pred = rc2.predict_with_pipeline(finetuned_source, input_dict, prediction_length)
    score_and_save("lora_transfer_from_source", pred, time.time() - t0)

    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(OUTPUT_DIR / "transfer_metrics_chronos2.csv", index=False)
    preds_df = pd.concat(pred_rows, ignore_index=True)
    preds_df.to_csv(OUTPUT_DIR / "transfer_predictions_chronos2.csv", index=False)
    print(f"\nSaved -> {OUTPUT_DIR}")


if __name__ == "__main__":
    run()

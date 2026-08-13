# Improved Chronos-2 LoRA fine-tuning: fixes the original finetune_pipeline()
# (run_chronos2.py), which called fit() without validation_inputs, so
# eval_strategy="no"/load_best_model_at_end=False and it simply trained for a
# fixed 1000 steps and kept the final weights, with LoRA hyperparameters
# taken verbatim from Amazon's own notebook rather than tuned for this data.
#
# Confirmed by reading src/chronos/chronos2/pipeline.py:295-321 before writing
# any of this: passing validation_inputs to fit() is not just "the eval set"
# - it auto-configures eval_strategy="steps"/eval_steps=100,
# save_strategy="steps"/save_steps=100, load_best_model_at_end=True,
# metric_for_best_model="eval_loss", plus a callback ensuring the final step
# is always evaluated/saved too. By the time fit() returns, the underlying
# model already has the *best validation checkpoint's* weights loaded, not
# the final step's - Chronos2Trainer (trainer.py) only overrides dataloader
# construction, no custom checkpoint logic. The public API doesn't expose the
# loss trajectory directly, so a custom TrainerCallback (HistoryCallback,
# below) captures it via fit()'s callbacks= parameter.
#
# Design (two stages, per pixel):
#   Stage 1 (search): train context = 2000-2019, validation = two
#   chronological folds (context ending 2020, context ending 2021 - each
#   fold's held-out target is that year's actual 45 steps, extracted
#   automatically by Chronos2Dataset in VALIDATION mode). 2022 is never
#   touched. Grid: learning_rate in {1e-5 (library's own recommended LoRA
#   default), 1e-4 (the original notebook's value)} x lora_rank in
#   {4, 8, 16} (alpha=2*rank, standard convention) = 6 configs. Early
#   stopping (patience=3 non-improving eval rounds = 300 steps) saves
#   compute and surfaces genuine overfitting. The best (lr, rank, step) per
#   pixel is chosen by minimum validation eval_loss - never by RMSE/R2 on
#   any observed value, which would leak test-like information into a
#   hyperparameter decision.
#   Stage 2 (final refit): retrain once more per pixel on the FULL
#   2000-2021 (all pre-2022 data, no validation split this time - matching
#   how zero-shot and the original LoRA run both used all pre-2022 data)
#   using the winning (lr, rank) fixed at the winning step count. This is
#   then evaluated on the untouched 2022 test year, exactly like the
#   existing zero-shot/finetuned_lora runs, and saved to a *new* directory
#   (outputs/finetuned_lora_improved/) - outputs/finetuned_lora/ (the
#   original run) is never modified.
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import EarlyStoppingCallback
from transformers.trainer_callback import TrainerCallback

import common_pipeline as cp
import plotting_utils as pu
import run_chronos2 as rc2

EARLIEST_YEAR = 2000
TRAIN_END_YEAR = 2019          # stage-1 training context: 2000-2019
VALIDATION_YEARS = [2020, 2021]  # two chronological validation folds
FINAL_TRAIN_END_YEAR = 2021    # stage-2: retrain on all pre-2022 data

SEARCH_LEARNING_RATES = [1e-5, 1e-4]
SEARCH_LORA_RANKS = [4, 8, 16]
MAX_STEPS = 1000
BATCH_SIZE = 32
EARLY_STOPPING_PATIENCE = 3   # x eval_steps=100 -> stops after 300 non-improving steps

OUTPUT_ROOT = cp.OUTPUTS_ROOT / "finetuned_lora_improved"
CHECKPOINT_ROOT = cp.OUTPUTS_ROOT / "finetune_checkpoints"  # already gitignored


def lora_config_dict(rank):
    return {
        "r": rank,
        "lora_alpha": rank * 2,
        "target_modules": [
            "self_attention.q", "self_attention.v", "self_attention.k", "self_attention.o",
            "output_patch_embedding.output_layer",
        ],
    }


class HistoryCallback(TrainerCallback):
    """Captures every logged training-loss and eval-loss point via fit()'s
    callbacks= hook, since the public API doesn't expose trainer.state
    directly."""

    def __init__(self):
        self.records = []

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        record = dict(logs)
        record["step"] = state.global_step
        self.records.append(record)


def build_input(df, start_year, end_year, target_col=cp.TARGET_COL, feature_cols=cp.FEATURE_COLS):
    years = df["date"].dt.year
    window = df[(years >= start_year) & (years <= end_year)]
    return {
        "target": window[target_col].to_numpy(dtype="float32"),
        "past_covariates": {c: window[c].to_numpy(dtype="float32") for c in feature_cols},
        # Values are unused during TRAIN/VALIDATION modes (the true future values are
        # extracted directly from the context series); only the keys matter, exactly as
        # in the original finetune_pipeline().
        "future_covariates": {c: None for c in feature_cols},
    }


def history_to_frame(history):
    df = pd.DataFrame(history)
    train = df[df["loss"].notna()][["step", "loss"]].rename(columns={"loss": "train_loss"}) if "loss" in df else pd.DataFrame(columns=["step", "train_loss"])
    eval_ = df[df["eval_loss"].notna()][["step", "eval_loss"]] if "eval_loss" in df else pd.DataFrame(columns=["step", "eval_loss"])
    return train.reset_index(drop=True), eval_.reset_index(drop=True)


def run_one_config(pipeline, train_input, validation_inputs, prediction_length, lr, rank, output_dir):
    history_cb = HistoryCallback()
    t0 = time.time()
    finetuned = pipeline.fit(
        inputs=[train_input],
        validation_inputs=validation_inputs,
        prediction_length=prediction_length,
        finetune_mode="lora",
        lora_config=lora_config_dict(rank),
        output_dir=output_dir,
        learning_rate=lr,
        num_steps=MAX_STEPS,
        batch_size=BATCH_SIZE,
        logging_steps=100,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=EARLY_STOPPING_PATIENCE), history_cb],
    )
    elapsed = time.time() - t0

    train_hist, eval_hist = history_to_frame(history_cb.records)
    if len(eval_hist) == 0:
        raise RuntimeError("No eval_loss recorded - validation_inputs wiring failed.")
    best_row = eval_hist.loc[eval_hist["eval_loss"].idxmin()]
    best_step, best_eval_loss = int(best_row["step"]), float(best_row["eval_loss"])

    return finetuned, train_hist, eval_hist, best_step, best_eval_loss, elapsed


def search_site(pipeline, df, site, prediction_length):
    train_input = build_input(df, EARLIEST_YEAR, TRAIN_END_YEAR)
    validation_inputs = [build_input(df, EARLIEST_YEAR, y) for y in VALIDATION_YEARS]

    site_dir = OUTPUT_ROOT / site / "search"
    site_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for lr in SEARCH_LEARNING_RATES:
        for rank in SEARCH_LORA_RANKS:
            tag = f"lr{lr:g}_r{rank}"
            print(f"\n--- {site} / search / {tag} ---")
            ckpt_dir = CHECKPOINT_ROOT / f"{site}_improved_search_{tag}"
            _, train_hist, eval_hist, best_step, best_eval_loss, elapsed = run_one_config(
                pipeline, train_input, validation_inputs, prediction_length, lr, rank, ckpt_dir
            )
            train_hist.to_csv(site_dir / f"{tag}_train_loss.csv", index=False)
            eval_hist.to_csv(site_dir / f"{tag}_eval_loss.csv", index=False)
            print(f"[{site}/{tag}] best_step={best_step} best_eval_loss={best_eval_loss:.5f} "
                  f"(ran {int(eval_hist['step'].max())} steps, {elapsed:.0f}s)")
            results.append({
                "site": site, "learning_rate": lr, "lora_rank": rank, "lora_alpha": rank * 2,
                "best_step": best_step, "best_eval_loss": best_eval_loss,
                "steps_run": int(eval_hist["step"].max()), "elapsed_sec": round(elapsed, 1),
            })

    results_df = pd.DataFrame(results).sort_values("best_eval_loss")
    results_df.to_csv(OUTPUT_ROOT / site / "search_summary.csv", index=False)
    print(f"\n=== {site}: search summary (sorted by validation eval_loss) ===")
    print(results_df.to_string(index=False))
    return results_df


def final_refit_and_evaluate(pipeline, df, site, winner, prediction_length):
    lr, rank, best_step = winner["learning_rate"], int(winner["lora_rank"]), int(winner["best_step"])
    print(f"\n--- {site} / stage-2 final refit: lr={lr}, rank={rank}, steps={best_step}, "
          f"training on {EARLIEST_YEAR}-{FINAL_TRAIN_END_YEAR} (all pre-2022 data) ---")

    full_input = build_input(df, EARLIEST_YEAR, FINAL_TRAIN_END_YEAR)
    ckpt_dir = CHECKPOINT_ROOT / f"{site}_improved_final"
    t0 = time.time()
    finetuned = pipeline.fit(
        inputs=[full_input],
        prediction_length=prediction_length,
        finetune_mode="lora",
        lora_config=lora_config_dict(rank),
        output_dir=ckpt_dir,
        learning_rate=lr,
        num_steps=best_step,
        batch_size=BATCH_SIZE,
        logging_steps=100,
    )
    elapsed = time.time() - t0
    print(f"[{site}] final refit done in {elapsed:.0f}s")

    input_dict, pred_len, future_dates, ground_truth = cp.build_chronos_inputs(df)
    pred = rc2.predict_with_pipeline(finetuned, input_dict, pred_len)
    metrics = cp.compute_metrics(ground_truth, pred)
    metrics.update(site=site, mode="finetuned_lora_improved", learning_rate=lr, lora_rank=rank,
                    lora_alpha=rank * 2, num_steps=best_step)

    out_dir = OUTPUT_ROOT / site
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": future_dates, "ground_truth": ground_truth, "prediction": pred}).to_csv(
        out_dir / "predictions.csv", index=False
    )
    with open(out_dir / "metrics.txt", "w") as f:
        for k, v in metrics.items():
            f.write(f"{k}: {v}\n")
    pu.plot_prediction(future_dates, ground_truth, pred,
                        f"{site} — Chronos-2 (improved LoRA fine-tuned) predicted vs. observed LAI, {cp.TEST_YEAR}",
                        out_dir, "prediction_plot", pred_color="#6A3D9A", pred_label="LoRA fine-tuned (improved)")
    print(f"[{site}] " + " ".join(f"{k}={v:.4f}" for k, v in metrics.items() if isinstance(v, float)))
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=cp.SITES)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    pipeline = rc2.get_pipeline(args.device)

    all_final_metrics = []
    for site in args.sites:
        df = cp.load_site_df(site)
        _, _, prediction_length, _ = (None, None, len(df[df["date"].dt.year == cp.TEST_YEAR]), None)

        summary_path = OUTPUT_ROOT / site / "search_summary.csv"
        if summary_path.exists():
            print(f"[{site}] search already done, loading {summary_path}")
            results_df = pd.read_csv(summary_path)
        else:
            results_df = search_site(pipeline, df, site, prediction_length)

        winner = results_df.sort_values("best_eval_loss").iloc[0]
        metrics = final_refit_and_evaluate(pipeline, df, site, winner, prediction_length)
        all_final_metrics.append(metrics)

    summary = pd.DataFrame(all_final_metrics)
    summary.to_csv(OUTPUT_ROOT / "finetuned_lora_improved_all_results.csv", index=False)
    print(f"\nSaved finetuned_lora_improved_all_results.csv to {OUTPUT_ROOT}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()

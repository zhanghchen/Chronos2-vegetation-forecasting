# Advanced Chronos-2 fine-tuning experiment: tests whether more advanced
# PEFT methods (DoRA, VeRA, IA3, LN-Tuning, BitFit, partial-last-block) can
# consistently beat zero-shot, using the exact same validated protocol as
# finetune_lora_improved.py (chronological validation folds, early
# stopping, two-stage search-then-final-refit, test set never touches
# hyperparameter selection). Every method starts from the identical
# pretrained Chronos-2 weights (advanced_finetuning_core.build_fresh_model)
# and gets an equal-sized 4-config search budget per pixel - no method
# receives more tuning effort than another.
#
# zero-shot, original LoRA, and improved LoRA are NOT rerun here - their
# already-saved results (outputs/zero_shot/, outputs/finetuned_lora/,
# outputs/finetuned_lora_improved/) are read directly for the final
# comparison. All NEW output goes to outputs/advanced_finetuning/, which
# does not exist yet and never overwrites those three directories.
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import EarlyStoppingCallback

import common_pipeline as cp
import run_chronos2 as rc2
import advanced_finetuning_core as afc

EARLIEST_YEAR = 2000
TRAIN_END_YEAR = 2019
VALIDATION_YEARS = [2020, 2021]
FINAL_TRAIN_END_YEAR = 2021
MAX_STEPS = 1000
BATCH_SIZE = 32
EARLY_STOPPING_PATIENCE = 3

# Equal-sized (4 configs/method/pixel) search grids - see
# CHRONOS2_ADVANCED_FINETUNING_REPORT.md for the rationale behind each.
SEARCH_GRIDS = {
    "dora": [{"learning_rate": lr, "rank": r} for lr in [1e-5, 1e-4] for r in [8, 16]],
    "vera": [{"learning_rate": lr, "rank": r} for lr in [1e-4, 1e-3] for r in [256, 1024]],
    "ia3": [{"learning_rate": lr} for lr in [1e-4, 1e-3, 1e-2, 1e-1]],
    "ln_tuning": [{"learning_rate": lr} for lr in [1e-4, 1e-3, 1e-2, 1e-1]],
    "bitfit": [{"learning_rate": lr} for lr in [1e-4, 1e-3, 1e-2, 1e-1]],
    "partial_last_block": [{"learning_rate": lr} for lr in [1e-6, 1e-5, 1e-4, 1e-3]],
}
METHOD_LABELS = {
    "dora": "DoRA", "vera": "VeRA", "ia3": "IA3", "ln_tuning": "LN-Tuning",
    "bitfit": "BitFit", "partial_last_block": "Partial (last block)",
}

OUTPUT_ROOT = cp.OUTPUTS_ROOT / "advanced_finetuning"
CHECKPOINT_ROOT = cp.OUTPUTS_ROOT / "finetune_checkpoints"  # already gitignored


def build_input(df, start_year, end_year, target_col=cp.TARGET_COL, feature_cols=cp.FEATURE_COLS):
    years = df["date"].dt.year
    window = df[(years >= start_year) & (years <= end_year)]
    return {
        "target": window[target_col].to_numpy(dtype="float32"),
        "past_covariates": {c: window[c].to_numpy(dtype="float32") for c in feature_cols},
        "future_covariates": {c: None for c in feature_cols},
    }


def history_to_frame(history):
    df = pd.DataFrame(history)
    train = df[df["loss"].notna()][["step", "loss"]].rename(columns={"loss": "train_loss"}) if "loss" in df else pd.DataFrame(columns=["step", "train_loss"])
    eval_ = df[df["eval_loss"].notna()][["step", "eval_loss"]] if "eval_loss" in df else pd.DataFrame(columns=["step", "eval_loss"])
    return train.reset_index(drop=True), eval_.reset_index(drop=True)


def run_one_config(pipeline, method, config, train_input, validation_inputs, prediction_length, output_dir):
    history_cb = afc.HistoryCallback()
    finetuned, n_trainable, n_total, elapsed, peak_mem = afc.fit_with_adaptation(
        pipeline, [train_input], prediction_length, method,
        rank=config.get("rank"), validation_inputs=validation_inputs,
        learning_rate=config["learning_rate"], num_steps=MAX_STEPS, batch_size=BATCH_SIZE,
        output_dir=output_dir, logging_steps=100,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=EARLY_STOPPING_PATIENCE), history_cb],
    )
    train_hist, eval_hist = history_to_frame(history_cb.records)
    if len(eval_hist) == 0:
        raise RuntimeError("No eval_loss recorded - validation_inputs wiring failed.")
    best_row = eval_hist.loc[eval_hist["eval_loss"].idxmin()]
    best_step, best_eval_loss = int(best_row["step"]), float(best_row["eval_loss"])
    return finetuned, train_hist, eval_hist, best_step, best_eval_loss, elapsed, n_trainable, n_total, peak_mem


def search_site_method(pipeline, df, site, method, prediction_length):
    train_input = build_input(df, EARLIEST_YEAR, TRAIN_END_YEAR)
    validation_inputs = [build_input(df, EARLIEST_YEAR, y) for y in VALIDATION_YEARS]

    site_dir = OUTPUT_ROOT / method / site / "search"
    site_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for config in SEARCH_GRIDS[method]:
        tag = "_".join(f"{k}{v:g}" for k, v in config.items())
        print(f"\n--- {method}/{site} / search / {tag} ---")
        ckpt_dir = CHECKPOINT_ROOT / f"{site}_advadapt_{method}_search_{tag}"
        _, train_hist, eval_hist, best_step, best_eval_loss, elapsed, n_trainable, n_total, peak_mem = run_one_config(
            pipeline, method, config, train_input, validation_inputs, prediction_length, ckpt_dir
        )
        train_hist.to_csv(site_dir / f"{tag}_train_loss.csv", index=False)
        eval_hist.to_csv(site_dir / f"{tag}_eval_loss.csv", index=False)
        print(f"[{method}/{site}/{tag}] best_step={best_step} best_eval_loss={best_eval_loss:.5f} "
              f"trainable={n_trainable} ({100*n_trainable/n_total:.4f}%) "
              f"(ran {int(eval_hist['step'].max())} steps, {elapsed:.0f}s, peak_mem={peak_mem/1e6:.0f}MB)")
        results.append({
            "site": site, "method": method, **config, "best_step": best_step, "best_eval_loss": best_eval_loss,
            "steps_run": int(eval_hist["step"].max()), "elapsed_sec": round(elapsed, 1),
            "n_trainable": n_trainable, "n_total": n_total, "peak_mem_mb": round(peak_mem / 1e6, 1),
        })

    results_df = pd.DataFrame(results).sort_values("best_eval_loss")
    results_df.to_csv(OUTPUT_ROOT / method / site / "search_summary.csv", index=False)
    print(f"\n=== {method}/{site}: search summary (sorted by validation eval_loss) ===")
    print(results_df.to_string(index=False))
    return results_df


def final_refit_and_evaluate(pipeline, df, site, method, winner, prediction_length):
    config = {k: winner[k] for k in ["learning_rate", "rank"] if k in winner and pd.notna(winner[k])}
    if "rank" in config:
        config["rank"] = int(config["rank"])
    best_step = int(winner["best_step"])
    print(f"\n--- {method}/{site} / final refit: {config}, steps={best_step}, "
          f"training on {EARLIEST_YEAR}-{FINAL_TRAIN_END_YEAR} ---")

    full_input = build_input(df, EARLIEST_YEAR, FINAL_TRAIN_END_YEAR)
    ckpt_dir = CHECKPOINT_ROOT / f"{site}_advadapt_{method}_final"
    finetuned, n_trainable, n_total, elapsed, peak_mem = afc.fit_with_adaptation(
        pipeline, [full_input], prediction_length, method, rank=config.get("rank"),
        learning_rate=config["learning_rate"], num_steps=best_step, batch_size=BATCH_SIZE,
        output_dir=ckpt_dir, logging_steps=100,
    )
    print(f"[{method}/{site}] final refit done in {elapsed:.0f}s")

    input_dict, pred_len, future_dates, ground_truth = cp.build_chronos_inputs(df)
    pred = rc2.predict_with_pipeline(finetuned, input_dict, pred_len)
    metrics = cp.compute_metrics(ground_truth, pred)
    metrics.update(site=site, method=method, mode=f"advanced_{method}", num_steps=best_step,
                    n_trainable=n_trainable, n_total=n_total, train_time_sec=round(elapsed, 1),
                    peak_mem_mb=round(peak_mem / 1e6, 1), **config)

    out_dir = OUTPUT_ROOT / method / site
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": future_dates, "ground_truth": ground_truth, "prediction": pred}).to_csv(
        out_dir / "predictions.csv", index=False
    )
    with open(out_dir / "metrics.txt", "w") as f:
        for k, v in metrics.items():
            f.write(f"{k}: {v}\n")
    print(f"[{method}/{site}] " + " ".join(f"{k}={v:.4f}" for k, v in metrics.items() if isinstance(v, float)))
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=cp.SITES)
    parser.add_argument("--methods", nargs="+", default=list(SEARCH_GRIDS), choices=list(SEARCH_GRIDS))
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    pipeline = rc2.get_pipeline(args.device)

    all_final_metrics = []
    all_final_path = OUTPUT_ROOT / "advanced_finetuning_all_results.csv"
    if all_final_path.exists():
        all_final_metrics = pd.read_csv(all_final_path).to_dict("records")
    done = {(r["method"], r["site"]) for r in all_final_metrics}

    for method in args.methods:
        for site in args.sites:
            if (method, site) in done:
                print(f"[skip] {method}/{site} already in {all_final_path}")
                continue
            df = cp.load_site_df(site)
            prediction_length = len(df[df["date"].dt.year == cp.TEST_YEAR])

            summary_path = OUTPUT_ROOT / method / site / "search_summary.csv"
            if summary_path.exists():
                print(f"[{method}/{site}] search already done, loading {summary_path}")
                results_df = pd.read_csv(summary_path)
            else:
                results_df = search_site_method(pipeline, df, site, method, prediction_length)

            winner = results_df.sort_values("best_eval_loss").iloc[0]
            metrics = final_refit_and_evaluate(pipeline, df, site, method, winner, prediction_length)
            all_final_metrics.append(metrics)

            pd.DataFrame(all_final_metrics).to_csv(all_final_path, index=False)
            print(f"[checkpoint] saved through {method}/{site}")

    summary = pd.DataFrame(all_final_metrics)
    summary.to_csv(all_final_path, index=False)
    print(f"\nSaved advanced_finetuning_all_results.csv to {OUTPUT_ROOT}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()

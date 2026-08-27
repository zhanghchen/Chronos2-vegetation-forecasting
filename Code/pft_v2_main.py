# Main driver for the PFT-v2 research loop: screens 4 candidate
# conditioning architectures (deep_mlp = original design, deep_mlp_reg =
# smaller+dropout+weight-decay, linear_mixture = per-PFT-class learned
# modulation vectors linearly combined by fractional weight - see
# pft_v2_model.py docstrings for the reasoning behind each), all on
# expanded pre-2022 temporal supervision (pft_v2_dataset.py: 8 train + 3
# val rolling one-year-ahead windows, 2010-2021). Selects the winner using
# ONLY pre-2022 validation evidence, then runs the shuffled-PFT control and
# the single final 2022 check for: zero-shot baseline, winning
# architecture (fractional), winning architecture (dominant), and the
# shuffled-PFT control (fractional). Everything is logged to
# experiment_log.md as it happens.
#
# Resumable by design (checkpoints on each stage's output files): earlier
# runs in this project have been interrupted by full environment
# teardowns even under nohup/setsid, so every stage is skipped and its
# saved result reloaded if its output already exists, rather than rerun.
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2
import pft_v2_dataset as pvd
import pft_v2_train as pvt
from pft_v2_model import Chronos2PFTModelV2

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_v2"
LOG_PATH = OUTPUT_DIR / "experiment_log.md"


def log(msg):
    print(msg)
    with open(LOG_PATH, "a") as f:
        f.write(msg + "\n")


def screen_or_load(arch, all_pixels, sel, pft_mode, device, tag):
    out_dir = OUTPUT_DIR / tag / arch
    curve_path = out_dir / "search_curve.csv"
    if curve_path.exists():
        curve = pd.read_csv(curve_path)
        if set(curve["lr"].unique()) >= set(pvt.LR_GRID):
            best_row = curve.loc[curve["val_loss"].idxmin()]
            best = {"arch": arch, "val_loss": float(best_row.val_loss), "val_r2": float(best_row.val_r2),
                    "step": int(best_row.step), "lr": float(best_row.lr), "n_params": int(best_row.n_params)}
            print(f"[skip] {tag}/{arch} already screened: {best}")
            return best
    return pvt.screen_architecture(arch, all_pixels, sel, pft_mode, device, tag=tag)


def final_refit_or_load(arch, best_cfg, all_pixels, sel, pft_mode, device, tag):
    out_dir = OUTPUT_DIR / tag / arch
    ckpt_path = out_dir / "conditioner.pt"
    if ckpt_path.exists():
        print(f"[skip] {tag}/{arch} already refit, loading checkpoint")
        pipeline = rc2.get_pipeline(device)
        conditioner = pvt.ARCHITECTURES[arch](len(pvd.PFT_CLASSES), pipeline.model.config.d_model)
        model = Chronos2PFTModelV2.from_pretrained_base(pipeline.model, conditioner).to(device)
        model.pft_conditioner.load_state_dict(torch.load(ckpt_path, map_location=device))
        model.eval()
        return model, out_dir
    return pvt.final_refit(arch, best_cfg, all_pixels, sel, pft_mode, device, tag=tag)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        with open(LOG_PATH, "w") as f:
            f.write("# PFT-v2 Experiment Log\n\n")
    log(f"\n--- resume/run at {pd.Timestamp.now()} ---")
    log(f"Train windows: {pvd.TRAIN_WINDOWS}")
    log(f"Val windows: {pvd.VAL_WINDOWS}")
    log(f"Test window (touched once, at the end): {pvd.TEST_WINDOW}\n")

    sel = pvd.load_selection_table()
    all_pixels = sel["pixel_id"].tolist()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # --- Stage 1: architecture screening (fractional PFT, pre-2022 only) ---
    summary_path = OUTPUT_DIR / "architecture_screen_summary.csv"
    if summary_path.exists():
        screen_df = pd.read_csv(summary_path)
        log("## Stage 1: loaded from checkpoint\n")
    else:
        log("## Stage 1: architecture screening (fractional PFT, pre-2022 validation only)\n")
        screen_results = []
        for arch in pvt.ARCHITECTURES:
            t0 = time.time()
            best = screen_or_load(arch, all_pixels, sel, "fractional", device, tag="screen_fractional")
            best["screen_time_sec"] = round(time.time() - t0, 1)
            screen_results.append(best)
            log(f"- **{arch}**: n_params={best['n_params']}, best val_loss={best['val_loss']:.5f}, "
                f"val_r2={best['val_r2']:.4f}, lr={best['lr']}, step={best['step']} "
                f"({best['screen_time_sec']:.0f}s)")
        screen_df = pd.DataFrame(screen_results)
        screen_df.to_csv(summary_path, index=False)

    winner = screen_df.loc[screen_df["val_loss"].idxmin()].to_dict()
    log(f"\n**Winning architecture (by pre-2022 validation loss): {winner['arch']}** "
        f"(val_loss={winner['val_loss']:.5f}, val_r2={winner['val_r2']:.4f})\n")

    # --- Stage 2: same winning architecture, dominant PFT (pre-2022 only) ---
    log("## Stage 2: winning architecture, dominant PFT (pre-2022 validation only)\n")
    dom_best = screen_or_load(winner["arch"], all_pixels, sel, "dominant", device, tag="screen_dominant")
    log(f"- dominant: val_loss={dom_best['val_loss']:.5f}, val_r2={dom_best['val_r2']:.4f}, "
        f"lr={dom_best['lr']}, step={dom_best['step']}\n")

    # --- Stage 3: shuffled-PFT control, same architecture (pre-2022 only) ---
    log("## Stage 3: shuffled-PFT control, winning architecture (pre-2022 validation only)\n")
    shuffled_sel = pvd.shuffled_pft_table(sel, seed=pvt.SEED)
    shuf_best = screen_or_load(winner["arch"], all_pixels, shuffled_sel, "fractional", device, tag="screen_shuffled")
    log(f"- shuffled: val_loss={shuf_best['val_loss']:.5f}, val_r2={shuf_best['val_r2']:.4f}, "
        f"lr={shuf_best['lr']}, step={shuf_best['step']}\n")

    # --- Stage 4: final refits (all pre-2022 windows) ---
    log("## Stage 4: final refits on all pre-2022 windows\n")
    model_real_frac, dir_real_frac = final_refit_or_load(winner["arch"], winner, all_pixels, sel, "fractional",
                                                            device, tag="final_fractional")
    model_real_dom, dir_real_dom = final_refit_or_load(winner["arch"], dom_best, all_pixels, sel, "dominant",
                                                          device, tag="final_dominant")
    model_shuf, dir_shuf = final_refit_or_load(winner["arch"], shuf_best, all_pixels, shuffled_sel, "fractional",
                                                  device, tag="final_shuffled")

    # --- Stage 5: THE SINGLE FINAL 2022 EVALUATION ---
    final_summary_path = OUTPUT_DIR / "final_2022_summary.csv"
    if final_summary_path.exists():
        log("## Stage 5: already complete (loaded from checkpoint)\n")
        print(pd.read_csv(final_summary_path).to_string(index=False))
        return

    log("## Stage 5: final, single 2022 evaluation\n")
    baseline_dir = OUTPUT_DIR / "final_baseline"
    baseline_metrics_path = baseline_dir / "metrics_test2022.csv"
    if baseline_metrics_path.exists():
        baseline_metrics = pd.read_csv(baseline_metrics_path)
        log("- baseline (zero-shot): loaded from checkpoint")
    else:
        pipeline = rc2.get_pipeline(device)
        baseline_dir.mkdir(parents=True, exist_ok=True)
        tensors, n_out, meta = pvt.build_window_tensors(all_pixels, sel, pvd.TEST_WINDOW, "baseline", device)
        with torch.no_grad():
            base_out = pipeline.model(context=tensors["context"], group_ids=tensors["group_ids"],
                                        future_covariates=tensors["future_covariates"], num_output_patches=n_out)
        is_target = tensors["is_target_row"].cpu().numpy()
        median_idx = base_out.quantile_preds.shape[1] // 2
        target_preds = base_out.quantile_preds[is_target, median_idx, :].cpu().numpy()
        rows = []
        for i, m in enumerate(meta):
            gt, pr = m["ground_truth"], target_preds[i][: len(m["ground_truth"])]
            valid = ~np.isnan(gt) & ~np.isnan(pr)
            if valid.sum() >= 3 and np.std(gt[valid]) > 0:
                metrics = cp.compute_metrics(gt[valid], pr[valid])
                metrics.update(pixel_id=m["pixel_id"])
                rows.append(metrics)
        baseline_metrics = pd.DataFrame(rows)
        baseline_metrics.to_csv(baseline_metrics_path, index=False)
        log(f"- **baseline (zero-shot)**: mean R2={baseline_metrics.R2.mean():.4f}, "
            f"mean RMSE={baseline_metrics.RMSE.mean():.4f}")

    m_frac = pvt.evaluate_on_window(model_real_frac, all_pixels, sel, "fractional", device,
                                       pvd.TEST_WINDOW, dir_real_frac, "test2022")
    log(f"- **{winner['arch']} + fractional PFT**: mean R2={m_frac.R2.mean():.4f}, "
        f"mean RMSE={m_frac.RMSE.mean():.4f}")

    m_dom = pvt.evaluate_on_window(model_real_dom, all_pixels, sel, "dominant", device,
                                      pvd.TEST_WINDOW, dir_real_dom, "test2022")
    log(f"- **{winner['arch']} + dominant PFT**: mean R2={m_dom.R2.mean():.4f}, "
        f"mean RMSE={m_dom.RMSE.mean():.4f}")

    m_shuf = pvt.evaluate_on_window(model_shuf, all_pixels, shuffled_sel, "fractional", device,
                                       pvd.TEST_WINDOW, dir_shuf, "test2022")
    log(f"- **{winner['arch']} + SHUFFLED PFT (control)**: mean R2={m_shuf.R2.mean():.4f}, "
        f"mean RMSE={m_shuf.RMSE.mean():.4f}")

    summary = pd.DataFrame([
        {"method": "baseline_zero_shot", "mean_R2": baseline_metrics.R2.mean(), "mean_RMSE": baseline_metrics.RMSE.mean()},
        {"method": f"{winner['arch']}_fractional", "mean_R2": m_frac.R2.mean(), "mean_RMSE": m_frac.RMSE.mean()},
        {"method": f"{winner['arch']}_dominant", "mean_R2": m_dom.R2.mean(), "mean_RMSE": m_dom.RMSE.mean()},
        {"method": f"{winner['arch']}_shuffled_control", "mean_R2": m_shuf.R2.mean(), "mean_RMSE": m_shuf.RMSE.mean()},
    ])
    summary.to_csv(final_summary_path, index=False)
    log("\n## Final 2022 summary\n")
    log(summary.to_string(index=False))
    log("\nDone.")


if __name__ == "__main__":
    main()

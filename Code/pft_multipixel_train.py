# Full multi-pixel PFT-conditioning experiment: trains the FiLM head
# (pft_multipixel_model.Chronos2PFTModel) on pooled batches across many
# pixels, for both PFT representations (fractional, dominant) and both
# holdout designs (A: temporal, B: spatial), then evaluates against the
# frozen zero-shot baseline (no PFT at all).
#
# Leak-free protocol (documented simplification for this first pooled
# proof-of-concept - see CHRONOS2_PFT_MULTIPIXEL_REPORT.md): rolling
# one-year-ahead training windows (context<=2018->2019, context<=2019->2020)
# provide the actual gradient signal; a held-out validation window
# (context<=2020->2021, forward-pass only, no gradients) is used to select
# the best (lr, step) via early stopping; the final refit then ALSO trains
# on the validation window (now legitimate, since its selection role is
# done) before a single, ungraded evaluation on context<=2021->2022 - the
# true test year, never touched by any gradient step in any configuration.
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2
import pft_multipixel_dataset as pmd
from pft_multipixel_model import Chronos2PFTModel

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_multipixel"
CKPT_DIR = OUTPUT_DIR / "checkpoints"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CKPT_DIR.mkdir(parents=True, exist_ok=True)

SEARCH_WINDOWS = [(2018, 2019), (2019, 2020)]
VAL_WINDOW = (2020, 2021)
FINAL_WINDOWS = SEARCH_WINDOWS + [VAL_WINDOW]
TEST_WINDOW = (2021, 2022)

LR_GRID = [1e-3, 3e-3, 1e-2]
SEARCH_STEPS = 150
EVAL_EVERY = 10
FINAL_STEPS_CAP = 300
SEED = 42


def set_seed(seed=SEED):
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def to_device(batch, device):
    return {
        "context": torch.tensor(batch["context"], device=device),
        "future_covariates": torch.tensor(batch["future_covariates"], device=device),
        "future_target": torch.tensor(batch["future_target"], device=device),
        "group_ids": torch.tensor(batch["group_ids"], device=device),
        "pft_features": torch.tensor(batch["pft_features"], device=device),
        "is_target_row": torch.tensor(batch["is_target_row"], device=device),
    }, batch["prediction_length"]


def build_window_tensors(pixel_ids, sel, window, pft_mode, device):
    context_end_year, future_year = window
    batch, meta = pmd.build_batch(pixel_ids, sel, context_end_year=context_end_year,
                                    future_year=future_year, pft_mode=pft_mode)
    tensors, pred_len = to_device(batch, device)
    n_out_patches = -(-pred_len // 16)  # output_patch_size=16, verified in pft_multipixel_model smoke test
    return tensors, pred_len, n_out_patches, meta


def run_step(model, windows_tensors, optimizer=None):
    """windows_tensors: list of (tensors, n_out_patches). Gradient-accumulates
    across all windows before a single optimizer step, so every window
    contributes equally per update."""
    total_loss = 0.0
    if optimizer is not None:
        optimizer.zero_grad()
    for tensors, n_out_patches in windows_tensors:
        _, loss = model(
            context=tensors["context"], group_ids=tensors["group_ids"],
            future_covariates=tensors["future_covariates"], future_target=tensors["future_target"],
            num_output_patches=n_out_patches, pft_features=tensors["pft_features"],
            is_target_row=tensors["is_target_row"],
        )
        loss = loss / len(windows_tensors)
        if optimizer is not None:
            loss.backward()
        total_loss += loss.item()
    if optimizer is not None:
        optimizer.step()
    return total_loss


@torch.no_grad()
def eval_window(model, tensors, n_out_patches, meta):
    """Forward-pass-only evaluation; returns per-pixel predictions (median
    quantile) + the pooled loss (used for validation/early-stopping)."""
    model.eval()
    preds, loss = model(
        context=tensors["context"], group_ids=tensors["group_ids"],
        future_covariates=tensors["future_covariates"], future_target=tensors["future_target"],
        num_output_patches=n_out_patches, pft_features=tensors["pft_features"],
        is_target_row=tensors["is_target_row"],
    )
    is_target = tensors["is_target_row"].cpu().numpy()
    median_idx = preds.shape[1] // 2  # quantiles=[0.1..0.9], middle = 0.5
    target_preds = preds[is_target, median_idx, :].cpu().numpy()
    per_pixel = []
    for i, m in enumerate(meta):
        pred = target_preds[i][: len(m["ground_truth"])]
        per_pixel.append({"pixel_id": m["pixel_id"], "dates": m["future_dates"],
                            "ground_truth": m["ground_truth"], "prediction": pred})
    return per_pixel, (loss.item() if loss is not None else None)


def search_and_refit(train_pixel_ids, sel, pft_mode, device, tag):
    set_seed()
    pipeline = rc2.get_pipeline(device)
    base_model = pipeline.model

    search_windows_tensors = [build_window_tensors(train_pixel_ids, sel, w, pft_mode, device)
                                for w in SEARCH_WINDOWS]
    search_windows_tensors = [(t, n) for (t, pl, n, m) in search_windows_tensors]
    val_tensors, val_pred_len, val_n_out, val_meta = build_window_tensors(train_pixel_ids, sel, VAL_WINDOW, pft_mode, device)

    search_results = []
    best = {"val_loss": np.inf}
    for lr in LR_GRID:
        model = Chronos2PFTModel.from_pretrained_base(base_model, pft_dim=len(pmd.PFT_CLASSES)).to(device)
        model.freeze_base()
        optimizer = torch.optim.Adam(model.pft_encoder.parameters(), lr=lr)

        curve = []
        for step in range(SEARCH_STEPS):
            model.train()
            train_loss = run_step(model, search_windows_tensors, optimizer)
            if step % EVAL_EVERY == 0 or step == SEARCH_STEPS - 1:
                _, val_loss = eval_window(model, val_tensors, val_n_out, val_meta)
                curve.append({"step": step, "train_loss": train_loss, "val_loss": val_loss})
                if val_loss < best["val_loss"]:
                    best = {"val_loss": val_loss, "lr": lr, "step": step}
        search_results.extend([{**c, "lr": lr} for c in curve])
        print(f"  [{tag}/{pft_mode}] lr={lr}: final val_loss={curve[-1]['val_loss']:.5f}, "
              f"best so far: lr={best['lr']} step={best['step']} val_loss={best['val_loss']:.5f}")

    search_df = pd.DataFrame(search_results)
    out_dir = OUTPUT_DIR / tag / pft_mode
    out_dir.mkdir(parents=True, exist_ok=True)
    search_df.to_csv(out_dir / "search_curve.csv", index=False)
    print(f"[{tag}/{pft_mode}] SELECTED: lr={best['lr']}, best_step={best['step']}, val_loss={best['val_loss']:.5f}")

    # Final refit: search windows + the validation window (now legitimate),
    # best_step (+1, since step indices are 0-based) at the selected lr.
    final_windows_tensors = search_windows_tensors + [(val_tensors, val_n_out)]
    final_model = Chronos2PFTModel.from_pretrained_base(base_model, pft_dim=len(pmd.PFT_CLASSES)).to(device)
    final_model.freeze_base()
    optimizer = torch.optim.Adam(final_model.pft_encoder.parameters(), lr=best["lr"])
    n_final_steps = min(best["step"] + 1, FINAL_STEPS_CAP)
    t0 = time.time()
    for step in range(n_final_steps):
        final_model.train()
        run_step(final_model, final_windows_tensors, optimizer)
    elapsed = time.time() - t0
    print(f"[{tag}/{pft_mode}] final refit: {n_final_steps} steps in {elapsed:.0f}s")

    torch.save(final_model.pft_encoder.state_dict(), out_dir / "pft_encoder.pt")
    with open(out_dir / "config.json", "w") as f:
        json.dump({"lr": best["lr"], "best_step": best["step"], "n_final_steps": n_final_steps,
                    "val_loss": best["val_loss"], "train_time_sec": round(elapsed, 1)}, f, indent=2)

    return final_model, out_dir


def evaluate_on_test(model, eval_pixel_ids, sel, pft_mode, device, out_dir, label):
    tensors, pred_len, n_out, meta = build_window_tensors(eval_pixel_ids, sel, TEST_WINDOW, pft_mode, device)
    per_pixel, _ = eval_window(model, tensors, n_out, meta)

    rows = []
    for p in per_pixel:
        gt, pr = p["ground_truth"], p["prediction"]
        valid = ~np.isnan(gt) & ~np.isnan(pr)
        gt_v, pr_v = gt[valid], pr[valid]
        if len(gt_v) < 3 or np.std(gt_v) == 0:
            continue
        m = cp.compute_metrics(gt_v, pr_v)
        m.update(pixel_id=p["pixel_id"])
        rows.append(m)
        pd.DataFrame({"date": p["dates"], "ground_truth": gt, "prediction": pr}).to_csv(
            out_dir / f"predictions_{label}_{p['pixel_id']}.csv", index=False
        )
    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(out_dir / f"metrics_{label}.csv", index=False)
    print(f"[{label}] mean R2={metrics_df.R2.mean():.4f}  mean RMSE={metrics_df.RMSE.mean():.4f}  "
          f"n_pixels={len(metrics_df)}")
    return metrics_df


def run_zero_shot_baseline(pixel_ids, sel, device, out_dir, label):
    """No PFT at all - the plain frozen pretrained model, no training."""
    pipeline = rc2.get_pipeline(device)
    tensors, pred_len, n_out, meta = build_window_tensors(pixel_ids, sel, TEST_WINDOW, "baseline", device)
    with torch.no_grad():
        base_out = pipeline.model(
            context=tensors["context"], group_ids=tensors["group_ids"],
            future_covariates=tensors["future_covariates"], num_output_patches=n_out,
        )
        preds = base_out.quantile_preds
    is_target = tensors["is_target_row"].cpu().numpy()
    median_idx = preds.shape[1] // 2
    target_preds = preds[is_target, median_idx, :].cpu().numpy()

    rows = []
    for i, m in enumerate(meta):
        gt = m["ground_truth"]
        pr = target_preds[i][: len(gt)]
        valid = ~np.isnan(gt) & ~np.isnan(pr)
        gt_v, pr_v = gt[valid], pr[valid]
        if len(gt_v) < 3 or np.std(gt_v) == 0:
            continue
        metrics = cp.compute_metrics(gt_v, pr_v)
        metrics.update(pixel_id=m["pixel_id"])
        rows.append(metrics)
        pd.DataFrame({"date": m["future_dates"], "ground_truth": gt, "prediction": pr}).to_csv(
            out_dir / f"predictions_{label}_{m['pixel_id']}.csv", index=False
        )
    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(out_dir / f"metrics_{label}.csv", index=False)
    print(f"[{label}] (zero-shot baseline) mean R2={metrics_df.R2.mean():.4f} n_pixels={len(metrics_df)}")
    return metrics_df


def main():
    sel = pmd.load_selection_table()
    all_pixels = sel["pixel_id"].tolist()
    spatial_train = pd.read_csv(cp.DATA_DIR / "data" / "processed" / "pft_multipixel_spatial_train.csv")["pixel_id"].tolist()
    spatial_holdout = pd.read_csv(cp.DATA_DIR / "data" / "processed" / "pft_multipixel_spatial_holdout.csv")["pixel_id"].tolist()

    device = "cuda" if torch.cuda.is_available() else "cpu"

    baseline_dir = OUTPUT_DIR / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    run_zero_shot_baseline(all_pixels, sel, device, baseline_dir, "expA_all70")
    run_zero_shot_baseline(spatial_holdout, sel, device, baseline_dir, "expB_holdout15")

    for pft_mode in ["dominant", "fractional"]:
        print(f"\n=== Experiment A (temporal holdout), {pft_mode} ===")
        model, out_dir = search_and_refit(all_pixels, sel, pft_mode, device, tag="expA_temporal")
        evaluate_on_test(model, all_pixels, sel, pft_mode, device, out_dir, "expA_all70")

        print(f"\n=== Experiment B (spatial holdout), {pft_mode} ===")
        model_b, out_dir_b = search_and_refit(spatial_train, sel, pft_mode, device, tag="expB_spatial")
        evaluate_on_test(model_b, spatial_holdout, sel, pft_mode, device, out_dir_b, "expB_holdout15")

    print("\nAll runs complete.")


if __name__ == "__main__":
    main()

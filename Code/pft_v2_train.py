# PFT-v2 research loop: screens several PFT-conditioning architectures on
# expanded pre-2022 temporal supervision (8 train / 3 val rolling windows,
# see pft_v2_dataset.py), selects the winner using ONLY pre-2022 validation
# evidence, then (and only then) runs the shuffled-PFT control and the
# single, final 2022 evaluation. Fixed seeds throughout.
import json
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2
import pft_v2_dataset as pvd
from pft_v2_model import Chronos2PFTModelV2, DeepMLPConditioner, LinearMixtureConditioner, LowRankMLPConditioner

OUTPUT_DIR = cp.OUTPUTS_ROOT / "pft_v2"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SEED = 42
WINDOWS_PER_STEP = 2  # randomly sampled from TRAIN_WINDOWS each step
SEARCH_STEPS = 200
EVAL_EVERY = 20
FINAL_STEPS_CAP = 400

ARCHITECTURES = {
    "deep_mlp": lambda pft_dim, d_model: DeepMLPConditioner(pft_dim, d_model, hidden_dim=64, dropout=0.0),
    "deep_mlp_reg": lambda pft_dim, d_model: DeepMLPConditioner(pft_dim, d_model, hidden_dim=32, dropout=0.3),
    "linear_mixture": lambda pft_dim, d_model: LinearMixtureConditioner(pft_dim, d_model),
    "low_rank": lambda pft_dim, d_model: LowRankMLPConditioner(pft_dim, d_model, rank=8, hidden_dim=16, dropout=0.1),
}
WEIGHT_DECAY = {"deep_mlp": 0.0, "deep_mlp_reg": 1e-3, "linear_mixture": 1e-4, "low_rank": 1e-3}
LR_GRID = [1e-3, 3e-3]


def set_seed(seed=SEED):
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
    batch, meta = pvd.build_batch(pixel_ids, sel, context_end_year=window[0], future_year=window[1], pft_mode=pft_mode)
    tensors, pred_len = to_device(batch, device)
    n_out_patches = -(-pred_len // 16)
    return tensors, n_out_patches, meta


def compute_step_loss(model, tensors, n_out_patches, optimizer=None):
    _, loss = model(
        context=tensors["context"], group_ids=tensors["group_ids"],
        future_covariates=tensors["future_covariates"], future_target=tensors["future_target"],
        num_output_patches=n_out_patches, pft_features=tensors["pft_features"],
        condition_rows=tensors["is_target_row"],
    )
    return loss


@torch.no_grad()
def eval_window(model, tensors, n_out_patches, meta):
    model.eval()
    preds, loss = model(
        context=tensors["context"], group_ids=tensors["group_ids"],
        future_covariates=tensors["future_covariates"], future_target=tensors["future_target"],
        num_output_patches=n_out_patches, pft_features=tensors["pft_features"],
        condition_rows=tensors["is_target_row"],
    )
    is_target = tensors["is_target_row"].cpu().numpy()
    median_idx = preds.shape[1] // 2
    target_preds = preds[is_target, median_idx, :].cpu().numpy()
    per_pixel_r2 = []
    for i, m in enumerate(meta):
        gt = m["ground_truth"]
        pr = target_preds[i][: len(gt)]
        valid = ~np.isnan(gt) & ~np.isnan(pr)
        if valid.sum() >= 3 and np.std(gt[valid]) > 0:
            ss_res = np.sum((gt[valid] - pr[valid]) ** 2)
            ss_tot = np.sum((gt[valid] - gt[valid].mean()) ** 2)
            per_pixel_r2.append(1 - ss_res / ss_tot)
    return (loss.item() if loss is not None else None), float(np.mean(per_pixel_r2)) if per_pixel_r2 else np.nan


def screen_architecture(arch_name, train_pixel_ids, sel, pft_mode, device, tag):
    set_seed()
    pipeline = rc2.get_pipeline(device)
    base_model = pipeline.model
    d_model = base_model.config.d_model

    train_tensors = {w: build_window_tensors(train_pixel_ids, sel, w, pft_mode, device) for w in pvd.TRAIN_WINDOWS}
    val_tensors = {w: build_window_tensors(train_pixel_ids, sel, w, pft_mode, device) for w in pvd.VAL_WINDOWS}

    results = []
    best_overall = {"val_loss": np.inf}
    for lr in LR_GRID:
        set_seed()
        conditioner = ARCHITECTURES[arch_name](len(pvd.PFT_CLASSES), d_model)
        model = Chronos2PFTModelV2.from_pretrained_base(base_model, conditioner).to(device)
        model.freeze_base()
        n_params = sum(p.numel() for p in model.pft_conditioner.parameters())
        optimizer = torch.optim.Adam(model.pft_conditioner.parameters(), lr=lr, weight_decay=WEIGHT_DECAY[arch_name])

        curve = []
        best = {"val_loss": np.inf}
        for step in range(SEARCH_STEPS):
            model.train()
            windows = random.sample(pvd.TRAIN_WINDOWS, WINDOWS_PER_STEP)
            optimizer.zero_grad()
            total_train_loss = 0.0
            for w in windows:
                tensors, n_out, _ = train_tensors[w]
                loss = compute_step_loss(model, tensors, n_out) / len(windows)
                loss.backward()
                total_train_loss += loss.item()
            optimizer.step()

            if step % EVAL_EVERY == 0 or step == SEARCH_STEPS - 1:
                val_losses, val_r2s = [], []
                for w in pvd.VAL_WINDOWS:
                    tensors, n_out, meta = val_tensors[w]
                    vl, vr2 = eval_window(model, tensors, n_out, meta)
                    val_losses.append(vl)
                    val_r2s.append(vr2)
                mean_val_loss = float(np.mean(val_losses))
                mean_val_r2 = float(np.mean(val_r2s))
                curve.append({"step": step, "train_loss": total_train_loss, "val_loss": mean_val_loss,
                               "val_r2": mean_val_r2})
                if mean_val_loss < best["val_loss"]:
                    best = {"val_loss": mean_val_loss, "val_r2": mean_val_r2, "step": step}

        results.extend([{**c, "lr": lr, "arch": arch_name, "n_params": n_params} for c in curve])
        print(f"  [{tag}/{arch_name}] lr={lr}: n_params={n_params} best_step={best['step']} "
              f"val_loss={best['val_loss']:.5f} val_r2={best['val_r2']:.4f}")
        if best["val_loss"] < best_overall["val_loss"]:
            best_overall = {**best, "lr": lr, "n_params": n_params}

    out_dir = OUTPUT_DIR / tag / arch_name
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(out_dir / "search_curve.csv", index=False)
    print(f"[{tag}/{arch_name}] SELECTED: lr={best_overall['lr']}, step={best_overall['step']}, "
          f"val_loss={best_overall['val_loss']:.5f}, val_r2={best_overall['val_r2']:.4f}")
    return {"arch": arch_name, **best_overall}


def final_refit(arch_name, best_cfg, train_pixel_ids, sel, pft_mode, device, tag):
    """Retrains from scratch using ALL pre-2022 windows (train+val, now
    legitimate) for best_cfg['step']+1 steps at the selected lr - the val
    windows' role as a selection signal is over once this is called."""
    set_seed()
    pipeline = rc2.get_pipeline(device)
    base_model = pipeline.model
    d_model = base_model.config.d_model

    conditioner = ARCHITECTURES[arch_name](len(pvd.PFT_CLASSES), d_model)
    model = Chronos2PFTModelV2.from_pretrained_base(base_model, conditioner).to(device)
    model.freeze_base()
    optimizer = torch.optim.Adam(model.pft_conditioner.parameters(), lr=best_cfg["lr"],
                                   weight_decay=WEIGHT_DECAY[arch_name])

    all_tensors = {w: build_window_tensors(train_pixel_ids, sel, w, pft_mode, device) for w in pvd.FINAL_WINDOWS}
    n_steps = min(best_cfg["step"] + 1, FINAL_STEPS_CAP)
    t0 = time.time()
    for step in range(n_steps):
        model.train()
        windows = random.sample(pvd.FINAL_WINDOWS, WINDOWS_PER_STEP)
        optimizer.zero_grad()
        for w in windows:
            tensors, n_out, _ = all_tensors[w]
            (compute_step_loss(model, tensors, n_out) / len(windows)).backward()
        optimizer.step()
    elapsed = time.time() - t0

    out_dir = OUTPUT_DIR / tag / arch_name
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.pft_conditioner.state_dict(), out_dir / "conditioner.pt")
    with open(out_dir / "final_config.json", "w") as f:
        json.dump({"arch": arch_name, **{k: v for k, v in best_cfg.items() if k != "arch"},
                    "n_final_steps": n_steps, "train_time_sec": round(elapsed, 1)}, f, indent=2)
    print(f"[{tag}/{arch_name}] final refit: {n_steps} steps in {elapsed:.0f}s")
    return model, out_dir


@torch.no_grad()
def evaluate_on_window(model, pixel_ids, sel, pft_mode, device, window, out_dir, label):
    tensors, n_out, meta = build_window_tensors(pixel_ids, sel, window, pft_mode, device)
    model.eval()
    preds, _ = model(
        context=tensors["context"], group_ids=tensors["group_ids"],
        future_covariates=tensors["future_covariates"], num_output_patches=n_out,
        pft_features=tensors["pft_features"], condition_rows=tensors["is_target_row"],
    )
    is_target = tensors["is_target_row"].cpu().numpy()
    median_idx = preds.shape[1] // 2
    target_preds = preds[is_target, median_idx, :].cpu().numpy()

    rows = []
    for i, m in enumerate(meta):
        gt, pr = m["ground_truth"], target_preds[i][: len(m["ground_truth"])]
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
    print(f"[{label}] mean R2={metrics_df.R2.mean():.4f} mean RMSE={metrics_df.RMSE.mean():.4f} n={len(metrics_df)}")
    return metrics_df

# Stage 2: fine-tunes Chronos-2 (shared LoRA adapter, pooled across sites)
# with a physics-informed loss built from Stage 1's frozen (Q_pi, Xi) -
# see physics_guided_lai_field.py's module docstring for the full
# adaptation story. This is the SMALL-SCALE VALIDATION pass (3 sites x 2
# LOYO folds), not the full 70-site x 11-fold comparison - checking the
# physics loss actually does something and doesn't break training before
# committing to the full run.
#
# Does NOT use Chronos2Trainer/Chronos2Dataset: that pipeline is a thin
# transformers.Trainer subclass with no custom-loss hook, and its sliding-
# window batches drop per-example site/date metadata that the physics loss
# needs (to look up lat/lon for Q_pi and the calendar time for its seasonal
# encoding). Instead calls Chronos2Model.forward() directly, bypassing the
# two no_grad layers in pipeline.predict()/predict_quantiles() (confirmed
# by reading src/chronos/chronos2/pipeline.py - predict() is @torch.no_grad
# decorated, _predict_step() ALSO wraps the model call in `with
# torch.no_grad()`), so gradients flow from the point forecast back to the
# LoRA weights. Per-example conversion via
# chronos.chronos2.dataset.validate_and_prepare_single_dict_input (the same
# function Chronos2Dataset itself uses per-row, called here one window at a
# time so site identity/dates are known to the caller).
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from peft import LoraConfig, get_peft_model

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_pipeline as cp  # noqa: E402
import run_chronos2 as rc2  # noqa: E402
import loyo_cv_chronos2 as loyo  # noqa: E402
import physics_guided_lai_field as phy  # noqa: E402 - reuses candidate_terms/CoordMLP/TERM_NAMES

# NOTE: the installed `chronos` package's function is named
# validate_and_prepare_single_dict_task (not *_input - that's what the repo
# source under /home/deh25003/chronos-forecasting/src is currently called,
# but the chronos2 conda env has a different installed build). Confirmed by
# introspecting the actual installed module rather than trusting the repo
# source read.
from chronos.chronos2 import Chronos2Model  # noqa: E402
from chronos.chronos2.dataset import validate_and_prepare_single_dict_task  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STAGE1_CKPT = ROOT / "outputs/physics_guided_lai_neuralode/stage1_neuralode_checkpoint.pt"  # v2 (Neural ODE,
# no jaggedness artifact) - see physics_guided_lai_neuralode.py. Same checkpoint dict keys as v1's
# physics_guided_lai_field.py, so no other change needed here.
OUT_DIR = ROOT / "outputs/physics_guided_chronos2_finetune"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VALIDATION_SITES = ["evergreen", "high_amplitude_deciduous", "low_amplitude"]
VALIDATION_YEARS = [2012, 2022]

CONTEXT_LENGTH = 200  # 8-day steps (~4.4 years) of context per training window
PRED_LENGTH = 20  # 8-day steps (~160 days) predicted per training window - shorter than a
# full LOYO fold (45 steps) to keep the small-scale validation pass fast
N_TRAIN_WINDOWS_PER_FOLD = 16
NUM_STEPS = 200  # small-scale validation; full run would use cp.FINETUNE_NUM_STEPS=1000
LEARNING_RATE = 1e-4  # matches cp.FINETUNE_LEARNING_RATE
BETA_PHYSICS = 0.01  # physics-loss weight during Chronos-2 fine-tuning (separate knob from
# Stage 1's own ALPHA_PHY - this one trades off against Chronos-2's native data loss, a
# very different scale of problem, so was not assumed to be the same weight).
# First small-scale validation at 0.1: physics-finetune R2 was WORSE than
# both zero-shot and plain-finetune on all 6/6 validation folds, and its
# data_loss was consistently much higher than plain-finetune's (e.g.
# evergreen/2022: 0.51 vs 0.18) - the physics term was dominating the
# gradient and pulling predictions away from fitting real data, toward
# Stage 1's own (imperfect - see its jaggedness caveat) phenology-ODE
# prior. Lowered 10x to re-test whether this is a pure weighting problem.

LORA_TARGET_MODULES = ["self_attention.q", "self_attention.v", "self_attention.k", "self_attention.o",
                        "output_patch_embedding.output_layer"]
LORA_RANK = 8

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_stage1():
    ckpt = torch.load(STAGE1_CKPT, map_location=DEVICE, weights_only=False)
    q_pi = phy.CoordMLP(ckpt["norm"]["t_mean"], ckpt["norm"]["t_std"]).to(DEVICE)
    q_pi.load_state_dict(ckpt["q_pi"])
    q_pi.eval()
    for p in q_pi.parameters():
        p.requires_grad_(False)
    site_embedding = torch.nn.Embedding(len(ckpt["site_to_idx"]), phy.SITE_EMBED_DIM).to(DEVICE)
    site_embedding.load_state_dict(ckpt["site_embedding"])
    site_embedding.eval()
    for p in site_embedding.parameters():
        p.requires_grad_(False)
    xi = ckpt["xi"].to(DEVICE)
    return q_pi, site_embedding, xi, ckpt["site_to_idx"], ckpt["norm"], ckpt["climate_mean"], ckpt["climate_std"]


def build_training_windows(df, site, window_start_year, test_year, rng):
    """Mirrors loyo.build_chronos_inputs_loyo's train/test year split (no
    leakage across test_year), but instead of ONE context->test_year window,
    samples N_TRAIN_WINDOWS_PER_FOLD random (context, target) windows from
    WITHIN the pre-test-year history for Chronos-2 fine-tuning examples."""
    train_df = df[(df["date"].dt.year >= window_start_year) & (df["date"].dt.year < test_year)].reset_index(drop=True)
    windows = []
    max_start = len(train_df) - CONTEXT_LENGTH - PRED_LENGTH
    if max_start < 1:
        return windows
    starts = rng.integers(0, max_start, size=min(N_TRAIN_WINDOWS_PER_FOLD, max_start))
    for s in starts:
        ctx = train_df.iloc[s:s + CONTEXT_LENGTH]
        tgt = train_df.iloc[s + CONTEXT_LENGTH:s + CONTEXT_LENGTH + PRED_LENGTH]
        windows.append((ctx, tgt))
    return windows


def make_model_inputs(ctx, tgt, device):
    raw = {
        "target": ctx[cp.TARGET_COL].to_numpy(dtype="float32"),
        "past_covariates": {c: ctx[c].to_numpy(dtype="float32") for c in cp.FEATURE_COLS},
        "future_covariates": {c: tgt[c].to_numpy(dtype="float32") for c in cp.FEATURE_COLS},
    }
    context, future_cov, n_targets, n_covariates, n_future_covariates = validate_and_prepare_single_dict_task(
        raw, idx=0, prediction_length=len(tgt))
    return context.to(device=device, dtype=torch.float32), future_cov.to(device=device, dtype=torch.float32), n_targets


def physics_rhs(lai_seq, tgt_df, site, site_to_idx, norm, climate_mean, climate_std, q_pi, site_embedding, xi):
    """Phi(LAI, climate).Xi + Q_pi at each step of tgt_df, using Stage 1's
    frozen Q_pi/Xi - matches physics_guided_lai_field.py's candidate_terms
    exactly (same term order/definitions), so this is a direct reuse of the
    Stage 1 physics, not a re-derivation."""
    t_years = (tgt_df["date"] - pd.Timestamp("2000-01-01")).dt.days / 365.25
    t_n = ((t_years - norm["t_mean"]) / norm["t_std"]).to_numpy(dtype="float32")
    lat_n = (tgt_df["lat"].iloc[0] - norm["lat_mean"]) / (norm["lat_std"] + 1e-8)
    lon_n = (tgt_df["lon"].iloc[0] - norm["lon_mean"]) / (norm["lon_std"] + 1e-8)
    coords = torch.tensor(np.stack([np.full_like(t_n, lat_n), np.full_like(t_n, lon_n), t_n], axis=1),
                           dtype=torch.float32, device=DEVICE)
    site_idx = torch.full((len(t_n),), site_to_idx[site], device=DEVICE)
    embed = site_embedding(site_idx)

    smoothed_cols = [f"{c}_smooth" for c in cp.FEATURE_COLS]
    climate_raw = tgt_df[smoothed_cols].to_numpy(dtype="float32")
    climate_n = (climate_raw - climate_mean) / climate_std
    climate_t = torch.tensor(climate_n, dtype=torch.float32, device=DEVICE)

    phi = phy.candidate_terms(lai_seq, climate_t)
    q_val = q_pi(coords, embed)
    return (phi * xi).sum(dim=1) + q_val


def run_condition(pipeline_model, df, site, test_year, window_start, use_physics,
                   q_pi, site_embedding, xi, site_to_idx, norm, climate_mean, climate_std, rng):
    model = get_peft_model(phy_build_fresh_model(pipeline_model), LoraConfig(
        r=LORA_RANK, lora_alpha=LORA_RANK * 2, target_modules=LORA_TARGET_MODULES)).to(DEVICE)
    model.train()
    qlevels = model.base_model.model.chronos_config.quantiles
    assert 0.5 in qlevels, f"checkpoint has no median quantile level: {qlevels}"
    median_idx = qlevels.index(0.5)
    output_patch_size = model.base_model.model.chronos_config.output_patch_size
    num_output_patches = -(-PRED_LENGTH // output_patch_size)  # ceil div

    windows = build_training_windows(df, site, window_start, test_year, rng)
    if not windows:
        return None, []

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LEARNING_RATE)
    loss_history = []
    t0 = time.time()
    for step in range(NUM_STEPS):
        ctx, tgt = windows[step % len(windows)]
        context, future_cov, n_targets = make_model_inputs(ctx, tgt, DEVICE)
        group_ids = torch.zeros(context.shape[0], dtype=torch.long, device=DEVICE)
        out = model(context=context, group_ids=group_ids, future_covariates=future_cov,
                    num_output_patches=num_output_patches)
        pred = out.quantile_preds[:n_targets, median_idx, :len(tgt)].squeeze(0)

        target_t = torch.tensor(tgt[cp.TARGET_COL].to_numpy(dtype="float32"), device=DEVICE)
        data_loss = ((pred - target_t) ** 2).mean()

        if use_physics:
            dt_years = 8.0 / 365.25  # 8-day composite step
            dlai_dt = (pred[2:] - pred[:-2]) / (2 * dt_years)  # central difference, interior points
            rhs = physics_rhs(pred, tgt, site, site_to_idx, norm, climate_mean, climate_std,
                               q_pi, site_embedding, xi)[1:-1]
            phy_loss = ((dlai_dt - rhs) ** 2).mean()
            loss = data_loss + BETA_PHYSICS * phy_loss
        else:
            phy_loss = torch.zeros(())
            loss = data_loss

        opt.zero_grad()
        loss.backward()
        opt.step()
        loss_history.append(dict(step=step, data_loss=data_loss.item(), phy_loss=phy_loss.item()))

    print(f"    [{'physics' if use_physics else 'plain'}] {NUM_STEPS} steps in {time.time()-t0:.0f}s, "
          f"final data_loss={loss_history[-1]['data_loss']:.4f} phy_loss={loss_history[-1]['phy_loss']:.4f}")

    from chronos.chronos2 import Chronos2Pipeline
    model.eval()
    merged = model.merge_and_unload() if hasattr(model, "merge_and_unload") else model
    return Chronos2Pipeline(model=merged), loss_history


def phy_build_fresh_model(pipeline_model):
    from copy import deepcopy
    config = deepcopy(pipeline_model.config)
    model = Chronos2Model(config).to(pipeline_model.device)
    model.load_state_dict(pipeline_model.state_dict())
    return model


def evaluate_fold(pipeline, df, site, test_year, window_start):
    input_dict, prediction_length, future_dates, ground_truth = loyo.build_chronos_inputs_loyo(
        df, test_year, window_start)
    pred = rc2.predict_with_pipeline(pipeline, input_dict, prediction_length)
    from sklearn.metrics import r2_score
    return r2_score(ground_truth, pred)


def main():
    base_pipeline = rc2.get_pipeline(DEVICE)
    q_pi, site_embedding, xi, site_to_idx, norm, climate_mean, climate_std = load_stage1()
    rng = np.random.default_rng(0)

    rows = []
    for site in VALIDATION_SITES:
        df = cp.load_site_df(site)
        # Stage 1 (physics_guided_lai_field.py / physics_guided_lai_neuralode.py)
        # trained Xi/Q_pi against SMOOTHED climate (trailing rolling mean,
        # phy.CLIMATE_SMOOTH_WINDOW) - physics_rhs must use the same
        # smoothed columns, or Phi/Xi are evaluated on a different feature
        # distribution than they were fit on.
        smoothed_cols = [f"{c}_smooth" for c in cp.FEATURE_COLS]
        df[smoothed_cols] = df[cp.FEATURE_COLS].rolling(phy.CLIMATE_SMOOTH_WINDOW, min_periods=1).mean()
        for test_year in VALIDATION_YEARS:
            window_start = test_year - loyo.WINDOW_YEARS
            print(f"\n=== {site} / test_year={test_year} ===")

            zero_shot_r2 = evaluate_fold(base_pipeline, df, site, test_year, window_start)
            print(f"    zero-shot R2={zero_shot_r2:.4f}")

            plain_pipeline, plain_hist = run_condition(
                base_pipeline.model, df, site, test_year, window_start, False,
                q_pi, site_embedding, xi, site_to_idx, norm, climate_mean, climate_std, rng)
            plain_r2 = evaluate_fold(plain_pipeline, df, site, test_year, window_start) if plain_pipeline else np.nan

            phys_pipeline, phys_hist = run_condition(
                base_pipeline.model, df, site, test_year, window_start, True,
                q_pi, site_embedding, xi, site_to_idx, norm, climate_mean, climate_std, rng)
            phys_r2 = evaluate_fold(phys_pipeline, df, site, test_year, window_start) if phys_pipeline else np.nan

            print(f"    plain-finetune R2={plain_r2:.4f}  physics-finetune R2={phys_r2:.4f}")
            rows.append(dict(site=site, test_year=test_year, zero_shot_R2=zero_shot_r2,
                              plain_finetune_R2=plain_r2, physics_finetune_R2=phys_r2))

            pd.DataFrame(plain_hist).to_csv(OUT_DIR / f"{site}_{test_year}_plain_history.csv", index=False)
            pd.DataFrame(phys_hist).to_csv(OUT_DIR / f"{site}_{test_year}_physics_history.csv", index=False)

    results = pd.DataFrame(rows)
    results.to_csv(OUT_DIR / "validation_results.csv", index=False)
    print("\n=== Validation summary ===")
    print(results.to_string(index=False))


if __name__ == "__main__":
    main()

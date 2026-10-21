# Stage 2 using Prof. Wang's exact logistic growth-mortality equation
# (see Code/physics_guided_phenology_equation.py), superseding
# physics_guided_chronos2_finetune.py's small-scale validation, which used
# the earlier ad hoc linear-Xi equation and showed no consistent
# improvement over plain fine-tuning. Same custom training loop/rationale
# (no Chronos2Trainer - no custom-loss hook, drops site/date metadata the
# physics loss needs; calls Chronos2Model.forward() directly to get
# gradients past the two no_grad layers in pipeline.predict()) - only the
# physics RHS changes: r_net(T,PAR).V.(1-V/k_net(P,SM,VPD)) -
# m_net(SPEI,T_freeze).V + Q_pi, using Stage 1's frozen networks instead
# of a linear candidate-term library.
#
# Expanded validation scope vs. the earlier pass: all 11 LOYO years
# (2012-2022) for the same 3 original project sites (33 folds instead of
# 6), to get a more convincing sample before concluding anything about
# whether this equation's fine-tuning helps.
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from peft import LoraConfig, get_peft_model
from sklearn.metrics import r2_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_pipeline as cp  # noqa: E402
import run_chronos2 as rc2  # noqa: E402
import loyo_cv_chronos2 as loyo  # noqa: E402
import physics_guided_phenology_equation as phen  # noqa: E402 - reuses SubFunc/KNet/CoordEmbed/ODEFunc-style RHS

from chronos.chronos2 import Chronos2Model  # noqa: E402
from chronos.chronos2.dataset import validate_and_prepare_single_dict_task  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STAGE1_CKPT = ROOT / "outputs/physics_guided_phenology_lai/checkpoint.pt"
SITES_DIR = ROOT / "data/processed/sites_phenology"  # superset of cp.load_site_df's columns
# (adds PAR/T_freeze/SM_proxy/SPEI_proxy/pet) - needed for the physics loss, not for Chronos-2's
# own inputs (which still only use cp.FEATURE_COLS, unchanged).
OUT_DIR = ROOT / "outputs/physics_guided_chronos2_finetune_phenology"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VALIDATION_SITES = ["evergreen", "high_amplitude_deciduous", "low_amplitude"]
VALIDATION_YEARS = loyo.FOLD_TEST_YEARS  # all 11 (2012-2022), not just 2 - see module docstring

CONTEXT_LENGTH = 200
PRED_LENGTH = 20
N_TRAIN_WINDOWS_PER_FOLD = 16
NUM_STEPS = 200
LEARNING_RATE = 1e-4
BETA_PHYSICS = 0.001  # calibrated via smoke test on evergreen/2022: 0.01 gave phy_loss~30 (physics dominated, hurt R2); 0.001 gave the most balanced result among the weights tried. Fixed BEFORE the full 33-fold run, not re-tuned per-fold.
# re-checked empirically (not assumed) via a smoke test before the full run - see run log.

LORA_TARGET_MODULES = ["self_attention.q", "self_attention.v", "self_attention.k", "self_attention.o",
                        "output_patch_embedding.output_layer"]
LORA_RANK = 8

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_stage1():
    ckpt = torch.load(STAGE1_CKPT, map_location=DEVICE, weights_only=False)
    norm = ckpt["norm"]
    r_net = phen.SubFunc().to(DEVICE); r_net.load_state_dict(ckpt["r_net"]); r_net.eval()
    k_net = phen.KNet().to(DEVICE); k_net.load_state_dict(ckpt["k_net"]); k_net.eval()
    m_net = phen.SubFunc().to(DEVICE); m_net.load_state_dict(ckpt["m_net"]); m_net.eval()
    q_pi = phen.CoordEmbed(norm["t_mean"], norm["t_std"]).to(DEVICE)
    q_pi.load_state_dict(ckpt["q_pi"]); q_pi.eval()
    site_embedding = torch.nn.Embedding(len(ckpt["site_to_idx"]), phen.SITE_EMBED_DIM).to(DEVICE)
    site_embedding.load_state_dict(ckpt["site_embedding"]); site_embedding.eval()
    for net in (r_net, k_net, m_net, q_pi, site_embedding):
        for p in net.parameters():
            p.requires_grad_(False)
    return r_net, k_net, m_net, q_pi, site_embedding, ckpt["site_to_idx"], norm


def build_training_windows(df, site, window_start_year, test_year, rng):
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


def physics_rhs(v_seq, tgt_df, site, site_to_idx, norm, r_net, k_net, m_net, q_pi, site_embedding):
    """dV/dt = r(T,PAR).V.(1-V/K(P,SM,VPD)) - m(SPEI,T_freeze).V + Q_pi, evaluated
    at tgt_df's dates with Stage 1's frozen networks - direct reuse, not a re-derivation."""
    t_years = (tgt_df["date"] - pd.Timestamp("2000-01-01")).dt.days / 365.25
    t_n = ((t_years - norm["t_mean"]) / norm["t_std"]).to_numpy(dtype="float32")
    lat_n_val = (tgt_df["lat"].iloc[0] - norm["lat_mean"]) / (norm["lat_std"] + 1e-8)
    lon_n_val = (tgt_df["lon"].iloc[0] - norm["lon_mean"]) / (norm["lon_std"] + 1e-8)
    coords = torch.tensor(np.stack([np.full_like(t_n, lat_n_val), np.full_like(t_n, lon_n_val), t_n], axis=1),
                           dtype=torch.float32, device=DEVICE)
    site_idx = torch.full((len(t_n),), site_to_idx[site], device=DEVICE)
    embed = site_embedding(site_idx)

    def std(col, key):
        return torch.tensor(((tgt_df[col] - norm[f"{key}_mean"]) / norm[f"{key}_std"]).to_numpy(dtype="float32"),
                             device=DEVICE)

    T = torch.tensor((((tgt_df["tmmx"] + tgt_df["tmmn"]) / 2 - norm["T_mean"]) / norm["T_std"]).to_numpy(
        dtype="float32"), device=DEVICE)
    PAR = std("PAR", "PAR")
    P = std("pr", "P")
    SM = std("SM_proxy", "SM")
    VPD = std("vpd", "VPD")
    SPEI = std("SPEI_proxy", "SPEI")
    Tfz = std("T_freeze", "Tfz")

    r = r_net(T, PAR)
    K = k_net(P, SM, VPD)
    m = m_net(SPEI, Tfz)
    q_val = q_pi(coords, embed)
    v = v_seq.clamp(min=0.0, max=100.0)
    return r * v * (1 - v / (K + 1e-6)) - m * v + q_val


def run_condition(pipeline_model, df, site, test_year, window_start, use_physics,
                   r_net, k_net, m_net, q_pi, site_embedding, site_to_idx, norm, rng):
    model = get_peft_model(phy_build_fresh_model(pipeline_model), LoraConfig(
        r=LORA_RANK, lora_alpha=LORA_RANK * 2, target_modules=LORA_TARGET_MODULES)).to(DEVICE)
    model.train()
    qlevels = model.base_model.model.chronos_config.quantiles
    assert 0.5 in qlevels, f"checkpoint has no median quantile level: {qlevels}"
    median_idx = qlevels.index(0.5)
    output_patch_size = model.base_model.model.chronos_config.output_patch_size
    num_output_patches = -(-PRED_LENGTH // output_patch_size)

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
            dt_years = 8.0 / 365.25
            dv_dt = (pred[2:] - pred[:-2]) / (2 * dt_years)
            rhs = physics_rhs(pred, tgt, site, site_to_idx, norm, r_net, k_net, m_net, q_pi, site_embedding)[1:-1]
            phy_loss = ((dv_dt - rhs) ** 2).mean()
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
    return r2_score(ground_truth, pred)


def main():
    base_pipeline = rc2.get_pipeline(DEVICE)
    r_net, k_net, m_net, q_pi, site_embedding, site_to_idx, norm = load_stage1()
    rng = np.random.default_rng(0)

    rows = []
    for site in VALIDATION_SITES:
        df = pd.read_csv(SITES_DIR / f"{site}.csv", parse_dates=["date"])
        for test_year in VALIDATION_YEARS:
            window_start = test_year - loyo.WINDOW_YEARS
            print(f"\n=== {site} / test_year={test_year} ===")

            zero_shot_r2 = evaluate_fold(base_pipeline, df, site, test_year, window_start)
            print(f"    zero-shot R2={zero_shot_r2:.4f}")

            plain_pipeline, plain_hist = run_condition(
                base_pipeline.model, df, site, test_year, window_start, False,
                r_net, k_net, m_net, q_pi, site_embedding, site_to_idx, norm, rng)
            plain_r2 = evaluate_fold(plain_pipeline, df, site, test_year, window_start) if plain_pipeline else np.nan

            phys_pipeline, phys_hist = run_condition(
                base_pipeline.model, df, site, test_year, window_start, True,
                r_net, k_net, m_net, q_pi, site_embedding, site_to_idx, norm, rng)
            phys_r2 = evaluate_fold(phys_pipeline, df, site, test_year, window_start) if phys_pipeline else np.nan

            print(f"    plain-finetune R2={plain_r2:.4f}  physics-finetune R2={phys_r2:.4f}")
            rows.append(dict(site=site, test_year=test_year, zero_shot_R2=zero_shot_r2,
                              plain_finetune_R2=plain_r2, physics_finetune_R2=phys_r2))
            pd.DataFrame(rows).to_csv(OUT_DIR / "validation_results.csv", index=False)  # checkpoint every fold

    results = pd.DataFrame(rows)
    results.to_csv(OUT_DIR / "validation_results.csv", index=False)
    print("\n=== Validation summary ===")
    print(results.to_string(index=False))
    print(f"\nmean: zero-shot={results.zero_shot_R2.mean():.4f} plain={results.plain_finetune_R2.mean():.4f} "
          f"physics={results.physics_finetune_R2.mean():.4f}")
    print(f"median: zero-shot={results.zero_shot_R2.median():.4f} plain={results.plain_finetune_R2.median():.4f} "
          f"physics={results.physics_finetune_R2.median():.4f}")
    n_phys_best = ((results.physics_finetune_R2 > results.zero_shot_R2) &
                   (results.physics_finetune_R2 > results.plain_finetune_R2)).sum()
    print(f"physics-finetune beats BOTH other conditions in {n_phys_best}/{len(results)} folds")


if __name__ == "__main__":
    main()

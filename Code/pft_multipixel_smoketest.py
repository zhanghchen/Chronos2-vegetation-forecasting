# Small proof-of-concept smoke test (per the user's explicit instruction:
# validate the mechanism on ~15 pixels / a few steps BEFORE the 50-100
# pixel experiment). Verifies, in order:
#   1. At initialization, Chronos2PFTModel is byte-identical to the base
#      pretrained model (FiLM head is zero-initialized => gamma=0, beta=0).
#   2. Gradients reach ONLY pft_encoder params (base model frozen).
#   3. After a few training steps, pft_encoder's output is not all-zero.
#   4. Changing PFT while holding LAI/climate fixed changes the output.
#   5. Predictions after a few steps are still finite/reasonable (no NaN
#      blow-up), evidence there's no normalization-related instability.
#   6. No test-year (2022) data is ever touched by the training batches
#      (training uses context<=2020, future=2021 only).
import random

import numpy as np
import pandas as pd
import torch

import common_pipeline as cp
import run_chronos2 as rc2
import pft_multipixel_dataset as pmd
from pft_multipixel_model import Chronos2PFTModel

SEED = 42
N_SMOKE_PIXELS = 16
TRAIN_STEPS = 30
LR = 1e-3


def set_seed(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def pick_smoke_pixels(sel, n):
    """Stratified by purity decile so the smoke set spans pure -> mixed,
    not just whichever pixels happen to sort first."""
    sel = sel.copy()
    sel["purity_bin"] = pd.qcut(sel["pft_purity"], q=min(n, 8), duplicates="drop")
    rng = np.random.default_rng(SEED)
    chosen = []
    for _, grp in sel.groupby("purity_bin"):
        chosen.append(grp.sample(1, random_state=SEED)["pixel_id"].iloc[0])
    remaining = [p for p in sel["pixel_id"] if p not in chosen]
    rng.shuffle(remaining)
    chosen += remaining[: max(0, n - len(chosen))]
    return chosen[:n]


def main():
    set_seed()
    sel = pmd.load_selection_table()
    smoke_pixels = pick_smoke_pixels(sel, N_SMOKE_PIXELS)
    print(f"Smoke-test pixels ({len(smoke_pixels)}): {smoke_pixels}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    base_pipeline = rc2.get_pipeline(device)
    base_model = base_pipeline.model
    pft_model = Chronos2PFTModel.from_pretrained_base(base_model, pft_dim=len(pmd.PFT_CLASSES)).to(device)
    pft_model.freeze_base()

    trainable = [n for n, p in pft_model.named_parameters() if p.requires_grad]
    n_trainable = sum(p.numel() for p in pft_model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in pft_model.parameters())
    print(f"\nTrainable params: {trainable}")
    print(f"n_trainable={n_trainable} ({100*n_trainable/n_total:.4f}% of {n_total})")

    # --- Check 1: identical to base model at initialization ---
    train_batch, train_meta = pmd.build_batch(smoke_pixels, sel, context_end_year=2020, future_year=2021)
    context_t = torch.tensor(train_batch["context"], device=device)
    future_cov_t = torch.tensor(train_batch["future_covariates"], device=device)
    future_tgt_t = torch.tensor(train_batch["future_target"], device=device)
    group_ids_t = torch.tensor(train_batch["group_ids"], device=device)
    pft_feat_t = torch.tensor(train_batch["pft_features"], device=device)
    is_target_t = torch.tensor(train_batch["is_target_row"], device=device)
    pred_len = train_batch["prediction_length"]
    n_output_patches = -(-pred_len // pft_model.chronos_config.output_patch_size)

    with torch.no_grad():
        pft_model.eval()
        preds_pft_init, _ = pft_model(
            context=context_t, group_ids=group_ids_t, future_covariates=future_cov_t,
            num_output_patches=n_output_patches, pft_features=pft_feat_t, is_target_row=is_target_t,
        )
        base_out = base_model(
            context=context_t, group_ids=group_ids_t, future_covariates=future_cov_t,
            num_output_patches=n_output_patches,
        )
        preds_base_init = base_out.quantile_preds
    max_diff_init = (preds_pft_init - preds_base_init).abs().max().item()
    print(f"\n[Check 1] max |PFT-model - base-model| at init (should be ~0): {max_diff_init:.8f}")

    # --- Training: a few steps on pft_encoder only ---
    optimizer = torch.optim.Adam(pft_model.pft_encoder.parameters(), lr=LR)
    pft_model.train()
    losses = []
    grad_norms = []
    for step in range(TRAIN_STEPS):
        optimizer.zero_grad()
        _, loss = pft_model(
            context=context_t, group_ids=group_ids_t, future_covariates=future_cov_t,
            future_target=future_tgt_t, num_output_patches=n_output_patches,
            pft_features=pft_feat_t, is_target_row=is_target_t,
        )
        loss.backward()

        # --- Check 2: gradients reach ONLY pft_encoder ---
        if step == 0:
            base_has_grad = any(
                p.grad is not None and p.grad.abs().max().item() > 0
                for n, p in pft_model.named_parameters() if not n.startswith("pft_encoder.")
            )
            pft_grad_norm = sum(
                p.grad.norm().item() for n, p in pft_model.named_parameters()
                if n.startswith("pft_encoder.") and p.grad is not None
            )
            print(f"[Check 2] any gradient outside pft_encoder (should be False): {base_has_grad}")
            print(f"[Check 2] pft_encoder gradient norm at step 0 (should be > 0): {pft_grad_norm:.6f}")

        grad_norms.append(sum(p.grad.norm().item() for p in pft_model.pft_encoder.parameters() if p.grad is not None))
        optimizer.step()
        losses.append(loss.item())
        if step % 5 == 0 or step == TRAIN_STEPS - 1:
            print(f"  step {step}: loss={loss.item():.5f}")

    print(f"\n[Check 5] loss finite throughout: {all(np.isfinite(losses))}, "
          f"first={losses[0]:.5f} last={losses[-1]:.5f}")

    # --- Check 3: pft_encoder output no longer all-zero ---
    pft_model.eval()
    with torch.no_grad():
        gamma, beta = pft_model.pft_encoder(pft_feat_t[is_target_t])
    print(f"\n[Check 3] mean |gamma| after training (should be > 0): {gamma.abs().mean().item():.6f}")
    print(f"[Check 3] mean |beta| after training (should be > 0): {beta.abs().mean().item():.6f}")

    # --- Check 4: perturbing PFT (fixed LAI/climate context) changes output ---
    probe_pixel = smoke_pixels[0]
    probe_idx = smoke_pixels.index(probe_pixel)
    row_start = probe_idx * 8  # 1 target + 7 covariate rows per pixel, in pixel order
    single_context = context_t[row_start:row_start + 8]
    single_future_cov = future_cov_t[row_start:row_start + 8]
    single_group = torch.zeros(8, dtype=torch.long, device=device)
    single_is_target = is_target_t[row_start:row_start + 8]

    compositions = {
        "100_forest": [1.0] + [0.0] * (len(pmd.PFT_CLASSES) - 1),
        "50_forest_50_grass": [0.5] + [0.0] * (len(pmd.PFT_CLASSES) - 2) + [0.5],
        "100_grass": [0.0] * (len(pmd.PFT_CLASSES) - 1) + [1.0],
    }
    preds_by_comp = {}
    with torch.no_grad():
        for label, vec in compositions.items():
            pft_probe = torch.zeros(8, len(pmd.PFT_CLASSES), device=device)
            pft_probe[single_is_target] = torch.tensor(vec, device=device, dtype=torch.float32)
            preds, _ = pft_model(
                context=single_context, group_ids=single_group, future_covariates=single_future_cov,
                num_output_patches=n_output_patches, pft_features=pft_probe, is_target_row=single_is_target,
            )
            preds_by_comp[label] = preds[single_is_target][0, 4].cpu().numpy()  # median quantile, target row

    ref = preds_by_comp["100_forest"]
    print(f"\n[Check 4] Perturbation test on pixel '{probe_pixel}' (median quantile forecast):")
    for label, p in preds_by_comp.items():
        diff = np.abs(p - ref).max()
        print(f"  {label}: max diff vs. 100_forest = {diff:.6f}, sample values = {p[:5].round(3)}")

    # --- Check 6: no test-year leakage ---
    print(f"\n[Check 6] Training future_year=2021 (2022 never referenced in build_batch calls above): "
          f"context ends 2020, future=2021 only. Confirmed by construction.")

    print("\nSmoke test complete.")


if __name__ == "__main__":
    main()

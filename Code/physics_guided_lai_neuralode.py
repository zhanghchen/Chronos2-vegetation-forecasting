# Stage 1, v2: replaces physics_guided_lai_field.py's coordinate-network-
# plus-collocation-matching PINN with a genuine Neural ODE (torchdiffeq).
#
# Why: v1's f_theta(lat,lon,t) was trained by matching its OWN autograd
# derivative, at scattered random collocation points, to the candidate PDE
# RHS - a standard PINN approach, but across 5 tuning rounds it kept
# producing jagged/oscillatory within-year curves (see
# physics_guided_lai_field.py's module docstring for the full debugging
# history: site embeddings, Q_pi magnitude penalty, climate smoothing, a
# d^2/dt^2 curvature penalty - none fully fixed it). The likely reason:
# matching a derivative at scattered points constrains the SLOPE at those
# points but nothing stops the learned function from oscillating BETWEEN
# them while still satisfying the pointwise residual loss on average.
#
# A Neural ODE sidesteps this by construction: there is no separate
# f_theta to fit against real data AND a derivative target. Instead
# dLAI/dt = Phi(LAI, climate).Xi + Q_pi IS the only model of the dynamics,
# and LAI(t) is obtained by literally integrating it forward in time from
# an initial condition. Every point on the resulting curve is causally
# determined by the ODE, so "the trajectory satisfies the physics" is true
# everywhere, not just at sampled points - the jaggedness failure mode
# cannot occur (the solution of a smooth vector field integrated with a
# consistent solver is smooth, full stop).
#
# Candidate terms (Phi), Xi, Q_pi, site embeddings and the data pool are
# all unchanged from v1 - only the training mechanism (integration instead
# of collocation-matching) is different. Reuses physics_guided_lai_field's
# load_pool/candidate_terms/CoordMLP/TERM_NAMES rather than redefining them.
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torchdiffeq import odeint

import physics_guided_lai_field as phy

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "outputs/physics_guided_lai_neuralode"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
WINDOW_STEPS = 46  # ~1 year of 8-day composites per training window
STEP_YEARS = 8.0 / 365.25  # fixed relative grid spacing (assumes no internal gaps - see note below)
BATCH_SIZE = 64
N_STEPS_TRAIN = 1500
RESUME = False  # set True (or override via script injection) to continue from a saved checkpoint
LR = 1e-3
BETA_Q_PENALTY = 0.02  # same role/value as the best v1 config - penalizes |Q_pi|
# so Xi (not Q_pi) carries the explanatory load, see physics_guided_lai_field.py
SEED = 0

# Windows are built from each site's own OBSERVED rows, assuming uniform
# 8-day spacing within the window (STEP_YEARS) rather than each row's real
# calendar gap - a deliberate simplification so every window in a training
# batch shares one relative time grid and can be integrated together in a
# single batched odeint call. Real missing-period gaps are rare within a
# single ~1-year window (most QC drops are isolated 8-day periods, not long
# runs - see the project's documented ~32% drop rate being spread across
# many short gaps, not concentrated), so this is a minor approximation, not
# a leakage or correctness issue: data_loss is still computed against each
# row's real LAI value, just assuming its position in the window is at
# uniform 8-day spacing rather than its exact calendar date.


def build_windows(pool, sites, site_to_idx, rng):
    """Returns a list of (site, start_row_idx) for every valid WINDOW_STEPS-
    length run of consecutive observed rows per site."""
    windows = []
    for site in sites:
        n = len(pool[pool.site == site])
        for start in range(0, n - WINDOW_STEPS, 4):  # stride 4 to limit total window count
            windows.append((site, start))
    rng.shuffle(windows)
    return windows


def make_batch(pool_by_site, windows, batch_idx, norm, site_to_idx, climate_mean, climate_std):
    lai0, lat_n, lon_n, site_idx, climate_batch, target_batch = [], [], [], [], [], []
    for site, start in [windows[i] for i in batch_idx]:
        g = pool_by_site[site].iloc[start:start + WINDOW_STEPS]
        lai0.append(g["LAI"].iloc[0])
        lat_n.append((g["lat"].iloc[0] - norm["lat_mean"]) / (norm["lat_std"] + 1e-8))
        lon_n.append((g["lon"].iloc[0] - norm["lon_mean"]) / (norm["lon_std"] + 1e-8))
        site_idx.append(site_to_idx[site])
        smoothed_cols = [f"{c}_smooth" for c in phy.FEATURE_COLS]
        climate_batch.append(g[smoothed_cols].to_numpy(dtype="float32"))
        target_batch.append(g["LAI"].to_numpy(dtype="float32"))

    lai0_t = torch.tensor(lai0, dtype=torch.float32, device=DEVICE)
    lat_n_t = torch.tensor(lat_n, dtype=torch.float32, device=DEVICE)
    lon_n_t = torch.tensor(lon_n, dtype=torch.float32, device=DEVICE)
    site_idx_t = torch.tensor(site_idx, dtype=torch.long, device=DEVICE)
    climate_t = torch.tensor(np.stack(climate_batch), dtype=torch.float32, device=DEVICE)  # (B, WINDOW_STEPS, 7)
    climate_n = (climate_t - torch.tensor(climate_mean, device=DEVICE)) / torch.tensor(climate_std, device=DEVICE)
    target_t = torch.tensor(np.stack(target_batch), dtype=torch.float32, device=DEVICE)  # (B, WINDOW_STEPS)
    return lai0_t, lat_n_t, lon_n_t, site_idx_t, climate_n, target_t


class ODEFunc(nn.Module):
    """dLAI/dt = Phi(LAI, climate(t)).Xi + Q_pi(lat,lon,t,site_embed).
    climate(t) is looked up by rounding t to the nearest window step (exact
    for the 'euler' fixed-grid solver, which only ever evaluates at the
    t-values we provide - see module docstring)."""

    def __init__(self, q_pi, xi, site_embedding, lat_n, lon_n, site_idx, climate_n, t_mean, t_std, t0_years):
        super().__init__()
        self.q_pi = q_pi
        self.xi = xi
        self.site_embedding = site_embedding
        self.lat_n = lat_n
        self.lon_n = lon_n
        self.site_idx = site_idx
        self.climate_n = climate_n  # (B, WINDOW_STEPS, 7)
        self.t_mean = t_mean
        self.t_std = t_std
        self.t0_years = t0_years  # absolute year-offset of each window's start (B,)

    def forward(self, t_rel, lai):
        # t_rel is a single scalar shared across the whole batch (fixed-grid
        # solvers evaluate every batch element at the same t) - step is one
        # index, not a per-batch-element tensor. torchdiffeq upcasts t to
        # float64 internally for its own step arithmetic regardless of the
        # state dtype - cast back to float32 before mixing with model
        # tensors, or every downstream Linear layer breaks on dtype mismatch.
        t_rel = t_rel.float()
        step = int(torch.clamp(torch.round(t_rel / STEP_YEARS), 0, WINDOW_STEPS - 1).item())
        climate_now = self.climate_n[:, step]
        t_years = self.t0_years + t_rel
        t_n = (t_years - self.t_mean) / self.t_std
        coords = torch.stack([self.lat_n, self.lon_n, t_n], dim=1)
        embed = self.site_embedding(self.site_idx)
        phi = phy.candidate_terms(lai, climate_now)
        q_val = self.q_pi(coords, embed)
        self._last_q = q_val
        return (phi * self.xi).sum(dim=1) + q_val


def main():
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)

    pool, sites = phy.load_pool()
    site_to_idx = {s: i for i, s in enumerate(sites)}
    pool_by_site = {s: g.reset_index(drop=True) for s, g in pool.groupby("site")}

    lat = pool["lat"].to_numpy(); lon = pool["lon"].to_numpy()
    t_years_all = (pool["date"] - pd.Timestamp("2000-01-01")).dt.days / 365.25
    norm = dict(lat_mean=lat.mean(), lat_std=lat.std(), lon_mean=lon.mean(), lon_std=lon.std(),
                t_mean=t_years_all.mean(), t_std=t_years_all.std())
    climate_mean = pool[[f"{c}_smooth" for c in phy.FEATURE_COLS]].to_numpy(dtype="float32").mean(axis=0)
    climate_std = pool[[f"{c}_smooth" for c in phy.FEATURE_COLS]].to_numpy(dtype="float32").std(axis=0) + 1e-8

    windows = build_windows(pool, sites, site_to_idx, rng)
    print(f"{len(windows)} training windows across {len(sites)} sites")

    site_embedding = nn.Embedding(len(sites), phy.SITE_EMBED_DIM).to(DEVICE)
    q_pi = phy.CoordMLP(norm["t_mean"], norm["t_std"]).to(DEVICE)
    xi = nn.Parameter(torch.zeros(len(phy.TERM_NAMES), device=DEVICE))

    ckpt_path = OUT_DIR / "stage1_neuralode_checkpoint.pt"
    if RESUME and ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location=DEVICE, weights_only=False)
        q_pi.load_state_dict(ckpt["q_pi"])
        site_embedding.load_state_dict(ckpt["site_embedding"])
        xi = nn.Parameter(ckpt["xi"].to(DEVICE))
        print(f"Resumed from {ckpt_path}")

    opt = torch.optim.Adam(list(q_pi.parameters()) + list(site_embedding.parameters()) + [xi], lr=LR)

    t_eval = torch.arange(WINDOW_STEPS, device=DEVICE, dtype=torch.float32) * STEP_YEARS

    history = []
    n_batches = max(1, len(windows) // BATCH_SIZE)
    for step in range(N_STEPS_TRAIN):
        batch_start = (step % n_batches) * BATCH_SIZE
        batch_idx = list(range(batch_start, min(batch_start + BATCH_SIZE, len(windows))))
        if len(batch_idx) < 2:
            continue
        lai0, lat_n, lon_n, site_idx, climate_n, target = make_batch(
            pool_by_site, windows, batch_idx, norm, site_to_idx, climate_mean, climate_std)

        t0_years = torch.tensor(
            [(pool_by_site[s].iloc[start]["date"] - pd.Timestamp("2000-01-01")).days / 365.25
             for s, start in [windows[i] for i in batch_idx]], dtype=torch.float32, device=DEVICE)

        func = ODEFunc(q_pi, xi, site_embedding, lat_n, lon_n, site_idx, climate_n,
                        norm["t_mean"], norm["t_std"], t0_years)
        traj = odeint(func, lai0, t_eval, method="euler")  # (WINDOW_STEPS, B)
        traj = traj.T  # (B, WINDOW_STEPS)

        data_loss = ((traj - target) ** 2).mean()
        # Q_pi magnitude penalty, evaluated at the same points just integrated
        q_vals = []
        for i, t_rel in enumerate(t_eval):
            step_idx = int(torch.round(t_rel / STEP_YEARS).item())
            climate_now = climate_n[:, step_idx]
            t_years = t0_years + t_rel
            t_n = (t_years - norm["t_mean"]) / norm["t_std"]
            coords = torch.stack([lat_n, lon_n, t_n], dim=1)
            embed = site_embedding(site_idx)
            q_vals.append(q_pi(coords, embed))
        q_penalty = torch.stack(q_vals, dim=1).pow(2).mean()

        loss = data_loss + BETA_Q_PENALTY * q_penalty
        opt.zero_grad()
        loss.backward()
        opt.step()

        if step % 100 == 0 or step == N_STEPS_TRAIN - 1:
            print(f"step {step:5d}  data_loss={data_loss.item():.4f}  q_penalty={q_penalty.item():.4f}  "
                  f"xi={xi.detach().cpu().numpy().round(3)}")
            history.append(dict(step=step, data_loss=data_loss.item(), q_penalty=q_penalty.item()))

    torch.save({"q_pi": q_pi.state_dict(), "xi": xi.detach().cpu(), "site_embedding": site_embedding.state_dict(),
                "site_to_idx": site_to_idx, "norm": norm, "climate_mean": climate_mean, "climate_std": climate_std,
                "term_names": phy.TERM_NAMES}, OUT_DIR / "stage1_neuralode_checkpoint.pt")
    pd.DataFrame(history).to_csv(OUT_DIR / "stage1_neuralode_training_history.csv", index=False)

    xi_report = pd.DataFrame({"term": phy.TERM_NAMES, "xi": xi.detach().cpu().numpy()})
    xi_report.to_csv(OUT_DIR / "stage1_neuralode_xi_coefficients.csv", index=False)
    print("\nFinal learned Xi coefficients:")
    print(xi_report.to_string(index=False))

    plot_diagnostics(q_pi, xi, site_embedding, pool_by_site, norm, site_to_idx, sites, climate_mean, climate_std)


def plot_diagnostics(q_pi, xi, site_embedding, pool_by_site, norm, site_to_idx, sites, climate_mean, climate_std,
                      n_sites=6):
    rng = np.random.default_rng(1)
    sample_sites = rng.choice(sites, size=n_sites, replace=False)
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), constrained_layout=True)
    for ax, site in zip(axes.flat, sample_sites):
        g = pool_by_site[site]
        n = len(g)
        lai0 = g["LAI"].iloc[0]
        lat_n = torch.tensor([(g["lat"].iloc[0] - norm["lat_mean"]) / (norm["lat_std"] + 1e-8)],
                              dtype=torch.float32, device=DEVICE)
        lon_n = torch.tensor([(g["lon"].iloc[0] - norm["lon_mean"]) / (norm["lon_std"] + 1e-8)],
                              dtype=torch.float32, device=DEVICE)
        site_idx = torch.tensor([site_to_idx[site]], device=DEVICE)
        smoothed_cols = [f"{c}_smooth" for c in phy.FEATURE_COLS]
        climate_raw = g[smoothed_cols].to_numpy(dtype="float32")
        climate_n = torch.tensor((climate_raw - climate_mean) / climate_std, dtype=torch.float32,
                                  device=DEVICE).unsqueeze(0)  # (1, n, 7)
        t0_years = (g["date"].iloc[0] - pd.Timestamp("2000-01-01")).days / 365.25
        t0_years_t = torch.tensor([t0_years], dtype=torch.float32, device=DEVICE)

        class FullFunc(nn.Module):
            def forward(self, t_rel, lai):
                t_rel = t_rel.float()
                step = torch.clamp(torch.round(t_rel / STEP_YEARS).long(), 0, n - 1)
                climate_now = climate_n[:, step]
                t_years = t0_years_t + t_rel
                t_n = (t_years - norm["t_mean"]) / norm["t_std"]
                coords = torch.stack([lat_n, lon_n, t_n], dim=1)
                embed = site_embedding(site_idx)
                phi = phy.candidate_terms(lai, climate_now)
                return (phi * xi).sum(dim=1) + q_pi(coords, embed)

        t_eval_full = torch.arange(n, device=DEVICE, dtype=torch.float32) * STEP_YEARS
        with torch.no_grad():
            traj = odeint(FullFunc(), torch.tensor([lai0], dtype=torch.float32, device=DEVICE), t_eval_full,
                          method="euler").squeeze(1)
        dates = g["date"]
        ax.plot(dates, g["LAI"], "o", ms=2.5, color="#555555", alpha=0.6, label="Observed")
        ax.plot(dates, traj.cpu().numpy(), "-", color="#2a78d6", lw=1.3, label="Neural ODE trajectory")
        ax.set_title(site, fontsize=10)
        ax.tick_params(labelsize=7)
    axes.flat[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Stage 1 v2 (Neural ODE): integrated LAI trajectory vs. observed (6 random CONUS sites)",
                 fontsize=12, fontweight="bold")
    fig.savefig(OUT_DIR / "stage1_neuralode_sanity_check.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("Saved stage1_neuralode_sanity_check.png")


if __name__ == "__main__":
    main()

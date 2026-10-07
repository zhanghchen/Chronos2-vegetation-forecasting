# Stage 1 of a physics-guided LAI modeling experiment, adapted from
# PhyDL-NWP (Luo et al., KDD'25, arXiv:2505.14555). That paper trains two
# coordinate-conditioned MLPs for weather downscaling - f_theta(x,y,t) ->
# field value, Q_pi(x,y,t) -> a "latent force" residual the PDE can't
# explain - jointly with sparse PDE coefficients Xi, enforcing
# d(f_theta)/dt = Phi(f_theta) . Xi + Q_pi via autograd, then freezes
# (f_theta, Xi, Q_pi) and fine-tunes a pretrained forecasting model with
# an added physics loss.
#
# Adaptation notes (this is NOT a 1:1 port - the paper's domain is
# meteorology on a spatial grid, this one is point-sampled vegetation):
#   - No spatial derivatives: LAI doesn't advect/diffuse in space the way
#     wind/temperature fields do. f_theta/Q_pi here take (lat, lon, t) and
#     are trained POOLED across all 70 CONUS pixels (not per-pixel) so
#     they learn one shared implicit LAI field, matching the user's
#     request ("input lat/lon and the corresponding coordinate, output
#     the corresponding LAI value").
#   - The PDE is replaced with a phenology-driven growth/decay ODE (no
#     canonical "LAI equation" exists the way Navier-Stokes exists for
#     wind - this is standard in the Growing-Season-Index/light-water-
#     temperature-limitation family of phenology models, not invented
#     from nothing): d(LAI)/dt = Phi(LAI, climate) . Xi + Q_pi, with a
#     small candidate term library built from the project's existing
#     gridMET covariates (Code/common_pipeline.py's FEATURE_COLS).
#   - Xi is trained end-to-end by gradient descent jointly with
#     f_theta/Q_pi (no separate SINDy-style iterative thresholding step
#     as in the original paper) - a deliberate simplification, noted
#     here rather than silently dropped.
#   - Time is encoded as continuous-years-since-2000 (captures long-term
#     trend) PLUS a differentiable seasonal encoding sin/cos(2*pi*doy/365)
#     computed INSIDE the network from that same scalar (not precomputed
#     as separate frozen features), so autograd d/dt correctly
#     back-propagates through the seasonal component too.
#
# Output: a trained field-and-PDE checkpoint + diagnostic plots (learned
# Xi coefficients, reconstructed-vs-observed curves for a few sites,
# gap-filled series) for manual sanity-checking before Stage 2 (using
# this as a physics-loss term in Chronos-2 LoRA fine-tuning).
import json
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = ROOT / "data/processed/sites"
LOYO_DIR = ROOT / "outputs/loyo_cv"
OUT_DIR = ROOT / "outputs/physics_guided_lai"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLS = ["tmmx", "tmmn", "pr", "srad", "vpd", "sph", "vs"]
LAI_MAX = 7.0  # physiological ceiling used in the radiation-limited growth term, m^2/m^2
CLIMATE_SMOOTH_WINDOW = 4  # 4 8-day composites ~ 1 month trailing rolling mean, see note below

# Second fix (round 2, attempted but INSUFFICIENT on its own): reconstructed
# curves came out high-frequency/jagged. Hypothesis was that instantaneous
# climate covariates in the candidate terms were forcing d(LAI)/dt to react
# to short-term climate noise, so each covariate was replaced with a
# trailing rolling mean (CLIMATE_SMOOTH_WINDOW). This did NOT meaningfully
# change the jaggedness when tested - wrong diagnosis, or at least an
# incomplete one; kept anyway since physiologically-lagged drivers are
# still the more defensible choice, but see the real fix below.
#
# Third fix (round 3): revised diagnosis after (2) didn't help - f_theta is
# an 8-layer/100-unit Tanh MLP regressing directly on ~73k individual noisy
# 8-day LAI retrievals (data_loss fits every point exactly), with nothing
# penalizing wiggliness in time. That's enough capacity to fit retrieval-
# level noise, not just the underlying seasonal trajectory. Added a direct
# temporal-smoothness penalty on d^2(LAI)/dt^2 (bounded "acceleration") -
# a biologically reasonable prior (canopy LAI doesn't jerk around) and a
# more direct fix than guessing at which input needed smoothing.
HIDDEN_DIM = 100
N_HIDDEN_LAYERS = 8  # matches PhyDL-NWP's reported f_theta/Q_pi size
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

N_EPOCHS = 4000
LR = 1e-3
ALPHA_PHY = 1.0  # physics-loss weight (data loss is O(LAI^2)~O(1), kept comparable - see diagnostics)
BETA_Q_PENALTY = 0.02  # penalizes |Q_pi| so it stays a residual "latent force",
GAMMA_SMOOTH = 0.0  # penalizes d^2(LAI)/dt^2, see note below - DISABLED for the
# final checkpoint: tried 0.05 (over-smoothed, flattened the seasonal cycle
# away entirely) and 0.0003 (too weak to visibly reduce the within-year
# jaggedness, while still measurably hurting data_loss) - neither resolved
# the jaggedness, and Xi's sign/relative-magnitude pattern was identical
# with or without it across all 5 tuning rounds. Since this checkpoint's
# only downstream use is as a physics-loss regularizer for Stage 2 (not a
# standalone LAI reconstruction product), kept the better-fitting
# BETA_Q_PENALTY-only configuration rather than paying the data_loss cost
# for a penalty that wasn't fixing the thing it was meant to fix.
# not the thing that explains all of d(LAI)/dt on its own - see note below
N_COLLOCATION_PER_SITE = 200  # extra random-time points per site for the physics loss (gap-filling signal)
SEED = 0
SITE_EMBED_DIM = 8

# Second issue found by inspection: without this penalty, Xi shrank toward
# ~0 over training (final run: all |Xi|<0.01) while Q_pi silently absorbed
# the entire d(LAI)/dt signal - Q_pi has unconstrained capacity, so nothing
# forced the explicit, interpretable Phi.Xi term to carry any explanatory
# load. That defeats the point of a "physics-guided" model (end state is
# just a disguised neural ODE). Q_pi is supposed to be a small correction
# for what the candidate terms can't explain (PhyDL-NWP's own framing:
# "a supplement to missing variables"), not the primary mechanism - added
# an L2 penalty on Q_pi's magnitude so Xi is forced to explain what it can.

# First pass (lat/lon/t only, no site identity) underfit badly: the
# reconstruction sanity-check plot showed near-identical seasonal curves
# across sites with very different LAI ranges (e.g. px064_shrubs_bd
# observed 0.4-1.9 vs. reconstructed 0.6-1.05) - raw lat/lon doesn't carry
# vegetation-type information, and two nearby pixels can be forest vs.
# grassland with very different dynamics, unlike a physically smooth
# weather field. Fixed by adding a learned per-site embedding as an extra
# input (common in PINN/multi-task "context vector" setups) - this keeps
# the shared Xi/physics structure but lets f_theta/Q_pi disambiguate
# individual sites' dynamics. lat/lon is kept too (useful if this is ever
# extended to unseen sites via nearest-neighbor embedding lookup).


def load_pool():
    sites = sorted(p.name for p in LOYO_DIR.iterdir() if p.is_dir() and p.name != "comparison")
    assert len(sites) == 70, f"expected 70 CONUS sites, found {len(sites)}"
    rows = []
    for site in sites:
        df = pd.read_csv(SITES_DIR / f"{site}.csv", parse_dates=["date"])
        df["site"] = site
        rows.append(df)
    pool = pd.concat(rows, ignore_index=True)
    n_before = len(pool)
    pool = pool.dropna(subset=["LAI"] + FEATURE_COLS).reset_index(drop=True)
    if len(pool) < n_before:
        print(f"Dropped {n_before - len(pool)} rows with NaN LAI/climate values")

    pool = pool.sort_values(["site", "date"]).reset_index(drop=True)
    smoothed_cols = [f"{c}_smooth" for c in FEATURE_COLS]
    pool[smoothed_cols] = pool.groupby("site")[FEATURE_COLS].transform(
        lambda s: s.rolling(CLIMATE_SMOOTH_WINDOW, min_periods=1).mean())
    return pool, sites


def make_features(pool, site_to_idx):
    t_years = (pool["date"] - pd.Timestamp("2000-01-01")).dt.days / 365.25
    lat = pool["lat"].to_numpy()
    lon = pool["lon"].to_numpy()
    # normalize to ~[-1,1] ranges for stable MLP training
    lat_n = (lat - lat.mean()) / (lat.std() + 1e-8)
    lon_n = (lon - lon.mean()) / (lon.std() + 1e-8)
    t_n = (t_years - t_years.mean()) / (t_years.std() + 1e-8)
    coords = np.stack([lat_n, lon_n, t_n.to_numpy()], axis=1).astype("float32")
    site_idx = pool["site"].map(site_to_idx).to_numpy(dtype="int64")
    smoothed_cols = [f"{c}_smooth" for c in FEATURE_COLS]
    climate = pool[smoothed_cols].to_numpy(dtype="float32")
    lai = pool["LAI"].to_numpy(dtype="float32")
    return coords, site_idx, climate, lai, dict(lat_mean=lat.mean(), lat_std=lat.std(), lon_mean=lon.mean(),
                                                 lon_std=lon.std(), t_mean=t_years.mean(), t_std=t_years.std())


class CoordMLP(nn.Module):
    """f_theta or Q_pi: (lat_n, lon_n, t_n, site_embedding) -> scalar field
    value. Seasonal sin/cos computed INSIDE forward from t_n so d(.)/dt (via
    the coords tensor's autograd) correctly includes the seasonal chain rule
    - see module docstring. site_embedding disambiguates vegetation-type-
    driven dynamics that raw lat/lon can't (see SITE_EMBED_DIM note above)."""

    def __init__(self, t_mean, t_std, embed_dim=SITE_EMBED_DIM, hidden=HIDDEN_DIM, n_layers=N_HIDDEN_LAYERS):
        super().__init__()
        self.t_mean = t_mean
        self.t_std = t_std
        in_dim = 5 + embed_dim  # lat_n, lon_n, t_n, sin(doy), cos(doy), site_embedding
        layers = [nn.Linear(in_dim, hidden), nn.Tanh()]
        for _ in range(n_layers - 1):
            layers += [nn.Linear(hidden, hidden), nn.Tanh()]
        layers += [nn.Linear(hidden, 1)]
        self.net = nn.Sequential(*layers)

    def forward(self, coords, site_embed):
        lat_n, lon_n, t_n = coords[:, 0:1], coords[:, 1:2], coords[:, 2:3]
        t_years = t_n * self.t_std + self.t_mean
        doy_angle = 2 * np.pi * (t_years % 1.0)  # fraction-of-year -> radians
        season = torch.cat([torch.sin(doy_angle), torch.cos(doy_angle)], dim=1)
        x = torch.cat([lat_n, lon_n, t_n, season, site_embed], dim=1)
        return self.net(x).squeeze(-1)


TERM_NAMES = ["bias", "LAI_self_decay", "radiation_limited_growth", "temp_forcing", "precip_forcing", "vpd_stress"]


def candidate_terms(lai_hat, climate):
    """Phi(LAI, climate): candidate phenology-ODE terms, see module docstring.
    climate columns: tmmx, tmmn, pr, srad, vpd, sph, vs (Code/common_pipeline.FEATURE_COLS)."""
    tmmx, tmmn, pr, srad, vpd = climate[:, 0], climate[:, 1], climate[:, 2], climate[:, 3], climate[:, 4]
    t_mean = (tmmx + tmmn) / 2.0
    bias = torch.ones_like(lai_hat)
    self_decay = lai_hat
    rad_growth = srad * (1.0 - lai_hat / LAI_MAX)
    temp_forcing = t_mean
    precip_forcing = pr
    vpd_stress = vpd * lai_hat
    return torch.stack([bias, self_decay, rad_growth, temp_forcing, precip_forcing, vpd_stress], dim=1)


def main():
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    pool, sites = load_pool()
    site_to_idx = {s: i for i, s in enumerate(sites)}
    coords, site_idx, climate, lai, norm = make_features(pool, site_to_idx)
    print(f"Loaded {len(pool)} observations across {len(sites)} CONUS sites")

    # standardize climate columns (candidate terms mix very different scales -
    # tmmx ~290K, pr ~mm, srad ~W/m2 - without this Xi is ill-conditioned)
    climate_mean = climate.mean(axis=0)
    climate_std = climate.std(axis=0) + 1e-8
    climate_n = (climate - climate_mean) / climate_std

    coords_t = torch.tensor(coords, device=DEVICE)
    site_idx_t = torch.tensor(site_idx, device=DEVICE)
    climate_t = torch.tensor(climate_n, dtype=torch.float32, device=DEVICE)
    lai_t = torch.tensor(lai, device=DEVICE)

    site_embedding = nn.Embedding(len(sites), SITE_EMBED_DIM).to(DEVICE)
    f_theta = CoordMLP(norm["t_mean"], norm["t_std"]).to(DEVICE)
    q_pi = CoordMLP(norm["t_mean"], norm["t_std"]).to(DEVICE)
    xi = nn.Parameter(torch.zeros(len(TERM_NAMES), device=DEVICE))

    # random collocation points (same lat/lon as real sites, random times in
    # [min,max] of the pool) for the physics loss - lets it regularize
    # between/around observed points, not just exactly at them (this is what
    # gives the gap-filling behavior).
    rng = np.random.default_rng(SEED)
    site_lat_lon = pool.groupby("site")[["lat", "lon"]].first()
    colloc_rows, colloc_site_idx = [], []
    t_min, t_max = coords[:, 2].min(), coords[:, 2].max()
    for site_name, (lat_v, lon_v) in site_lat_lon.iterrows():
        lat_n = (lat_v - norm["lat_mean"]) / (norm["lat_std"] + 1e-8)
        lon_n = (lon_v - norm["lon_mean"]) / (norm["lon_std"] + 1e-8)
        t_rand = rng.uniform(t_min, t_max, size=N_COLLOCATION_PER_SITE)
        for t_v in t_rand:
            colloc_rows.append([lat_n, lon_n, t_v])
            colloc_site_idx.append(site_to_idx[site_name])
    colloc_coords = torch.tensor(np.array(colloc_rows, dtype="float32"), device=DEVICE)
    colloc_site_idx_t = torch.tensor(colloc_site_idx, device=DEVICE)
    # nearest-observation climate lookup for collocation points (climate is
    # external forcing data, not something f_theta/Q_pi predict)
    from scipy.spatial import cKDTree
    obs_tree = cKDTree(coords[:, [0, 1, 2]])
    _, nn_idx = obs_tree.query(colloc_coords.cpu().numpy())
    colloc_climate = climate_t[nn_idx]
    print(f"{len(colloc_rows)} collocation points added for the physics loss")

    all_site_idx_t = torch.cat([site_idx_t, colloc_site_idx_t], dim=0)

    opt = torch.optim.Adam(list(f_theta.parameters()) + list(q_pi.parameters()) +
                            list(site_embedding.parameters()) + [xi], lr=LR)

    history = []
    for epoch in range(N_EPOCHS):
        opt.zero_grad()

        embed_obs = site_embedding(site_idx_t)
        lai_pred_obs = f_theta(coords_t, embed_obs)
        data_loss = ((lai_pred_obs - lai_t) ** 2).mean()

        all_coords = torch.cat([coords_t, colloc_coords], dim=0).clone().requires_grad_(True)
        all_climate = torch.cat([climate_t, colloc_climate], dim=0)
        embed_all = site_embedding(all_site_idx_t)
        lai_pred_all = f_theta(all_coords, embed_all)
        dlai_dt_full = torch.autograd.grad(lai_pred_all.sum(), all_coords, create_graph=True)[0]
        dlai_dt = dlai_dt_full[:, 2]
        # chain rule: coords[:,2] is t_n = (t_years - t_mean)/t_std, so d/dt_years = d/dt_n * dt_n/dt_years = d/dt_n / t_std
        dlai_dt_years = dlai_dt / norm["t_std"]
        if GAMMA_SMOOTH > 0:  # skip the (expensive) double-backward when disabled
            d2lai_dt2 = torch.autograd.grad(dlai_dt.sum(), all_coords, create_graph=True)[0][:, 2] / (norm["t_std"] ** 2)
            smooth_penalty = (d2lai_dt2 ** 2).mean()
        else:
            smooth_penalty = torch.zeros((), device=DEVICE)

        phi = candidate_terms(lai_pred_all, all_climate)
        q_val = q_pi(all_coords, embed_all)
        rhs = (phi * xi).sum(dim=1) + q_val
        phy_loss = ((dlai_dt_years - rhs) ** 2).mean()
        q_penalty = (q_val ** 2).mean()

        loss = data_loss + ALPHA_PHY * phy_loss + BETA_Q_PENALTY * q_penalty + GAMMA_SMOOTH * smooth_penalty
        loss.backward()
        opt.step()

        if epoch % 100 == 0 or epoch == N_EPOCHS - 1:
            print(f"epoch {epoch:5d}  data_loss={data_loss.item():.4f}  phy_loss={phy_loss.item():.4f}  "
                  f"q_penalty={q_penalty.item():.4f}  smooth={smooth_penalty.item():.4f}  "
                  f"xi={xi.detach().cpu().numpy().round(3)}")
            history.append(dict(epoch=epoch, data_loss=data_loss.item(), phy_loss=phy_loss.item(),
                                 q_penalty=q_penalty.item(), smooth_penalty=smooth_penalty.item()))

    torch.save({"f_theta": f_theta.state_dict(), "q_pi": q_pi.state_dict(), "xi": xi.detach().cpu(),
                "site_embedding": site_embedding.state_dict(), "site_to_idx": site_to_idx,
                "norm": norm, "climate_mean": climate_mean, "climate_std": climate_std,
                "term_names": TERM_NAMES}, OUT_DIR / "stage1_checkpoint.pt")
    pd.DataFrame(history).to_csv(OUT_DIR / "stage1_training_history.csv", index=False)

    xi_final = xi.detach().cpu().numpy()
    xi_report = pd.DataFrame({"term": TERM_NAMES, "xi": xi_final})
    xi_report.to_csv(OUT_DIR / "stage1_xi_coefficients.csv", index=False)
    print("\nFinal learned Xi coefficients:")
    print(xi_report.to_string(index=False))

    plot_diagnostics(f_theta, site_embedding, pool, norm, site_to_idx, sites)


def plot_diagnostics(f_theta, site_embedding, pool, norm, site_to_idx, sites, n_sites=6):
    f_theta.eval()
    rng = np.random.default_rng(1)
    sample_sites = rng.choice(sites, size=n_sites, replace=False)
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), constrained_layout=True)
    for ax, site in zip(axes.flat, sample_sites):
        g = pool[pool.site == site].sort_values("date")
        t_years = (g["date"] - pd.Timestamp("2000-01-01")).dt.days / 365.25
        t_n = (t_years - norm["t_mean"]) / norm["t_std"]
        lat_n = (g["lat"].iloc[0] - norm["lat_mean"]) / (norm["lat_std"] + 1e-8)
        lon_n = (g["lon"].iloc[0] - norm["lon_mean"]) / (norm["lon_std"] + 1e-8)
        # dense time grid spanning the site's observed range, for a smooth reconstructed curve
        t_dense = np.linspace(t_n.min(), t_n.max(), 400)
        coords_dense = torch.tensor(np.stack([np.full_like(t_dense, lat_n), np.full_like(t_dense, lon_n),
                                               t_dense], axis=1).astype("float32"), device=DEVICE)
        site_idx_dense = torch.full((len(t_dense),), site_to_idx[site], device=DEVICE)
        with torch.no_grad():
            embed_dense = site_embedding(site_idx_dense)
            lai_dense = f_theta(coords_dense, embed_dense).cpu().numpy()
        dates_dense = pd.Timestamp("2000-01-01") + pd.to_timedelta(
            (t_dense * norm["t_std"] + norm["t_mean"]) * 365.25, unit="D")
        ax.plot(g["date"], g["LAI"], "o", ms=2.5, color="#555555", alpha=0.6, label="Observed")
        ax.plot(dates_dense, lai_dense, "-", color="#2a78d6", lw=1.5, label="f_theta reconstruction")
        ax.set_title(site, fontsize=10)
        ax.tick_params(labelsize=7)
    axes.flat[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Stage 1: physics-guided implicit LAI field vs. observed (6 random CONUS sites)",
                 fontsize=12, fontweight="bold")
    fig.savefig(OUT_DIR / "stage1_reconstruction_sanity_check.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved stage1_reconstruction_sanity_check.png")


if __name__ == "__main__":
    main()

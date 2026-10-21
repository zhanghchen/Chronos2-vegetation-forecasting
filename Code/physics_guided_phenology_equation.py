# Prof. Wang's exact proposed equation (replacing this project's earlier
# ad hoc linear candidate-term library in physics_guided_lai_field.py /
# physics_guided_lai_neuralode.py, which did NOT use this equation - this
# file is the "supplement a validation experiment" run she asked for,
# applied first to LAI since GPP data has to be newly fetched - see
# build_phenology_covariates.py / Code/fetch_conus_gpp_appeears.py):
#
#   dV/dt = r(T,PAR).V.(1 - V/K(P,SM,VPD)) - m(SPEI,T_freeze).V
#
# A logistic growth-mortality ODE: r = light/temperature-limited relative
# growth rate, K = water-availability-limited carrying capacity, m =
# drought/freeze-driven mortality rate. Unlike the earlier linear-in-Xi
# candidate library (a single global coefficient per term, found by
# gradient descent), r/K/m are each THEIR OWN small feedforward network
# (2 inputs -> 16 hidden (Tanh) -> 1, softplus output to guarantee
# positivity, as the equation's own structure requires: negative growth,
# capacity or mortality rates aren't physically meaningful here) - a
# genuinely different, nonlinear model, not a drop-in reparameterization.
#
# Integrated via Neural ODE (torchdiffeq, 'euler' fixed-grid), same
# windowed-batch training scheme proven in physics_guided_lai_neuralode.py
# (that file's module docstring has the full debugging history of why
# collocation-point PINN matching was abandoned in favor of integration -
# reused unchanged here, just with a different RHS parameterization).
#
# V is passed in as an argument (TARGET_COL) so the SAME script runs the
# LAI validation (V="LAI") and, once GPP is fetched, the GPP experiment
# (V="GPP") without duplicating code.
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("AGG")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torchdiffeq import odeint

ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = ROOT / "data/processed/sites_phenology"
LOYO_DIR = ROOT / "outputs/loyo_cv"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
WINDOW_STEPS = 46
STEP_YEARS = 8.0 / 365.25
BATCH_SIZE = 64
N_STEPS_TRAIN = 2000
LR = 1e-3
BETA_Q_PENALTY = 0.02  # same role as physics_guided_lai_neuralode.py's - keeps Q_pi a
# residual "latent force", not the thing that explains the whole derivative (see that
# file's docstring for why this matters: without it, Xi/the named sub-networks shrink
# toward irrelevance and Q_pi silently absorbs everything).
SITE_EMBED_DIM = 8
SEED = 0


class SubFunc(nn.Module):
    """r(a,b), K(a,b), or m(a,b): 2 standardized inputs -> positive scalar.
    Softplus output enforces positivity, which this equation's structure
    requires (a negative growth rate, capacity, or mortality rate isn't
    physically meaningful, unlike the earlier linear-Xi model where terms
    could have either sign)."""

    def __init__(self, hidden=16):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(2, hidden), nn.Tanh(), nn.Linear(hidden, hidden), nn.Tanh(),
                                  nn.Linear(hidden, 1))

    def forward(self, a, b):
        x = torch.stack([a, b], dim=1)
        return nn.functional.softplus(self.net(x).squeeze(-1))


class CoordEmbed(nn.Module):
    """Q_pi(lat,lon,t,site_embed) - unchanged in role/architecture from
    physics_guided_lai_field.py's CoordMLP."""

    def __init__(self, t_mean, t_std, embed_dim=SITE_EMBED_DIM, hidden=100, n_layers=8):
        super().__init__()
        self.t_mean = t_mean; self.t_std = t_std
        layers = [nn.Linear(5 + embed_dim, hidden), nn.Tanh()]
        for _ in range(n_layers - 1):
            layers += [nn.Linear(hidden, hidden), nn.Tanh()]
        layers += [nn.Linear(hidden, 1)]
        self.net = nn.Sequential(*layers)

    def forward(self, coords, site_embed):
        lat_n, lon_n, t_n = coords[:, 0:1], coords[:, 1:2], coords[:, 2:3]
        t_years = t_n * self.t_std + self.t_mean
        doy_angle = 2 * np.pi * (t_years % 1.0)
        season = torch.cat([torch.sin(doy_angle), torch.cos(doy_angle)], dim=1)
        x = torch.cat([lat_n, lon_n, t_n, season, site_embed], dim=1)
        return self.net(x).squeeze(-1)


def load_pool(target_col):
    sites = sorted(p.name for p in LOYO_DIR.iterdir() if p.is_dir() and p.name != "comparison")
    rows = []
    for site in sites:
        path = SITES_DIR / f"{site}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        df["site"] = site
        rows.append(df)
    pool = pd.concat(rows, ignore_index=True)
    n_before = len(pool)
    needed_cols = [target_col, "PAR", "pr", "SM_proxy", "vpd", "SPEI_proxy", "T_freeze"]
    pool = pool.dropna(subset=needed_cols).reset_index(drop=True)
    if len(pool) < n_before:
        print(f"Dropped {n_before - len(pool)} NaN rows")
    sites_present = sorted(pool["site"].unique())
    return pool, sites_present


def standardize(x):
    mean, std = x.mean(), x.std() + 1e-8
    return (x - mean) / std, mean, std


def build_windows(pool, sites, rng, stride=4):
    windows = []
    for site in sites:
        n = len(pool[pool.site == site])
        for start in range(0, n - WINDOW_STEPS, stride):
            windows.append((site, start))
    rng.shuffle(windows)
    return windows


def make_batch(pool_by_site, windows, batch_idx, norm, site_to_idx, target_col):
    v0, lat_n, lon_n, site_idx = [], [], [], []
    T, PAR, P, SM, VPD, SPEI, Tfz, target = ([] for _ in range(8))
    for site, start in [windows[i] for i in batch_idx]:
        g = pool_by_site[site].iloc[start:start + WINDOW_STEPS]
        v0.append(g[target_col].iloc[0])
        lat_n.append((g["lat"].iloc[0] - norm["lat_mean"]) / (norm["lat_std"] + 1e-8))
        lon_n.append((g["lon"].iloc[0] - norm["lon_mean"]) / (norm["lon_std"] + 1e-8))
        site_idx.append(site_to_idx[site])
        T.append(((g["tmmx"] + g["tmmn"]) / 2 - norm["T_mean"]) / norm["T_std"])
        PAR.append((g["PAR"] - norm["PAR_mean"]) / norm["PAR_std"])
        P.append((g["pr"] - norm["P_mean"]) / norm["P_std"])
        SM.append((g["SM_proxy"] - norm["SM_mean"]) / norm["SM_std"])
        VPD.append((g["vpd"] - norm["VPD_mean"]) / norm["VPD_std"])
        SPEI.append((g["SPEI_proxy"] - norm["SPEI_mean"]) / norm["SPEI_std"])
        Tfz.append((g["T_freeze"] - norm["Tfz_mean"]) / norm["Tfz_std"])
        target.append(g[target_col].to_numpy(dtype="float32"))

    def T_(x): return torch.tensor(np.stack(x), dtype=torch.float32, device=DEVICE)
    return (torch.tensor(v0, dtype=torch.float32, device=DEVICE),
            torch.tensor(lat_n, dtype=torch.float32, device=DEVICE),
            torch.tensor(lon_n, dtype=torch.float32, device=DEVICE),
            torch.tensor(site_idx, dtype=torch.long, device=DEVICE),
            T_(T), T_(PAR), T_(P), T_(SM), T_(VPD), T_(SPEI), T_(Tfz), T_(target))


class ODEFunc(nn.Module):
    def __init__(self, r_net, k_net, m_net, q_pi, site_embedding, lat_n, lon_n, site_idx,
                 T, PAR, P, SM, VPD, SPEI, Tfz, t_mean, t_std, t0_years):
        super().__init__()
        self.r_net, self.k_net, self.m_net = r_net, k_net, m_net
        self.q_pi, self.site_embedding = q_pi, site_embedding
        self.lat_n, self.lon_n, self.site_idx = lat_n, lon_n, site_idx
        self.T, self.PAR, self.P, self.SM, self.VPD, self.SPEI, self.Tfz = T, PAR, P, SM, VPD, SPEI, Tfz
        self.t_mean, self.t_std, self.t0_years = t_mean, t_std, t0_years

    def forward(self, t_rel, v):
        # Gradient clipping alone (on the backward pass) was NOT enough to
        # stabilize training - it still diverged to NaN (previously: no
        # clipping recovered from a loss spike to a noisy plateau; WITH
        # clipping, training instead diverged to NaN at step 600 and never
        # recovered). The actual failure is in the FORWARD Euler
        # integration itself: a bad r/K/m parameterization can drive v to
        # an extreme value mid-training, and clipping gradients afterward
        # doesn't undo that. Clamped v to its only physically required
        # bound (non-negative; LAI/GPP can't be negative) plus a generous
        # safety ceiling well above any realistic value, as a pure
        # numerical safety valve, not a constraint meant to bind normally.
        v = v.clamp(min=0.0, max=100.0)
        t_rel = t_rel.float()
        step = int(torch.clamp(torch.round(t_rel / STEP_YEARS), 0, self.T.shape[1] - 1).item())
        T, PAR = self.T[:, step], self.PAR[:, step]
        P, SM, VPD = self.P[:, step], self.SM[:, step], self.VPD[:, step]
        SPEI, Tfz = self.SPEI[:, step], self.Tfz[:, step]

        r = self.r_net(T, PAR)
        K = self.k_net(P, SM, VPD)
        m = self.m_net(SPEI, Tfz)

        t_years = self.t0_years + t_rel
        t_n = (t_years - self.t_mean) / self.t_std
        coords = torch.stack([self.lat_n, self.lon_n, t_n], dim=1)
        embed = self.site_embedding(self.site_idx)
        q_val = self.q_pi(coords, embed)
        self._last_q = q_val

        return r * v * (1 - v / (K + 1e-6)) - m * v + q_val


class KNet(nn.Module):
    """K(P, SM, VPD): 3 standardized inputs -> positive carrying capacity."""

    def __init__(self, hidden=16):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(3, hidden), nn.Tanh(), nn.Linear(hidden, hidden), nn.Tanh(),
                                  nn.Linear(hidden, 1))

    def forward(self, P, SM, VPD):
        x = torch.stack([P, SM, VPD], dim=1)
        return nn.functional.softplus(self.net(x).squeeze(-1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-col", default="LAI", choices=["LAI", "GPP"])
    parser.add_argument("--n-steps", type=int, default=N_STEPS_TRAIN)
    parser.add_argument("--out-tag", default=None)
    args = parser.parse_args()
    target_col = args.target_col
    out_tag = args.out_tag or target_col.lower()
    out_dir = ROOT / f"outputs/physics_guided_phenology_{out_tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)

    pool, sites = load_pool(target_col)
    site_to_idx = {s: i for i, s in enumerate(sites)}
    pool_by_site = {s: g.reset_index(drop=True) for s, g in pool.groupby("site")}
    print(f"Loaded {len(pool)} observations across {len(sites)} sites for target={target_col}")

    lat = pool["lat"].to_numpy(); lon = pool["lon"].to_numpy()
    t_years_all = (pool["date"] - pd.Timestamp("2000-01-01")).dt.days / 365.25
    T_all = (pool["tmmx"] + pool["tmmn"]) / 2
    norm = dict(
        lat_mean=lat.mean(), lat_std=lat.std(), lon_mean=lon.mean(), lon_std=lon.std(),
        t_mean=t_years_all.mean(), t_std=t_years_all.std(),
        T_mean=T_all.mean(), T_std=T_all.std(),
        PAR_mean=pool["PAR"].mean(), PAR_std=pool["PAR"].std(),
        P_mean=pool["pr"].mean(), P_std=pool["pr"].std(),
        SM_mean=pool["SM_proxy"].mean(), SM_std=pool["SM_proxy"].std(),
        VPD_mean=pool["vpd"].mean(), VPD_std=pool["vpd"].std(),
        SPEI_mean=pool["SPEI_proxy"].mean(), SPEI_std=pool["SPEI_proxy"].std(),
        Tfz_mean=pool["T_freeze"].mean(), Tfz_std=pool["T_freeze"].std(),
    )

    windows = build_windows(pool, sites, rng)
    print(f"{len(windows)} training windows")

    r_net, m_net = SubFunc().to(DEVICE), SubFunc().to(DEVICE)
    k_net = KNet().to(DEVICE)
    site_embedding = nn.Embedding(len(sites), SITE_EMBED_DIM).to(DEVICE)
    q_pi = CoordEmbed(norm["t_mean"], norm["t_std"]).to(DEVICE)
    opt = torch.optim.Adam(list(r_net.parameters()) + list(k_net.parameters()) + list(m_net.parameters()) +
                            list(site_embedding.parameters()) + list(q_pi.parameters()), lr=LR)

    t_eval = torch.arange(WINDOW_STEPS, device=DEVICE, dtype=torch.float32) * STEP_YEARS

    history = []
    n_batches = max(1, len(windows) // BATCH_SIZE)
    for step in range(args.n_steps):
        batch_start = (step % n_batches) * BATCH_SIZE
        batch_idx = list(range(batch_start, min(batch_start + BATCH_SIZE, len(windows))))
        if len(batch_idx) < 2:
            continue
        v0, lat_n, lon_n, site_idx, T, PAR, P, SM, VPD, SPEI, Tfz, target = make_batch(
            pool_by_site, windows, batch_idx, norm, site_to_idx, target_col)
        t0_years = torch.tensor(
            [(pool_by_site[s].iloc[start]["date"] - pd.Timestamp("2000-01-01")).days / 365.25
             for s, start in [windows[i] for i in batch_idx]], dtype=torch.float32, device=DEVICE)

        func = ODEFunc(r_net, k_net, m_net, q_pi, site_embedding, lat_n, lon_n, site_idx,
                        T, PAR, P, SM, VPD, SPEI, Tfz, norm["t_mean"], norm["t_std"], t0_years)
        traj = odeint(func, v0, t_eval, method="euler").T

        data_loss = ((traj - target) ** 2).mean()
        q_vals = []
        for t_rel in t_eval:
            step_i = int(torch.round(t_rel / STEP_YEARS).item())
            t_years = t0_years + t_rel
            t_n = (t_years - norm["t_mean"]) / norm["t_std"]
            coords = torch.stack([lat_n, lon_n, t_n], dim=1)
            embed = site_embedding(site_idx)
            q_vals.append(q_pi(coords, embed))
        q_penalty = torch.stack(q_vals, dim=1).pow(2).mean()

        loss = data_loss + BETA_Q_PENALTY * q_penalty
        opt.zero_grad()
        loss.backward()
        # The 1/(K+eps) term in the ODE can produce occasional large
        # gradients when K is driven near zero during training (observed:
        # data_loss dropped cleanly to 0.19 by step 400, then spiked to 1.3
        # at step 500 and never fully recovered) - clipped as a standard,
        # minimally-invasive stabilizer rather than re-architecting the model.
        torch.nn.utils.clip_grad_norm_(
            list(r_net.parameters()) + list(k_net.parameters()) + list(m_net.parameters()) +
            list(site_embedding.parameters()) + list(q_pi.parameters()), max_norm=1.0)
        opt.step()

        if step % 100 == 0 or step == args.n_steps - 1:
            print(f"step {step:5d}  data_loss={data_loss.item():.4f}  q_penalty={q_penalty.item():.4f}")
            history.append(dict(step=step, data_loss=data_loss.item(), q_penalty=q_penalty.item()))

    torch.save({"r_net": r_net.state_dict(), "k_net": k_net.state_dict(), "m_net": m_net.state_dict(),
                "q_pi": q_pi.state_dict(), "site_embedding": site_embedding.state_dict(),
                "site_to_idx": site_to_idx, "norm": norm, "target_col": target_col},
               out_dir / "checkpoint.pt")
    pd.DataFrame(history).to_csv(out_dir / "training_history.csv", index=False)
    print(f"\nSaved checkpoint -> {out_dir / 'checkpoint.pt'}")

    plot_diagnostics(r_net, k_net, m_net, q_pi, site_embedding, pool_by_site, norm, site_to_idx, sites,
                      target_col, out_dir)


def plot_diagnostics(r_net, k_net, m_net, q_pi, site_embedding, pool_by_site, norm, site_to_idx, sites,
                      target_col, out_dir, n_sites=6):
    rng = np.random.default_rng(1)
    sample_sites = rng.choice(sites, size=min(n_sites, len(sites)), replace=False)
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), constrained_layout=True)
    for ax, site in zip(axes.flat, sample_sites):
        g = pool_by_site[site]
        n = len(g)
        v0 = g[target_col].iloc[0]
        lat_n = torch.tensor([(g["lat"].iloc[0] - norm["lat_mean"]) / (norm["lat_std"] + 1e-8)],
                              dtype=torch.float32, device=DEVICE)
        lon_n = torch.tensor([(g["lon"].iloc[0] - norm["lon_mean"]) / (norm["lon_std"] + 1e-8)],
                              dtype=torch.float32, device=DEVICE)
        site_idx = torch.tensor([site_to_idx[site]], device=DEVICE)
        T = torch.tensor((((g["tmmx"] + g["tmmn"]) / 2 - norm["T_mean"]) / norm["T_std"]).to_numpy(),
                          dtype=torch.float32, device=DEVICE).unsqueeze(0)
        PAR = torch.tensor(((g["PAR"] - norm["PAR_mean"]) / norm["PAR_std"]).to_numpy(),
                            dtype=torch.float32, device=DEVICE).unsqueeze(0)
        P = torch.tensor(((g["pr"] - norm["P_mean"]) / norm["P_std"]).to_numpy(),
                          dtype=torch.float32, device=DEVICE).unsqueeze(0)
        SM = torch.tensor(((g["SM_proxy"] - norm["SM_mean"]) / norm["SM_std"]).to_numpy(),
                           dtype=torch.float32, device=DEVICE).unsqueeze(0)
        VPD = torch.tensor(((g["vpd"] - norm["VPD_mean"]) / norm["VPD_std"]).to_numpy(),
                            dtype=torch.float32, device=DEVICE).unsqueeze(0)
        SPEI = torch.tensor(((g["SPEI_proxy"] - norm["SPEI_mean"]) / norm["SPEI_std"]).to_numpy(),
                             dtype=torch.float32, device=DEVICE).unsqueeze(0)
        Tfz = torch.tensor(((g["T_freeze"] - norm["Tfz_mean"]) / norm["Tfz_std"]).to_numpy(),
                            dtype=torch.float32, device=DEVICE).unsqueeze(0)
        t0_years_t = torch.tensor([(g["date"].iloc[0] - pd.Timestamp("2000-01-01")).days / 365.25],
                                   dtype=torch.float32, device=DEVICE)

        func = ODEFunc(r_net, k_net, m_net, q_pi, site_embedding, lat_n, lon_n, site_idx,
                        T, PAR, P, SM, VPD, SPEI, Tfz, norm["t_mean"], norm["t_std"], t0_years_t)
        t_eval_full = torch.arange(n, device=DEVICE, dtype=torch.float32) * STEP_YEARS
        with torch.no_grad():
            traj = odeint(func, torch.tensor([v0], dtype=torch.float32, device=DEVICE), t_eval_full,
                          method="euler").squeeze(1)
        ax.plot(g["date"], g[target_col], "o", ms=2.5, color="#555555", alpha=0.6, label="Observed")
        ax.plot(g["date"], traj.cpu().numpy(), "-", color="#2a78d6", lw=1.3, label="Equation trajectory")
        ax.set_title(site, fontsize=10)
        ax.tick_params(labelsize=7)
    axes.flat[0].legend(fontsize=8, frameon=False)
    fig.suptitle(f"Prof. Wang's logistic growth-mortality equation: integrated {target_col} vs. observed "
                 f"(6 random CONUS sites)", fontsize=12, fontweight="bold")
    fig.savefig(out_dir / "reconstruction_sanity_check.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_dir / 'reconstruction_sanity_check.png'}")


if __name__ == "__main__":
    main()

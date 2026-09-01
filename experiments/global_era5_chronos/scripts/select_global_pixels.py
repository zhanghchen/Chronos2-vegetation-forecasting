# Global, non-U.S. pixel selection for the ERA5+Chronos-2 evaluation
# (Part 9-10). Uses the full-resolution global ESA CCI PFT product
# (/shared/.../Global_PFTs/, 300m native, verified NOT limited to CONUS -
# unlike our regridded PFTs_regrid_to_gridMET copy) to build a
# PFT-diverse, geographically-spread candidate set via farthest-point
# sampling, explicitly excluding the CONUS bounding box already covered
# by every prior experiment in this project.
#
# This does NOT depend on ERA5 or a global LAI product - it only needs
# the already-available global PFT file - so it can run independently of
# the (slow, CDS-rate-limited) ERA5 download work.
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

PFT_FILE = "/shared/guw02001/hoq23003/DL4Vegetation/Data/Global_PFTs/ESACCI-LC-L4-PFT-Map-300m-P1Y-2020-v2.0.8.nc"
OUT_DIR = Path(__file__).resolve().parent.parent / "data_selection"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ESA CCI class names as stored in the file (hyphens, not underscores -
# different from our CONUS regrid copy's variable names, which use "_").
CLASSES = [
    "TREES-NE", "TREES-BD", "TREES-BE", "TREES-ND",
    "SHRUBS-NE", "SHRUBS-BE", "SHRUBS-BD", "SHRUBS-ND",
    "GRASS-NAT", "GRASS-MAN",
]
NONVEG_CLASSES = ["BARE", "BUILT", "SNOWICE", "WATER_INLAND", "WATER_OCEAN"]

CANDIDATE_GRID_DEG = 1.0  # candidate lattice spacing - coarse enough to keep the point-lookup count manageable
MIN_SEPARATION_KM = 800   # minimum great-circle separation between selected pixels
N_TARGET = 45
SEED = 42

# CONUS bounding box already covered by every prior experiment in this
# project - excluded here since Part 8 requires the primary experiment to
# be OUTSIDE the United States.
CONUS_BBOX = dict(lat_min=24.0, lat_max=50.0, lon_min=-125.5, lon_max=-66.0)
# Rough exclusions for other US territory (Alaska, Hawaii) so "non-U.S."
# is not violated by an edge case.
ALASKA_BBOX = dict(lat_min=51.0, lat_max=72.0, lon_min=-180.0, lon_max=-129.0)
HAWAII_BBOX = dict(lat_min=18.0, lat_max=23.0, lon_min=-161.0, lon_max=-154.0)


def in_bbox(lat, lon, bbox):
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"])


def is_us(lat, lon):
    return in_bbox(lat, lon, CONUS_BBOX) or in_bbox(lat, lon, ALASKA_BBOX) or in_bbox(lat, lon, HAWAII_BBOX)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def build_candidate_pool():
    ds = nc.Dataset(PFT_FILE)
    file_lat = ds.variables["lat"][:]   # 64800, native ~300m grid
    file_lon = ds.variables["lon"][:]   # 129600
    lat_step = float(file_lat[1] - file_lat[0])
    lon_step = float(file_lon[1] - file_lon[0])
    print(f"Native grid: {len(file_lat)}x{len(file_lon)}, lat_step={lat_step:.6f}, lon_step={lon_step:.6f}")

    # native step is exactly 1/360 degree, so a stride of 360 gives an
    # EXACT 1.0-degree lattice - a single aligned hyperslab (strided) read
    # per class covers the whole globe in one call. This replaced an
    # earlier version that used fancy/scattered indexing for the same
    # ~49K candidate points, which never finished (>115s with zero
    # progress) - HDF5 fancy-indexing across arbitrary, widely-separated
    # chunk boundaries is far slower than one strided hyperslab read.
    stride = int(round(CANDIDATE_GRID_DEG / abs(lat_step)))
    assert abs(stride * abs(lat_step) - CANDIDATE_GRID_DEG) < 1e-6, "CANDIDATE_GRID_DEG must be a multiple of the native step"

    all_classes = CLASSES + NONVEG_CLASSES
    print(f"Reading {len(all_classes)} classes at stride {stride} (one hyperslab read each)...", flush=True)
    grids = {}
    for c in all_classes:
        grids[c] = np.asarray(ds.variables[c][0, ::stride, ::stride])
        print(f"  {c}: {grids[c].shape}", flush=True)
    ds.close()

    lat_grid = np.asarray(file_lat[::stride])
    lon_grid = np.asarray(file_lon[::stride])
    lat2d, lon2d = np.meshgrid(lat_grid, lon_grid, indexing="ij")

    veg_stack = np.stack([grids[c] for c in CLASSES], axis=-1).astype(float)
    nonveg_total = sum(grids[c].astype(float) for c in NONVEG_CLASSES)
    veg_total = veg_stack.sum(axis=-1)

    lat_ok = (lat2d >= -60) & (lat2d <= 76)
    us_mask = np.zeros_like(lat2d, dtype=bool)
    for bbox in [CONUS_BBOX, ALASKA_BBOX, HAWAII_BBOX]:
        us_mask |= (lat2d >= bbox["lat_min"]) & (lat2d <= bbox["lat_max"]) & (lon2d >= bbox["lon_min"]) & (lon2d <= bbox["lon_max"])
    mask = lat_ok & (~us_mask) & (veg_total >= 40)

    rr, cc = np.where(mask)
    rows = []
    for r, c_ in zip(rr, cc):
        frac = {cls: float(veg_stack[r, c_, k]) for k, cls in enumerate(CLASSES)}
        rows.append({"lat": float(lat2d[r, c_]), "lon": float(lon2d[r, c_]),
                      "row": int(r), "col": int(c_), "nonveg_frac": float(nonveg_total[r, c_]), **frac})
    df = pd.DataFrame(rows)
    print(f"Candidate pool after land/vegetation filter: {len(df)} points")
    return df


def farthest_point_sample(df, n_target, min_sep_km):
    frac = df[[f"{c}" for c in CLASSES]].to_numpy() / 100.0
    frac = frac / np.clip(frac.sum(axis=1, keepdims=True), 1e-6, None)
    coords = df[["lat", "lon"]].to_numpy()

    rng = np.random.default_rng(SEED)
    # seed with one purity-extremal candidate per class so sampling reliably
    # reaches the corners of composition space
    seed_idx = []
    for j in range(frac.shape[1]):
        idx = int(np.argmax(frac[:, j]))
        if frac[idx, j] > 0.85:
            seed_idx.append(idx)
    seed_idx = list(dict.fromkeys(seed_idx))

    selected = list(seed_idx)
    selected_mask = np.zeros(len(df), dtype=bool)
    selected_mask[selected] = True

    while selected_mask.sum() < n_target:
        d_feat = np.linalg.norm(frac[None, :, :] - frac[selected_mask][:, None, :], axis=-1).min(axis=0)
        # geographic separation (vectorized haversine against all selected)
        sel_coords = coords[selected_mask]
        geo_d = np.min(
            [haversine_km(coords[:, 0], coords[:, 1], sc[0], sc[1]) for sc in sel_coords], axis=0
        )
        eligible = (geo_d >= min_sep_km) & (~selected_mask)
        if not eligible.any():
            print("Ran out of geographically-eligible candidates before reaching n_target.")
            break
        d_feat_masked = np.where(eligible, d_feat, -np.inf)
        next_idx = int(np.argmax(d_feat_masked))
        selected_mask[next_idx] = True
    return np.where(selected_mask)[0], frac


REGION_BOXES = [
    ("Amazon / Tropical S. America", -20, 12, -80, -45),
    ("Southern S. America", -56, -20, -76, -34),
    ("Western Europe", 43, 60, -10, 15),
    ("Eastern Europe", 45, 60, 15, 40),
    ("Mediterranean", 30, 45, -10, 36),
    ("Central/Southern Africa", -35, -5, 10, 40),
    ("East Africa / Sahel", -5, 18, 20, 50),
    ("South Asia", 5, 35, 65, 92),
    ("East Asia", 20, 53, 100, 145),
    ("Southeast Asia", -10, 20, 92, 140),
    ("Central Asia", 35, 55, 45, 90),
    ("Australia", -44, -10, 112, 154),
    ("Siberia / Boreal Eurasia", 55, 72, 40, 180),
    ("Canada", 42, 75, -141, -52),
    ("Middle East", 12, 40, 36, 63),
]


def region_of(lat, lon):
    for name, lat_min, lat_max, lon_min, lon_max in REGION_BOXES:
        if lat_min <= lat < lat_max and lon_min <= lon < lon_max:
            return name
    return "Other"


def main():
    df = build_candidate_pool()
    idx, frac = farthest_point_sample(df, N_TARGET, MIN_SEPARATION_KM)
    sel = df.iloc[idx].reset_index(drop=True)
    sel_frac = frac[idx]

    dom_idx = sel_frac.argmax(axis=1)
    sel["dominant_pft"] = [CLASSES[i] for i in dom_idx]
    sel["pft_purity"] = sel_frac.max(axis=1)
    p = np.clip(sel_frac, 1e-12, None)
    sel["pft_entropy"] = -(p * np.log(p)).sum(axis=1)
    sel["region"] = [region_of(la, lo) for la, lo in zip(sel.lat, sel.lon)]
    sel["pixel_id"] = [f"g{i:03d}_{d.lower().replace('-', '_')}" for i, d in enumerate(sel.dominant_pft)]

    out_cols = ["pixel_id", "lat", "lon", "region", "dominant_pft", "pft_purity", "pft_entropy"] + list(CLASSES)
    sel[out_cols].to_csv(OUT_DIR / "global_candidate_pixels.csv", index=False)

    print(f"\nSelected {len(sel)} non-U.S. global pixels.")
    print(sel["dominant_pft"].value_counts())
    print(f"\nPurity range: {sel['pft_purity'].min():.2f} - {sel['pft_purity'].max():.2f}")
    print(f"\nRegion counts:\n{sel['region'].value_counts()}")
    print(f"\nSaved to {OUT_DIR / 'global_candidate_pixels.csv'}")


if __name__ == "__main__":
    main()
